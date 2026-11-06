"""Per-panel object visibility, independent of DG visibility and final renders."""
import numpy as np
_cache={}

def member_mask(names,members):
    prefixes={s.split('.',1)[0].rstrip('|') for s in members}
    return np.asarray([any(name==p or name.startswith(p+'|') for p in prefixes) for name in names],bool)

def panel_for_destination(destination):
    from maya import cmds
    panels=cmds.getPanel(type='modelPanel') or []
    if destination in panels:return destination
    for p in panels:
        if cmds.modelPanel(p,q=True,modelEditor=True)==destination:return p
    focused=cmds.getPanel(withFocus=True)
    return focused if focused in panels else None

def snapshots(destination=''):
    from maya import cmds
    result={}
    for panel in cmds.getPanel(type='modelPanel') or []:
        try:
            enabled=bool(cmds.isolateSelect(panel,q=True,state=True))
            set_name=cmds.isolateSelect(panel,q=True,viewObjects=True) if enabled else ''
            members=cmds.sets(set_name,q=True) or [] if set_name else []
            resolved=[]
            for member in members:
                resolved.extend(cmds.ls(member,long=True) or [])
            polygons=bool(cmds.modelEditor(panel,q=True,polymeshes=True))
            result[panel]=(enabled,polygons,tuple(sorted(resolved)))
        except RuntimeError:continue
    selected=panel_for_destination(destination)
    if destination and destination not in result and selected in result:result[destination]=result[selected]
    return result

def sync(lib,names,destination=''):
    import ctypes as c
    signature=tuple(names)
    states=snapshots(destination)
    states['__all__']=(False,True,())
    counts={}
    for panel,state in states.items():
        key=(signature,state)
        if _cache.get(panel)==key:continue
        isolated,polygons,members=state
        visible=member_mask(names,members) if isolated else np.ones(len(names),bool)
        if not polygons:visible[:]=False
        values=np.ascontiguousarray(np.r_[1,visible],np.float32)
        lib.rt_scope(panel.encode('utf-8'),c.c_void_p(values.ctypes.data),len(values))
        _cache[panel]=key
    for panel,(isolated,polygons,members) in states.items():
        counts[panel]=dict(isolated=isolated,visible_meshes=(int(member_mask(names,members).sum()) if isolated else len(names)) if polygons else 0)
    return counts

def reset():_cache.clear()

def is_display_set(name):
    from maya import cmds
    for panel in cmds.getPanel(type='modelPanel') or []:
        try:
            if cmds.isolateSelect(panel,q=True,viewObjects=True)==name:return True
        except RuntimeError:pass
    return False

def export_filter(destination=''):
    """Legacy backend: exclude hidden objects from both strokes and blockers."""
    from maya import cmds
    states=snapshots(destination);panel=destination if destination in states else panel_for_destination(destination)
    if panel not in states:return None
    isolated,polygons,members=states[panel]
    if not polygons:return ()
    if not isolated:return None
    names=cmds.ls(type='mesh',long=True,allPaths=True) or []
    mask=member_mask(names,members)
    return tuple(n for n,visible in zip(names,mask) if visible)
