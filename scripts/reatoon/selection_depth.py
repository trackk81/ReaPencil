"""Read-only camera-axis depth measurement for selected evaluated mesh objects.

Distances are Maya API internal centimetres, matching CPU reduction parameters.
Work runs only when requested by the editor, never during viewport refresh.
"""
import math

def measure_selected(camera=None):
    import numpy as np
    from maya import cmds
    from maya.api import OpenMaya as om, OpenMayaUI as ui
    selected=cmds.ls(selection=True,long=True,objectsOnly=True) or []
    if not selected:raise ValueError('Select mesh objects to measure.')
    source='explicit'
    if camera is None:
        if not cmds.about(batch=True):
            try:camera=ui.M3dView.active3dView().getCamera().fullPathName();source='viewport'
            except RuntimeError:pass
        if camera is None:
            cameras=cmds.ls(type='camera',long=True) or []
            camera=next((c for c in cameras if cmds.getAttr(c+'.renderable')),None);source='renderable'
        if camera is None:raise ValueError('No camera is available for depth measurement.')
    selection=om.MSelectionList();selection.add(camera);cam=selection.getDagPath(0)
    if cam.node().hasFn(om.MFn.kTransform):cam.extendToShape()
    if not cam.node().hasFn(om.MFn.kCamera):raise ValueError('Select a valid camera for depth measurement.')
    matrix=cam.inclusiveMatrix();eye=om.MPoint(0,0,0)*matrix;forward=om.MVector(0,0,-1)*matrix
    if forward.length()<1e-12:raise ValueError('Camera transform has no valid viewing direction.')
    forward.normalize();origin=np.array([eye.x,eye.y,eye.z]);direction=np.array([forward.x,forward.y,forward.z])
    near=float(om.MFnCamera(cam).nearClippingPlane);paths={}
    def visit(path):
        node=path.node()
        if node.hasFn(om.MFn.kMesh):
            if not om.MFnDagNode(path).isIntermediateObject:paths[path.fullPathName()]=om.MDagPath(path)
        elif node.hasFn(om.MFn.kTransform):
            fn=om.MFnDagNode(path)
            for index in range(fn.childCount()):
                child=om.MDagPath(path);child.push(fn.child(index));visit(child)
    for name in selected:
        entry=om.MSelectionList()
        try:entry.add(name);visit(entry.getDagPath(0))
        except RuntimeError:continue
    minimum=math.inf;maximum=-math.inf;count=0
    for path in paths.values():
        points=om.MFnMesh(path).getPoints(om.MSpace.kWorld)
        if not points:continue
        values=np.array([(p.x,p.y,p.z) for p in points],dtype=np.float64)
        depth=(values-origin)@direction
        if not np.isfinite(depth).all():raise ValueError('Selected mesh contains invalid coordinates.')
        minimum=min(minimum,float(depth.min()));maximum=max(maximum,float(depth.max()));count+=len(points)
    if not count:raise ValueError('Select mesh objects to measure.')
    if maximum<=near:raise ValueError('Selected mesh objects are behind the camera or its near clip plane.')
    if maximum>1000000.:raise ValueError('Measured depth exceeds the supported 1000000 cm range.')
    start=max(1.,near,minimum);end=maximum;padded=False
    if end<=start+1e-6:
        padded=True;end=min(1000000.,start+max(.001,abs(start)*1e-6))
        if end<=start:start=end-.001
    from .depth_reduction import validate
    validate([start,end,1.,0.])
    return dict(start=start,end=end,camera=cam.fullPathName(),camera_source=source,unit='cm',
                raw_minimum=minimum,raw_maximum=maximum,meshes=len(paths),vertices=count,
                clamped_near=minimum<max(1.,near),padded=padded)
