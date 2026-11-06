"""Maya adapter for GPU geometry. Does not change the CPU render adapter."""
import ctypes
import json
import time
import numpy as np
from maya import cmds, OpenMaya as om1
from maya.api import OpenMaya as om
from . import maya_scene
from .gpu_geometry import GPUScene


def _raw_local(fn):
    """Copy Maya-owned float/double storage before the mesh owner can expire."""
    try:
        address=int(fn.getRawDoublePoints());scalar=ctypes.c_double
    except RuntimeError:
        address=int(fn.getRawPoints());scalar=ctypes.c_float
    if not address:
        raise RuntimeError('Maya returned a null mesh point buffer')
    return np.ctypeslib.as_array((scalar*(fn.numVertices()*3)).from_address(address)).reshape(-1,3).copy()


def _raw_world(fn, path):
    local=_raw_local(fn)
    matrix=np.asarray(path.inclusiveMatrix(),np.float64).reshape(4,4)
    return local@matrix[:3,:3]+matrix[3,:3]


def _smooth_input(fn,path,fast_fn=None):
    """Exact evaluated base geometry, transform, crease and subdivision state.

    Reading the base mesh still evaluates animation/deformers every time. Only
    the redundant subdivision of unchanged inputs is skipped.
    """
    points=_raw_local(fn)
    matrix=np.asarray(path.inclusiveMatrix(),np.float64).reshape(4,4)
    options=om1.MMeshSmoothOptions();fn.getSmoothMeshDisplayOptions(options)
    values=tuple(getattr(options,name)() for name in (
        'divisions','subdivisionType','boundaryRule','keepBorderEdge','keepHardEdge',
        'propEdgeHardness','smoothness','openSubdivCreaseMethod',
        'openSubdivFaceVaryingBoundary','openSubdivSmoothTriangles','openSubdivVertexBoundary'))
    creases=[]
    if fast_fn is not None:
        for getter in (fast_fn.getCreaseEdges,fast_fn.getCreaseVertices):
            try:
                ids,weights=getter()
                creases.extend((np.asarray(ids,dtype=np.uint32).tobytes(),np.asarray(weights,dtype=np.float64).tobytes()))
            except RuntimeError:creases.extend((b'',b''))
    else:
        for getter in (fn.getCreaseEdges,fn.getCreaseVertices):
            ids=om1.MUintArray();weights=om1.MDoubleArray()
            try:getter(ids,weights)
            except RuntimeError:pass # Maya uses kFailure for an absent crease array.
            creases.extend((tuple(ids),tuple(weights)))
    return points,matrix,(values,*creases)


def _smooth_world(fn,path,divisions):
    """Evaluate the same viewport subdivision, then copy its native point array.

    The detached data owner stays alive through the copy. No scene node,
    subdivision option, or precision threshold is changed.
    """
    options=om1.MMeshSmoothOptions()
    fn.getSmoothMeshDisplayOptions(options)
    options.setDivisions(divisions);options.setSmoothUVs(False)
    owner=om1.MFnMeshData().create()
    smooth=om1.MFnMesh(fn.generateSmoothMesh(owner,options))
    return _raw_world(smooth,path)


