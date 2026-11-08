"""Persistent VP2 buffers, current-camera GPU silhouettes, legacy feature fallback."""
import ctypes as c,json,time
from pathlib import Path
import numpy as np
from maya import cmds
from . import viewport as vp,maya_scene,line_graph,renderer,retained_geometry
from .gpu_viewport import LiveScene

_key=None
_library=None
_passes=None
_geometry_style_key=None
_mode=None
_fallback_generation=-1
_fallback_reason=''
_device_error=None
_last_api=None
_deferred_entries=[]
_deferred_camera_key=None
_fixed_group_count=0
_fixed_segments=0
_fixed_batches=0
_group_segment_counts={}
MAX_RETAINED_GROUP_SEGMENTS=262144


def _set_style(style_id,width,color):
    _library.rt_style(style_id,width,color)
    style=next((p['styles'][style_id-p['retained_style_offset']] for p in (_passes or []) if p.get('retained_style_offset',-1)<=style_id<p.get('retained_style_offset',-1)+len(p['styles'])),{})
    curve=style.get('width_depth_reduction',[])
    if curve and not style.get('width_reduction_origin'):
        from .depth_reduction import validate
        values=validate(curve)
    else:values=[0.,0.,1.,1.]
    _library.rt_style_depth(style_id,(c.c_float*4)(*values))


def _begin_pass():
    _library.rt_begin_pass();_group_segment_counts.clear()


def _add_bounded(points,parameters,style_id,width,color):
    """Keep every segment while bounding native VP2 draw-item vertex counts.

    Maya can silently omit oversized retained items. Bound both a single large
    submission and accumulation of many small meshes into the same style item.
    Splitting creates ordered draw items; it does not simplify or discard lines.
    """
    for first in range(0,len(points),MAX_RETAINED_GROUP_SEGMENTS):
        p=points[first:first+MAX_RETAINED_GROUP_SEGMENTS]
        q=parameters[first:first+MAX_RETAINED_GROUP_SEGMENTS]
        if _group_segment_counts.get(style_id,0)+len(p)>MAX_RETAINED_GROUP_SEGMENTS:_begin_pass()
        if not _library.rt_add_retained(p.ctypes.data,q.ctypes.data,len(p),width,color):
            raise retained_geometry.UnsupportedRetained('Retained GPU buffer transfer failed')
        _group_segment_counts[style_id]=_group_segment_counts.get(style_id,0)+len(p)

def bind(lib):
    global _library,_mode,_key,_device_error,_fallback_generation
    _mode=None;_key=None;_device_error=None;_fallback_generation=-1
    _library=lib
    lib.rt_effect.argtypes=[c.c_char_p];lib.rt_effect.restype=None
    lib.rt_add_retained.argtypes=[c.c_void_p,c.c_void_p,c.c_uint,c.c_float,c.POINTER(c.c_float)]
    lib.rt_add_retained.restype=c.c_int
    lib.rt_begin_pass.argtypes=[];lib.rt_begin_pass.restype=None
    lib.rt_style.argtypes=[c.c_uint,c.c_float,c.POINTER(c.c_float)];lib.rt_style.restype=None
    lib.rt_style_depth.argtypes=[c.c_uint,c.POINTER(c.c_float)];lib.rt_style_depth.restype=None
    lib.rt_mode.argtypes=[c.c_int];lib.rt_mode.restype=None
    if hasattr(lib,'rt_reuse'):
        lib.rt_reuse.argtypes=[c.c_uint,c.c_uint];lib.rt_reuse.restype=None
        lib.rt_group_count.argtypes=[];lib.rt_group_count.restype=c.c_uint
        lib.rt_edge_positions.argtypes=[c.c_void_p,c.c_void_p,c.c_uint,c.c_void_p,c.c_void_p];lib.rt_edge_positions.restype=None
    lib.rt_add.argtypes=[c.c_void_p,c.c_uint,c.c_float,c.POINTER(c.c_float),c.c_int,c.POINTER(c.c_float),c.c_int]
    lib.rt_add.restype=c.c_int
    lib.rt_effect(str(Path(__file__).parent/'shaders/retained_lines.ogsfx').encode('utf-8'))
    if hasattr(lib,'rt_scope'):
        lib.rt_scope.argtypes=[c.c_char_p,c.c_void_p,c.c_uint];lib.rt_scope.restype=None
        from . import view_scope
        view_scope.reset()

def _evaluate_edges(mesh,data):
    v=np.ascontiguousarray(mesh['vertices'],np.float64)
    _library.rt_edge_positions(v.ctypes.data,data['topology'].ctypes.data,len(data['owners']),data['points'].ctypes.data,data['parameters'].ctypes.data)

