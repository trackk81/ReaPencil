"""Evaluate Maya's real Smooth Mesh geometry in memory, with provenance.

No DG nodes, history, selection, source UVs or source preview attributes change.
CPU uses render subdivision controls; viewport uses its displayed preview level.
"""
from maya import cmds
from maya.api import OpenMaya as om
import numpy as np
from . import legacy_smooth


def _source_face(values, face_count):
    """Decode a constant face ID stored in Maya's float32 UV channel.

    OpenSubdiv can round a constant 1762 to 1762.0001220703125 (one ULP).
    A fixed 1e-4 epsilon rejects valid large IDs. Allow a small float32 error,
    while still requiring every corner to identify the same original face.
    """
    values=np.asarray(values,dtype=np.float64)
    if not len(values) or not np.isfinite(values).all():
        raise ValueError('Non-finite or missing source-face provenance')
    original=int(np.rint(values[0]))
    tolerance=max(1e-6,min(.125,4*abs(float(np.spacing(np.float32(original))))))
    if (not 0<=original<face_count or np.any(np.rint(values)!=original)
            or np.any(np.abs(values-original)>tolerance)):
        raise ValueError('Mixed source-face provenance: '+repr(values.tolist()))
    return original


def level(path, enabled=True, purpose="render"):
    if purpose not in ("render", "viewport"):
        raise ValueError("Geometry purpose must be render or viewport")
    node = path.fullPathName()
    if not enabled or not cmds.getAttr(node + ".displaySmoothMesh"):
        return 0
    attr = "smoothLevel" if purpose == "viewport" or cmds.getAttr(node + ".useSmoothPreviewForRender") else "renderSmoothLevel"
    return max(0, int(cmds.getAttr(node + "." + attr)))


def _options(fn, divisions):
    options = fn.getSmoothMeshDisplayOptions()
    options.divisions = divisions
    # This changes UV interpolation only. Linear face-corner provenance remains
    # exact across subdivision boundaries; geometry uses Maya's native settings.
    options.smoothUVs = False
    return options


def _point_array(points):
    # MPointArray's generic NumPy sequence conversion probes every coordinate
    # through __getitem__. Direct component iteration avoids that overhead and
    # preserves all four doubles (including w) for the same matrix operation.
    return np.fromiter((c for p in points for c in (p.x,p.y,p.z,p.w)),
                       dtype=np.float64,count=len(points)*4).reshape(-1,4)


def _world(fn, path, as_arrays=False):
    matrix = np.asarray(path.inclusiveMatrix(),dtype=np.float64).reshape(4,4)
    points=_point_array(fn.getPoints(om.MSpace.kObject))
    result=(points@matrix)[:,:3]
    return np.ascontiguousarray(result) if as_arrays else result.tolist()


def world_points(path, enabled=True, purpose="viewport", as_arrays=False):
    """Fast animated-position update, with the same vertex order as evaluate."""
    fn = om.MFnMesh(path)
    divisions = level(path, enabled, purpose)
    if not divisions:
        points=fn.getPoints(om.MSpace.kWorld)
        return np.ascontiguousarray(_point_array(points)[:,:3]) if as_arrays else [[p.x,p.y,p.z] for p in points]
    if legacy_smooth.required(fn, purpose):
        input_owner = om.MFnMeshData().create()
        om.MFnMesh().copy(fn.object(), input_owner)
        smooth, owner = legacy_smooth.generate(fn, input_owner, divisions)
        return _world(smooth, path,as_arrays)
    parent = om.MFnMeshData().create()
    smooth = om.MFnMesh(fn.generateSmoothMesh(parent, _options(fn, divisions)))
    return _world(smooth, path,as_arrays)


