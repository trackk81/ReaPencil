"""Original, deterministic CPU cel/edge renderer. No Maya or Pencil+ dependency.

This is a reference implementation, not a Pencil+ renderer or file-format clone.
Cast shadows, texture sampling, curved strokes and PLD are not implemented.
Polygon edges drive wire/crease/material features. CPU outlines can follow the
rendered triangle silhouette, including internal nonplanar-quad transitions.
Noncoplanar intersections use an independent triangle AABB BVH implementation.
"""
from __future__ import annotations

import json
import math
import struct
import zlib
import time
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np

from .intersections import find_intersections, find_render_intersections


DEFAULTS = dict(width=640, height=480, supersample=2, background=[1, 1, 1],
                line_width=1.5, line_color=[0.04, 0.04, 0.07], hidden_lines=False,
                hidden_color=[0.5, 0.5, 0.6], outline=True, open_edges=True,
                crease=True, crease_angle=40.0, material_boundaries=True,
                selected_edges=True, wireframe=False, hard_edges=True,
                intersections=True, self_intersections=False, intersection_tolerance=1e-7,
                depth_bias=0.002, distance_reduction=0.0, width_variation=0.0,
                taper=0.0, dash_length=0.0, seed=1, line_sets={},edge_prepare_workers=4)


def _unit(v, fallback=None):
    a = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(a))
    if n < 1e-12:
        if fallback is not None:
            return np.asarray(fallback, dtype=float)
        raise ValueError("Zero-length direction vector")
    return a / n


def _color(value):
    a = np.asarray(value, dtype=float)
    if a.shape != (3,) or not np.isfinite(a).all():
        raise ValueError("Color must contain three finite numbers")
    return np.clip(a, 0, 1)


def _camera(config, width, height):
    eye = np.asarray(config.get("position", [5, 4, 7]), dtype=float)
    forward = _unit(np.asarray(config.get("target", [0, 0, 0])) - eye)
    right = _unit(np.cross(forward, config.get("up", [0, 1, 0])))
    up = np.cross(right, forward)
    near, far = float(config.get("near", 0.1)), float(config.get("far", 10000))
    if not 0 < near < far:
        raise ValueError("Camera requires 0 < near < far")
    fov = float(config.get("fov_y", 45))
    if not 0 < fov < 179:
        raise ValueError("fov_y must be between 0 and 179 degrees")
    ortho = config.get("projection", "perspective") == "orthographic"
    span = float(config.get("ortho_width", 10))
    if span <= 0:
        raise ValueError("ortho_width must be positive")
    film_aspect=float(config.get('film_aspect',width/height))
    if not math.isfinite(film_aspect) or film_aspect<=0:raise ValueError('Invalid camera film aspect')
    # Maya can keep a film gate aspect that differs from a requested preview
    # image's width/height. Scale projection axes independently in camera space.
    basis=np.stack([right,up,forward])
    if ortho:basis[1]*=film_aspect/(width/height)
    else:basis[0]*=(width/height)/film_aspect
    return dict(eye=eye, forward=forward, basis=basis,
                near=near, far=far, ortho=ortho, span=span, width=width,
                height=height, focal=height / (2 * math.tan(math.radians(fov) / 2)))


def _project(points, camera):
    p = np.asarray(points, dtype=float)
    if camera["ortho"]:
        factor = camera["width"] / camera["span"]
    else:
        factor = camera["focal"] / p[..., 2]
    return np.stack([camera["width"] / 2 + p[..., 0] * factor,
                     camera["height"] / 2 - p[..., 1] * factor], axis=-1)


def _clip_polygon(points, near, far):
    result = [np.asarray(p, dtype=float) for p in points]
    for plane, sign in ((near, 1), (far, -1)):
        source, result = result, []
        if not source:
            break
        a = source[-1]
        ina = sign * (a[2] - plane) >= 0
        for b in source:
            inb = sign * (b[2] - plane) >= 0
            if ina != inb:
                t = (plane - a[2]) / (b[2] - a[2])
                result.append(a + (b - a) * t)
            if inb:
                result.append(b)
            a, ina = b, inb
    return result


def _clip_segment(a, b, near, far):
    lo, hi = 0., 1.
    dz = b[2] - a[2]
    if abs(dz) < 1e-14:
        return None if a[2] < near or a[2] > far else (a.copy(), b.copy())
    t0, t1 = sorted(((near - a[2]) / dz, (far - a[2]) / dz))
    lo, hi = max(lo, t0), min(hi, t1)
    return None if lo > hi else (a + (b - a) * lo, a + (b - a) * hi)


def _screen_clip(p, q, width, height, margin=0.):
    # Liang-Barsky, preserving screen interpolation for depth reconstruction.
    d = q - p
    lo, hi = 0., 1.
    for a, b in ((-d[0], p[0] + margin), (d[0], width + margin - p[0]),
                 (-d[1], p[1] + margin), (d[1], height + margin - p[1])):
        if abs(a) < 1e-14:
            if b < 0:
                return None
        elif a < 0:
            lo = max(lo, b / a)
        else:
            hi = min(hi, b / a)
        if lo > hi:
            return None
    return lo, hi


def _face_normal(vertices, face):
    p = vertices[face]
    # Newell remains stable when the first three polygon points are collinear.
    n = np.sum(np.cross(p, np.roll(p, -1, axis=0)), axis=0)
    return _unit(n, [0, 1, 0])


def cel_color(normal, material, light):
    """Evaluate diffuse-only reference lighting and the material color ramp."""
    l = _unit(light.get("direction", [0.4, 0.8, 0.6]))
    value = (max(0., float(np.dot(normal, l))) * float(light.get("intensity", 1.))
             + float(light.get("ambient", 0.15)) + float(material.get("gradation_offset", 0.)))
    return shade_amount(value, material)


