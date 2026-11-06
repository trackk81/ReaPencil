"""Memory-bounded, spatially paged GPU viewport for large Maya scenes.

No geometry decimation or segment cap: pages retain whole-mesh adjacency,
cross-page triangle pairs use the same predicates, and visibility queries visit
every relevant page. Evicted static GPU arrays are backed by private temp files.
The CPU final renderer does not import this module.
"""
from collections import OrderedDict
from pathlib import Path
import tempfile
import time
import numpy as np
from .gpu_geometry import GPUScene, SOURCE, morton_order
from .gpu_paged_kernels import SOURCE as PAGE_SOURCE
from .opencl_runtime import Runtime, Buffer


def clip_mask(runtime,points_buffer,count,camera):
    clip=camera.get('viewport_clip')
    if not count or clip is None:return np.ones(count,bool)
    matrix=runtime.buffer(np.asarray(clip['matrix'],np.float64))
    flags=runtime.buffer(np.full(count,-1,np.int32))
    try:
        margin=float(clip.get('margin_pixels',8))
        runtime.run('rt_clip_segments',count,points_buffer,matrix,flags,count,
            2*margin/max(1,clip['width']),2*margin/max(1,clip['height']),local_size=64)
        return runtime.read(flags,count,np.int32)!=-5
    finally:matrix.close();flags.close()


def clipped_edges(gpu,count,camera):
    r=gpu.runtime;indices=np.flatnonzero(clip_mask(r,gpu.edge_output,count,camera)).astype(np.int32)
    if len(indices)==count:
        return r.read(gpu.edge_output,(count*2,4)),r.read(gpu.edge_output_owners,count,np.int32),r.read(gpu.edge_output_meta,(count,2),np.int32)
    buffers=[r.buffer(indices),r.buffer(len(indices)*64),r.buffer(len(indices)*4),r.buffer(len(indices)*8)]
    try:
        r.run('page_gather_edges',len(indices),gpu.edge_output,gpu.edge_output_owners,gpu.edge_output_meta,*buffers,len(indices),local_size=64)
        return r.read(buffers[1],(len(indices)*2,4)),r.read(buffers[2],len(indices),np.int32),r.read(buffers[3],(len(indices),2),np.int32)
    finally:
        for b in buffers:b.close()


def visible_bounds(bounds, camera):
    """Conservative whole-box frustum rejection, including wide-line margin."""
    bounds=np.asarray(bounds,np.float64)
    clip=camera.get('viewport_clip')
    if clip is None:return np.ones(len(bounds),bool)
    matrix=np.asarray(clip['matrix'],np.float64).reshape(4,4)
    margin=float(clip.get('margin_pixels',8))
    visible=np.ones(len(bounds),bool)
    center=(bounds[:,0]+bounds[:,1])*.5;radius=(bounds[:,1]-bounds[:,0])*.5
    w=matrix[:,3]
    for axis,dimension in ((0,'width'),(1,'height')):
        m=2*margin/max(1,clip[dimension])
        for sign in (-1,1):
            plane=w+sign*matrix[:,axis]
            maximum=center@plane[:3]+plane[3]+radius@np.abs(plane[:3])
            wmax=np.abs(center@w[:3]+w[3])+radius@np.abs(w[:3])
            error=128*np.finfo(float).eps*(np.abs(center)@np.abs(plane[:3])+abs(plane[3])+radius@np.abs(plane[:3]))+1e-9
            visible &= maximum >= -m*wmax-error
    return visible


def ray_box_candidates(points, eye, bounds):
    """A blocker of a whole stroke must intersect its midpoint sightline."""
    delta=points[:,:,:3].mean(axis=1)-eye
    low=np.zeros(len(delta));high=np.ones(len(delta))
    for axis in range(3):
        d=delta[:,axis];parallel=np.abs(d)<1e-30
        valid=(eye[axis]>=bounds[0,axis])&(eye[axis]<=bounds[1,axis])
        high[parallel & ~valid]=-1
        safe=np.where(parallel,1.,d)
        a=(bounds[0,axis]-eye[axis])/safe;b=(bounds[1,axis]-eye[axis])/safe
        low=np.maximum(low,np.where(parallel,-np.inf,np.minimum(a,b)))
        high=np.minimum(high,np.where(parallel,np.inf,np.maximum(a,b)))
    return low<=high+1e-12


