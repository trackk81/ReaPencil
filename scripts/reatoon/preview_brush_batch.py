"""Batch the existing procedural brush arithmetic without reducing samples."""
import numpy as np
from collections import OrderedDict,deque

_topology=OrderedDict()
_topology_bytes=0


def connectivity_seed():
    """Immutable connectivity only; no camera lengths or mutable cache shared."""
    return tuple((key,(tuple(chains),cost)) for key,(chains,cost) in _topology.items()),_topology_bytes


def seed_connectivity(seed):
    global _topology,_topology_bytes
    entries,cost=seed;_topology=OrderedDict(entries);_topology_bytes=cost


def domains(points,camera):
    """Cache only world connectivity; evaluate projected lengths every frame."""
    from .renderer import _project
    global _topology_bytes
    points=np.asarray(points,float);rounded=np.round(points,10);key=rounded.tobytes()
    chains=_topology.get(key)
    if chains is None:
        adjacency={};keys=[]
        for i,pair in enumerate(rounded.tolist()):
            ends=tuple(tuple(p) for p in pair);keys.append(ends)
            for v in ends:adjacency.setdefault(v,[]).append(i)
        used=set();chains=[]
        for i in range(len(points)):
            if i in used:continue
            chain=deque([(i,0,1)]);used.add(i)
            for side in (0,1):
                current=i;end=side
                while True:
                    edges=adjacency[keys[current][end]]
                    if len(edges)!=2:break
                    other=edges[0] if edges[1]==current else edges[1]
                    if other in used:break
                    near=0 if keys[other][0]==keys[current][end] else 1;far=1-near;used.add(other)
                    if side==0:chain.appendleft((other,far,near))
                    else:chain.append((other,near,far))
                    current,end=other,far
            if len(chain)>1:chains.append(tuple(chain))
        # Bound retained topology, including Python tuple overhead conservatively.
        cost=len(key)+sum(len(c)*160 for c in chains)
        while _topology and (_topology_bytes+cost>32*1024**2 or len(_topology)>=256):
            _,(_,oldcost)=_topology.popitem(last=False);_topology_bytes-=oldcost
        if cost<=32*1024**2:_topology[key]=(chains,cost);_topology_bytes+=cost
    else:
        _topology.move_to_end(key);chains=chains[0]
    cam=(points-camera['eye'])@camera['basis'].T
    xy=_project(np.where(np.abs(cam[:,:,2:3])<1e-12,cam+np.array([0,0,1e-12]),cam),camera)
    lengths=np.linalg.norm(xy[:,1]-xy[:,0],axis=1)
    reverse=(xy[:,1,0]<xy[:,0,0])|((xy[:,1,0]==xy[:,0,0])&(xy[:,1,1]<xy[:,0,1]))
    result=np.column_stack((np.where(reverse,lengths,0.),np.where(reverse,0.,lengths)))
    for chain in chains:
        if tuple(xy[chain[-1][0],chain[-1][2]])<tuple(xy[chain[0][0],chain[0][1]]):chain=[(k,b,a) for k,a,b in reversed(chain)]
        cursor=0.
        for k,a,b in chain:result[k,a]=cursor;cursor+=lengths[k];result[k,b]=cursor
    return result


