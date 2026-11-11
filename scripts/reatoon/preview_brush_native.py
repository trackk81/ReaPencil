"""Owned native preview arithmetic with array-owned allocation lifetimes."""
import ctypes as c
from pathlib import Path
import numpy as np

_lib=None
_attempted=False
status=dict(available=False,calls=0,fallbacks=0)


class _Result(c.Structure):
    _fields_=[('count',c.c_uint64),('points',c.c_void_p),('u',c.c_void_p),('source',c.c_void_p),('thin',c.c_void_p)]


class _Owner:
    def __init__(self,handle,lib):self.handle=handle;self.lib=lib
    def __del__(self):
        try:self.lib.rb_free(self.handle)
        except Exception:pass


def _load():
    global _lib,_attempted
    if _attempted:return _lib
    _attempted=True
    try:
        path=Path(__file__).resolve().parents[2]/'plug-ins/2025/reaPencilPreviewBrush201b.dll'
        lib=c.CDLL(str(path));lib.rb_version.restype=c.c_int
        if lib.rb_version()!=201:raise ValueError('Unexpected preview brush ABI')
        lib.rb_expand.argtypes=[c.c_void_p,c.c_uint64,c.c_void_p,c.c_void_p];lib.rb_expand.restype=c.POINTER(_Result)
        lib.rb_free.argtypes=[c.POINTER(_Result)];lib.rb_free.restype=None;lib.rb_error.restype=c.c_char_p
        _lib=lib;status['available']=True
    except (OSError,AttributeError,ValueError) as error:status['error']=str(error)
    return _lib


def _array(address,ctype,shape,owner):
    raw=(ctype*int(np.prod(shape))).from_address(address);raw._owner=owner
    array=np.ctypeslib.as_array(raw).reshape(shape);array.setflags(write=False);return array


def expand(points,style,camera,phase):
    if style.get('line_pattern',0)!=0 or int(style.get('brush_preset',0)) not in (1,2,3):return None
    lib=_load()
    if lib is None:return None
    points=np.ascontiguousarray(points,np.float64);phase=np.ascontiguousarray(phase,np.float64)
    if not len(points):return np.empty((0,2,3)),np.empty((0,2)),np.empty(0,np.int64),np.empty(0,np.uint8)
    if points.shape!=(len(points),2,3) or phase.shape!=(len(points),2) or not np.isfinite(points).all() or not np.isfinite(phase).all():return None
    config=np.array([*camera['eye'],*np.asarray(camera['basis']).ravel(),*np.linalg.inv(camera['basis']).T.ravel(),camera['width'],camera['height'],camera['span'],camera['focal'],camera['near'],int(camera['ortho']),style['line_width'],style.get('brush_width_scale',1.),style.get('brush_roughness',1.),style.get('brush_density',1.),style['brush_preset'],style.get('pattern_amplitude',3.),style.get('pattern_period',20.)],np.float64)
    if not np.isfinite(config).all():return None
    handle=lib.rb_expand(points.ctypes.data,len(points),phase.ctypes.data,config.ctypes.data)
    if not handle:
        status['fallbacks']+=1;status['error']=(lib.rb_error() or b'Preview compute failed').decode('utf8',errors='replace');return None
    status['calls']+=1;owner=_Owner(handle,lib);result=handle.contents;n=int(result.count)
    return (_array(result.points,c.c_double,(n,2,3),owner),_array(result.u,c.c_double,(n,2),owner),_array(result.source,c.c_int64,(n,),owner),_array(result.thin,c.c_uint8,(n,),owner))
