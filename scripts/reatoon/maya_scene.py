"""Maya scene adapter. Original implementation; no Pencil+ runtime dependency."""
import contextlib
import json
import math
import os
import time
import numpy as np

from maya import cmds
from maya.api import OpenMaya as om

DEFAULT_SETTINGS = {
    "enabled_smooth_mesh": False,
    "relative_line_size": False,
    "connect_collinear_dashes": False,
    "line_opacity": 1.0, "blend_mode": 0, "brush_key": "",
    "brush_size_scale": 1.0,
    "width_profile": [], "alpha_profile": [], "alpha_depth_reduction": [], "width_depth_reduction": [], "alpha_reduction_origin": [], "width_reduction_origin": [], "profile_direction": -30.0,
    "profile_split_angle": 90.0, "profile_loop_direction": 0, "pencil_profile_width": True,
    "width": 640, "height": 480, "supersample": 2,
    "background": [1.0, 1.0, 1.0], "line_width": 1.5,
    "line_color": [0.05, 0.05, 0.08], "hidden_lines": False,
    "feature_brushes": {}, "hidden_style": {},
    "hidden_color": [0.5, 0.5, 0.6], "outline": True, "open_edges": True,
    "crease": True, "crease_angle": 40.0, "crease_angle_max": 180.0, "material_boundaries": True,
    "selected_edges": True, "wireframe": False, "hard_edges": True,
    "intersections": True, "self_intersections": False,
    "merge_groups": True, "lineset_id": 1,
    "intersection_tolerance": 1e-7,
    "depth_bias": 0.002, "distance_reduction": 0.0,
    "width_variation": 0.0, "taper": 0.0, "dash_length": 0.0, "dash_gap": -1.0, "seed": 1,
}


@contextlib.contextmanager
def undo_chunk(name="ReaToon"):
    cmds.undoInfo(openChunk=True, chunkName=name)
    try:
        yield
    finally:
        cmds.undoInfo(closeChunk=True)


def _tag(node, kind):
    if not cmds.attributeQuery("reaToonKind", node=node, exists=True):
        cmds.addAttr(node, longName="reaToonKind", dataType="string")
    cmds.setAttr(node + ".reaToonKind", kind, type="string")


def _tagged(kind, node_type=None, include_namespaces=True):
    nodes = cmds.ls(type=node_type) if node_type else cmds.ls(":*.reaToonKind", objectsOnly=True, recursive=include_namespaces)
    return [n for n in (nodes or [])
            if cmds.attributeQuery("reaToonKind", node=n, exists=True)
            and cmds.getAttr(n + ".reaToonKind") == kind]


def _json_attr(node, name, value=None):
    if value is None:
        if not cmds.attributeQuery(name, node=node, exists=True):
            return {}
        return json.loads(cmds.getAttr(node + "." + name) or "{}")
    if not cmds.attributeQuery(name, node=node, exists=True):
        cmds.addAttr(node, longName=name, dataType="string")
    cmds.setAttr(node + "." + name, json.dumps(value, sort_keys=True), type="string")


