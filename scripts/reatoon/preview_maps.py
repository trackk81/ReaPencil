"""Normal-preview Maya brush maps. Bake only on DG changes; sample on GPU.

The same 256-square Maya UV tile and color/width blend used by the CPU path
are uploaded once. Camera changes do not evaluate Maya textures or mesh UVs.
"""
import ctypes as c
import json
import numpy as np
from maya import cmds
from maya.api import OpenMaya as om
from . import maya_brush_maps as maps, brush_map_geometry as geo

_lib=None
_textures={}
_callbacks=[]
_dirty=set()
_watch_key=None
_sampling=False
_warnings=set()
stats=dict(samples=0,uploads=0,uv_exports=0)


def reset_scene():
    global _watch_key
    for cb in _callbacks:
        try:om.MMessage.removeCallback(cb)
        except RuntimeError:pass
    _callbacks.clear();_watch_key=None;_dirty.update(_textures);_warnings.clear()


def bind(lib):
    global _lib,_watch_key
    for cb in _callbacks:
        try:om.MMessage.removeCallback(cb)
        except RuntimeError:pass
    _callbacks.clear();_textures.clear();_dirty.clear();_warnings.clear();_watch_key=None
    _lib=lib if hasattr(lib,'rt_style_maps') else None
    if _lib:
        lib.rt_style_maps.argtypes=[c.c_uint,c.c_int,c.c_int,c.c_float,c.c_float,c.c_int]
        lib.rt_map_texture.argtypes=[c.c_uint,c.c_void_p,c.c_uint,c.c_uint,c.c_uint]
        lib.rt_map_uv.argtypes=[c.c_void_p,c.c_uint]
        lib.rt_map_uv_vertices.argtypes=[c.c_void_p,c.c_uint]
        lib.rt_map_dash.argtypes=[c.c_uint,c.c_float,c.c_float]


def warn(error):
    text=str(error)
    if text not in _warnings:
        _warnings.add(text);cmds.warning('ReaPencil preview map: '+text)


def configured(styles):
    return any(s.get('brush_maps') for s in geo.iter_styles(styles))


def _invalidate(identity):
    if _sampling:return
    _dirty.add(identity)
    from . import viewport
    viewport.request_refresh(style_changed=True)


def watch(styles):
    """Observe only upstream map nodes, not unrelated scene shader edits."""
    global _watch_key
    descriptors=[d for s in geo.iter_styles(styles) for d in s.get('brush_maps',{}).values() if maps.active(d)]
    key=json.dumps(descriptors,sort_keys=True)
    if key==_watch_key:return
    for cb in _callbacks:
        try:om.MMessage.removeCallback(cb)
        except RuntimeError:pass
    _callbacks.clear();_watch_key=key
    for d in descriptors:
        try:
            node=maps.resolve_node(d,cmds);identity=(cmds.ls(node,uuid=True) or [node])[0]
            for dependency in set((cmds.listHistory(node,pruneDagObjects=True) or [])+[node]):
                sel=om.MSelectionList();sel.add(dependency);obj=sel.getDependNode(0)
                _callbacks.append(om.MNodeMessage.addNodeDirtyCallback(obj,lambda *_,ident=identity:_invalidate(ident)))
                def changed(msg,*_,ident=identity):
                    global _watch_key
                    if msg & (om.MNodeMessage.kAttributeSet|om.MNodeMessage.kConnectionMade|om.MNodeMessage.kConnectionBroken):
                        _watch_key=None;_invalidate(ident)
                _callbacks.append(om.MNodeMessage.addAttributeChangedCallback(obj,changed))
        except (ValueError,RuntimeError) as e:warn(e)


