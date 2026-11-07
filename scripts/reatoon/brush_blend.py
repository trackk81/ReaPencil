"""CPU brush composition inferred from controlled original RGBA samples."""
import colorsys
import ctypes as c
import numpy as np

MODES=('Normal','Additive','Subtractive','Multiply','Screen','Overlay','Hard Light','Soft Light',
       'Darken','Lighten','Difference','Exclusion','Hue','Saturation','Color','Luminosity')

def blend_color(back,source,mode):
    b,s=np.broadcast_arrays(np.asarray(back,float),np.asarray(source,float))
    if mode==0:return s
    if mode==1:return b+s
    if mode==2:return b-s
    if mode==3:return b*s
    if mode==4:return b+s-b*s
    if mode==5:return np.where(b<.5,2*b*s,1-2*(1-b)*(1-s))
    if mode==6:return np.where(s<.5,2*b*s,1-2*(1-b)*(1-s))
    if mode==7:
        d=np.where(b<=.25,((16*b-12)*b+4)*b,np.sqrt(np.maximum(b,0)))
        return np.where(s<=.5,b-(1-2*s)*b*(1-b),b+(2*s-1)*(d-b))
    if mode==8:return np.minimum(b,s)
    if mode==9:return np.maximum(b,s)
    if mode==10:return np.abs(b-s)
    if mode==11:return b+s-2*b*s
    if not 12<=mode<=15:raise ValueError('Unknown CPU brush blend mode')
    rows=[]
    for x,y in zip(b.reshape(-1,3),s.reshape(-1,3)):
        bh,bs,bv=colorsys.rgb_to_hsv(*x);sh,ss,sv=colorsys.rgb_to_hsv(*y)
        rows.append(colorsys.hsv_to_rgb(*( (bh,ss,sv) if mode==12 else (sh,bs,sv) if mode==13 else (bh,bs,sv) if mode==14 else (sh,ss,bv))))
    return np.asarray(rows).reshape(b.shape)

def reference(target,source,mode,opacity):
    """White-matte RGB and independent Porter-Duff coverage alpha."""
    target=np.asarray(target,np.float64);source=np.asarray(source,np.float64)
    sa=source[...,3:4]*opacity;ba=target[...,3:4]
    straight=np.divide(source[...,:3],source[...,3:4],out=np.zeros_like(source[...,:3]),where=source[...,3:4]>0)
    back=target[...,:3]+1-ba
    display=np.clip(back*(1-sa)+blend_color(back,straight,mode)*sa,0,1)
    alpha=sa+ba*(1-sa)
    result=np.concatenate((display-(1-alpha),alpha),axis=-1).astype(np.float32)
    return np.where(sa>0,result,target).astype(np.float32)

def composite(target,source,mode=0,opacity=1.):
    if not 0<=int(mode)<len(MODES) or int(mode)!=mode or not np.isfinite(opacity) or not 0<=opacity<=1:
        raise ValueError('Invalid brush composition parameters')
    if target.shape!=source.shape or target.dtype!=np.float32 or source.dtype!=np.float32 or not target.flags.c_contiguous or not source.flags.c_contiguous:
        raise ValueError('Brush layers must be contiguous float32 RGBA')
    from .cpu_brush import library
    lib=library();lib.rp_brush_composite.argtypes=[c.c_void_p,c.c_void_p,c.c_int64,c.c_int,c.c_double];lib.rp_brush_composite.restype=c.c_int
    if lib.rp_brush_composite(target.ctypes.data,source.ctypes.data,target.size//4,int(mode),opacity):raise RuntimeError('CPU brush composition failed')