def shade_amount(amount, material):
    """Map scalar diffuse lighting to arbitrary color bands or the default 3.

    Optional ramp entries: {position, color, interpolation, enabled=True}.
    Interpolation is attached to the left stop: 0/none (step), 1/linear,
    2/smooth (cubic smoothstep), 3/spline (nonuniform cubic Hermite). These are
    independent reference interpolation functions, not an assertion of exact
    Pencil+ shading/interpolation. Duplicate positions use the final entry.
    """
    values = np.asarray(amount, dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Shading values must be finite")
    ramp = material.get("ramp")
    if ramp:
        entries = {}
        modes = {"none": 0, "step": 0, "constant": 0, "linear": 1, "smooth": 2, "spline": 3}
        for entry in ramp:
            if not entry.get("enabled", True):
                continue
            position = float(entry["position"])
            if not math.isfinite(position) or not 0 <= position <= 1:
                raise ValueError("Ramp positions must be finite and in [0,1]")
            mode = entry.get("interpolation", 0)
            if isinstance(mode, str):
                mode = modes.get(mode.lower(), -1)
            if mode not in (0, 1, 2, 3):
                raise ValueError("Ramp interpolation must be none/linear/smooth/spline or 0..3")
            entries[position] = (_color(entry["color"]), int(mode))
        if entries:
            positions = np.array(sorted(entries))
            colors = np.array([entries[p][0] for p in positions])
            interpolation = np.array([entries[p][1] for p in positions])
            flat = values.reshape(-1)
            indices = np.clip(np.searchsorted(positions, flat, side="right") - 1, 0, len(positions) - 1)
            result = colors[indices].copy()
            if len(positions) > 1:
                for index in range(len(positions) - 1):
                    mask = (indices == index) & (flat >= positions[index])
                    if not np.any(mask) or interpolation[index] == 0:
                        continue
                    distance = positions[index + 1] - positions[index]
                    t = np.clip((flat[mask] - positions[index]) / distance, 0, 1)[:, None]
                    if interpolation[index] == 1:
                        result[mask] = colors[index] * (1 - t) + colors[index + 1] * t
                    elif interpolation[index] == 2:
                        blend = t * t * (3 - 2 * t)
                        result[mask] = colors[index] * (1 - blend) + colors[index + 1] * blend
                    else:
                        previous, following = max(0, index - 1), min(len(positions) - 1, index + 2)
                        slope_a = (colors[index + 1] - colors[previous]) / (positions[index + 1] - positions[previous])
                        slope_b = (colors[following] - colors[index]) / (positions[following] - positions[index])
                        result[mask] = ((2 * t**3 - 3 * t**2 + 1) * colors[index]
                                        + (t**3 - 2 * t**2 + t) * distance * slope_a
                                        + (-2 * t**3 + 3 * t**2) * colors[index + 1]
                                        + (t**3 - t**2) * distance * slope_b)
            return np.clip(result.reshape(values.shape + (3,)), 0, 1)
    base = _color(material.get("color", [.65, .7, .85]))
    result = np.broadcast_to(base, values.shape + (3,)).copy()
    result[values < float(material.get("threshold", .5))] = _color(material.get("shadow_color", base * .4))
    result[values >= float(material.get("highlight_threshold", .85))] = _color(material.get("highlight_color", np.minimum(base * 1.2, 1)))
    return result


def _raster_triangle(points, rgb, depth, image, camera, normals=None, material=None, light=None, depth_planes=None,
                     mesh_owners=None, mesh_index=-1):
    s = _project(points, camera)
    if not np.isfinite(s).all():
        return
    xmin, ymin = np.maximum(np.floor(s.min(axis=0)), 0).astype(int)
    xmax, ymax = np.minimum(np.ceil(s.max(axis=0)),
                            [camera["width"] - 1, camera["height"] - 1]).astype(int)
    if xmin > xmax or ymin > ymax:
        return
    a, b, c = s
    den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(den) < 1e-12:
        return
    plane = None
    if depth_planes is not None:
        vertex_depths = np.asarray(points)[:, 2]
        values = vertex_depths if camera["ortho"] else 1 / vertex_depths
        plane = np.linalg.solve(np.column_stack([s, np.ones(3)]), values)
    # Bounded row blocks avoid allocating a full frame for every triangle.
    for top in range(ymin, ymax + 1, 128):
        bottom = min(top + 128, ymax + 1)
        yy, xx = np.mgrid[top:bottom, xmin:xmax + 1].astype(float)
        xx += .5
        yy += .5
        u = ((b[1] - c[1]) * (xx - c[0]) + (c[0] - b[0]) * (yy - c[1])) / den
        v = ((c[1] - a[1]) * (xx - c[0]) + (a[0] - c[0]) * (yy - c[1])) / den
        w = 1 - u - v
        valid = (u >= -1e-8) & (v >= -1e-8) & (w >= -1e-8)
        if camera["ortho"]:
            z = u * points[0][2] + v * points[1][2] + w * points[2][2]
        else:
            inv = u / points[0][2] + v / points[1][2] + w / points[2][2]
            z = np.divide(1., inv, out=np.full_like(inv, np.inf), where=inv > 0)
        target = depth[top:bottom, xmin:xmax + 1]
        mask = valid & (z < target)
        target[mask] = z[mask]
        if mesh_owners is not None:
            mesh_owners[top:bottom, xmin:xmax + 1][mask] = mesh_index
        if depth_planes is not None:
            depth_planes[top:bottom, xmin:xmax + 1][mask] = plane
        if normals is None:
            image[top:bottom, xmin:xmax + 1][mask] = rgb
        else:
            n = np.asarray(normals, dtype=float)
            if camera["ortho"]:
                interp = u[..., None] * n[0] + v[..., None] * n[1] + w[..., None] * n[2]
            else:
                interp = (u[..., None] * n[0] / points[0][2] + v[..., None] * n[1] / points[1][2]
                          + w[..., None] * n[2] / points[2][2])
            magnitude = np.linalg.norm(interp, axis=-1, keepdims=True)
            interp = np.divide(interp, magnitude, out=np.zeros_like(interp), where=magnitude > 1e-12)
            light = light or {}
            mat = material or {}
            amount = (np.maximum(0., interp @ _unit(light.get("direction", [.4, .8, .6])))
                      * float(light.get("intensity", 1.)) + float(light.get("ambient", .15))
                      + float(mat.get("gradation_offset", 0.)))
            shaded = shade_amount(amount, mat)
            image[top:bottom, xmin:xmax + 1][mask] = shaded[mask]


EDGE_FEATURES = ('wireframe', 'open', 'outline', 'crease', 'material', 'hard', 'selected')


def prepare_edges(mesh):
    """Prepare camera-independent topology once per evaluated geometry snapshot.

    Polygon edges remain polygon edges (no triangulation diagonals). Ragged
    face adjacency supports non-manifold meshes without a two-face assumption.
    The returned arrays are a separate cache; the serializable mesh is untouched.
    """
    vertices = np.asarray(mesh['vertices'], dtype=float)
    faces = mesh.get('faces', mesh.get('triangles', []))
    counts = (np.full(len(faces),faces.shape[1],dtype=np.int64)
              if isinstance(faces,np.ndarray) and faces.ndim==2 else
              np.asarray([len(face) for face in faces],dtype=np.int64))
    if not len(counts) or np.any(counts < 3):
        raise ValueError('Meshes require polygon faces with at least three vertices')
    starts = np.concatenate(([0], np.cumsum(counts)[:-1]))
    try:
        flat = np.asarray(faces,dtype=np.int64).reshape(-1)
    except ValueError:  # mixed polygon sizes
        flat = np.concatenate(faces).astype(np.int64)
    following = np.arange(len(flat)) + 1
    following[np.cumsum(counts)-1] = starts
    points, next_points = vertices[flat], vertices[flat[following]]
    normals = np.add.reduceat(np.cross(points, next_points), starts)
    lengths = np.linalg.norm(normals, axis=1)
    normals = np.divide(normals, lengths[:, None], out=np.zeros_like(normals), where=lengths[:, None] > 1e-12)
    normals[lengths <= 1e-12] = [0, 1, 0]
    centers = np.add.reduceat(points, starts) / counts[:, None]
    raw_pairs = np.sort(np.column_stack((flat, flat[following])), axis=1)
    packed_keys = len(vertices)<2**32 and raw_pairs.min()>=0
    if packed_keys:
        codes=(raw_pairs[:,0].astype(np.uint64)<<np.uint64(32))|raw_pairs[:,1].astype(np.uint64)
        unique,inverse,edge_counts=np.unique(codes,return_inverse=True,return_counts=True)
        pairs=np.column_stack((unique>>np.uint64(32),unique&np.uint64(0xffffffff))).astype(np.int64)
    else:
        pairs, inverse, edge_counts = np.unique(raw_pairs, axis=0, return_inverse=True, return_counts=True)
    order = np.argsort(inverse, kind='stable')
    owners = np.repeat(np.arange(len(faces)), counts)[order]
    edge_starts = np.concatenate(([0], np.cumsum(edge_counts)[:-1]))
    first_normals = np.repeat(normals[owners[edge_starts]], edge_counts, axis=0)
    min_dot = np.minimum.reduceat(np.einsum('ij,ij->i', first_normals, normals[owners]), edge_starts)
    mids = np.asarray(mesh.get('material_ids', [0]*len(faces)))[owners]
    material = np.minimum.reduceat(mids, edge_starts) != np.maximum.reduceat(mids, edge_starts)
    def marked(name):
        entries=mesh.get(name,[])
        if not len(entries):return np.zeros(len(pairs),dtype=bool)
        if packed_keys:
            rows=np.sort(np.asarray(entries,dtype=np.int64).reshape(-1,2),axis=1)
            keys=(rows[:,0].astype(np.uint64)<<np.uint64(32))|rows[:,1].astype(np.uint64)
            return np.isin(unique,keys)
        wanted={tuple(sorted(x)) for x in entries}
        return np.asarray([tuple(p) in wanted for p in pairs])
    return dict(vertices=vertices, pairs=pairs, normals=normals, centers=centers,
                owners=owners, starts=edge_starts, counts=edge_counts, min_dot=min_dot,
                material=material, hard=marked('hard_edges'),selected=marked('selected_edges'))


def prepare_mesh_edges(meshes, workers=1):
    """Prepare independent NumPy mesh topology with deterministic input order."""
    workers=max(1,min(int(workers),8,len(meshes)))
    if workers==1:
        return [prepare_edges(mesh) for mesh in meshes]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(prepare_edges,meshes))


