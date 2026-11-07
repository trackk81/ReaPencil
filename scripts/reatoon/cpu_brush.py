"""Batched native CPU runs, evaluating width/alpha at each nearest stroke point."""
import ctypes as c
from pathlib import Path
import numpy as np
_lib=None


def library():
    global _lib
    if _lib is None:
        _lib=c.CDLL(str(Path(__file__).resolve().parents[2]/'plug-ins/2025/reaPencilBrush108.dll'))
        _lib.rp_profile_runs.argtypes=[c.c_void_p,c.c_int,c.c_int,c.c_int64,c.c_void_p,c.c_int64,c.c_void_p,c.c_double,c.c_double,c.c_double,c.c_double,c.c_void_p,c.c_int,c.c_void_p,c.c_int]
        _lib.rp_profile_runs.restype=c.c_int
    return _lib


def draw_runs(layer,runs,original,u0,u1,width,width_table,alpha_table,smoothing=0.):
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
    status=_lib.rp_profile_runs(layer.ctypes.data,layer.shape[1],layer.shape[0],layer.strides[0]//4,r.ctypes.data,len(r),o.ctypes.data,u0,u1,width,smoothing,w.ctypes.data,len(w),a.ctypes.data,len(a))
    if status:raise RuntimeError('CPU profile rasterization failed')


def render_segments(records,camera,depth,planes,visible,ss,visibility=None,union_coverage=False):
    """Complete CPU batches for profile raster, without Python per-edge sampling."""
    from .brush_profiles import stroke_tables
    from .native_cpu import Visibility,SegmentResult
    rows=list(records);n=len(rows)
    if not n:return dict(classified_edges=0,visible_segments=0,hidden_segments=0)
    styles=[r['settings'] for r in rows]
    if any(s.get('hidden_lines') or any(float(s.get(k,0))!=0 for k in ('dash_length','distance_reduction','width_variation','taper')) for s in styles):return None
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
        ([int(bool(s.get('alpha_profile')) or union_coverage)|(2 if '_profile_source_width' in s else 0) for s in styles],np.uint8),
        (points,np.float64),([s['line_width'] for s in styles],np.float64),([s['depth_bias'] for s in styles],np.float64),
        (np.clip([s['line_color'] for s in styles],0,1),np.float64),([s.get('output_to_elements_only',False) for s in styles],np.bool_),([bool(r['features']) for r in rows],np.bool_)]]
    return _execute(arrays,camera,depth,planes,visible,ss,visibility,n)


def _execute(arrays,camera,depth,planes,visible,ss,visibility,n):
    from .native_cpu import Visibility,SegmentResult
    context=Visibility(*[visibility[i].ctypes.data for i in (0,3,4,5,1,2,6)],len(visibility[0])) if visibility is not None else None
    eye=np.ascontiguousarray(camera['eye'],np.float64);basis=np.ascontiguousarray(np.linalg.inv(camera['basis']).T,np.float64)
    lib=library();lib.rp_profile_segments.argtypes=[c.c_void_p]*10+[c.c_int64]+[c.c_void_p]*3+[c.c_int]*4+[c.c_double]*4+[c.c_void_p]*4
    lib.rp_profile_segments.restype=c.c_int;lib.rp_profile_free.argtypes=[c.c_void_p];lib.rp_profile_free.restype=None
    result=SegmentResult()
    status=lib.rp_profile_segments(*[a.ctypes.data for a in arrays],n,depth.ctypes.data,planes.ctypes.data,visible.ctypes.data,
        camera['width'],camera['height'],ss,int(camera['ortho']),camera['span'],camera['focal'],camera['near'],camera['far'],
        c.byref(context) if context else None,eye.ctypes.data,basis.ctypes.data,c.byref(result))
    try:
        if status:raise RuntimeError('Native CPU profile segment stage failed')
        out=np.ctypeslib.as_array(result.rows,shape=(result.size,5)) if result.size else np.empty((0,5))
        count=int(np.count_nonzero(~arrays[8][out[:,0].astype(np.int64)]))
        return dict(classified_edges=n,visible_segments=count,hidden_segments=0,segment_backend='native-cpu-profile-segments',
                    profile_visibility_refinement=dict(checked_samples=int(result.checked),hidden_samples=int(result.hidden)))
    finally:lib.rp_profile_free(result.rows)


def render_packed(packed,camera,depth,planes,visible,ss,visibility=None,union_coverage=False):
    """Keep large batches packed through topology, projection and rasterization."""
    packed._flush()
    if not len(packed):return dict(classified_edges=0,visible_segments=0,hidden_segments=0)
    if any('records' in part for part in packed.parts):return None
    styles=list(packed.styles())
    if any(s.get('hidden_lines') or any(float(s.get(k,0))!=0 for k in ('dash_length','distance_reduction','width_variation','taper')) for s in styles):return None
    from .brush_profiles import stroke_tables
    world,widths,biases,colors,only,enabled=packed.arrays();points=np.ascontiguousarray((world-camera['eye'])@camera['basis'].T,np.float64)
    if np.any(points[:,:,2]<=0):return None
    n=len(points);u=np.empty((n,2));keys=np.empty((n,4),np.int64);vertices=np.full((n,2),-1,np.int64)
    angles=np.empty((n,3));offsets=np.empty((n,4),np.int64);alpha=np.empty(n,np.uint8);tables=[];cache={};cursor=0;start=0
    lines={}
    for part in packed.parts:
        end=start+part['count'];sl=slice(start,end);s=part['settings'];key=id(s)
        if key not in cache:
            w,a=stroke_tables(s);cache[key]=(len(cache),[cursor,len(w),cursor+len(w),len(a)])
            tables.extend([w,a]);cursor+=len(w)+len(a)
        sid,off=cache[key];offsets[sl]=off;alpha[sl]=int(bool(s.get('alpha_profile')) or union_coverage)|(2 if '_profile_source_width' in s else 0);angles[sl]=[s.get('profile_direction',-30.),s.get('profile_split_angle',0.),s.get('profile_loop_direction',0)]
        line=part.get('line');lid=lines.setdefault(line,len(lines));keys[sl,0]=part['mesh_index'];keys[sl,1]=sid;keys[sl,2]=lid;keys[sl,3]=part['flags']
        if 'vertex_ids' in part:vertices[sl]=part['vertex_ids']
        start=end
    lib=library();lib.rp_profile_coordinates.argtypes=[c.c_void_p]*5+[c.c_int64]+[c.c_int]*3+[c.c_double]*2+[c.c_void_p];lib.rp_profile_coordinates.restype=c.c_int
    status=lib.rp_profile_coordinates(points.ctypes.data,world.ctypes.data,keys.ctypes.data,vertices.ctypes.data,angles.ctypes.data,n,camera['width'],camera['height'],int(camera['ortho']),camera['span'],camera['focal'],u.ctypes.data)
    if status:raise RuntimeError('Native profile topology allocation failed')
    arrays=[u,np.ascontiguousarray(np.concatenate(tables)),offsets,alpha,points,widths,biases,colors,only,enabled]
    return _execute(arrays,camera,depth,planes,visible,ss,visibility,n)
