"""Optional exact-location CPU visibility refinement for ambiguous samples."""
import time
from concurrent.futures import ThreadPoolExecutor
import numpy as np

def prepare(meshes,prepared=None):
    """Pack original BVH forests; prepared intersection dictionaries are reusable."""
    from .accelerator import enable
    enable()
    started=time.perf_counter()
    if prepared is None:
        from .intersections import _prepare
        def one(mesh):
            return _prepare(mesh,native_bvh=True)
        with ThreadPoolExecutor(max_workers=4) as pool:prepared=list(pool.map(one,meshes))
    roots=[];arrays=[[] for _ in range(6)];triangles=[]
    node_offset=triangle_offset=order_offset=0
    for item in prepared:
        if item is None or not len(item['positions']):continue
        low,high,child,ranges,order=item['flat']
        roots.append(node_offset)
        arrays[0].append(low);arrays[1].append(high)
        arrays[2].append(np.where(child>=0,child+node_offset,-1))
        arrays[3].append(np.where(ranges>=0,ranges+order_offset,-1))
        arrays[4].append(order+triangle_offset)
        triangles.append(item['positions'])
        node_offset+=len(low);triangle_offset+=len(item['positions']);order_offset+=len(order)
    if not roots:
        return dict(arguments=(np.empty(0,np.int64),np.empty((0,3)),np.empty((0,3)),
            np.empty((0,2),np.int64),np.empty((0,2),np.int64),np.empty(0,np.int64),np.empty((0,3,3))),
            prepare_seconds=time.perf_counter()-started,triangles=0)
    packed=tuple(np.concatenate(parts) for parts in arrays[:5])
    return dict(arguments=(np.asarray(roots,np.int64),*packed,np.concatenate(triangles)),prepare_seconds=time.perf_counter()-started,triangles=triangle_offset)

def visible_samples(context,xy,camera_z,camera):
    """True means no triangle before this sample; depths are camera-space z."""
    from ._visibility_kernel import visible
    xy=np.asarray(xy,np.float64).reshape(-1,2)
    depths=np.asarray(camera_z,np.float64)
    inverse=np.linalg.inv(np.asarray(camera['basis'],np.float64))
    camera_rays=np.ones((len(xy),3),np.float64)
    camera_rays[:,0]=xy[:,0]-camera['width']/2
    camera_rays[:,1]=camera['height']/2-xy[:,1]
    if camera['ortho']:
        camera_rays[:,:2]*=camera['span']/camera['width'];camera_rays[:,2]=0
        origins=np.asarray(camera['eye'])+camera_rays@inverse.T
        directions=np.tile(inverse[:,2],(len(xy),1))
    else:
        camera_rays[:,:2]/=camera['focal']
        origins=np.tile(np.asarray(camera['eye'],np.float64),(len(xy),1))
        directions=camera_rays@inverse.T
    return visible(origins,directions,depths,float(camera['near']),*context['arguments'])
