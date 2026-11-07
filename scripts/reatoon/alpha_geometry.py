"""Texture isocontours -> conforming polygon cells, with no imaging dependency.

Cells use an even/odd fill, so disconnected islands and holes survive. They are
clipped to the original UV triangles and retain barycentric deformation binds.
Nothing here changes the Maya scene or the offline rendering backend.
"""
from collections import defaultdict
import numpy as np


def contours(alpha, threshold=.5, simplify=.25):
    a=np.asarray(alpha,np.float64)
    if a.ndim!=2 or not a.size or not np.isfinite(a).all():
        raise ValueError('Alpha must be a finite, nonempty 2D array')
    if not 0<threshold<1:raise ValueError('Alpha threshold must be between 0 and 1')
    if np.all(a<threshold):return []
    if np.all(a>=threshold):return [np.array([[0.,0.],[1.,0.],[1.,1.],[0.,1.]])]
    h,w=a.shape
    a=np.pad(a,1,constant_values=0)
    a[np.abs(a-threshold)<1e-7]=threshold+1e-7
    inside=a>=threshold
    codes=(inside[:-1,:-1].astype(np.uint8)+2*inside[:-1,1:].astype(np.uint8)+
           4*inside[1:,1:].astype(np.uint8)+8*inside[1:,:-1].astype(np.uint8))
    y,x=np.nonzero((codes!=0)&(codes!=15))
    if not len(x):return []
    values=np.stack((a[y,x],a[y,x+1],a[y+1,x+1],a[y+1,x]),axis=1)
    # Batch the same arithmetic, retaining the original row/edge order and
    # bottom-left UV origin. Only boundary cells need double-precision corners.
    pts=np.stack((np.column_stack((x-.5,h-y+.5)),np.column_stack((x+.5,h-y+.5)),
                  np.column_stack((x+.5,h-y-.5)),np.column_stack((x-.5,h-y-.5))),axis=1)
    crossings=(values>=threshold)!=np.roll(values>=threshold,-1,axis=1)
    coordinates=np.empty_like(pts)
    for i in range(4):
        j=(i+1)%4;use=crossings[:,i]
        t=(threshold-values[use,i])/(values[use,j]-values[use,i])
        coordinates[use,i]=pts[use,i]+t[:,None]*(pts[use,j]-pts[use,i])
    edges=np.arange(4);first=np.argmax(crossings,axis=1)
    last=np.max(np.where(crossings,edges,-1),axis=1);rows=np.arange(len(x))
    segments=np.empty((len(x),2,2,2),np.float64)
    segments[:,0,0]=coordinates[rows,first];segments[:,0,1]=coordinates[rows,last]
    saddle=crossings.sum(axis=1)==4
    # Preserve the bilinear asymptotic decider and its segment ordering.
    f=values[saddle]-threshold;q=f[:,0]*f[:,2]-f[:,1]*f[:,3]
    which=np.flatnonzero(saddle);positive=which[q>=0];negative=which[q<0]
    segments[positive,0]=coordinates[positive][:,[0,1]]
    segments[positive,1]=coordinates[positive][:,[2,3]]
    segments[negative,0]=coordinates[negative][:,[0,3]]
    segments[negative,1]=coordinates[negative][:,[1,2]]
    keep=np.column_stack((np.ones(len(x),bool),saddle)).ravel()
    segments=segments.reshape(-1,2,2)[keep]
    # One bulk rounding pass replaces two small NumPy calls per segment.
    keys=np.round(segments,10).tolist();points={};adj=defaultdict(list)
    for (a,b),(ka,kb) in zip(segments,keys):
        ka=tuple(ka);kb=tuple(kb)
        if ka==kb:continue
        points[ka]=a;points[kb]=b;adj[ka].append(kb);adj[kb].append(ka)
    if any(len(v)!=2 for v in adj.values()):
        # Exact samples equal to the threshold can create a four-way junction.
        raise ValueError('Degenerate alpha contour; change the threshold slightly')
    remaining=set(adj);loops=[]
    # Keep the same deterministic start/order without repeatedly scanning every
    # unvisited vertex for each small hole in a foliage texture.
    for first in sorted(adj):
        if first not in remaining:continue
        key=first;previous=None;loop=[]
        while True:
            loop.append(points[key]);remaining.discard(key)
            following=next(k for k in adj[key] if k!=previous)
            previous,key=key,following
            if key==first:break
        p=np.asarray(loop)
        if len(p)<3:continue
        if simplify>0 and len(p)>4:
            # Split a closed loop at widely separated vertices before RDP.
            split=int(np.argmax(np.sum((p-p[0])**2,axis=1)))
            p=np.concatenate((_rdp(p[:split+1],simplify)[:-1],
                              _rdp(np.concatenate((p[split:],p[:1])),simplify)[:-1]))
        p=np.clip(p/np.array([w,h]),0,1)
        p=_clean(p)
        if len(p)>=3:loops.append(p)
    return loops


