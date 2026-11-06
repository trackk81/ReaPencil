"""Persistent OpenCL viewport scene: GPU BVH refit, intersections and edge tests.

CPU builds connectivity/Morton order once. Every geometry update refits the BVH
and computes complete triangle intersections on the GPU (no cached pair list).
Endpoints are read back for Maya's MUIDrawManager; this is not zero-copy drawing.
"""
import math
import time
import numpy as np
from .opencl_runtime import Runtime
from .gpu_kernels import SOURCE as GEOMETRY_SOURCE
from .gpu_visibility import SOURCE as VISIBILITY_SOURCE
SOURCE = GEOMETRY_SOURCE + VISIBILITY_SOURCE


def morton_order(points):
    lo, hi = points.min(axis=0), points.max(axis=0)
    q = ((points-lo)/np.maximum(hi-lo, 1e-30)*1048575).astype(np.uint64)
    def spread(value):
        value=value.copy()
        for shift,mask in ((32,0x1f00000000ffff),(16,0x1f0000ff0000ff),
                           (8,0x100f00f00f00f00f),(4,0x10c30c30c30c30c3),(2,0x1249249249249249)):
            value=(value|(value<<np.uint64(shift)))&np.uint64(mask)
        return value
    code=spread(q[:,0])|(spread(q[:,1])<<np.uint64(1))|(spread(q[:,2])<<np.uint64(2))
    return np.argsort(code, kind='stable')