def classify_edge_indices(prepared, camera, settings):
    """Vectorized classification; return selected edge indices and feature bits."""
    p = prepared
    flags = np.zeros(len(p['pairs']), dtype=np.uint8)
    multi = p['counts'] > 1
    if settings.get('wireframe'):
        flags |= 1
    if settings.get('open_edges'):
        flags[p['counts'] == 1] |= 2
    if settings.get('outline'):
        if 'outline_mask' in p:
            silhouettes=p['outline_mask']
        else:
            view = -camera['forward'] if camera['ortho'] else camera['eye']-p['centers']
            facing = np.sum(p['normals'] * view, axis=1) > 0
            facing = facing[p['owners']]
            silhouettes = np.logical_or.reduceat(facing, p['starts']) != np.logical_and.reduceat(facing, p['starts'])
        flags[multi & silhouettes] |= 4
    if settings.get('crease'):
        flags[multi & (p['min_dot'] < math.cos(math.radians(float(settings['crease_angle']))) - 1e-8)] |= 8
    if settings.get('material_boundaries'):
        flags[multi & p['material']] |= 16
    if settings.get('hard_edges'):
        flags[p['hard']] |= 32
    if settings.get('selected_edges'):
        flags[p['selected']] |= 64
    return np.flatnonzero(flags), flags


def classify_edges(mesh, camera, settings, prepared=None):
    """Return vertex pairs and feature names using prepared polygon topology."""
    prepared = prepare_edges(mesh) if prepared is None else prepared
    indices, flags = classify_edge_indices(prepared, camera, settings)
    for index in indices:
        yield tuple(prepared['pairs'][index]), [name for bit, name in enumerate(EDGE_FEATURES) if int(flags[index]) & (1 << bit)]


def line_style_passes(scene, settings=None):
    """Pure shared CPU/GPU pass resolution; -1 means no line target.

    Higher Line priorities draw later. Within each Line, the lowest style ID
    wins among targeted incident faces, preserving full geometric adjacency.
    Legacy scenes produce one pass with the existing per-mesh styles.
    """
    cfg = dict(DEFAULTS)
    cfg.update(settings or {})
    table = dict(scene.get("line_sets", {}))
    table.update(cfg.get("line_sets", {}))
    meshes = scene.get("meshes", [])
    if not any("line_passes" in mesh for mesh in meshes):
        styles = [dict(cfg, **table.get(mesh.get("line_set", ""), {})) for mesh in meshes]
        return [dict(line=None, priority=0, styles=styles,
                     face_style_ids=[np.full(len(m.get("faces", m.get("triangles", []))), i, dtype=np.int32)
                                     for i, m in enumerate(meshes)])]
    lines = {}
    for mesh in meshes:
        for item in mesh.get("line_passes", []):
            lines[item["line"]] = item["priority"]
    result = []
    for line, priority in sorted(lines.items(), key=lambda item: (item[1], item[0])):
        assignments = []
        selected_edges = []
        for mesh in meshes:
            faces = len(mesh.get("faces", mesh.get("triangles", [])))
            item = next((p for p in mesh.get("line_passes", []) if p["line"] == line), None)
            values = item["face_line_sets"] if item else [None] * faces
            if len(values) != faces:
                raise ValueError("line_passes face_line_sets must match polygon faces")
            assignments.append(values)
            selected_edges.append(item.get("selected_edges", {}) if item else {})
        keys = sorted({key for values in assignments for key in values if key is not None}
                      | {key for values in selected_edges for key, pairs in values.items() if pairs},
                      key=lambda key: (table.get(key, {}).get("_order", 0), key))
        indices = {key: i for i, key in enumerate(keys)}
        result.append(dict(line=line, priority=priority,
                           styles=[dict(cfg, **table.get(key, {})) for key in keys],
                           selected_edges=[{indices[key]: pairs for key, pairs in values.items() if key in indices}
                                           for values in selected_edges],
                           face_style_ids=[np.asarray([indices.get(key, -1) for key in values], dtype=np.int32)
                                           for values in assignments]))
    return result


