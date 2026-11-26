"""UV provenance for CPU brush maps, allocated only for enabled maps.

Mesh edges use the lowest adjacent polygon index at UV seams. Intersections
use the owning triangle selected by the line-set resolver. These deterministic
rules avoid seams changing when camera motion changes edge classification.
"""
import numpy as np


def active(style):
    return any(isinstance(value, dict) and value.get('enabled', True)
               and float(value.get('amount', 1.)) > 0.
               for value in style.get('brush_maps', {}).values())


def iter_styles(styles):
    """Accept raw settings, resolved brush channels, or a sequence of styles."""
    if isinstance(styles, dict):
        yield styles
        for value in styles.get('feature_brushes', {}).values():
            yield from iter_styles(value)
        if styles.get('hidden_style'):
            yield from iter_styles(styles['hidden_style'])
        for channel in styles.get('_brush_channels', ()):
            yield from iter_styles(channel['settings'])
            for value in channel.get('brushes', {}).values():
                yield from iter_styles(value)
    else:
        for value in styles:
            yield from iter_styles(value)


def any_active(styles):
    return any(active(style) for style in iter_styles(styles))


def uv_sets(styles):
    return sorted({str(value.get('uv_set', ''))
                   for style in iter_styles(styles)
                   for value in style.get('brush_maps', {}).values()
                   if isinstance(value, dict) and value.get('enabled', True)
                   and float(value.get('amount', 1.)) > 0.})


def _error(mesh, message):
    return ValueError('Brush map UVs: '+message+' ('+str(mesh.get('name', 'mesh'))+')')


def build_uv_lookup(mesh, counts, vertices, uv_counts, uv_ids, coordinates):
    """Build compact polygon/vertex UV keys; pure NumPy for testability."""
    counts = np.asarray(counts, np.int64)
    vertices = np.asarray(vertices, np.int64)
    uc = np.asarray(uv_counts, np.int64)
    ui = np.asarray(uv_ids, np.int64)
    coords = np.asarray(coordinates, np.float64).reshape(-1, 2)
    if counts.shape != uc.shape or counts.sum() != len(vertices) or uc.sum() != len(ui):
        raise _error(mesh, 'UV topology differs from evaluated mesh')
    valid_faces = (counts == uc) & (uc > 0)
    face_ids = np.repeat(np.arange(len(counts)), counts)
    keep = valid_faces[face_ids]
    values = ui[valid_faces[np.repeat(np.arange(len(uc)), uc)]]
    keys = face_ids[keep] * len(mesh['vertices']) + vertices[keep]
    valid_ids = (values >= 0) & (values < len(coords))
    keys, values = keys[valid_ids], values[valid_ids]
    order = np.argsort(keys, kind='stable')
    keys, values = keys[order], values[order]
    triangles = np.asarray(mesh['triangles'], np.int64).reshape(-1, 3)
    faces = np.asarray(mesh['triangle_faces'], np.int64)
    queries = faces[:, None] * len(mesh['vertices']) + triangles
    triangle_uv, good = lookup_uv(keys, values, coords, queries)
    good = np.all(good, axis=1)
    return dict(keys=keys, ids=values, coordinates=coords,
                triangle_uv=triangle_uv, triangle_valid=good)


def lookup_uv(keys, ids, coordinates, queries):
    """Missing UVs remain NaN and are rejected only when a mapped line uses them."""
    queries = np.asarray(queries, np.int64)
    positions = np.searchsorted(keys, queries)
    good = positions < len(keys)
    if len(keys):
        good[good] &= keys[positions[good]] == queries[good]
    result = np.full(queries.shape+(2,), np.nan, np.float64)
    result[good] = coordinates[ids[positions[good]]]
    good &= np.isfinite(result).all(axis=-1)
    return result, good


