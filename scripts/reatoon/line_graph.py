"""Serializable line passes and live object/material targeting for Maya.

Each Line is an independent pass. Higher renderPriority draws later; within
a Line, the first matching LineSet wins. Targets are live DG connections and
ordinary Maya set memberships, never a snapshot of shader assignments.
"""
import json

from maya import cmds
from maya.api import OpenMaya as om


class LineNode(om.MPxNode):
    TYPE = "revToonLine"
    ID = om.MTypeId(0x0007F7F8)

    @staticmethod
    def creator():
        return LineNode()

    @staticmethod
    def initialize():
        _attributes(LineNode, True)


class LineSetNode(om.MPxNode):
    TYPE = "revToonLineSet"
    ID = om.MTypeId(0x0007F7F9)

    @staticmethod
    def creator():
        return LineSetNode()

    @staticmethod
    def initialize():
        _attributes(LineSetNode, False)


class RenderSettingsNode(om.MPxNode):
    TYPE = "revToonRenderSettings"
    ID = om.MTypeId(0x0007F7FA)

    @staticmethod
    def creator():
        return RenderSettingsNode()

    @staticmethod
    def initialize():
        for name, short, value in (("reaToonSettingsJson", "rsj", "{}"), ("reaToonKind", "rtk", "settings")):
            attr = om.MFnTypedAttribute().create(name, short, om.MFnData.kString, om.MFnStringData().create(value))
            RenderSettingsNode.addAttribute(attr)
        numeric = om.MFnNumericAttribute()
        RenderSettingsNode.addAttribute(numeric.create("enabledSmoothMesh", "esm", om.MFnNumericData.kBoolean, False))


class RenderElementNode(om.MPxNode):
    TYPE = "revToonRenderElement"
    ID = om.MTypeId(0x0007F7FB)

    @staticmethod
    def creator():
        return RenderElementNode()

    @staticmethod
    def initialize():
        attr = om.MFnTypedAttribute().create("elementJson", "elj", om.MFnData.kString, om.MFnStringData().create("{}"))
        RenderElementNode.addAttribute(attr)


def _attributes(cls, line):
    numeric = om.MFnNumericAttribute()
    attr = numeric.create("active", "act", om.MFnNumericData.kBoolean, True)
    numeric.keyable = True
    cls.addAttribute(attr)
    typed = om.MFnTypedAttribute()
    attr = typed.create("overrides", "ovr", om.MFnData.kString, om.MFnStringData().create("{}"))
    cls.addAttribute(attr)
    if line:
        attr = numeric.create("renderPriority", "rp", om.MFnNumericData.kInt, 0)
        numeric.keyable = True
        cls.addAttribute(attr)
        attr = numeric.create("outputToRE", "ore", om.MFnNumericData.kBoolean, False)
        numeric.keyable = True
        cls.addAttribute(attr)
    for name, short, multi in (([("lineSets", "ls", True)]) if line else
                               [("objectTargets", "ot", False), ("shaderTargets", "st", True)]):
        message = om.MFnMessageAttribute()
        attr = message.create(name, short)
        message.array = multi
        cls.addAttribute(attr)


def register(plugin):
    registered = []
    try:
        for cls in (LineNode, LineSetNode, RenderSettingsNode, RenderElementNode):
            plugin.registerNode(cls.TYPE, cls.ID, cls.creator, cls.initialize)
            registered.append(cls)
    except Exception:
        for cls in reversed(registered):
            plugin.deregisterNode(cls.ID)
        raise


def unregister(plugin):
    for cls in (RenderElementNode, RenderSettingsNode, LineSetNode, LineNode):
        plugin.deregisterNode(cls.ID)


def _incoming(plug):
    return cmds.listConnections(plug, source=True, destination=False) or []


def list_lines():
    return sorted(cmds.ls(type=LineNode.TYPE) or [], key=lambda n: (cmds.getAttr(n + ".renderPriority"), n))


