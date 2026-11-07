"""Optional CPU-only bulk kernels; portable NumPy/Numba paths remain available."""
import ctypes
from pathlib import Path
import numpy as np
_lib=None

class QueryMesh(ctypes.Structure):
    _fields_=[(k,ctypes.c_void_p) for k in ('low','high','child','ranges','order','tri','triLow','triHigh','indices','owners','normal','area','longest','activeTri','activeNode')]
class QueryResult(ctypes.Structure):
    _fields_=[('rows',ctypes.POINTER(ctypes.c_double)),('size',ctypes.c_int64),('counts',ctypes.c_int64*9),('code',ctypes.c_int)]

class Visibility(ctypes.Structure):
    _fields_=[(k,ctypes.c_void_p) for k in ('roots','child','ranges','order','low','high','tri')]+[('nr',ctypes.c_int64)]
class SegmentResult(ctypes.Structure):
    _fields_=[('rows',ctypes.POINTER(ctypes.c_double)),('size',ctypes.c_int64),('checked',ctypes.c_int64),('hidden',ctypes.c_int64)]

def library():
    global _lib
    if _lib is False:return None
    if _lib is None:
        try:
            lib=ctypes.CDLL(str(Path(__file__).resolve().parents[2]/'plug-ins/2025/reaPencilCPU111.dll'))
            lib.rp_facts.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int64]+[ctypes.c_void_p]*6
            lib.rp_facts.restype=ctypes.c_int
            lib.rp_bvh.argtypes=[ctypes.c_void_p]*2+[ctypes.c_int64]*2+[ctypes.c_void_p]*5
            lib.rp_bvh.restype=ctypes.c_int64
            lib.rp_edges.argtypes=[ctypes.c_void_p]*3+[ctypes.c_int64]*2+[ctypes.c_void_p]*9
            lib.rp_edges.restype=ctypes.c_int64
            lib.rp_depth.argtypes=[ctypes.c_void_p]*2+[ctypes.c_int64]+[ctypes.c_void_p]*3+[ctypes.c_int,ctypes.c_int64]+[ctypes.c_int]*3+[ctypes.c_double]*4
            lib.rp_depth.restype=ctypes.c_int64
            lib.rp_query.argtypes=[ctypes.POINTER(QueryMesh),ctypes.POINTER(QueryMesh),ctypes.c_int,ctypes.c_double,ctypes.c_int64,ctypes.c_int64,ctypes.POINTER(QueryResult)]
            lib.rp_query.restype=ctypes.c_int
            lib.rp_query_free.argtypes=[ctypes.POINTER(ctypes.c_double)]
            lib.rp_query_free.restype=None
            ptr=ctypes.c_void_p;integer=ctypes.c_int;wide=ctypes.c_int64;real=ctypes.c_double
            signatures={
                'rp_stroke':[ptr,integer,integer,wide,ptr,ptr,real,ptr],
                'rp_down':[ptr,ptr,integer,integer,integer,integer],
                'rp_active':[ptr]*5+[wide],
                'rp_surface':[ptr]*3+[integer]*3+[real],
                'rp_mask':[ptr,ptr,wide]+[ptr]*3+[integer]*3+[real]*7,
                'rp_segments':[ptr]*6+[wide]+[ptr]*3+[integer]*4+[real]*4+[ptr]*4,
            }
            for name,args in signatures.items():
                function=getattr(lib,name);function.argtypes=args;function.restype=integer if name=='rp_segments' else None
            _lib=lib
        except OSError:_lib=False;return None
    return _lib

def facts(vertices,triangles):
    lib=library()
    if lib is None:return None
    v=np.ascontiguousarray(vertices,np.float64);t=np.ascontiguousarray(triangles,np.int64);n=len(t)
    values=[np.empty((n,3,3)),np.empty((n,3)),np.empty((n,3)),np.empty((n,3)),np.empty(n),np.empty(n)]
    if lib.rp_facts(v.ctypes.data,t.ctypes.data,n,*[a.ctypes.data for a in values])!=0:raise RuntimeError('CPU triangle preparation failed')
    return values

