"""Opt-in alpha boundary settings on Maya meshes and non-destructive export."""
from .i18n import tr
import json,os
from functools import lru_cache
import numpy as np
from maya import cmds
from maya.api import OpenMaya as om
from . import alpha_geometry as geometry

ATTRIBUTE='reaPencilAlphaBoundary'


def _triangulate_contours(loops):
    """Maya's constrained polygon tessellator avoids slicing every tiny island.

    Build a detached mesh data object, never scene DAG/history nodes. Validate
    filled area so a failed hole triangulation cannot silently fill transparency.
    """
    if not loops:return []
    areas=np.array([np.sum(geometry._cross(p,np.roll(p,-1,axis=0)))*.5 for p in loops])
    bounds=np.array([[p.min(axis=0),p.max(axis=0)] for p in loops]);parents=[]
    for i,p in enumerate(loops):
        point=p[0]
        candidates=np.flatnonzero((np.abs(areas)>abs(areas[i])+1e-14)&
            np.all(bounds[:,0]<point+1e-10,axis=1)&np.all(bounds[:,1]>point-1e-10,axis=1))
        parent=-1
        for j in sorted(candidates,key=lambda j:abs(areas[j])):
            a=loops[j];b=np.roll(a,-1,axis=0)
            active=(a[:,1]>point[1])!=(b[:,1]>point[1])
            a,b=a[active],b[active]
            x=a[:,0]+(point[1]-a[:,1])*(b[:,0]-a[:,0])/(b[:,1]-a[:,1])
            if np.count_nonzero(x>point[0])%2:parent=int(j);break
        parents.append(parent)
    depths=[]
    for parent in parents:
        depth=0
        while parent>=0:depth+=1;parent=parents[parent]
        depths.append(depth)
    outers=[i for i,depth in enumerate(depths) if depth%2==0]
    loops=[p if (areas[i]>0)==(depths[i]%2==0) else p[::-1] for i,p in enumerate(loops)]
    counts=[len(loops[i]) for i in outers];points=np.concatenate([loops[i] for i in outers])
    owner=om.MFnMeshData().create();fn=om.MFnMesh()
    fn.create(om.MPointArray([(float(x),float(y),0) for x,y in points]),counts,list(range(len(points))),parent=owner)
    for face,outer in enumerate(outers):
        holes=[i for i,p in enumerate(parents) if p==outer]
        if holes:
            points=np.concatenate([loops[i] for i in holes])
            fn.addHoles(face,om.MPointArray([(float(x),float(y),0) for x,y in points]),[len(loops[i]) for i in holes],False)
    _,ids=fn.getTriangles();points=np.array([[p.x,p.y] for p in fn.getPoints()])
    tris=points[np.asarray(ids,np.int32).reshape(-1,3)]
    actual=np.abs(geometry._cross(tris[:,1]-tris[:,0],tris[:,2]-tris[:,0])).sum()*.5
    expected=sum(abs(a)*(-1 if depth%2 else 1) for a,depth in zip(areas,depths))
    if abs(actual-expected)>max(1e-8,expected*1e-6):
        raise ValueError('Maya could not triangulate the alpha holes faithfully; reduce Simplify')
    return tris


def configuration(shape):
    if not cmds.attributeQuery(ATTRIBUTE,node=shape,exists=True):return None
    value=cmds.getAttr(shape+'.'+ATTRIBUTE)
    data=json.loads(value) if value else None
    return data if data and data.get('enabled',True) else None


def selected_meshes():
    result=[]
    for node in cmds.ls(sl=True,long=True,objectsOnly=True) or []:
        if cmds.nodeType(node)=='mesh':result.append(node)
        elif cmds.nodeType(node)=='transform':
            result.extend(cmds.listRelatives(node,allDescendents=True,type='mesh',fullPath=True) or [])
        elif cmds.nodeType(node) in ('lambert','blinn','phong','phongE','aiStandardSurface','standardSurface','rampShader'):
            for sg in cmds.listConnections(node,type='shadingEngine') or []:
                for member in cmds.sets(sg,q=True) or []:
                    base=member.split('.')[0]
                    result.extend(cmds.ls(base,type='mesh',long=True) or
                                  cmds.listRelatives(base,shapes=True,noIntermediate=True,fullPath=True,type='mesh') or [])
    return sorted(set(n for n in result if not cmds.getAttr(n+'.intermediateObject')))