def retained(points,parameters,owners,styles,camera,flags,outline,fixed=None):
    from .stroke_presets import active,expand as scalar,variant_owner
    output=[];params=[];own=[];bits=[];eligible=[];uvs=[];order=[]
    for owner in np.unique(owners):
        ids=np.flatnonzero(owners==owner);style=styles[int(owner)]
        spans=domains(points[ids],camera) if active(style) else None
        chunks=[]
        native=None
        if style.get('line_pattern',0)==0 and int(style.get('brush_preset',0)) in (1,2,3):
            from .preview_brush_native import expand as native_expand
            native=native_expand(points[ids],style,camera,spans)
        if native is not None:
            p,t,source,thin=native
            if len(source):chunks.append((p,t,ids[source],np.where(thin,variant_owner(style,int(owner),True) if style.get("brush_preset") else int(owner),int(owner))))
        elif style.get('line_pattern')!=7 and (int(style.get('brush_preset',0)) in (1,2,3) or style.get('line_pattern')==1 and not style.get('brush_preset')):
            for start in range(0,len(ids),64):
                selected=ids[start:start+64]
                p,t,source,thin=expand(points[selected],style,camera,spans[start:start+64])
                if len(source):chunks.append((p,t,selected[source],np.where(thin,variant_owner(style,int(owner),True) if style.get("brush_preset") else int(owner),int(owner))))
        elif not active(style):chunks.append((points[ids],np.tile([0.,1.],(len(ids),1)),ids,np.full(len(ids),owner,np.int32)))
        else:
            for j,i in enumerate(ids):
                for p,t,thin in scalar(points[i],style,camera,phase=spans[j]):
                    chunks.append((p,t,np.full(len(p),i,np.int64),np.full(len(p),variant_owner(style,int(owner),thin),np.int32)))
        for p,t,source,child in chunks:
            n=len(p)
            if not n:continue
            output.append(p);params.append(parameters[source]);own.append(child)
            bits.append(flags[source] if flags is not None else np.zeros(n,np.int64))
            eligible.append(outline[source] if outline is not None else np.zeros(n,bool))
            if fixed is not None:
                a=fixed[source,0];b=fixed[source,1];t=a[:,None]+t*(b-a)[:,None]
            uvs.append(t);order.append(source)
    if not output:return np.empty((0,2,3)),np.empty((0,2,4),np.float32),np.empty(0,np.int32),np.empty((0,2),np.int64),np.empty(0,np.int64),np.empty(0,bool),np.empty((0,2))
    def join(parts):return parts[0] if len(parts)==1 else np.concatenate(parts)
    n=sum(len(a) for a in output)
    arrays=[join(a) for a in (output,params,own,bits,eligible,uvs)]
    if len(np.unique(owners))>1:
        index=np.argsort(join(order),kind='stable');arrays=[a[index] for a in arrays]
    return (arrays[0],arrays[1],arrays[2].astype(np.int32,copy=False),np.arange(n*2,dtype=np.int64).reshape(-1,2),arrays[3],arrays[4],arrays[5])


