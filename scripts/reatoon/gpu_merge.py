"""GPU nearest-face queries trim internal group silhouettes at pixel spacing.

Only outline-only strokes participate. Creases, selected edges and intersection
lines retain their own meaning. Projection follows the centered viewport camera.
"""
import numpy as np
from .renderer import _camera, _project


def filter_outlines(gpu, points, owners, styles, camera, groups, width, height):
    cam=_camera(camera,int(width),int(height))
    # The projection basis includes film-gate aspect scaling, so its transpose
    # is not generally its inverse. Undo both camera rotation and that scaling.
    camera_to_world=np.linalg.inv(cam['basis']).T
    pairs=points.reshape(-1,2,4)
    membership={}
    for group in groups:
        members=frozenset(group['mesh_indices'])
        for index in members:membership.setdefault(index,members)
    meta=gpu.last_edge_meta
    eligible=np.asarray([s.get('merge_groups',True) for s in styles],bool)[owners]
    grouped=np.asarray([int(m) in membership for m in meta[:,0]],bool)
    candidate=np.flatnonzero(eligible & grouped & (meta[:,1]!=0) & ((meta[:,1]&~6)==0))
    if not len(candidate):return points,owners,dict(samples=0,suppressed_samples=0)
    ends=(pairs[candidate,:,:3]-cam['eye'])@cam['basis'].T
    depth_ok=np.all(ends[:,:,2]>cam['near'],axis=1)
    candidate=candidate[depth_ok];ends=ends[depth_ok]
    screen=_project(ends,cam);delta=screen[:,1]-screen[:,0]
    lengths=np.linalg.norm(delta,axis=1)
    valid=lengths>1e-8
    candidate=candidate[valid];ends=ends[valid];delta=delta[valid];lengths=lengths[valid]
    if not len(candidate):return points,owners,dict(samples=0,suppressed_samples=0)
    counts=np.clip(np.ceil(lengths),1,8192).astype(np.int64)
    normals=np.column_stack((-delta[:,1],delta[:,0]))/lengths[:,None]
    retained=np.ones(len(pairs),bool);retained[candidate]=False
    kept=[pairs[retained]];kept_owners=[owners[retained]]
    mesh_group=np.full(len(gpu.meshes),-1,np.int32)
    for group_id,group in enumerate(groups):
        for mesh in group['mesh_indices']:
            if mesh_group[mesh]<0:mesh_group[mesh]=group_id
    removed=0
    # Vectorize all projection/sample generation. Batches are bounded in CPU
    # memory and the GPU reader separately limits each ray allocation to 64K.
    cumulative=np.r_[0,np.cumsum(counts)]
    begin=0
    while begin<len(candidate):
        end=max(begin+1,int(np.searchsorted(cumulative,cumulative[begin]+32768,side='right')-1))
        end=min(end,len(candidate))
        n=counts[begin:end];starts=np.r_[0,np.cumsum(n)[:-1]]
        edge=np.repeat(np.arange(len(n)),n)
        t=(np.arange(int(n.sum()))-starts[edge]+.5)/n[edge]
        local=ends[begin:end]
        center=local[edge,0]+t[:,None]*(local[edge,1]-local[edge,0])
        screen=_project(center,cam)
        sides=(screen[:,None,:]+normals[begin:end][edge,None,:]*np.array([-1.,1.])[None,:,None]).reshape(-1,2)
        x=sides[:,0]-cam['width']/2;y=cam['height']/2-sides[:,1]
        if cam['ortho']:
            local=np.column_stack((x*cam['span']/cam['width'],y*cam['span']/cam['width'],np.zeros(len(x))))
            origin=cam['eye']+local@camera_to_world
            direction=np.tile(cam['forward'],(len(x),1))
        else:
            origin=np.tile(cam['eye'],(len(x),1))
            direction=np.column_stack((x/cam['focal'],y/cam['focal'],np.ones(len(x))))@camera_to_world
        hits=gpu.nearest_mesh(np.column_stack((origin,np.zeros(len(x)))),
                              np.column_stack((direction,np.zeros(len(x)))),cam['near'],cam['far']).reshape(-1,2)
        hit_groups=np.where(hits>=0,mesh_group[np.maximum(hits,0)],-1)
        source_indices=candidate[begin:end][edge]
        target_group=mesh_group[meta[source_indices,0]]
        suppress=np.all(hit_groups==target_group[:,None],axis=1)
        removed+=int(suppress.sum());visible=~suppress
        first=np.r_[True,edge[1:]!=edge[:-1]];last=np.r_[edge[1:]!=edge[:-1],True]
        run_start=np.flatnonzero(visible & (first|np.r_[True,~visible[:-1]]))
        run_end=np.flatnonzero(visible & (last|np.r_[~visible[1:],True]))+1
        if len(run_start):
            local_edge=edge[run_start]
            intervals=np.column_stack((run_start-starts[local_edge],run_end-starts[local_edge]))/n[local_edge,None]
            indices=candidate[begin:end][local_edge]
            segments=pairs[indices,0,None,:]+intervals[:,:,None]*(pairs[indices,1,None,:]-pairs[indices,0,None,:])
            kept.append(segments);kept_owners.append(owners[indices])
        begin=end
    return (np.concatenate(kept).reshape(-1,4),np.concatenate(kept_owners),
            dict(samples=int(counts.sum()),suppressed_samples=removed))
