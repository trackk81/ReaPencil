"""Scene-persisted barycentric strokes and a selected-mesh drawing context."""
import json
import numpy as np
from maya import cmds
from maya.api import OpenMaya as om,OpenMayaUI as ui
from . import surface_strokes as numeric
MARKER='reaPencilSurfaceStroke'
_draw={};_warnings=set()
_brush=dict(shape='uniform',pressure=False,minimum=.1,smoothing=0.,width=None,stabilization_strength=30.,catchup=True)
_eraser=dict(radius=20.)
_erase={}
_live=None;_live_revision=0

def source_style(line_set):
    from . import line_graph as graph
    for line in graph.snapshot():
        for item in line['sets']:
            if item['node']==line_set:return line['line'],item['settings']
    for line in graph.list_lines():
        if line_set in graph.list_sets(line):
            return line,dict(graph.get_settings(line),**graph.resolved_settings(line_set))
    raise ValueError('Choose an existing ReaPencil Line Set before drawing')

def preview_revision():return _live_revision

def sync_preview(scene):
    """Inject GPU-only feedback into an exported scene, never into Maya/DG."""
    dirty=set()
    for index,mesh in enumerate(scene['meshes']):
        previous=mesh.get('_drawing_revision',-1)
        if previous==_live_revision:continue
        values=[s for s in mesh.get('_surface_strokes',[]) if not s.get('_drawing_feedback')]
        old_count=len(mesh.get('_surface_strokes',[]));applicable=_live is not None and mesh['name']==_draw.get('shape')
        if applicable:values.append(dict(_live))
        if len(values)!=old_count or applicable:dirty.add(index)
        if values:mesh['_surface_strokes']=values
        else:mesh.pop('_surface_strokes',None)
        mesh['_drawing_revision']=_live_revision
    return dirty

def _freeze_brush(line_set,options):
    value=dict(options);width=value.pop('width',None)
    if width is not None:
        _,source=source_style(line_set);base=float(source.get('line_width',1.5))
        value['width_scale']=float(width)/base if base>0 else 1.
    return value

def _changed():
    from . import viewport
    viewport._scene_changed();viewport.request_refresh()

def repair_selected_legacy_drawings():
    """Explicit repair only: v1 import/demo bindings were already correct."""
    from . import maya_scene
    selected=[n for n in cmds.ls(sl=True,long=True) or [] if cmds.attributeQuery(MARKER,node=n,exists=True)]
    if not selected:raise ValueError('Select old directly drawn stroke network nodes first')
    repaired=[]
    with maya_scene.undo_chunk('Repair old surface drawing coordinates'):
        for node in selected:
            value=json.loads(cmds.getAttr(node+'.bindings'))
            if value.get('version')!=1:continue
            value['weights']=np.roll(np.asarray(value['weights'],float),-1,axis=1).tolist()
            value.update(version=2,input_contract='maya-bary-v1-v2-v3',legacy_mouse_repaired=True)
            cmds.setAttr(node+'.bindings',json.dumps(value),type='string');repaired.append(node)
    if repaired:_changed()
    return repaired

def nodes():return cmds.ls('*.'+MARKER,objectsOnly=True,recursive=True) or []

def records():
    from . import line_graph as graph
    owners={s:l for l in graph.list_lines() if cmds.getAttr(l+'.active') for s in graph.list_sets(l) if cmds.getAttr(s+'.active')}
    result={}
    for node in nodes():
        shapes=cmds.listConnections(node+'.source',s=True,d=False,shapes=True)
        sets=cmds.listConnections(node+'.lineSet',s=True,d=False) or []
        if not shapes or not sets or sets[0] not in owners:continue
        paths=cmds.ls(shapes[0],long=True,allPaths=True) or []
        if len(paths)!=1:continue
        raw=cmds.getAttr(node+'.bindings')
        if not raw:continue
        try:value=json.loads(raw)
        except (ValueError,TypeError):
            om.MGlobal.displayWarning(node+': invalid surface stroke data; skipped');continue
        value.update(node=node,style=sets[0],line=owners[sets[0]])
        result.setdefault(paths[0],[]).append(value)
    return result

def attach(mesh,evaluated,values,warnings):
    if not values:return
    key=numeric.topology_key(mesh['faces']);valid=[]
    for record in values:
        if record['level']!=evaluated['level'] or record['topology']!=key:
            message=record['node']+': surface stroke topology/smooth level changed; rebind or redraw the stroke'
            warnings.append(message)
            if message not in _warnings:om.MGlobal.displayWarning(message);_warnings.add(message)
            continue
        valid.append(dict(record))
    if valid:mesh['_surface_strokes']=valid;numeric.update(mesh,mesh['vertices'])