def _source(plug,inverted=False):
    links=cmds.listConnections(plug,s=True,d=False,plugs=True) or []
    if len(links)!=1:return None
    node,attr=links[0].split('.',1);kind=cmds.nodeType(node)
    if kind=='reverse':
        component={'outputX':'inputX','outputY':'inputY','outputZ':'inputZ'}.get(attr,'input')
        return _source(node+'.'+component,not inverted)
    if kind!='file':return None
    if attr.startswith('outTransparency'):
        inverted=not inverted;channel='luminance' if cmds.getAttr(node+'.alphaIsLuminance') else 'alpha'
    elif attr=='outAlpha':channel='luminance' if cmds.getAttr(node+'.alphaIsLuminance') else 'alpha'
    else:channel={'outColorR':'red','outColorG':'green','outColorB':'blue'}.get(attr,'luminance')
    unsupported=[]
    for name,default in [('coverage',(1.,1.)),('translateFrame',(0.,0.)),('rotateFrame',0.),('rotateUV',0.),
                         ('mirrorU',False),('mirrorV',False),('stagger',False),('noiseUV',(0.,0.))]:
        value=cmds.getAttr(node+'.'+name)
        if isinstance(value,list):value=value[0]
        if not np.allclose(value,default):unsupported.append(name)
    if unsupported:raise ValueError(node+': Alpha Boundary does not yet support '+', '.join(unsupported))
    if bool(cmds.getAttr(node+'.wrapU'))!=bool(cmds.getAttr(node+'.wrapV')):
        raise ValueError(node+': use matching U and V wrap for Alpha Boundary')
    if cmds.getAttr(node+'.useFrameExtension') or cmds.getAttr(node+'.uvTilingMode'):
        raise ValueError(node+': animated textures and UDIM require baking to a single image first')
    if channel=='alpha' and (cmds.getAttr(node+'.alphaGain')!=1 or cmds.getAttr(node+'.alphaOffset')!=0):
        raise ValueError(node+': bake non-default alpha gain/offset before boundary generation')
    return dict(file_node=node,path=cmds.getAttr(node+'.fileTextureName'),channel=channel,invert=inverted,
                repeat=list(cmds.getAttr(node+'.repeatUV')[0]),offset=list(cmds.getAttr(node+'.offset')[0]),
                wrap=bool(cmds.getAttr(node+'.wrapU') and cmds.getAttr(node+'.wrapV')))


def material_sources(shape):
    from .maya_scene import _dag
    path=_dag(shape);engines,ids=om.MFnMesh(path).getConnectedShaders(path.instanceNumber());sources={}
    for index,sg in enumerate(engines):
        shaders=cmds.listConnections(om.MFnDependencyNode(sg).name()+'.surfaceShader',s=True,d=False) or []
        if not shaders:continue
        shader=shaders[0]
        for attr,invert in [('opacity',False),('transparency',True)]:
            if cmds.attributeQuery(attr,node=shader,exists=True):
                source=_source(shader+'.'+attr,invert)
                if source:
                    sources[str(index)]=dict(source,shader=shader,shader_uuid=(cmds.ls(shader,uuid=True) or [''])[0]);break
    return sources