def texture(descriptor):
    global _sampling
    if not maps.active(descriptor):return -1,0.
    try:
        node=maps.resolve_node(descriptor,cmds);identity=(cmds.ls(node,uuid=True) or [node])[0]
        entry=_textures.get(identity)
        if entry is None:
            if len(_textures)>=256:raise ValueError('256 preview brush maps reached; restart Maya to reclaim the texture cache')
            entry=_textures[identity]=dict(id=len(_textures),revision=0)
        if not entry['revision'] or identity in _dirty:
            _sampling=True
            try:
                rgba=np.ones((maps.RESOLUTION,maps.RESOLUTION,4),np.float32)
                rgba[:,:,:3]=maps._sample(node,cmds)['pixels'];stats['samples']+=1
                entry['revision']+=1
                _lib.rt_map_texture(entry['id'],rgba.ctypes.data,rgba.shape[1],rgba.shape[0],entry['revision'])
                stats['uploads']+=1;entry.pop('error',None)
            except (ValueError,RuntimeError) as e:
                entry['error']=str(e);entry['revision']+=1
            finally:_sampling=False;_dirty.discard(identity)
        if entry.get('error'):raise ValueError(entry['error'])
        return entry['id'],float(descriptor.get('amount',1.))
    except (ValueError,RuntimeError) as e:warn(e);return -1,0.


def set_style(style_id,style):
    if not _lib:return
    values=[texture(style.get('brush_maps',{}).get(k)) for k in ('color','width')]
    # Mode 2 has no facing gate, but keeps the mapped shader layout allocated
    # while a broken texture is repaired. Stale texels are never reused.
    facing=int(style.get('_map_facing',0)) or (2 if geo.active(style) or style.get('dash_length') else 0)
    _lib.rt_style_maps(style_id,values[0][0],values[1][0],values[0][1],values[1][1],facing)
    dash=float(style.get('dash_length',0.));gap=float(style.get('dash_gap',-1.))
    _lib.rt_map_dash(style_id,dash,gap if gap>=0 else dash)


def expand_passes(passes,scene,settings):
    """Resolve specific brushes with exactly the CPU channel defaults/scaling."""
    if not configured([s for p in passes for s in p['styles']]):return
    from . import renderer
    resolved=renderer.line_style_passes(scene,dict(settings,_cpu_brush_channels=True))
    for item,source in zip(passes,resolved):
        base=list(item['styles']);item['_map_routes']={}
        for owner,raw in enumerate(source['styles'][:len(base)]):
            if '_brush_channels' not in raw:continue
            channel=raw['_brush_channels'][0];routes={}
            for name in ('outline','open','intersection','hard','material','selected','crease','wireframe'):
                brush=channel['brushes'].get(name,channel['brushes'].get('outline') if name=='open' else None) or channel['settings']
                for facing in ((1,) if name=='outline' else ((-1,) if name not in ('open','intersection') else (0,))):
                    child=dict(brush,_map_facing=facing,_map_child=True)
                    child.pop('_brush_channels',None)
                    routes[name]=len(item['styles']);item['styles'].append(child)
                    item['style_nodes'].append(item['style_nodes'][owner])
            item['_map_routes'][owner]=routes
    for item in passes:
        for target,style in enumerate(list(item['styles'])):
            if geo.active(style):unmapped_style(item,target)
    watch([s for p in passes for s in p['styles']])


def ensure_uv(mesh,style):
    wanted=geo.uv_sets(style)
    if not wanted:return
    if all(k in mesh.get('_brush_map_uvs',{}) for k in wanted):return
    from . import maya_scene
    previous=mesh.get('_brush_map_uvs',{})
    geo.export_uv_sets(mesh,maya_scene._dag(mesh['name']),dict(level=mesh.get('smooth_level',0),purpose='viewport'),style)
    mesh['_brush_map_uvs']={**previous,**mesh['_brush_map_uvs']};stats['uv_exports']+=1


def pack_uv(uvs,style,count):
    values=np.zeros((count,2,4),np.float32)
    for channel,start in (('color',0),('width',2)):
        descriptor=style.get('brush_maps',{}).get(channel)
        if not maps.active(descriptor):continue
        uv=uvs[descriptor.get('uv_set','')]
        if not np.isfinite(uv).all() or np.any(uv < -1e-6) or np.any(uv > 1.+1e-6):
            raise ValueError('Brush maps require assigned UVs in the 0..1 tile')
        values[:,:,start:start+2]=uv
    return values