def world_line_segments(scene, settings=None, intersections=None, prepared_edges=None, intersection_masks=None, style_passes=None, packed=False,prepared_intersections=None):
    """Return camera-selected world-space segments for rendering or VP2.

    Result contains ``segments``, ``warnings`` and ``intersection_diagnostics``.
    Each segment contains a/b XYZ lists, features, mesh_index, mesh name, and
    merged settings. No visibility/depth filtering occurs in this function.
    Pass precomputed ``find_intersections`` records as ``intersections`` to
    reuse camera-independent geometry work; [] disables intersection work.
    Default None computes intersections only when some line set enables them.
    """
    cfg = dict(DEFAULTS)
    cfg.update(settings or {})
    camera = _camera(scene.get("camera", {}), int(cfg["width"]), int(cfg["height"]))
    meshes = scene.get("meshes", [])
    from .packed_segments import PackedSegments
    segments, warnings, diagnostic = PackedSegments() if packed else [], [], {}
    passes = line_style_passes(scene, cfg) if style_passes is None else style_passes
    prepared_edges = (prepared_edges if prepared_edges is not None else
                      prepare_mesh_edges(meshes,cfg.get('edge_prepare_workers',1)))
    all_styles = [style for item in passes for style in item['styles']]
    triangle_outlines=None
    if cfg.get('triangle_outlines',False) and any(style.get('outline') for style in all_styles):
        from .cpu_outline import outline_edges
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max(1,min(4,len(meshes)))) as pool:
            triangle_outlines=list(pool.map(lambda pair:outline_edges(pair[0],camera,pair[1]),zip(meshes,prepared_edges)))
    if any(local.get("intersections") or local.get("self_intersections") for local in all_styles):
        if intersections is None:
            intersections = find_render_intersections(meshes, self_intersections=any(local.get("self_intersections") for local in all_styles),
                                               tolerance=cfg.get("intersection_tolerance", 1e-7), diagnostics=diagnostic,
                                               merge_segments=not any("line_passes" in m for m in meshes),triangle_masks=intersection_masks,
                                               prepared_output=prepared_intersections)
        warnings.append("Intersection lines use supplied triangles; coplanar overlaps and point-only contacts are omitted. Self mode excludes shared vertices and same-polygon pairs.")
    else:
        intersections = []
    for item in passes:
        styles, face_ids = item["styles"], item["face_style_ids"]
        for index, mesh in enumerate(meshes):
            prepared = prepared_edges[index]
            owners = face_ids[index][prepared["owners"]]
            sentinel = len(styles)
            edge_styles = np.minimum.reduceat(np.where(owners < 0, sentinel, owners), prepared["starts"])
            if "selected_edges" in item and any(len(pairs) for pairs in item['selected_edges'][index].values()):
                pair_indices = {tuple(pair): edge for edge, pair in enumerate(prepared["pairs"])}
                for style_id, pairs in item["selected_edges"][index].items():
                    for pair in pairs:
                        edge = pair_indices.get(tuple(sorted(pair)))
                        if edge is not None:
                            edge_styles[edge] = min(edge_styles[edge], style_id)
            diagonal_styles=None
            candidates=np.unique(edge_styles)
            if triangle_outlines is not None:
                mask,diagonal_pairs,diagonal_faces=triangle_outlines[index]
                diagonal_styles=face_ids[index][diagonal_faces]
                diagonal_styles=np.where(diagonal_styles<0,sentinel,diagonal_styles)
                candidates=np.union1d(candidates,np.unique(diagonal_styles))
            for style_id in candidates:
                if style_id == sentinel:
                    continue
                local = styles[style_id]
                classifier = prepared
                if "selected_edges" in item:
                    wanted = item["selected_edges"][index].get(int(style_id), [])
                    selected_mask=np.zeros(len(prepared['pairs']),dtype=bool)
                    if len(wanted):
                        wanted={tuple(sorted(pair)) for pair in wanted}
                        selected_mask=np.asarray([tuple(pair) in wanted for pair in prepared['pairs']])
                    classifier = dict(prepared, selected=selected_mask)
                if triangle_outlines is not None:
                    classifier=dict(classifier,outline_mask=mask)
                indices, flags = classify_edge_indices(classifier, camera, local)
                chosen=indices[edge_styles[indices] == style_id]
                if packed:
                    segments.add_edges(mesh,index,prepared,chosen,flags,local,item['line'])
                else:
                    for edge in chosen:
                        pair = prepared['pairs'][edge]
                        features = [name for bit, name in enumerate(EDGE_FEATURES) if int(flags[edge]) & (1 << bit)]
                        segments.append(dict(a=list(mesh['vertices'][pair[0]]), b=list(mesh['vertices'][pair[1]]),
                                             features=features, mesh_index=index, mesh=mesh.get('name', 'mesh'),
                                             settings=local, line=item['line']))
                if triangle_outlines is not None and local.get('outline'):
                    chosen=np.flatnonzero(diagonal_styles==style_id)
                    if packed:
                        segments.add_edges(mesh,index,dict(vertices=prepared['vertices'],pairs=diagonal_pairs),
                            chosen,np.full(len(diagonal_pairs),4,np.uint8),local,item['line'])
                    else:
                        for pair in diagonal_pairs[chosen]:
                            segments.append(dict(a=list(mesh['vertices'][pair[0]]),b=list(mesh['vertices'][pair[1]]),
                                features=['outline'],mesh_index=index,mesh=mesh.get('name','mesh'),settings=local,line=item['line']))
        for intersection in intersections:
            first, second = intersection["mesh_indices"]
            enabled = []
            feature = "self_intersections" if first == second else "intersections"
            for pair in intersection.get("triangle_pairs", []):
                for index, triangle in zip((first, second), pair):
                    mesh = meshes[index]
                    triangle_faces = mesh.get("triangle_faces")
                    if triangle_faces is None and mesh.get("triangles") is None:
                        triangle_faces = [face for face, vertices in enumerate(mesh.get("faces", []))
                                          for _ in range(len(vertices) - 2)]
                    face = triangle_faces[triangle] if triangle_faces is not None else triangle
                    style_id = int(face_ids[index][face])
                    if style_id >= 0 and styles[style_id].get(feature):
                        enabled.append((style_id, index))
            if not enabled:
                continue
            style_id, index = min(enabled)
            segments.append(dict(a=intersection["a"], b=intersection["b"], features=["intersection"],
                                 mesh_index=index, mesh=meshes[index].get("name", "mesh"),
                                 settings=styles[style_id], mesh_indices=intersection["mesh_indices"], line=item["line"]))
    return dict(segments=segments, warnings=warnings, intersection_diagnostics=diagnostic)


