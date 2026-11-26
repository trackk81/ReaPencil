"""Exact contour/UV intersection without retaining mask triangulation seams.

The threshold and simplified contours are unchanged. Only interior tessellation
is replaced; surfaces, holes, original triangle boundaries and binds remain.
"""
import numpy as np
from . import alpha_geometry as geometry
from . import alpha_tessellation as tess


def _conform(pieces, contour_points):
    """Split collinear T-junctions GLU encodes using zero-area triangles.

    Removing those degenerate triangles alone exposes false open edges. Keep
    the same surface by splitting only affected triangles, not every mask cell.
    Contour vertices also keep both sides of a source UV seam conforming.
    """
    if not len(pieces):return pieces
    flat=pieces.reshape(-1,2)
    _,first,inverse=np.unique(np.round(flat,12),axis=0,return_index=True,return_inverse=True)
    vertices=flat[first];tri=inverse.reshape(-1,3)
    pairs=np.sort(np.concatenate((tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]])),axis=1)
    edges,counts=np.unique(pairs,axis=0,return_counts=True)
    points=np.concatenate((vertices,contour_points))
    _,first=np.unique(np.round(points,12),axis=0,return_index=True);points=points[first]
    orders=[np.argsort(points[:,axis]) for axis in (0,1)]
    sorted_axes=[points[order,axis] for axis,order in enumerate(orders)]
    splits={}
    for a,b in edges[counts==1]:
        p,q=vertices[a],vertices[b];delta=q-p;length2=delta@delta
        if length2<1e-24:continue
        lo=np.minimum(p,q)-1e-11;hi=np.maximum(p,q)+1e-11
        starts=[np.searchsorted(sorted_axes[j],lo[j],side='left') for j in (0,1)]
        ends=[np.searchsorted(sorted_axes[j],hi[j],side='right') for j in (0,1)]
        axis=0 if ends[0]-starts[0]<ends[1]-starts[1] else 1
        candidates=points[orders[axis][starts[axis]:ends[axis]]]
        t=((candidates-p)@delta)/length2
        on=(t>1e-10)&(t<1-1e-10)&(np.abs(geometry._cross(delta,candidates-p))<1e-11*np.sqrt(length2))
        if np.any(on):
            chosen=candidates[on];splits[(int(a),int(b))]=chosen[np.argsort(t[on])]
    if not splits:return pieces
    result=[]
    for ids,original in zip(tri,pieces):
        polygon=[];changed=False
        for a,b in zip(ids,np.roll(ids,-1)):
            polygon.append(vertices[a]);extra=splits.get((min(a,b),max(a,b)))
            if extra is not None:
                polygon.extend(extra if a<b else extra[::-1]);changed=True
        if changed:
            polygon=np.asarray(polygon);center=original.mean(axis=0)
            result.extend(np.stack((np.repeat(center[None],len(polygon),axis=0),polygon,np.roll(polygon,-1,axis=0)),axis=1))
        else:result.append(original)
    return np.asarray(result)


class Region:
    def __init__(self, loops):
        self.loops = []
        if not loops: return
        areas=np.array([np.sum(geometry._cross(p,np.roll(p,-1,axis=0)))*.5 for p in loops])
        bounds=np.array([[p.min(axis=0),p.max(axis=0)] for p in loops])
        parents=[]
        for i,p in enumerate(loops):
            point=p[0]
            ids=np.flatnonzero((np.abs(areas)>abs(areas[i])+1e-14)&
                np.all(bounds[:,0]<point+1e-10,axis=1)&np.all(bounds[:,1]>point-1e-10,axis=1))
            parent=-1
            for j in sorted(ids,key=lambda j:abs(areas[j])):
                a=loops[j];b=np.roll(a,-1,axis=0)
                active=(a[:,1]>point[1])!=(b[:,1]>point[1]);a,b=a[active],b[active]
                x=a[:,0]+(point[1]-a[:,1])*(b[:,0]-a[:,0])/(b[:,1]-a[:,1])
                if np.count_nonzero(x>point[0])%2: parent=int(j);break
            parents.append(parent)
        for i,parent in enumerate(parents):
            depth=0
            while parent>=0: depth+=1;parent=parents[parent]
            self.loops.append(loops[i] if (areas[i]>0)==(depth%2==0) else loops[i][::-1])
        self.bounds=bounds

    def clip(self, uv, wrap):
        uv=np.asarray(uv,np.float64)
        basis=np.stack((uv[1]-uv[0],uv[2]-uv[0]),axis=1)
        determinant=np.linalg.det(basis)
        if abs(determinant)<1e-14: raise ValueError('Alpha boundary requires non-degenerate UV triangles')
        if not wrap and (uv.min()<-1e-10 or uv.max()>1+1e-10):
            raise ValueError('Non-wrapping alpha UVs outside 0–1 require baking to an image first')
        if not self.loops:return np.empty((0,3,3),np.float64)
        low=np.floor(uv.min(axis=0)).astype(int);high=np.ceil(uv.max(axis=0)).astype(int)
        size=np.maximum(1,high-low)
        if wrap and int(size[0])*int(size[1])>256:raise ValueError('Alpha UV tiling exceeds 256 tiles per source triangle')
        shifts=[(0,0)] if not wrap else [(x,y) for x in range(low[0],low[0]+size[0]) for y in range(low[1],low[1]+size[1])]
        result=[];inverse=np.linalg.inv(basis)
        for shift in shifts:
            t=uv-np.asarray(shift);lo=t.min(axis=0);hi=t.max(axis=0)
            ids=np.flatnonzero(np.all(self.bounds[:,1]>=lo,axis=1)&np.all(self.bounds[:,0]<=hi,axis=1))
            if not len(ids):continue
            # Alpha has signed winding 0/1; the source triangle adds one.
            # ABS_GEQ_TWO therefore fills precisely their intersection.
            triangle=t if determinant>0 else t[::-1]
            pieces=tess.triangulate([self.loops[i] for i in ids]+[triangle],winding_rule=100134,accurate_intersections=True)
            if not len(pieces):continue
            area=np.abs(geometry._cross(pieces[:,1]-pieces[:,0],pieces[:,2]-pieces[:,0]))
            pieces=pieces[area>=1e-15]
            pieces=_conform(pieces,np.concatenate([self.loops[i] for i in ids]+[triangle]))
            xy=(pieces+shift-uv[0])@inverse.T
            weights=np.concatenate((1-xy.sum(axis=2,keepdims=True),xy),axis=2)
            if determinant<0:weights=weights[:,::-1]
            result.append(weights)
        return np.concatenate(result) if result else np.empty((0,3,3),np.float64)