class LiveScene:
    def __init__(self, camera_path, settings, camera,retained=False):
        started=time.perf_counter()
        self.scene = maya_scene.export_scene(camera_path.fullPathName(),settings,camera_override=camera,
                                            include_normals=False,geometry_purpose='viewport',
                                            include_materials=False,as_arrays=True,
                                            mesh_filter=None if retained else camera.get('_viewport_mesh_filter'))
        exported=time.perf_counter()
        self.empty=not self.scene['meshes']
        if self.empty:
            self.gpu=None
            return
        if retained or sum(len(m['triangles']) for m in self.scene['meshes'])>3000000:
            from .gpu_paged import PagedGPUScene
            self.gpu=PagedGPUScene(self.scene['meshes'],retain_planes=retained)
        else:
            try:self.gpu = GPUScene(self.scene['meshes'])
            except ValueError as error:
                if not str(error).startswith(('GPU scene requires','GPU BVH allocation exceeds')):raise
                from .gpu_paged import PagedGPUScene
                self.gpu=PagedGPUScene(self.scene['meshes'])
        constructed=time.perf_counter()
        self.paths, self.functions = [], []
        self.counts = []
        self.smooth_levels=[]
        self.smooth_plugs=[]
        self.smooth_inputs=[]
        self.fast_functions=[]
        self.level_plugs=[]
        for mesh in self.scene['meshes']:
            path = maya_scene._dag(mesh['name'])
            selection=om1.MSelectionList();selection.add(mesh['name'])
            old_path=om1.MDagPath();selection.getDagPath(0,old_path)
            fn=om1.MFnMesh(old_path)
            fn2=om.MFnMesh(path);self.fast_functions.append(fn2)
            dep=om.MFnDependencyNode(path.node())
            self.level_plugs.append((dep.findPlug('displaySmoothMesh',False),dep.findPlug('smoothLevel',False)))
            self.paths.append(path)
            self.functions.append(fn)
            self.counts.append((fn.numVertices(),fn.numPolygons()))
            self.smooth_levels.append(int(mesh.get('smooth_level',0)))
            plug=None
            if self.smooth_levels[-1]:
                # Use Maya's already evaluated preview only when it matches our
                # provenance topology. Unusual/custom preview modes retain the
                # independent evaluator instead of silently using another mesh.
                candidate=om1.MFnDependencyNode(old_path.node()).findPlug('outSmoothMesh',False)
                owner=candidate.asMObject()
                preview=om1.MFnMesh(owner)
                world=_raw_world(preview,path)
                expected=np.asarray(mesh['vertices'],np.float64)
                if world.shape==expected.shape and np.allclose(world,expected,rtol=0,atol=1e-10):
                    # API 2 verifies order once; animation only copies positions.
                    p2=om.MFnDependencyNode(path.node()).findPlug('outSmoothMesh',False).asMObject()
                    _,tri2=om.MFnMesh(p2).getTriangles()
                    if np.array_equal(np.asarray(tri2).reshape(-1,3),mesh['triangles']):plug=candidate
            self.smooth_plugs.append(plug)
            self.smooth_inputs.append(_smooth_input(fn,path,fn2) if self.smooth_levels[-1] else None)
        self.positions = np.concatenate([np.asarray(m['vertices'],np.float64) for m in self.scene['meshes']])
        self.generation = -1
        self.cache_key = None
        self.groups = []
        self.report = {}
        self.style_passes=None
        self.style_key=None
        self.startup_report=dict(export_ms=(exported-started)*1000,
            gpu_scene_build_ms=(constructed-exported)*1000,
            live_binding_ms=(time.perf_counter()-constructed)*1000,
            construction_ms=(time.perf_counter()-started)*1000,
            cached_preview_meshes=sum(p is not None for p in self.smooth_plugs))

    def close(self):
        if self.gpu is not None:self.gpu.close()

    def update(self):
        """Borrow raw doubles only while copying; never retain Maya-owned pointers."""
        changed = []
        for i,(path,fn,counts) in enumerate(zip(self.paths,self.functions,self.counts)):
            fn.syncObject()
            if (fn.numVertices(),fn.numPolygons())!=counts:
                raise ValueError('GPU topology changed; rebuild required')
            if self.smooth_levels[i]:
                display,level=self.level_plugs[i]
                if (max(0,level.asInt()) if display.asInt() else 0)!=self.smooth_levels[i]:
                    raise ValueError('Smooth subdivision level changed; rebuild required')
                fn2=self.fast_functions[i];fn2.syncObject()
                current=_smooth_input(fn,path,fn2);previous=self.smooth_inputs[i]
                if (previous is not None and current[2]==previous[2] and
                        np.array_equal(current[0],previous[0]) and np.array_equal(current[1],previous[1])):
                    continue
                plug=self.smooth_plugs[i]
                if plug is not None:
                    owner=plug.asMObject()
                    world=_raw_world(om1.MFnMesh(owner),path)
                else:
                    world=_smooth_world(fn,path,self.smooth_levels[i])
                self.smooth_inputs[i]=current
            else:
                world=_raw_world(fn,path)
            if self.scene['meshes'][i].get('alpha_boundary'):
                from .alpha_boundary import deform
                world=deform(self.scene['meshes'][i],world)
            start,end=self.gpu.offsets[i:i+2]
            if len(world)!=end-start:
                raise ValueError('Smoothed GPU topology changed; rebuild required')
            if not np.array_equal(world,self.positions[start:end]):
                self.positions[start:end]=world
                changed.append(i)
        if changed:
            self.gpu.update(self.positions,changed_meshes=changed)
        self.changed_meshes=changed
        return bool(changed)

    def draw(self, camera, settings, generation, native=False):
        if self.empty:
            return [],dict(state='ready',backend='opencl_gpu',segments=0,submitted_segments=0,
                           mesh_count=0,triangles=0,reason='fully_transparent_alpha',geometry_generation=generation)
        started=time.perf_counter()
        from . import renderer,line_graph,viewport
        if viewport._gpu_graph_dirty:
            line_graph.refresh_scene(self.scene)
            viewport._gpu_graph_dirty=False
            self.style_passes=None
        if viewport._gpu_style_dirty:
            if self.style_passes is not None:
                table={target['node']:target['settings'] for line in line_graph.snapshot() for target in line['sets']}
                self.scene['line_sets']=table
                for item in self.style_passes:
                    if item.get('style_nodes') is None:
                        self.style_passes=None;break
                    item['styles']=[dict(settings,**table.get(n,{})) for n in item['style_nodes']]
                if self.style_passes is not None:
                    self.style_key=(json.dumps(table,sort_keys=True),json.dumps(settings,sort_keys=True))
            viewport._gpu_style_dirty=False
        if not any('line_passes' in m for m in self.scene['meshes']):
            self.scene['line_sets']={n:maya_scene._json_attr(n,'reaToonOverrides') for n in self.scene.get('line_sets',{})}
        style_key=(json.dumps(self.scene.get('line_sets',{}),sort_keys=True),json.dumps(settings,sort_keys=True))
        key=(generation,*style_key,json.dumps(camera,sort_keys=True),native)
        if self.cache_key==key:
            return self.groups,dict(self.report,draw_cache_hit=True,prepare_ms=(time.perf_counter()-started)*1000)
        if self.style_passes is None or self.style_key!=style_key:
            self.style_passes=renderer.line_style_passes(self.scene,settings)
            for item in self.style_passes:
                if item['line']:
                    nodes=line_graph.list_sets(item['line'])
                    item['style_nodes']=[nodes[int(s['_order'])] for s in item['styles']]
            self.style_key=style_key
        passes=self.style_passes
        geometry_changed=False
        if generation!=self.generation:
            geometry_changed=self.update()
            self.generation=generation
        if getattr(self.gpu,'paged',False):
            if 'viewport_clip' in camera:
                camera['viewport_clip']['margin_pixels']=max(8.,max((float(s.get('line_width',1.5)) for p in passes for s in p['styles']),default=1.5)+4.)
            self.gpu.set_camera(camera)
        update_ms=(time.perf_counter()-started)*1000
        compute_ms=0.0
        pack_ms=0.0
        total=0
        submitted=0
        diagnostics=dict(backend='opencl_gpu',device=self.gpu.runtime.name,segments=0,passes=[])
        batches={}
        def add(points,owners,styles):
            pairs=points.reshape(-1,2,4)
            # Usually one style covers many meshes. Group styles before filtering
            # to avoid scanning the complete segment array once per mesh.
            style_owners={}
            for i,s in enumerate(styles):
                key=(tuple(s.get('line_color',[.04,.04,.07])),max(.25,round(float(s.get('line_width',1.5))*4)/4),
                     bool(s.get('hidden_lines')),tuple(s.get('hidden_color',[.5,.5,.6])),float(s.get('dash_length',0))>0,
                     float(s.get('distance_reduction',0)))
                style_owners.setdefault(key,[]).append(i)
            for key,indices in style_owners.items():
                chosen=pairs if len(indices)==len(styles) else pairs[np.isin(owners,indices)]
                if not len(chosen):continue
                reduction=key[-1]
                if reduction:
                    distances=np.linalg.norm(chosen[:,:,:3].mean(axis=1)-np.asarray(camera['position']),axis=1)
                    widths=np.maximum(.25,np.round(np.maximum(.1,key[1]/(1+reduction*distances))*4)/4)
                    for width in np.unique(widths):
                        k=(key[0],float(width),*key[2:5])
                        batches.setdefault(k,[]).append(chosen[widths==width].reshape(-1,4))
                else:
                    batches.setdefault(key[:5],[]).append(chosen.reshape(-1,4))
        groups=[]
        for item in passes:
            styles=item['styles']
            if not styles:continue
            compute_start=time.perf_counter()
            if getattr(self.gpu,'_live_style_pass',None) is not item:
                self.gpu.configure_face_styles(item['face_style_ids'],len(styles),item.get('selected_edges'))
                self.gpu._live_style_pass=item
            cross,cross_owners,info=self.gpu.intersections(styles,float(settings.get('intersection_tolerance',1e-7)))
            edge,edge_owners=self.gpu.edges(styles,camera,self.scene.get('merge_groups'),
                                          settings.get('width',640),settings.get('height',480))
            raw_count=(len(edge)+len(cross))//2
            from .gpu_visibility import filter_segments
            if 'viewport_clip' in camera:
                camera['viewport_clip']['margin_pixels']=max(8.,max(float(s.get('line_width',1.5)) for s in styles)+4.)
            # VP2 surface-depth bias leaks near-coplanar intersection strokes.
            # Silhouettes already follow its visible surface; only cross strokes
            # need the more expensive, strictly conservative shadow certificate.
            cross,cross_owners,visibility=filter_segments(self.gpu,cross,cross_owners,styles,camera)
            compute_ms+=(time.perf_counter()-compute_start)*1000
            pack_start=time.perf_counter()
            batches={}
            add(edge,edge_owners,styles)
            add(cross,cross_owners,styles)
            groups.extend((k,np.concatenate(values) if native else om.MPointArray(np.concatenate(values))) for k,values in batches.items())
            pack_ms+=(time.perf_counter()-pack_start)*1000
            total+=raw_count
            submitted+=len(edge_owners)+len(cross_owners)
            diagnostics['segments']+=info['segments']
            diagnostics['passes'].append(dict(info,line=item['line'],merge_groups=self.gpu.merge_diagnostics,
                                              visibility=visibility))
        self.groups=groups
        self.cache_key=key
        self.report=dict(state='ready',backend='opencl_gpu',device=self.gpu.runtime.name,native_transfer=native,
            startup=self.startup_report,
            evaluated_frame=float(cmds.currentTime(query=True)),
            mesh_count=len(self.scene['meshes']),triangles=self.gpu.triangle_count,
            smooth_mesh_count=sum(level>0 for level in self.smooth_levels),smooth_levels=self.smooth_levels,
            geometry_generation=generation,geometry_updated=geometry_changed,
            segments=total,submitted_segments=submitted,batches=len(self.groups),draw_cache_hit=False,
            geometry_update_ms=update_ms,gpu_compute_readback_ms=compute_ms,
            pack_ms=pack_ms,
            prepare_ms=(time.perf_counter()-started)*1000,
            intersection_diagnostics=diagnostics,
            warnings=['GPU viewport omits coplanar overlaps and point contacts. Collinear triangle segments are not merged.',
                      'Hidden strokes are an approximate x-ray underlay; taper/variation are CPU render only.'])
        if getattr(self.gpu,'paged',False):self.report['paging']=self.gpu.diagnostics()
        return self.groups,self.report