@lru_cache(maxsize=32)
def _image_cells(path,modified,size,channel,invert,threshold,resolution,simplify):
    from PySide6.QtGui import QImage
    from PySide6.QtCore import Qt
    image=QImage(path)
    if image.isNull():raise ValueError('Cannot read alpha texture: '+path)
    if channel=='alpha' and not image.hasAlphaChannel():
        raise ValueError('Image has no alpha channel; choose Luminance for an opacity mask: '+path)
    if max(image.width(),image.height())>resolution:
        image=image.scaled(resolution,resolution,Qt.KeepAspectRatio,Qt.SmoothTransformation)
    image=image.convertToFormat(QImage.Format_RGBA8888)
    data=np.frombuffer(image.constBits(),np.uint8,count=image.sizeInBytes()).reshape(image.height(),image.bytesPerLine())
    rgba=data[:,:image.width()*4].reshape(image.height(),image.width(),4).astype(np.float64)/255.
    if channel=='luminance':alpha=rgba[:,:,:3]@np.array([.2126,.7152,.0722])
    else:alpha=rgba[:,:,dict(red=0,green=1,blue=2,alpha=3)[channel]]
    if invert:alpha=1-alpha
    loops=geometry.contours(alpha,threshold,simplify)
    return _triangulate_contours(loops),dict(texture_size=[image.width(),image.height()],contours=len(loops),
                                            contour_vertices=sum(len(p) for p in loops))


def _cells(source,config):
    path=os.path.abspath(os.path.expandvars(source['path']))
    stat=os.stat(path)
    return _image_cells(path,stat.st_mtime_ns,stat.st_size,source['channel'],bool(source.get('invert',False)),
                        float(config['threshold']),int(config['resolution']),float(config['simplify']))


def apply_selected(path='',channel='alpha',invert=False,threshold=.5,resolution=256,simplify=.25):
    from . import maya_scene,viewport
    shapes=selected_meshes()
    if not shapes:raise ValueError('Select polygon objects or their materials first')
    if not 0<threshold<1 or not 16<=resolution<=4096 or not 0<=simplify<=2:
        raise ValueError('Use threshold 0–1, resolution 16–4096, simplify 0–2 pixels')
    plans=[]
    selected_materials={n for n in cmds.ls(sl=True) or [] if cmds.attributeQuery('outColor',node=n.split('.')[0],exists=True)
                        and cmds.nodeType(n.split('.')[0]) not in ('mesh','transform')}
    for shape in shapes:
        sources=({'all':dict(path=os.path.abspath(path),channel=channel,invert=bool(invert),wrap=True)} if path else material_sources(shape))
        if selected_materials and not path:sources={k:s for k,s in sources.items() if s.get('shader') in selected_materials}
        if not sources:continue
        config=dict(version=1,enabled=True,threshold=threshold,resolution=resolution,simplify=simplify,sources=sources)
        for source in sources.values():_cells(source,config) # Validate before any scene edits.
        plans.append((shape,config))
    if not plans:raise ValueError('No supported opacity texture is connected. Choose an image explicitly.')
    with maya_scene.undo_chunk('ReaPencil Alpha Boundary'):
        for shape,config in plans:maya_scene._json_attr(shape,ATTRIBUTE,config)
    viewport._scene_changed();viewport.request_refresh()
    return [shape for shape,_ in plans]


def remove_selected():
    from . import maya_scene,viewport
    shapes=selected_meshes()
    with maya_scene.undo_chunk('Remove ReaPencil Alpha Boundary'):
        for shape in shapes:
            if cmds.attributeQuery(ATTRIBUTE,node=shape,exists=True):cmds.deleteAttr(shape+'.'+ATTRIBUTE)
    viewport._scene_changed();viewport.request_refresh()
    return shapes


def _texture_fn(path,evaluated):
    """Subdivision provenance uses a synthetic UV set; evaluate real UVs separately."""
    if not evaluated['level']:return om.MFnMesh(path),None
    from . import legacy_smooth
    source=om.MFnMesh(path);owner=om.MFnMeshData().create()
    if legacy_smooth.required(source,evaluated.get('purpose','render')):
        om.MFnMesh().copy(source.object(),owner)
        return legacy_smooth.generate(source,owner,evaluated['level'])
    options=source.getSmoothMeshDisplayOptions();options.divisions=evaluated['level']
    return om.MFnMesh(source.generateSmoothMesh(owner,options)),owner


