"""Exact render subdivision for Maya's legacy creased meshes.

generateSmoothMesh and polySmooth differ for fractional/decaying legacy
creases. Evaluate a detached polySmoothFace node with the render-command
settings. The modifier is deliberately never applied to the scene graph.
"""
from maya import cmds
from maya.api import OpenMaya as om


def subdivision_type(source):
    if source.findPlug('useGlobalSmoothDrawType', False).asBool():
        value = cmds.optionVar(query='globalPolyDefaultSmoothDrawType')
        return (0, 2, 3)[int(value)]
    return source.findPlug('smoothDrawType', False).asInt()


def required(source, purpose):
    if purpose != 'render' or subdivision_type(source) != 0:
        return False
    for getter in (source.getCreaseEdges, source.getCreaseVertices):
        try:
            if any(value > 0 for value in getter()[1]):
                return True
        except RuntimeError:
            # Maya reports kFailure when the crease array does not exist.
            pass
    return False


def generate(source, input_owner, divisions):
    """Return an owned mesh-data result without creating any scene DG nodes."""
    modifier = om.MDGModifier()
    node = om.MFnDependencyNode(modifier.createNode('polySmoothFace'))
    node.findPlug('inputPolymesh', False).setMObject(input_owner)
    component_fn = om.MFnSingleIndexedComponent()
    component = component_fn.create(om.MFn.kMeshPolygonComponent)
    component_fn.setCompleteData(source.numPolygons)
    list_fn = om.MFnComponentListData()
    components = list_fn.create()
    list_fn.add(component)
    node.findPlug('inputComponents', False).setMObject(components)
    for name in ('useInputComp', 'maya65Above', 'maya2008Above',
                 'useOsdBoundaryMethods', 'osdIndependentUVChannels'):
        node.findPlug(name, False).setBool(True)
    node.findPlug('method', False).setInt(0)
    node.findPlug('divisions', False).setInt(divisions)
    node.findPlug('subdivisionType', False).setInt(subdivision_type(source))
    node.findPlug('continuity', False).setDouble(source.findPlug('continuity', False).asDouble())
    for name in ('boundaryRule', 'keepMapBorders', 'osdVertBoundary',
                 'osdFvarBoundary', 'osdCreaseMethod'):
        node.findPlug(name, False).setInt(source.findPlug(name, False).asInt())
    for name in ('propagateEdgeHardness', 'keepBorder', 'keepHardEdge',
                 'osdFvarPropagateCorners', 'osdSmoothTriangles'):
        node.findPlug(name, False).setBool(source.findPlug(name, False).asBool())
    # Only UV interpolation changes; face/corner IDs remain exact for material
    # and explicit-edge mapping. Source UVs belong to a separate copied mesh.
    node.findPlug('smoothUVs', False).setBool(False)
    output = node.findPlug('output', False).asMObject()
    owner = om.MFnMeshData().create()
    result = om.MFnMesh(om.MFnMesh().copy(output, owner))
    return result, owner