def edge_uv(mesh,data,style):
    if not geo.active(style):return None
    ensure_uv(mesh,style)
    from .gpu_topology import prepare
    top=prepare(mesh);ids=data['edge_ids'];n=len(top['pairs'])
    faces=np.minimum.reduceat(top['owners'],top['starts'])
    allfaces=np.r_[faces,top['diagonal_faces']][ids]
    pairs=np.concatenate((top['pairs'],top['diagonal_pairs']))[ids]
    queries=allfaces[:,None]*len(mesh['vertices'])+pairs
    uvs={}
    for name in geo.uv_sets(style):
        d=mesh['_brush_map_uvs'][name];uv,good=geo.lookup_uv(d['keys'],d['ids'],d['coordinates'],queries)
        if not good.all():raise ValueError('Missing brush map UVs on '+mesh['name'])
        uvs[name]=uv
    return pack_uv(uvs,style,len(ids))


def route_edges(item,mesh,data):
    """Partition static flags once; GPU resolves silhouette priority per view."""
    from .brush_channels import FEATURES,PRIORITY
    for owner in np.unique(data['owners']):
        selected=np.flatnonzero(data['owners']==owner);routes=item.get('_map_routes',{}).get(int(owner))
        groups=[]
        if not routes:groups=[(selected,int(owner),None)]
        else:
            base=item['styles'][int(owner)];flags=data['static_flags'][selected]
            eligible=data['outline_eligible'][selected]
            boundary=(flags&2)!=0
            if base.get('outline'):
                groups.append((selected[eligible & ~boundary],routes['outline'],False))
            if base.get('open_edges'):groups.append((selected[boundary],routes['open'],False))
            remaining=~boundary
            for name in PRIORITY:
                if name in ('outline','open','intersection'):continue
                chosen=remaining & ((flags & (1<<FEATURES.index(name)))!=0)
                if chosen.any():groups.append((selected[chosen],routes[name],False))
                remaining[chosen]=False
        for ids,target,dynamic in groups:
            if not len(ids):continue
            subset={k:(v[ids] if isinstance(v,np.ndarray) and len(v)==len(data['owners']) else v) for k,v in data.items()}
            if dynamic is not None:subset['dynamic']=np.zeros(len(ids),bool)
            style=item['styles'][target]
            try:uv=edge_uv(mesh,subset,style)
            except (ValueError,RuntimeError) as e:
                warn(e);uv=None
                # Per-mesh invalid UVs must not paint an arbitrary texel.
                target=unmapped_style(item,target)
            yield subset,target,uv


def unmapped_style(item,target):
    cache=item.setdefault('_unmapped_styles',{})
    if target not in cache:
        cache[target]=len(item['styles']);item['styles'].append(dict(item['styles'][target],brush_maps={}))
        item['style_nodes'].append(item['style_nodes'][target])
    return cache[target]


def closest_triangles(mesh,points):
    """Find evaluated owner triangles only when generated geometry changes."""
    cached=mesh.get('_preview_map_intersector')
    if cached is None or cached[0] is not mesh['vertices']:
        vertices=np.asarray(mesh['vertices']);tris=np.asarray(mesh['triangles'])
        owner=om.MFnMeshData().create();fn=om.MFnMesh()
        obj=fn.create(om.MPointArray(vertices.tolist()),[3]*len(tris),tris.ravel().tolist(),parent=owner)
        inter=om.MMeshIntersector();inter.create(obj)
        cached=mesh['_preview_map_intersector']=(mesh['vertices'],inter,owner)
    inter=cached[1];mid=np.asarray(points).mean(axis=1)
    return np.asarray([inter.getClosestPoint(om.MPoint(*p)).face for p in mid],np.int64)


def closest_uv(mesh,points,style):
    if not geo.active(style):return None
    ensure_uv(mesh,style)
    return pack_uv(geo.intersection_uv(mesh,points,closest_triangles(mesh,points),style),style,len(points))


def triangle_uv(mesh,indices,style):
    if not geo.active(style):return None
    ensure_uv(mesh,style);values=np.zeros((len(indices),3,4),np.float32)
    for channel,start in (('color',0),('width',2)):
        descriptor=style.get('brush_maps',{}).get(channel)
        if not maps.active(descriptor):continue
        d=mesh['_brush_map_uvs'][descriptor.get('uv_set','')];uv=d['triangle_uv'][indices]
        if not d['triangle_valid'][indices].all() or np.any(uv < -1e-6) or np.any(uv>1.+1e-6):raise ValueError('Alpha card brush maps require assigned UVs in the 0..1 tile')
        values[:,:,start:start+2]=uv
    return values