def transform_mesh(mesh,path,evaluated,config):
    fn,owner=_texture_fn(path,evaluated)
    if fn.numVertices!=len(mesh['vertices']) or fn.numPolygons!=len(mesh['faces']):
        raise ValueError('Alpha UV topology differs from evaluated mesh: '+mesh['name'])
    triangles=np.asarray(mesh['triangles'],np.int64);tfaces=np.asarray(mesh['triangle_faces'],np.int32)
    uvset=fn.currentUVSetName();uvs=[];maps={};face_cells={};face_sources={};stats=[]
    sources=config['sources']
    if 'all' not in sources:
        current={};engines,_=om.MFnMesh(path).getConnectedShaders(path.instanceNumber())
        for index,sg in enumerate(engines):
            shaders=cmds.listConnections(om.MFnDependencyNode(sg).name()+'.surfaceShader',s=True,d=False) or []
            if not shaders:continue
            uuid=(cmds.ls(shaders[0],uuid=True) or [''])[0]
            for source in sources.values():
                if source.get('shader_uuid')==uuid or (not source.get('shader_uuid') and source.get('shader')==shaders[0]):
                    current[str(index)]=source;break
        sources=current
    for face in np.unique(tfaces):
        material=str(mesh['material_ids'][face]);source=sources.get('all',sources.get(material))
        if source is None:continue
        cells,info=_cells(source,config);face_cells[int(face)]=cells;face_sources[int(face)]=source
        if info not in stats:stats.append(info)
        face_vertices=list(fn.getPolygonVertices(int(face)))
        maps[int(face)]={v:fn.getPolygonUV(int(face),i,uvset) for i,v in enumerate(face_vertices)}
    for triangle,face in zip(triangles,tfaces):
        if int(face) in maps:
            source=face_sources[int(face)]
            uv=np.array([maps[int(face)][int(v)] for v in triangle])
            uv=uv*np.asarray(source.get('repeat',[1,1]))+np.asarray(source.get('offset',[0,0]))
        else:uv=np.array([[0,0],[1,0],[0,1]])
        uvs.append(uv)
    # Per-material wrap differences are explicit; avoid silently interpreting one
    # material's UVs using another material's sampler.
    wrapping={bool(s.get('wrap',True)) for s in face_sources.values()}
    if len(wrapping)>1:raise ValueError('Use matching U/V wrap on alpha materials in one mesh')
    cut=geometry.cut_mesh(mesh['vertices'],triangles,tfaces,uvs,face_cells,wrap=next(iter(wrapping),True))
    mapping=cut.pop('source_faces');bind=dict(ids=cut.pop('bind_ids'),weights=cut.pop('bind_weights'),
                                            source_vertex_count=len(mesh['vertices']))
    # Descendants of authored hard/selected edges survive trimming.
    edge_map={}
    for face in cut['faces']:
        for a,b in zip(face,face[1:]+face[:1]):
            support=set(int(i) for vi in (a,b) for i,w in zip(bind['ids'][vi],bind['weights'][vi]) if abs(w)>1e-9)
            if len(support)==2:
                pair=tuple(sorted(support))
                edge_map.setdefault(pair,set()).add(tuple(sorted((a,b))))
    def remap(pairs):return [list(edge) for p in pairs for edge in edge_map.get(tuple(sorted(map(int,p))),())]
    base=np.asarray(mesh.get('base_face_ids',np.arange(len(mesh['faces']))),np.int32)
    mesh['base_face_ids']=base[mapping];mesh['material_ids']=np.asarray(mesh['material_ids'])[mapping].tolist()
    for item in mesh.get('line_passes',[]):
        item['face_line_sets']=[item['face_line_sets'][i] for i in mapping]
        item['selected_edges']={k:remap(v) for k,v in item.get('selected_edges',{}).items()}
    for name in ('hard_edges','selected_edges'):mesh[name]=remap(mesh.get(name,[]))
    if mesh.get('smooth_level'):
        mesh['base_edge_children']={key:remap(values) for key,values in mesh['base_edge_children'].items()}
    else:mesh['base_edge_children']={'%d,%d'%p:[list(e) for e in edges] for p,edges in edge_map.items()}
    mesh.pop('triangle_normals',None)
    mesh.update(cut);mesh['alpha_boundary']=True;mesh['_alpha_binding']=bind;mesh['alpha_boundary_stats']=stats
    return mesh


