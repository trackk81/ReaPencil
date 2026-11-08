"""Reuse whole-triangle invisibility certificates for constant CPU strokes.

Only an exact authored edge which is also an edge of a certified triangle can
be rejected. Missing/invalid triangulation correspondence is retained. This
does not infer a polygon's coverage from its vertex bounds or triangulation
count, so unused components and non-manifold polygons remain conservative.
"""
import ctypes
from pathlib import Path
import numpy as np

_lib=None


def keep_edges(pairs,triangles,triangle_active):
    global _lib
    pairs=np.ascontiguousarray(pairs,np.int64).reshape(-1,2)
    result=np.ones(len(pairs),np.bool_)
    if not len(pairs) or np.all(triangle_active):return result
    triangles=np.ascontiguousarray(triangles,np.int64).reshape(-1,3)
    active=np.ascontiguousarray(triangle_active,np.bool_)
    if len(active)!=len(triangles):raise ValueError('One visibility certificate is required per triangle')
    if (pairs.size and (pairs.min()<0 or pairs.max()>=2**32)) or (triangles.size and (triangles.min()<0 or triangles.max()>=2**32)):
        return result
    if _lib is None:
        try:
            lib=ctypes.CDLL(str(Path(__file__).resolve().parents[2]/'plug-ins/2025/reaPencilSegments159.dll'))
            lib.rp_edge_mask159.argtypes=[ctypes.c_void_p,ctypes.c_int64,ctypes.c_void_p,ctypes.c_int64,ctypes.c_void_p,ctypes.c_void_p]
            lib.rp_edge_mask159.restype=ctypes.c_int
            _lib=lib
        except (OSError,AttributeError):_lib=False
    if _lib and _lib.rp_edge_mask159(pairs.ctypes.data,len(pairs),triangles.ctypes.data,len(triangles),active.ctypes.data,result.ctypes.data)!=0:
        raise RuntimeError('CPU edge visibility certificate allocation failed')
    return result