def _switch(mode):
    global _mode,_key,_passes,_geometry_style_key,_deferred_entries,_deferred_camera_key
    if _mode!=mode:
        if vp._gpu_scene is not None:vp._gpu_scene.close()
        vp._gpu_scene=None;vp._gpu_rebuild=True;vp._native_last_groups=None
        _key=None;_passes=None;_geometry_style_key=None;_mode=mode
        _deferred_entries=[];_deferred_camera_key=None
    _library.rt_mode(mode=='retained')

def _fallback(camera_name,aspect,reason,destination=''):
    global _fallback_generation,_fallback_reason
    _switch('legacy');vp._native_prepare(camera_name,aspect,destination)
    _fallback_generation=vp._generation;_fallback_reason=reason
    vp._last_report['retained_fallback_reason']=reason

def prepare(camera_name,aspect,draw_api=4,destination=''):
    global _last_api,_fallback_generation
    api_changed=_last_api!=draw_api
    if api_changed:_fallback_generation=-1;_last_api=draw_api
    if not camera_name or not cmds.objExists(camera_name):
        _library.rt_begin();_library.rt_end();return
    if draw_api!=4:return _fallback(camera_name,aspect,'Retained drawing requires OpenGL Core Profile',destination)
    if _device_error:return _fallback(camera_name,aspect,_device_error,destination)
    # Vertex animation does not turn non-manifold topology into manifold
    # topology. Keep its live GPU scene instead of rebuilding both backends.
    if _mode=='legacy' and not api_changed and not (vp._gpu_rebuild or vp._gpu_graph_dirty or vp._gpu_style_dirty):
        return _fallback(camera_name,aspect,_fallback_reason,destination)
    _switch('retained')
    try:
        _prepare(camera_name,aspect)
        if hasattr(_library,'rt_scope') and vp._gpu_scene is not None:
            from . import view_scope
            vp._last_report['view_scopes']=view_scope.sync(_library,[m['name'] for m in vp._gpu_scene.scene['meshes']],destination)
            vp._last_report['draw_destination']=destination
    except retained_geometry.UnsupportedRetained as error:
        _fallback(camera_name,aspect,str(error),destination)

def _draw_deferred(camera):
    """Upload only exceptional silhouette edges; retain all ordinary GPU data."""
    total=batches=0
    _begin_pass()
    for data,styles,offset,mesh_id in _deferred_entries:
        visible=retained_geometry.deferred_camera_mask(data,camera)
        for owner in np.unique(data['owners'][visible]):
            selected=visible&(data['owners']==owner)
            points=np.ascontiguousarray(data['points'][selected],np.float64)
            parameters=np.zeros((len(points),2,4),np.float32)
            parameters[:,0,:3]=data['normal0'][selected];parameters[:,1,:3]=data['normal1'][selected]
            parameters[:,:,3]=2*(mesh_id+1)
            style=styles[int(owner)];width=float(style.get('line_width',1.5))
            color=(c.c_float*3)(*style.get('line_color',[.04,.04,.07]))
            _set_style(offset+int(owner),width,color)
            _add_bounded(points,parameters,offset+int(owner),width,color)
            total+=len(points);batches+=1
    return total,batches