def _rdp(p,epsilon):
    if len(p)<3:return p
    d=p[-1]-p[0];length=float(d@d)
    t=np.clip((p-p[0])@d/max(length,1e-30),0,1)
    distance=np.linalg.norm(p-(p[0]+t[:,None]*d),axis=1)
    i=int(np.argmax(distance))
    if distance[i]<=epsilon:return p[[0,-1]]
    return np.concatenate((_rdp(p[:i+1],epsilon)[:-1],_rdp(p[i:],epsilon)))


def _clean(p):
    p=np.asarray(p,np.float64).reshape(-1,2)
    if len(p):p=p[np.linalg.norm(p-np.roll(p,1,axis=0),axis=1)>1e-10]
    return p


def filled_cells(loops):
    """Vertical trapezoids, conforming at every shared vertical side."""
    if not loops:return []
    aa=np.concatenate(loops);bb=np.concatenate([np.roll(p,-1,axis=0) for p in loops])
    xs=np.unique(np.round(aa[:,0],12));quads=[];side_points=defaultdict(set)
    for x0,x1 in zip(xs[:-1],xs[1:]):
        if x1-x0<1e-11:continue
        mid=(x0+x1)*.5
        use=((aa[:,0]<mid)&(bb[:,0]>mid))|((bb[:,0]<mid)&(aa[:,0]>mid))
        a,b=aa[use],bb[use]
        slope=(b[:,1]-a[:,1])/(b[:,0]-a[:,0])
        order=np.argsort(a[:,1]+(mid-a[:,0])*slope)
        if len(order)%2:raise ValueError('Open alpha contour cannot be filled')
        for low,high in order.reshape(-1,2):
            y0=a[:,1]+(x0-a[:,0])*slope;y1=a[:,1]+(x1-a[:,0])*slope
            q=np.array([[x0,y0[low]],[x1,y1[low]],[x1,y1[high]],[x0,y0[high]]])
            quads.append(q)
            for x,y in q:side_points[round(x,12)].add(round(y,12))
    sides={x:np.array(sorted(values)) for x,values in side_points.items()}
    result=[]
    for q in quads:
        polygon=[]
        for a,b in zip(q,np.roll(q,-1,axis=0)):
            polygon.append(a)
            if abs(a[0]-b[0])<1e-11:
                ys=sides[round(a[0],12)]
                ys=ys[(ys>min(a[1],b[1])+1e-10)&(ys<max(a[1],b[1])-1e-10)]
                if b[1]<a[1]:ys=ys[::-1]
                polygon.extend((a[0],y) for y in ys)
        polygon=_clean(polygon)
        if len(polygon)>=3:result.append(polygon)
    return result


def _cross(a,b):return a[...,0]*b[...,1]-a[...,1]*b[...,0]


def clip_polygon(p,triangle):
    sign=1 if _cross(triangle[1]-triangle[0],triangle[2]-triangle[0])>0 else -1
    for a,b in zip(triangle,np.roll(triangle,-1,axis=0)):
        if not len(p):break
        d=sign*_cross(b-a,p-a);q=[]
        for i in range(len(p)):
            j=(i+1)%len(p);inside=d[i]>=-1e-11;next_inside=d[j]>=-1e-11
            if inside:q.append(p[i])
            if inside!=next_inside:q.append(p[i]+(d[i]/(d[i]-d[j]))*(p[j]-p[i]))
        p=_clean(q)
    return p


