"""CPU polygon tessellation fallback for complex texture-alpha holes on Windows.

Use the system GLU tessellator without submitting any graphics commands. The
odd winding rule preserves nested holes regardless of contour orientation.
"""
import ctypes as C
from functools import lru_cache
import numpy as np

@lru_cache(maxsize=1)
def _library():
    if not hasattr(C,'WinDLL'):raise RuntimeError('Complex alpha tessellation requires Windows GLU')
    lib=C.WinDLL('glu32.dll');ptr=C.c_void_p;dbl=C.c_double;uint=C.c_uint
    declarations={
        'gluNewTess':([],ptr),'gluDeleteTess':([ptr],None),
        'gluTessCallback':([ptr,uint,ptr],None),
        'gluTessProperty':([ptr,uint,dbl],None),
        'gluTessNormal':([ptr,dbl,dbl,dbl],None),
        'gluTessBeginPolygon':([ptr,ptr],None),'gluTessEndPolygon':([ptr],None),
        'gluTessBeginContour':([ptr],None),'gluTessEndContour':([ptr],None),
        'gluTessVertex':([ptr,C.POINTER(dbl),ptr],None),
    }
    for name,(args,result) in declarations.items():
        fn=getattr(lib,name);fn.argtypes=args;fn.restype=result
    return lib

def triangulate(loops):
    if not loops:return np.empty((0,3,2),np.float64)
    arrays=[np.asarray(p,np.float64).reshape(-1,2) for p in loops]
    if any(len(p)<3 or not np.isfinite(p).all() for p in arrays):raise ValueError('Invalid alpha contours')
    coords=np.zeros((sum(map(len,arrays)),3),np.float64);coords[:,:2]=np.concatenate(arrays)
    points=coords[:,:2].tolist();indices=[];errors=[];callback=C.WINFUNCTYPE
    def begin(mode):
        if mode!=4:errors.append('Non-triangle primitive: %s'%mode)
    def vertex(data):indices.append(int(data)-1)
    def combine(xyz,data,weights,result):
        points.append([xyz[0],xyz[1]]);result[0]=len(points)
    callbacks={100100:callback(None,C.c_uint)(begin),
        100101:callback(None,C.c_void_p)(vertex),
        100104:callback(None,C.c_ubyte)(lambda flag:None),
        100103:callback(None,C.c_uint)(lambda code:errors.append(code)),
        100105:callback(None,C.POINTER(C.c_double),C.POINTER(C.c_void_p),C.POINTER(C.c_float),C.POINTER(C.c_void_p))(combine)}
    lib=_library();tess=lib.gluNewTess()
    if not tess:raise MemoryError('Cannot allocate alpha tessellator')
    try:
        for kind,fn in callbacks.items():lib.gluTessCallback(tess,kind,C.cast(fn,C.c_void_p))
        lib.gluTessProperty(tess,100140,100130.) # GLU_TESS_WINDING_RULE / ODD
        lib.gluTessNormal(tess,0.,0.,1.)
        lib.gluTessBeginPolygon(tess,None);offset=0
        for loop in arrays:
            lib.gluTessBeginContour(tess)
            for i in range(offset,offset+len(loop)):
                lib.gluTessVertex(tess,C.cast(coords.ctypes.data+i*24,C.POINTER(C.c_double)),i+1)
            offset+=len(loop);lib.gluTessEndContour(tess)
        lib.gluTessEndPolygon(tess)
    finally:lib.gluDeleteTess(tess)
    if errors or len(indices)%3:raise ValueError('Alpha tessellation failed: '+str(errors))
    return np.asarray(points,np.float64)[np.asarray(indices,np.int64).reshape(-1,3)]