def _prepare(camera_name,aspect):
    global _key,_passes,_geometry_style_key,_deferred_entries,_deferred_camera_key
    global _fixed_group_count,_fixed_segments,_fixed_batches
    started=time.perf_counter()
    key=(vp._generation,vp._gpu_rebuild,vp._gpu_graph_dirty,vp._gpu_style_dirty)
    if _key==key and not _deferred_entries:
        vp._last_report.update(prepare_ms=(time.perf_counter()-started)*1000,
                               geometry_updated=False,retained_geometry_reused=True)
        return
    path=maya_scene._dag(camera_name);camera=vp._camera_data(path,aspect)
    camera_key=(tuple(camera['position']),tuple(camera['target']),camera['projection'])
    if _key==key:
        if camera_key==_deferred_camera_key:
            vp._last_report.update(prepare_ms=(time.perf_counter()-started)*1000,
                                   geometry_updated=False,retained_geometry_reused=True)
            return
        _library.rt_begin();_library.rt_reuse(0,_fixed_group_count)
        count,batches=_draw_deferred(camera);_library.rt_end();_deferred_camera_key=camera_key
        vp._last_report.update(segments=_fixed_segments+count,submitted_segments=_fixed_segments+count,
            batches=_fixed_batches+batches,exceptional_visible_segments=count,retained_geometry_reused=True,
            prepare_ms=(time.perf_counter()-started)*1000)
        return
    lines=line_graph.list_lines()
    nodes=cmds.ls(type=vp.NODE_NAME) or []
    vp._graph_mode|=bool(lines) or any(cmds.getAttr(n+'.lineGraphMode') for n in nodes)
    if vp._graph_mode:
        for n in nodes:
            if not cmds.getAttr(n+'.lineGraphMode'):cmds.setAttr(n+'.lineGraphMode',True)
    if vp._graph_mode and not lines:
        _library.rt_begin();_library.rt_end();_key=key
        vp._last_report=dict(state='ready',backend='retained_gpu',segments=0,submitted_segments=0,reason='empty_line_graph')
        return
    if vp._watchers_stale:vp._watch_scene()
    from . import preview_settings
    settings=preview_settings.load()
    rebuilt=vp._gpu_scene is None or vp._gpu_rebuild
    if rebuilt:
        geometry_cache=(vp._gpu_scene.smooth_rebuild_cache() if vp._smooth_rebuild_only and vp._gpu_scene is not None and not vp._gpu_scene.empty else None)
        if vp._gpu_scene is not None:vp._gpu_scene.close()
        vp._gpu_scene=LiveScene(path,settings,camera,retained=True,geometry_cache=geometry_cache)
        vp._gpu_scene.generation=vp._generation;_passes=None
        vp._gpu_rebuild=False;vp._gpu_graph_dirty=False
        vp._smooth_rebuild_only=False
    live=vp._gpu_scene
    changed=False
    if not live.empty and live.generation!=vp._generation:
        changed=live.update();live.generation=vp._generation
    graph_dirty=vp._gpu_graph_dirty
    if graph_dirty:
        line_graph.refresh_scene(live.scene);_passes=None;vp._gpu_graph_dirty=False
    if vp._gpu_style_dirty:
        # Retain face target arrays on a brush-only edit.
        table={target['node']:target['settings'] for line in line_graph.snapshot() for target in line['sets']}
        live.scene['line_sets']=table
        if _passes is not None:
            for item in _passes:
                base=dict(renderer.DEFAULTS,**settings)
                item['styles']=[dict(dict(base,**table.get(n,{})),**{k:v for k,v in old.items() if k.startswith('_')}) for old,n in zip(item['styles'],item['style_nodes'])]
        vp._gpu_style_dirty=False
    if _passes is None:
        _passes=renderer.line_style_passes(live.scene,settings)
        for item in _passes:
            nodes=line_graph.list_sets(item['line']) if item['line'] else []
            item['style_nodes']=[nodes[int(s['_order'])] for s in item['styles']] if nodes else []
    preview_settings.filter_passes(_passes)
    if live.scene.get('merge_groups'):raise retained_geometry.UnsupportedRetained('Merge Groups use the legacy GPU viewport')
    if any(s.get(k) for item in _passes for s in item['styles'] for k in ('hidden_lines','dash_length','distance_reduction','width_variation','taper')):
        raise retained_geometry.UnsupportedRetained('Advanced brush styles use the legacy GPU viewport')
    geometry_style_key=json.dumps([[{k:v for k,v in style.items() if k not in ('line_color','line_width','width_depth_reduction')} for style in p['styles']] for p in _passes],sort_keys=True)
    style_offset=0
    for item in _passes:
        item['retained_style_offset']=style_offset
        for i,style in enumerate(item['styles']):
            color=(c.c_float*3)(*style.get('line_color',[.04,.04,.07]))
            _set_style(style_offset+i,float(style.get('line_width',1.5)),color)
        style_offset+=len(item['styles'])
    if not rebuilt and not changed and not graph_dirty and geometry_style_key==_geometry_style_key:
        styles_by_offset={p['retained_style_offset']:p['styles'] for p in _passes}
        _deferred_entries=[(d,styles_by_offset[o],o,i) for d,_,o,i in _deferred_entries]
        _key=(vp._generation,vp._gpu_rebuild,vp._gpu_graph_dirty,vp._gpu_style_dirty)
        vp._last_report.update(geometry_generation=vp._generation,geometry_updated=False,retained_geometry_reused=True,
                              prepare_ms=(time.perf_counter()-started)*1000)
        return
    partial=hasattr(_library,'rt_reuse') and len(live.scene['meshes'])<=256
    dirty=set(getattr(live,'changed_meshes',[]))
    reuse=partial and changed and not rebuilt and not graph_dirty and geometry_style_key==_geometry_style_key
    _library.rt_begin();total=0;edge_total=0;cross_total=0;batch_count=0;pass_reports=[]
    _deferred_entries=[]
    def submit(points,parameters,styles,owners):
        nonlocal total,batch_count
        unique=np.unique(owners)
        for owner in unique:
            style=styles[int(owner)]
            selected=owners==owner
            p=np.ascontiguousarray(points if len(unique)==1 else points[selected],np.float64)
            q=np.ascontiguousarray(parameters if len(unique)==1 else parameters[selected],np.float32)
            color=(c.c_float*3)(*style.get('line_color',[.04,.04,.07]))
            _set_style(item['retained_style_offset']+int(owner),float(style.get('line_width',1.5)),color)
            _add_bounded(p,q,item['retained_style_offset']+int(owner),float(style.get('line_width',1.5)),color)
            total+=len(p);batch_count+=1
    if not live.empty:
        for item in _passes:
            _begin_pass()
            styles=item['styles']
            if not styles:continue
            gpu=live.gpu;gpu.configure_face_styles(item['face_style_ids'],len(styles),item.get('selected_edges'))
            gpu.set_camera(camera) # No viewport_clip: retain ALL pages and future views.
            cross,owners,report=gpu.intersections(styles,settings.get('intersection_tolerance',1e-7))
            parameters=gpu.cross_planes.copy();parameters[:,:,3]=(parameters[:,:,3]+1)*2
            submit(cross.reshape(-1,2,4)[:,:,:3],parameters,styles,owners)
            cross_total+=len(owners);pass_reports.append(report)
            if not reuse:item['edge_cache']={};item['edge_ranges']={};item['deferred_cache']={}
            for i,mesh in enumerate(live.scene['meshes']):
                faces=item['face_style_ids'][i];selected=item.get('selected_edges')
                selected=None if selected is None else selected[i]
                if not np.any(faces>=0) and not selected:continue
                if partial:
                    _begin_pass();first=_library.rt_group_count()
                    if reuse and i not in dirty and i in item['edge_ranges']:
                        old,count,segments=item['edge_ranges'][i];_library.rt_reuse(old,count)
                        item['edge_ranges'][i]=(first,count,segments);total+=segments;edge_total+=segments
                        if i in item['deferred_cache']:
                            _deferred_entries.append((item['deferred_cache'][i],styles,item['retained_style_offset'],i))
                        continue
                cache=item['edge_cache'].setdefault(i,{}) if partial else None
                if cache is not None:cache['evaluate']=_evaluate_edges
                try:data=retained_geometry.candidates(mesh,faces,styles,selected,cache=cache,
                                                     defer_nonmanifold=hasattr(_library,'rt_reuse'))
                except retained_geometry.UnsupportedRetained as error:
                    raise retained_geometry.UnsupportedRetained(mesh['name']+': '+str(error)) from error
                parameters=data.get('parameters')
                if parameters is None:
                    parameters=np.zeros((len(data['owners']),2,4),np.float32)
                    parameters[:,0,:3]=data['normal0'];parameters[:,1,:3]=data['normal1']
                parameters[:,0,3]=2*(i+1)+data['dynamic'];parameters[:,1,3]=2*(i+1)
                submit(data['points'],parameters,styles,data['owners']);edge_total+=len(data['owners'])
                item['deferred_cache'].pop(i,None)
                if data.get('deferred') is not None:
                    item['deferred_cache'][i]=data['deferred']
                    _deferred_entries.append((data['deferred'],styles,item['retained_style_offset'],i))
                if partial:item['edge_ranges'][i]=(first,_library.rt_group_count()-first,len(data['owners']))
    # Keep authored line-pass compositing order. Exceptional strokes currently
    # form a small tail group; with multiple passes that tail could overpaint a
    # later line. The established complete path remains the oracle for that case.
    if _deferred_entries and len(_passes)>1:
        raise retained_geometry.UnsupportedRetained('Multiple line passes with exceptional silhouettes use the legacy GPU viewport')
    _fixed_group_count=_library.rt_group_count();_fixed_segments=total;_fixed_batches=batch_count
    deferred_count,deferred_batches=_draw_deferred(camera)
    total+=deferred_count;batch_count+=deferred_batches;edge_total+=deferred_count
    _deferred_camera_key=camera_key
    native_groups=_library.rt_group_count();_library.rt_end()
    _geometry_style_key=geometry_style_key
    _key=(vp._generation,vp._gpu_rebuild,vp._gpu_graph_dirty,vp._gpu_style_dirty)
    vp._last_report=dict(state='ready',backend='retained_gpu',segments=total,submitted_segments=total,
        edge_candidates=edge_total,intersection_segments=cross_total,batches=batch_count,
        mesh_count=len(live.scene['meshes']),triangles=sum(len(m['triangles']) for m in live.scene['meshes']),
        smooth_mesh_count=sum(m.get('smooth_level',0)>0 for m in live.scene['meshes']),
        geometry_generation=vp._generation,geometry_updated=changed,prepare_ms=(time.perf_counter()-started)*1000,
        camera_classification='GPU shader on every frame',intersection_diagnostics=pass_reports)
    vp._last_report.update(exceptional_edges=sum(len(d['owners']) for d,_,_,_ in _deferred_entries),
                           exceptional_visible_segments=deferred_count,retained_draw_groups=native_groups,
                           retained_group_segment_limit=MAX_RETAINED_GROUP_SEGMENTS)