def deform(mesh,source_world):
    bind=mesh.get('_alpha_binding')
    if bind is None:return source_world
    if len(source_world)!=bind['source_vertex_count']:raise ValueError('Alpha source topology changed; rebuild required')
    return np.sum(np.asarray(source_world)[bind['ids']]*bind['weights'][:,:,None],axis=1)


def show():
    from .ui import _safe
    window='reaPencilAlphaBoundaryWindow'
    if cmds.window(window,exists=True):cmds.deleteUI(window)
    cmds.window(window,title=tr('ReaPencil — Alpha Boundary'),widthHeight=(470,340))
    cmds.columnLayout(adjustableColumn=True,rowSpacing=8)
    cmds.text(label=tr('Select objects or materials. Original meshes stay unchanged.'),align='left')
    cmds.text(label=tr('Cutout boundaries are used by live lines and CPU rendering.'),align='left')
    file=cmds.textFieldButtonGrp(label=tr('Image (optional)'),buttonLabel=tr('Browse'),text=tr(''))
    def browse(*_):
        chosen=cmds.fileDialog2(fileMode=1,caption='Choose alpha or opacity image')
        if chosen:cmds.textFieldButtonGrp(file,e=True,text=chosen[0])
    cmds.textFieldButtonGrp(file,e=True,buttonCommand=browse)
    cmds.text(label=tr('Blank image: detect opacity textures from assigned materials.'),align='left')
    channel=cmds.optionMenuGrp(label=tr('Image channel'))
    for label in ('Alpha','Luminance','Red','Green','Blue'):cmds.menuItem(label=tr(label))
    invert=cmds.checkBoxGrp(label=tr('Invert'),value1=False)
    threshold=cmds.floatSliderGrp(label=tr('Threshold'),field=True,minValue=.01,maxValue=.99,value=.5)
    resolution=cmds.intFieldGrp(label=tr('Boundary resolution'),value1=256)
    simplify=cmds.floatFieldGrp(label=tr('Simplify (pixels)'),value1=.25)
    status=cmds.text(label=tr(''),align='left',wordWrap=True)
    def apply(*_):
        shapes=apply_selected(cmds.textFieldButtonGrp(file,q=True,text=True).strip(),
            cmds.optionMenuGrp(channel,q=True,value=True).lower(),cmds.checkBoxGrp(invert,q=True,value1=True),
            cmds.floatSliderGrp(threshold,q=True,value=True),cmds.intFieldGrp(resolution,q=True,value1=True),
            cmds.floatFieldGrp(simplify,q=True,value1=True))
        cmds.text(status,e=True,label=tr('Applied to %d mesh(es). Enable Open Edges in the Line Set.'%len(shapes)))
    cmds.button(label=tr('Apply / Update Selected'),command=lambda *_:_safe(apply))
    cmds.button(label=tr('Remove from Selected'),command=lambda *_:_safe(remove_selected))
    selected=selected_meshes()
    current=configuration(selected[0]) if selected else None
    if current:
        cmds.floatSliderGrp(threshold,e=True,value=current['threshold'])
        cmds.intFieldGrp(resolution,e=True,value1=current['resolution'])
        cmds.floatFieldGrp(simplify,e=True,value1=current['simplify'])
        source=current['sources'].get('all')
        if source:
            cmds.textFieldButtonGrp(file,e=True,text=source['path'])
            cmds.optionMenuGrp(channel,e=True,value=source['channel'].capitalize())
            cmds.checkBoxGrp(invert,e=True,value1=source.get('invert',False))
    cmds.showWindow(window)
    return window