def validate_settings(values, partial=False):
    """Reject unknown keys and non-finite values before persisting a preset."""
    if not isinstance(values, dict):
        raise ValueError("Settings must be an object.")
    result = {} if partial else dict(DEFAULT_SETTINGS)
    ranges = {"width": (16, 4096), "height": (16, 4096), "supersample": (1, 4),
              "profile_split_angle": (0,180), "profile_loop_direction": (0,1), "profile_direction": (-360,360), "line_width": (0.1, 64), "line_opacity": (0, 1), "blend_mode": (0,15), "brush_size_scale": (0, 1), "crease_angle": (0, 180), "crease_angle_max": (0, 180),
              "intersection_tolerance": (1e-12, 0.01),
              "depth_bias": (0, 1), "distance_reduction": (0, 1000),
              "width_variation": (0, 1), "taper": (0, 1),
              "dash_length": (0, 10000), "dash_gap": (-1, 10000), "seed": (0, 2147483647), "lineset_id": (1, 8)}
    for key, value in values.items():
        if key not in DEFAULT_SETTINGS:
            raise ValueError("Unknown setting: " + str(key))
        default = DEFAULT_SETTINGS[key]
        if key in ("feature_brushes","hidden_style"):
            from .brush_channels import validate_nested
            value=validate_nested(value,validate_settings,hidden=key=="hidden_style")
        elif key in ('alpha_reduction_origin','width_reduction_origin'):
            from .depth_reduction import validate_origin
            value=validate_origin(value)
        elif key in ('alpha_depth_reduction','width_depth_reduction'):
            from .depth_reduction import validate
            value=validate(value)
        elif key in ("width_profile","alpha_profile"):
            from .brush_profiles import validate_profile,profile_table
            value=validate_profile(value);profile_table(value)
        elif key=="brush_key":
            if not isinstance(value,str) or len(value)>256 or any(c in value for c in "\r\n"):raise ValueError("Invalid brush identity")
        elif isinstance(default, bool):
            if not isinstance(value, bool):
                raise ValueError(key + " must be boolean")
        elif isinstance(default, list):
            if not isinstance(value, (list, tuple)) or len(value) != 3:
                raise ValueError(key + " requires three RGB values")
            value = [float(v) for v in value]
            if not all(math.isfinite(v) and 0 <= v <= 1 for v in value):
                raise ValueError(key + " RGB values must be finite and in [0, 1]")
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(key + " must be a finite number")
            low, high = ranges[key]
            if not low <= value <= high:
                raise ValueError("%s must be between %s and %s" % (key, low, high))
            if isinstance(default, int):
                if int(value) != value:
                    raise ValueError(key + " must be an integer")
                value = int(value)
        result[key] = value
    if not partial:
        from .render_limits import check_frame_samples
        check_frame_samples(result['width'],result['height'],result['supersample'])
    return result


def settings_node(create=False):
    nodes = _tagged("settings", include_namespaces=False)
    if not nodes:nodes = _tagged("settings")
    roots = [node for node in nodes if ":" not in node]
    nodes = roots or nodes
    canonical = [node for node in nodes if cmds.nodeType(node) == "revToonRenderSettings"]
    if canonical:
        if not cmds.attributeQuery("enabledSmoothMesh", node=canonical[0], exists=True):
            cmds.addAttr(canonical[0], longName="enabledSmoothMesh", attributeType="bool", defaultValue=False)
        return canonical[0]
    if not create:
        return nodes[0] if nodes else None
    values = _json_attr(nodes[0], "reaToonSettingsJson") if nodes else {}
    node_type = "revToonRenderSettings" if "revToonRenderSettings" in cmds.allNodeTypes() else "network"
    node = cmds.createNode(node_type, name="revToonRenderSettings", skipSelect=True)
    _tag(node, "settings")
    _json_attr(node, "reaToonSettingsJson", values)
    if not cmds.attributeQuery("enabledSmoothMesh", node=node, exists=True):
        cmds.addAttr(node, longName="enabledSmoothMesh", attributeType="bool", defaultValue=False)
    cmds.setAttr(node + ".enabledSmoothMesh", bool(values.get("enabled_smooth_mesh", False)))
    return node


def load_settings():
    node = settings_node()
    values = _json_attr(node, "reaToonSettingsJson") if node else {}
    if node and cmds.attributeQuery("enabledSmoothMesh", node=node, exists=True):
        values["enabled_smooth_mesh"] = bool(cmds.getAttr(node + ".enabledSmoothMesh"))
    return validate_settings(values)


def save_settings(values):
    values = validate_settings(values)
    with undo_chunk("ReaToon settings"):
        node = settings_node(create=True)
        _tag(node, "settings")
        _json_attr(node, "reaToonSettingsJson", values)
        cmds.setAttr(node + ".enabledSmoothMesh", values["enabled_smooth_mesh"])
    return node


def save_preset(path):
    with open(path, "w", encoding="utf-8") as stream:
        json.dump({"format": "reatoon-preset", "version": 1, "settings": load_settings()}, stream, indent=2)
    return path


