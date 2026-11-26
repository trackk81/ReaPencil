"""Retain source cards; share exact opacity contours between CPU rays and lines.

No tessellated leaf interiors are created. Textures and repeated UV templates
are shared; contour positions are expanded only for camera-visible triangles.
"""
import ctypes as c
import numpy as np


class Mask(c.Structure):
    _fields_=[('edges',c.c_void_p),('starts',c.c_void_p),('ids',c.c_void_p),('bins',c.c_int64),('grid',c.c_void_p),('size',c.c_int64)]


class Scene(c.Structure):
    _fields_=[(k,c.c_void_p) for k in ('lookup','uv','masks','wrap','regions')]


class Region:
    def __init__(self, region):
        self.loops=region.loops
        self.edges=np.ascontiguousarray(np.concatenate([np.stack((p,np.roll(p,-1,axis=0)),axis=1) for p in self.loops]) if self.loops else np.empty((0,2,2)),np.float64)
        bins=512;rows=[[] for _ in range(bins)]
        for i,e in enumerate(self.edges):
            lo,hi=np.clip(np.floor(np.sort(e[:,1])*bins).astype(int),0,bins-1)
            for b in range(lo,hi+1):rows[b].append(i)
        self.starts=np.r_[0,np.cumsum([len(r) for r in rows])].astype(np.int64)
        self.ids=np.concatenate(rows).astype(np.int32) if self.starts[-1] else np.empty(0,np.int32)
        # Exact acceleration: cells touched by any contour always use the
        # original polygon test. Only certified homogeneous cells are cached.
        from .native_cpu import alpha_grid
        size=2048
        grid=alpha_grid(Mask(self.edges.ctypes.data,self.starts.ctypes.data,self.ids.ctypes.data,bins,None,size),size)
        self.grid=grid
        self.native=Mask(self.edges.ctypes.data,self.starts.ctypes.data,self.ids.ctypes.data,bins,grid.ctypes.data,size)
        self.templates={};self.interval_cache={}

    def contains(self, points, wrap=True):
        points=np.asarray(points,np.float64).reshape(-1,2)
        if wrap:points=points-np.floor(points)
        result=np.zeros(len(points),bool)
        for i,(x,y) in enumerate(points):
            if not (0<=x<=1 and 0<=y<=1):continue
            b=min(511,max(0,int(y*512)));e=self.edges[self.ids[self.starts[b]:self.starts[b+1]]]
            delta=e[:,1]-e[:,0];relative=np.array([x,y])-e[:,0]
            cross=delta[:,0]*relative[:,1]-delta[:,1]*relative[:,0]
            on=(np.abs(cross)<=1e-12*np.abs(delta).sum(axis=1))&np.all(np.array([x,y])>=e.min(axis=1)-1e-12,axis=1)&np.all(np.array([x,y])<=e.max(axis=1)+1e-12,axis=1)
            if np.any(on):result[i]=True;continue
            active=(e[:,0,1]>y)!=(e[:,1,1]>y);p,q=e[active,0],e[active,1]
            result[i]=np.count_nonzero(p[:,0]+(y-p[:,1])*(q[:,0]-p[:,0])/(q[:,1]-p[:,1])>x)%2
        return result

    def tiled_edges(self,uv,wrap):
        if not wrap:
            if uv.min()<-1e-10 or uv.max()>1+1e-10:raise ValueError('Non-wrapping alpha UVs outside 0–1')
            return self.edges
        lo=np.floor(uv.min(axis=0)).astype(int);hi=np.maximum(lo+1,np.ceil(uv.max(axis=0)).astype(int))
        if np.prod(hi-lo)>256:raise ValueError('Alpha UV tiling exceeds 256 tiles per source triangle')
        return np.concatenate([self.edges+np.array([x,y]) for x in range(lo[0],hi[0]) for y in range(lo[1],hi[1])])

    def boundary(self, uv, wrap):
        key=(uv.tobytes(),wrap)
        if key in self.templates:return self.templates[key]
        basis=np.stack((uv[1]-uv[0],uv[2]-uv[0]),axis=1)
        if abs(np.linalg.det(basis))<1e-14:
            # A collapsed UV triangle can still cross an opacity boundary.
            # Its preimage is a straight segment on the original card.
            pairs=((0,1),(1,2),(2,0));i,j=max(pairs,key=lambda p:np.sum((uv[p[1]]-uv[p[0]])**2))
            d=uv[j]-uv[i];length=d@d
            if length<1e-28:return np.empty((0,2,3))
            coordinate=(uv-uv[i])@d/length;out=[]
            cuts={t for interval in self.intervals(uv[[i,j]],wrap) for t in interval if 1e-12<t<1-1e-12}
            for t in sorted(cuts):
                hits=[]
                for p,q in pairs:
                    delta=coordinate[q]-coordinate[p]
                    if abs(delta)<1e-14:continue
                    f=(t-coordinate[p])/delta
                    if -1e-12<=f<=1+1e-12:
                        v=np.zeros(3);v[p]=1-f;v[q]=f
                        if not any(np.allclose(v,h,rtol=0,atol=1e-12) for h in hits):hits.append(v)
                if len(hits)==2:out.append(hits)
            return np.asarray(out,np.float64).reshape(-1,2,3)
        edges=self.tiled_edges(uv,wrap)
        xy=(edges-uv[0])@np.linalg.inv(basis).T
        bary=np.concatenate((1-xy.sum(axis=2,keepdims=True),xy),axis=2)
        a=bary[:,0];delta=bary[:,1]-a;lo=np.zeros(len(a));hi=np.ones(len(a));valid=np.ones(len(a),bool)
        for j in range(3):
            d=delta[:,j];moving=np.abs(d)>1e-14
            t=np.divide(-a[:,j],d,out=np.zeros_like(d),where=moving)
            lo=np.where(d>1e-14,np.maximum(lo,t),lo);hi=np.where(d< -1e-14,np.minimum(hi,t),hi)
            valid&=moving|(a[:,j]>=-1e-10)
        valid&=hi-lo>1e-12
        out=a[valid,None]+delta[valid,None]*np.stack((lo[valid],hi[valid]),axis=1)[:,:,None]
        if len(self.templates)>=1024:self.templates.pop(next(iter(self.templates)))
        self.templates[key]=out
        return out

    def intervals(self,uv,wrap):
        """Opaque subintervals of a UV line, using the same contour edges."""
        key=(np.asarray(uv).tobytes(),wrap)
        if key in self.interval_cache:return self.interval_cache[key]
        a,b=np.asarray(uv);d=b-a
        if d@d<1e-28:return [(0.,1.)] if self.contains([a],wrap)[0] else []
        e=self.tiled_edges(np.asarray(uv),wrap);p=e[:,0];q=e[:,1]-p
        cross=lambda x,y:x[...,0]*y[...,1]-x[...,1]*y[...,0]
        den=cross(d,q);ok=np.abs(den)>1e-16
        t=np.divide(cross(p-a,q),den,out=np.zeros(len(e)),where=ok)
        u=np.divide(cross(p-a,d),den,out=np.zeros(len(e)),where=ok)
        cuts=np.unique(np.r_[0.,t[ok&(t>0)&(t<1)&(u>=0)&(u<=1)],1.])
        inside=self.contains(a+((cuts[:-1]+cuts[1:])*.5)[:,None]*d,wrap)
        result=[]
        for lo,hi in zip(cuts[:-1][inside],cuts[1:][inside]):
            if hi-lo<=1e-12:continue
            if result and lo<=result[-1][1]+1e-12:result[-1]=(result[-1][0],hi)
            else:result.append((lo,hi))
        if len(self.interval_cache)>=4096:self.interval_cache.pop(next(iter(self.interval_cache)))
        self.interval_cache[key]=result
        return result


