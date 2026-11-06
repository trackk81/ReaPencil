"""Live Viewport 2.0 polygon lines for RevToon.

World-space line segments are sent directly to MUIDrawManager. Maya's VP2
scene depth tests visible lines. An optional dashed x-ray underlay is a fast
hidden-line preview, not the CPU renderer's visibility-split vector result.

Type ID 0x0007F7F7 is in Autodesk's site-local development range (0..0x7ffff).
It is NOT a globally allocated distribution ID and may collide with another
site's custom plug-in. This is a technical identity, not a licensing mechanism.

References:
https://help.autodesk.com/cloudhelp/2022/ENU/Maya-SDK/Maya-Python-API/Dependency-Graph-Plug-in-Basics/Dependency-Graph-Plug-ins.html
https://help.autodesk.com/cloudhelp/2026/ENU/MAYA-API-REF/cpp_ref/class_m_h_w_render_1_1_m_u_i_draw_manager.html
"""
import json
import math
import time
import os

from maya import cmds
from maya.api import OpenMaya as om
from maya.api import OpenMayaRender as omr
from maya.api import OpenMayaUI as omui

NODE_NAME = "reaToonViewport"
TYPE_ID = om.MTypeId(0x0007F7F7)
DRAW_CLASSIFICATION = "drawdb/geometry/reaToonViewport"
DRAW_REGISTRANT = "ReaToonViewportDraw"
# Bound estimated resident Python geometry and native draw buffers, rather
# than rejecting a scene merely for exceeding an arbitrary triangle count.
MAX_GEOMETRY_BYTES = 512 * 1024 * 1024
MAX_DRAW_BYTES = 64 * 1024 * 1024
MAX_SEGMENTS = MAX_DRAW_BYTES // (2 * 4 * 8)

_registered = False
_callbacks = []
_node_callbacks = []
_watchers_stale = True
_generation = 1
_snapshot_generation = -1
_snapshot = None
_settings_key = None
_intersection_cache = None
_snapshot_ms = 0.0
_prepared_edges = None
_static_draw_cache = None
_last_report = {"state": "disabled", "segments": 0, "warnings": []}
_gpu_scene = None
_gpu_rebuild = True
_gpu_graph_dirty = True
_native_lib = None
_native_plugin = None
_native_last_groups = None
_refresh_pending=False
_exiting=False
_gpu_style_dirty=False
_graph_mode=False
_retained_native=False
_view_mesh_filter=None
_geometry_dirty_objects=set()
_smooth_rebuild_only=False


_fast_target_revision=0
def request_refresh(graph_changed=False,style_changed=False):
    global _fast_target_revision
    if graph_changed or style_changed:_fast_target_revision+=1
    """Coalesce editor/DG changes; never redraw inside a DG deletion callback."""
    global _refresh_pending,_gpu_graph_dirty,_gpu_style_dirty
    _gpu_graph_dirty |= graph_changed;_gpu_style_dirty |= style_changed
    _invalidate()
    if _refresh_pending or _exiting or cmds.about(batch=True):return
    from maya import utils
    _refresh_pending=True
    def redraw():
        global _refresh_pending
        _refresh_pending=False
        if _exiting or not _registered:return
        nodes=cmds.ls(type=NODE_NAME,long=True) or []
        from . import fast_viewport
        if any(cmds.getAttr(n+'.linePreviewEnabled') for n in nodes) or (fast_viewport._library is not None and fast_viewport.status()['enabled']):cmds.refresh(force=True)
    utils.executeDeferred(redraw)


def _invalidate(*_):
    global _generation
    _generation += 1
    if _ and isinstance(_[0],om.MObject):
        _geometry_dirty_objects.add(om.MObjectHandle(_[0]).hashCode())


def _scene_changed(*_):
    global _fast_target_revision
    _fast_target_revision+=1
    global _watchers_stale, _gpu_rebuild, _gpu_graph_dirty,_smooth_rebuild_only
    _smooth_rebuild_only=False
    _watchers_stale = True
    _gpu_rebuild = True
    _gpu_graph_dirty = True
    _invalidate()


def _node_changed(node,*_):
    global _watchers_stale,_graph_mode
    try:kind=om.MFnDependencyNode(node).typeName
    except RuntimeError:return _scene_changed()
    if kind=='objectSet':
        from .view_scope import is_display_set
        if is_display_set(om.MFnDependencyNode(node).name()):return
        _watchers_stale=True
        request_refresh(graph_changed=True)
        return
    if kind in ('revToonLine','revToonLineSet','revToonRenderElement'):
        _watchers_stale=True
        if kind=='revToonLine':_graph_mode=True
        request_refresh(graph_changed=True)
    else:_scene_changed()