def load_preset(path):
    if os.path.getsize(path) > 65536:
        raise ValueError("Preset exceeds the 64 KiB limit.")
    with open(path, encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict) or data.get("format") != "reatoon-preset" or data.get("version") != 1:
        raise ValueError("This is not a supported ReaToon preset.")
    settings = validate_settings(data.get("settings"))
    save_settings(settings)
    return settings


def create_toon_material(name="reaToonMaterial", assign=True, color=(0.65, 0.32, 0.16),
                         shadow_color=None, highlight_color=None, threshold=0.5,
                         highlight_threshold=0.85):
    """Create a Maya stepped rampShader with metadata for the CPU renderer."""
    for rgb in (color, shadow_color, highlight_color):
        if rgb is not None and (len(rgb) != 3 or not all(isinstance(c, (int, float)) and math.isfinite(c) and 0 <= c <= 1 for c in rgb)):
            raise ValueError("Material colors require three finite values in [0, 1].")
    if not (isinstance(threshold, (int, float)) and isinstance(highlight_threshold, (int, float))
            and math.isfinite(threshold) and math.isfinite(highlight_threshold)
            and 0 <= threshold <= highlight_threshold <= 1):
        raise ValueError("Material thresholds must satisfy 0 <= shadow <= highlight <= 1.")
    selection = cmds.ls(selection=True, long=True) or []
    with undo_chunk("Create ReaToon material"):
        shader = cmds.shadingNode("rampShader", asShader=True, name=name)
        _tag(shader, "material")
        sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=shader + "SG")
        cmds.connectAttr(shader + ".outColor", sg + ".surfaceShader", force=True)
        colors = {"reaToonBaseColor": color,
                  "reaToonShadowColor": shadow_color if shadow_color is not None else [c * 0.38 for c in color],
                  "reaToonHighlightColor": highlight_color if highlight_color is not None else [min(1.0, c * 0.55 + 0.45) for c in color]}
        for attr, rgb in colors.items():
            cmds.addAttr(shader, longName=attr, attributeType="float3", usedAsColor=True)
            for channel in "RGB":
                cmds.addAttr(shader, longName=attr + channel, attributeType="float", parent=attr, minValue=0, maxValue=1)
            cmds.setAttr(shader + "." + attr, *rgb, type="float3")
        for attr, value in [("reaToonThreshold", threshold), ("reaToonHighlightThreshold", highlight_threshold), ("reaToonGradationOffset", 0.0)]:
            cmds.addAttr(shader, longName=attr, attributeType="double", defaultValue=value,
                         minValue=-1 if "Offset" in attr else 0, maxValue=1, keyable=True)
        for index in (cmds.getAttr(shader + ".color", multiIndices=True) or []):
            cmds.removeMultiInstance("%s.color[%d]" % (shader, index), b=True)
        for i, (pos, source) in enumerate([(0.0, "reaToonShadowColor"), (threshold, "reaToonBaseColor"), (highlight_threshold, "reaToonHighlightColor")]):
            element = "%s.color[%d]" % (shader, i)
            cmds.setAttr(element + ".color_Position", pos)
            cmds.setAttr(element + ".color_Interp", 0)
            cmds.connectAttr(shader + "." + source, element + ".color_Color", force=True)
        cmds.connectAttr(shader + ".reaToonThreshold", shader + ".color[1].color_Position", force=True)
        cmds.connectAttr(shader + ".reaToonHighlightThreshold", shader + ".color[2].color_Position", force=True)
        if assign and selection:
            cmds.sets(selection, edit=True, forceElement=sg)
        if selection:
            cmds.select(selection, replace=True)
    return shader


