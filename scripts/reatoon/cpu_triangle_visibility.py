"""Conservative whole-triangle bounds for visible CPU intersection queries.

Only suitable for the existing visible-line point-depth rule. Hidden lines,
render elements and any different visibility policy require the full query.
The caller must supply the maximum screen clipping margin and depth bias of
EVERY line style. This module does not modify geometry or remap triangle IDs.
"""
import numpy as np


def visibility_masks(meshes,camera,depth,depth_planes,max_depth_bias,screen_margin,
                     world_tolerance=1e-7):
    if max_depth_bias<0 or screen_margin<1 or world_tolerance<0:
        raise ValueError('Conservative bounds require nonnegative bias/tolerance and screen margin >=1')
    from .accelerator import enable
    enable()
    from ._triangle_visibility_kernel import surface_bounds,triangle_mask
    depth=np.asarray(depth,np.float64)
    planes=np.asarray(depth_planes,np.float64)
    if depth.shape!=(camera['height'],camera['width']) or planes.shape!=(*depth.shape,3):
        raise ValueError('Depth arrays must match camera dimensions')
    bound=surface_bounds(depth,planes,bool(camera['ortho']),float(screen_margin))
    masks=[]
    counters=np.zeros(4,np.int64)
    for mesh in meshes:
        vertices=(np.asarray(mesh['vertices'],np.float64)-camera['eye']) @ camera['basis'].T
        raw=np.asarray(mesh['triangles'])
        if raw.size and raw.dtype.kind not in 'iu' and (not np.isfinite(raw).all() or np.any(raw!=np.floor(raw))):
            raise ValueError('Triangle indices must be finite integers')
        triangles=np.ascontiguousarray(raw,np.int64).reshape(-1,3)
        if triangles.size and (triangles.min()<0 or triangles.max()>=len(vertices)):
            raise ValueError('Triangle vertex index out of range')
        mask,counts=triangle_mask(vertices,triangles,bound,bool(camera['ortho']),
            float(camera['span']),float(camera['focal']),float(camera['near']),float(camera['far']),
            float(max_depth_bias),float(screen_margin),float(world_tolerance))
        masks.append(mask);counters+=counts
    return masks,dict(triangles=int(counters.sum()),kept=int(counters[0]),outside_depth=int(counters[1]),
                      outside_screen=int(counters[2]),occluded=int(counters[3]),
                      method='whole projected bounding rectangle, analytic pixel-plane extrema',
                      production_enabled=False)
