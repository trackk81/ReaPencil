"""Compiled CPU depth-only rasterization for line visibility.

Uses the optional existing Numba sidecar. No GPU work, shading or silent
Python fallback: callers can explicitly choose their reference fallback when
the accelerator is unavailable. Output arrays are modified in place.
"""
import numpy as np


def rasterize_mesh(camverts, tris, camera, depth, depth_planes,
                   mesh_owners=None, mesh_index=-1):
    from .accelerator import enable
    enable()
    try:
        from ._depth_kernel import rasterize
    except (ImportError, OSError, RuntimeError, AttributeError) as error:
        raise RuntimeError('Compiled CPU depth accelerator unavailable: %s' % error) from error
    vertices=np.ascontiguousarray(camverts,dtype=np.float64)
    raw_triangles=np.asarray(tris)
    if raw_triangles.size and (not np.isfinite(raw_triangles).all()
                              or np.any(raw_triangles!=np.floor(raw_triangles))):
        raise ValueError('Triangle indices must be finite integers')
    triangles=np.ascontiguousarray(raw_triangles,dtype=np.int64)
    if vertices.ndim!=2 or vertices.shape[1]!=3 or not np.isfinite(vertices).all():
        raise ValueError('Camera vertices must be finite Nx3')
    if triangles.size==0:triangles=triangles.reshape(0,3)
    if triangles.ndim!=2 or triangles.shape[1]!=3:
        raise ValueError('Triangles must be Nx3')
    if triangles.size and (triangles.min()<0 or triangles.max()>=len(vertices)):
        raise ValueError('Triangle vertex index out of range')
    width,height=int(camera['width']),int(camera['height'])
    for array,shape in ((depth,(height,width)),(depth_planes,(height,width,3))):
        if array.shape!=shape or array.dtype!=np.float64 or not array.flags.c_contiguous or not array.flags.writeable:
            raise ValueError('Depth outputs must be writable contiguous float64 arrays of camera dimensions')
    has_owners=mesh_owners is not None
    if has_owners:
        if mesh_owners.shape!=(height,width) or mesh_owners.dtype not in (np.int32,np.int64) or not mesh_owners.flags.c_contiguous or not mesh_owners.flags.writeable:
            raise ValueError('Mesh owners must be writable contiguous integer camera image')
    else:
        mesh_owners=np.empty((1,1),np.int32)
    count=rasterize(vertices,triangles,depth,depth_planes,mesh_owners,has_owners,int(mesh_index),
                    bool(camera['ortho']),float(camera['span']),float(camera['focal']),
                    float(camera['near']),float(camera['far']))
    return {'backend':'numba-cpu-depth','triangles':int(count)}
