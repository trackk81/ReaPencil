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

def bind(lib):
    global _library,_mode,_key,_device_error,_fallback_generation
    _mode=None;_key=None;_device_error=None;_fallback_generation=-1
    _library=lib
    lib.rt_effect.argtypes=[c.c_char_p];lib.rt_effect.restype=None
    lib.rt_add_retained.argtypes=[c.c_void_p,c.c_void_p,c.c_uint,c.c_float,c.POINTER(c.c_float)]
    lib.rt_add_retained.restype=c.c_int
    lib.rt_begin_pass.argtypes=[];lib.rt_begin_pass.restype=None
    lib.rt_style.argtypes=[c.c_uint,c.c_float,c.POINTER(c.c_float)];lib.rt_style.restype=None
    lib.rt_mode.argtypes=[c.c_int];lib.rt_mode.restype=None
    lib.rt_add.argtypes=[c.c_void_p,c.c_uint,c.c_float,c.POINTER(c.c_float),c.c_int,c.POINTER(c.c_float),c.c_int]
    lib.rt_add.restype=c.c_int
    lib.rt_effect(str(Path(__file__).parent/'shaders/retained_lines.ogsfx').encode('utf-8'))

def _switch(mode):
    global _mode,_key,_passes,_geometry_style_key
    if _mode!=mode:
        if vp._gpu_scene is not None:vp._gpu_scene.close()
        vp._gpu_scene=None;vp._gpu_rebuild=True;vp._native_last_groups=None
        _key=None;_passes=None;_geometry_style_key=None;_mode=mode
    _library.rt_mode(mode=='retained')

def _fallback(camera_name,aspect,reason):
    global _fallback_generation,_fallback_reason
    _switch('legacy');vp._native_prepare(camera_name,aspect)
    _fallback_generation=vp._generation;_fallback_reason=reason
    vp._last_report['retained_fallback_reason']=reason

def prepare(camera_name,aspect,draw_api=4):
    global _last_api,_fallback_generation
    api_changed=_last_api!=draw_api
    if api_changed:_fallback_generation=-1;_last_api=draw_api
    if not camera_name or not cmds.objExists(camera_name):
        _library.rt_begin();_library.rt_end();return
    if draw_api!=4:return _fallback(camera_name,aspect,'Retained drawing requires OpenGL Core Profile')
    if _device_error:return _fallback(camera_name,aspect,_device_error)
    # Vertex animation does not turn non-manifold topology into manifold
    # topology. Keep its live GPU scene instead of rebuilding both backends.
    if _mode=='legacy' and not api_changed and not (vp._gpu_rebuild or vp._gpu_graph_dirty or vp._gpu_style_dirty):
        return _fallback(camera_name,aspect,_fallback_reason)
    _switch('retained')
    try:_prepare(camera_name,aspect)
    except retained_geometry.UnsupportedRetained as error:
        _fallback(camera_name,aspect,str(error))