def create_line_set(name="reaToonLineSet", overrides=None):
    members = cmds.ls(selection=True, long=True, flatten=True) or []
    if not members:
        raise ValueError("Select mesh objects or polygon edges first.")
    for member in members:
        node = member.split(".", 1)[0]
        if cmds.nodeType(node) not in ("mesh", "transform"):
            raise ValueError("Line sets accept polygon objects or edges only.")
        if cmds.nodeType(node) == "transform" and not cmds.listRelatives(node, shapes=True, noIntermediate=True, type="mesh"):
            raise ValueError("Selected transforms must have a polygon mesh shape.")
        if "." in member and ".e[" not in member:
            raise ValueError("Use whole objects or polygon edges, not vertices/faces.")
    values = validate_settings(overrides or {}, partial=True)
    with undo_chunk("Create ReaToon line set"):
        node = cmds.sets(members, name=name)
        _tag(node, "lineSet")
        _json_attr(node, "reaToonOverrides", values)
    return node


def _dag(name):
    sel = om.MSelectionList()
    try:
        sel.add(name)
    except RuntimeError as error:
        raise RuntimeError('RevToon DAG object is unavailable: %r' % name) from error
    return sel.getDagPath(0)


def camera_names():
    return cmds.ls(type="camera", long=True) or []


def _camera(name, aspect):
    if not name:
        cameras = camera_names()
        name = next((c for c in cameras if cmds.getAttr(c + ".renderable")), None)
        name = name or ("perspShape" if cmds.objExists("perspShape") else cameras[0] if cameras else None)
    if not name:
        raise ValueError("The scene has no camera.")
    path = _dag(name)
    if path.node().hasFn(om.MFn.kTransform):
        path.extendToShape()
    fn = om.MFnCamera(path)
    matrix = path.inclusiveMatrix()
    eye = om.MPoint(0, 0, 0) * matrix
    forward = om.MVector(0, 0, -1) * matrix
    up = om.MVector(0, 1, 0) * matrix
    forward.normalize()
    up.normalize()
    left, right, bottom, top = fn.getRenderingFrustum(aspect)
    near = float(fn.nearClippingPlane)
    if abs(left + right) > 1e-6 or abs(top + bottom) > 1e-6:
        raise ValueError("Camera film offsets/asymmetric frusta are not supported; use a centered camera.")
    vertical_fov = math.degrees(2 * math.atan((top - bottom) / (2 * near)))
    return {"position": [eye.x, eye.y, eye.z],
            "target": [eye.x + forward.x, eye.y + forward.y, eye.z + forward.z],
            "up": [up.x, up.y, up.z],
            "projection": "orthographic" if fn.isOrtho() else "perspective",
            "fov_y": 45.0 if fn.isOrtho() else vertical_fov, "ortho_width": float(fn.orthoWidth),
            "near": near, "far": float(fn.farClippingPlane), "film_aspect":float(aspect), "name": path.fullPathName()}


def _color(node, attr, default):
    try:
        value = cmds.getAttr(node + "." + attr)
        if isinstance(value, list) and value and isinstance(value[0], tuple):
            return [float(x) for x in value[0][:3]]
    except (ValueError, RuntimeError):
        pass
    return list(default)


def _scalar(node, attr, default):
    try:
        return float(cmds.getAttr(node + "." + attr))
    except (ValueError, TypeError, RuntimeError):
        return default


def _material(sg, warnings):
    shaders = cmds.listConnections(sg + ".surfaceShader", source=True, destination=False) or []
    node = shaders[0] if shaders else ""
    if node:
        from . import pencil_compat
        imported = pencil_compat.material_override(node, warnings)
        if imported is not None:
            return imported
    custom = node and cmds.attributeQuery("reaToonBaseColor", node=node, exists=True)
    color = _color(node, "reaToonBaseColor" if custom else "color", (0.5, 0.5, 0.5))
    if not custom:
        if node and cmds.attributeQuery("baseColor", node=node, exists=True):
            color = _color(node, "baseColor", color)
        warnings.append("%s: shader reduced to constant color; textures, transparency and custom shading are not reproduced." % (node or sg))
    return {"name": node or sg, "color": color,
            "shadow_color": _color(node, "reaToonShadowColor", [c * .38 for c in color]),
            "highlight_color": _color(node, "reaToonHighlightColor", [min(1, c * .55 + .45) for c in color]),
            "threshold": _scalar(node, "reaToonThreshold", .5),
            "highlight_threshold": _scalar(node, "reaToonHighlightThreshold", .85),
            "gradation_offset": _scalar(node, "reaToonGradationOffset", 0), "opacity": 1.0}