class _Page:
    # Scratch/output buffers are completely overwritten before use. Keep only
    # reusable topology/geometry on disk, not large unused line/candidate arrays.
    scratch={'candidates','edge_output','edge_output_owners','edge_output_meta',
             'cross_output','cross_output_owners','cross_mesh_pairs','cross_sourceplanes','counter',
             'outline_counts','hint_pixels','hint_view','features','crease','modes','camera'}
    geometric={'vertices','lo','hi','triangle_normals','metrics','normals','centers','dirty_nodes','dirty_meshes'}
    styled={'face_styles','triangle_styles','selected_styles'}
    core={'vertices','triangles','owners','lo','hi','dirty_nodes'}

    def __init__(self, ids, meshes, directory):
        self.ids=np.asarray(ids,np.int32);self.meshes=[meshes[i] for i in ids]
        self.directory=directory;self.gpu=None;self.frozen=None;self.style_key=None
        self.dirty=False;self.backing_bytes=0
        self.geometry_version=0;self.backing_versions={}

    def freeze(self,keep_core=False):
        gpu=self.gpu
        if gpu is None or not gpu.buffers:return
        if getattr(gpu,'visibility_history',None) is not None:
            gpu.visibility_history[1].close();gpu.visibility_history=None
        names={id(value):name for name,value in vars(gpu).items() if isinstance(value,Buffer)}
        self.directory.mkdir(parents=True,exist_ok=True)
        entries={entry[0]:entry for entry in (self.frozen or [])}
        kept=[]
        for index,buffer in enumerate(gpu.buffers):
            name=names.get(id(buffer))
            if name is None:raise RuntimeError('Untracked GPU page buffer')
            path=self.directory/(name+'.bin')
            scratch=name in self.scratch
            version=(self.geometry_version if name in self.geometric else self.style_key if name in self.styled else 0)
            if not scratch and (not path.is_file() or self.backing_versions.get(name)!=version):
                # Memory-map the cache on demand; do not retain a second full
                # scene worth of topology in Python's heap.
                gpu.runtime.read(buffer,buffer.size,np.uint8).tofile(path)
                self.backing_versions[name]=version
            entries[name]=(name,buffer.size,None if scratch else path)
            if keep_core and name in self.core:kept.append(buffer)
            else:buffer.close()
        gpu.buffers[:]=kept;self.frozen=list(entries.values())
        gpu.hint_key=None
        self.backing_bytes=sum(size for _,size,path in self.frozen if path is not None)

    def thaw(self,runtime,mode='full'):
        full=mode=='full' or self.dirty
        if self.gpu is None:
            self.gpu=GPUScene(self.meshes,max_intersections=32768,runtime=runtime)
            self.gpu.clip_edges=True
        elif self.frozen is not None:
            entries=self.frozen
            for name,size,path in entries:
                if not full and name not in self.core:continue
                if getattr(self.gpu,name).handle:continue
                if path is None:buffer=self.gpu.buf(size)
                else:
                    data=np.memmap(path,mode='r',dtype=np.uint8,shape=(size,))
                    try:buffer=self.gpu.buf(data)
                    finally:data._mmap.close()
                setattr(self.gpu,name,buffer)
            if full:self.frozen=None
        if self.dirty:
            self.gpu.update(np.concatenate([m['vertices'] for m in self.meshes]))
            self.geometry_version+=1
            self.dirty=False
        if mode=='core' and self.frozen is None:self.freeze(keep_core=True)
        return self.gpu