def cross_uv(item,scene,points,parameters,owners):
    output=[]
    for owner in np.unique(owners):
        ids=np.flatnonzero(owners==owner);target=item.get('_map_routes',{}).get(int(owner),{}).get('intersection',int(owner))
        style=item['styles'][target]
        if not geo.active(style):output.append((ids,target,None));continue
        # Match the actual incident polygon's line set, not an unrelated
        # polygon on the same mesh. Stable mesh order resolves shared owners.
        mesh_ids=(parameters[ids,:,3]/2-1).astype(int)
        chosen=np.full(len(ids),-1,np.int32);triangles=np.zeros(len(ids),np.int64)
        for mesh_id in np.unique(mesh_ids):
            face_styles=np.asarray(item['face_style_ids'][mesh_id])
            if not np.any(face_styles==owner):continue
            rows=np.flatnonzero(np.any(mesh_ids==mesh_id,axis=1) & (chosen<0))
            if not len(rows):continue
            mesh=scene['meshes'][mesh_id]
            try:
                tids=closest_triangles(mesh,points[ids[rows]])
                faces=np.asarray(mesh.get('triangle_faces',np.arange(len(mesh['triangles']))))[tids]
                match=face_styles[faces]==owner
                chosen[rows[match]]=mesh_id;triangles[rows[match]]=tids[match]
            except (ValueError,RuntimeError) as e:warn(e)
        for mesh_id in np.unique(chosen):
            rows=np.flatnonzero(chosen==mesh_id);sel=ids[rows];draw_target=target
            try:
                if mesh_id<0:raise ValueError('No matching intersection owner polygon for brush maps')
                mesh=scene['meshes'][mesh_id];ensure_uv(mesh,style)
                uv=pack_uv(geo.intersection_uv(mesh,points[sel],triangles[rows],style),style,len(sel))
            except (ValueError,RuntimeError) as e:warn(e);uv=None;draw_target=unmapped_style(item,target)
            output.append((sel,draw_target,uv))
    return output


def expand_presets(points,parameters,owners,styles,camera,vertices,flags,outline,uv,fixed,active):
    if camera is None or not any(active(styles[int(i)]) for i in np.unique(owners)):
        return points,parameters,owners,vertices,flags,outline,None,uv
    from .stroke_presets import expand,domains,variant_owner
    spans={}
    for owner in np.unique(owners):
        ids=np.flatnonzero(owners==owner)
        if active(styles[int(owner)]):spans.update(zip(ids,domains(points[ids],camera)))
    out=[];params=[];ids=[];bits=[];eligible=[];coords=[];mapped=[]
    for i,(ends,owner) in enumerate(zip(points,owners)):
        style=styles[int(owner)]
        chunks=expand(ends,style,camera,phase=spans[i]) if active(style) else [(ends[None],np.array([[0.,1.]]),False)]
        for pairs,t,thin in chunks:
            n=len(pairs);out.append(pairs);params.append(np.repeat(parameters[i:i+1],n,axis=0))
            ids.extend([variant_owner(style,int(owner),thin)]*n)
            bits.extend([int(flags[i]) if flags is not None else 0]*n);eligible.extend([bool(outline[i]) if outline is not None else False]*n)
            mapped.append(uv[i,0]+t[:,:,None]*(uv[i,1]-uv[i,0]))
            coords.append(t if fixed is None else fixed[i,0]+t*(fixed[i,1]-fixed[i,0]))
    n=len(ids)
    if not n:return np.empty((0,2,3)),np.empty((0,2,4)),np.empty(0,np.int32),None,None,None,None,np.empty((0,2,4))
    return np.concatenate(out),np.concatenate(params),np.asarray(ids,np.int32),np.arange(n*2).reshape(n,2),np.asarray(bits,np.int64),np.asarray(eligible,bool),np.concatenate(coords),np.concatenate(mapped)
