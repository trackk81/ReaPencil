"""Undoable screen-disk trimming of authored strokes on the chosen mesh/set."""
import copy,json
import numpy as np
from maya import cmds
from maya.api import OpenMaya as om,OpenMayaUI as ui
from . import surface_input as numeric,surface_strokes as strokes

_state={}

def _close():
    if _state.pop('chunk',False):cmds.undoInfo(closeChunk=True)

def _screen(points):
    view=ui.M3dView.active3dView()
    matrix=np.asarray(view.modelViewMatrix()*view.projectionMatrix(),float).reshape(4,4)
    clip=np.column_stack((points,np.ones(len(points))))@matrix
    xy=(clip[:,:2]/clip[:,3,None]*.5+.5)*[view.portWidth(),view.portHeight()]
    return xy,clip[:,3]

def _world_t(t,w0,w1):
    denominator=(1-t)/w0+t/w1
    return float((t/w1)/denominator) if abs(denominator)>1e-20 else float(t)

def _binding(point):
    path=_state['path'];fn=_state['evaluated']['fn'];local=om.MPoint(*point)*path.inclusiveMatrixInverse();near,face=fn.getClosestPoint(local,om.MSpace.kObject)
    counts=fn.getTriangles()[0]
    for index in range(counts[face]):
        ids=list(fn.getPolygonTriangleVertices(face,index));p=np.asarray([[fn.getPoint(v).x,fn.getPoint(v).y,fn.getPoint(v).z] for v in ids]);q=np.asarray([near.x,near.y,near.z]);v=np.linalg.lstsq((p[1:]-p[0]).T,q-p[0],rcond=None)[0];weights=np.r_[1-v.sum(),v]
        if weights.min()>=-1e-6:
            weights=np.maximum(weights,0);weights/=weights.sum();return ids,weights.tolist()
    raise ValueError('Cannot project eraser cut to a source triangle')

def _fragment(value,points,w,refs):
    result=copy.deepcopy(value);ids=[];weights=[];source=[]
    for index,t_screen in refs:
        t=_world_t(t_screen,w[index],w[index+1]);source.append((index,t))
        if t<1e-9:ids.append(value['ids'][index]);weights.append(value['weights'][index])
        elif t>1-1e-9:ids.append(value['ids'][index+1]);weights.append(value['weights'][index+1])
        elif value['ids'][index]==value['ids'][index+1]:ids.append(value['ids'][index]);weights.append(((1-t)*np.asarray(value['weights'][index])+t*np.asarray(value['weights'][index+1])).tolist())
        else:
            tri,bary=_binding((1-t)*points[index]+t*points[index+1]);ids.append(tri);weights.append(bary)
    result['ids']=ids;result['weights']=weights;brush=result.setdefault('brush',{})
    old=value.get('brush',{});u=np.asarray(old.get('u',[]),float)
    if len(u)!=len(points):
        length=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))];u=length/max(length[-1],1e-20)
    pressure=np.asarray(old.get('pressure_values',np.ones(len(points))),float)
    if len(pressure)!=len(points):pressure=np.ones(len(points))
    brush.update(u=[float((1-t)*u[i]+t*u[i+1]) for i,t in source],pressure_values=[float((1-t)*pressure[i]+t*pressure[i+1]) for i,t in source],preserve_domain=True)
    result['erased_fragment']=True
    return result