class PagedGPUScene:
    paged=True

    def __init__(self,meshes,page_triangle_target=400000,retain_planes=False):
        self.retain_planes=bool(retain_planes)
        extra=''
        if self.retain_planes:
            from .gpu_retained_kernels import SOURCE as extra
        self.meshes=meshes;self.runtime=r=Runtime();r.build(SOURCE+PAGE_SOURCE+extra)
        self.memory_budget=min(2*1024**3,r.global_memory_bytes//5)
        self.resident_limit=int(self.memory_budget*.72)
        self.offsets=np.cumsum([0]+[len(m['vertices']) for m in meshes])
        self.triangle_count=sum(len(m['triangles']) for m in meshes)
        self._temp=tempfile.TemporaryDirectory(prefix='ReaPencilGPUPage_')
        self._hint_buffers=(r.buffer(2048*2048*8),r.buffer(13*8)) if 'cl_khr_int64_extended_atomics' in r.extensions else ()
        self._resident=OrderedDict();self.pages=[];self.cross_cache=None
        self.bounds=np.asarray([[np.min(m['vertices'],axis=0),np.max(m['vertices'],axis=0)] for m in meshes],np.float64)
        # Group nearby complete meshes. Splitting polygons would introduce false
        # open edges at page seams; complete adjacency is intentionally retained.
        target=max(1,min(int(page_triangle_target),self.memory_budget//3000))
        order=morton_order(self.bounds.mean(axis=1))
        group=[];count=0
        for index in order:
            n=len(meshes[index]['triangles'])
            if group and count+n>target:
                self.pages.append(_Page(group,meshes,Path(self._temp.name)/str(len(self.pages))))
                group=[];count=0
            group.append(int(index));count+=n
        if group:self.pages.append(_Page(group,meshes,Path(self._temp.name)/str(len(self.pages))))
        self._update_bounds()
        self._face_styles=None;self._selected=None;self._style_count=0;self._style_version=0
        self._cross_by_page={};self._cross_between={}
        self._pass_caches=OrderedDict();self._pass_cache=None
        self.camera={};self.active=np.arange(len(self.pages));self.last_edge_meta=None
        self.merge_diagnostics={};self.page_loads=0;self.peak_resident_bytes=0

    def _update_bounds(self):
        self.page_bounds=np.asarray([[self.bounds[p.ids,0].min(axis=0),self.bounds[p.ids,1].max(axis=0)] for p in self.pages])
        self.page_bounds[:,0]-=1e-7;self.page_bounds[:,1]+=1e-7

    def set_camera(self,camera):
        self.camera=camera
        active=np.flatnonzero(visible_bounds(self.page_bounds,camera))
        if not np.array_equal(active,self.active):self.cross_cache=None
        self.active=active

    def _bytes(self):
        return sum(sum(b.size for b in p.gpu.buffers) for p in self.pages if p.gpu is not None)+sum(b.size for b in self._hint_buffers)

    def _load(self,index,protect=(),mode='full'):
        page=self.pages[index]
        needs_load=(index not in self._resident or (mode=='full' and page.frozen is not None) or page.dirty)
        if needs_load:
            # Leave room for the incoming page and its scratch growth. Two
            # pages are pinned only during cross-page intersection queries.
            full=mode=='full' or page.dirty or page.gpu is None
            triangles=sum(len(m['triangles']) for m in page.meshes)
            reserve=max(192*1024**2,triangles*850) if full else max(16*1024**2,triangles*180)
            while self._resident and self._bytes()+reserve>self.resident_limit:
                eligible=[i for i in self._resident if i not in protect and i!=index]
                # Prefer discarding outline/intersection scratch while retaining
                # the compact BVH. Global occlusion then reuses resident cores.
                victim=next((i for i in eligible if self.pages[i].frozen is None),None)
                if victim is not None:
                    self.pages[victim].freeze(keep_core=True);continue
                victim=next(iter(eligible),None)
                if victim is None:break
                self.pages[victim].freeze();del self._resident[victim]
            page.thaw(self.runtime,mode=mode);self._resident[index]=None;self.page_loads+=1
        else:
            page.thaw(self.runtime,mode=mode);self._resident.move_to_end(index)
        self.peak_resident_bytes=max(self.peak_resident_bytes,self._bytes())
        if self._bytes()>self.memory_budget:
            raise RuntimeError('A GPU page exceeds the available device budget; reduce a single oversized mesh or its subdivision.')
        gpu=page.gpu
        if self._hint_buffers:
            gpu.hint_pixels,gpu.hint_view=self._hint_buffers
            gpu.hint_key=None
        if mode=='full' and self._face_styles is not None and page.style_key!=self._style_version:
            gpu.configure_face_styles([self._face_styles[i] for i in page.ids],self._style_count,
                None if self._selected is None else [self._selected[i] for i in page.ids])
            page.style_key=self._style_version
        return gpu

    def configure_face_styles(self,face_style_ids,style_count,selected_edges=None):
        self._face_styles=face_style_ids;self._style_count=style_count;self._selected=selected_edges
        self._style_version+=1;self.cross_cache=None
        key=(id(face_style_ids),id(selected_edges),style_count)
        if key not in self._pass_caches:
            targeted=np.asarray([np.any(v>=0) or (selected_edges is not None and any(len(p) for p in selected_edges[i].values()))
                                 for i,v in enumerate(face_style_ids)],bool)
            self._pass_caches[key]=dict(faces=face_style_ids,selected=selected_edges,within={},between={},key=None,
                edge_pages=np.asarray([np.any(targeted[p.ids]) for p in self.pages]))
        self._pass_caches.move_to_end(key)
        while len(self._pass_caches)>8:self._pass_caches.popitem(last=False)
        self._pass_cache=self._pass_caches[key]
        self._cross_by_page=self._pass_cache['within'];self._cross_between=self._pass_cache['between']
        self._cross_key=self._pass_cache['key']

    def update(self,vertices,changed_meshes=None):
        changed=set(range(len(self.meshes)) if changed_meshes is None else changed_meshes)
        for index in changed:
            start,end=self.offsets[index:index+2];points=vertices[start:end]
            self.meshes[index]['vertices']=points
            self.bounds[index]=[points.min(axis=0),points.max(axis=0)]
        dirty=set()
        for i,page in enumerate(self.pages):
            if changed.intersection(page.ids):page.dirty=True;dirty.add(i)
        for cache in self._pass_caches.values():
            for k in list(cache['within']):
                if k in dirty:del cache['within'][k]
            for k in list(cache['between']):
                if dirty.intersection(k):del cache['between'][k]
        self._update_bounds();self.cross_cache=None

    def _between(self,ai,bi,styles,tolerance):
        a=self._load(ai);b=self._load(bi,protect=(ai,));r=self.runtime
        modes=np.asarray([[s.get('intersections',False),s.get('self_intersections',False)] for s in styles],np.int32)
        r.write(a.modes,modes)
        results=[];owners=[];planes=[];candidates=0
        if self.retain_planes and not hasattr(a,'cross_sourceplanes'):a.cross_sourceplanes=a.buf(a.capacity*32)
        pending=[(0,a.triangle_count)]
        while pending:
            first,count=pending.pop();r.write(a.counter,np.zeros(1,np.int32))
            r.run('page_candidates',count,a.lo,a.hi,b.lo,b.hi,a.triangle_styles,b.triangle_styles,a.modes,
                  a.candidates,a.counter,a.base,b.base,b.triangle_count,first,count,a.candidate_capacity,float(tolerance),local_size=64)
            n=int(r.read(a.counter,1,np.int32)[0])
            if n>a.candidate_capacity:
                if count==1:raise RuntimeError('One triangle exceeds bounded GPU candidate storage')
                half=count//2;pending.extend(((first,half),(first+half,count-half)));continue
            candidates+=n
            # At most one segment per candidate. Output in fixed-size slices,
            # so dense foliage cannot grow a giant output allocation.
            for start in range(0,n,a.capacity):
                size=min(a.capacity,n-start)
                pairs=r.buffer(r.read(a.candidates,(size,2),np.int32,offset=start*8))
                try:
                    r.write(a.counter,np.zeros(1,np.int32))
                    r.run('retained_page_intersections' if self.retain_planes else 'page_intersections',size,a.vertices,a.triangles,a.owners,a.triangle_faces,a.lo,a.hi,
                          a.triangle_normals,a.metrics,a.modes,a.cross_output,a.cross_output_owners,a.cross_mesh_pairs,
                          a.counter,size,a.base,float(tolerance),a.capacity,pairs,a.triangle_styles,0,
                          b.vertices,b.triangles,b.owners,b.triangle_normals,b.metrics,b.triangle_styles,
                          *([a.cross_sourceplanes] if self.retain_planes else []),local_size=64)
                    found=int(r.read(a.counter,1,np.int32)[0])
                    if found:
                        results.append(r.read(a.cross_output,(found*2,4)))
                        owners.append(r.read(a.cross_output_owners,found,np.int32))
                        if self.retain_planes:
                            payload=r.read(a.cross_sourceplanes,(found,2,4),np.float32)
                            payload[:,0,3]=self.pages[ai].ids[payload[:,0,3].astype(np.int32)]
                            payload[:,1,3]=self.pages[bi].ids[payload[:,1,3].astype(np.int32)]
                            planes.append(payload)
                finally:pairs.close()
        # The shared output scratch was used for cross-page strokes. Local
        # intersections are retained as CPU cache only; no resident direct read.
        result=(np.concatenate(results) if results else np.empty((0,4)),
                np.concatenate(owners) if owners else np.empty(0,np.int32),candidates)
        return (*result,np.concatenate(planes) if planes else np.empty((0,2,4),np.float32)) if self.retain_planes else result

    def _within(self,index,styles,tolerance):
        a=self._load(index);r=self.runtime
        modes=np.asarray([[s.get('intersections',False),s.get('self_intersections',False)] for s in styles],np.int32)
        r.write(a.modes,modes);results=[];owners=[];planes=[];candidates=0
        if self.retain_planes and not hasattr(a,'cross_sourceplanes'):a.cross_sourceplanes=a.buf(a.capacity*32)
        pending=[(0,a.triangle_count)]
        while pending:
            first,count=pending.pop();r.write(a.counter,np.zeros(1,np.int32))
            r.run('page_local_candidates',count,a.triangles,a.owners,a.triangle_faces,a.lo,a.hi,a.modes,
                  a.candidates,a.counter,a.triangle_count,a.base,float(tolerance),a.candidate_capacity,a.triangle_styles,
                  first,count,local_size=64)
            n=int(r.read(a.counter,1,np.int32)[0])
            if n>a.candidate_capacity:
                if count==1:raise RuntimeError('One triangle exceeds bounded GPU candidate storage')
                half=count//2;pending.extend(((first,half),(first+half,count-half)));continue
            candidates+=n
            for start in range(0,n,a.capacity):
                size=min(a.capacity,n-start);pairs=r.buffer(r.read(a.candidates,(size,2),np.int32,offset=start*8))
                try:
                    r.write(a.counter,np.zeros(1,np.int32))
                    r.run('retained_intersections' if self.retain_planes else 'intersections',size,a.vertices,a.triangles,a.owners,a.triangle_faces,a.lo,a.hi,
                          a.triangle_normals,a.metrics,a.modes,a.cross_output,a.cross_output_owners,a.cross_mesh_pairs,
                          a.counter,size,a.base,float(tolerance),a.capacity,pairs,a.triangle_styles,0,
                          *([a.cross_sourceplanes] if self.retain_planes else []),local_size=64)
                    found=int(r.read(a.counter,1,np.int32)[0])
                    if found:
                        results.append(r.read(a.cross_output,(found*2,4)));owners.append(r.read(a.cross_output_owners,found,np.int32))
                        if self.retain_planes:
                            payload=r.read(a.cross_sourceplanes,(found,2,4),np.float32)
                            payload[:,:,3]=self.pages[index].ids[payload[:,:,3].astype(np.int32)]
                            planes.append(payload)
                finally:pairs.close()
        result=(np.concatenate(results) if results else np.empty((0,4)),
                np.concatenate(owners) if owners else np.empty(0,np.int32),candidates)
        return (*result,np.concatenate(planes) if planes else np.empty((0,2,4),np.float32)) if self.retain_planes else result

    def intersections(self,styles,tolerance=1e-7):
        key=(tuple((bool(s.get('intersections')),bool(s.get('self_intersections'))) for s in styles),float(tolerance))
        if key!=getattr(self,'_cross_key',None):
            self._cross_by_page.clear();self._cross_between.clear();self.cross_cache=None;self._cross_key=key
            if self._pass_cache is not None:self._pass_cache['key']=key
        if self.cross_cache is not None:return self.cross_cache
        start=time.perf_counter();points=[];owners=[];planes=[];candidate_count=0;between_count=0
        if any(a or b for a,b in key[0]):
            def mask(column):
                modes=np.r_[np.asarray([m[column] for m in key[0]],bool),False]
                targeted=np.asarray([np.any(modes[values]) for values in self._face_styles],bool)
                return np.asarray([np.any(targeted[p.ids]) for p in self.pages])
            cross_pages=mask(0);self_pages=mask(1)
            for i in self.active:
                if not cross_pages[i] and not self_pages[i]:continue
                if i not in self._cross_by_page:
                    self._cross_by_page[i]=self._within(i,styles,tolerance)
                item=self._cross_by_page[i];p,o,n=item[:3];points.append(p);owners.append(o);candidate_count+=n
                if self.retain_planes:planes.append(item[3])
            if any(a for a,b in key[0]):
                for offset,i in enumerate(self.active):
                    lo,hi=self.page_bounds[i]
                    others=self.active[offset+1:]
                    overlap=np.all(self.page_bounds[others,0]<=hi+tolerance,axis=1)&np.all(self.page_bounds[others,1]>=lo-tolerance,axis=1)
                    for j in others[overlap]:
                        if not cross_pages[i] and not cross_pages[j]:continue
                        pair=(int(i),int(j))
                        if pair not in self._cross_between:self._cross_between[pair]=self._between(i,j,styles,tolerance)
                        item=self._cross_between[pair];p,o,n=item[:3];points.append(p);owners.append(o);candidate_count+=n;between_count+=len(o)
                        if self.retain_planes:planes.append(item[3])
        p=np.concatenate(points) if points else np.empty((0,4))
        o=np.concatenate(owners) if owners else np.empty(0,np.int32)
        if self.retain_planes:self.cross_planes=np.concatenate(planes) if planes else np.empty((0,2,4),np.float32)
        self.cross_cache=(p,o,dict(backend='opencl_gpu_paged',device=self.runtime.name,segments=len(o),triangles=self.triangle_count,
            candidate_pairs=candidate_count,cross_page_segments=between_count,pages=len(self.pages),active_pages=len(self.active),
            gpu_intersection_readback_ms=(time.perf_counter()-start)*1000))
        return self.cross_cache

    def edges(self,styles,camera,merge_groups=None,width=640,height=480):
        points=[];owners=[];metadata=[]
        for index in self.active:
            if self._pass_cache is not None and not self._pass_cache['edge_pages'][index]:continue
            page=self.pages[index];gpu=self._load(index)
            p,o=gpu.edges(styles,camera)
            points.append(p);owners.append(o)
            if merge_groups and len(o):
                meta=gpu.last_edge_meta.copy()
                meta[:,0]=page.ids[meta[:,0]];metadata.append(meta)
        p=np.concatenate(points) if points else np.empty((0,4))
        o=np.concatenate(owners) if owners else np.empty(0,np.int32)
        self.merge_diagnostics=dict(samples=0,suppressed_samples=0)
        if merge_groups and len(o):
            self.last_edge_meta=np.concatenate(metadata)
            from .gpu_merge import filter_outlines
            p,o,self.merge_diagnostics=filter_outlines(self,p,o,styles,camera,merge_groups,width,height)
        return p,o

    def filter_segments(self,points,owners,styles,camera,return_mask=False):
        from .gpu_visibility import certify
        started=time.perf_counter();pairs=np.asarray(points).reshape(-1,2,4)
        keep=np.ones(len(pairs),bool)
        allowed=np.asarray([not s.get('hidden_lines',False) for s in styles],bool)[owners]
        checked=0
        if camera.get('viewport_clip') is not None:
            # Cull once before all page queries, including hidden-line strokes.
            # This is geometric frustum clipping, never an occlusion shortcut.
            for begin in range(0,len(pairs),131072):
                chunk=pairs[begin:begin+131072];buffer=self.runtime.buffer(chunk)
                try:keep[begin:begin+len(chunk)]=clip_mask(self.runtime,buffer,len(chunk),camera)
                finally:buffer.close()
        frustum_culled=int((~keep).sum())
        blocker_pages=np.full(len(pairs),-1,np.int32);blocker_triangles=np.full(len(pairs),-1,np.int32)
        if camera.get('projection','perspective')=='perspective':
            eye=np.asarray(camera['position'])
            forward=np.asarray(camera['target'])-eye;forward=forward/np.linalg.norm(forward)
            camera_key=(eye.tobytes(),forward.tobytes(),float(camera.get('near',.1)))
            def query(i,ids,hints=None):
                nonlocal checked
                gpu=self._load(i,mode='core')
                for begin in range(0,len(ids),65536):
                    chunk=ids[begin:begin+65536]
                    if getattr(gpu,'visibility_history',None) is not None:
                        gpu.visibility_history[1].close();gpu.visibility_history=None
                    if hints is not None:
                        # A previous blocker is only a traversal hint. The GPU
                        # checks its current triangle against both new endpoints
                        # and the current camera before suppressing any stroke.
                        gpu.visibility_history=(len(chunk),self.runtime.buffer(hints[begin:begin+len(chunk)]))
                        gpu.visibility_history_camera=camera_key
                    else:gpu.visibility_history_camera=None
                    blockers=certify(gpu,pairs[chunk],camera)
                    hidden=blockers>=0;rejected=hidden|(blockers==-5)
                    keep[chunk[rejected]]=False
                    blocker_pages[chunk[hidden]]=i;blocker_triangles[chunk[hidden]]=blockers[hidden]
                    checked+=len(chunk)
            prior=None if self._pass_cache is None else self._pass_cache.get('visibility')
            if prior is not None and len(prior[0])==len(pairs):
                for i,group in prior[2].items():
                    if i not in self.active:continue
                    ids=group[keep[group]&allowed[group]]
                    if len(ids):query(i,ids,prior[1][ids])
            # Large enclosing geometry (e.g. a background dome) can certify
            # many strokes at once. Ordering affects work only, never validity.
            volume=np.prod(self.page_bounds[:,1]-self.page_bounds[:,0],axis=1)
            order=self.active[np.argsort(-volume[self.active],kind='stable')]
            for i in order:
                ids=np.flatnonzero(keep & allowed)
                if not len(ids):break
                candidate=ray_box_candidates(pairs[ids],eye,self.page_bounds[i]);ids=ids[candidate]
                if not len(ids):continue
                query(i,ids)
        if self._pass_cache is not None:
            groups={int(i):np.flatnonzero(blocker_pages==i) for i in np.unique(blocker_pages) if i>=0}
            self._pass_cache['visibility']=(blocker_pages,blocker_triangles,groups)
        result=(pairs[keep].reshape(-1,4),owners[keep],dict(backend='opencl_gpu_paged_shadow_certificate',
            input_segments=len(pairs),checked_segments=checked,rejected_segments=int((~keep).sum()),
            frustum_culled=frustum_culled,hidden_style_bypass=int((~allowed).sum()),seconds=time.perf_counter()-started))
        return (*result,keep) if return_mask else result

    def nearest_mesh(self,origins,directions,near,far):
        result=np.full(len(origins),-1,np.int32);distance=np.full(len(origins),far,np.float64);r=self.runtime
        for i in self.active:
            page=self.pages[i];gpu=self._load(i,mode='core')
            for start in range(0,len(origins),65536):
                end=min(len(origins),start+65536);n=end-start
                buffers=[r.buffer(origins[start:end]),r.buffer(directions[start:end]),r.buffer(n*4),r.buffer(n*8)]
                try:
                    r.run('page_nearest_mesh',n,gpu.vertices,gpu.triangles,gpu.owners,gpu.lo,gpu.hi,*buffers[:3],
                          gpu.base,n,float(near),float(far),buffers[3],local_size=64)
                    hit=r.read(buffers[2],n,np.int32);depth=r.read(buffers[3],n)
                    use=(hit>=0)&(depth<distance[start:end])
                    result[start:end][use]=page.ids[hit[use]];distance[start:end][use]=depth[use]
                finally:
                    for buffer in buffers:buffer.close()
        return result

    def diagnostics(self):
        return dict(pages=len(self.pages),active_pages=len(self.active),loaded_pages=sum(p.gpu is not None for p in self.pages),
            resident_pages=len(self._resident),resident_gpu_bytes=self._bytes(),peak_resident_gpu_bytes=self.peak_resident_bytes,
            resident_full_pages=sum(self.pages[i].frozen is None for i in self._resident),
            memory_budget_bytes=self.memory_budget,page_loads=self.page_loads,
            backing_bytes=sum(p.backing_bytes for p in self.pages))

    def close(self):
        for page in getattr(self,'pages',[]):
            if page.gpu is not None:page.gpu.close()
        for buffer in getattr(self,'_hint_buffers',()):buffer.close()
        if hasattr(self,'runtime'):self.runtime.close()
        if hasattr(self,'_temp'):
            directory=Path(self._temp.name).resolve()
            if directory.parent!=Path(tempfile.gettempdir()).resolve() or not directory.name.startswith('ReaPencilGPUPage_'):
                raise RuntimeError('Refusing to remove an unexpected GPU cache directory')
            self._temp.cleanup()

    def __del__(self):self.close()