def _attribute_changed(message, *args):
    global _gpu_rebuild, _gpu_graph_dirty,_smooth_rebuild_only
    flags = (om.MNodeMessage.kAttributeSet | om.MNodeMessage.kConnectionMade |
             om.MNodeMessage.kConnectionBroken | om.MNodeMessage.kAttributeArrayAdded |
             om.MNodeMessage.kAttributeArrayRemoved | om.MNodeMessage.kAttributeAdded |
             om.MNodeMessage.kAttributeRemoved)
    if message & flags:
        _invalidate(args[0].node() if args else None)
        if args:
            plug=args[0]
            name=plug.partialName(useLongNames=True)
            kind=om.MFnDependencyNode(plug.node()).typeName
            if kind in ('revToonLine','revToonLineSet') and name=='overrides':
                request_refresh(style_changed=True)
            elif kind in ('revToonLine','revToonLineSet','revToonRenderElement','objectSet','shadingEngine') or name=='revToonMergeGroup':
                _gpu_graph_dirty=True
                request_refresh(graph_changed=True)
            if kind=='shadingEngine' or (kind=='objectSet' and cmds.attributeQuery('reaToonKind',node=om.MFnDependencyNode(plug.node()).name(),exists=True)):
                _gpu_rebuild=True;_smooth_rebuild_only=False
            if name in ('reaPencilAlphaBoundary','uvSet','uvPivot','visibility','intermediateObject','edgeSmoothing','enabledSmoothMesh',
                        'displaySmoothMesh','smoothLevel','renderSmoothLevel','useSmoothPreviewForRender',
                        'smoothDrawType','useGlobalSmoothDrawType','boundaryRule','keepHardEdge',
                        'keepBorder','propagateEdgeHardness','keepMapBorders','smoothUVs') or name.startswith(('osd','uvSet')):
                smooth_change=name in ('displaySmoothMesh','smoothLevel','renderSmoothLevel','useSmoothPreviewForRender','smoothDrawType','useGlobalSmoothDrawType','boundaryRule','keepHardEdge','keepBorder','propagateEdgeHardness','keepMapBorders','smoothUVs') or name.startswith('osd')
                if not _gpu_rebuild:_smooth_rebuild_only=smooth_change
                elif not smooth_change:_smooth_rebuild_only=False
                _gpu_rebuild=True
                if name=='reaPencilAlphaBoundary':request_refresh()


def _targets_changed(*_):
    global _fast_target_revision
    _fast_target_revision+=1
    # Maya set membership edits do not reliably emit attributeChanged.
    # Rebuild material-boundary metadata as well as the per-face target map.
    global _gpu_rebuild,_gpu_graph_dirty,_smooth_rebuild_only
    if _:
        try:
            from .view_scope import is_display_set
            if is_display_set(om.MFnDependencyNode(_[0]).name()):return
        except (RuntimeError,TypeError):pass
    _gpu_rebuild=True
    _smooth_rebuild_only=False
    _gpu_graph_dirty=True
    request_refresh(graph_changed=True)


def _remove_callbacks(callbacks):
    while callbacks:
        callback = callbacks.pop()
        try:
            om.MMessage.removeCallback(callback)
        except RuntimeError:
            pass


def _watch_scene():
    """Watch evaluated geometry, its ancestors and persistent style nodes."""
    global _watchers_stale
    from . import maya_scene
    _remove_callbacks(_node_callbacks)
    names = set()
    for mesh in cmds.ls(type="mesh", long=True, allPaths=True) or []:
        names.add(mesh)
        parent = mesh.rsplit("|", 1)[0]
        while parent:
            names.add(parent)
            parent = parent.rsplit("|", 1)[0]
    names.update(cmds.ls(type="shadingEngine") or [])
    # A merge group can contain existing/nested sets whose membership changes
    # independently of the registered wrapper set.
    names.update(cmds.ls(type="objectSet") or [])
    for node_type in ('revToonLine','revToonLineSet','revToonRenderElement','revToonRenderSettings'):
        if node_type in cmds.allNodeTypes():names.update(cmds.ls(type=node_type) or [])
    names.update(cmds.ls('*.revToonGraphOwned',objectsOnly=True) or [])
    names.update(cmds.ls("*.reaToonKind", objectsOnly=True,recursive=True) or [])
    seen = set()
    for name in names:
        try:
            if cmds.nodeType(name)=='objectSet':
                from .view_scope import is_display_set
                if is_display_set(name):continue
            selection = om.MSelectionList()
            selection.add(name)
            obj = selection.getDependNode(0)
            key = om.MObjectHandle(obj).hashCode()
            if key in seen:
                continue
            seen.add(key)
            _node_callbacks.append(om.MNodeMessage.addNodeDirtyCallback(obj, _invalidate))
            _node_callbacks.append(om.MNodeMessage.addAttributeChangedCallback(obj, _attribute_changed))
            if obj.hasFn(om.MFn.kMesh):
                _node_callbacks.append(om.MPolyMessage.addPolyTopologyChangedCallback(obj, _scene_changed))
            if obj.hasFn(om.MFn.kSet):
                _node_callbacks.append(om.MObjectSetMessage.addSetMembersModifiedCallback(obj,_targets_changed))
        except RuntimeError:
            continue
    _watchers_stale = False