def create_line(name="revToonLine"):
    priority = min(99, max((cmds.getAttr(node + ".renderPriority") for node in list_lines()), default=-1) + 1)
    node = cmds.createNode(LineNode.TYPE, name=name, skipSelect=True)
    set_priority(node, priority)
    return node


def list_sets(line):
    result = []
    for index in sorted(cmds.getAttr(line + ".lineSets", multiIndices=True) or []):
        result.extend(n for n in _incoming("%s.lineSets[%d]" % (line, index))
                      if cmds.nodeType(n) == LineSetNode.TYPE)
    return result


def create_line_set(line, name="revToonLineSet", overrides=None, position=0):
    if cmds.nodeType(line) != LineNode.TYPE:
        raise ValueError("A revToonLine must own each Line Set")
    node = cmds.createNode(LineSetNode.TYPE, name=name, skipSelect=True)
    target_set = cmds.sets(empty=True, name=node + "Objects")
    cmds.addAttr(target_set, longName="revToonGraphOwned", attributeType="bool", defaultValue=True)
    cmds.connectAttr(target_set + ".message", node + ".objectTargets")
    ordered = list_sets(line)
    indices = cmds.getAttr(line + ".lineSets", multiIndices=True) or []
    cmds.connectAttr(node + ".message", "%s.lineSets[%d]" % (line, max(indices, default=-1) + 1))
    set_settings(node, overrides or {})
    if position is not None:
        ordered.insert(max(0, min(len(ordered), int(position))), node)
        reorder_sets(line, ordered)
    return node


def get_settings(node):
    return json.loads(cmds.getAttr(node + ".overrides") or "{}")


def set_settings(node, settings):
    from .maya_scene import validate_settings
    values = validate_settings(settings, partial=True)
    cmds.setAttr(node + ".overrides", json.dumps(values, sort_keys=True), type="string")


def set_active(node, value):
    cmds.setAttr(node + ".active", bool(value))


def set_priority(line, value):
    cmds.setAttr(line + ".renderPriority", int(value))


def reorder_sets(line, ordered_nodes):
    old = list_sets(line)
    if len(ordered_nodes) != len(set(ordered_nodes)) or set(old) != set(ordered_nodes):
        raise ValueError("Reordering must contain every owned Line Set exactly once")
    for index in cmds.getAttr(line + ".lineSets", multiIndices=True) or []:
        cmds.removeMultiInstance("%s.lineSets[%d]" % (line, index), b=True)
    for index, node in enumerate(ordered_nodes):
        cmds.connectAttr(node + ".message", "%s.lineSets[%d]" % (line, index))


def _objects(node):
    objects = _incoming(node + ".objectTargets")
    if not objects:
        target = cmds.sets(empty=True, name=node + "Objects")
        cmds.addAttr(target, longName="revToonGraphOwned", attributeType="bool", defaultValue=True)
        cmds.connectAttr(target + ".message", node + ".objectTargets")
        return target
    return objects[0]


def get_targets(node):
    objects = _incoming(node + ".objectTargets")
    return dict(objects=(cmds.sets(objects[0], query=True) or []) if objects else [],
                shaders=list(dict.fromkeys(_incoming(node + ".shaderTargets"))))


def add_targets(node, targets, kind="objects"):
    if kind not in ("objects", "shaders"):
        raise ValueError("Target kind must be objects or shaders")
    targets = list(dict.fromkeys(targets))
    if kind == "objects":
        for target in targets:
            base = target.split(".", 1)[0]
            if cmds.nodeType(base) not in ("transform", "mesh") or ("." in target and not any(x in target for x in (".f[", ".e["))):
                raise ValueError("Object targets require polygon objects, faces or edges")
            if cmds.nodeType(base) == "transform" and not cmds.listRelatives(base, shapes=True, noIntermediate=True, type="mesh"):
                raise ValueError("Object target has no polygon shape: " + base)
        if targets:
            cmds.sets(targets, addElement=_objects(node))
    else:
        existing = get_targets(node)["shaders"]
        for target in targets:
            if cmds.nodeType(target) == "shadingEngine":
                raise ValueError("Choose a surface shader, not its shading group")
            from . import pencil_unknown
            if not cmds.attributeQuery("outColor", node=target, exists=True) and pencil_unknown.kind(target)!='PencilMaterial':
                raise ValueError("Shader targets require an outColor attribute")
            if target not in existing:
                indices = cmds.getAttr(node + ".shaderTargets", multiIndices=True) or []
                cmds.connectAttr(target + ".message", "%s.shaderTargets[%d]" % (node, max(indices, default=-1) + 1))
                existing.append(target)


