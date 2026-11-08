"""Recognize renderable polygon surfaces without treating empty shapes as errors."""
from maya import cmds
from maya.api import OpenMaya as om


def mesh_function(path):
    """Return the evaluated mesh function set, or None for a zero-face shape.

    Imported empty mesh data supports MFnMesh but shader queries fail. A newly
    created empty shape has no mesh data at all, so even MFnMesh rejects it.
    Only that constructor case uses the command fallback; real lookup failures
    and failures on nonempty geometry remain visible to the caller.
    """
    try:
        fn = om.MFnMesh(path)
    except ValueError:
        if path.node().hasFn(om.MFn.kMesh) and cmds.polyEvaluate(path.fullPathName(), face=True) == 0:
            return None
        raise
    return fn if fn.numPolygons else None


def surface_input_changed(message, plug, *_):
    """Invalidate an excluded placeholder when its first mesh data is supplied."""
    flags = om.MNodeMessage.kConnectionMade | om.MNodeMessage.kConnectionBroken | om.MNodeMessage.kAttributeSet
    if message & flags and plug.partialName(useLongNames=True) in ('inMesh', 'cachedInMesh', 'outMesh'):
        from . import viewport
        viewport._scene_changed()
        viewport.request_refresh(graph_changed=True)