def _stroke(layer, a, b, width, color):
    """Rasterize one stroke's sampled capsules into its own premultiplied layer."""
    if width <= 0:
        return
    h, w = layer.shape[:2]
    radius = width / 2
    low = np.maximum(np.floor(np.minimum(a, b) - radius - 1), 0).astype(int)
    high = np.minimum(np.ceil(np.maximum(a, b) + radius + 1), [w - 1, h - 1]).astype(int)
    if np.any(high < low):
        return
    yy, xx = np.mgrid[low[1]:high[1] + 1, low[0]:high[0] + 1].astype(float)
    vx, vy = b - a
    denom = vx * vx + vy * vy
    t = np.clip(((xx + .5 - a[0]) * vx + (yy + .5 - a[1]) * vy) / max(denom, 1e-15), 0, 1)
    dist = np.hypot(xx + .5 - (a[0] + t * vx), yy + .5 - (a[1] + t * vy))
    alpha = np.clip(radius + .5 - dist, 0, 1)
    region = layer[low[1]:high[1] + 1, low[0]:high[0] + 1]
    # Max coverage avoids darkness artifacts where short sampled strokes overlap.
    mask = alpha > region[..., 3]
    region[..., :3][mask] = np.asarray(color) * alpha[mask, None]
    region[..., 3][mask] = alpha[mask]


def _over(destination, source):
    """Source-over premultiplied layers; later strokes win at opaque crossings."""
    destination[:] = source + destination * (1 - source[..., 3, None])


def _surface_depth_at(xy, depth, planes, camera):
    """Evaluate the winning surface at line samples, not pixel centres.

    The z-buffer is still a sampled visibility buffer; within its winning
    pixel, depth uses the triangle's exact affine z/reciprocal-z plane. This
    prevents sloped edges from spuriously hiding behind their own surfaces.
    """
    ix = np.clip(np.floor(xy[:, 0]).astype(int), 0, camera["width"] - 1)
    iy = np.clip(np.floor(xy[:, 1]).astype(int), 0, camera["height"] - 1)
    coeff = planes[iy, ix]
    values = coeff[:, 0] * xy[:, 0] + coeff[:, 1] * xy[:, 1] + coeff[:, 2]
    if not camera["ortho"]:
        values = np.divide(1., values, out=np.full_like(values, np.inf), where=values > 0)
    return np.where(np.isfinite(depth[iy, ix]), values, np.inf)


