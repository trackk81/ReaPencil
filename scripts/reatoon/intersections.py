"""World-space noncoplanar triangle intersections, independent of Maya.

The BVH broad phase prunes disjoint triangle boxes. Coplanar overlaps and
zero-length point contacts intentionally produce no line. Shared edges of
different meshes can produce a line; self intersections exclude triangles
sharing any vertex index or originating from the same source polygon.

This detects intersections of supplied tessellation, not subdivision limit
surfaces. All input vertices must already be transformed into world space.
"""
from __future__ import annotations

import time
import os
import hashlib
import threading
from collections import OrderedDict
from collections import deque
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from .robust_predicates import strictly_separated, orient3d_value


class IntersectionBatches:
    """Ordered native rows; legacy callers can still iterate exact records."""
    def __init__(self):self.batches=[];self.count=0;self._pending=[];self._pair=None
    def add(self,i,j,rows):
        if len(rows):self.batches.append((i,j,rows));self.count+=len(rows)
    def append_record(self,i,j,segment,ti,tj):
        # Keep scalar fallback compact too, with bounded Python scratch.
        if self._pair!=(i,j):self.flush();self._pair=(i,j)
        self._pending.append([*segment[0],*segment[1],ti,tj]);self.count+=1
        if len(self._pending)>=4096:self.flush()
    def flush(self):
        if self._pending:
            self.batches.append((*self._pair,np.asarray(self._pending,np.float64)))
            self._pending=[]
    def __len__(self):return self.count
    def __iter__(self):
        self.flush()
        for i,j,rows in self.batches:
            for row in rows:
                yield dict(a=row[:3],b=row[3:6],mesh_indices=[i,j],
                           triangle_pairs=[[int(row[6]),int(row[7])]],features=['intersection'])


_QUERY_CACHE=OrderedDict()
_QUERY_LOCK=threading.Lock()
_QUERY_BYTES=0
_QUERY_LIMIT=128*1024*1024


def clear_query_cache():
    global _QUERY_BYTES
    with _QUERY_LOCK:_QUERY_CACHE.clear();_QUERY_BYTES=0


def _query_cached(key,compute):
    global _QUERY_BYTES
    if key is None:return compute()
    with _QUERY_LOCK:
        found=_QUERY_CACHE.get(key)
        if found is not None:_QUERY_CACHE.move_to_end(key);return found
    result=compute()
    size=result[0].nbytes+result[1].nbytes+256
    if result[2] or size>_QUERY_LIMIT:return result
    with _QUERY_LOCK:
        if key not in _QUERY_CACHE:
            _QUERY_CACHE[key]=result;_QUERY_BYTES+=size
        while _QUERY_BYTES>_QUERY_LIMIT:
            _,old=_QUERY_CACHE.popitem(last=False);_QUERY_BYTES-=old[0].nbytes+old[1].nbytes+256
    return result


class IntersectionLimitError(RuntimeError):
    """Explicit budget failure; partial intersections are never returned."""