def remove_targets(node, targets, kind="objects"):
    if kind == "objects":
        if targets:
            cmds.sets(targets, remove=_objects(node))
    elif kind == "shaders":
        for index in cmds.getAttr(node + ".shaderTargets", multiIndices=True) or []:
            plug = "%s.shaderTargets[%d]" % (node, index)
            if set(_incoming(plug)) & set(targets):
                cmds.removeMultiInstance(plug, b=True)
    else:
        raise ValueError("Target kind must be objects or shaders")


def delete_line_set(node):
    if not cmds.objExists(node):return
    targets = _incoming(node + ".objectTargets")
    # Maya's delete traversal can include message-connected sets. Detach all
    # target references before deleting the owner, including foreign sets.
    for attr in ("objectTargets", "shaderTargets"):
        connections = cmds.listConnections(node + "." + attr, source=True, destination=False,
                                           plugs=True, connections=True) or []
        for destination, source in zip(connections[::2], connections[1::2]):
            cmds.disconnectAttr(source, destination)
    # Maya can delete dependent Line nodes when their connected LineSet is
    # deleted. Remove its outgoing message links before traversing deletion.
    connections=cmds.listConnections(node+'.message',source=False,destination=True,plugs=True) or []
    for destination in connections:
        cmds.disconnectAttr(node+'.message',destination)
    cmds.delete(node)
    for target in targets:
        if (cmds.objExists(target) and cmds.nodeType(target) == "objectSet"
                and cmds.attributeQuery("revToonGraphOwned", node=target, exists=True)
                and cmds.getAttr(target + ".revToonGraphOwned")
                and not cmds.listConnections(target + ".message", source=False, destination=True)):
            cmds.delete(target)


def delete_line(line):
    if not cmds.objExists(line):return
    for node in list_sets(line):
        delete_line_set(node)
    if cmds.objExists(line):cmds.delete(line)


def snapshot():
    """Resolve DG links once per scene export; material face assignments stay live."""
    result = []
    for line in list_lines():
        if not cmds.getAttr(line + ".active"):
            continue
        sets = []
        for index, node in enumerate(list_sets(line)):
            if not cmds.getAttr(node + ".active"):
                continue
            values = dict(get_settings(line), **get_settings(node))
            values["output_to_elements_only"] = bool(cmds.getAttr(line + ".outputToRE"))
            values["_order"] = index
            targets = get_targets(node)
            targets["objects"] = cmds.ls(targets["objects"], long=True, flatten=True) or [] if targets["objects"] else []
            sets.append(dict(node=node, settings=values, **targets))
        result.append(dict(line=line, priority=int(cmds.getAttr(line + ".renderPriority")), sets=sets))
    return result