def _erase_at(position):
    from . import surface_lines as sl
    center=np.asarray(position[:2],float);radius=_state['radius'];remaining=[];changed=0
    for entry in _state['entries']:
        node,value,points=entry['node'],entry['value'],entry['points'];xy,w=_screen(points)
        if np.any(center+radius<xy.min(axis=0)) or np.any(center-radius>xy.max(axis=0)):remaining.append(entry);continue
        query={}
        def visible(index,t):
            pixel=(1-t)*xy[index]+t*xy[index+1];hit=sl._hit(*pixel,state=_state)
            if hit is None:return False
            tri,bary=hit;front=np.sum(_state['evaluated']['world_points'][tri]*np.asarray(bary)[:,None],axis=0);fraction=_world_t(t,w[index],w[index+1]);point=(1-fraction)*points[index]+fraction*points[index+1]
            tolerance=max(1e-5,float(np.linalg.norm(points[index+1]-points[index]))*.3)
            result=np.linalg.norm(front-point)<=tolerance
            if result:query[(index,t)]=point
            return result
        pieces=numeric.outside_disk(xy,center,radius,visible)
        # Reuse the active Preview BVH in one batch so other foreground
        # objects protect covered strokes too, without a per-mesh CPU scan.
        if query:
            from . import viewport
            live=viewport._gpu_scene
            if live is not None and not live.empty and hasattr(live.gpu,'nearest_mesh'):
                names=[m['name'] for m in live.scene['meshes']]
                if _state['shape'] in names:
                    keys=list(query);samples=np.asarray([query[k] for k in keys]);view=ui.M3dView.active3dView();world=view.modelViewMatrix().inverse();eye=np.asarray(world,float).reshape(4,4)[3,:3]
                    camera=view.getCamera();orthographic=om.MFnCamera(camera).isOrtho()
                    if orthographic:
                        direction=om.MVector(0,0,-1)*world;direction=np.asarray([direction.x,direction.y,direction.z]);direction/=np.linalg.norm(direction);directions=np.tile(direction,(len(samples),1));origins=samples-((samples-eye)@direction)[:,None]*direction
                    else:
                        origins=np.tile(eye,(len(samples),1));directions=samples-origins;directions/=np.maximum(np.linalg.norm(directions,axis=1)[:,None],1e-30)
                    origins=np.column_stack((origins,np.ones(len(origins))));directions=np.column_stack((directions,np.zeros(len(directions))))
                    owners=live.gpu.nearest_mesh(np.ascontiguousarray(origins),np.ascontiguousarray(directions),0.,1e12)
                    _state['occlusion_query_counts']={int(k):int(np.count_nonzero(owners==k)) for k in np.unique(owners)}
                    # Maya's source-mesh ray already verified this point. A GPU
                    # miss at a triangle seam must not invent a protected gap.
                    allowed={key:owner<0 or owner==names.index(_state['shape']) for key,owner in zip(keys,owners)}
                    pieces=numeric.outside_disk(xy,center,radius,lambda i,t:allowed.get((i,t),False))
        kept=sum((piece[-1][0]+piece[-1][1])-(piece[0][0]+piece[0][1]) for piece in pieces)
        if kept>=len(points)-1-1e-8:remaining.append(entry);continue
        changed+=1
        for index,refs in enumerate(pieces):
            new=_fragment(value,points,w,refs)
            if index==0:target=node;cmds.setAttr(target+'.bindings',json.dumps(new),type='string')
            else:
                target=sl.create(_state['shape'],_state['set'],new['ids'],new['weights'],new['level'],_state['evaluated']['faces'],new.get('brush'));cmds.setAttr(target+'.bindings',json.dumps(new),type='string')
            mesh=dict(_surface_strokes=[copy.deepcopy(new)]);strokes.update(mesh,_state['evaluated']['world_points']);remaining.append(dict(node=target,value=new,points=mesh['_surface_strokes'][0]['points']))
        if not pieces:cmds.delete(node)
    _state['entries']=remaining
    if changed:sl._changed()
    return changed

def _press(position):
    from . import surface_lines as sl
    shape=_state['shape'];line_set=_state['set'];_state['path'],_state['evaluated']=sl._evaluated(shape);_state['accel']=om.MFnMesh.autoUniformGridParams();entries=[]
    for record in sl.records().get(shape,[]):
        if record['style']!=line_set or record['level']!=_state['evaluated']['level'] or record['topology']!=strokes.topology_key(_state['evaluated']['faces']):continue
        node=record['node'];value=json.loads(cmds.getAttr(node+'.bindings'));mesh=dict(_surface_strokes=[copy.deepcopy(value)]);strokes.update(mesh,_state['evaluated']['world_points']);entries.append(dict(node=node,value=value,points=mesh['_surface_strokes'][0]['points']))
    _state['entries']=entries;cmds.undoInfo(openChunk=True,chunkName='Erase ReaPencil Surface Strokes');_state['chunk']=True
    _erase_at(position);_state['screen']=np.asarray(position[:2],float)

def _drag(position):
    point=np.asarray(position[:2],float);previous=_state.get('screen',point);steps=max(1,int(np.ceil(np.linalg.norm(point-previous)/max(1.,_state['radius']*.4))))
    for t in np.linspace(0,1,steps+1)[1:]:_erase_at((1-t)*previous+t*point)
    _state['screen']=point

def begin(shape,line_set,radius=20.):
    _close();_state.clear();_state.update(shape=shape,set=line_set,radius=float(radius))
    context='reaPencilSurfaceEraseContext'
    if cmds.draggerContext(context,exists=True):cmds.deleteUI(context)
    def press():
        try:_press(cmds.draggerContext(context,q=True,anchorPoint=True))
        except Exception:_close();raise
    def drag():
        try:_drag(cmds.draggerContext(context,q=True,dragPoint=True))
        except Exception:_close();raise
    cmds.draggerContext(context,pressCommand=press,dragCommand=drag,releaseCommand=_close,finalize=_close,cursor='crossHair',space='screen',undoMode='step')
    from .surface_feedback import install
    cmds.setToolTo(context);install();om.MGlobal.displayInfo('ReaPencil: erase authored strokes on the selected mesh/Line Set. Ctrl+Z restores an eraser gesture.')

