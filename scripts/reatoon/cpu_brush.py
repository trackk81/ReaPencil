"""Batched native CPU runs, evaluating width/alpha at each nearest stroke point."""
import ctypes as c
from pathlib import Path
import numpy as np
_lib=None


def library():
    global _lib
    if _lib is None:
        _lib=c.CDLL(str(Path(__file__).resolve().parents[2]/'plug-ins/2025/reaPencilBrush125.dll'))
        _lib.rp_profile_runs.argtypes=[c.c_void_p,c.c_int,c.c_int,c.c_int64,c.c_void_p,c.c_int64,c.c_void_p,c.c_double,c.c_double,c.c_double,c.c_double,c.c_void_p,c.c_int,c.c_void_p,c.c_int]
        _lib.rp_profile_runs.restype=c.c_int
    return _lib


def draw_runs(layer,runs,original,u0,u1,width,width_table,alpha_table,smoothing=0.,depth_values=None,alpha_depth=None,width_depth=None,alpha_reference=None,width_reference=None):
    global _lib
    if not len(runs):return
    if layer.dtype!=np.float32 or layer.ndim!=3 or layer.shape[2]!=4 or layer.strides[-2:]!=(16,4):raise ValueError('Profile layer must be float32 RGBA')
    library()
    arrays=[np.ascontiguousarray(a,np.float64) for a in (runs,original,width_table,alpha_table)]
    r,o,w,a=arrays
    if r.ndim!=2 or r.shape[1]!=7 or o.shape!=(4,) or any(not np.isfinite(x).all() for x in arrays):raise ValueError('Invalid profile arrays')
    for lut in (w,a):
        if lut.ndim!=2 or lut.shape[1]!=2 or not 2<=len(lut)<=65536 or np.any(np.diff(lut[:,0])<=0):raise ValueError('Invalid profile lookup table')
    if not np.isfinite([u0,u1,width,smoothing]).all() or width<0 or smoothing<0:raise ValueError('Invalid profile stroke parameters')
    args=(layer.ctypes.data,layer.shape[1],layer.shape[0],layer.strides[0]//4,r.ctypes.data,len(r),o.ctypes.data,u0,u1,width,smoothing,w.ctypes.data,len(w),a.ctypes.data,len(a))
    d=None
    if depth_values is not None:
        d=np.ascontiguousarray(depth_values,np.float64)
        if d.shape!=(5,) or not np.isfinite(d).all() or min(d[:2])<=0 or d[3]<=d[2]:raise ValueError('Invalid depth stroke parameters')
    if alpha_reference is not None or width_reference is not None:
        def depth_vector(value):
            if value is None:return None
            a=np.ascontiguousarray(value,np.float64)
            if a.shape!=(7,) or not np.isfinite(a).all() or min(a[:2])<=0 or a[4]<=a[3] or np.any((a[5:]<0)|(a[5:]>1)):raise ValueError('Invalid reference stroke reduction')
            return a
        def reference_vector(value,reduction):
            if value is None:return None
            a=np.ascontiguousarray(value,np.float64)
            if reduction is None or a.shape!=(9,) or not np.isfinite(a).all() or min(a[:2])<=0 or a[2] not in (0,1):raise ValueError('Invalid reference stroke coordinates')
            return a
        ad,wd=depth_vector(alpha_depth),depth_vector(width_depth)
        ar,wr=reference_vector(alpha_reference,ad),reference_vector(width_reference,wd)
        _lib.rp_profile_runs_reference.argtypes=_lib.rp_profile_runs.argtypes+[c.c_void_p]*5;_lib.rp_profile_runs_reference.restype=c.c_int
        status=_lib.rp_profile_runs_reference(*args,*[a.ctypes.data if a is not None else None for a in (d,ad,wd,ar,wr)])
    elif width_depth is not None:
        wd=np.ascontiguousarray(width_depth,np.float64)
        if wd.shape!=(7,) or not np.isfinite(wd).all() or min(wd[:2])<=0 or wd[4]<=wd[3] or np.any((wd[5:]<0)|(wd[5:]>1)):raise ValueError('Invalid width-depth stroke parameters')
        ad=np.ascontiguousarray(alpha_depth,np.float64) if alpha_depth is not None else None
        if ad is not None and (ad.shape!=(7,) or not np.isfinite(ad).all() or min(ad[:2])<=0 or ad[4]<=ad[3] or np.any((ad[5:]<0)|(ad[5:]>1))):raise ValueError('Invalid alpha-depth stroke parameters')
        _lib.rp_profile_runs_depth_width.argtypes=_lib.rp_profile_runs.argtypes+[c.c_void_p]*3;_lib.rp_profile_runs_depth_width.restype=c.c_int
        status=_lib.rp_profile_runs_depth_width(*args,d.ctypes.data if d is not None else None,ad.ctypes.data if ad is not None else None,wd.ctypes.data)
    elif alpha_depth is not None:
        reduction=np.ascontiguousarray(alpha_depth,np.float64)
        if reduction.shape!=(7,) or not np.isfinite(reduction).all() or min(reduction[:2])<=0 or reduction[4]<=reduction[3] or np.any((reduction[5:]<0)|(reduction[5:]>1)):raise ValueError('Invalid alpha-depth stroke parameters')
        _lib.rp_profile_runs_reduced.argtypes=_lib.rp_profile_runs.argtypes+[c.c_void_p,c.c_void_p];_lib.rp_profile_runs_reduced.restype=c.c_int
        status=_lib.rp_profile_runs_reduced(*args,d.ctypes.data if d is not None else None,reduction.ctypes.data)
    elif d is not None:
        _lib.rp_profile_runs_depth.argtypes=_lib.rp_profile_runs.argtypes+[c.c_void_p];_lib.rp_profile_runs_depth.restype=c.c_int
        status=_lib.rp_profile_runs_depth(*args,d.ctypes.data)
    else:status=_lib.rp_profile_runs(*args)
    if status:raise RuntimeError('CPU profile rasterization failed')


def render_segments(records,camera,depth,planes,visible,ss,visibility=None,union_coverage=False):
    """Complete CPU batches for profile raster, without Python per-edge sampling."""
    from .brush_profiles import stroke_tables
    from .native_cpu import Visibility,SegmentResult
    rows=list(records);n=len(rows)
    if not n:return dict(classified_edges=0,visible_segments=0,hidden_segments=0)
    styles=[r['settings'] for r in rows]
    if any((s.get('hidden_lines') and s.get('_visibility_mode')!=-1) or any(float(s.get(k,0))!=0 for k in ('dash_length','distance_reduction','width_variation','taper')) for s in styles):return None
    points=np.ascontiguousarray((np.asarray([[r['a'],r['b']] for r in rows])-camera['eye'])@camera['basis'].T,np.float64)
    if np.any(points[:,:,2]<=0):return None
    tables=[];cache={};offsets=[];cursor=0
    for s in styles:
        key=id(s)
        if key not in cache:
            w,a=stroke_tables(s);cache[key]=[cursor,len(w),cursor+len(w),len(a)];tables.extend([w,a]);cursor+=len(w)+len(a)
        offsets.append(cache[key])
    arrays=[np.ascontiguousarray(a,dtype) for a,dtype in [
        ([r.get('_profile_u',[0.,1.]) for r in rows],np.float64),(np.concatenate(tables),np.float64),(offsets,np.int64),
        ([int(bool(s.get('alpha_profile')) or bool(s.get('alpha_depth_reduction')) or bool(s.get('width_depth_reduction')) or union_coverage)|(2 if '_profile_source_width' in s else 0) for s in styles],np.uint8),
        (points,np.float64),([s['line_width'] for s in styles],np.float64),([s['depth_bias'] for s in styles],np.float64),
        (np.clip([s['line_color'] for s in styles],0,1),np.float64),([s.get('output_to_elements_only',False) for s in styles],np.bool_),([int(bool(r['features']))*(3 if s.get('_visibility_mode')==-1 else 1) for r,s in zip(rows,styles)],np.uint8)]]
    reductions=np.asarray([s.get('alpha_depth_reduction') or [0.,0.,0.,0.] for s in styles],np.float64) if any(s.get('alpha_depth_reduction') for s in styles) else None
    return _execute(arrays,camera,depth,planes,visible,ss,visibility,n,reductions=reductions,size_reductions=np.asarray([s.get('width_depth_reduction') or [0.,0.,0.,0.] for s in styles],np.float64) if any(s.get('width_depth_reduction') for s in styles) else None,alpha_references=_reference_rows(styles,'alpha_reduction_origin'),width_references=_reference_rows(styles,'width_reduction_origin'))


def _execute(arrays,camera,depth,planes,visible,ss,visibility,n,group_image=None,group_ids=None,depth_range=None,reductions=None,size_reductions=None,alpha_references=None,width_references=None):
    from .native_cpu import Visibility,SegmentResult
    context=Visibility(*[visibility[i].ctypes.data for i in (0,3,4,5,1,2,6)],len(visibility[0])) if visibility is not None else None
    eye=np.ascontiguousarray(camera['eye'],np.float64);basis=np.ascontiguousarray(np.linalg.inv(camera['basis']).T,np.float64)
    lib=library();lib.rp_profile_segments.argtypes=[c.c_void_p]*10+[c.c_int64]+[c.c_void_p]*3+[c.c_int]*4+[c.c_double]*4+[c.c_void_p]*8
    lib.rp_profile_segments.restype=c.c_int;lib.rp_profile_free.argtypes=[c.c_void_p];lib.rp_profile_free.restype=None
    result=SegmentResult();merged=c.c_int64()
    gi=np.ascontiguousarray(group_image,np.int32) if group_image is not None else None
    ids=np.ascontiguousarray(group_ids,np.int32) if group_ids is not None else None
    dr=np.ascontiguousarray(depth_range,np.float64) if depth_range is not None else None
    execute=lib.rp_profile_segments
    extra=[]
    if reductions is not None:
        reductions=np.ascontiguousarray(reductions,np.float64)
        if reductions.shape!=(n,4) or not np.isfinite(reductions).all():raise ValueError('Invalid per-segment alpha-depth parameters')
        execute=lib.rp_profile_segments_reduced;execute.argtypes=lib.rp_profile_segments.argtypes+[c.c_void_p];execute.restype=c.c_int;extra=[reductions.ctypes.data]
    if size_reductions is not None:
        size_reductions=np.ascontiguousarray(size_reductions,np.float64)
        if size_reductions.shape!=(n,4) or not np.isfinite(size_reductions).all():raise ValueError('Invalid per-segment width-depth parameters')
        execute=lib.rp_profile_segments_depth_width;execute.argtypes=lib.rp_profile_segments.argtypes+[c.c_void_p]*2;execute.restype=c.c_int
        extra=[reductions.ctypes.data if reductions is not None else None,size_reductions.ctypes.data]
    if alpha_references is not None or width_references is not None:
        refs=[]
        for value in (alpha_references,width_references):
            a=np.ascontiguousarray(value,np.float64) if value is not None else None
            if a is not None and (a.shape!=(n,4) or not np.isfinite(a).all() or np.any((a[:,0]!=0)&(a[:,0]!=1))):raise ValueError('Invalid per-segment reference origins')
            refs.append(a)
        execute=lib.rp_profile_segments_reference;execute.argtypes=lib.rp_profile_segments.argtypes+[c.c_void_p]*4;execute.restype=c.c_int
        extra=[a.ctypes.data if a is not None else None for a in (reductions,size_reductions,*refs)]
    status=execute(*[a.ctypes.data for a in arrays],n,depth.ctypes.data,planes.ctypes.data,visible.ctypes.data,
        camera['width'],camera['height'],ss,int(camera['ortho']),camera['span'],camera['focal'],camera['near'],camera['far'],
        c.byref(context) if context else None,eye.ctypes.data,basis.ctypes.data,gi.ctypes.data if gi is not None else None,ids.ctypes.data if ids is not None else None,c.byref(merged),dr.ctypes.data if dr is not None else None,c.byref(result),*extra)
    try:
        if status:raise RuntimeError('Native CPU profile segment stage failed')
        out=np.ctypeslib.as_array(result.rows,shape=(result.size,5)) if result.size else np.empty((0,5))
        count=int(np.count_nonzero(~arrays[8][out[:,0].astype(np.int64)]))
        is_hidden=bool(n and np.any(arrays[9]&2))
        return dict(classified_edges=n,visible_segments=0 if is_hidden else count,hidden_segments=count if is_hidden else 0,segment_backend='native-cpu-profile-segments',
                    merge_suppressed_samples=merged.value,profile_visibility_refinement=dict(checked_samples=int(result.checked),hidden_samples=int(result.hidden)))
    finally:lib.rp_profile_free(result.rows)


def render_packed(packed,camera,depth,planes,visible,ss,visibility=None,union_coverage=False,group_image=None,mesh_groups=None,depth_range=None,retain_coordinates=False):
    """Keep large batches packed through topology, projection and rasterization."""
    packed._flush()
    if not len(packed):return dict(classified_edges=0,visible_segments=0,hidden_segments=0)
    if any('records' in part for part in packed.parts):return None
    styles=list(packed.styles())
    if any((s.get('hidden_lines') and s.get('_visibility_mode')!=-1) or any(float(s.get(k,0))!=0 for k in ('dash_length','distance_reduction','width_variation','taper')) for s in styles):return None
    from .brush_profiles import stroke_tables
    world,widths,biases,colors,only,enabled=packed.arrays();enabled=enabled.astype(np.uint8);points=np.ascontiguousarray((world-camera['eye'])@camera['basis'].T,np.float64)
    if np.any(points[:,:,2]<=0):return None
    n=len(points);u=np.empty((n,2));keys=np.empty((n,4),np.int64);vertices=np.full((n,2),-1,np.int64)
    angles=np.empty((n,3));offsets=np.empty((n,4),np.int64);alpha=np.empty(n,np.uint8);tables=[];cache={};cursor=0;start=0
    lines={}
    for part in packed.parts:
        end=start+part['count'];sl=slice(start,end);s=part['settings'];key=id(s)
        if key not in cache:
            w,a=stroke_tables(s);cache[key]=(len(cache),[cursor,len(w),cursor+len(w),len(a)])
            tables.extend([w,a]);cursor+=len(w)+len(a)
        sid,off=cache[key];offsets[sl]=off;
        if s.get('_visibility_mode')==-1:enabled[sl]=np.where(enabled[sl]!=0,np.uint8(3),np.uint8(0))
        alpha[sl]=int(bool(s.get('alpha_profile')) or bool(s.get('alpha_depth_reduction')) or bool(s.get('width_depth_reduction')) or union_coverage)|(2 if '_profile_source_width' in s else 0);angles[sl]=[s.get('profile_direction',-30.),s.get('profile_split_angle',0.),s.get('profile_loop_direction',0)]
        line=part.get('line');lid=lines.setdefault(line,len(lines));keys[sl,0]=part['mesh_index'];keys[sl,1]=sid;keys[sl,2]=lid;keys[sl,3]=part['flags']
        if 'vertex_ids' in part:vertices[sl]=part['vertex_ids']
        start=end
    lib=library();lib.rp_profile_coordinates.argtypes=[c.c_void_p]*5+[c.c_int64]+[c.c_int]*3+[c.c_double]*2+[c.c_void_p];lib.rp_profile_coordinates.restype=c.c_int
    if all('profile_u' in part for part in packed.parts):u=np.ascontiguousarray(np.concatenate([part['profile_u'] for part in packed.parts]),np.float64)
    else:
        status=lib.rp_profile_coordinates(points.ctypes.data,world.ctypes.data,keys.ctypes.data,vertices.ctypes.data,angles.ctypes.data,n,camera['width'],camera['height'],int(camera['ortho']),camera['span'],camera['focal'],u.ctypes.data)
        if status:raise RuntimeError('Native profile topology allocation failed')
        start=0
        for part in packed.parts:
            end=start+part['count']
            if 'profile_u' in part:u[start:end]=part['profile_u']
            start=end
    if retain_coordinates:
        start=0
        for part in packed.parts:
            part['profile_u']=u[start:start+part['count']];start+=part['count']
    arrays=[u,np.ascontiguousarray(np.concatenate(tables)),offsets,alpha,points,widths,biases,colors,only,enabled]
    group_ids=None
    if group_image is not None and mesh_groups is not None:
        group_ids=np.concatenate([np.where(((part['flags']&6)!=0)&((part['flags']&np.uint8(249))==0),int(mesh_groups[part['mesh_index']]) if part['settings'].get('merge_groups',True) else -1,-1).astype(np.int32) for part in packed.parts])
    reductions=np.concatenate([np.tile(part['settings'].get('alpha_depth_reduction') or [0.,0.,0.,0.],(part['count'],1)) for part in packed.parts]) if any(s.get('alpha_depth_reduction') for s in styles) else None
    return _execute(arrays,camera,depth,planes,visible,ss,visibility,n,group_image,group_ids,depth_range,reductions,size_reductions=np.concatenate([np.tile(part['settings'].get('width_depth_reduction') or [0.,0.,0.,0.],(part['count'],1)) for part in packed.parts]) if any(s.get('width_depth_reduction') for s in styles) else None,alpha_references=_reference_rows([p['settings'] for p in packed.parts],'alpha_reduction_origin',[p['count'] for p in packed.parts]),width_references=_reference_rows([p['settings'] for p in packed.parts],'width_reduction_origin',[p['count'] for p in packed.parts]))


def _reference_rows(styles,key,counts=None):
    if not any(s.get(key) for s in styles):return None
    rows=np.asarray([[1.,*s[key]] if s.get(key) else [0.,0.,0.,0.] for s in styles],np.float64)
    return rows if counts is None else np.repeat(rows,counts,axis=0)


def reference_vector(a,b,camera,origin):
    if not origin:return None
    relative=np.asarray([a,b])@np.linalg.inv(camera['basis']).T+camera['eye']-np.asarray(origin)
    return [a[2],b[2],int(camera['ortho']),*relative.ravel()]