def _line_membership(path, line_sets):
    mesh_name = path.fullPathName()
    transform = mesh_name.rsplit("|", 1)[0]
    chosen = None
    edges = set()
    for node, members, overrides in line_sets:
        matched = False
        for member in members:
            for item in cmds.ls(member, long=True, flatten=True) or []:
                base = item.split(".", 1)[0]
                if base not in (mesh_name, transform):
                    continue
                matched = True
                if ".e[" in item:
                    edges.add(int(item.rsplit("[", 1)[1][:-1]))
        if matched:
            chosen = node  # deterministic last set wins for overlapping sets
    return chosen, edges


def export_scene(camera=None, settings=None, camera_override=None, include_normals=True, geometry_purpose="render", include_materials=True, as_arrays=False, mesh_filter=None, geometry_cache=None, mesh_ready=None, alpha_configuration=None):
    from . import line_graph
    from . import smooth_geometry
    from . import alpha_boundary
    settings = validate_settings(settings or load_settings())
    warnings = []
    graph_enabled = bool(line_graph.list_lines())
    graph = line_graph.snapshot() if graph_enabled else []
    line_sets = [(node, cmds.sets(node, query=True) or [], validate_settings(_json_attr(node, "reaToonOverrides"), partial=True))
                 for node in sorted(_tagged("lineSet", "objectSet"))]
    # Only explicit component targets need the expensive descendant-edge map.
    # GPU outlines/intersections consume the evaluated topology directly.
    need_edge_provenance=(include_normals or
        any('.e[' in member for line in graph for target in line['sets'] for member in target['objects']) or
        any('.e[' in member for _,members,_ in line_sets for member in members))
    result = {"camera": camera_override if camera_override is not None else _camera(camera, float(settings["width"]) / settings["height"]),
              "meshes": [], "light": {"direction": [0.4, 0.8, 0.6], "intensity": 1.0, "ambient": 0.15},
              "warnings": warnings, "frame": float(cmds.currentTime(query=True)),
              "line_sets": {n: v for n, _, v in line_sets}}
    if graph_enabled:
        result["line_sets"] = {target["node"]: target["settings"] for line in graph for target in line["sets"]}
    lights = (cmds.ls(type="directionalLight", long=True) or []) if include_materials else []
    lights = [name for name in lights if _dag(name).isVisible()]
    if lights:
        lamp = _dag(lights[0])
        direction = om.MVector(0, 0, 1) * lamp.inclusiveMatrix()
        direction.normalize()
        result["light"] = {"direction": list(direction), "intensity": cmds.getAttr(lights[0] + ".intensity"), "ambient": 0.15}
        if len(lights) > 1:
            warnings.append("Only the first visible directional light is used; other lights are ignored.")
    elif include_materials:
        warnings.append("No directional light: using the ReaToon preview light.")
    for name in cmds.ls(type="mesh", long=True, allPaths=True) or []:
        if geometry_purpose=='viewport' and mesh_filter is not None and name not in mesh_filter:continue
        path = _dag(name)
        if cmds.getAttr(name + ".intermediateObject") or not path.isVisible():
            continue
        source_fn = om.MFnMesh(path)
        alpha_config=(alpha_configuration or alpha_boundary.configuration)(name)
        shading_engines, ids = source_fn.getConnectedShaders(path.instanceNumber())
        chosen, selected = _line_membership(path, line_sets)
        passes = None
        if graph_enabled:
            shader_names = []
            for sg in shading_engines:
                sources = cmds.listConnections(om.MFnDependencyNode(sg).name() + ".surfaceShader", source=True, destination=False) or []
                shader_names.append(sources[0] if sources else "")
            passes, selected = line_graph.resolve_mesh(path, source_fn.numPolygons, shader_names, ids, graph)
        uniform=(geometry_purpose=='render' and not need_edge_provenance and not alpha_config
                 and (not len(ids) or min(ids)==max(ids))
                 and all(len(set(item['face_line_sets']))<=1 for item in (passes or [])))
        evaluated=None
        cached=(geometry_cache or {}).get(name) if geometry_purpose=='viewport' and as_arrays and not need_edge_provenance and not alpha_config else None
        if cached is not None:evaluated=cached['geometry']
        if evaluated is None and as_arrays and not need_edge_provenance and not include_normals and not alpha_config:
            from . import native_mesh
            try:
                divisions=smooth_geometry.level(path,settings['enabled_smooth_mesh'],geometry_purpose)
                if geometry_purpose=='render':
                    from . import render_geometry_cache
                    evaluated=render_geometry_cache.evaluate(path,divisions,uniform=uniform)
                else:
                    evaluated=native_mesh.evaluate(path,divisions,purpose=geometry_purpose)
            except RuntimeError as error:
                if 'exporter is unavailable' not in str(error):raise
                warnings.append(str(error)+'; using Maya Python geometry evaluation')
        if evaluated is None:
            evaluated = smooth_geometry.evaluate(path, settings["enabled_smooth_mesh"], geometry_purpose,
                                                 need_edge_provenance=need_edge_provenance or bool(alpha_config),as_arrays=as_arrays)
        fn = evaluated.get("fn")
        faces=evaluated.get('faces')
        if faces is None:
            counts, indices = fn.getVertices()
            faces, cursor = [], 0
            for count in counts:
                faces.append(list(indices[cursor:cursor + count]))
                cursor += count
        if 'triangles' in evaluated:
            triangles,triangle_faces=evaluated['triangles'],evaluated['triangle_faces']
        else:
            triangle_counts, triangle_vertices = fn.getTriangles()
            triangles = np.asarray(triangle_vertices,dtype=np.int64).reshape(-1,3)
            triangle_faces = np.repeat(np.arange(len(triangle_counts)),np.asarray(triangle_counts,dtype=np.int64))
        if not as_arrays:
            triangles=triangles.tolist();triangle_faces=triangle_faces.tolist()
        materials = [(_material(om.MFnDependencyNode(sg).name(), warnings) if include_materials else
                      {'name':om.MFnDependencyNode(sg).name()}) for sg in shading_engines]
        if not materials:
            materials = [{"name": "unassigned", "color": [.5, .5, .5], "shadow_color": [.19, .19, .19],
                          "highlight_color": [.8, .8, .8], "threshold": .5, "highlight_threshold": .85, "gradation_offset": 0, "opacity": 1}]
        hard_edges, selected_edges = evaluated.get('hard_edges',[]), []
        if fn is None and selected:raise RuntimeError('Native export cannot omit selected-edge provenance')
        for edge in range(fn.numEdges if fn is not None else 0):
            if not fn.isEdgeSmooth(edge):
                hard_edges.append(list(fn.getEdgeVertices(edge)))
            if not evaluated["level"] and edge in selected:
                selected_edges.append(list(fn.getEdgeVertices(edge)))
        mesh = {"name": name, "vertices": evaluated["world_points"], "faces": faces,
                "triangles": triangles, "triangle_faces": triangle_faces,
                "material_ids": [] if geometry_purpose=="render" and fn is None else (np.maximum(0,np.asarray(ids,dtype=np.int64)[evaluated['base_face_ids']]).tolist() if len(ids) else [0]*len(faces)), "materials": materials,
                "hard_edges": hard_edges, "selected_edges": selected_edges,
                "smooth_level": evaluated["level"], "geometry_purpose": geometry_purpose,
                "base_face_count": evaluated["base_face_count"], "base_vertex_count": evaluated["base_vertex_count"],
                "base_edge_count": evaluated["base_edge_count"]}
        if geometry_purpose=='render' and fn is None:
            mesh['_render_geometry']=evaluated
            mesh['material_ids']=np.maximum(0,np.asarray(ids,dtype=np.int64)[evaluated['base_face_ids']]) if len(ids) else np.zeros(len(faces),np.int64)
        if geometry_purpose=='viewport' and fn is None:
            mesh['_native_evaluated']=evaluated
            if cached is not None and cached.get('topology') is not None:mesh['_gpu_topology']=cached['topology']
        if evaluated["level"]:
            mesh["base_face_ids"] = evaluated["base_face_ids"]
            mesh["base_edge_children"] = evaluated["base_edge_children"]
            source_edges = om.MItMeshEdge(path)
            for edge in selected:
                source_edges.setIndex(edge)
                selected_edges.extend(smooth_geometry.remap_edges(mesh, [[source_edges.vertexId(0), source_edges.vertexId(1)]]))
        if include_normals:
            try:
                normal_matrix = path.inclusiveMatrix().inverse().transpose()
                def normal(face_id, vertex):
                    if not evaluated["level"]:
                        return list(fn.getFaceVertexNormal(face_id, vertex, om.MSpace.kWorld))
                    value = fn.getFaceVertexNormal(face_id, vertex, om.MSpace.kObject) * normal_matrix
                    value.normalize()
                    return list(value)
                mesh["triangle_normals"] = [[normal(face_id, vertex) for vertex in triangle]
                                            for triangle, face_id in zip(triangles, triangle_faces)]
            except RuntimeError:
                warnings.append(name + ": face-vertex normals unavailable; using face normals.")
        if passes is not None:
            mesh["line_passes"] = smooth_geometry.remap_passes(mesh, passes)
        elif chosen:
            mesh["line_set"] = chosen
        if alpha_config:
            evaluated['purpose']=geometry_purpose
            alpha_boundary.transform_mesh(mesh,path,evaluated,alpha_config)
            if not len(mesh['triangles']):
                result['alpha_empty']=True
                continue
        result["meshes"].append(mesh)
        if mesh_ready is not None:mesh_ready(mesh)
    result["warnings"] = list(dict.fromkeys(warnings))
    from . import render_elements
    result["merge_groups"] = line_graph.export_merge_groups(result["meshes"])
    result["render_elements"] = render_elements.snapshot()
    result["scene_name"] = os.path.splitext(os.path.basename(cmds.file(query=True, sceneName=True) or "untitled"))[0]
    if not result["meshes"] and not result.get('alpha_empty') and not (geometry_purpose=='viewport' and mesh_filter is not None):
        raise ValueError("No visible polygon meshes to render.")
    return result