def bvh(lows,highs):
    lib=library()
    if lib is None:return None
    a=np.ascontiguousarray(lows,np.float64);b=np.ascontiguousarray(highs,np.float64);n=len(a);cap=2*(n//8+1)+1
    arrays=[np.empty((cap,3)),np.empty((cap,3)),np.empty((cap,2),np.int64),np.empty((cap,2),np.int64),np.empty(n,np.int64)]
    used=lib.rp_bvh(a.ctypes.data,b.ctypes.data,n,cap,*[x.ctypes.data for x in arrays])
    if used<0:raise RuntimeError('CPU BVH preparation failed')
    return tuple(x[:used] for x in arrays[:4])+(arrays[4],)

def edges(vertices,flat,counts,mids):
    lib=library()
    if lib is None:return None
    v=np.ascontiguousarray(vertices,np.float64);f=np.ascontiguousarray(flat,np.int64);c=np.ascontiguousarray(counts,np.int64);m=np.ascontiguousarray(mids,np.int64)
    nf,nc=len(c),len(f)
    if v.ndim!=2 or v.shape[1]!=3 or not np.isfinite(v).all():raise ValueError('Vertices must be finite Nx3')
    if c.ndim!=1 or np.any(c<3) or int(c.sum())!=nc:raise ValueError('Invalid polygon counts')
    if f.ndim!=1 or (nc and (f.min()<0 or f.max()>=len(v))):raise ValueError('Invalid polygon indices')
    if m.ndim!=1 or len(m)!=nf:raise ValueError('One material ID is required per polygon')
    arrays=[np.empty((nf,3)),np.empty((nf,3)),np.empty((nc,2),np.int64),np.empty(nc,np.int64),np.empty(nc,np.int64),np.empty(nc,np.int64),np.empty(nc),np.empty(nc,np.uint8)]
    n=lib.rp_edges(v.ctypes.data,f.ctypes.data,c.ctypes.data,nf,nc,m.ctypes.data,*[x.ctypes.data for x in arrays])
    if n<0:raise RuntimeError('CPU edge preparation failed')
    normals,centers,pairs,owners,starts,counts,dot,material=arrays
    return dict(vertices=v,normals=normals,centers=centers,pairs=pairs[:n].copy(),owners=owners,starts=starts[:n].copy(),counts=counts[:n].copy(),min_dot=dot[:n].copy(),material=material[:n].astype(bool))

def depth(vertices,triangles,camera,depth,planes,owners,index):
    lib=library()
    if lib is None:return None
    count=lib.rp_depth(vertices.ctypes.data,triangles.ctypes.data,len(triangles),depth.ctypes.data,planes.ctypes.data,
        owners.ctypes.data if owners is not None else None,owners.dtype.itemsize if owners is not None else 0,int(index),
        int(camera['width']),int(camera['height']),int(camera['ortho']),float(camera['span']),float(camera['focal']),float(camera['near']),float(camera['far']))
    if count<0:raise RuntimeError('Native CPU depth failed')
    return int(count)

def query(*args):
    a=list(args)
    if len(a)==30:a.extend([None]*4)
    def pack(indices):return QueryMesh(*[a[i].ctypes.data if a[i] is not None else None for i in indices])
    first=pack([0,1,2,3,4,10,12,13,16,18,20,22,24,30,32])
    second=pack([5,6,7,8,9,11,14,15,17,19,21,23,25,31,33])
    result=QueryResult();lib=library()
    if lib.rp_query(ctypes.byref(first),ctypes.byref(second),int(a[26]),float(a[27]),int(a[28]),int(a[29]),ctypes.byref(result))!=0:
        raise RuntimeError('Native CPU intersection allocation failed')
    try:
        if result.code==3:raise ValueError('Triangle coordinates exceed robust native predicate range')
        rows=np.ctypeslib.as_array(result.rows,shape=(result.size,8)).copy() if result.size else np.empty((0,8))
        return rows,np.asarray(result.counts).copy(),result.code
    finally:lib.rp_query_free(result.rows)


def stroke(layer,a,b,width,color):
    if layer.dtype!=np.float32 or layer.strides[-2:]!=(16,4):
        from .accelerator import enable
        enable()
        from ._stroke_kernel import stroke as reference
        return reference(layer,a,b,width,color)
    a=np.ascontiguousarray(a,np.float64);b=np.ascontiguousarray(b,np.float64);color=np.ascontiguousarray(color,np.float64)
    library().rp_stroke(layer.ctypes.data,layer.shape[1],layer.shape[0],layer.strides[0]//4,a.ctypes.data,b.ctypes.data,float(width),color.ctypes.data)

def down_float32(image,scale):
    image=np.ascontiguousarray(image,np.float32);h,w,c=image.shape
    out=np.empty((h//scale,w//scale,c),np.float32)
    library().rp_down(image.ctypes.data,out.ctypes.data,w,h,c,int(scale))
    return out

def active_bvh_nodes(child,ranges,order,triangles):
    out=np.empty(len(child),np.bool_)
    library().rp_active(child.ctypes.data,ranges.ctypes.data,order.ctypes.data,triangles.ctypes.data,out.ctypes.data,len(child))
    return out

def surface_bounds(depth,planes,ortho,margin):
    depth=np.ascontiguousarray(depth,np.float64);planes=np.ascontiguousarray(planes,np.float64)
    out=np.empty_like(depth);h,w=depth.shape
    library().rp_surface(depth.ctypes.data,planes.ctypes.data,out.ctypes.data,w,h,int(ortho),float(margin))
    return out

def triangle_mask(vertices,triangles,bounds,ortho,span,focal,near,far,bias,margin,tolerance):
    vertices=np.ascontiguousarray(vertices,np.float64);triangles=np.ascontiguousarray(triangles,np.int64)
    out=np.empty(len(triangles),np.bool_);counts=np.zeros(4,np.int64);h,w=bounds.shape
    library().rp_mask(vertices.ctypes.data,triangles.ctypes.data,len(triangles),bounds.ctypes.data,out.ctypes.data,counts.ctypes.data,w,h,int(ortho),span,focal,near,far,bias,margin,tolerance)
    return out,counts

def segments(points,widths,biases,colors,only,enabled,depth,planes,visible,ss,ortho,span,focal,near,far,visibility,eye,inverse_basis,stats):
    arrays=[np.ascontiguousarray(a,dtype) for a,dtype in zip((points,widths,biases,colors,only,enabled),(np.float64,np.float64,np.float64,np.float64,np.bool_,np.uint8))]
    eye=np.ascontiguousarray(eye,np.float64);inverse_basis=np.ascontiguousarray(inverse_basis,np.float64)
    context=Visibility(*[visibility[i].ctypes.data for i in (0,3,4,5,1,2,6)],len(visibility[0])) if visibility is not None else None
    result=SegmentResult();h,w=depth.shape;lib=library()
    status=lib.rp_segments(*[a.ctypes.data for a in arrays],len(points),depth.ctypes.data,planes.ctypes.data,visible.ctypes.data,w,h,int(ss),int(ortho),span,focal,near,far,ctypes.byref(context) if context else None,eye.ctypes.data,inverse_basis.ctypes.data,ctypes.byref(result))
    if status!=0:raise RuntimeError('Native CPU segment allocation failed')
    try:
        rows=np.ctypeslib.as_array(result.rows,shape=(result.size,5)).copy() if result.size else np.empty((0,5))
        stats[:]=[result.checked,result.hidden]
        return [(int(row[0]),*row[1:]) for row in rows]
    finally:lib.rp_query_free(result.rows)
