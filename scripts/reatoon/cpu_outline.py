"""Actual rendered-triangle silhouette candidates on polygonal meshes.

Original boundary features retain their polygon topology. Added triangulation
edges are returned separately and carry only outline semantics.
"""
import numpy as np


def outline_edges(mesh,camera,prepared_original_edges):
    vertices=np.asarray(mesh['vertices'],np.float64)
    triangles=np.asarray(mesh['triangles'],np.int64).reshape(-1,3)
    face_ids=np.asarray(mesh['triangle_faces'],np.int64)
    original=np.asarray(prepared_original_edges['pairs'],np.int64).reshape(-1,2)
    mask=np.zeros(len(original),np.bool_)
    empty=np.empty((0,2),np.int64)
    if not len(triangles):return mask,empty,np.empty(0,np.int64)
    if len(vertices)>=2**32 or triangles.min()<0 or triangles.max()>=len(vertices):
        raise ValueError('Outline triangle indices exceed valid uint32 vertex range')
    if len(face_ids)!=len(triangles):raise ValueError('Outline triangle face IDs must match triangles')
    p=vertices[triangles]
    normal=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0])
    view=-np.asarray(camera['forward']) if camera['ortho'] else np.asarray(camera['eye'])-p[:,0]
    front=np.sum(normal*view,axis=1)>0
    chosen=triangles[front]
    if not len(chosen):return mask,empty,np.empty(0,np.int64)
    edges=np.concatenate((chosen[:,[0,1]],chosen[:,[1,2]],chosen[:,[2,0]]))
    edges.sort(axis=1)
    codes=(edges[:,0].astype(np.uint64)<<np.uint64(32))|edges[:,1].astype(np.uint64)
    ordering=np.argsort(codes,kind='stable')
    sorted_codes=codes[ordering]
    starts=np.r_[0,np.flatnonzero(sorted_codes[1:]!=sorted_codes[:-1])+1]
    unique=sorted_codes[starts];first=ordering[starts]
    counts=np.diff(np.r_[starts,len(codes)])
    original_codes=(original[:,0].astype(np.uint64)<<np.uint64(32))|original[:,1].astype(np.uint64)
    # prepared polygon pairs are lexicographically sorted by their builder.
    locations=np.searchsorted(original_codes,unique)
    matches=locations<len(original_codes)
    if len(original_codes):matches[matches]=original_codes[locations[matches]]==unique[matches]
    selected=locations[matches]
    total=np.asarray(prepared_original_edges['counts'])
    mask[selected]=(counts[matches]>0)&(counts[matches]<total[selected])&(total[selected]>1)
    diagonals=(~matches)&(counts==1)
    keys=unique[diagonals]
    pairs=np.column_stack((keys>>np.uint64(32),keys&np.uint64(0xffffffff))).astype(np.int64)
    owners=np.tile(face_ids[front],3)
    result_faces=owners[first[diagonals]]
    # A vertex pair may be an internal diagonal in several distinct polygons.
    # Its two-sided incidence belongs to each polygon separately, not to an
    # artificial nonmanifold connection between coincident triangulations.
    sorted_owners=owners[ordering]
    low_owner=np.minimum.reduceat(sorted_owners,starts)
    high_owner=np.maximum.reduceat(sorted_owners,starts)
    unusual=np.flatnonzero((~matches)&(counts>1)&(low_owner!=high_owner))
    extra_pairs=[];extra_faces=[]
    for index in unusual:
        face,count=np.unique(sorted_owners[starts[index]:starts[index]+counts[index]],return_counts=True)
        key=unique[index]
        pair=[int(key>>np.uint64(32)),int(key&np.uint64(0xffffffff))]
        for owner in face[count==1]:extra_pairs.append(pair);extra_faces.append(owner)
    if extra_pairs:
        pairs=np.concatenate((pairs,np.asarray(extra_pairs,np.int64)))
        result_faces=np.concatenate((result_faces,np.asarray(extra_faces,np.int64)))
        order=np.lexsort((result_faces,pairs[:,1],pairs[:,0]))
        pairs=pairs[order];result_faces=result_faces[order]
    return mask,pairs,result_faces