class Data:
    def __init__(self, lookup, uv, masks, wrap, regions):
        self.lookup=np.ascontiguousarray(lookup,np.int32);self.uv=np.ascontiguousarray(uv,np.float64).reshape(-1,3,2)
        self.masks=np.ascontiguousarray(masks,np.int32);self.wrap=np.ascontiguousarray(wrap,np.uint8);self.regions=regions
        self.native_masks=(Mask*len(regions))(*[r.native for r in regions])
        self.native=Scene(self.lookup.ctypes.data,self.uv.ctypes.data,self.masks.ctypes.data,self.wrap.ctypes.data,c.addressof(self.native_masks))


_regions={}


def transform_mesh(mesh,path,evaluated,config):
    from . import alpha_boundary as ab
    from maya.api import OpenMaya as om
    from maya import cmds
    fn,owner=ab._texture_fn(path,evaluated)
    if fn.numVertices!=len(mesh['vertices']) or fn.numPolygons!=len(mesh['faces']):raise ValueError('Alpha UV topology differs from evaluated mesh')
    counts,vertices=map(lambda a:np.asarray(a,np.int64),fn.getVertices())
    uc,ui=map(lambda a:np.asarray(a,np.int64),fn.getAssignedUVs());coords=np.column_stack(fn.getUVs()).astype(np.float64)
    validfaces=(counts==uc)&(uc>0);fi=np.repeat(np.arange(len(counts)),counts);ok=validfaces[fi]
    keys=fi[ok]*fn.numVertices+vertices[ok];vals=ui[validfaces[np.repeat(np.arange(len(uc)),uc)]]
    order=np.argsort(keys);keys=keys[order];vals=vals[order]
    tri=np.asarray(mesh['triangles'],np.int64);tf=np.asarray(mesh['triangle_faces'],np.int32)
    queries=tf[:,None]*fn.numVertices+tri;pos=np.searchsorted(keys,queries)
    good=np.all(pos<len(keys),axis=1)&validfaces[tf]
    if len(keys):good[good]&=np.all(keys[pos[good]]==queries[good],axis=1)
    else:good[:]=False
    sources=config['sources']
    if 'all' not in sources:
        current={};engines,_=om.MFnMesh(path).getConnectedShaders(path.instanceNumber())
        for i,sg in enumerate(engines):
            shaders=cmds.listConnections(om.MFnDependencyNode(sg).name()+'.surfaceShader',s=True,d=False) or []
            if not shaders:continue
            uuid=(cmds.ls(shaders[0],uuid=True) or [''])[0]
            for source in sources.values():
                if source.get('shader_uuid')==uuid or (not source.get('shader_uuid') and source.get('shader')==shaders[0]):current[str(i)]=source;break
        sources=current
    lookup=np.full(len(tri),-1,np.int32);uv=[];masks=[];wraps=[];regions=[];stats=[];cursor=0;unassigned=0
    material=np.asarray(mesh['material_ids'])[tf]
    for key,source in sources.items():
        selected=np.ones(len(tri),bool) if key=='all' else material==int(key)
        # An unmapped face has no texture-defined cutout. Keep its original
        # surface/edges, report it, and continue the valid UV portions.
        unassigned+=int(np.count_nonzero(selected&~good))
        ids=np.flatnonzero(selected&good)
        if not len(ids):continue
        contour,info=ab._cells(source,config,compact=True)
        rid=id(contour)
        if rid not in _regions or _regions[rid][0] is not contour:
            if len(_regions)>=32:_regions.pop(next(iter(_regions)))
            _regions[rid]=(contour,Region(contour))
        region=_regions[rid][1];regions.append(region);stats.append(info)
        mapped=coords[vals[pos[ids]]]*np.asarray(source.get('repeat',[1,1]))+np.asarray(source.get('offset',[0,0]))
        if not source.get('wrap',True) and (mapped.min()<-1e-10 or mapped.max()>1+1e-10):raise ValueError('Non-wrapping alpha UVs outside 0–1')
        lookup[ids]=np.arange(cursor,cursor+len(ids),dtype=np.int32);cursor+=len(ids)
        uv.append(mapped);masks.extend([len(regions)-1]*len(ids));wraps.extend([source.get('wrap',True)]*len(ids))
    if regions:
        mesh['_cpu_alpha']=Data(lookup,np.concatenate(uv),masks,wraps,regions)
        mesh['alpha_boundary']=True;mesh['alpha_boundary_stats']=stats
    if unassigned:mesh['cpu_alpha_warning']='%s: %d triangles have no assigned alpha UV; retained as opaque source faces'%(mesh['name'],unassigned)
    return mesh