class GPUScene:
    def __init__(self, meshes, max_intersections=200000, runtime=None):
        from .gpu_topology import prepare
        start = time.perf_counter()
        self._owns_runtime = runtime is None
        self.runtime = r = Runtime() if runtime is None else runtime
        if self._owns_runtime:r.build(SOURCE)
        self.program_ms=(time.perf_counter()-start)*1000
        self.buffers = []
        self.meshes = meshes
        self.capacity = max_intersections
        self.offsets = np.cumsum([0]+[len(m['vertices']) for m in meshes])
        vertices = np.concatenate([np.asarray(m['vertices'], np.float64) for m in meshes])
        triangles, owners, triangle_faces, global_faces = [], [], [], []
        pairs, ranges, adjacent, metadata, edge_owners = [], [], [], [], []
        polygon_vertices, polygon_ranges = [], []
        outline_indices, diagonal_pairs, diagonal_faces, diagonal_owners = [], [], [], []
        topology_start=time.perf_counter()
        prepared=[mesh.get('_gpu_topology') or prepare(mesh) for mesh in meshes]
        for mesh,p in zip(meshes,prepared):
            if mesh.get('_retain_topology'):mesh['_gpu_topology']=p
        polygon_edge_count=sum(len(p['pairs']) for p in prepared)
        pair_offset=diagonal_offset=0
        face_offset = edge_offset = vertex_cursor = 0
        for mi, (mesh,p) in enumerate(zip(meshes,prepared)):
            offset = self.offsets[mi]
            faces = mesh['faces']
            tris=p['triangles'];tfaces=p['triangle_faces']
            triangles.append(tris+offset)
            owners.append(np.full(len(tris),mi,np.int32))
            triangle_faces.append(tfaces)
            global_faces.append(tfaces+face_offset)
            pairs.append(p['pairs']+offset)
            ranges.append(np.column_stack((p['starts']+edge_offset,p['counts'])))
            adjacent.append(p['owners']+face_offset)
            metadata.append(p['metadata'])
            edge_owners.append(np.full(len(p['pairs']),mi,np.int32))
            edge_offset += len(p['owners'])
            polygon_ranges.append(np.column_stack((p['face_starts']+vertex_cursor,p['face_counts'])))
            polygon_vertices.append(p['flat']+offset)
            vertex_cursor+=len(p['flat'])
            ids=p['outline_indices'];original=ids<len(p['pairs'])
            outline_indices.append((ids+np.where(original,pair_offset,polygon_edge_count+diagonal_offset-len(p['pairs']))).astype(np.int32))
            diagonal_pairs.append(p['diagonal_pairs']+offset)
            diagonal_faces.append(p['diagonal_faces']+face_offset)
            diagonal_owners.append(np.full(len(p['diagonal_pairs']),mi,np.int32))
            pair_offset+=len(p['pairs']);diagonal_offset+=len(p['diagonal_pairs'])
            face_offset += len(faces)
        self.topology_ms=(time.perf_counter()-topology_start)*1000
        del prepared
        triangles = np.concatenate(triangles).astype(np.int32)
        self.triangle_count = len(triangles)
        if not self.triangle_count:
            raise ValueError('GPU viewport requires triangles')
        morton_start=time.perf_counter()
        order = morton_order(vertices[triangles].mean(axis=1))
        self.morton_ms=(time.perf_counter()-morton_start)*1000
        self.base = 1 << (self.triangle_count-1).bit_length()
        if self.base > 2**24:
            raise ValueError('GPU BVH allocation exceeds viewport budget')
        estimated=(self.base*2*36+vertices.nbytes+self.triangle_count*80+
                   polygon_edge_count*108+diagonal_offset*96+face_offset*72+64000000+self.capacity*76)
        # Reserve most VRAM for Maya and other applications. A fixed 512 MiB
        # ceiling wrongly rejected authored smooth scenes on large GPUs.
        budget=min(2*1024**3, r.global_memory_bytes//5)
        self.memory_budget=budget
        if estimated>budget:
            raise ValueError('GPU scene requires %.1f MiB; device-aware budget is %.1f MiB' %
                             (estimated/1024**2,budget/1024**2))
        self.estimated_gpu_bytes=estimated
        self.vertices = self.buf(vertices)
        self.triangles = self.buf(triangles[order])
        self._triangle_owners_cpu=np.concatenate(owners).astype(np.int32)[order]
        self._mesh_triangle_indices=[np.flatnonzero(self._triangle_owners_cpu==i).astype(np.int32) for i in range(len(meshes))]
        self._mesh_face_offsets=np.cumsum([0]+[len(m['faces']) for m in meshes])
        self.owners = self.buf(self._triangle_owners_cpu)
        self.triangle_faces = self.buf(np.concatenate(triangle_faces).astype(np.int32)[order])
        self._triangle_global_faces=np.concatenate(global_faces).astype(np.int32)[order]
        self.outline_indices=self.buf(np.concatenate(outline_indices).astype(np.int32)[order])
        self.diagonal_count=diagonal_offset
        self.diagonal_pairs=self.buf(np.concatenate(diagonal_pairs).astype(np.int32))
        self.diagonal_faces=self.buf(np.concatenate(diagonal_faces).astype(np.int32))
        self.diagonal_owners=self.buf(np.concatenate(diagonal_owners).astype(np.int32))
        self.outline_counts=self.buf((polygon_edge_count+diagonal_offset)*4)
        self.lo, self.hi = self.buf(self.base*2*16), self.buf(self.base*2*16)
        self.triangle_normals = self.buf(len(triangles)*32)
        self.metrics = self.buf(len(triangles)*16)
        self.pairs = self.buf(np.concatenate(pairs).astype(np.int32))
        self._pairs_cpu=np.concatenate(pairs).astype(np.int32)
        self._edge_lookup=None
        self.edge_count = sum(len(p) for p in pairs)
        self._selected_style_values=np.full(self.edge_count,-3,np.int32)
        self.selected_styles=self.buf(self._selected_style_values)
        self.ranges = self.buf(np.concatenate(ranges).astype(np.int32))
        self.adjacent = self.buf(np.concatenate(adjacent).astype(np.int32))
        self.metadata = self.buf(np.concatenate(metadata).astype(np.int32))
        self.edge_owners = self.buf(np.concatenate(edge_owners).astype(np.int32))
        self.polygon_vertices = self.buf(np.concatenate(polygon_vertices).astype(np.int32))
        self.polygon_ranges = self.buf(np.concatenate(polygon_ranges).astype(np.int32))
        self.face_count = face_offset
        self.normals, self.centers = self.buf(self.face_count*32), self.buf(self.face_count*32)
        output_capacity=self.edge_count+self.diagonal_count
        self.edge_output, self.edge_output_owners = self.buf(output_capacity*64),self.buf(output_capacity*4)
        self.edge_output_meta=self.buf(output_capacity*8)
        self.last_edge_meta=None
        self.cross_output, self.cross_output_owners = self.buf(self.capacity*64),self.buf(self.capacity*4)
        self.cross_mesh_pairs = self.buf(self.capacity*8)
        self.counter = self.buf(np.zeros(1,np.int32))
        self.candidate_capacity = 8000000
        self.candidates = self.buf(self.candidate_capacity*8)
        self.camera = self.buf(7*8)
        self.features, self.crease, self.modes = self.buf(len(meshes)*4),self.buf(len(meshes)*8),self.buf(len(meshes)*8)
        self._style_capacity=len(meshes)
        self._face_style_values=np.concatenate([np.full(len(m['faces']),i,np.int32) for i,m in enumerate(meshes)])
        self.face_styles=self.buf(self._face_style_values)
        self.triangle_styles=self.buf(self._face_style_values[self._triangle_global_faces])
        self.last_modes = None
        self.cross_cache = None
        self.cross_pairs_cpu=None
        self._pending_mesh_changes=set()
        self.dirty_nodes=self.buf(self.base*2*4)
        self.dirty_meshes=self.buf(len(meshes)*4)
        self.visibility_static_prefix=0
        self.update(vertices)
        self.build_ms = (time.perf_counter()-start)*1000

    def buf(self, value):
        b = self.runtime.buffer(value)
        self.buffers.append(b)
        return b

    def close(self):
        history=getattr(self,'visibility_history',None)
        if history is not None:
            history[1].close();self.visibility_history=None
        for b in getattr(self,'buffers',[]):
            b.close()
        if hasattr(self,'buffers'):
            self.buffers.clear()
        if hasattr(self,'runtime') and getattr(self,'_owns_runtime',True):
            self.runtime.close()

    def __del__(self):
        self.close()

    def update(self, vertices, changed_meshes=None):
        r = self.runtime
        vertices=np.asarray(vertices,np.float64)
        changed=None if changed_meshes is None else sorted(set(map(int,changed_meshes)))
        if changed is not None and any(i<0 or i>=len(self.meshes) for i in changed):raise ValueError('Invalid changed mesh index')
        partial=changed is not None and 0<len(changed)<len(self.meshes)
        temporary=[]
        flags=np.ones(len(self.meshes),np.int32)
        if partial:
            flags[:]=0;flags[list(self._pending_mesh_changes.union(changed))]=1
        r.write(self.dirty_meshes,flags)
        r.run('dirty_leaves',self.base,self.owners,self.dirty_meshes,self.dirty_nodes,self.triangle_count,self.base,local_size=64)
        self.visibility_static_prefix=0
        if partial:
            for i in changed:
                start,end=self.offsets[i:i+2]
                r.write(self.vertices,vertices[start:end],offset=int(start)*24)
            ids=np.concatenate([self._mesh_triangle_indices[i] for i in changed])
            tb=r.buffer(ids);temporary.append(tb)
            r.run('triangles_indexed',len(ids),self.vertices,self.triangles,self.lo,self.hi,self.triangle_normals,self.metrics,self.triangle_count,self.base,tb,len(ids),local_size=64)
        else:
            r.write(self.vertices, vertices)
            r.run('triangles', self.base, self.vertices,self.triangles,self.lo,self.hi,self.triangle_normals,self.metrics,self.triangle_count,self.base,local_size=64)
        start = self.base//2
        while start:
            r.run('refit',start,self.lo,self.hi,start,self.dirty_nodes,local_size=64)
            start//=2
        if partial:
            ids=np.concatenate([np.arange(self._mesh_face_offsets[i],self._mesh_face_offsets[i+1],dtype=np.int32) for i in changed])
            fb=r.buffer(ids);temporary.append(fb)
            r.run('polygon_normals_indexed',len(ids),self.vertices,self.polygon_vertices,self.polygon_ranges,self.normals,self.centers,self.face_count,fb,len(ids),local_size=64)
            self._pending_mesh_changes.update(changed)
        else:
            r.run('polygon_normals',self.face_count,self.vertices,self.polygon_vertices,self.polygon_ranges,self.normals,self.centers,self.face_count,local_size=64)
            self.cross_cache = None
            self._pending_mesh_changes.clear()
        for b in temporary:b.close()

    def configure_face_styles(self, face_style_ids, style_count, selected_edges=None):
        """Keep original topology/adjacency; only change the per-face targets."""
        values=np.concatenate(face_style_ids).astype(np.int32)
        if len(values)!=self.face_count or np.any(values>=style_count) or np.any(values < -1):
            raise ValueError('Invalid GPU face style assignment')
        if style_count>self._style_capacity:
            for old in (self.features,self.crease,self.modes):
                old.close();self.buffers.remove(old)
            self.features,self.crease,self.modes=self.buf(style_count*4),self.buf(style_count*8),self.buf(style_count*8)
            self._style_capacity=style_count
        if not np.array_equal(values,self._face_style_values):
            self.runtime.write(self.face_styles,values)
            self.runtime.write(self.triangle_styles,values[self._triangle_global_faces])
            self._face_style_values=values
            self.cross_cache=None
        selected=np.full(self.edge_count,-3 if selected_edges is None else -2,np.int32)
        if selected_edges is not None and any(len(pairs) for per_mesh in selected_edges for pairs in per_mesh.values()):
            if self._edge_lookup is None:
                self._edge_lookup=(self._pairs_cpu[:,0].astype(np.uint64)<<np.uint64(32))|self._pairs_cpu[:,1].astype(np.uint64)
            for mesh_index,style_edges in enumerate(selected_edges):
                offset=self.offsets[mesh_index]
                for style,pairs in style_edges.items():
                    if not len(pairs):continue
                    vertices=np.sort(np.asarray(pairs,np.uint64).reshape(-1,2)+np.uint64(offset),axis=1)
                    keys=(vertices[:,0]<<np.uint64(32))|vertices[:,1]
                    indices=np.searchsorted(self._edge_lookup,keys)
                    valid=indices<len(self._edge_lookup)
                    valid[valid]=self._edge_lookup[indices[valid]]==keys[valid]
                    indices=indices[valid]
                    selected[indices]=np.where(selected[indices]>=0,np.minimum(selected[indices],int(style)),int(style))
        if not np.array_equal(selected,self._selected_style_values):
            self.runtime.write(self.selected_styles,selected)
            self._selected_style_values=selected

    def intersections(self, styles, tolerance=1e-7):
        modes = np.asarray([[s.get('intersections',False),s.get('self_intersections',False)] for s in styles],np.int32)
        key = (modes.tobytes(),tolerance)
        if self.cross_cache is not None and self.last_modes == key and not self._pending_mesh_changes:
            return self.cross_cache
        r = self.runtime
        r.write(self.modes,modes)
        r.write(self.counter,np.zeros(1,np.int32))
        start = time.perf_counter()
        candidates = 0
        previous=self.cross_cache
        self.visibility_static_prefix=0
        dirty=sorted(self._pending_mesh_changes)
        incremental=bool(previous is not None and self.last_modes==key and dirty and self.cross_pairs_cpu is not None)
        reused=0
        if incremental:
            keep=~np.isin(self.cross_pairs_cpu,dirty).any(axis=1)
            reused=int(keep.sum())
            work_ids=np.concatenate([self._mesh_triangle_indices[i] for i in dirty])
            # A full update can be cheaper when most meshes change. Both paths
            # enumerate every eligible pair; this threshold never drops lines.
            if len(work_ids)>self.triangle_count*.5:incremental=False;reused=0
        if incremental:
            # Ping-pong resident output: static strokes stay on the GPU; newly
            # computed intersections are appended behind the preserved prefix.
            spare=getattr(self,'_cross_spare',None)
            if spare is None or spare[0].size<self.capacity*64:
                prior_bytes=sum(b.size for b in spare) if spare else 0
                extra=self.capacity*76-prior_bytes
                if self.estimated_gpu_bytes+extra>self.memory_budget:
                    raise RuntimeError('GPU intersection cache exceeds device memory budget')
                if spare:
                    for b in spare:b.close();self.buffers.remove(b)
                spare=tuple(self.buf(self.capacity*stride) for stride in (64,4,8))
                self.estimated_gpu_bytes+=extra
            old_outputs=(self.cross_output,self.cross_output_owners,self.cross_mesh_pairs)
            self.cross_output,self.cross_output_owners,self.cross_mesh_pairs=spare
            self._cross_spare=old_outputs
        if modes.any():
            if incremental:
                changed=np.zeros(len(self.meshes),np.int32);changed[dirty]=1
                wb,cb=r.buffer(work_ids),r.buffer(changed)
                try:r.run('candidates_indexed',len(work_ids),self.triangles,self.owners,self.triangle_faces,self.lo,self.hi,self.modes,self.candidates,self.counter,self.triangle_count,self.base,float(tolerance),self.candidate_capacity,self.triangle_styles,wb,cb,len(work_ids),local_size=64)
                finally:wb.close();cb.close()
            else:
                r.run('candidates',self.triangle_count,self.triangles,self.owners,self.triangle_faces,self.lo,self.hi,
                      self.modes,self.candidates,self.counter,self.triangle_count,self.base,float(tolerance),self.candidate_capacity,self.triangle_styles,local_size=64)
            candidates=int(r.read(self.counter,1,np.int32)[0])
            if candidates>self.candidate_capacity:
                raise RuntimeError('GPU candidate buffer exceeded; partial lines discarded')
            while True:
                r.write(self.counter,np.zeros(1,np.int32))
                r.run('intersections',candidates,self.vertices,self.triangles,self.owners,self.triangle_faces,
                      self.lo,self.hi,self.triangle_normals,self.metrics,self.modes,self.cross_output,self.cross_output_owners,self.cross_mesh_pairs,
                      self.counter,candidates,self.base,float(tolerance),self.capacity,self.candidates,self.triangle_styles,reused,local_size=64)
                required=reused+int(r.read(self.counter,1,np.int32)[0])
                if required<=self.capacity:
                    break
                # The first pass counts ALL intersections even after the output
                # fills. Allocate from that count and rerun the same candidates;
                # never display truncated lines or change geometric tolerances.
                capacity=max(required,int(self.capacity*1.5))
                extra=(capacity-self.capacity)*76
                if self.estimated_gpu_bytes+extra>self.memory_budget:
                    raise RuntimeError('GPU intersection output exceeds device memory budget; partial lines discarded')
                for name,stride in (('cross_output',64),('cross_output_owners',4),('cross_mesh_pairs',8)):
                    old=getattr(self,name)
                    old.close();self.buffers.remove(old)
                    setattr(self,name,self.buf(capacity*stride))
                self.estimated_gpu_bytes+=extra
                self.capacity=capacity
        count = int(r.read(self.counter,1,np.int32)[0])
        if reused+count>self.capacity:
            raise RuntimeError('GPU intersection capacity exceeded (%d > %d); partial lines discarded' % (count,self.capacity))
        points = r.read(self.cross_output,(count*2,4),offset=reused*64)
        owners = r.read(self.cross_output_owners,count,np.int32,offset=reused*4)
        pairs=r.read(self.cross_mesh_pairs,(count,2),np.int32,offset=reused*8)
        if incremental:
            keep_ids=np.flatnonzero(keep).astype(np.int32)
            kb=r.buffer(keep_ids)
            try:r.run('preserve_cross',reused,*old_outputs,self.cross_output,self.cross_output_owners,self.cross_mesh_pairs,kb,reused,local_size=64)
            finally:kb.close()
            total=reused+count
            joined=np.empty((total*2,4),np.float64)
            np.compress(keep,previous[0].reshape(-1,2,4),axis=0,out=joined[:reused*2].reshape(-1,2,4))
            joined[reused*2:]=points;points=joined
            owners=np.concatenate((previous[1][keep],owners))
            pairs=np.concatenate((self.cross_pairs_cpu[keep],pairs))
            if (getattr(self,'visibility_history_source',None) is previous[0] and
                    len(getattr(self,'visibility_last_blockers',[]))==len(previous[1])):
                hints=np.r_[self.visibility_last_blockers[keep],np.full(count,-1,np.int32)].astype(np.int32)
                history=getattr(self,'visibility_history',None)
                if history is not None:history[1].close()
                self.visibility_history=(total,r.buffer(hints))
                self.visibility_history_camera=getattr(self,'visibility_last_camera',None)
                self.visibility_static_prefix=reused
            count=total
        self.cross_pairs_cpu=pairs
        self._pending_mesh_changes.clear()
        self.cross_cache = (points,owners,dict(backend='opencl_gpu',device=r.name,segments=count,
            triangles=self.triangle_count,candidate_pairs=candidates,incremental=incremental,reused_static_segments=reused,
            evaluated_triangles=len(work_ids) if incremental else self.triangle_count,gpu_intersection_readback_ms=(time.perf_counter()-start)*1000))
        self.last_modes = key
        return self.cross_cache

    def edges(self, styles, camera, merge_groups=None, width=640, height=480):
        from .renderer import EDGE_FEATURES
        feature_keys = ('wireframe','open_edges','outline','crease','material_boundaries','hard_edges','selected_edges')
        r = self.runtime
        features = np.asarray([sum((1<<i) for i,key in enumerate(feature_keys) if s.get(key,False)) for s in styles],np.int32)
        crease = np.asarray([math.cos(math.radians(s.get('crease_angle',45))) for s in styles],np.float64)
        eye = np.asarray(camera['position'],np.float64)
        forward = np.asarray(camera['target'],np.float64)-eye
        forward /= max(np.linalg.norm(forward),1e-30)
        r.write(self.camera,np.concatenate((eye,forward,[camera.get('projection')=='orthographic'])))
        r.write(self.features,features)
        r.write(self.crease,crease)
        r.write(self.counter,np.zeros(1,np.int32))
        if np.any(features&4):
            r.run('clear_outline_counts',self.edge_count+self.diagonal_count,self.outline_counts,self.edge_count+self.diagonal_count,local_size=64)
            r.run('triangle_outline_counts',self.triangle_count,self.vertices,self.triangles,
                  self.outline_indices,self.camera,self.outline_counts,self.triangle_count,local_size=64)
        r.run('edges',self.edge_count,self.vertices,self.pairs,self.ranges,self.adjacent,self.metadata,
              self.edge_owners,self.normals,self.centers,self.features,self.crease,self.camera,
              self.edge_output,self.edge_output_owners,self.counter,self.face_styles,self.selected_styles,self.edge_output_meta,self.outline_counts,self.edge_count,local_size=64)
        if self.diagonal_count and np.any(features&4):
            r.run('diagonal_outlines',self.diagonal_count,self.vertices,self.diagonal_pairs,self.diagonal_faces,
                  self.diagonal_owners,self.outline_counts,self.edge_count,self.features,self.face_styles,
                  self.edge_output,self.edge_output_owners,self.counter,self.edge_output_meta,self.diagonal_count,local_size=64)
        count = int(r.read(self.counter,1,np.int32)[0])
        if getattr(self,'clip_edges',False):
            from .gpu_paged import clipped_edges
            points,owners,self.last_edge_meta=clipped_edges(self,count,camera)
        else:points,owners=r.read(self.edge_output,(count*2,4)),r.read(self.edge_output_owners,count,np.int32)
        self.merge_diagnostics=dict(samples=0,suppressed_samples=0)
        if merge_groups and count:
            self.last_edge_meta=r.read(self.edge_output_meta,(count,2),np.int32)
            from .gpu_merge import filter_outlines
            points,owners,self.merge_diagnostics=filter_outlines(self,points,owners,styles,camera,merge_groups,width,height)
        return points,owners

    def nearest_mesh(self, origins, directions, near, far):
        """GPU BVH ray queries; bounded chunks keep temporary allocation small."""
        result=[]
        for start in range(0,len(origins),65536):
            a=np.ascontiguousarray(origins[start:start+65536],np.float64)
            b=np.ascontiguousarray(directions[start:start+65536],np.float64)
            buffers=[]
            try:
                for value in (a,b,len(a)*4):buffers.append(self.runtime.buffer(value))
                self.runtime.run('nearest_mesh',len(a),self.vertices,self.triangles,self.owners,self.lo,self.hi,
                                 *buffers,self.base,len(a),float(near),float(far),local_size=64)
                result.append(self.runtime.read(buffers[2],len(a),np.int32))
            finally:
                for buffer in buffers:buffer.close()
        return np.concatenate(result) if result else np.empty(0,np.int32)
