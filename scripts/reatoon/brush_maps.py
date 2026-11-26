"""UV colour/size maps on CPU strokes, with bounded raster-space sampling.

Textures are frozen on Maya's main thread; this module never calls Maya. Map
work is opt-in and uses the existing native depth-tested coverage rasterizer.
"""
import ctypes as c
import numpy as np

BATCH_SIZE = 65536


def active(style):
    return any(m.get('enabled', True) and float(m.get('amount', 1.)) > 0.
               for m in style.get('brush_maps', {}).values())


def sample(texture, uv):
    pixels = np.asarray(texture['pixels'], np.float32)
    if pixels.ndim != 3 or pixels.shape[2] != 3:
        raise ValueError('Brush map must contain finite RGB samples')
    uv = np.asarray(uv, np.float64)
    if not np.isfinite(uv).all():
        raise ValueError('Brush map UV coordinates must be finite')
    if texture.get('uv_domain') and (np.any(uv < -1e-6) or np.any(uv > 1.+1e-6)):
        raise ValueError('Brush maps currently require UVs in the 0..1 tile; tiled/UDIM UVs are not supported')
    # Maya samples are at texel centres, bottom row first (v increases upwards).
    h, w = pixels.shape[:2]
    repeat = texture.get('repeat', True)
    q = (uv % 1. if repeat else np.clip(uv, 0., 1.))*[w, h]-.5
    low = np.floor(q).astype(np.int64); f = q-low
    x, y = low.T
    def fetch(xx, yy):
        return pixels[yy % h, xx % w] if repeat else pixels[np.clip(yy, 0, h-1), np.clip(xx, 0, w-1)]
    return ((fetch(x,y)*(1-f[:,0,None])+fetch(x+1,y)*f[:,0,None])*(1-f[:,1,None])
            +(fetch(x,y+1)*(1-f[:,0,None])+fetch(x+1,y+1)*f[:,0,None])*f[:,1,None])


def coordinates(packed, camera):
    """Assign profiles before splitting; map samples must not restart a curve."""
    if not any(s.get('width_profile') or s.get('alpha_profile') for s in packed.styles()):
        for p in packed.parts:
            p.setdefault('profile_u', np.tile([0., 1.], (p['count'],1)))
        return
    from .cpu_brush import library
    world = np.ascontiguousarray(np.concatenate([p['points'] for p in packed.parts]), np.float64)
    points = np.ascontiguousarray((world-camera['eye'])@camera['basis'].T)
    n=len(world); keys=np.empty((n,4),np.int64); vertices=np.full((n,2),-1,np.int64)
    angles=np.empty((n,3)); u=np.empty((n,2)); styles={}; lines={}; start=0
    for p in packed.parts:
        end=start+p['count']; s=p['settings']; sl=slice(start,end)
        keys[sl,0]=p['mesh_index']; keys[sl,1]=styles.setdefault(id(s),len(styles))
        keys[sl,2]=lines.setdefault(p.get('line'),len(lines)); keys[sl,3]=p['flags']
        if 'vertex_ids' in p: vertices[sl]=p['vertex_ids']
        angles[sl]=[s.get('profile_direction',-30.),s.get('profile_split_angle',0.),s.get('profile_loop_direction',0)]
        start=end
    lib=library(); fn=lib.rp_profile_coordinates
    fn.argtypes=[c.c_void_p]*5+[c.c_int64]+[c.c_int]*3+[c.c_double]*2+[c.c_void_p]; fn.restype=c.c_int
    status=fn(points.ctypes.data,world.ctypes.data,keys.ctypes.data,vertices.ctypes.data,angles.ctypes.data,n,camera['width'],camera['height'],int(camera['ortho']),camera['span'],camera['focal'],u.ctypes.data)
    if status: raise RuntimeError('Brush-map profile coordinates failed')
    start=0
    for p in packed.parts:
        p.setdefault('profile_u',u[start:start+p['count']]); start+=p['count']