def resolve_mesh(path, face_count, material_shaders, material_ids, graph):
    """Return independent passes and selected edge IDs for this DAG instance."""
    shape = path.fullPathName()
    transform = shape.rsplit("|", 1)[0]
    selected = set()
    passes = []
    for line in graph:
        styles = [None] * face_count
        edge_targets = {}
        for target in line["sets"]:
            faces = set()
            target_edges = []
            for member in target["objects"]:
                base = member.split(".", 1)[0]
                if base not in (shape, transform):
                    continue
                if ".f[" in member:
                    faces.add(int(member.rsplit("[", 1)[1][:-1]))
                elif ".e[" in member:
                    edge = int(member.rsplit("[", 1)[1][:-1])
                    iterator = om.MItMeshEdge(path)
                    iterator.setIndex(edge)
                    selected.add(edge)
                    target_edges.append([iterator.vertexId(0), iterator.vertexId(1)])
                else:
                    faces.update(range(face_count))
            shader_ids = {i for i, shader in enumerate(material_shaders) if shader in target["shaders"]}
            faces.update(i for i, material in enumerate(material_ids) if int(material) in shader_ids)
            for face in faces:
                if 0 <= face < face_count and styles[face] is None:
                    styles[face] = target["node"]
            edge_targets[target["node"]] = target_edges
        passes.append(dict(line=line["line"], priority=line["priority"], face_line_sets=styles, selected_edges=edge_targets))
    return passes, selected


def refresh_scene(scene):
    """Refresh graph styles, SG assignments and targets without copying geometry.

    Must run on Maya's main thread. Changes only line_sets, line_passes and
    selected_edges; callers invalidate prepared selected-edge masks afterwards.
    """
    from .maya_scene import _dag, _tagged, _json_attr, _line_membership
    from . import smooth_geometry
    enabled = bool(list_lines())
    graph = snapshot() if enabled else []
    legacy = [(node, cmds.sets(node, query=True) or [], _json_attr(node, "reaToonOverrides"))
              for node in sorted(_tagged("lineSet", "objectSet"))]
    scene["line_sets"] = ({target["node"]: target["settings"] for line in graph for target in line["sets"]}
                          if enabled else {node: values for node, _, values in legacy})
    for mesh in scene["meshes"]:
        path = _dag(mesh["name"])
        if enabled:
            shading_engines, ids = om.MFnMesh(path).getConnectedShaders(path.instanceNumber())
            shaders = []
            for sg in shading_engines:
                incoming = _incoming(om.MFnDependencyNode(sg).name() + ".surfaceShader")
                shaders.append(incoming[0] if incoming else "")
            passes, selected = resolve_mesh(path, mesh.get("base_face_count", len(mesh["faces"])), shaders, ids, graph)
            mesh["line_passes"] = smooth_geometry.remap_passes(mesh, passes)
            mesh.pop("line_set", None)
        else:
            chosen, selected = _line_membership(path, legacy)
            mesh.pop("line_passes", None)
            mesh.pop("line_set", None)
            if chosen:
                mesh["line_set"] = chosen
        iterator = om.MItMeshEdge(path)
        edges = []
        for index in selected:
            iterator.setIndex(index)
            edges.append([iterator.vertexId(0), iterator.vertexId(1)])
        mesh["selected_edges"] = smooth_geometry.remap_edges(mesh, edges)
    from . import render_elements
    scene["merge_groups"] = export_merge_groups(scene["meshes"])
    scene["render_elements"] = render_elements.snapshot()
    return scene


def migrate_legacy():
    """Explicit, additive and UUID-idempotent upgrade of legacy tagged sets.

    Original objectSets and overrides remain intact. No migration is performed
    simply by opening an editor or exporting a scene.
    """
    from .maya_scene import _tagged, _json_attr, undo_chunk
    marker = "revToonLegacySourceUUID"
    existing = {cmds.getAttr(node + "." + marker) for node in cmds.ls(type=LineSetNode.TYPE) or []
                if cmds.attributeQuery(marker, node=node, exists=True)}
    candidates = []
    for node in sorted(_tagged("lineSet", "objectSet"), reverse=True):
        uuid = (cmds.ls(node, uuid=True) or [node])[0]
        if uuid not in existing:
            candidates.append((node, uuid))
    result = dict(line=None, created=[], skipped=len(existing), sources_preserved=True)
    if not candidates:
        return result
    with undo_chunk("Upgrade legacy RevToon Line Sets"):
        line = create_line("revToonUpgradedLine")
        result["line"] = line
        for source, uuid in candidates:
            node = create_line_set(line, source + "Graph", _json_attr(source, "reaToonOverrides"), position=None)
            members = cmds.sets(source, query=True) or []
            if members:
                add_targets(node, members)
            cmds.addAttr(node, longName=marker, dataType="string")
            cmds.setAttr(node + "." + marker, uuid, type="string")
            result["created"].append(node)
    return result


