"""Optional Numba CPU kernel; identical full-resolution triangle geometry.

Importing this module requires Numba. intersections.py loads it lazily and
falls back when Numba is absent or incompatible. No fast-math is used: the
reference tolerance and coplanar/adjacency semantics remain unchanged.
"""
import numpy as np
from numba import njit
from ._robust_kernel import orient3d_value


@njit(cache=True,nogil=True)
def active_bvh_nodes(children,ranges,order,triangles):
    """Mark only wholly inactive subtrees; never rebuild or shrink boxes."""
    active=np.zeros(len(children),np.bool_)
    # The existing builder allocates children after their parent.
    for node in range(len(children)-1,-1,-1):
        left,right=children[node]
        if left>=0:active[node]=active[left] or active[right]
        else:
            for position in range(ranges[node,0],ranges[node,1]):
                if triangles[order[position]]:
                    active[node]=True
                    break
    return active


@njit(cache=True, nogil=True, inline='always')
def _section_into(tri, distances, eps, points):
    count = 0
    for k in range(3):
        next_k = (k + 1) % 3
        da, db = distances[k], distances[next_k]
        for mode in range(2):
            valid = da == 0 if mode == 0 else ((da < 0 and db > 0) or (da > 0 and db < 0))
            if not valid:
                continue
            fraction = 0.0 if mode == 0 else da / (da - db)
            px=tri[k,0]+(tri[next_k,0]-tri[k,0])*fraction
            py=tri[k,1]+(tri[next_k,1]-tri[k,1])*fraction
            pz=tri[k,2]+(tri[next_k,2]-tri[k,2])*fraction
            unique = True
            for j in range(count):
                squared=(px-points[j,0])**2
                squared+=(py-points[j,1])**2
                squared+=(pz-points[j,2])**2
                if squared <= eps * eps:
                    unique = False
                    break
            if unique:
                points[count,0]=px
                points[count,1]=py
                points[count,2]=pz
                count += 1
    return count