def create(shape,line_set,ids,weights,level,faces,brush=None):
    from . import maya_scene,line_graph as graph
    ids=np.asarray(ids,np.int64);weights=np.asarray(weights,np.float64)
    if ids.ndim!=2 or ids.shape[1]!=3 or weights.shape!=ids.shape or len(ids)<2 or not np.isfinite(weights).all() or np.any(weights<-1e-7) or not np.allclose(weights.sum(axis=1),1):raise ValueError('Invalid surface stroke bindings')
    with maya_scene.undo_chunk('Draw ReaPencil Surface Stroke'):
        node=cmds.createNode('network',name='reaPencilSurfaceStroke',skipSelect=True)
        cmds.addAttr(node,ln=MARKER,at='bool',dv=True);cmds.addAttr(node,ln='source',at='message');cmds.addAttr(node,ln='lineSet',at='message');cmds.addAttr(node,ln='bindings',dt='string')
        cmds.connectAttr(shape+'.message',node+'.source');cmds.connectAttr(line_set+'.message',node+'.lineSet')
        value=dict(version=2,ids=ids.tolist(),weights=weights.tolist(),level=int(level),topology=numeric.topology_key(faces),input_contract='maya-bary-v1-v2-v3')
        if brush:value['brush']=brush
        cmds.setAttr(node+'.bindings',json.dumps(value),type='string')
    _changed();return node

def _evaluated(shape):
    from . import smooth_geometry,maya_scene
    path=om.MSelectionList().add(shape).getDagPath(0)
    value=smooth_geometry.evaluate(path,True,'viewport',as_arrays=True)
    _,ids=value['fn'].getTriangles();value['triangles']=np.asarray(ids,np.int64).reshape(-1,3)
    return path,value

def bind_points(shape,line_set,world_points):
    """API/import path: project supplied world points and create one undoable stroke."""
    path,e=_evaluated(shape);fn=e['fn'];ids=[];weights=[];positions=[]
    triangle_counts=fn.getTriangles()[0]
    def project(point):
        local=om.MPoint(*point)*path.inclusiveMatrixInverse();near,face=fn.getClosestPoint(local,om.MSpace.kObject)
        for ti in range(triangle_counts[face]):
            tri=list(fn.getPolygonTriangleVertices(face,ti));p=np.array([[x.x,x.y,x.z] for x in (fn.getPoint(v) for v in tri)]);q=np.array([near.x,near.y,near.z]);xy=np.linalg.lstsq((p[1:]-p[0]).T,q-p[0],rcond=None)[0];w=np.r_[1-xy.sum(),xy]
            if np.min(w)>=-1e-7:
                world=near*path.inclusiveMatrix();return tri,w,np.array([world.x,world.y,world.z])
        raise ValueError('Cannot bind point to a source triangle')
    def append(hit,depth=0):
        if ids and hit[0]!=ids[-1] and depth<20 and np.linalg.norm(hit[2]-positions[-1])>1e-7:
            midpoint=project((positions[-1]+hit[2])*.5)
            append(midpoint,depth+1);append(hit,depth+1);return
        if not positions or np.linalg.norm(hit[2]-positions[-1])>1e-10:
            ids.append(hit[0]);weights.append(hit[1]);positions.append(hit[2])
    for point in world_points:append(project(point))
    return create(shape,line_set,ids,weights,e['level'],e['faces'])


def _hit(x,y,state=None):
    view=ui.M3dView.active3dView();origin=om.MPoint();direction=om.MVector()
    ix,iy=int(np.floor(x)),int(np.floor(y));view.viewToWorld(ix,iy,origin,direction)
    # Maya's API accepts integer pixels. Interpolate neighboring rays so a
    # stabilized subpixel path does not snap back to the pixel grid.
    for dx,dy,fraction in ((1,0,float(x-ix)),(0,1,float(y-iy))):
        if fraction>1e-8:
            other=om.MPoint();ray=om.MVector();base=om.MPoint();base_ray=om.MVector();view.viewToWorld(ix+dx,iy+dy,other,ray);view.viewToWorld(ix,iy,base,base_ray)
            origin+=fraction*(other-base);direction+=fraction*(ray-base_ray)
    state=_draw if state is None else state
    path=state['path'];fn=state['evaluated']['fn'];inverse=path.inclusiveMatrixInverse()
    o=origin*inverse;v=direction*inverse
    hit=fn.closestIntersection(om.MFloatPoint(o),om.MFloatVector(v),om.MSpace.kObject,1e12,False,accelParams=state['accel'])
    if hit is None:return None
    point,param,face,triangle,b1,b2=hit
    # Maya defines P=b1*V0+b2*V1+(1-b1-b2)*V2. The old cyclic
    # permutation moved every mouse hit to a different place in its face.
    weights=np.maximum([b1,b2,1-b1-b2],0.);weights/=weights.sum()
    return list(fn.getPolygonTriangleVertices(face,triangle)),weights.tolist()