def evaluate(path, enabled=True, purpose="render", need_edge_provenance=True, as_arrays=False):
    """Return fn/owners/world_points/level and exact source face/edge mappings.

    Keep the result alive while using fn: owners retains mesh-data lifetimes.
    base_edge_children maps 'sourceVertex0,sourceVertex1' to child vertex pairs.
    Set need_edge_provenance=False only when no selected-edge mapping is needed;
    subdivision geometry, source face/material provenance and vertex order stay exact.
    as_arrays retains numeric topology/points internally; callers serializing
    the result must explicitly encode NumPy arrays. Defaults retain list API.
    """
    source = om.MFnMesh(path)
    divisions = level(path, enabled, purpose)
    base_counts, base_indices = source.getVertices()
    base_faces, offset = [], 0
    for count in base_counts:
        base_faces.append(list(base_indices[offset:offset + count]))
        offset += count
    result = dict(fn=source, owners=[], level=divisions, base_face_ids=np.arange(source.numPolygons) if as_arrays else list(range(source.numPolygons)),
                  base_edge_children={}, base_face_count=source.numPolygons,
                  base_vertex_count=source.numVertices, base_edge_count=source.numEdges,faces=base_faces,edge_provenance=bool(need_edge_provenance))
    if not divisions:
        points=source.getPoints(om.MSpace.kWorld)
        result["world_points"] = np.ascontiguousarray(_point_array(points)[:,:3]) if as_arrays else [[p.x,p.y,p.z] for p in points]
        if as_arrays and len(base_counts) and all(count==base_counts[0] for count in base_counts):
            result['faces']=np.asarray(base_indices,dtype=np.int64).reshape(-1,base_counts[0])
        return result
    expected_faces = sum(base_counts) * 4 ** (divisions - 1)
    if expected_faces > 2_000_000:
        raise ValueError("%s: requested smooth level %d produces %d faces; reduce the authored smooth level (no geometry was approximated)" %
                         (path.fullPathName(), divisions, expected_faces))
    copy_owner = om.MFnMeshData().create()
    copy = om.MFnMesh(om.MFnMesh().copy(source.object(), copy_owner))
    uv_sets = copy.getUVSetNames()
    if not uv_sets:
        raise ValueError("%s: no UV set available for exact subdivision provenance" % path.fullPathName())
    uv_set = uv_sets[0]
    copy.clearUVs(uv_set)
    u, v = [], []
    for face, count in enumerate(base_counts):
        u.extend([float(face)] * count)
        v.extend(float(corner) for corner in range(count))
    copy.setUVs(u, v, uv_set)
    copy.assignUVs(base_counts, list(range(len(u))), uv_set)
    if legacy_smooth.required(source, purpose):
        fn, smooth_owner = legacy_smooth.generate(source, copy_owner, divisions)
    else:
        smooth_owner = om.MFnMeshData().create()
        fn = om.MFnMesh(copy.generateSmoothMesh(smooth_owner, _options(source, divisions)))
    counts, indices = fn.getVertices()
    uv_counts, uv_indices = fn.getAssignedUVs(uv_set)
    us, vs = fn.getUVs(uv_set)
    if list(counts) != list(uv_counts):
        raise ValueError("Maya subdivision did not preserve exact face provenance")
    # Validate all corners as arrays instead of allocating NumPy arrays and
    # dispatching several scalar operations for every subdivided face.
    lengths=np.asarray(counts,dtype=np.int64)
    starts=np.cumsum(lengths)-lengths
    corner_u=np.asarray(us,dtype=np.float64)[np.asarray(uv_indices,dtype=np.int64)]
    rounded=np.rint(corner_u)
    origins=rounded[starts]
    expected=np.repeat(origins,lengths)
    tolerances=np.maximum(1e-6,np.minimum(.125,4*np.abs(np.spacing(expected.astype(np.float32)))))
    invalid=(~np.isfinite(corner_u))|(expected<0)|(expected>=len(base_faces))|(rounded!=expected)|(np.abs(corner_u-expected)>tolerances)
    if np.any(invalid):
        bad=int(np.searchsorted(starts,int(np.flatnonzero(invalid)[0]),side='right')-1)
        raise ValueError('%s: child face %d: Mixed source-face provenance' % (path.fullPathName(),bad))
    decoded=origins.astype(np.int64)
    if not as_arrays:decoded=decoded.tolist()
    flat=np.asarray(indices,dtype=np.int64)
    uniform=bool(len(lengths) and np.all(lengths==lengths[0]))
    faces=(flat.reshape(-1,int(lengths[0])) if uniform
           else [flat[start:start+count].tolist() for start,count in zip(starts,lengths)])
    if uniform and not as_arrays:faces=faces.tolist()
    provenance=decoded
    descendants = {}
    if need_edge_provenance:
        following=np.arange(len(flat))+1
        following[np.cumsum(lengths)-1]=starts
        lower=np.minimum(flat,flat[following]);upper=np.maximum(flat,flat[following])
        keys=lower.astype(np.uint64)*np.uint64(fn.numVertices)+upper.astype(np.uint64)
        _,first,inverse,edge_counts=np.unique(keys,return_index=True,return_inverse=True,return_counts=True)
        grouped=np.argsort(inverse,kind='stable')
        edge_starts=np.cumsum(edge_counts)-edge_counts
        owners=np.repeat(np.asarray(provenance,dtype=np.int64),lengths)
        grouped_owners=owners[grouped]
        interior=(edge_counts>1)&(np.minimum.reduceat(grouped_owners,edge_starts)==np.maximum.reduceat(grouped_owners,edge_starts))
        # Preserve the original traversal/insertion order for selected-edge output.
        corners=np.sort(first[~interior])
        corner_v=np.asarray(vs,dtype=np.float64)[np.asarray(uv_indices,dtype=np.int64)]
        source_ids=owners[corners]
        source_lengths=np.asarray(base_counts,dtype=np.int64)[source_ids]
        a=corner_v[corners];b=corner_v[following[corners]]
        source_corners=np.where(b<a,source_lengths-1,np.floor((a+b)*.5+1e-6)).astype(np.int64)
        if np.any((source_corners<0)|(source_corners>=source_lengths)):
            raise ValueError('Maya subdivision edge provenance is invalid')
        descendants = {}
        for corner,source_id,source_corner in zip(corners,source_ids,source_corners):
            original_face = base_faces[source_id]
            source_pair = sorted((original_face[source_corner], original_face[(source_corner + 1) % len(original_face)]))
            key = "%d,%d" % tuple(source_pair)
            descendants.setdefault(key, []).append([int(lower[corner]),int(upper[corner])])
    result.update(fn=fn, owners=[copy_owner, smooth_owner], base_face_ids=provenance,
                  base_edge_children=descendants, world_points=_world(fn, path,as_arrays),faces=faces)
    return result


def remap_passes(mesh, passes):
    """Expand source polygon and explicit-edge styles to the smooth topology."""
    if not mesh.get("smooth_level") and not mesh.get('alpha_boundary'):
        return passes
    mapping = mesh["base_face_ids"]
    edges = mesh["base_edge_children"]
    result = []
    for item in passes:
        selected = {}
        for style, pairs in item.get("selected_edges", {}).items():
            selected[style] = [child for pair in pairs for child in edges.get("%d,%d" % tuple(sorted(pair)), [])]
        values=item["face_line_sets"]
        expanded=([values[0]]*len(mapping) if values and len(set(values))==1 else [values[source] for source in mapping])
        result.append(dict(item,face_line_sets=expanded,selected_edges=selected))
    return result


def remap_edges(mesh, pairs):
    if not mesh.get("smooth_level") and not mesh.get('alpha_boundary'):
        return pairs
    return [child for pair in pairs for child in mesh["base_edge_children"].get("%d,%d" % tuple(sorted(pair)), [])]