def triangulate_uv(triangle,cells,wrap=True,_bounds=None):
    """Return filled convex polygons in the triangle, as barycentric weights."""
    uv=np.asarray(triangle,np.float64)
    if not wrap and (np.min(uv)<-1e-10 or np.max(uv)>1+1e-10):
        raise ValueError('Non-wrapping alpha UVs outside 0–1 require baking to an image first')
    basis=np.stack((uv[1]-uv[0],uv[2]-uv[0]),axis=1)
    if abs(np.linalg.det(basis))<1e-14:raise ValueError('Alpha boundary requires non-degenerate UV triangles')
    inverse=np.linalg.inv(basis);result=[]
    low=np.floor(uv.min(axis=0)).astype(int);high=np.ceil(uv.max(axis=0)).astype(int)
    tiles=[(0,0)] if not wrap else [(x,y) for x in range(low[0],max(low[0]+1,high[0]))
                                  for y in range(low[1],max(low[1]+1,high[1]))]
    if len(tiles)>256:raise ValueError('Alpha UV tiling exceeds 256 tiles per source triangle')
    for shift in tiles:
        t=uv-np.asarray(shift)
        lo=t.min(axis=0);hi=t.max(axis=0)
        contained=None;rejected=None
        if isinstance(cells,np.ndarray):
            lower,upper=_bounds if _bounds is not None else (cells.min(axis=1),cells.max(axis=1))
            selected=cells[np.all(upper>=lo-1e-10,axis=1)&np.all(lower<=hi+1e-10,axis=1)]
            # Most small opacity triangles are wholly inside one source UV
            # triangle. Preserve their exact vertices instead of clipping them
            # three times. Near-duplicate vertices still use the original path.
            sign=1 if _cross(t[1]-t[0],t[2]-t[0])>0 else -1
            contained=np.ones(len(selected),bool);rejected=np.zeros(len(selected),bool)
            for a,b in zip(t,np.roll(t,-1,axis=0)):
                inside=sign*_cross(b-a,selected-a)>=-1e-11
                # Reject only before any edge would clip the original polygon.
                # This is exactly the old clipper's empty result, including its
                # tolerance, without assumptions about intermediate rounding.
                rejected |= contained & ~np.any(inside,axis=1)
                contained &= np.all(inside,axis=1)
            contained &= np.all(np.linalg.norm(selected-np.roll(selected,1,axis=1),axis=2)>1e-10,axis=1)
        else:selected=[c for c in cells if np.all(c.max(axis=0)>=lo-1e-10) and np.all(c.min(axis=0)<=hi+1e-10)]
        for index,cell in enumerate(selected):
            if rejected is not None and rejected[index]:continue
            p=cell if contained is not None and contained[index] else clip_polygon(cell,t)
            if len(p)<3:continue
            area=abs(np.sum(_cross(p,np.roll(p,-1,axis=0))))
            if area<1e-15:continue
            xy=(p+shift-uv[0])@inverse.T
            bary=np.column_stack((1-xy.sum(axis=1),xy))
            if _cross(uv[1]-uv[0],uv[2]-uv[0])<0:bary=bary[::-1]
            result.append(bary)
    return result


def cut_mesh(vertices,triangles,triangle_faces,triangle_uvs,face_cells,wrap=True):
    """Build cutout topology; map every output vertex to three source vertices."""
    vertices=np.asarray(vertices,np.float64);triangles=np.asarray(triangles,np.int64)
    points=[];bind_ids=[];bind_weights=[];faces=[];source_faces=[];lookup={};templates={};bounds={}
    def vertex(ids,weights):
        # The sparse original-vertex binding also welds across triangle/UV seams.
        values={int(i):float(w) for i,w in zip(ids,weights) if abs(w)>1e-9}
        key=tuple(sorted((i,round(w,9)) for i,w in values.items()))
        if key not in lookup:
            lookup[key]=len(points);points.append(weights@vertices[ids]);bind_ids.append(ids);bind_weights.append(weights)
        return lookup[key]
    for ids,face,uv in zip(triangles,triangle_faces,triangle_uvs):
        cells=face_cells.get(int(face))
        if cells is None:polygons=[np.eye(3)]
        else:
            key=(id(cells),tuple(np.round(np.asarray(uv).ravel(),12)),wrap)
            if key not in templates:
                if isinstance(cells,np.ndarray) and id(cells) not in bounds:
                    bounds[id(cells)]=(cells.min(axis=1),cells.max(axis=1))
                templates[key]=triangulate_uv(uv,cells,wrap,_bounds=bounds.get(id(cells)))
            polygons=templates[key]
        for weights in polygons:
            poly=[vertex(ids,w) for w in weights]
            # Source winding is preserved by the barycentric polygon ordering.
            if len(set(poly))<3:continue
            faces.append(poly);source_faces.append(int(face))
    tris=[];tfaces=[]
    # Center fans retain collinear side vertices, avoiding T-junctions/open edges.
    for fi,face in enumerate(faces):
        if len(face)==3:tris.append(face);tfaces.append(fi);continue
        center=len(points);points.append(np.mean([points[v] for v in face],axis=0))
        # All corners lie in one source triangle, but a welded corner may have
        # a different equivalent triangle binding. Recover the center directly.
        # Bind the center through averaging sparse corner contributions.
        sparse=defaultdict(float)
        for vi in face:
            for i,w in zip(bind_ids[vi],bind_weights[vi]):sparse[int(i)]+=float(w)/len(face)
        sparse={i:w for i,w in sparse.items() if abs(w)>1e-9}
        if len(sparse)>3:raise ValueError('Alpha cell crosses an untracked source triangle')
        ids=list(sparse);weights=list(sparse.values())
        while len(ids)<3:ids.append(ids[0]);weights.append(0.)
        bind_ids.append(ids);bind_weights.append(weights)
        for a,b in zip(face,face[1:]+face[:1]):tris.append([center,a,b]);tfaces.append(fi)
    return dict(vertices=np.asarray(points,np.float64).reshape(-1,3),faces=faces,
        triangles=np.asarray(tris,np.int32).reshape(-1,3),triangle_faces=np.asarray(tfaces,np.int32),
        source_faces=np.asarray(source_faces,np.int32),
        bind_ids=np.asarray(bind_ids,np.int64).reshape(-1,3),bind_weights=np.asarray(bind_weights,np.float64).reshape(-1,3))