def expand(points,style,camera,phase):
    """Return pairs, source parameters, source edge IDs and thin-style bits."""
    from .renderer import _project
    from .stroke_presets import path_offsets,_noise,lanes
    points=np.asarray(points,float);phase=np.asarray(phase,float)
    if not len(points):return np.empty((0,2,3)),np.empty((0,2)),np.empty(0,np.int64),np.empty(0,bool)
    texture=int(style.get('brush_preset',0));assert texture in (0,1,2,3)
    cam=(points-camera['eye'])@camera['basis'].T
    # Keep the oracle's unchanged near-plane fallback, including its style.
    near=np.any(cam[:,:,2]<=camera['near'],axis=1);ids=np.flatnonzero(~near)
    output=[];uvs=[];sources=[];thins=[];keys=[]
    if np.any(near):
        fallback=np.flatnonzero(near);output.append(points[fallback]);uvs.append(np.tile([0.,1.],(len(fallback),1)))
        sources.append(fallback);thins.append(np.zeros(len(fallback),bool));keys.append(fallback*16)
    if len(ids):
        c=cam[ids];screen=_project(c,camera);delta=screen[:,1]-screen[:,0];length=np.linalg.norm(delta,axis=1)
        p=screen[:,0];margin=float(style.get('pattern_amplitude',3.))+float(style.get('pattern_period',20.))+float(style['line_width'])
        lo=np.zeros(len(ids));hi=np.ones(len(ids));valid=length>=1e-8
        for a,b in ((-delta[:,0],p[:,0]+margin),(delta[:,0],camera['width']+margin-p[:,0]),(-delta[:,1],p[:,1]+margin),(delta[:,1],camera['height']+margin-p[:,1])):
            nonzero=np.abs(a)>=1e-14;ratio=np.divide(b,a,out=np.zeros_like(a),where=nonzero)
            valid&=nonzero|(b>=0);lo=np.where(nonzero&(a<0),np.maximum(lo,ratio),lo);hi=np.where(nonzero&(a>0),np.minimum(hi,ratio),hi);valid&=lo<=hi
        keep_ids=np.flatnonzero(valid);ids=ids[keep_ids];c=c[keep_ids];screen=screen[keep_ids];delta=delta[keep_ids];length=length[keep_ids];lo=lo[keep_ids];hi=hi[keep_ids]
        if len(ids):
            step=1. if texture else min(1.,float(style.get('pattern_period',20.))/24.)
            n=np.maximum(1,np.ceil(length*(hi-lo)/step).astype(np.int64));sizes=n+1
            starts=np.r_[0,np.cumsum(sizes)[:-1]];edge=np.repeat(np.arange(len(ids)),sizes)
            j=np.arange(sizes.sum())-np.repeat(starts,sizes)
            # np.linspace uses multiplication by the rounded step and explicit endpoint.
            u=lo[edge]+j*((hi-lo)/n)[edge];u[j==n[edge]]=hi[edge[j==n[edge]]]
            distance=phase[ids[edge],0]+u*(phase[ids[edge],1]-phase[ids[edge],0])
            along,offset,path_keep=path_offsets(distance,style)
            first=np.flatnonzero(j<n[edge]);e=edge[first];t=np.column_stack((u[first],u[first+1]));dmid=(distance[first]+distance[first+1])*.5
            reverse=phase[ids,1]<phase[ids,0];tangent=delta/length[:,None];tangent[reverse]*=-1
            normal=np.column_stack((-delta[:,1],delta[:,0]))/length[:,None];normal[reverse]*=-1
            z=c[e,0,2,None]+t*(c[e,1,2]-c[e,0,2])[:,None] if camera['ortho'] else 1/((1-t)/c[e,0,2,None]+t/c[e,1,2,None])
            base=screen[e,0,None,:]+t[:,:,None]*delta[e,None,:]+np.column_stack((along[first],along[first+1]))[:,:,None]*tangent[e,None,:]
            count=lanes(style)
            if texture:
                width=float(style['line_width'])*(.55 if texture==3 else 1.)*style.get('brush_width_scale',1.);spacing=width/count
                envelope=.6+.4*_noise(distance*.055,texture*97)
                common=width*.1*style.get('brush_roughness',1.)*(_noise(distance*.12,texture*73)-.5)
                threshold=1.-(1.-(0.,.10,.33,.16)[texture])*style.get('brush_density',1.)
            inverse=np.linalg.inv(camera['basis']).T
            for lane in range(count):
                disp=offset
                visible=path_keep[first]
                if texture:
                    disp=offset+(lane-(count-1)/2)*spacing*envelope
                    disp=disp+width*.13*style.get('brush_roughness',1.)*(_noise(distance*.65,lane+texture*17)-.5)
                    disp=disp+common
                    visible=visible&(_noise(dmid*.9,lane+texture*41)>threshold)
                selected=np.flatnonzero(visible)
                if not len(selected):continue
                xy=base[selected]+np.column_stack((disp[first[selected]],disp[first[selected]+1]))[:,:,None]*normal[e[selected],None,:]
                local=np.empty((len(selected),2,3));local[:,:,2]=z[selected]
                if camera['ortho']:
                    factor=camera['width']/camera['span'];local[:,:,:2]=(xy-[camera['width']/2,camera['height']/2])/[factor,-factor]
                else:local[:,:,:2]=(xy-[camera['width']/2,camera['height']/2])*z[selected,:,None]/[camera['focal'],-camera['focal']]
                source=ids[e[selected]];output.append(local@inverse+camera['eye']);uvs.append(t[selected]);sources.append(source)
                thins.append(np.full(len(selected),bool(texture),bool));keys.append(source*16+lane)
    if not output:return np.empty((0,2,3)),np.empty((0,2)),np.empty(0,np.int64),np.empty(0,bool)
    order=np.argsort(np.concatenate(keys),kind='stable')
    return tuple(np.concatenate(a)[order] for a in (output,uvs,sources,thins))