def pack_visibility(meshes):
    if not any(m.get('_cpu_alpha') for m in meshes):return None
    lookup=[];uv=[];masks=[];wrap=[];regions=[];cursor=0;seen={}
    for mesh in meshes:
        a=mesh.get('_cpu_alpha');n=len(mesh['triangles'])
        if a is None:lookup.append(np.full(n,-1,np.int32));continue
        lookup.append(np.where(a.lookup>=0,a.lookup+cursor,-1));cursor+=len(a.uv);uv.append(a.uv);wrap.append(a.wrap)
        remap=[]
        for r in a.regions:
            if id(r) not in seen:seen[id(r)]=len(regions);regions.append(r)
            remap.append(seen[id(r)])
        masks.append(np.asarray(remap,np.int32)[a.masks])
    return Data(np.concatenate(lookup),np.concatenate(uv),np.concatenate(masks),np.concatenate(wrap),regions)


def _binding_keys(ids,weights):
    ids=np.broadcast_to(ids,weights.shape).copy();weight=np.rint(weights*1e9).astype(np.int64)
    ids[weight==0]=-1;order=np.argsort(ids,axis=-1)
    return np.concatenate((np.take_along_axis(ids,order,axis=-1),np.take_along_axis(weight,order,axis=-1)),axis=-1)


