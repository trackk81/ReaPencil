"""Bulk topology preparation; all animated geometric tests stay on the GPU."""
import numpy as np


def prepare(mesh):
    faces=mesh['faces']
    counts=(np.full(len(faces),faces.shape[1],np.int64)
            if isinstance(faces,np.ndarray) and faces.ndim==2 else
            np.asarray([len(face) for face in faces],np.int64))
    try:flat=np.asarray(faces,np.int32).reshape(-1)
    except ValueError:flat=np.concatenate(faces).astype(np.int32)
    if not len(counts) or np.any(counts<3):raise ValueError('GPU mesh requires polygon faces')
    starts=np.cumsum(counts)-counts
    following=np.arange(len(flat))+1;following[np.cumsum(counts)-1]=starts
    lower=np.minimum(flat,flat[following]);upper=np.maximum(flat,flat[following])
    codes=(lower.astype(np.uint64)<<np.uint64(32))|upper.astype(np.uint64)
    order=np.argsort(codes,kind='stable');sorted_codes=codes[order]
    first=np.r_[0,np.flatnonzero(sorted_codes[1:]!=sorted_codes[:-1])+1]
    keys=sorted_codes[first];edge_counts=np.diff(np.r_[first,len(codes)])
    owners=np.repeat(np.arange(len(faces),dtype=np.int32),counts)[order]
    material_ids=np.asarray(mesh.get('material_ids',np.zeros(len(faces),np.int32)))[owners]
    material=np.minimum.reduceat(material_ids,first)!=np.maximum.reduceat(material_ids,first)
    def marked(name):
        entries=mesh.get(name,[])
        if not len(entries):return np.zeros(len(keys),bool)
        rows=np.sort(np.asarray(entries,np.uint64).reshape(-1,2),axis=1)
        return np.isin(keys,(rows[:,0]<<np.uint64(32))|rows[:,1])
    pairs=np.column_stack((keys>>np.uint64(32),keys&np.uint64(0xffffffff))).astype(np.int32)
    triangles=mesh.get('triangles');triangle_faces=mesh.get('triangle_faces')
    if triangles is None:
        triangles=[];triangle_faces=[]
        for face_id,face in enumerate(faces):
            for corner in range(1,len(face)-1):
                triangles.append([face[0],face[corner],face[corner+1]]);triangle_faces.append(face_id)
    triangles=np.asarray(triangles,np.int32).reshape(-1,3)
    triangle_faces=np.asarray(triangle_faces,np.int32)
    edges=triangles[:,[[0,1],[1,2],[2,0]]].reshape(-1,2)
    edges.sort(axis=1)
    triangle_keys=(edges[:,0].astype(np.uint64)<<np.uint64(32))|edges[:,1].astype(np.uint64)
    locations=np.searchsorted(keys,triangle_keys)
    original=locations<len(keys)
    original[original]=keys[locations[original]]==triangle_keys[original]
    diagonal_indices=np.flatnonzero(~original)
    diagonal_faces=np.repeat(triangle_faces,3)[diagonal_indices]
    diagonal_keys=triangle_keys[diagonal_indices]
    # Group a diagonal by both endpoints AND its polygon owner. Coincident
    # triangulations of distinct polygons must never cancel one another.
    diagonal_order=np.lexsort((diagonal_faces,diagonal_keys))
    dk=diagonal_keys[diagonal_order];df=diagonal_faces[diagonal_order]
    if len(dk):
        dfirst=np.r_[0,np.flatnonzero((dk[1:]!=dk[:-1])|(df[1:]!=df[:-1]))+1]
        groups=np.cumsum(np.r_[True,(dk[1:]!=dk[:-1])|(df[1:]!=df[:-1])])-1
        locations[diagonal_indices[diagonal_order]]=len(keys)+groups
        dkeys=dk[dfirst];dfaces=df[dfirst]
        dpairs=np.column_stack((dkeys>>np.uint64(32),dkeys&np.uint64(0xffffffff))).astype(np.int32)
    else:dpairs=np.empty((0,2),np.int32);dfaces=np.empty(0,np.int32)
    return dict(pairs=pairs,starts=first,counts=edge_counts,owners=owners,
                metadata=material.astype(np.int32)*16+marked('hard_edges')*32+marked('selected_edges')*64,
                flat=flat,face_starts=starts,face_counts=counts,triangles=triangles,
                triangle_faces=triangle_faces,outline_indices=locations.reshape(-1,3),
                diagonal_pairs=dpairs,diagonal_faces=dfaces)
