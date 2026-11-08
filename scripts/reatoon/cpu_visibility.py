"""Optional exact-location CPU visibility refinement for ambiguous samples."""
import time
from concurrent.futures import ThreadPoolExecutor
import numpy as np

def _root_hierarchy(roots,low,high,children,ranges):
    """Link unchanged mesh BVHs under a balanced hierarchy of exact bounds.

    Any-hit queries previously visited every mesh root for each ambiguous
    sample. Union bounds skip distant groups without changing any triangle,
    sample, tolerance or intersection predicate. Small forests stay unchanged.
    """
    roots=np.asarray(roots,np.int64)
    if len(roots)<8:return roots,low,high,children,ranges
    offset=len(low);extra=len(roots)-1
    out_low=np.empty((offset+extra,3),np.float64);out_low[:offset]=low
    out_high=np.empty_like(out_low);out_high[:offset]=high
    out_children=np.full((offset+extra,2),-1,np.int64);out_children[:offset]=children
    out_ranges=np.full_like(out_children,-1);out_ranges[:offset]=ranges
    centers=low[roots]*.5+high[roots]*.5
    next_node=offset
    def build(ids):
        nonlocal next_node
        if len(ids)==1:return int(roots[ids[0]])
        node=next_node;next_node+=1
        axis=int(np.argmax(np.ptp(centers[ids],axis=0)))
        ordered=ids[np.argsort(centers[ids,axis],kind='stable')];middle=len(ids)//2
        left=build(ordered[:middle]);right=build(ordered[middle:])
        out_children[node]=(left,right)
        out_low[node]=np.minimum(out_low[left],out_low[right])
        out_high[node]=np.maximum(out_high[left],out_high[right])
        return node
    root=build(np.arange(len(roots)))
    return np.asarray([root],np.int64),out_low,out_high,out_children,out_ranges


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
    roots,low,high,children,ranges=_root_hierarchy(roots,*packed[:4])
    return dict(arguments=(roots,low,high,children,ranges,packed[4],np.concatenate(triangles)),prepare_seconds=time.perf_counter()-started,triangles=triangle_offset)

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