def _prepare(camera_name,aspect):
    global _key,_passes,_geometry_style_key
    key=(vp._generation,vp._gpu_rebuild,vp._gpu_graph_dirty,vp._gpu_style_dirty)
    if _key==key:return
    started=time.perf_counter()
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
    path=maya_scene._dag(camera_name);camera=vp._camera_data(path,aspect)
    if vp._watchers_stale:vp._watch_scene()
    settings=maya_scene.load_settings()
    rebuilt=vp._gpu_scene is None or vp._gpu_rebuild
    if rebuilt:
        if vp._gpu_scene is not None:vp._gpu_scene.close()
        vp._gpu_scene=LiveScene(path,settings,camera,retained=True)
        vp._gpu_scene.generation=vp._generation;_passes=None
        vp._gpu_rebuild=False;vp._gpu_graph_dirty=False
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
    if live.scene.get('merge_groups'):raise retained_geometry.UnsupportedRetained('Merge Groups use the legacy GPU viewport')
    if any(s.get(k) for item in _passes for s in item['styles'] for k in ('hidden_lines','dash_length','distance_reduction','width_variation','taper')):
        raise retained_geometry.UnsupportedRetained('Advanced brush styles use the legacy GPU viewport')
    geometry_style_key=json.dumps([[{k:v for k,v in style.items() if k not in ('line_color','line_width')} for style in p['styles']] for p in _passes],sort_keys=True)
    style_offset=0
    for item in _passes:
        item['retained_style_offset']=style_offset
        for i,style in enumerate(item['styles']):
            color=(c.c_float*3)(*style.get('line_color',[.04,.04,.07]))
            _library.rt_style(style_offset+i,float(style.get('line_width',1.5)),color)
        style_offset+=len(item['styles'])
    if not rebuilt and not changed and not graph_dirty and geometry_style_key==_geometry_style_key:
        _key=(vp._generation,vp._gpu_rebuild,vp._gpu_graph_dirty,vp._gpu_style_dirty)
        vp._last_report.update(geometry_generation=vp._generation,geometry_updated=False,retained_geometry_reused=True,
                              prepare_ms=(time.perf_counter()-started)*1000)
        return
    _library.rt_begin();total=0;edge_total=0;cross_total=0;batch_count=0;pass_reports=[]
    def submit(points,parameters,styles,owners):
        nonlocal total,batch_count
        for owner in np.unique(owners):
            style=styles[int(owner)]
            selected=owners==owner
            p=np.ascontiguousarray(points[selected],np.float64)
            q=np.ascontiguousarray(parameters[selected],np.float32)
            color=(c.c_float*3)(*style.get('line_color',[.04,.04,.07]))
            _library.rt_style(item['retained_style_offset']+int(owner),float(style.get('line_width',1.5)),color)
            if not _library.rt_add_retained(c.c_void_p(p.ctypes.data),c.c_void_p(q.ctypes.data),len(p),float(style.get('line_width',1.5)),color):
                raise retained_geometry.UnsupportedRetained('Retained GPU buffer transfer failed')
            total+=len(p);batch_count+=1
    if not live.empty:
        for item in _passes:
            _library.rt_begin_pass()
            styles=item['styles']
            if not styles:continue
            gpu=live.gpu;gpu.configure_face_styles(item['face_style_ids'],len(styles),item.get('selected_edges'))
            gpu.set_camera(camera) # No viewport_clip: retain ALL pages and future views.
            cross,owners,report=gpu.intersections(styles,settings.get('intersection_tolerance',1e-7))
            parameters=gpu.cross_planes.copy();parameters[:,0,3]=0;parameters[:,1,3]=1
            submit(cross.reshape(-1,2,4)[:,:,:3],parameters,styles,owners)
            cross_total+=len(owners);pass_reports.append(report)
            for i,mesh in enumerate(live.scene['meshes']):
                faces=item['face_style_ids'][i];selected=item.get('selected_edges')
                selected=None if selected is None else selected[i]
                if not np.any(faces>=0) and not selected:continue
                try:data=retained_geometry.candidates(mesh,faces,styles,selected)
                except retained_geometry.UnsupportedRetained as error:
                    raise retained_geometry.UnsupportedRetained(mesh['name']+': '+str(error)) from error
                parameters=np.zeros((len(data['owners']),2,4),np.float32)
                parameters[:,0,:3]=data['normal0'];parameters[:,1,:3]=data['normal1']
                parameters[:,0,3]=data['dynamic']
                submit(data['points'],parameters,styles,data['owners']);edge_total+=len(data['owners'])
    _library.rt_end()
    _geometry_style_key=geometry_style_key
    _key=(vp._generation,vp._gpu_rebuild,vp._gpu_graph_dirty,vp._gpu_style_dirty)
    vp._last_report=dict(state='ready',backend='retained_gpu',segments=total,submitted_segments=total,
        edge_candidates=edge_total,intersection_segments=cross_total,batches=batch_count,
        mesh_count=len(live.scene['meshes']),triangles=sum(len(m['triangles']) for m in live.scene['meshes']),
        smooth_mesh_count=sum(m.get('smooth_level',0)>0 for m in live.scene['meshes']),
        geometry_generation=vp._generation,geometry_updated=changed,prepare_ms=(time.perf_counter()-started)*1000,
        camera_classification='GPU shader on every frame',intersection_diagnostics=pass_reports)