def export_uv_sets(mesh, path, evaluated, styles):
    """Read UVs of the same smooth-mesh evaluation used by the CPU renderer."""
    wanted = uv_sets(styles)
    if not wanted:
        return
    from .alpha_boundary import _texture_fn
    fn, owner = _texture_fn(path, evaluated)
    if fn.numVertices != len(mesh['vertices']) or fn.numPolygons != len(mesh['faces']):
        raise _error(mesh, 'UV topology differs from evaluated mesh')
    counts, vertices = fn.getVertices()
    available = set(fn.getUVSetNames())
    current = fn.currentUVSetName()
    cache = {}
    exported = {}
    for alias in wanted:
        name = alias or current
        if name not in available:
            raise _error(mesh, 'UV set is missing: '+repr(name))
        if name not in cache:
            uv_counts, uv_ids = fn.getAssignedUVs(name)
            coordinates = np.column_stack(fn.getUVs(name))
            cache[name] = build_uv_lookup(mesh, counts, vertices, uv_counts, uv_ids, coordinates)
        exported[alias] = cache[name]
    mesh['_brush_map_uvs'] = exported


def _data(mesh, uv_set):
    data = mesh.get('_brush_map_uvs', {}).get(uv_set)
    if data is None:
        raise _error(mesh, 'UV set was not exported: '+repr(uv_set))
    return data


def edge_uv(mesh, prepared, indices, style):
    """Choose a stable incident face independently for each classified edge."""
    wanted = uv_sets(style)
    if not wanted:
        return {}
    indices = np.asarray(indices, np.int64)
    starts = np.asarray(prepared['starts'], np.int64)
    owners = np.asarray(prepared['owners'], np.int64)
    counts = np.asarray(prepared['counts'], np.int64)
    if np.any(counts[indices] <= 0):
        raise _error(mesh, 'edge has no incident polygon')
    # The native edge cache need not preserve polygon ordering within each edge.
    faces = np.minimum.reduceat(owners, starts)[indices]
    pairs = np.asarray(prepared['pairs'], np.int64)[indices]
    queries = faces[:, None] * len(mesh['vertices']) + pairs
    result = {}
    for name in wanted:
        data = _data(mesh, name)
        uv, good = lookup_uv(data['keys'], data['ids'], data['coordinates'], queries)
        if not good.all():
            row = int(np.flatnonzero(~np.all(good, axis=1))[0])
            raise _error(mesh, 'missing or invalid UVs on polygon '+str(int(faces[row]))+
                         ', UV set '+repr(name))
        result[name] = uv
    return result


def intersection_uv(mesh, points, triangle_ids, style):
    """Interpolate map UVs on one owner triangle without a world-space search."""
    wanted = uv_sets(style)
    if not wanted:
        return {}
    points = np.asarray(points, np.float64).reshape(-1, 2, 3)
    triangle_ids = np.asarray(triangle_ids, np.int64)
    triangles = np.asarray(mesh['triangles'], np.int64)
    if np.any(triangle_ids < 0) or np.any(triangle_ids >= len(triangles)):
        raise _error(mesh, 'intersection has an invalid owner triangle')
    vertices = np.asarray(mesh['vertices'], np.float64)[triangles[triangle_ids]]
    e0 = vertices[:, 1]-vertices[:, 0]
    e1 = vertices[:, 2]-vertices[:, 0]
    d00 = np.einsum('ij,ij->i', e0, e0)
    d01 = np.einsum('ij,ij->i', e0, e1)
    d11 = np.einsum('ij,ij->i', e1, e1)
    denominator = d00*d11-d01*d01
    if np.any(denominator <= np.maximum(d00*d11, 1e-300)*1e-14):
        raise _error(mesh, 'intersection owner triangle is degenerate')
    delta = points-vertices[:, :1]
    d20 = np.einsum('ikj,ij->ik', delta, e0)
    d21 = np.einsum('ikj,ij->ik', delta, e1)
    b1 = (d11[:, None]*d20-d01[:, None]*d21)/denominator[:, None]
    b2 = (d00[:, None]*d21-d01[:, None]*d20)/denominator[:, None]
    result = {}
    for name in wanted:
        data = _data(mesh, name)
        if not data['triangle_valid'][triangle_ids].all():
            raise _error(mesh, 'missing or invalid UVs on intersection owner, UV set '+repr(name))
        uv = data['triangle_uv'][triangle_ids]
        result[name] = (uv[:, :1]+b1[..., None]*(uv[:, 1:2]-uv[:, :1])+
                        b2[..., None]*(uv[:, 2:3]-uv[:, :1]))
    return result