def _png(path, data):
    data = np.clip(np.rint(np.asarray(data) * 255), 0, 255).astype(np.uint8)
    h, w, channels = data.shape
    def chunk(kind, value):
        return struct.pack(">I", len(value)) + kind + value + struct.pack(">I", zlib.crc32(kind + value) & 0xffffffff)
    raw = b"".join(b"\x00" + row.tobytes() for row in data)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6 if channels == 4 else 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _down(image, scale):
    if scale == 1:
        return image
    h, w, c = image.shape
    return image.reshape(h // scale, scale, w // scale, scale, c).mean(axis=(1, 3))


def _straight(layer):
    result = layer.copy()
    result[..., :3] = np.divide(layer[..., :3], layer[..., 3, None],
                                out=np.zeros_like(layer[..., :3]), where=layer[..., 3, None] > 1e-9)
    return result


def _white_matte_rgba(layer):
    """Pencil-style main output: RGB on white, with separate coverage alpha.

    This is deliberately not straight alpha. The visible/hidden auxiliary
    passes retain straight-alpha RGB for compositors.
    """
    result=layer.copy()
    result[...,:3]+=1-layer[...,3,None]
    return result


def render(scene, output_prefix, settings=None):
    """Render scene to six image/vector passes and a JSON manifest.

    Edges and triangles are clipped against near/far planes. Perspective depth
    is reconstructed from reciprocal camera depth. Line visibility is sampled
    at subpixel intervals and split in the vector outputs accordingly.
    """
    started=time.perf_counter()
    cfg = dict(DEFAULTS)
    cfg.update(settings or {})
    line_only=bool(cfg.get('line_only',False))
    width, height, ss = int(cfg["width"]), int(cfg["height"]), int(cfg["supersample"])
    if not (1 <= width <= 4096 and 1 <= height <= 4096 and ss in (1, 2, 3, 4)):
        raise ValueError("Resolution must be 1..4096 and supersample 1..4")
    if width * height * ss * ss > 16_777_216:
        raise ValueError("Supersampled frame exceeds 16 megapixels; reduce resolution or supersample")
    w, h = width * ss, height * ss
    camera = _camera(scene.get("camera", {}), w, h)
    depth = np.full((h, w), np.inf, dtype=np.float64)
    depth_planes = np.zeros((h, w, 3), dtype=np.float64)
    mesh_owners = np.full((h, w), -1, dtype=np.int32) if scene.get("merge_groups") else None
    beauty = np.empty((h, w, 3), dtype=np.float32)
    beauty[:] = _color(cfg["background"])
    visible = np.zeros((h, w, 4), dtype=np.float32)
    hidden = np.zeros_like(visible)
    meshes = scene.get("meshes", [])
    stats = dict(meshes=len(meshes), triangles=0, classified_edges=0, visible_segments=0, hidden_segments=0,
                 width=width, height=height, supersample=ss)
    warnings = ["Reference renderer: partial Pencil snapshot import only; no native Pencil evaluation, texture sampling, cast shadows or PLD.",
                "Vector strokes use sampled visibility and widths; depth PNG maps camera near to white and far to black."]
    stroke_fn=_stroke
    stats['stroke_backend']='python-cpu-reference'
    if line_only and cfg.get('compiled_strokes',True):
        try:
            from .cpu_stroke import get_stroke
            stroke_fn=get_stroke()
            stats['stroke_backend']='numba-cpu-stroke'
        except RuntimeError as error:
            if 'accelerator unavailable' not in str(error):raise
            warnings.append(str(error)+'; using Python CPU stroke reference')
    from . import render_elements
    elements, element_results = [], []
    for record in scene.get("render_elements", []):
        element = dict(render_elements.validate({k: v for k, v in record.items() if k != "name"}), name=record.get("name", "element"))
        if not element["active"]:
            element_results.append(dict(name=element["name"], status="disabled"))
        elif element["kind"] == "pld" or element["output_element"] == "velocity":
            reason = "Proprietary PLD output is not implemented" if element["kind"] == "pld" else "Velocity requires temporal geometry samples and is not implemented"
            element_results.append(dict(name=element["name"], status="unsupported", reason=reason))
            warnings.append(element["name"] + ": " + reason)
        else:
            if len(elements) >= 32 or (len(elements) + 1) * h * w * 2 > 67_108_864:
                raise ValueError("Render element image budget exceeded; reduce active elements or resolution")
            elements.append((element, np.zeros((2, h, w, 4), dtype=np.float32) if element["kind"] == "line" else None))
    mesh_groups = np.full(len(meshes), -1, dtype=np.int32)
    for group in scene.get("merge_groups", []):
        mesh_groups[group["mesh_indices"]] = int(group["id"])
    group_image = None
    for mesh_index, mesh in enumerate(meshes):
        verts = np.asarray(mesh["vertices"], dtype=float)
        if verts.ndim != 2 or verts.shape[1] != 3 or not np.isfinite(verts).all():
            raise ValueError("Mesh vertices must be a finite Nx3 array")
        faces = mesh.get("faces", mesh.get("triangles", []))
        if isinstance(faces,np.ndarray):
            if faces.ndim!=2 or faces.shape[1]<3 or (faces.size and (faces.min()<0 or faces.max()>=len(verts))):
                raise ValueError("Polygon has invalid vertex indices")
        else:
            for face in faces:
                if len(face) < 3 or min(face) < 0 or max(face) >= len(verts):
                    raise ValueError("Polygon has invalid vertex indices")
        tris = mesh.get("triangles")
        tri_faces = mesh.get("triangle_faces")
        if tris is None:
            tris, tri_faces = [], []
            for index, face in enumerate(faces):
                for j in range(1, len(face) - 1):
                    tris.append([face[0], face[j], face[j + 1]])
                    tri_faces.append(index)
            warnings.append("Fan triangulation used for %s; supply Maya triangulation for concave polygons." % mesh.get("name", "mesh"))
        if tri_faces is None:
            if len(tris) != len(faces):
                raise ValueError("triangle_faces is required for triangulated polygon meshes")
            tri_faces = list(range(len(tris)))
        if len(tris) != len(tri_faces):
            raise ValueError("triangles and triangle_faces counts differ")
        mats = mesh.get("materials") or [{}]
        if any(material.get("ramp") for material in mats):
            warnings.append("Imported color ramps use RevToon's diffuse lighting and reference interpolation; exact original light/shadow response is not reproduced.")
        mids = mesh.get("material_ids", [0] * len(faces))
        if len(mids) != len(faces) or any(i < 0 or i >= len(mats) for i in mids):
            raise ValueError("material_ids must select one valid material for each face")
        normals = [] if line_only else [_face_normal(verts, face) for face in faces]
        colors = [] if line_only else [cel_color(n, mats[mid], scene.get("light", {})) for n, mid in zip(normals, mids)]
        if any(float(m.get("opacity", 1)) != 1 for m in mats):
            warnings.append("Transparent material rendered opaque: %s" % mesh.get("name", "mesh"))
        camverts = (verts - camera["eye"]) @ camera["basis"].T
        if line_only and cfg.get('compiled_depth',True):
            from .cpu_depth import rasterize_mesh
            face_indices=np.asarray(tri_faces,dtype=np.int64)
            if len(face_indices) and (face_indices.min()<0 or face_indices.max()>=len(faces)):
                raise ValueError('Invalid triangle_faces entry')
            try:
                raster=rasterize_mesh(camverts,tris,camera,depth,depth_planes,mesh_owners,mesh_index)
                stats['triangles']+=raster['triangles']
                stats['depth_backend']=raster['backend']
                continue
            except RuntimeError as error:
                if 'accelerator unavailable' not in str(error):raise
                warnings.append(str(error)+'; using Python CPU depth reference')
                stats['depth_backend']='python-cpu-reference'
        triangle_normals = None if line_only else mesh.get("triangle_normals")
        if triangle_normals is not None and len(triangle_normals) != len(tris):
            raise ValueError("triangle_normals must contain three normals for every triangle")
        if triangle_normals is None and not line_only:
            warnings.append("Per-polygon flat shading used without triangle_normals: %s" % mesh.get("name", "mesh"))
        for tri_index, (tri, fi) in enumerate(zip(tris, tri_faces)):
            if len(tri) != 3 or min(tri) < 0 or max(tri) >= len(verts) or not 0 <= fi < len(faces):
                raise ValueError("Invalid triangle or triangle_faces entry")
            points = camverts[tri]
            if triangle_normals is not None:
                supplied = np.asarray(triangle_normals[tri_index], dtype=float)
                if supplied.shape != (3, 3) or not np.isfinite(supplied).all():
                    raise ValueError("triangle_normals must be finite world-space 3x3 vectors")
                points = np.concatenate([points, supplied], axis=1)
            clipped = _clip_polygon(points, camera["near"], camera["far"])
            for j in range(1, len(clipped) - 1):
                polygon = np.asarray([clipped[0], clipped[j], clipped[j + 1]])
                _raster_triangle(polygon[:, :3], cfg['background'] if line_only else colors[fi], depth, beauty, camera,
                                 polygon[:, 3:] if triangle_normals is not None else None,
                                 mats[mids[fi]], scene.get("light", {}), depth_planes, mesh_owners, mesh_index)
                stats["triangles"] += 1
    depth_finished=time.perf_counter()
    if mesh_owners is not None:
        group_image = np.where(mesh_owners >= 0, mesh_groups[np.maximum(0, mesh_owners)], -1)
    vectors = []
    styles=line_style_passes(scene,cfg)
    all_styles=[s for item in styles for s in item['styles']]
    masks=None;cull_stats=None
    if (line_only and cfg.get('visibility_cull',True) and not elements and
        not any(s.get('hidden_lines',False) for s in all_styles) and
        all('triangles' in m and 'triangle_faces' in m for m in meshes)):
        try:
            from .cpu_triangle_visibility import visibility_masks
            max_width=max((max(0.,float(s['line_width']))*(1+np.clip(float(s.get('width_variation',0)),0,.95))*ss for s in all_styles),default=0.)
            bias=max((float(s['depth_bias']) for s in all_styles),default=0.)
            masks,cull_stats=visibility_masks(meshes,camera,depth,depth_planes,bias,max_width/2+1,float(cfg.get('intersection_tolerance',1e-7)))
            cull_stats['production_enabled']=True
        except ImportError as error:
            warnings.append('Triangle visibility accelerator unavailable: %s; using full intersection query' % error)
    refined=(line_only and cfg.get('exact_visibility',False) and cfg.get('compiled_segments',True)
             and not elements and group_image is None and
             not any(s.get('hidden_lines',False) or any(float(s.get(k,0))!=0 for k in
                 ('dash_length','distance_reduction','width_variation','taper')) for s in all_styles))
    prepared_intersections=[] if refined else None
    line_data = world_line_segments(scene, cfg,intersection_masks=masks,style_passes=styles,
                                   packed=line_only and cfg.get('compiled_segments',True),
                                   prepared_intersections=prepared_intersections)
    visibility=None
    if refined:
        try:
            from .cpu_visibility import prepare
            reuse=(prepared_intersections if prepared_intersections and
                   all(item['flat'] is not None or not len(item['positions']) for item in prepared_intersections) else None)
            visibility=prepare(meshes,prepared=reuse)['arguments']
        except ImportError as error:
            warnings.append('CPU ray visibility accelerator unavailable: %s; using sampled depth visibility' % error)
    del prepared_intersections
    if cull_stats:line_data['intersection_diagnostics']['visibility_culling']=cull_stats
    warnings.extend(line_data["warnings"])
    packed_lines=line_data['segments']
    stats['intersection_segments']=(packed_lines.intersection_count if hasattr(packed_lines,'intersection_count') else
                                   sum('intersection' in segment['features'] for segment in packed_lines))
    stats["intersection_diagnostics"] = line_data["intersection_diagnostics"]
    geometry_finished=time.perf_counter()
    remaining_segments=line_data['segments']
    if line_only and cfg.get('compiled_segments',True):
        try:
            from .cpu_segments import render_segments
            batch=render_segments(remaining_segments,camera,depth,depth_planes,visible,hidden,ss,group_image,elements,
                                  collect_vectors=cfg.get('auxiliary_outputs',True) or bool(elements),visibility=visibility)
        except ImportError as error:
            warnings.append('Compiled CPU segment accelerator unavailable: %s; using reference segment processing' % error)
            batch=None
        if batch is not None:
            vectors.extend(batch['vectors'])
            for name in ('visible_segments','hidden_segments','classified_edges'):stats[name]=batch[name]
            stats['segment_backend']=batch['backend']
            if visibility is not None:stats['visibility_refinement']=batch['visibility_refinement']
            remaining_segments=[]
    for edge_index, segment in enumerate(remaining_segments):
        mesh_index = segment["mesh_index"]
        local, kinds = segment["settings"], segment["features"]
        stats["classified_edges"] += 1
        points = (np.asarray([segment["a"], segment["b"]], dtype=float) - camera["eye"]) @ camera["basis"].T
        ends = _clip_segment(points[0], points[1], camera["near"], camera["far"])
        if ends is None:
            continue
        a, b = ends
        p, q = _project(np.array([a, b]), camera)
        maximum_width = max(0., float(local["line_width"])) * (1 + np.clip(float(local.get("width_variation", 0)), 0, .95)) * ss
        if maximum_width <= 0:
            continue
        margin = maximum_width / 2 + 1
        clipped = _screen_clip(p, q, w, h, margin)
        if clipped is None:
            continue
        lo, hi = clipped
        clipped_ends = np.array([p + lo * (q - p), p + hi * (q - p)])
        low = np.maximum(np.floor(clipped_ends.min(axis=0) - margin), 0).astype(int)
        high = np.minimum(np.ceil(clipped_ends.max(axis=0) + margin), [w, h]).astype(int)
        if np.any(high <= low):
            continue
        edge_visible = np.zeros((high[1] - low[1], high[0] - low[0], 4), dtype=np.float32)
        edge_hidden = np.zeros_like(edge_visible)
        element_strokes = [(element, layer, np.zeros((2,) + edge_visible.shape, dtype=np.float32)) for element, layer in elements
                           if layer is not None
                           and int(local.get("lineset_id", 1)) in element["lineset_ids"]]
        length = float(np.linalg.norm(q - p))
        count = max(1, int(math.ceil(length * (hi - lo) * 1.5)))
        ts = np.linspace(lo, hi, count + 1)
        mid = (ts[:-1] + ts[1:]) * .5
        xy = p[None, :] + mid[:, None] * (q - p)[None, :]
        if camera["ortho"]:
            z = a[2] + mid * (b[2] - a[2])
        else:
            z = 1 / ((1 - mid) / a[2] + mid / b[2])
        surface_z = _surface_depth_at(xy, depth, depth_planes, camera)
        front = z <= surface_z + float(local["depth_bias"]) * np.maximum(1., z)
        merged = np.zeros(len(mid), dtype=bool)
        if group_image is not None and local.get("merge_groups", True) and mesh_groups[mesh_index] >= 0 and set(kinds) & {"outline", "open"}:
            delta = q - p
            normal = np.array([-delta[1], delta[0]]) / max(np.linalg.norm(delta), 1e-12) * ss
            both = []
            for side in (-1, 1):
                sample = np.floor(xy + normal * side).astype(int)
                valid = (sample[:, 0] >= 0) & (sample[:, 0] < w) & (sample[:, 1] >= 0) & (sample[:, 1] < h)
                match = np.zeros(len(mid), dtype=bool)
                match[valid] = group_image[sample[valid, 1], sample[valid, 0]] == mesh_groups[mesh_index]
                both.append(match)
            merged = both[0] & both[1]
            stats["merge_suppressed_samples"] = stats.get("merge_suppressed_samples", 0) + int(np.count_nonzero(merged))
        rng = np.random.default_rng(int(local["seed"]) + mesh_index * 1000003 + edge_index)
        phase = rng.uniform(0, 2 * math.pi)
        records = []
        for k, is_visible in enumerate(front):
            sample_kinds = [feature for feature in kinds if not (merged[k] and feature in ("outline", "open"))]
            if not sample_kinds:
                continue
            if not is_visible and not local["hidden_lines"]:
                continue
            dash = float(local.get("dash_length", 0)) * ss
            if dash > 0 and int(mid[k] * length / dash) % 2:
                continue
            line_width = max(0., float(local["line_width"]))
            reduction = max(0., float(local.get("distance_reduction", 0)))
            line_width /= 1 + reduction * z[k]
            variation = np.clip(float(local.get("width_variation", 0)), 0, .95)
            line_width *= 1 + variation * math.sin(mid[k] * math.pi * 6 + phase)
            taper = np.clip(float(local.get("taper", 0)), 0, 1)
            line_width *= max(.05, 1 - taper * abs(2 * mid[k] - 1))
            if line_width <= 0:
                continue
            start, end = p + ts[k] * (q - p), p + ts[k + 1] * (q - p)
            color = _color(local["line_color"] if is_visible else local["hidden_color"])
            layer = edge_visible if is_visible else edge_hidden
            stroke_fn(layer, start - low, end - low, line_width * ss, color)
            for element, _, scratch in element_strokes:
                if render_elements.accepts(element, bool(is_visible), sample_kinds, local):
                    element_color = color
                    if element["output_element"] == "depth":
                        value = np.clip(1 - (z[k] - element["z_min"]) / (element["z_max"] - element["z_min"]), 0, 1)
                        element_color = [value] * 3
                    stroke_fn(scratch[int(is_visible)], start - low, end - low, line_width * ss, element_color)
            # Coalesce adjacent strokes with equal style to keep vector output compact.
            style = (bool(is_visible), round(line_width, 3), tuple(color), tuple(sample_kinds))
            if records and records[-1][0] == style and np.linalg.norm(records[-1][2] - start / ss) < 1e-6:
                records[-1][2] = end / ss
            else:
                records.append([style, start / ss, end / ss])
        # Accumulate a stroke's overlapping samples by maximum coverage,
        # then composite the complete stroke in draw order. Different
        # colored edges therefore agree with SVG/EPS painter ordering.
        if not local.get("output_to_elements_only", False):
            _over(visible[low[1]:high[1], low[0]:high[0]], edge_visible)
            _over(hidden[low[1]:high[1], low[0]:high[0]], edge_hidden)
        for _, layer, scratch in element_strokes:
            for visibility in (0, 1):
                _over(layer[visibility, low[1]:high[1], low[0]:high[0]], scratch[visibility])
        for (vis, size, color, features), start, end in records:
            vectors.append(dict(visible=vis, width=size, color=list(color), a=start.tolist(), b=end.tolist(),
                                mesh=segment["mesh"], features=list(features), settings=local))
            if not local.get("output_to_elements_only", False):
                stats["visible_segments" if vis else "hidden_segments"] += 1
    strokes_finished=time.perf_counter()
    if line_only:
        beauty=hidden.copy()
        _over(beauty,visible)
    else:
        # Hidden strokes are intentionally an x-ray overlay on the fill.
        beauty = hidden[..., :3] + beauty * (1 - hidden[..., 3, None])
        beauty = visible[..., :3] + beauty * (1 - visible[..., 3, None])
    auxiliary=cfg.get('auxiliary_outputs',True)
    prefix = Path(output_prefix).expanduser().resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    paths = {k: str(prefix.parent / (prefix.name + "_" + k + ext)) for k, ext in
             (("beauty", ".png"), ("visible", ".png"), ("hidden", ".png"), ("depth", ".png"),
              ("lines", ".svg"), ("eps", ".eps"), ("manifest", ".json")) if auxiliary or k in ('beauty','manifest')}
    _png(Path(paths["beauty"]), _white_matte_rgba(_down(beauty,ss)) if line_only else _down(beauty, ss))
    if auxiliary:
        depth_img = np.where(np.isfinite(depth), np.clip(1 - (depth - camera["near"]) / (camera["far"] - camera["near"]), 0, 1), 0)
        depth_img = np.repeat(depth_img[..., None], 3, axis=2)
        _png(Path(paths['visible']), _straight(_down(visible, ss)))
        _png(Path(paths['hidden']), _straight(_down(hidden, ss)))
        _png(Path(paths['depth']), _down(depth_img, ss))
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (width, height, width, height)]
    eps = ["%!PS-Adobe-3.0 EPSF-3.0", "%%%%BoundingBox: 0 0 %d %d" % (width, height), "1 setlinecap 1 setlinejoin"]
    # Raster composites the hidden pass before the visible pass; mirror that
    # ordering so a hidden stroke cannot obscure a visible one in vector tools.
    for vector in (sorted(vectors, key=lambda item: item['visible']) if auxiliary else ()):
        if vector["settings"].get("output_to_elements_only", False):
            continue
        a, b, color = vector["a"], vector["b"], vector["color"]
        rgb = tuple(int(round(c * 255)) for c in color)
        svg.append('<path d="M %.4f %.4f L %.4f %.4f" fill="none" stroke="rgb(%d,%d,%d)" stroke-width="%.3f" stroke-linecap="round" data-visibility="%s" data-features="%s"><title>%s</title></path>' %
                   (*a, *b, *rgb, vector["width"], "visible" if vector["visible"] else "hidden",
                    " ".join(vector["features"]), escape(vector["mesh"])))
        eps.append("%.6f %.6f %.6f setrgbcolor %.4f setlinewidth newpath %.4f %.4f moveto %.4f %.4f lineto stroke" %
                   (*color, vector["width"], a[0], height - a[1], b[0], height - b[1]))
    svg.append("</svg>")
    eps.extend(["showpage", "%%EOF"])
    if auxiliary:
        Path(paths['lines']).write_text('\n'.join(svg), encoding='utf-8')
        Path(paths['eps']).write_text('\n'.join(eps), encoding='ascii')
    for element, layer in elements:
        path = render_elements.output_path(element, prefix, scene.get("scene_name", ""))
        if layer is not None:
            _over(layer[0], layer[1])
            layer = layer[0]
            if element["bg_color_enable"]:
                layer[..., :3] += np.asarray(element["bg_color"]) * (1 - layer[..., 3, None])
                layer[..., 3] = 1
            _png(path, _straight(_down(layer, ss)))
        else:
            lines = ["%!PS-Adobe-3.0 EPSF-3.0", "%%%%BoundingBox: 0 0 %d %d" % (width, height), "1 setlinecap 1 setlinejoin"]
            for vector in sorted(vectors, key=lambda item: item["visible"]):
                if not render_elements.accepts(element, vector["visible"], vector["features"], vector["settings"]):
                    continue
                a, b = vector["a"], vector["b"]
                lines.append("%.6f %.6f %.6f setrgbcolor %.4f setlinewidth newpath %.4f %.4f moveto %.4f %.4f lineto stroke" %
                             (*vector["color"], vector["width"], a[0], height - a[1], b[0], height - b[1]))
            lines.extend(["showpage", "%%EOF"])
            path.write_text("\n".join(lines), encoding="ascii")
            if element["file_type"] == "ai_eps":
                warnings.append(element["name"] + ": standards-compliant EPS written; Illustrator-specific editable metadata is not implemented.")
        element_results.append(dict(name=element["name"], status="written", kind=element["kind"], path=str(path)))
    stats['output_mode']='lines_rgba' if line_only else 'shaded_rgb'
    if line_only:stats['rgb_encoding']='white_matte_with_coverage_alpha'
    stats['timings_seconds']=dict(depth=depth_finished-started,line_geometry=geometry_finished-depth_finished,
        strokes=strokes_finished-geometry_finished,output=time.perf_counter()-strokes_finished,total=time.perf_counter()-started)
    result = dict(paths=paths, stats=stats, warnings=list(dict.fromkeys(warnings)),
                  render_elements=element_results,
                  depth_range=dict(near=camera["near"], far=camera["far"], encoding="white-near, black-far/background"))
    Path(paths["manifest"]).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