def _append_hit(hit,screen,pressure=1.,depth=0):
    previous=_draw.get('hit_screen')
    if _draw['ids'] and hit[0]!=_draw['ids'][-1] and previous is not None and depth<16 and np.linalg.norm(screen-previous)>.001:
        mid=(screen+previous)*.5;mid_hit=_hit(*mid)
        if mid_hit is not None:
            mid_pressure=(float(_draw['pressures'][-1])+pressure)*.5
            _append_hit(mid_hit,mid,mid_pressure,depth+1);_append_hit(hit,screen,pressure,depth+1);return
    if not _draw['ids'] or hit[0]!=_draw['ids'][-1] or np.linalg.norm(np.array(hit[1])-_draw['weights'][-1])>1e-7:
        _draw['ids'].append(hit[0]);_draw['weights'].append(hit[1]);_draw['pressures'].append(float(pressure))
    _draw['hit_screen']=np.asarray(screen)

def _sample(position,pressure=None,_force=False):
    from .surface_input import stabilize
    x,y=position[:2]
    if pressure is None:
        from .surface_brush_ui import current_pressure
        pressure=current_pressure() if _draw.get('brush',{}).get('pressure') else 1.
    pressure=float(np.clip(pressure,0.,1.))
    previous=_draw.get('raw_screen') if not _force else _draw.get('screen')
    old_pressure=_draw.get('sample_pressure',pressure)
    options=_draw.get('brush',{});filtered=_draw.get('screen');steps=max(1,int(np.ceil(np.linalg.norm(np.array([x,y])-previous)/2))) if previous is not None else 1
    for t in np.linspace(0,1,steps+1)[1:] if previous is not None else [1]:
        raw=(1-t)*previous+t*np.array([x,y]) if previous is not None else np.array([x,y])
        p=raw if _force else stabilize(filtered,raw,options.get('stabilization_strength',0),options.get('smoothing',0))
        filtered=p;hit=_hit(*p)
        if hit is None:
            _finish();continue
        _append_hit(hit,p,(1-t)*old_pressure+t*pressure)
    _draw['screen']=filtered;_draw['raw_screen']=np.array([x,y])
    _draw['sample_pressure']=pressure
    _preview()

def _clear_preview():
    global _live,_live_revision
    if _live is not None:
        _live=None;_live_revision+=1
        if not cmds.about(batch=True):cmds.refresh(currentView=True,force=True)

def _preview():
    global _live,_live_revision
    if len(_draw.get('ids',[]))<2:return
    mesh=dict(_surface_strokes=[dict(ids=list(_draw['ids']),weights=list(_draw['weights']))]);numeric.update(mesh,_draw['evaluated']['world_points']);value=mesh['_surface_strokes'][0];points=value['points'];length=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    brush=dict(_draw['brush'],pressure_values=list(_draw['pressures']),u=(length/max(length[-1],1e-20)).tolist())
    value.update(node='__reaPencil_live_drawing__',style=_draw['set'],line=_draw['line'],brush=brush,_drawing_feedback=True)
    _live=value;_live_revision+=1
    if not cmds.about(batch=True):
        from . import surface_feedback
        surface_feedback.update_now()
        # Dragger contexts can defer normal DG/Qt repaint until release.
        # Render this already sampled stroke now, without a scene rebuild.
        cmds.refresh(currentView=True,force=True)

def _finish():
    if len(_draw.get('ids',[]))>=2:
        mesh=dict(_surface_strokes=[dict(ids=_draw['ids'],weights=_draw['weights'])]);numeric.update(mesh,_draw['evaluated']['world_points'])
        points=mesh['_surface_strokes'][0]['points'];length=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
        brush=dict(_draw.get('brush',{}));brush.update(pressure_values=_draw['pressures'],u=(length/max(length[-1],1e-20)).tolist())
        create(_draw['shape'],_draw['set'],_draw['ids'],_draw['weights'],_draw['evaluated']['level'],_draw['evaluated']['faces'],brush)
    _draw['ids']=[];_draw['weights']=[];_draw['pressures']=[];_draw['hit_screen']=None;_clear_preview()

