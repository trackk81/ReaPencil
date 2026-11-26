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
    offset = len(low)-len(roots)+1
    out_low, out_high, out_children, out_ranges = low, high, children, ranges
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
    items = [item for item in prepared if item is not None and len(item['positions'])]
    triangle_count = sum(len(item['positions']) for item in items)
    tree_nodes = sum(len(item['flat'][0]) for item in items)
    nodes = tree_nodes + (len(items)-1 if len(items)>=8 else 0)
    low = np.empty((nodes,3),np.float64)
    high = np.empty_like(low)
    children = np.full((nodes,2),-1,np.int64)
    ranges = np.full_like(children,-1)
    triangles = np.empty((triangle_count,3,3),np.float64)
    order = np.empty(sum(len(item['flat'][4]) for item in items),np.int64)
    roots=[]
    node_offset=triangle_offset=order_offset=0
    for item in items:
        lo,hi,child,span,indices=item['flat']
        roots.append(node_offset)
        end=node_offset+len(lo)
        low[node_offset:end]=lo
        high[node_offset:end]=hi
        np.add(child,node_offset,out=children[node_offset:end],where=child>=0)
        np.add(span,order_offset,out=ranges[node_offset:end],where=span>=0)
        np.add(indices,triangle_offset,out=order[order_offset:order_offset+len(indices)])
        positions=item['positions']
        triangles[triangle_offset:triangle_offset+len(positions)]=positions
        node_offset=end
        triangle_offset+=len(positions)
        order_offset+=len(indices)
    roots,low,high,children,ranges=_root_hierarchy(roots,low,high,children,ranges)
    from .cpu_alpha import pack_visibility
    active_meshes=[m for m,p in zip(meshes,prepared) if p is not None and len(p['positions'])]
    alpha=pack_visibility(active_meshes)
    arguments=(roots,low,high,children,ranges,order,triangles)
    if alpha is not None:arguments+=(alpha,)
    return dict(arguments=arguments,prepare_seconds=time.perf_counter()-started,triangles=triangle_count)

def visible_samples(context,xy,camera_z,camera):
    """True means no triangle before this sample; depths are camera-space z."""
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
    if len(context['arguments'])>7:
        import ctypes as c
        from .native_cpu import library,visibility_context
        ctx=visibility_context(context['arguments']);out=np.empty(len(depths),np.uint8)
        lib=library();lib.rp_alpha_visible.argtypes=[c.c_void_p]*3+[c.c_int64,c.c_double]+[c.c_void_p]*2
        lib.rp_alpha_visible.restype=None
        origins=np.ascontiguousarray(origins);directions=np.ascontiguousarray(directions);depths=np.ascontiguousarray(depths)
        lib.rp_alpha_visible(origins.ctypes.data,directions.ctypes.data,depths.ctypes.data,len(depths),float(camera['near']),c.byref(ctx),out.ctypes.data)
        return out.astype(bool)
    from ._visibility_kernel import visible
    return visible(origins,directions,depths,float(camera['near']),*context['arguments'])