def render_scene(output_prefix, camera=None, settings=None, write_scene=False, auxiliary_outputs=True,exact_visibility=True):
    from . import renderer
    values = validate_settings(settings or load_settings())
    started=time.perf_counter()
    device_aspect=float(cmds.getAttr('defaultResolution.deviceAspectRatio'))
    camera_data=_camera(camera,device_aspect)
    from concurrent.futures import ThreadPoolExecutor
    from .intersections import _prepare, _native_function
    native,_=_native_function('auto')
    from .native_cpu import library
    prepass=None
    if native is not None and library() is not None and values.get('compiled_depth',True):
        ss=int(values['supersample']);w=int(values['width'])*ss;h=int(values['height'])*ss
        # The same production resolution guard applies before allocation.
        from .render_limits import check_frame_samples
        from .line_graph import list_merge_groups
        check_frame_samples(values['width'],values['height'],ss)
        prepass=dict(camera=renderer._camera(camera_data,w,h),depth=np.full((h,w),np.inf),
                     planes=np.zeros((h,w,3)),owners=np.full((h,w),-1,np.int32) if list_merge_groups() else None,
                     counts=[],meshes=[],outlines=[])
    pending=[];depth_tasks=[]
    def prepare_cpu(mesh,index):
        edges=renderer._render_edges(mesh)
        if native is not None:_prepare(mesh,native_bvh=True)
        if prepass is not None:
            from .cpu_outline import outline_edges
            prepass['outlines'][index]=outline_edges(mesh,prepass['camera'],edges)
    def prepare_depth(mesh,index):
        from .cpu_depth import rasterize_mesh
        camera=prepass['camera']
        vertices=(np.asarray(mesh['vertices'],np.float64)-camera['eye']) @ camera['basis'].T
        result=rasterize_mesh(vertices,mesh['triangles'],camera,prepass['depth'],prepass['planes'],prepass['owners'],index)
        mesh['_render_camera_vertices']=vertices
        prepass['counts'].append(result['triangles']);prepass['backend']=result['backend']
    # One ordered depth worker retains mesh ownership on exact depth ties.
    # All Maya API evaluation remains on the main thread. Both stages count
    # toward the measured render; no preparation is moved outside the timer.
    with ThreadPoolExecutor(max_workers=3) as workers,ThreadPoolExecutor(max_workers=1) as depth_worker:
        def ready(mesh):
            geometry=mesh.get('_render_geometry')
            if geometry is not None:
                if '_cpu_triangle_indices' not in geometry:geometry['_cpu_triangle_indices']=np.asarray(mesh['triangles'],np.int64)
                mesh['triangles']=geometry['_cpu_triangle_indices']
            index=len(prepass['meshes']) if prepass is not None else 0
            if prepass is not None:
                prepass['meshes'].append(id(mesh));prepass['outlines'].append(None)
                depth_tasks.append(depth_worker.submit(prepare_depth,mesh,index))
            if '_render_geometry' in mesh or prepass is not None:pending.append(workers.submit(prepare_cpu,mesh,index))
        scene = export_scene(camera, values,camera_override=camera_data,include_normals=False,
                             include_materials=False,as_arrays=True,mesh_ready=ready)
        for task in pending+depth_tasks:task.result()
    export_finished=time.perf_counter()
    values["line_sets"] = scene["line_sets"]
    # Maya's RevToon renderer is a line pass. Surface shading remains available
    # only to standalone reference-renderer callers that explicitly use it.
    values['line_only']=True
    values['auxiliary_outputs']=bool(auxiliary_outputs)
    values['exact_visibility']=bool(exact_visibility)
    values['triangle_outlines']=True
    output_prefix = os.path.abspath(output_prefix)
    os.makedirs(os.path.dirname(output_prefix), exist_ok=True)
    scene_path = None
    # Diagnostic geometry snapshots can be hundreds of MiB. They are not
    # renderer output and should not delay every ordinary Maya frame render.
    if write_scene:
        scene_path = output_prefix + "_scene.json"
        with open(scene_path, "w", encoding="utf-8") as stream:
            json.dump({"format": "reatoon-scene", "version": 1, "scene": dict(scene,meshes=[{k:v for k,v in m.items() if not k.startswith("_")} for m in scene["meshes"]]), "settings": values}, stream, separators=(',',':'),default=lambda value:value.tolist())
    snapshot_finished=time.perf_counter()
    from . import render_geometry_cache
    try:
        result = renderer.render(scene, output_prefix, values,depth_prepass=prepass)
    finally:
        render_geometry_cache.trim()
    result["geometry_cache"]=render_geometry_cache.stats()
    result['maya_timings_seconds']=dict(export=export_finished-started,snapshot=snapshot_finished-export_finished,
        render=time.perf_counter()-snapshot_finished,total=time.perf_counter()-started)
    result["scene_path"] = scene_path
    result["scene_warnings"] = scene["warnings"]
    for warning in scene["warnings"]:
        cmds.warning("ReaToon: " + warning)
    return result


def render_sequence(start, end, step, output_prefix, camera=None, settings=None):
    """Render a bounded inclusive frame sequence and restore the original time."""
    for value in (start, end, step):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or int(value) != value:
            raise ValueError("Frame bounds and step must be finite integers.")
    start, end, step = int(start), int(end), int(step)
    if step < 1 or end < start or (end - start) // step + 1 > 1000:
        raise ValueError("Use a positive step, start <= end, and at most 1000 frames.")
    if min(start, end) < -100000 or max(start, end) > 100000:
        raise ValueError("Frame bounds must be within -100000 to 100000.")
    original = cmds.currentTime(query=True)
    results = []
    try:
        for frame in range(start, end + 1, step):
            cmds.currentTime(frame, edit=True)
            prefix = "%s.%04d" % (output_prefix, frame)
            results.append({"frame": frame, "result": render_scene(prefix, camera, settings)})
    finally:
        cmds.currentTime(original, edit=True)
    return results