def begin(shape,line_set,brush=None):
    _clear_preview();path,e=_evaluated(shape);line,source=source_style(line_set);_draw.clear();_draw.update(shape=shape,set=line_set,line=line,source_style=source,path=path,evaluated=e,ids=[],weights=[],pressures=[],screen=None,raw_screen=None,hit_screen=None,brush=_freeze_brush(line_set,_brush if brush is None else brush),brush_options=brush,accel=om.MFnMesh.autoUniformGridParams())
    context='reaPencilSurfaceDrawContext'
    if cmds.draggerContext(context,exists=True):cmds.deleteUI(context)
    def press():
        _draw['line'],_draw['source_style']=source_style(line_set)
        _draw['brush']=_freeze_brush(line_set,_brush if _draw['brush_options'] is None else _draw['brush_options'])
        _draw['path'],_draw['evaluated']=_evaluated(shape);_draw.update(ids=[],weights=[],pressures=[],screen=None,raw_screen=None,hit_screen=None,accel=om.MFnMesh.autoUniformGridParams())
        _sample(cmds.draggerContext(context,q=True,anchorPoint=True))
    def drag():_sample(cmds.draggerContext(context,q=True,dragPoint=True))
    def release():
        if _draw.get('raw_screen') is not None and _draw['brush'].get('catchup',True):_sample(_draw['raw_screen'],pressure=_draw.get('sample_pressure',1.),_force=True)
        _finish();_draw['screen']=None;_draw['raw_screen']=None
    cmds.draggerContext(context,pressCommand=press,dragCommand=drag,releaseCommand=release,finalize=_clear_preview,cursor='crossHair',space='screen',undoMode='sequence')
    cmds.setToolTo(context);om.MGlobal.displayInfo('ReaPencil: drag on the selected mesh to draw. Q exits; Ctrl+Z undoes a stroke.')
    from .surface_brush_ui import install_tablet_filter
    install_tablet_filter()
    from .surface_feedback import install
    install()

def show():
    from .surface_brush_ui import show as open_brush
    return open_brush()

def _legacy_show():
    from . import line_graph as graph,i18n
    def text(en,ko):return en if i18n.language()=='en' else ko
    shapes=[]
    for n in cmds.ls(sl=True,long=True) or []:shapes.extend([n] if cmds.nodeType(n)=='mesh' else cmds.listRelatives(n,shapes=True,noIntermediate=True,fullPath=True,type='mesh') or [])
    if len(shapes)!=1:raise ValueError(text('Select one polygon mesh first','먼저 폴리곤 메시 하나를 선택하세요'))
    sets=[s for l in graph.list_lines() for s in graph.list_sets(l)]
    if not sets:raise ValueError(text('Create a ReaPencil Line Set first','먼저 ReaPencil 라인셋을 만드세요'))
    window='reaPencilSurfaceDrawing'
    if cmds.window(window,exists=True):cmds.deleteUI(window)
    cmds.window(window,title=text('ReaPencil — Draw on Mesh (Test)','ReaPencil — 메시 위에 선 그리기 (테스트)'),widthHeight=(470,220));cmds.columnLayout(adjustableColumn=True,rowSpacing=10)
    cmds.text(label=shapes[0],align='left');menu=cmds.optionMenuGrp(label=text('Line Set','라인셋'))
    for s in sets:cmds.menuItem(label=s)
    cmds.text(label=text('Drag to draw. Q exits; Ctrl+Z undoes. Keep topology and smooth level unchanged.','드래그로 그리기 · Q로 종료 · Ctrl+Z로 취소\n면·정점 구조와 스무스 단계를 유지해야 합니다.'),align='left',wordWrap=True)
    cmds.button(label=text('Start drawing','선 그리기 시작'),command=lambda *_:begin(shapes[0],cmds.optionMenuGrp(menu,q=True,value=True)))
    cmds.button(label=text('Select strokes on this mesh','이 메시의 그린 선 선택'),command=lambda *_:cmds.select([n for n in nodes() if shapes[0] in (cmds.ls(cmds.listConnections(n+'.source',s=True,d=False,shapes=True) or [],long=True) or [])],replace=True))
    cmds.showWindow(window);return window