def cut_mesh(vertices, triangles, triangle_faces, triangle_uvs, face_regions, wrap=True, triangle_budget=None):
    """Batch repeated UV templates and weld via sparse source-vertex bindings."""
    vertices=np.asarray(vertices,np.float64);triangles=np.asarray(triangles,np.int64)
    tf=np.asarray(triangle_faces,np.int32);uvs=np.asarray(triangle_uvs,np.float64)
    groups={}
    for i,(face,uv) in enumerate(zip(tf,uvs)):
        region=face_regions.get(int(face))
        key=(id(region),np.round(uv,12).tobytes()) if region is not None else (0,b'')
        if key not in groups:groups[key]=[region,uv,[]]
        groups[key][2].append(i)
    all_ids=[];all_weights=[];all_tris=[];source_faces=[];offset=0;count=0
    for region,uv,indices in groups.values():
        weights=region.clip(uv,wrap) if region is not None else np.eye(3)[None]
        if not len(weights):continue
        count+=len(indices)*len(weights)
        if triangle_budget is not None and count>triangle_budget:
            raise ValueError('Alpha cutout exceeds the preview triangle budget (%d)'%triangle_budget)
        flat=weights.reshape(-1,3)
        _,first,inverse=np.unique(np.round(flat,12),axis=0,return_index=True,return_inverse=True)
        unique=flat[first];local=inverse.reshape(-1,3)
        # Limit temporary broadcasting to a modest number of vertices.
        block=max(1,262144//len(unique))
        for start in range(0,len(indices),block):
            chosen=np.asarray(indices[start:start+block],np.int64);n=len(chosen);nv=len(unique)
            all_ids.append(np.repeat(triangles[chosen],nv,axis=0))
            all_weights.append(np.tile(unique,(n,1)))
            all_tris.append((local[None]+np.arange(n)[:,None,None]*nv+offset).reshape(-1,3))
            source_faces.append(np.repeat(tf[chosen],len(local)));offset+=n*nv
    if not all_ids:
        return dict(vertices=np.empty((0,3)),faces=[],triangles=np.empty((0,3),np.int32),triangle_faces=np.empty(0,np.int32),
            source_faces=np.empty(0,np.int32),bind_ids=np.empty((0,3),np.int64),bind_weights=np.empty((0,3)))
    ids=np.concatenate(all_ids);weights=np.concatenate(all_weights)
    # Same nine-decimal sparse bind identity as the established cutout path.
    active=np.abs(weights)>1e-9
    sparse_ids=np.where(active,ids,-1);order=np.argsort(sparse_ids,axis=1)
    key=np.empty((len(ids),6),np.int64)
    key[:,:3]=np.take_along_axis(sparse_ids,order,axis=1)
    key[:,3:]=np.rint(np.take_along_axis(np.where(active,weights,0.),order,axis=1)*1e9).astype(np.int64)
    _,first,inverse=np.unique(key,axis=0,return_index=True,return_inverse=True)
    ids=ids[first];weights=weights[first]
    tris=inverse[np.concatenate(all_tris)].astype(np.int32)
    faces=np.concatenate(source_faces)
    valid=(tris[:,0]!=tris[:,1])&(tris[:,1]!=tris[:,2])&(tris[:,2]!=tris[:,0]);tris=tris[valid];faces=faces[valid]
    return dict(vertices=np.einsum('ij,ijk->ik',weights,vertices[ids]),faces=tris.tolist(),triangles=tris,
        triangle_faces=np.arange(len(tris),dtype=np.int32),source_faces=faces,bind_ids=ids,bind_weights=weights)


def source_edge_map(triangles, bind_ids, bind_weights):
    """Only source-edge vertices can contribute to authored-edge descendants."""
    ids=np.asarray(bind_ids,np.int64);active=np.abs(bind_weights)>1e-9
    supported=active.sum(axis=1)<=2
    sparse=np.where(active,ids,-1);result={}
    for start in range(0,len(triangles),65536):
        tri=np.asarray(triangles[start:start+65536],np.int64)
        a=tri.reshape(-1);b=np.roll(tri,-1,axis=1).reshape(-1)
        keep=supported[a]&supported[b];a=a[keep];b=b[keep]
        if not len(a):continue
        support=np.concatenate((sparse[a],sparse[b]),axis=1)
        low=np.where(support>=0,support,np.iinfo(np.int64).max).min(axis=1);high=support.max(axis=1)
        keep=(low!=high)&np.all((support<0)|(support==low[:,None])|(support==high[:,None]),axis=1)
        rows=np.unique(np.column_stack((low[keep],high[keep],np.minimum(a[keep],b[keep]),np.maximum(a[keep],b[keep]))),axis=0)
        for lo,hi,ea,eb in rows:result.setdefault((int(lo),int(hi)),set()).add((int(ea),int(eb)))
    return result
