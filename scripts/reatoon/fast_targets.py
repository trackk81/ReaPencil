"""Cache target membership without extracting animated positions."""
import ctypes
import numpy as np
from maya import cmds
from maya.api import OpenMaya as om
from .mesh_surface import mesh_function,surface_input_changed
_key=None
rebuilds=0
_watching=False
_feature_watch=None
_last_plan={}

def sync():
    global _key,rebuilds,_watching,_feature_watch,_last_plan
    from . import viewport,line_graph,fast_viewport
    if viewport._watchers_stale or not _watching or _feature_watch!=any(fast_viewport._edge_flags):
        viewport._remove_callbacks(viewport._node_callbacks)
        for name in cmds.ls(type=('revToonLine','revToonLineSet','revToonRenderElement','objectSet','shadingEngine')) or []:
            sel=om.MSelectionList();sel.add(name);obj=sel.getDependNode(0)
            viewport._node_callbacks.append(om.MNodeMessage.addAttributeChangedCallback(obj,viewport._attribute_changed))
            if obj.hasFn(om.MFn.kSet):viewport._node_callbacks.append(om.MObjectSetMessage.addSetMembersModifiedCallback(obj,viewport._targets_changed))
        _feature_watch=any(fast_viewport._edge_flags)
        if _feature_watch:
            for name in cmds.ls(type=('mesh','polyCrease','polySoftEdge')) or []:
                sel=om.MSelectionList();sel.add(name)
                viewport._node_callbacks.append(om.MNodeMessage.addAttributeChangedCallback(sel.getDependNode(0),edge_changed))
                if sel.getDependNode(0).hasFn(om.MFn.kMesh):
                    viewport._node_callbacks.append(om.MPolyMessage.addPolyTopologyChangedCallback(sel.getDependNode(0),viewport._scene_changed))
        # Initial mesh input does not always emit a topology event. Watch empty
        # placeholders even when authored-edge overlays are disabled.
        for name in cmds.ls(type='mesh') or []:
            path=om.MSelectionList().add(name).getDagPath(0)
            if mesh_function(path) is None:
                viewport._node_callbacks.append(om.MNodeMessage.addAttributeChangedCallback(path.node(),surface_input_changed))
                if not _feature_watch:
                    viewport._node_callbacks.append(om.MPolyMessage.addPolyTopologyChangedCallback(path.node(),viewport._scene_changed))
        viewport._watchers_stale=False;_watching=True
    key=viewport._fast_target_revision
    if key==_key:return
    graph=line_graph.snapshot();members=[];all_full=True;assigned_shaders=set();empty_meshes=[]
    rebuilds+=1
    for name in cmds.ls(type='mesh',long=True,allPaths=True) or []:
        if cmds.getAttr(name+'.intermediateObject'):continue
        selection=om.MSelectionList();selection.add(name);path=selection.getDagPath(0);fn=mesh_function(path)
        # Maya may have a valid DAG shape with no mesh data. Shader queries on
        # these placeholders raise kFailure, including their instance paths.
        if fn is None:
            empty_meshes.append(name);continue
        engines,ids=fn.getConnectedShaders(path.instanceNumber());shaders=[]
        for engine in engines:
            source=cmds.listConnections(om.MFnDependencyNode(engine).name()+'.surfaceShader',source=True,destination=False) or []
            shaders.append(source[0] if source else '')
        assigned_shaders.update(shaders)
        passes,_=line_graph.resolve_mesh(path,fn.numPolygons,shaders,ids,graph)
        keep=np.zeros(fn.numPolygons,bool)
        for item in passes:keep|=np.asarray([v is not None for v in item['face_line_sets']])
        if keep.all() and len(keep):members.append(name)
        elif keep.any():
            all_full=False
            indices=np.flatnonzero(keep);starts=np.r_[0,np.flatnonzero(np.diff(indices)>1)+1];ends=np.r_[starts[1:]-1,len(indices)-1]
            members.extend(name+'.f[%d:%d]'%(indices[a],indices[b]) for a,b in zip(starts,ends))
        else:all_full=False
    blockers=[]
    for shape in cmds.ls(shapes=True,long=True) or []:
        sel=om.MSelectionList();sel.add(shape);obj=sel.getDagPath(0).node()
        if not any(obj.hasFn(k) for k in (om.MFn.kMesh,om.MFn.kNurbsCurve,om.MFn.kCamera,om.MFn.kLocator,om.MFn.kLight)):all_full=False;blockers.append(shape)
    unused=sorted({s for line in graph for item in line['sets'] for s in item['shaders']}-assigned_shaders)
    _last_plan=dict(unassigned_shader_targets=unused,revision=key,rebuilds=rebuilds,members=list(members),target_all=bool(all_full and members),other_shape_blockers=blockers,empty_meshes=empty_meshes)
    fast_viewport._target_summary=dict(unassigned_shader_targets=unused,target_ranges=len(members))
    lib=fast_viewport._library;lib.rp_fast_all.argtypes=[ctypes.c_int];lib.rp_fast_all(int(all_full and bool(members))); lib.rp_fast_targets.argtypes=[ctypes.c_char_p];lib.rp_fast_targets.restype=None
    lib.rp_fast_targets(('\n'.join(members)).encode('utf-8'));_key=key

def edge_changed(message,plug,*_):
    if not message&om.MNodeMessage.kAttributeSet:return
    node=om.MFnDependencyNode(plug.node());name=plug.partialName(useLongNames=True).lower()
    if node.typeName in ('polyCrease','polySoftEdge') or any(k in name for k in ('crease','edgesmoothing','normal','smooth','keepborder','keephard','boundary','continuity','osd')):
        from . import viewport
        viewport.request_refresh(graph_changed=True)

def edge_scope(panel):
    if not cmds.modelPanel(panel,exists=True):return '*'
    if not cmds.modelEditor(panel,q=True,polymeshes=True):return ''
    if not cmds.isolateSelect(panel,q=True,state=True):return '*'
    group=cmds.isolateSelect(panel,q=True,viewObjects=True)
    members=cmds.sets(group,q=True) or []
    return '\n'.join(n.split('.',1)[0] for n in (cmds.ls(members,long=True) or [])) if members else ''


def diagnostics():
    return dict(_last_plan)


def smooth_edge_pairs(name, pairs):
    """One-time exact topology mapping for Maya legacy crease preview geometry.

    Called by native authored-edge cache only when topology/options change.
    Actual animated positions stay in native code, with camera frames cached.
    """
    from . import smooth_geometry
    path=om.MSelectionList().add(name).getDagPath(0)
    mesh=smooth_geometry.evaluate(path,purpose='viewport',as_arrays=True)
    return [int(v) for pair in pairs
            for child in mesh['base_edge_children'].get('%d,%d'%tuple(sorted(pair)), [])
            for v in child]