def _piece_batches(part, camera, ss, textures):
    """Clip to the raster then sample at half-output-pixel intervals."""
    from .renderer import _project
    s=part['settings']; maps={k:v for k,v in s.get('brush_maps',{}).items()
                             if v.get('enabled',True) and v.get('amount',1)>0}
    for m in maps.values():
        if m.get('texture_id') not in textures:
            raise ValueError('Brush map texture was not evaluated: '+m.get('node',''))
        if m.get('uv_set','') not in part.get('map_uvs',{}):
            raise ValueError('Brush map UVs unavailable on '+part.get('mesh','mesh'))
    world=part['points']; pc=(world-camera['eye'])@camera['basis'].T
    xy=_project(pc,camera); delta=xy[:,1]-xy[:,0]
    lo=np.zeros(len(world)); hi=np.ones(len(world))
    margin=float(s['line_width'])*ss/2+2
    for axis,extent in enumerate((camera['width'],camera['height'])):
        a=xy[:,0,axis]; d=delta[:,axis]; parallel=np.abs(d)<1e-15
        safe=np.where(parallel,1.,d)
        t0=(-margin-a)/safe; t1=(extent+margin-a)/safe
        lo=np.maximum(lo,np.where(parallel,0.,np.minimum(t0,t1)))
        hi=np.minimum(hi,np.where(parallel,1.,np.maximum(t0,t1)))
        hi=np.where(parallel & ((a < -margin)|(a>extent+margin)), -1., hi)
    ids=np.flatnonzero(hi>lo)
    for source in ids:
        count=max(1,int(np.ceil(np.linalg.norm(delta[source])*(hi[source]-lo[source])*2./ss)))
        for first in range(0,count,BATCH_SIZE):
            last=min(first+BATCH_SIZE,count)
            t=lo[source]+(hi[source]-lo[source])*np.arange(first,last+1)/count
            # Screen interpolation is perspective-corrected back to the surface.
            z0,z1=pc[source,:,2]
            r=t if camera['ortho'] else (t/z1)/((1-t)/z0+t/z1)
            p=world[source,0]+r[:,None]*(world[source,1]-world[source,0])
            mid=(t[:-1]+t[1:])*.5
            rmid=mid if camera['ortho'] else (mid/z1)/((1-mid)/z0+mid/z1)
            n=last-first
            item=dict(part, points=np.stack([p[:-1],p[1:]],axis=1),count=n,
                      flags=np.full(n,part['flags'][source],np.uint8))
            steps=np.arange(first,last)
            item['map_caps']=np.asarray(np.where(steps>0,4,0)|np.where(steps<count-1,8,0),np.uint8)
            item.pop('vertex_ids',None);item.pop('map_uvs',None)
            u=part['profile_u'][source]
            item['profile_u']=u[0]+np.stack([t[:-1],t[1:]],axis=1)*(u[1]-u[0])
            for channel,m in maps.items():
                uv=part['map_uvs'][m.get('uv_set','')][source]
                rgb=np.clip(sample(textures[m['texture_id']],uv[0]+rmid[:,None]*(uv[1]-uv[0])),0.,1.)
                amount=float(m.get('amount',1.))
                if channel=='color':item['mapped_colors']=np.asarray(s['line_color'])*(1-amount)+rgb*amount
                elif channel=='width':item['mapped_widths']=float(s['line_width'])*((1-amount)+amount*rgb.mean(axis=1))
            # Native dashes use per-segment phase; split at their ORIGINAL phase.
            dash=float(s.get('dash_length',0.))*ss
            if dash>0:
                gap=float(s.get('dash_gap',-1.))*ss
                if gap<0:gap=dash
                keep=np.remainder(mid*np.linalg.norm(delta[source]),dash+gap)<dash if gap>0 else np.ones(n,bool)
                item['flags']=np.where(keep,item['flags'],0).astype(np.uint8)
                item['settings']=dict(s,dash_length=0.)
            yield item


def render(packed,camera,depth,planes,layer,ss,textures,visibility=None,
           group_image=None,mesh_groups=None,depth_range=None):
    from .cpu_brush import _clip_packed_depth, render_packed
    from .packed_segments import PackedSegments
    packed._flush()
    for texture in textures.values():
        if not np.isfinite(texture['pixels']).all():raise ValueError('Non-finite brush map pixels')
    if any('records' in p for p in packed.parts):
        raise ValueError('Brush maps require packed CPU strokes')
    # A path crossing the eye plane has no finite projected arc length. Clip
    # that batch before defining its curve domain; retain normal domains otherwise.
    if any(np.any((p['points']-camera['eye'])@camera['basis'][2]<=0) for p in packed.parts):
        packed=_clip_packed_depth(packed,camera,ss)
        if not len(packed):return dict(classified_edges=0,visible_segments=0,hidden_segments=0,merge_suppressed_samples=0,map_samples=0,peak_map_batch=0)
    coordinates(packed,camera)
    clipped=_clip_packed_depth(packed,camera,ss)
    stats=dict(classified_edges=0,visible_segments=0,hidden_segments=0,
               merge_suppressed_samples=0,map_samples=0,peak_map_batch=0,
               segment_backend='native-cpu-uv-brush-maps')
    batch=PackedSegments()
    def flush():
        nonlocal batch
        if not len(batch):return
        result=render_packed(batch,camera,depth,planes,layer,ss,visibility,
                             union_coverage=True,group_image=group_image,
                             mesh_groups=mesh_groups,depth_range=depth_range)
        if result is None:raise ValueError('Brush maps cannot combine with legacy reduction/variation/taper; use depth and width curves')
        for key in ('classified_edges','visible_segments','hidden_segments','merge_suppressed_samples'):
            stats[key]+=result.get(key,0)
        stats['peak_map_batch']=max(stats['peak_map_batch'],len(batch));batch=PackedSegments()
    for part in clipped.parts:
        pieces=_piece_batches(part,camera,ss,textures) if active(part['settings']) else (part,)
        for item in pieces:
            if len(batch)+item['count']>BATCH_SIZE:flush()
            batch.parts.append(item);batch.count+=item['count']
            stats['map_samples']+=item['count']
    flush()
    return stats