def _profile(style):return bool(style.get('width_profile') or style.get('alpha_profile') or style.get('connect_collinear_dashes'))


class TemplatePoints:
    """Repeat one contour on source triangles; expand only a requested batch."""
    def __init__(self,source,bary):
        self.source=np.ascontiguousarray(source,np.float64);self.bary=np.ascontiguousarray(bary,np.float64);self.shape=(len(source)*len(bary),2,3)
    def __len__(self):return self.shape[0]
    def slice_view(self,first,last):return TemplateSlice(self,first,last)
    def copy_to(self,out):self.slice_view(0,len(self)).copy_to(out)
    def __getitem__(self,key):
        if isinstance(key,tuple):return self[key[0]][(slice(None),*key[1:])] if isinstance(key[0],slice) else self[key[0]][key[1:]]
        if isinstance(key,slice):
            start,stop,step=key.indices(len(self))
            if step==1:
                out=np.empty((max(0,stop-start),2,3),np.float64)
                if stop<=start:return out
                size=len(self.bary);triangle,offset=divmod(start,size);cursor=0
                if offset:
                    n=min(stop-start,size-offset)
                    out[:n]=np.einsum('sab,bc->sac',self.bary[offset:offset+n],self.source[triangle])
                    cursor=n;triangle+=1
                full=(stop-start-cursor)//size
                if full:
                    n=full*size
                    out[cursor:cursor+n]=np.einsum('sab,tbc->tsac',self.bary,self.source[triangle:triangle+full]).reshape(-1,2,3)
                    cursor+=n;triangle+=full
                if cursor<len(out):out[cursor:]=np.einsum('sab,bc->sac',self.bary[:len(out)-cursor],self.source[triangle])
                return out
        ids=np.arange(*key.indices(len(self))) if isinstance(key,slice) else np.asarray(key)
        return np.einsum('...sb,...bc->...sc',self.bary[ids%len(self.bary)],self.source[ids//len(self.bary)])
    def __array__(self,dtype=None,copy=None):return np.asarray(self[:],dtype=dtype)


class TemplateSlice:
    def __init__(self,template,first,last):
        self.template=template;self.first=first;self.count=last-first;self.shape=(self.count,2,3)
    def __len__(self):return self.count
    def copy_to(self,out):
        if out.shape!=self.shape or out.dtype!=np.float64 or not out.flags.c_contiguous:raise ValueError('Contiguous float64 contour output required')
        from .native_cpu import alpha_points
        alpha_points(self.template.source,self.template.bary,self.first,self.count,out)
    def __array__(self,dtype=None,copy=None):
        out=np.empty(self.shape,np.float64);self.copy_to(out);return np.asarray(out,dtype=dtype)
    def __getitem__(self,key):return np.asarray(self)[key]


def _add(segments,mesh,index,points,flags,style,line,vertex_keys=None,map_uvs=None):
    if not len(points):return
    if hasattr(segments,'parts'):
        segments._flush();segments.parts.append(dict(points=points if isinstance(points,TemplatePoints) else np.ascontiguousarray(points),flags=np.full(len(points),flags,np.uint8),settings=style,mesh=mesh.get('name','mesh'),mesh_index=index,line=line,count=len(points)))
        if vertex_keys is not None:segments.parts[-1]['_alpha_vertex_keys']=vertex_keys
        if map_uvs is not None:segments.parts[-1]['map_uvs']=map_uvs
        segments.count+=len(points)
    else:
        from .renderer import EDGE_FEATURES
        for row,(a,b) in enumerate(points):
            record=dict(a=a,b=b,features=[name for bit,name in enumerate(EDGE_FEATURES) if flags&(1<<bit)],settings=style,mesh_index=index,mesh=mesh.get('name','mesh'),line=line)
            if map_uvs is not None:record['_map_uvs']={key:value[row] for key,value in map_uvs.items()}
            segments.append(record)


def append_boundaries(mesh,index,face_styles,styles,line,segments,camera,triangle_keep=None):
    a=mesh.get('_cpu_alpha')
    if a is None:return
    from .brush_channels import feature_styles
    tri=np.asarray(mesh['triangles']);tf=np.asarray(mesh['triangle_faces']);verts=np.asarray(mesh['vertices'])
    ids=np.flatnonzero(a.lookup>=0)
    if triangle_keep is not None:ids=ids[triangle_keep[ids]]
    # Reject only entire source triangles beyond a camera clipping plane.
    # Large/off-axis triangles that cross a plane are retained.
    cv=(verts-camera['eye'])@camera['basis'].T
    p=cv[tri[ids]];margin=max([s.get('line_width',1.) for s in styles]+[1.])*4+4
    if camera['ortho']:
        sx=np.full(p.shape[:2],(camera['width']/2+margin)*camera['span']/camera['width']);sy=np.full_like(sx,(camera['height']/2+margin)*camera['span']/camera['width'])
    else:sx=p[:,:,2]*(camera['width']/2+margin)/camera['focal'];sy=p[:,:,2]*(camera['height']/2+margin)/camera['focal']
    reject=np.any(np.stack([np.all(p[:,:,2]<camera['near'],axis=1),np.all(p[:,:,2]>camera['far'],axis=1),np.all(p[:,:,0]<-sx,axis=1),np.all(p[:,:,0]>sx,axis=1),np.all(p[:,:,1]<-sy,axis=1),np.all(p[:,:,1]>sy,axis=1)]),axis=0)
    # Connected profiles keep their off-screen arc length. Displaced brushes
    # and independently sized feature brushes retain the full source contour.
    from .stroke_presets import active
    if not any(_profile(s) or active(s) or '_brush_channels' in s or s.get('width_depth_reduction')
               for s in styles):ids=ids[~reject]
    rows=a.lookup[ids];owners=np.asarray(face_styles)[tf[ids]]
    for mid,region in enumerate(a.regions):
        take=a.masks[rows]==mid;mi=ids[take];mr=rows[take];mo=owners[take]
        if not len(mi):continue
        keys=np.concatenate((a.uv[mr].reshape(-1,6),a.wrap[mr,None]),axis=1)
        templates,inverse=np.unique(keys,axis=0,return_inverse=True)
        for k,key in enumerate(templates):
            selected=inverse==k;ii=mi[selected];oo=mo[selected];bary=region.boundary(key[:6].reshape(3,2),bool(key[6]))
            if not len(bary):continue
            for sid in np.unique(oo):
                if sid<0:continue
                for style in feature_styles(styles[sid],'open'):
                    if not style.get('open_edges',False):continue
                    chosen=ii[oo==sid]
                    from .stroke_presets import active
                    from .brush_map_geometry import active as maps_active, uv_sets, _data, _error
                    if hasattr(segments,'parts') and not _profile(style) and not active(style) and not maps_active(style):
                        _add(segments,mesh,index,TemplatePoints(verts[tri[chosen]],bary),2,style,line)
                        continue
                    # Bound transient world-coordinate arrays to about 4 MiB.
                    chunk=max(1,65536//len(bary))
                    for first in range(0,len(chosen),chunk):
                        source_ids=chosen[first:first+chunk];source=tri[source_ids]
                        points=np.einsum('sab,tbc->tsac',bary,verts[source]).reshape(-1,2,3)
                        keys=_binding_keys(source[:,None,None,:],np.broadcast_to(bary,(len(source),*bary.shape))).reshape(-1,2,6) if _profile(style) else None
                        map_uvs=None
                        if maps_active(style):
                            map_uvs={}
                            for uv_set in uv_sets(style):
                                data=_data(mesh,uv_set)
                                if not data['triangle_valid'][source_ids].all():raise _error(mesh,'missing or invalid UVs on alpha contour owner, UV set '+repr(uv_set))
                                map_uvs[uv_set]=np.einsum('sab,tbc->tsac',bary,data['triangle_uv'][source_ids]).reshape(-1,2,2)
                        _add(segments,mesh,index,points,2,style,line,keys,map_uvs)


def clip_edges(mesh,prepared,indices,flags,style,line,index,segments):
    """Clip authored/card edges, keeping untouched opaque edges in bulk."""
    a=mesh['_cpu_alpha'];tri=np.asarray(mesh['triangles']);tf=np.asarray(mesh['triangle_faces'])
    if '_alpha_edge_map' not in mesh:
        ids=np.flatnonzero(a.lookup>=0);pairs=tri[ids][:,[[0,1],[1,2],[2,0]]].reshape(-1,2)
        ordered=np.sort(pairs,axis=1).astype(np.uint64);keys=(ordered[:,0]<<np.uint64(32))|ordered[:,1]
        order=np.argsort(keys);mesh['_alpha_edge_map']=(keys[order],order,ids)
    keys,order,ids=mesh['_alpha_edge_map'];unmasked=[]
    pairkeys=prepared['pairs'][indices].astype(np.uint64);pairkeys=(pairkeys[:,0]<<np.uint64(32))|pairkeys[:,1]
    starts=np.searchsorted(keys,pairkeys);ends=np.searchsorted(keys,pairkeys,side='right')
    if hasattr(segments,'parts') and not _profile(style) and len(indices)>=128:
        return _clip_edges_native(mesh,prepared,indices,flags,style,line,index,segments,order,ids,starts,ends)
    from .brush_map_geometry import active as maps_active, edge_uv
    mapped=edge_uv(mesh,prepared,indices,style) if maps_active(style) else {}
    for row_index,(edge,start,end) in enumerate(zip(indices,starts,ends)):
        pair=prepared['pairs'][edge]
        if start==end:unmasked.append(edge);continue
        slots=order[start:end];ti=ids[slots//3];corners=np.asarray([[0,1],[1,2],[2,0]])[slots%3]
        entries=[]
        for t,corners in zip(ti,corners):
            uv=a.uv[a.lookup[t],corners]
            if tri[t,corners[0]]>tri[t,corners[1]]:uv=uv[::-1]
            entries.append((int(tf[t]),int(a.lookup[t]),uv))
        owners=prepared['owners'][prepared['starts'][edge]:prepared['starts'][edge]+prepared['counts'][edge]]
        if any(int(f) not in {e[0] for e in entries} for f in owners):unmasked.append(edge);continue
        intervals=[]
        for _,row,uv in entries:intervals.extend(a.regions[a.masks[row]].intervals(uv,bool(a.wrap[row])))
        merged=[]
        for lo,hi in sorted(intervals):
            if merged and lo<=merged[-1][1]+1e-12:merged[-1][1]=max(hi,merged[-1][1])
            else:merged.append([lo,hi])
        if merged:
            p,q=prepared['vertices'][pair];points=p+np.asarray(merged)[:,:,None]*(q-p)
            keys=None
            if _profile(style):
                t=np.asarray(merged);weights=np.stack((1-t,t,np.zeros_like(t)),axis=-1)
                keys=_binding_keys(np.r_[pair,-1],weights)
            map_uvs={name:uv[row_index,:1]+np.asarray(merged)[...,None]*(uv[row_index,1:2]-uv[row_index,:1]) for name,uv in mapped.items()} if mapped else None
            _add(segments,mesh,index,points,int(flags[edge]),style,line,keys,map_uvs)
    return np.asarray(unmasked,np.int64)


def _clip_edges_native(mesh,prepared,indices,flags,style,line,index,segments,order,ids,starts,ends):
    from .native_cpu import alpha_edges
    unmasked,rows=alpha_edges(mesh['_cpu_alpha'],mesh['triangles'],mesh['triangle_faces'],prepared,indices,order,ids,starts,ends)
    if len(rows):
        edge=rows[:,0].astype(np.int64);pair=prepared['vertices'][prepared['pairs'][edge]]
        points=pair[:,None,0]+rows[:,1:,None]*(pair[:,None,1]-pair[:,None,0])
        segments._flush();segments.parts.append(dict(points=points,flags=flags[edge],settings=style,mesh=mesh.get('name','mesh'),mesh_index=index,line=line,count=len(points)))
        from .brush_map_geometry import active as maps_active, edge_uv
        if maps_active(style):
            mapped=edge_uv(mesh,prepared,edge,style)
            segments.parts[-1]['map_uvs']={name:uv[:,:1]+rows[:,1:,None]*(uv[:,1:2]-uv[:,:1]) for name,uv in mapped.items()}
        segments.count+=len(points)
    return indices[unmasked]


def connect_profiles(meshes,segments):
    if not hasattr(segments,'parts'):return
    segments._flush()
    for index,mesh in enumerate(meshes):
        if not mesh.get('_cpu_alpha'):continue
        parts=[p for p in segments.parts if p.get('mesh_index')==index and
               ('_alpha_vertex_keys' in p or ('vertex_ids' in p and _profile(p['settings'])))]
        if not parts:continue
        keys=[]
        for p in parts:
            if '_alpha_vertex_keys' in p:keys.append(p.pop('_alpha_vertex_keys').reshape(-1,6))
            else:
                ids=p['vertex_ids'].reshape(-1);k=np.zeros((len(ids),6),np.int64);k[:,:2]=-1;k[:,2]=ids;k[:,5]=1000000000;keys.append(k)
        _,inverse=np.unique(np.concatenate(keys),axis=0,return_inverse=True);cursor=0
        for p in parts:
            count=p['count']*2;p['vertex_ids']=inverse[cursor:cursor+count].reshape(-1,2);cursor+=count


def line_intervals(mesh,triangle,points):
    a=mesh.get('_cpu_alpha')
    if a is None or a.lookup[triangle]<0:return [(0.,1.)]
    row=a.lookup[triangle];p=np.asarray(mesh['vertices'])[mesh['triangles'][triangle]]
    basis=np.stack((p[1]-p[0],p[2]-p[0]),axis=1)
    xy=np.linalg.lstsq(basis,(points-p[0]).T,rcond=None)[0].T
    uv=np.c_[1-xy.sum(axis=1),xy]@a.uv[row]
    return a.regions[a.masks[row]].intervals(uv,bool(a.wrap[row]))


def trim_intersections(meshes,intersections,progress=None):
    """Keep only the common opaque portions of both intersecting cards."""
    from .intersections import IntersectionBatches
    if not len(intersections):return intersections
    batches=intersections
    if not hasattr(batches,'batches'):
        batches=IntersectionBatches()
        for record in intersections:
            i,j=record['mesh_indices']
            for ti,tj in record['triangle_pairs']:batches.append_record(i,j,[record['a'],record['b']],ti,tj)
        batches.flush()
    result=IntersectionBatches()
    from .native_cpu import library,alpha_trim
    lib=library()
    if lib is None:raise RuntimeError('CPU alpha intersection accelerator unavailable')
    fn=lib.rp_alpha_trim;fn.argtypes=[c.c_void_p]*4+[c.c_int64,c.c_void_p,c.c_int64];fn.restype=c.c_int64
    completed=0;total=sum(len(rows) for _,_,rows in batches.batches)
    for i,j,rows in batches.batches:
        if not meshes[i].get('_cpu_alpha') and not meshes[j].get('_cpu_alpha'):
            result.add(i,j,rows);completed+=len(rows)
            if progress:progress('alpha_clip',completed,total)
            continue
        for start in range(0,len(rows),2048):
            if progress:progress('alpha_clip',completed,total,meshes[i].get('name',''))
            chunk=rows[start:start+2048];points=chunk[:,:6].reshape(-1,2,3)
            tids=np.ascontiguousarray(chunk[:,6:8],np.int64);uv=np.zeros((len(chunk),2,2,2));pointers=[]
            for side,index in enumerate((i,j)):
                mesh=meshes[index];a=mesh.get('_cpu_alpha');pointers.append(c.byref(a.native) if a is not None else None)
                if a is None:continue
                ids=a.lookup[tids[:,side]];valid=ids>=0
                p=np.asarray(mesh['vertices'])[np.asarray(mesh['triangles'])[tids[valid,side]]]
                e=p[:,1]-p[:,0];f=p[:,2]-p[:,0];q=points[valid]-p[:,None,0]
                ee=np.einsum('ij,ij->i',e,e);ff=np.einsum('ij,ij->i',f,f);ef=np.einsum('ij,ij->i',e,f);det=ee*ff-ef*ef
                qe=np.einsum('isj,ij->is',q,e);qf=np.einsum('isj,ij->is',q,f)
                safe=np.abs(det)>1e-28
                x=np.divide(qe*ff[:,None]-qf*ef[:,None],det[:,None],out=np.zeros_like(qe),where=safe[:,None])
                y=np.divide(qf*ee[:,None]-qe*ef[:,None],det[:,None],out=np.zeros_like(qf),where=safe[:,None])
                for bad in np.flatnonzero(~safe):x[bad],y[bad]=np.linalg.lstsq(np.stack((e[bad],f[bad]),axis=1),q[bad].T,rcond=None)[0]
                uv[valid,side]=np.einsum('isj,ijk->isk',np.stack((1-x-y,x,y),axis=-1),a.uv[ids[valid]])
            output=alpha_trim(*pointers,tids,uv);used=len(output)
            if used:
                output=output[:used];source=output[:,0].astype(np.int64);p=points[source]
                clipped=p[:,None,0]+output[:,1:,None]*(p[:,None,1]-p[:,None,0])
                result.add(i,j,np.column_stack((clipped.reshape(-1,6),chunk[source,6:8])))
            completed+=len(chunk)
    if progress:progress('alpha_clip',completed,total)
    return result
