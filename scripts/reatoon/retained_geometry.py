"""Camera-independent edge candidates for the retained GPU viewport.

Topology and static feature eligibility are prepared on geometry/style changes.
The draw shader evaluates front/back facing from current camera uniforms.
"""
import numpy as np
from .gpu_topology import prepare

FEATURES=('wireframe','open_edges','outline','crease','material_boundaries','hard_edges','selected_edges')
class UnsupportedRetained(ValueError):
    """Use the complete legacy GPU viewport for this topology or style."""


def candidates(mesh,face_styles,styles,selected_edges=None,cache=None):
    if cache is not None and 'evaluate' in cache and 'template' in cache:
        data=cache['template'];cache['evaluate'](mesh,data)
        return data
    p=cache.get('topology',mesh.get('_gpu_topology')) if cache is not None else None
    if p is None:
        p=prepare(mesh)
        if cache is not None:cache['topology']=p
    v=np.asarray(mesh['vertices'],np.float64)
    n=len(p['pairs']);pairs=np.concatenate((p['pairs'],p['diagonal_pairs']))
    incidence=p.get('retained_incidence')
    if incidence is None:
        locations=p['outline_indices'].reshape(-1)
        order=np.argsort(locations,kind='stable');ids=locations[order]
        starts=np.searchsorted(ids,np.arange(len(pairs)));ends=np.searchsorted(ids,np.arange(len(pairs)),side='right')
        incidence=p['retained_incidence']=(order,starts,ends)
    order,starts,ends=incidence
    counts=ends-starts
    # Non-manifold adjacency is handled explicitly by the existing GPU path;
    # never silently treat an arbitrary number of incident faces as two faces.
    if np.any(p['counts']>2) or np.any(counts>2):
        raise UnsupportedRetained('Retained edge shader requires at most two incident triangles (polygon maximum %d, triangle maximum %d)'%(p['counts'].max(),counts.max()))
    tri=p['triangles'];a=v[tri[:,0]];normals=np.cross(v[tri[:,1]]-a,v[tri[:,2]]-a)
    norm=np.linalg.norm(normals,axis=1);normals/=np.maximum(norm[:,None],1e-30)
    # Maya can omit degenerate source polygons from its triangulation. Their
    # incidence contributes no front-facing triangle, as in the OpenCL path.
    plane0=np.zeros((len(pairs),3),np.float64);plane1=plane0.copy()
    present=counts>0;plane0[present]=normals[order[starts[present]]//3]
    present=counts>1;plane1[present]=normals[order[ends[present]-1]//3]
    fs=np.asarray(face_styles,np.int32)
    adjacent=fs[p['owners']];adjacent=np.where(adjacent<0,2147483647,adjacent)
    own=np.minimum.reduceat(adjacent,p['starts'])
    selected=np.full(n,-3 if selected_edges is None else -2,np.int32)
    if selected_edges:
        keys=(p['pairs'][:,0].astype(np.uint64)<<np.uint64(32))|p['pairs'][:,1].astype(np.uint64)
        for style,edges in selected_edges.items():
            if not len(edges):continue
            edges=np.sort(np.asarray(edges,np.uint64),axis=1)
            q=(edges[:,0]<<np.uint64(32))|edges[:,1];indices=np.searchsorted(keys,q)
            valid=indices<len(keys);valid[valid]=keys[indices[valid]]==q[valid];indices=indices[valid]
            selected[indices]=np.where(selected[indices]<0,style,np.minimum(selected[indices],style))
    own=np.minimum(own,np.where(selected>=0,selected,2147483647))
    own[own==2147483647]=-1
    owners=np.r_[own,fs[p['diagonal_faces']]]
    features=np.r_[np.array([sum(1<<i for i,k in enumerate(FEATURES) if s.get(k,False)) for s in styles],np.int32),0]
    enabled=features[owners]
    meta=(p['metadata']&~64)|np.where(selected==-3,p['metadata']&64,np.where(selected==own,64,0))
    static=np.zeros(len(pairs),np.int32)
    static[:n]=(enabled[:n]&1)|np.where(p['counts']==1,enabled[:n]&2,0)|(meta&enabled[:n])
    if np.any(enabled[:n]&8):
        pv=v[p['flat']];following=np.arange(len(pv))+1;following[np.cumsum(p['face_counts'])-1]=p['face_starts']
        fn=np.add.reduceat(np.cross(pv,pv[following]),p['face_starts']);fn/=np.maximum(np.linalg.norm(fn,axis=1)[:,None],1e-30)
        first=fn[p['owners'][p['starts']]]
        dot=np.einsum('ij,ij->i',np.repeat(first,p['counts'],axis=0),fn[p['owners']])
        minimum=np.minimum.reduceat(dot,p['starts'])
        crease=np.r_[np.cos(np.radians([s.get('crease_angle',45.) for s in styles])),1.]
        angle_mask=(p['counts']>1)&(minimum<crease[own]-1e-8)
        if any(s.get('crease_angle_max',180.)<180. for s in styles):
            upper=np.r_[np.cos(np.radians([s.get('crease_angle_max',180.) for s in styles])),-1.]
            angle_mask &= minimum>=upper[own]-1e-8
        static[:n]|=np.where(angle_mask,enabled[:n]&8,0)
    dynamic=((enabled&4)!=0)&np.r_[p['counts']>1,np.ones(len(p['diagonal_pairs']),bool)]
    if cache is not None and 'evaluate' in cache and not any(s.get('crease') for s in styles):
        keep=(owners>=0)&((static!=0)|dynamic)
        triangles=np.full((len(pairs),6),-1,np.int32)
        present=counts>0;triangles[present,:3]=tri[order[starts[present]]//3]
        present=counts>1;triangles[present,3:]=tri[order[ends[present]-1]//3]
        size=int(keep.sum())
        data=dict(points=np.empty((size,2,3),np.float64),parameters=np.zeros((size,2,4),np.float32),
            topology=np.ascontiguousarray(np.c_[pairs,triangles][keep],np.int32),owners=owners[keep],dynamic=(static[keep]==0),static_flags=static[keep],edge_ids=np.flatnonzero(keep))
        data['normal0']=data['parameters'][:,0,:3];data['normal1']=data['parameters'][:,1,:3]
        cache['template']=data;cache['evaluate'](mesh,data)
        return data
    # Identical shader normals can never have opposite facing, for any camera.
    # Remove these provably inactive diagonals instead of uploading them every frame.
    dynamic &= np.any(plane0.astype(np.float32)!=plane1.astype(np.float32),axis=1)
    keep=(owners>=0)&((static!=0)|dynamic)
    return dict(points=np.ascontiguousarray(v[pairs[keep]]),owners=owners[keep],
                normal0=plane0[keep],normal1=plane1[keep],dynamic=(static[keep]==0),
                static_flags=static[keep],edge_ids=np.flatnonzero(keep))


def camera_mask(data,camera):
    """CPU oracle for shader tests; the interactive path uses GPU uniforms."""
    eye=np.asarray(camera['position'],np.float64)
    direction=(eye-np.asarray(camera['target']) if camera.get('projection')=='orthographic'
               else eye-data['points'][:,0])
    a=np.sum(data['normal0']*direction,axis=-1)>0
    b=np.sum(data['normal1']*direction,axis=-1)>0
    return ~data['dynamic']|(a!=b)