def find_render_intersections(meshes, diagnostics=None, **kwargs):
    """Retry complete CPU queries when output fills, within a bounded budget.

    Keep the explicit limits of find_intersections unchanged for its callers.
    Packed rows contain eight float64 values, versus a conservative 1 KiB
    per dictionary record. Both retain the existing 512 MiB record budget.
    Candidate work is bounded separately.
    """
    # This is a work guard, not a preallocated array. Scale its starting value
    # with supplied geometry to avoid repeating a completed large-scene query.
    triangle_count=sum(len(mesh.get('triangles',mesh.get('faces',[]))) for mesh in meshes)
    packed=kwargs.get('array_output',False) and not kwargs.get('merge_segments',True)
    record_bytes=8*np.dtype(np.float64).itemsize if packed else 1024
    maximum_segments=(512*1024*1024)//record_bytes
    segment_limit=min(maximum_segments,max(200_000,triangle_count//8))
    # As with packed output, this is a work counter, not allocated storage.
    # A city with millions of triangles otherwise completes almost all queries
    # before restarting at the small-scene default. Keep the same final guard.
    candidate_limit=min(32_000_000,max(2_000_000,triangle_count))
    retries=0
    while True:
        attempt={}
        try:
            result=find_intersections(meshes,max_segments=segment_limit,
                max_candidates=candidate_limit,diagnostics=attempt,**kwargs)
            attempt['budget_retries']=retries
            attempt['segment_capacity']=segment_limit
            attempt['record_bytes']=record_bytes
            attempt['record_budget_bytes']=512*1024*1024
            attempt['record_storage_bytes']=len(result)*record_bytes
            if diagnostics is not None:diagnostics.update(attempt)
            return result
        except IntersectionLimitError as error:
            if 'segment' in str(error).lower() and segment_limit<maximum_segments:
                segment_limit=min(maximum_segments,segment_limit*2)
            elif 'candidate' in str(error).lower() and candidate_limit<32_000_000:
                candidate_limit*=2
            else:
                if diagnostics is not None:diagnostics.update(attempt)
                raise
            retries+=1


class _Node:
    __slots__ = ("low", "high", "left", "right", "indices", "lows", "highs")

    def __init__(self, lows, highs, indices, leaf_size=8):
        self.low = lows[indices].min(axis=0)
        self.high = highs[indices].max(axis=0)
        self.left = self.right = None
        self.indices = None
        self.lows = self.highs = None
        if len(indices) <= leaf_size:
            self.indices = indices
            self.lows, self.highs = lows[indices], highs[indices]
        else:
            centers = (lows[indices] + highs[indices]) * .5
            axis = int(np.argmax(np.ptp(centers, axis=0)))
            order = indices[np.argsort(centers[:, axis], kind="stable")]
            middle = len(order) // 2
            self.left = _Node(lows, highs, order[:middle], leaf_size)
            self.right = _Node(lows, highs, order[middle:], leaf_size)


def _overlap(a_low, a_high, b_low, b_high, eps):
    return bool(np.all(a_low <= b_high + eps) and np.all(b_low <= a_high + eps))


def _leaf_pairs(left, right, eps, same=False):
    overlap = (np.all(left.lows[:, None, :] <= right.highs[None, :, :] + eps, axis=2)
               & np.all(right.lows[None, :, :] <= left.highs[:, None, :] + eps, axis=2))
    if same:
        overlap &= np.triu(np.ones(overlap.shape, dtype=bool), k=1)
    rows, cols = np.nonzero(overlap)
    for row, col in zip(rows, cols):
        yield int(left.indices[row]), int(right.indices[col])


def _pairs(left, right, eps, self_pair=False):
    if not _overlap(left.low, left.high, right.low, right.high, eps):
        return
    if self_pair and left is right:
        if left.indices is not None:
            yield from _leaf_pairs(left, right, eps, True)
        else:
            yield from _pairs(left.left, left.left, eps, True)
            yield from _pairs(left.left, left.right, eps, False)
            yield from _pairs(left.right, left.right, eps, True)
        return
    if left.indices is not None and right.indices is not None:
        yield from _leaf_pairs(left, right, eps)
    elif right.indices is not None or (left.indices is None and np.max(left.high - left.low) >= np.max(right.high - right.low)):
        yield from _pairs(left.left, right, eps)
        yield from _pairs(left.right, right, eps)
    else:
        yield from _pairs(left, right.left, eps)
        yield from _pairs(left, right.right, eps)


def _section(triangle, distances, eps):
    points = []
    for i in range(3):
        a, b = triangle[i], triangle[(i + 1) % 3]
        da, db = distances[i], distances[(i + 1) % 3]
        if da == 0:
            points.append(a)
        # Exact plane signs preserve crossings closer than the contact tolerance.
        if (da < 0 and db > 0) or (da > 0 and db < 0):
            points.append(a + (b - a) * (da / (da - db)))
    unique = []
    for point in points:
        if not any(np.linalg.norm(point - other) <= eps for other in unique):
            unique.append(point)
    return unique


def triangle_intersection(first, second, tolerance=1e-7):
    """Return (endpoint array or None, classification).

    Classifications: segment, disjoint, point-contact, coplanar, degenerate.
    A noncoplanar shared edge counts as a segment. Endpoint-only contact does
    not count as a line. The absolute tolerance is measured in scene units.
    """
    a, b = np.asarray(first, float), np.asarray(second, float)
    if a.shape != (3, 3) or b.shape != (3, 3) or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("Triangles must contain three finite XYZ points")
    eps = float(tolerance)
    if not np.isfinite(eps) or eps <= 0:
        raise ValueError("Intersection tolerance must be finite and positive")
    na, nb = np.cross(a[1] - a[0], a[2] - a[0]), np.cross(b[1] - b[0], b[2] - b[0])
    la, lb = np.linalg.norm(na), np.linalg.norm(nb)
    ea = max(np.linalg.norm(a[1] - a[0]), np.linalg.norm(a[2] - a[0]), np.linalg.norm(a[2] - a[1]))
    eb = max(np.linalg.norm(b[1] - b[0]), np.linalg.norm(b[2] - b[0]), np.linalg.norm(b[2] - b[1]))
    if la <= eps * max(ea, eps) or lb <= eps * max(eb, eps):
        return None, "degenerate"
    na, nb = na / la, nb / lb
    da = (a - b[0]) @ nb
    db = (b - a[0]) @ na
    if np.all(da > eps) or np.all(da < -eps) or np.all(db > eps) or np.all(db < -eps):
        return None, "disjoint"
    direction = np.cross(na, nb)
    length = np.linalg.norm(direction)
    if length <= 1e-12:
        return None, "coplanar" if np.max(np.abs(da)) <= eps and np.max(np.abs(db)) <= eps else "disjoint"
    if np.max(np.abs(da)) <= eps and np.max(np.abs(db)) <= eps:
        return None, "coplanar"
    if strictly_separated(a,b):
        return None, "disjoint"
    da = np.array([orient3d_value(p,b[1],b[2],b[0]) for p in a])
    db = np.array([orient3d_value(p,a[1],a[2],a[0]) for p in b])
    direction /= length
    pa, pb = _section(a, da, eps), _section(b, db, eps)
    if not pa or not pb:
        return None, "disjoint"
    origin = pa[0]
    ia = [float(np.dot(p - origin, direction)) for p in pa]
    ib = [float(np.dot(p - origin, direction)) for p in pb]
    low, high = max(min(ia), min(ib)), min(max(ia), max(ib))
    if high < low - eps:
        return None, "disjoint"
    if high - low <= eps:
        return None, "point-contact"
    return np.array([origin + low * direction, origin + high * direction]), "segment"


def _prepare(mesh, native_bvh=False):
    cache=mesh.get('_render_geometry') if native_bvh else None
    if cache is not None and '_bvh' in cache:return dict(cache['_bvh'])
    vertices = np.asarray(mesh.get("vertices", []), dtype=float)
    if vertices.size == 0:
        vertices = np.empty((0, 3))
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
        raise ValueError("Mesh vertices must be finite world-space Nx3 coordinates")
    triangles = mesh.get("triangles")
    faces = mesh.get("faces", [])
    owners = mesh.get("triangle_faces")
    if triangles is None:
        triangles, owners = [], []
        for fi, face in enumerate(faces):
            for j in range(1, len(face) - 1):
                triangles.append([face[0], face[j], face[j + 1]])
                owners.append(fi)
    indices = np.asarray(triangles, dtype=np.int64)
    if indices.size == 0:
        indices = np.empty((0, 3), dtype=np.int64)
    if indices.ndim != 2 or indices.shape[1] != 3 or (len(indices) and (indices.min() < 0 or indices.max() >= len(vertices))):
        raise ValueError("Triangle indices are invalid")
    if owners is not None and len(owners) != len(indices):
        raise ValueError("triangle_faces count must match triangles")
    from . import native_cpu
    facts=native_cpu.facts(vertices,indices) if native_bvh else None
    if facts is not None:positions,lows,highs,normals,areas,longest=facts
    else:
        positions = vertices[indices]
        lows = positions.min(axis=1) if len(indices) else np.empty((0, 3))
        highs = positions.max(axis=1) if len(indices) else np.empty((0, 3))
        cross = np.cross(positions[:, 1] - positions[:, 0], positions[:, 2] - positions[:, 0])
        areas = np.linalg.norm(cross, axis=1)
        normals = np.divide(cross, areas[:, None], out=np.zeros_like(cross), where=areas[:, None] > 0)
        longest = np.max(np.stack([np.linalg.norm(positions[:, 1] - positions[:, 0], axis=1),
                                  np.linalg.norm(positions[:, 2] - positions[:, 0], axis=1),
                                  np.linalg.norm(positions[:, 2] - positions[:, 1], axis=1)]), axis=0)
    flat=None
    if len(indices) and native_bvh:
        from types import SimpleNamespace
        flat=native_cpu.bvh(lows,highs)
        if flat is None:
            from ._bvh_kernel import build
            flat=build(lows,highs)
        root=SimpleNamespace(low=flat[0][0],high=flat[1][0])
    else:
        root=_Node(lows,highs,np.arange(len(indices)),leaf_size=16) if len(indices) else None
    result=dict(vertices=vertices, indices=indices, positions=positions, lows=lows, highs=highs,
                owners=owners, normals=normals, areas=areas, longest=longest,
                root=root,flat=flat)
    if cache is not None:
        result['cache_token']=object()
        cache['_bvh']=result
    return dict(result)


def _flat_bvh(root):
    nodes, order, ranges, children = [], [], [], []
    def visit(node):
        index = len(nodes)
        nodes.append(node)
        ranges.append([-1, -1])
        children.append([-1, -1])
        if node.indices is not None:
            ranges[index] = [len(order), len(order) + len(node.indices)]
            order.extend(node.indices)
        else:
            left = visit(node.left)
            right = visit(node.right)
            children[index] = [left, right]
        return index
    visit(root)
    return (np.asarray([n.low for n in nodes]), np.asarray([n.high for n in nodes]),
            np.asarray(children, dtype=np.int64), np.asarray(ranges, dtype=np.int64), np.asarray(order, dtype=np.int64))


def _native_function(backend):
    if backend == "python":
        return None, None
    if backend=='auto':
        from .native_cpu import library,query
        if library() is not None:return query,None
    try:
        from .accelerator import enable
        enable()
        from ._intersection_kernel import traverse
        return traverse, None
    except (ImportError, OSError, RuntimeError, AttributeError) as error:
        if backend == "numba":
            raise RuntimeError("Numba accelerator unavailable: %s" % error) from error
        return None, str(error)


def _merge_segments(records, eps):
    # Group by approximately equal direction, then explicitly verify distance
    # from a common line. The latter prevents merging nearby parallel lines.
    groups = {}
    for record in records:
        a, b = np.asarray(record["a"]), np.asarray(record["b"])
        d = b - a
        d /= np.linalg.norm(d)
        pivot = int(np.argmax(np.abs(d)))
        if d[pivot] < 0:
            d = -d
        key = (*record["mesh_indices"], *np.round(d, 7))
        lines = groups.setdefault(key, [])
        group = next((g for g in lines if np.linalg.norm(np.cross(a - g["origin"], g["direction"])) <= eps * 2
                      and np.linalg.norm(np.cross(b - g["origin"], g["direction"])) <= eps * 2), None)
        if group is None:
            group = dict(origin=a, direction=d, intervals=[], meshes=record["mesh_indices"])
            lines.append(group)
        origin, direction = group["origin"], group["direction"]
        low, high = sorted((float(np.dot(a - origin, direction)), float(np.dot(b - origin, direction))))
        group["intervals"].append([low, high, record["triangle_pairs"]])
    output = []
    for lines in groups.values():
        for group in lines:
            intervals = sorted(group["intervals"], key=lambda row: (row[0], row[1]))
            merged = []
            for lo, hi, pairs in intervals:
                if merged and lo <= merged[-1][1] + eps * 2:
                    merged[-1][1] = max(hi, merged[-1][1])
                    merged[-1][2].extend(pairs)
                else:
                    merged.append([lo, hi, list(pairs)])
            for lo, hi, pairs in merged:
                output.append(dict(a=(group["origin"] + lo * group["direction"]).tolist(),
                                   b=(group["origin"] + hi * group["direction"]).tolist(),
                                   mesh_indices=list(group["meshes"]),
                                   triangle_pairs=[list(pair) for pair in sorted({tuple(p) for p in pairs})],
                                   features=["intersection"]))
    output.sort(key=lambda r: (*r["mesh_indices"], *r["a"], *r["b"]))
    return output


def _mesh_pairs(data,self_intersections,eps):
    """Same ordered AABB pairs; compare rows in bulk with O(n) scratch."""
    active=[i for i,item in enumerate(data) if item['root'] is not None and
            ('active_triangles' not in item or np.any(item['active_triangles']))]
    if not active:return []
    def bounds(item):
        mask=item.get('active_triangles')
        if mask is None or np.all(mask):return item['root'].low,item['root'].high
        enabled=np.asarray(mask,dtype=np.bool_)
        return item['lows'][enabled].min(axis=0),item['highs'][enabled].max(axis=0)
    boxes=[bounds(data[i]) for i in active]
    lows=np.asarray([b[0] for b in boxes]);expanded_highs=np.asarray([b[1] for b in boxes])+eps
    pairs=[]
    for row,i in enumerate(active):
        start=row if self_intersections else row+1
        overlap=(np.all(lows[row]<=expanded_highs[start:],axis=1)&
                 np.all(lows[start:]<=expanded_highs[row],axis=1))
        pairs.extend((i,active[start+int(j)]) for j in np.flatnonzero(overlap))
    return pairs


def _native_records(data,native,self_intersections,eps,max_candidates,max_segments,counts,workers,array_output=False):
    """Bounded native queries; ordered consumption preserves deterministic output."""
    pairs=_mesh_pairs(data,self_intersections,eps)
    mask_keys=[hashlib.sha256(item['active_triangles'].tobytes()).digest() if 'active_triangles' in item else None for item in data]
    def query(pair):
        i,j=pair;a,b=data[i],data[j]
        arguments=(*a['flat'],*b['flat'],a['positions'],b['positions'],a['lows'],a['highs'],b['lows'],b['highs'],
            a['indices'],b['indices'],a['owner_array'],b['owner_array'],a['normals'],b['normals'],
            a['areas'],b['areas'],a['longest'],b['longest'],i==j,eps,max_candidates,max_segments)
        def compute():
            output=(native(*arguments,a['active_triangles'],b['active_triangles'],a['active_nodes'],b['active_nodes'])
                    if 'active_triangles' in a else native(*arguments))
            return np.asarray(output[0],np.float64).reshape(-1,8),output[1],output[2]
        # Successful complete queries are capacity-independent; every result
        # still passes the global guards below, even after a smaller request.
        key=((a['cache_token'],b['cache_token'],i==j,eps,mask_keys[i],mask_keys[j])
             if 'cache_token' in a and 'cache_token' in b else None)
        return _query_cached(key,compute)
    records=IntersectionBatches() if array_output else []
    pair_sizes=[int(np.count_nonzero(item['active_triangles'])) if 'active_triangles' in item
                else len(item['positions']) for item in data]
    def batches():
        # Small mesh pairs cost less than scheduling one Python Future. Keep
        # contiguous ordering and bound each group's worst-case triangle-pair
        # output; a large query remains alone with its original explicit guard.
        batch=[];cost=0
        for pair in pairs:
            i,j=pair
            potential=min(max_segments,pair_sizes[i]*pair_sizes[j])
            if batch and (len(batch)>=32 or cost+potential>65536):
                yield batch;batch=[];cost=0
            batch.append(pair);cost+=potential
        if batch:yield batch
    def query_batch(batch):
        results=[]
        for pair in batch:
            output=query(pair);results.append((pair,output))
            if output[2]:break
        return results
    with ThreadPoolExecutor(max_workers=workers) as executor:
        source=iter(batches())
        pending=deque()
        for _ in range(workers*2):
            batch=next(source,None)
            if batch is None:break
            pending.append(executor.submit(query_batch,batch))
        while pending:
            output=pending.popleft().result()
            next_batch=next(source,None)
            if next_batch is not None:pending.append(executor.submit(query_batch,next_batch))
            for (i,j),(segments,counters,failure) in output:
                for name,value in zip(('node_pairs','aabb_pairs','adjacent_skipped','narrow_pairs','plane_rejected',
                    'degenerate_pairs','coplanar_pairs','candidate_pairs','point_contacts'),counters):
                    counts[name]+=int(value)
                if failure or counts['candidate_pairs']>max_candidates or len(records)+len(segments)>max_segments:
                    kind='candidate' if failure==1 or counts['candidate_pairs']>max_candidates else 'segment'
                    raise IntersectionLimitError('Intersection %s budget exceeded; no partial lines returned'%kind)
                if array_output:records.add(i,j,segments)
                else:
                    records.extend(dict(a=row[:3],b=row[3:6],mesh_indices=[i,j],triangle_pairs=[[int(row[6]),int(row[7])]])
                                   for row in segments.tolist())
    return records


def find_intersections(meshes, self_intersections=False, tolerance=1e-7,
                       max_candidates=2_000_000, max_segments=200_000, diagnostics=None, backend="auto", merge_segments=True, workers=None,
                       triangle_masks=None,prepared_output=None,array_output=False):
    """Return merged world-space intersection records for scene mesh objects.

    Each record has ``a``, ``b`` XYZ lists, ``mesh_indices`` [i,j], contributing
    ``triangle_pairs`` and ``features: ['intersection']``. Collinear overlapping
    or adjacent segments are merged per mesh pair; segments from distinct mesh
    pairs remain separately styled. Pass a dict as diagnostics for counts.
    Budgets raise IntersectionLimitError rather than return incomplete lines.
    ``backend`` is auto (optional cached Numba kernel), numba, or python.
    candidate_pairs counts costly section/interval tests after adjacency and
    triangle-plane rejection; aabb_pairs/narrow_pairs retain broader counts.
    No geometry simplification or sampling is used by either backend.
    Disable merge_segments for per-face styling: every record then belongs to
    exactly one triangle pair, so a merged span cannot cross target boundaries.
    Optional triangle_masks skip queries without changing original triangle IDs,
    BVH boxes, traversal order or operand order. The caller owns mask correctness.
    """
    eps = float(tolerance)
    if not np.isfinite(eps) or eps <= 0:
        raise ValueError("Intersection tolerance must be finite and positive")
    if backend not in ("auto", "python", "numba"):
        raise ValueError("Intersection backend must be auto, python or numba")
    started = time.perf_counter()
    native, fallback_reason = _native_function(backend)
    triangle_count=sum(len(m.get('triangles',m.get('faces',[]))) for m in meshes)
    workers=(min(8,os.cpu_count() or 1) if native is not None and triangle_count>=100_000 and len(meshes)>=4 else 1) if workers is None else max(1,min(8,int(workers)))
    if native is not None and workers>1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            data=list(executor.map(lambda mesh:_prepare(mesh,native_bvh=True),meshes))
    else:
        data = [_prepare(mesh,native_bvh=native is not None) for mesh in meshes]
    if prepared_output is not None:
        prepared_output[:]=data
    if triangle_masks is not None:
        if len(triangle_masks)!=len(data):raise ValueError('One triangle mask is required per mesh')
        for item,mask in zip(data,triangle_masks):
            active=np.asarray(mask,dtype=np.bool_)
            if active.ndim!=1 or len(active)!=len(item['indices']):
                raise ValueError('Triangle mask must match original triangle count')
            item['active_triangles']=np.ascontiguousarray(active)
            item['active_nodes']=None
            if native is not None and item['root'] is not None:
                from .native_cpu import library,active_bvh_nodes
                if library() is None:
                    from ._intersection_kernel import active_bvh_nodes
                item['active_nodes']=active_bvh_nodes(item['flat'][2],item['flat'][3],item['flat'][4],active)
    if native is not None:
        for item in data:
            if item["root"] is not None:
                item["owner_array"] = np.asarray(item["owners"], dtype=np.int64) if item["owners"] is not None else np.full(len(item["indices"]), -1, np.int64)
    prepared_at = time.perf_counter()
    counts = dict(meshes=len(meshes), triangles=sum(len(item["indices"]) for item in data),
                  candidate_pairs=0, narrow_pairs=0, adjacent_skipped=0, coplanar_pairs=0,
                  degenerate_pairs=0, point_contacts=0, raw_segments=0, segments=0,
                  tolerance=eps, broadphase="triangle AABB BVH", node_pairs=0,
                  aabb_pairs=0, plane_rejected=0, backend=("native-cpu" if native is not None and native.__module__.endswith("native_cpu") else "numba-nogil" if native is not None else "python"),
                  fallback_reason=fallback_reason,workers=workers)
    if triangle_masks is not None:
        counts['triangle_masking']=dict(active=sum(int(np.count_nonzero(item['active_triangles'])) for item in data),
                                        total=triangle_count,preserves_original_bvh=True)
    records = IntersectionBatches() if array_output and not merge_segments else []
    if native is not None:
        try:
            records=_native_records(data,native,self_intersections,eps,max_candidates,max_segments,counts,workers,array_output and not merge_segments)
        except IntersectionLimitError:
            if diagnostics is not None:diagnostics.update(counts,incomplete=True,elapsed_seconds=time.perf_counter()-started)
            raise
        except Exception as error:
            if backend!='auto' or not (isinstance(error,(OSError,RuntimeError)) or type(error).__module__.startswith('numba.')):
                raise
            fallback_stats={}
            result=find_intersections(meshes,self_intersections,tolerance,max_candidates,max_segments,
                fallback_stats,backend='python',merge_segments=merge_segments,triangle_masks=triangle_masks,
                array_output=array_output)
            fallback_stats['fallback_reason']='Native execution unavailable: %s'%error
            fallback_stats['timings']['total_seconds']=time.perf_counter()-started
            if diagnostics is not None:diagnostics.update(fallback_stats)
            return result
    for i, first in enumerate(data if native is None else []):
        if first["root"] is None:
            continue
        for j in range(i if self_intersections else i + 1, len(data)):
            second = data[j]
            if second["root"] is None:
                continue
            if not _overlap(first["root"].low, first["root"].high, second["root"].low, second["root"].high, eps):
                continue
            for ti, tj in _pairs(first["root"], second["root"], eps, i == j):
                if triangle_masks is not None and (not first['active_triangles'][ti] or not second['active_triangles'][tj]):continue
                counts["aabb_pairs"] += 1
                if i == j:
                    same_face = first["owners"] is not None and first["owners"][ti] == first["owners"][tj]
                    if same_face or np.intersect1d(first["indices"][ti], first["indices"][tj]).size:
                        counts["adjacent_skipped"] += 1
                        continue
                if not _overlap(first["lows"][ti], first["highs"][ti], second["lows"][tj], second["highs"][tj], eps):
                    continue
                counts["narrow_pairs"] += 1
                if first["areas"][ti] <= eps * max(first["longest"][ti], eps) or second["areas"][tj] <= eps * max(second["longest"][tj], eps):
                    counts["degenerate_pairs"] += 1
                    continue
                a, b = first["positions"][ti], second["positions"][tj]
                normal_a, normal_b = first["normals"][ti], second["normals"][tj]
                distance_a, distance_b = (a - b[0]) @ normal_b, (b - a[0]) @ normal_a
                if (np.all(distance_a > eps) or np.all(distance_a < -eps)
                        or np.all(distance_b > eps) or np.all(distance_b < -eps)):
                    counts["plane_rejected"] += 1
                    continue
                if np.max(np.abs(distance_a)) <= eps and np.max(np.abs(distance_b)) <= eps:
                    counts["coplanar_pairs"] += 1
                    continue
                if np.linalg.norm(np.cross(normal_a, normal_b)) <= 1e-12:
                    counts["plane_rejected"] += 1
                    continue
                if strictly_separated(a,b):
                    counts['plane_rejected']+=1
                    continue
                counts["candidate_pairs"] += 1
                if counts["candidate_pairs"] > max_candidates:
                    raise IntersectionLimitError("Intersection candidate budget exceeded; no partial lines returned")
                segment, kind = triangle_intersection(first["positions"][ti], second["positions"][tj], eps)
                if kind == "coplanar":
                    counts["coplanar_pairs"] += 1
                elif kind == "degenerate":
                    counts["degenerate_pairs"] += 1
                elif kind == "point-contact":
                    counts["point_contacts"] += 1
                if segment is not None:
                    if isinstance(records,IntersectionBatches):records.append_record(i,j,segment,ti,tj)
                    else:records.append(dict(a=segment[0].tolist(), b=segment[1].tolist(),
                                             mesh_indices=[i, j], triangle_pairs=[[ti, tj]]))
                    if len(records) > max_segments:
                        raise IntersectionLimitError("Intersection segment budget exceeded; reduce mesh detail or raise max_segments explicitly")
    if isinstance(records,IntersectionBatches):records.flush()
    counts["raw_segments"] = len(records)
    traversed_at = time.perf_counter()
    if merge_segments:
        result=_merge_segments(records,eps)
    elif isinstance(records,IntersectionBatches):result=records
    else:
        # Records are owned by this query. Avoid duplicating hundreds of
        # thousands of dictionaries just to attach the common feature field.
        for record in records:record['features']=['intersection']
        result=records
    counts["segments"] = len(result)
    counts["timings"] = dict(prepare_seconds=prepared_at - started, traverse_seconds=traversed_at - prepared_at,
                             merge_seconds=time.perf_counter() - traversed_at, total_seconds=time.perf_counter() - started)
    if diagnostics is not None:
        diagnostics.update(counts)
    return result