@njit(cache=True, nogil=True)
def traverse(lows_a, highs_a, children_a, ranges_a, order_a,
             lows_b, highs_b, children_b, ranges_b, order_b,
             tri_a, tri_b, tri_lows_a, tri_highs_a, tri_lows_b, tri_highs_b,
             indices_a, indices_b, owners_a, owners_b,
             normals_a, normals_b, areas_a, areas_b, longest_a, longest_b,
             same_mesh, eps, candidate_budget, segment_budget,
             active_triangles_a=None,active_triangles_b=None,active_nodes_a=None,active_nodes_b=None):
    """Return complete segments, counters, status(0/1 candidates/2 segments).

    Counters: node_pairs, aabb_pairs, adjacent_skipped, narrow_pairs,
    plane_rejected, degenerate_pairs, coplanar_pairs, candidate_pairs,
    point_contacts. candidate_pairs counts actual section/interval tests after
    adjacency, degeneracy, sidedness and coplanarity have been eliminated.
    """
    counts = np.zeros(9, np.int64)
    output = []
    # Scratch belongs to this traversal invocation, so concurrent mesh-pair
    # queries never share memory. Avoid millions of tiny heap allocations.
    da,db=np.empty(3,np.float64),np.empty(3,np.float64)
    direction=np.empty(3,np.float64)
    pa,pb=np.empty((6,3),np.float64),np.empty((6,3),np.float64)
    stack = np.empty((len(lows_a) + len(lows_b) + 8, 2), np.int64)
    stack[0, 0], stack[0, 1] = 0, 0
    size = 1
    while size:
        size -= 1
        na, nb = stack[size, 0], stack[size, 1]
        if active_nodes_a is not None and not active_nodes_a[na]:continue
        if active_nodes_b is not None and not active_nodes_b[nb]:continue
        counts[0] += 1
        overlap = True
        for axis in range(3):
            if lows_a[na, axis] > highs_b[nb, axis] + eps or lows_b[nb, axis] > highs_a[na, axis] + eps:
                overlap = False
                break
        if not overlap:
            continue
        la, lb = children_a[na, 0], children_b[nb, 0]
        if same_mesh and na == nb and la >= 0:
            ra = children_a[na, 1]
            stack[size, 0], stack[size, 1] = ra, ra
            stack[size + 1, 0], stack[size + 1, 1] = la, ra
            stack[size + 2, 0], stack[size + 2, 1] = la, la
            size += 3
            continue
        if la >= 0 or lb >= 0:
            extent_a = max(highs_a[na, 0] - lows_a[na, 0], highs_a[na, 1] - lows_a[na, 1], highs_a[na, 2] - lows_a[na, 2])
            extent_b = max(highs_b[nb, 0] - lows_b[nb, 0], highs_b[nb, 1] - lows_b[nb, 1], highs_b[nb, 2] - lows_b[nb, 2])
            if lb < 0 or (la >= 0 and extent_a >= extent_b):
                stack[size, 0], stack[size, 1] = children_a[na, 1], nb
                stack[size + 1, 0], stack[size + 1, 1] = la, nb
            else:
                stack[size, 0], stack[size, 1] = na, children_b[nb, 1]
                stack[size + 1, 0], stack[size + 1, 1] = na, lb
            size += 2
            continue
        for oi in range(ranges_a[na, 0], ranges_a[na, 1]):
            ti = order_a[oi]
            if active_triangles_a is not None and not active_triangles_a[ti]:continue
            first_j = oi + 1 if same_mesh and na == nb else ranges_b[nb, 0]
            for oj in range(first_j, ranges_b[nb, 1]):
                tj = order_b[oj]
                if active_triangles_b is not None and not active_triangles_b[tj]:continue
                overlap = True
                for axis in range(3):
                    if tri_lows_a[ti, axis] > tri_highs_b[tj, axis] + eps or tri_lows_b[tj, axis] > tri_highs_a[ti, axis] + eps:
                        overlap = False
                        break
                if not overlap:
                    continue
                counts[1] += 1
                if same_mesh:
                    adjacent = owners_a[ti] >= 0 and owners_a[ti] == owners_b[tj]
                    if not adjacent:
                        for va in range(3):
                            for vb in range(3):
                                if indices_a[ti, va] == indices_b[tj, vb]:
                                    adjacent = True
                    if adjacent:
                        counts[2] += 1
                        continue
                counts[3] += 1
                if areas_a[ti] <= eps * max(longest_a[ti], eps) or areas_b[tj] <= eps * max(longest_b[tj], eps):
                    counts[5] += 1
                    continue
                for vertex in range(3):
                    da[vertex] = 0.0
                    db[vertex] = 0.0
                    for axis in range(3):
                        da[vertex] += (tri_a[ti, vertex, axis] - tri_b[tj, 0, axis]) * normals_b[tj, axis]
                        db[vertex] += (tri_b[tj, vertex, axis] - tri_a[ti, 0, axis]) * normals_a[ti, axis]
                if (min(da[0], da[1], da[2]) > eps or max(da[0], da[1], da[2]) < -eps
                        or min(db[0], db[1], db[2]) > eps or max(db[0], db[1], db[2]) < -eps):
                    counts[4] += 1
                    continue
                direction[0] = normals_a[ti, 1] * normals_b[tj, 2] - normals_a[ti, 2] * normals_b[tj, 1]
                direction[1] = normals_a[ti, 2] * normals_b[tj, 0] - normals_a[ti, 0] * normals_b[tj, 2]
                direction[2] = normals_a[ti, 0] * normals_b[tj, 1] - normals_a[ti, 1] * normals_b[tj, 0]
                length = np.sqrt(direction[0] ** 2 + direction[1] ** 2 + direction[2] ** 2)
                coplanar = max(abs(da[0]), abs(da[1]), abs(da[2])) <= eps and max(abs(db[0]), abs(db[1]), abs(db[2])) <= eps
                if coplanar:
                    counts[6] += 1
                    continue
                if length <= 1e-12:
                    counts[4] += 1
                    continue
                for vertex in range(3):
                    da[vertex]=orient3d_value(tri_a[ti,vertex],tri_b[tj,1],tri_b[tj,2],tri_b[tj,0])
                    db[vertex]=orient3d_value(tri_b[tj,vertex],tri_a[ti,1],tri_a[ti,2],tri_a[ti,0])
                    if not np.isfinite(da[vertex]) or not np.isfinite(db[vertex]):
                        raise ValueError("Triangle coordinates exceed robust native predicate range")
                if (min(da[0],da[1],da[2])>0 or max(da[0],da[1],da[2])<0
                        or min(db[0],db[1],db[2])>0 or max(db[0],db[1],db[2])<0):
                    counts[4]+=1
                    continue
                counts[7] += 1
                if counts[7] > candidate_budget:
                    return output, counts, 1
                direction /= length
                ca = _section_into(tri_a[ti], da, eps,pa)
                cb = _section_into(tri_b[tj], db, eps,pb)
                if ca == 0 or cb == 0:
                    continue
                mina, maxa, minb, maxb = np.inf, -np.inf, np.inf, -np.inf
                for point in range(ca):
                    value = 0.0
                    for axis in range(3):
                        value += (pa[point, axis] - pa[0, axis]) * direction[axis]
                    mina, maxa = min(mina, value), max(maxa, value)
                for point in range(cb):
                    value = 0.0
                    for axis in range(3):
                        value += (pb[point, axis] - pa[0, axis]) * direction[axis]
                    minb, maxb = min(minb, value), max(maxb, value)
                low, high = max(mina, minb), min(maxa, maxb)
                if high < low - eps:
                    continue
                if high - low <= eps:
                    counts[8] += 1
                    continue
                output.append((pa[0, 0] + low * direction[0], pa[0, 1] + low * direction[1], pa[0, 2] + low * direction[2],
                               pa[0, 0] + high * direction[0], pa[0, 1] + high * direction[1], pa[0, 2] + high * direction[2], ti, tj))
                if len(output) > segment_budget:
                    return output, counts, 2
    return output, counts, 0