def list_merge_groups(line=None):
    return sorted(node for node in cmds.ls("*.revToonMergeGroup", objectsOnly=True, long=True, recursive=True) or []
                  if cmds.attributeQuery("revToonMergeGroup", node=node, exists=True)
                  and cmds.getAttr(node + ".revToonMergeGroup"))


def register_merge_group(target):
    if cmds.nodeType(target) not in ("transform", "objectSet"):
        raise ValueError("Register an existing transform/group or objectSet")
    if not cmds.attributeQuery("revToonMergeGroup", node=target, exists=True):
        cmds.addAttr(target, longName="revToonMergeGroup", attributeType="bool", defaultValue=True)
    cmds.setAttr(target + ".revToonMergeGroup", True)
    return (cmds.ls(target, long=True) or [target])[0]


def create_merge_group(line=None, name="revToonMergeGroup", targets=None):
    node = cmds.sets(empty=True, name=name)
    register_merge_group(node)
    if targets:
        add_merge_targets(node, targets)
    return node


def get_merge_targets(group):
    if cmds.nodeType(group) == "transform":
        return cmds.listRelatives(group, children=True, fullPath=True) or []
    return cmds.sets(group, query=True) or []


def add_merge_targets(group, targets):
    if cmds.nodeType(group) != "objectSet":
        raise ValueError("DAG group membership follows its hierarchy; edit it in Maya's Outliner")
    for target in targets:
        if "." in target or cmds.nodeType(target) not in ("transform", "mesh", "objectSet"):
            raise ValueError("Merge groups accept mesh objects, hierarchies or object sets")
        if target == group:
            raise ValueError("A merge group cannot contain itself")
    if targets:
        cmds.sets(targets, addElement=group)


def remove_merge_targets(group, targets):
    if cmds.nodeType(group) != "objectSet":
        raise ValueError("DAG group membership follows its hierarchy; edit it in Maya's Outliner")
    if targets:
        cmds.sets(targets, remove=group)


def remove_merge_group(line=None, group=None):
    group = group if group is not None else line
    if not cmds.attributeQuery("revToonMergeGroup", node=group, exists=True):
        raise ValueError("Not an owned RevToon merge group")
    cmds.deleteAttr(group + ".revToonMergeGroup")


unregister_merge_group = remove_merge_group


def export_merge_groups(meshes):
    """Resolve nested DAG/objectSet membership; largest enclosing group wins."""
    def shapes(node, visited):
        if node in visited:
            return set()
        visited.add(node)
        kind = cmds.nodeType(node)
        if kind == "objectSet":
            result = set()
            for member in cmds.sets(node, query=True) or []:
                result.update(shapes(member.split(".", 1)[0], visited))
            return result
        if kind == "mesh":
            return set(cmds.ls(node, long=True, allPaths=True) or [])
        if kind == "transform":
            return set(cmds.listRelatives(node, allDescendents=True, fullPath=True, type="mesh") or [])
        return set()
    groups = []
    for node in list_merge_groups():
        names = shapes(node, set())
        indices = [i for i, mesh in enumerate(meshes) if mesh["name"] in names]
        if indices:
            groups.append(dict(node=node, mesh_indices=indices))
    groups.sort(key=lambda item: (-len(item["mesh_indices"]), item["node"]))
    claimed = set()
    for group in groups:
        group["mesh_indices"] = [i for i in group["mesh_indices"] if i not in claimed]
        claimed.update(group["mesh_indices"])
    return [dict(group, id=index) for index, group in enumerate(groups) if group["mesh_indices"]]