def _start_callbacks():
    if _callbacks:
        return
    _callbacks.append(om.MEventMessage.addEventCallback("timeChanged", _invalidate))
    _callbacks.append(om.MDGMessage.addNodeAddedCallback(_node_changed, "dependNode"))
    _callbacks.append(om.MDGMessage.addNodeRemovedCallback(_node_changed, "dependNode"))
    _callbacks.append(om.MDagMessage.addParentAddedCallback(_scene_changed))
    _callbacks.append(om.MDagMessage.addParentRemovedCallback(_scene_changed))
    _callbacks.append(om.MSceneMessage.addCallback(om.MSceneMessage.kAfterOpen, _scene_changed))
    _callbacks.append(om.MSceneMessage.addCallback(om.MSceneMessage.kAfterNew, _scene_changed))
    # Maya embeds Python and does not always run tempfile's atexit handlers.
    # Explicitly release private GPU paging files on scene replacement/exit.
    for event in (om.MSceneMessage.kBeforeOpen,om.MSceneMessage.kBeforeNew):
        _callbacks.append(om.MSceneMessage.addCallback(event,_release_gpu_scene))
    _callbacks.append(om.MSceneMessage.addCallback(om.MSceneMessage.kMayaExiting,_on_exit))
    _callbacks.append(om.MEventMessage.addEventCallback("Undo", _scene_changed))
    _callbacks.append(om.MEventMessage.addEventCallback("Redo", _scene_changed))


def _release_gpu_scene(*_):
    global _gpu_scene,_gpu_rebuild,_native_last_groups,_graph_mode
    scene=_gpu_scene;_gpu_scene=None;_gpu_rebuild=True;_native_last_groups=None
    _graph_mode=False
    if scene is not None:scene.close()


def _on_exit(*_):
    global _exiting
    _exiting=True;_release_gpu_scene()


def _stop_callbacks():
    _remove_callbacks(_callbacks)
    _remove_callbacks(_node_callbacks)


def _camera_data(path, aspect):
    """Use the actual viewport camera, not the render-camera checkbox."""
    fn = om.MFnCamera(path)
    matrix = path.inclusiveMatrix()
    eye = om.MPoint(0, 0, 0) * matrix
    direction = (om.MVector(0, 0, -1) * matrix).normal()
    up = (om.MVector(0, 1, 0) * matrix).normal()
    # Silhouette classification needs position/direction only. A centered
    # angular approximation is sufficient; Maya projects the drawn geometry.
    return {"position": [eye.x, eye.y, eye.z],
            "target": [eye.x + direction.x, eye.y + direction.y, eye.z + direction.z],
            "up": list(up), "projection": "orthographic" if fn.isOrtho() else "perspective",
            "fov_y": math.degrees(fn.verticalFieldOfView()),
            "ortho_width": float(fn.orthoWidth), "near": float(fn.nearClippingPlane),
            "far": float(fn.farClippingPlane)}


def _snapshot_for(camera_path, settings):
    global _snapshot_generation, _snapshot, _settings_key, _intersection_cache, _snapshot_ms, _prepared_edges
    from . import maya_scene
    key = json.dumps(settings, sort_keys=True)
    if _watchers_stale:
        _watch_scene()
    if _snapshot is None or _snapshot_generation != _generation:
        # Reuses the same validated geometry contract as the offline renderer.
        # VP2 owns projection and supports shifted/asymmetric film gates.
        # Only camera position/direction are needed for edge classification.
        started = time.perf_counter()
        snapshot = maya_scene.export_scene(camera_path.fullPathName(), settings,
                                           camera_override=_camera_data(camera_path, 1.0), include_normals=False)
        estimated = sum(len(m["vertices"]) * 176 + len(m.get("triangles", [])) * 192
                        + sum(64 + 36 * len(face) for face in m["faces"])
                        + len(m.get("hard_edges", [])) * 144 for m in snapshot["meshes"])
        if estimated > MAX_GEOMETRY_BYTES:
            raise ValueError("Live line geometry estimate %.1f MiB exceeds memory budget %d MiB."
                             % (estimated / 1048576, MAX_GEOMETRY_BYTES // 1048576))
        snapshot["viewport_estimated_bytes"] = estimated
        _snapshot_ms = (time.perf_counter() - started) * 1000
        _snapshot = snapshot
        _snapshot_generation = _generation
        _settings_key = key
        _intersection_cache = None
        _prepared_edges = None
    return _snapshot


def _intersection_records(scene, settings):
    global _intersection_cache
    from . import renderer
    # Geometry intersections are independent of camera position. Cache them
    # until geometry/time/style membership changes, including on animation.
    styles = []
    for mesh in scene["meshes"]:
        style = dict(settings)
        style.update(settings.get("line_sets", {}).get(mesh.get("line_set"), {}))
        styles.append(style)
    mode_key = (any(s.get("intersections", False) for s in styles),
                any(s.get("self_intersections", False) for s in styles),
                settings.get("intersection_tolerance", 1e-7))
    if _intersection_cache is None or _intersection_cache[2] != mode_key:
        if any(style.get("intersections", False) or style.get("self_intersections", False) for style in styles):
            from .intersections import find_intersections
            diagnostics = {}
            records = find_intersections(scene["meshes"],
                                         self_intersections=any(style.get("self_intersections", False) for style in styles),
                                         tolerance=settings.get("intersection_tolerance", 1e-7),
                                         diagnostics=diagnostics)
            _intersection_cache = (records, diagnostics, mode_key)
        else:
            _intersection_cache = ([], {}, mode_key)
    records, diagnostics, _ = _intersection_cache
    return records, diagnostics


def _world_segments(scene, settings):
    from . import renderer
    records, diagnostics = _intersection_records(scene, settings)
    if hasattr(renderer, "world_line_segments"):
        result = renderer.world_line_segments(scene, settings, intersections=records)
        result["intersection_diagnostics"] = diagnostics
        return result
    # Compatibility during a staged update: edge drawing remains functional
    # even if the renderer module was imported before its new helper appeared.
    camera = renderer._camera(scene["camera"], settings["width"], settings["height"])
    segments = []
    for mesh_index, mesh in enumerate(scene["meshes"]):
        style = dict(settings)
        style.update(settings.get("line_sets", {}).get(mesh.get("line_set"), {}))
        for pair, features in renderer.classify_edges(mesh, camera, style):
            segments.append({"a": mesh["vertices"][pair[0]], "b": mesh["vertices"][pair[1]],
                             "mesh_index": mesh_index, "features": features, "settings": style})
    for record in records:
        style = dict(settings)
        index = record["mesh_indices"][0]
        style.update(settings.get("line_sets", {}).get(scene["meshes"][index].get("line_set"), {}))
        if style.get("intersections", False):
            segments.append(dict(record, mesh_index=index, settings=style))
    return {"segments": segments, "warnings": [], "intersection_diagnostics": diagnostics}


def _packed_groups(scene, settings):
    """Vectorized camera classification and bulk native point-array creation."""
    global _prepared_edges, _static_draw_cache
    import numpy as np
    from . import renderer
    if _prepared_edges is None:
        _prepared_edges = [renderer.prepare_edges(mesh) for mesh in scene["meshes"]]
    camera = renderer._camera(scene["camera"], settings["width"], settings["height"])
    styles = [dict(settings, **settings.get("line_sets", {}).get(mesh.get("line_set"), {}))
              for mesh in scene["meshes"]]
    batches = {}
    count = 0
    eye = np.asarray(scene["camera"]["position"])
    def append(points, style):
        nonlocal count
        if not len(points):
            return
        count += len(points) // 2
        if count > MAX_SEGMENTS:
            raise ValueError("Live line draw buffer exceeds %d MiB budget." % (MAX_DRAW_BYTES // 1048576))
        color = tuple(style.get("line_color", [.04, .04, .07]))
        hidden = bool(style.get("hidden_lines", False))
        hidden_color = tuple(style.get("hidden_color", [.5, .5, .6]))
        dashed = float(style.get("dash_length", 0)) > 0
        width = float(style.get("line_width", 1.5))
        reduction = float(style.get("distance_reduction", 0))
        if reduction:
            pairs = points.reshape(-1, 2, 3)
            distances = np.linalg.norm(pairs.mean(axis=1) - eye, axis=1)
            widths = np.maximum(.25, np.round(np.maximum(.1, width / (1 + reduction * distances)) * 4) / 4)
            for value in np.unique(widths):
                key = (color, float(value), hidden, hidden_color, dashed)
                batches.setdefault(key, []).append(pairs[widths == value].reshape(-1, 3))
        else:
            key = (color, max(.25, round(width * 4) / 4), hidden, hidden_color, dashed)
            batches.setdefault(key, []).append(points)
    if any('line_passes' in mesh for mesh in scene['meshes']):
        result=renderer.world_line_segments(scene,settings,prepared_edges=_prepared_edges)
        for record in result['segments']:
            append(np.asarray([record['a'],record['b']],dtype=float),record['settings'])
        groups=[(key,om.MPointArray(np.concatenate(arrays))) for key,arrays in batches.items()]
        styles=[style for item in renderer.line_style_passes(scene,settings) for style in item['styles']]
        return groups,count,result.get('intersection_diagnostics',{}),styles,result.get('warnings',[])
    classified = [renderer.classify_edge_indices(prepared, camera, style)
                  for prepared, style in zip(_prepared_edges, styles)]
    cacheable = not any(style.get("distance_reduction", 0) for style in styles)
    static_key = (_snapshot_generation, json.dumps(styles, sort_keys=True))
    cached = _static_draw_cache if cacheable and _static_draw_cache and _static_draw_cache[0] == static_key else None
    def pack():
        # Maya accepts ndarray sequences directly. Avoid transient nested
        # Python lists that otherwise trigger expensive whole-scene GC scans.
        return [(key, om.MPointArray(np.concatenate(arrays))) for key, arrays in batches.items()]
    if cached:
        _, static_groups, count, diagnostics, warnings = cached
    else:
        for prepared, style, (indices, flags) in zip(_prepared_edges, styles, classified):
            static_indices = indices[(flags[indices] & 251) != 0]
            append(prepared["vertices"][prepared["pairs"][static_indices]].reshape(-1, 3), style)
        records, diagnostics = _intersection_records(scene, settings)
        intersection_batches = {}
        for record in records:
            owners = record["mesh_indices"]
            is_self = owners[0] == owners[1]
            for owner in dict.fromkeys(owners):
                if styles[owner].get("self_intersections" if is_self else "intersections", False):
                    intersection_batches.setdefault(owner, []).extend((record["a"], record["b"]))
                    break
        for owner, points in intersection_batches.items():
            append(np.asarray(points, dtype=float), styles[owner])
        static_groups = pack()
        warnings = ["Coplanar overlaps and point-only contacts are omitted from intersection lines."] if records else []
        if cacheable:
            _static_draw_cache = (static_key, static_groups, count, diagnostics, warnings)
    # Only silhouette edges lacking another enabled static feature change with
    # the camera. Native buffers for hard/crease/material/intersection edges
    # stay resident, avoiding Python allocations and cyclic GC stalls on orbit.
    batches = {}
    for prepared, style, (indices, flags) in zip(_prepared_edges, styles, classified):
        dynamic_indices = indices[flags[indices] == 4]
        append(prepared["vertices"][prepared["pairs"][dynamic_indices]].reshape(-1, 3), style)
    return static_groups + pack(), count, diagnostics, styles, list(warnings)


def build_draw_data(camera_path, old_data=None, aspect=1.0, clip=None):
    """Prepare renderable data; callable in mayapy for deterministic probes."""
    global _last_report, _gpu_scene, _gpu_rebuild, _gpu_graph_dirty,_graph_mode
    from . import maya_scene
    begin = time.perf_counter()
    data = old_data if isinstance(old_data, _DrawData) else _DrawData()
    if os.environ.get('REVTOON_VIEWPORT_BACKEND','gpu').lower() != 'cpu':
        try:
            from .gpu_viewport import LiveScene
            from . import line_graph
            lines=line_graph.list_lines()
            nodes=cmds.ls(type=NODE_NAME) or []
            _graph_mode |= bool(lines) or any(cmds.getAttr(n+'.lineGraphMode') for n in nodes)
            if _graph_mode:
                for n in nodes:
                    if not cmds.getAttr(n+'.lineGraphMode'):cmds.setAttr(n+'.lineGraphMode',True)
            if _graph_mode and not lines:
                data.groups=[];data.report=dict(state='ready',backend='opencl_gpu',segments=0,submitted_segments=0,
                    reason='empty_line_graph',evaluated_frame=float(cmds.currentTime(query=True)))
                _last_report=dict(data.report)
                return data
            settings=maya_scene.load_settings()
            camera=_camera_data(camera_path,aspect)
            if _view_mesh_filter is not None:camera['_viewport_mesh_filter']=_view_mesh_filter
            if clip is not None:camera['viewport_clip']=clip
            if _watchers_stale:
                _watch_scene()
            if _gpu_scene is None or _gpu_rebuild:
                if _gpu_scene is not None:
                    _gpu_scene.close()
                _gpu_scene=None
                _gpu_scene=LiveScene(camera_path,settings,camera)
                # The constructor has just uploaded these evaluated positions.
                # Repeating subdivision on the first draw used to dominate startup.
                _gpu_scene.generation=_generation
                _gpu_graph_dirty=False
                _gpu_rebuild=False
            data.groups,data.report=_gpu_scene.draw(camera,settings,_generation,native=_native_lib is not None)
            data.report=dict(data.report,prepare_ms=(time.perf_counter()-begin)*1000)
        except Exception as error:
            # Explicit error, not an undisclosed slow CPU fallback or stale lines.
            import traceback
            data.groups=[]
            data.report=dict(state='error',backend='opencl_gpu',segments=0,error=str(error),traceback=traceback.format_exc(),warnings=[])
            _gpu_rebuild=True
        _last_report=dict(data.report)
        return data
    try:
        settings = maya_scene.load_settings()
        snapshot = _snapshot_for(camera_path, settings)
        scene = dict(snapshot)
        scene["camera"] = _camera_data(camera_path, aspect)
        values = dict(settings, line_sets=scene.get("line_sets", {}))
        cache_key = (_snapshot_generation, json.dumps(values, sort_keys=True),
                     tuple(scene["camera"]["position"]), tuple(scene["camera"]["target"]),
                     scene["camera"]["projection"])
        if data.cache_key == cache_key:
            data.report = dict(data.report, prepare_ms=round((time.perf_counter() - begin) * 1000, 3),
                               draw_cache_hit=True)
            _last_report = dict(data.report)
            return data
        data.groups = []
        classify_start = time.perf_counter()
        data.groups, count, diagnostics, styles, warnings = _packed_groups(scene, values)
        classify_ms = (time.perf_counter() - classify_start) * 1000
        if any(style.get(key, 0) for style in styles for key in ("taper", "width_variation")):
            warnings.append("VP2 preview uses constant width per edge; taper/width variation are offline-only.")
        if any(style.get("hidden_lines") for style in styles):
            warnings.append("Hidden preview is a dashed x-ray underlay; exact hidden segmentation is offline-only.")
        data.report = {"state": "ready", "segments": count, "batches": len(data.groups),
                       "mesh_count": len(scene["meshes"]), "geometry_generation": _snapshot_generation,
                       "prepare_ms": round((time.perf_counter() - begin) * 1000, 3),
                       "draw_cache_hit": False, "export_ms": round(_snapshot_ms, 3),
                       "classify_and_pack_ms": round(classify_ms, 3),
                       "estimated_geometry_bytes": scene.get("viewport_estimated_bytes", 0),
                       "triangles": sum(len(m.get("triangles", [])) for m in scene["meshes"]),
                       "warnings": warnings, "intersection_diagnostics": diagnostics}
        data.cache_key = cache_key
    except Exception as error:
        data.groups = []
        data.cache_key = None
        data.report = {"state": "error", "segments": 0, "error": str(error), "warnings": []}
    _last_report = dict(data.report)
    return data


def _native_prepare(camera_name, aspect, destination=''):
    """Called synchronously by the native VP2 adapter, never on a worker thread."""
    global _native_last_groups,_view_mesh_filter,_gpu_rebuild,_snapshot
    import ctypes as c
    from . import maya_scene
    from .view_scope import export_filter
    current_filter=export_filter(destination)
    if current_filter!=_view_mesh_filter:
        _view_mesh_filter=current_filter;_gpu_rebuild=True;_snapshot=None;_invalidate()
    # VP2 may still invoke a locator while its view camera is being removed
    # during scene replacement. Never reuse strokes from the previous view.
    if not camera_name or not cmds.objExists(camera_name):
        _native_lib.rt_begin()
        _native_lib.rt_end()
        _native_last_groups=None
        return
    clip=None
    if hasattr(_native_lib,'rt_view_projection'):
        matrix=(c.c_double*16)();width=c.c_int();height=c.c_int()
        if _native_lib.rt_view_projection(matrix,c.byref(width),c.byref(height)):
            clip=dict(matrix=list(matrix),width=width.value,height=height.value)
    data=build_draw_data(maya_scene._dag(camera_name),aspect=aspect,clip=clip)
    if data.groups is _native_last_groups:
        return
    transfer_started=time.perf_counter()
    _native_lib.rt_begin()
    for (color,width,hidden,hidden_color,dashed),points in data.groups:
        colors=(c.c_float*3)(*color)
        hidden_colors=(c.c_float*3)(*hidden_color)
        # The native API bounds each submission, not the total frame. Large
        # forests can exceed one million strokes of the same style.
        for start in range(0,len(points),2097152):
            chunk=points[start:start+2097152]
            ok=_native_lib.rt_add(c.c_void_p(chunk.ctypes.data),len(chunk),width,colors,hidden,hidden_colors,dashed)
            if not ok:
                _native_lib.rt_begin()
                _native_lib.rt_end()
                raise RuntimeError('Native viewport buffer submission failed')
    _native_lib.rt_end()
    _native_last_groups=data.groups
    _last_report['native_transfer_ms']=(time.perf_counter()-transfer_started)*1000


class _DrawData(om.MUserData):
    def __init__(self):
        super(_DrawData, self).__init__(False)
        self.groups = []
        self.report = {}
        self.cache_key = None


class ViewportNode(omui.MPxLocatorNode):
    enabled = om.MObject()

    @staticmethod
    def creator():
        return ViewportNode()

    @staticmethod
    def initialize():
        attr = om.MFnNumericAttribute()
        ViewportNode.enabled = attr.create("linePreviewEnabled", "lpe", om.MFnNumericData.kBoolean, True)
        attr.keyable = True
        attr.storable = True
        ViewportNode.addAttribute(ViewportNode.enabled)
        attr=om.MFnNumericAttribute()
        mode=attr.create('lineGraphMode','lgm',om.MFnNumericData.kBoolean,False)
        attr.storable=True;attr.hidden=True
        ViewportNode.addAttribute(mode)

    def isBounded(self):
        return _retained_native

    def boundingBox(self):
        return om.MBoundingBox(om.MPoint(-1e8,-1e8,-1e8),om.MPoint(1e8,1e8,1e8))


class ViewportDrawOverride(omr.MPxDrawOverride):
    def __init__(self, obj):
        # Always-dirty ensures camera orbit and each animated redraw classify
        # current silhouettes; geometry/intersections have their own cache.
        super(ViewportDrawOverride, self).__init__(obj, None, True)

    @staticmethod
    def creator(obj):
        return ViewportDrawOverride(obj)

    def supportedDrawAPIs(self):
        return omr.MRenderer.kOpenGL | omr.MRenderer.kOpenGLCoreProfile | omr.MRenderer.kDirectX11

    def hasUIDrawables(self):
        return True

    def isBounded(self, obj_path, camera_path):
        return False

    def disableInternalBoundingBoxDraw(self):
        return True

    def transform(self, obj_path, camera_path):
        return om.MMatrix()  # line coordinates have already been transformed

    def prepareForDraw(self, obj_path, camera_path, frame_context, old_data):
        enabled = om.MFnDependencyNode(obj_path.node()).findPlug("linePreviewEnabled", False).asBool()
        if not enabled:
            data = old_data if isinstance(old_data, _DrawData) else _DrawData()
            data.groups = []
            return data
        aspect = 1.0
        if frame_context is not None:
            try:
                _, _, width, height = frame_context.getViewportDimensions()
                aspect = float(width) / max(height, 1)
            except (AttributeError, RuntimeError, TypeError):
                pass
        clip=None
        if frame_context is not None:
            try:
                clip=dict(matrix=list(frame_context.getMatrix(omr.MFrameContext.kViewProjMtx)),width=width,height=height)
            except (AttributeError,RuntimeError,TypeError):pass
        return build_draw_data(camera_path, old_data, aspect,clip)

    def addUIDrawables(self, obj_path, draw_manager, frame_context, data):
        if not isinstance(data, _DrawData):
            return
        draw_manager.beginDrawable(omr.MUIDrawManager.kNonSelectable)
        try:
            # Submit every underlay before the depth-tested visible strokes.
            # This is intentionally approximate x-ray preview, not CPU-style
            # visibility segmentation.
            if any(key[2] for key, _ in data.groups):
                draw_manager.beginDrawInXray()
                try:
                    for (color, width, hidden, hidden_color, dashed), points in data.groups:
                        if hidden:
                            draw_manager.setLineWidth(width)
                            draw_manager.setColor(om.MColor((*hidden_color, 1.0)))
                            draw_manager.setLineStyle(omr.MUIDrawManager.kDashed)
                            # Maya x-ray state affects mesh(kLines), not lineList.
                            draw_manager.mesh(omr.MUIDrawManager.kLines, points)
                finally:
                    draw_manager.endDrawInXray()
            for (color, width, hidden, hidden_color, dashed), points in data.groups:
                draw_manager.setLineWidth(width)
                draw_manager.setColor(om.MColor((*color, 1.0)))
                draw_manager.setLineStyle(omr.MUIDrawManager.kDashed if dashed else omr.MUIDrawManager.kSolid)
                draw_manager.setDepthPriority(omr.MRenderItem.sDormantWireDepthPriority)
                draw_manager.lineList(points, False)
        finally:
            draw_manager.endDrawable()


def register(plugin_fn):
    global _registered, _native_lib, _native_plugin, _retained_native, DRAW_CLASSIFICATION
    from pathlib import Path
    native_dir=Path(__file__).resolve().parents[2]/'plug-ins'/cmds.about(version=True)
    retained=native_dir/'reaPencilDraw090.mll'
    if not retained.is_file():retained=native_dir/'reaPencilDraw088.mll'
    if not retained.is_file():retained=native_dir/'reaPencilDraw087.mll'
    if not retained.is_file():retained=native_dir/'reaPencilDraw084.mll'
    native_enabled=(os.environ.get('REVTOON_VIEWPORT_BACKEND','gpu')!='cpu' and os.environ.get('REVTOON_NATIVE_DRAW','1')!='0')
    _retained_native=bool(native_enabled and retained.is_file() and os.environ.get('REAPENCIL_RETAINED_VIEWPORT','1')!='0')
    DRAW_CLASSIFICATION='drawdb/subscene/reaToonViewport' if _retained_native else 'drawdb/geometry/reaToonViewport'
    plugin_fn.registerNode(NODE_NAME, TYPE_ID, ViewportNode.creator, ViewportNode.initialize,
                           om.MPxNode.kLocatorNode, DRAW_CLASSIFICATION)
    try:
        native=retained if _retained_native else native_dir/'revToonDraw081.mll'
        if not native.is_file():native=native.with_name('revToonDraw.mll')
        if (native.is_file() and os.environ.get('REVTOON_VIEWPORT_BACKEND','gpu')!='cpu'
                and os.environ.get('REVTOON_NATIVE_DRAW','1')!='0'):
            import ctypes as c
            if native.stem in ('reaPencilDraw087','reaPencilDraw088','reaPencilDraw090'):
                for previous in ('reaPencilDraw084','reaPencilDraw087','reaPencilDraw088'):
                    if previous==native.stem:continue
                    if cmds.pluginInfo(previous,q=True,registered=True) and cmds.pluginInfo(previous,q=True,loaded=True):
                        if not cmds.pluginInfo(previous,q=True,unloadOk=True):raise RuntimeError('Restart Maya to update the GPU viewport module.')
                        if cmds.pluginInfo(previous,q=True,autoload=True):
                            cmds.pluginInfo(previous,e=True,autoload=False);cmds.pluginInfo(savePluginPrefs=True)
                        cmds.unloadPlugin(previous)
            cmds.loadPlugin(str(native),quiet=True)
            _native_plugin=native.stem
            _native_lib=c.CDLL(str(native))
            _native_lib.rt_begin.argtypes=[]
            _native_lib.rt_begin.restype=None
            _native_lib.rt_add.argtypes=[c.c_void_p,c.c_uint,c.c_float,c.POINTER(c.c_float),c.c_int,c.POINTER(c.c_float),c.c_int]
            _native_lib.rt_add.restype=c.c_int
            _native_lib.rt_end.argtypes=[]
            _native_lib.rt_end.restype=None
            if _retained_native:
                from . import retained_viewport
                retained_viewport.bind(_native_lib)
            if hasattr(_native_lib,'rt_view_projection'):
                _native_lib.rt_view_projection.argtypes=[c.POINTER(c.c_double),c.POINTER(c.c_int),c.POINTER(c.c_int)]
                _native_lib.rt_view_projection.restype=c.c_int
        else:
            omr.MDrawRegistry.registerDrawOverrideCreator(DRAW_CLASSIFICATION, DRAW_REGISTRANT,
                                                         ViewportDrawOverride.creator)
        _start_callbacks()
    except Exception:
        _stop_callbacks()
        try:
            if _native_plugin:
                cmds.unloadPlugin(_native_plugin)
                _native_plugin=None
                _native_lib=None
            else:
                omr.MDrawRegistry.deregisterDrawOverrideCreator(DRAW_CLASSIFICATION, DRAW_REGISTRANT)
        except RuntimeError:
            pass
        plugin_fn.deregisterNode(TYPE_ID)
        raise
    _registered = True
    _scene_changed()


def unregister(plugin_fn):
    global _registered, _snapshot, _intersection_cache, _prepared_edges, _static_draw_cache, _gpu_scene
    global _native_plugin, _native_lib, _native_last_groups
    from . import fast_viewport
    fast_viewport.shutdown()
    _stop_callbacks()
    if _native_plugin:
        cmds.unloadPlugin(_native_plugin)
        _native_plugin=None
        _native_lib=None
        _native_last_groups=None
    else:
        omr.MDrawRegistry.deregisterDrawOverrideCreator(DRAW_CLASSIFICATION, DRAW_REGISTRANT)
    plugin_fn.deregisterNode(TYPE_ID)
    _registered = False
    _snapshot = None
    _intersection_cache = None
    _prepared_edges = None
    _static_draw_cache = None
    if _gpu_scene is not None:
        _gpu_scene.close()
        _gpu_scene=None


def enable(_from_renderer=False):
    """Create one tiny helper locator, preserving the user's selection."""
    from . import fast_viewport
    if not _from_renderer:
        fast_viewport.disable()
        from . import preview_renderers
        preview_renderers.select_precise()
    if not _registered:
        raise RuntimeError("RevToon viewport node is not registered; load the plug-in first.")
    nodes = cmds.ls(type=NODE_NAME, long=True) or []
    if nodes:
        for node in nodes:
            cmds.setAttr(node + ".linePreviewEnabled", True)
            cmds.setAttr(node + ".visibility", True)
        _invalidate()
        cmds.refresh(force=True)
        return nodes[0]
    selection = cmds.ls(selection=True, long=True) or []
    cmds.undoInfo(openChunk=True, chunkName="Enable RevToon viewport")
    try:
        node = cmds.createNode(NODE_NAME, name="reaToonViewportShape", skipSelect=True)
        transform = cmds.listRelatives(node, parent=True, fullPath=True)[0]
        transform = cmds.rename(transform, "reaToonViewport")
        cmds.addAttr(transform, longName="reaToonViewportOwner", dataType="string")
        cmds.setAttr(transform + ".reaToonViewportOwner", "ReaToon", type="string", lock=True)
        for channel in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
            cmds.setAttr(transform + "." + channel, lock=True, keyable=False, channelBox=False)
        node = cmds.listRelatives(transform, shapes=True, fullPath=True)[0]
        if selection:
            cmds.select(selection, replace=True)
        else:
            cmds.select(clear=True)
    finally:
        cmds.undoInfo(closeChunk=True)
    _scene_changed()
    cmds.refresh(force=True)
    return node


def disable():
    """Remove only our viewport helper shapes/transforms, allowing plug-in unload."""
    global _gpu_scene, _native_last_groups
    from . import fast_viewport
    fast_viewport.disable()
    nodes = cmds.ls(type=NODE_NAME, long=True) or []
    selection = cmds.ls(selection=True, long=True) or []
    cmds.undoInfo(openChunk=True, chunkName="Disable RevToon viewport")
    try:
        for node in nodes:
            if not cmds.objExists(node):
                continue
            parent = (cmds.listRelatives(node, parent=True, fullPath=True) or [None])[0]
            children = cmds.listRelatives(parent, children=True, fullPath=True) if parent else []
            owned = parent and cmds.attributeQuery("reaToonViewportOwner", node=parent, exists=True)
            if owned and children == [node]:
                cmds.delete(parent)
            else:
                cmds.delete(node)
        retained = [item for item in selection if cmds.objExists(item)]
        cmds.select(retained, replace=True) if retained else cmds.select(clear=True)
    finally:
        cmds.undoInfo(closeChunk=True)
    _scene_changed()
    if _gpu_scene is not None:
        _gpu_scene.close()
        _gpu_scene=None
    if _native_lib is not None:
        _native_lib.rt_begin()
        _native_lib.rt_end()
        _native_last_groups=None
    cmds.refresh(force=True)
    return len(nodes)


def status():
    from . import fast_viewport
    if fast_viewport._library is not None and fast_viewport.status()['enabled']:return fast_viewport.status()
    nodes = cmds.ls(type=NODE_NAME, long=True) or [] if _registered else []
    return dict(_last_report, registered=_registered, nodes=nodes,
                enabled=any(cmds.getAttr(node + ".linePreviewEnabled") for node in nodes),
                node_type_id="0x0007F7F7 (site-local development ID)",
                geometry_memory_budget=MAX_GEOMETRY_BYTES, draw_memory_budget=MAX_DRAW_BYTES,
                max_segments=MAX_SEGMENTS)
