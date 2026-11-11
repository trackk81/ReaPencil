"""Portable PNG alpha masks and bounded CPU/Preview scan-band geometry."""
import base64,hashlib,zlib,math
from pathlib import Path
from functools import lru_cache
import numpy as np

LEVELS=31

def pack(alpha,name='pattern.png',mode='alpha'):
    array=np.asarray(alpha,np.uint8)
    if array.ndim!=2 or min(array.shape)<1 or max(array.shape)>512:raise ValueError('Pattern mask must be1–512 pixels per side')
    if not np.any(array):raise ValueError('PNG pattern has no visible ink')
    raw=array.tobytes();h,w=array.shape
    return dict(format='reapencil-png-mask',version=1,width=w,height=h,data=base64.b64encode(zlib.compress(raw,9)).decode('ascii'),sha256=hashlib.sha256(raw).hexdigest(),name=Path(name).name[:120],mode=mode)

def validate(value):
    if value=={}:return {}
    keys={'format','version','width','height','data','sha256','name','mode'}
    if not isinstance(value,dict) or set(value)!=keys or value['format']!='reapencil-png-mask' or value['version']!=1:raise ValueError('Invalid PNG pattern data')
    for key in ('width','height'):
        if isinstance(value[key],bool) or not isinstance(value[key],int) or not 1<=value[key]<=512:raise ValueError('Invalid PNG pattern dimensions')
    if not isinstance(value['data'],str) or len(value['data'])>400000 or not isinstance(value['sha256'],str) or len(value['sha256'])!=64:raise ValueError('Invalid PNG pattern payload')
    if not isinstance(value['name'],str) or len(value['name'])>120 or value['mode'] not in ('alpha','dark'):raise ValueError('Invalid PNG pattern metadata')
    array=mask(value)
    if not np.any(array):raise ValueError('PNG pattern is empty')
    return dict(value)

@lru_cache(maxsize=16)
def _decode(w,h,data,digest):
    expected=w*h
    try:
        encoded=base64.b64decode(data,validate=True);stream=zlib.decompressobj();raw=stream.decompress(encoded,expected+1)
    except (ValueError,zlib.error) as error:raise ValueError('Invalid PNG mask compression') from error
    if len(raw)!=expected or not stream.eof or stream.unused_data or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('PNG mask integrity check failed')
    result=np.frombuffer(raw,np.uint8).reshape(h,w);result.setflags(write=False);return result

def mask(value):return _decode(value['width'],value['height'],value['data'],value['sha256'])

def load_png(path,mode='auto'):
    from PySide6 import QtCore,QtGui
    path=Path(path)
    if path.suffix.lower()!='.png':raise ValueError('Choose a PNG image')
    reader=QtGui.QImageReader(str(path));size=reader.size()
    if size.width()<1 or size.height()<1 or max(size.width(),size.height())>4096:raise ValueError('PNG source must be at most4096 pixels per side')
    if bytes(reader.format()).lower()!=b'png':raise ValueError('File is not PNG')
    image=reader.read()
    if image.isNull():raise ValueError('Cannot read PNG: '+reader.errorString())
    if max(image.width(),image.height())>512:image=image.scaled(512,512,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation)
    image=image.convertToFormat(QtGui.QImage.Format_RGBA8888);a=np.frombuffer(image.constBits(),np.uint8,count=image.sizeInBytes()).reshape(image.height(),image.bytesPerLine())[:,:image.width()*4].reshape(image.height(),image.width(),4).copy()
    selected='alpha' if mode=='auto' and np.any(a[:,:,3]!=255) else 'dark' if mode=='auto' else mode
    if selected=='alpha':alpha=a[:,:,3]
    elif selected=='dark':alpha=np.rint((1-(a[:,:,:3]@[.2126,.7152,.0722])/255.)*a[:,:,3]).astype(np.uint8)
    else:raise ValueError('Unknown PNG mask mode')
    return pack(alpha,path.name,selected)

def is_image(style):return style.get('line_pattern')==7 or style.get('brush_preset')==4

def band_geometry(style):
    height=2*float(style.get('pattern_amplitude',3.)) if style.get('line_pattern')==7 else float(style['line_width'])*float(style.get('brush_width_scale',1.))
    height=max(height,.001);rows=max(1,min(512,int(math.ceil(height*2))))
    return height,rows,height/rows

def child_style(style,level):
    value=dict(style,line_pattern=0,brush_preset=0,line_image={},brush_image={},_png_band=True)
    value['line_width']=band_geometry(style)[2];value['line_opacity']=float(style.get('line_opacity',1.))*level/LEVELS
    for key in ('_png_owners','_preset_owners'):value.pop(key,None)
    return value

@lru_cache(maxsize=16)
def _float_mask(w,h,data,digest):return _decode(w,h,data,digest).astype(np.float32)/255.

def _sample(value,x,y):
    a=_float_mask(value['width'],value['height'],value['data'],value['sha256']);h,w=a.shape
    xx=np.mod(x,1.)*w-.5;yy=np.clip(y,0,1)*h-.5
    x0=np.floor(xx).astype(int);y0=np.floor(yy).astype(int);fx=xx-x0;fy=yy-y0
    p=a[np.clip(y0,0,h-1),x0%w]*(1-fx)+a[np.clip(y0,0,h-1),(x0+1)%w]*fx
    q=a[np.clip(y0+1,0,h-1),x0%w]*(1-fx)+a[np.clip(y0+1,0,h-1),(x0+1)%w]*fx
    return p*(1-fy)+q*fy

def expand(points,style,camera,scale,phase,path_offsets):
    """Raster mask coverage → thin world segments, grouped by31 alpha levels."""
    from . import renderer as r
    points=np.asarray(points,float);cam=(points-camera['eye'])@camera['basis'].T
    source_interval=(0.,1.)
    if np.any(cam[:,2]<camera['near']) or np.any(cam[:,2]>camera['far']):
        clipped=r._clip_segment(cam[0],cam[1],camera['near'],camera['far'])
        if clipped is None:return []
        dz=cam[1,2]-cam[0,2]
        source_interval=tuple((v[2]-cam[0,2])/dz for v in clipped) if abs(dz)>1e-20 else (0.,1.)
        cam=np.asarray(clipped);phase=None
    p,q=r._project(cam,camera)/scale;delta=q-p;length=np.linalg.norm(delta)
    if length<1e-8:return []
    height,rows,band=band_geometry(style);period=float(style.get('pattern_period',20.));margin=height+period+float(style.get('pattern_amplitude',3.))
    limits=r._screen_clip(p,q,camera['width']/scale,camera['height']/scale,margin)
    if limits is None:return []
    lo,hi=limits;count=max(1,int(np.ceil(length*(hi-lo)*2)))
    if rows*count>2000000:raise ValueError('PNG pattern exceeds the scan-band budget; reduce pattern height')
    u=np.linspace(lo,hi,count+1);mid=(u[:-1]+u[1:])*.5
    d=(phase[0]+u*(phase[1]-phase[0]))/scale if phase is not None else u*length
    dm=(d[:-1]+d[1:])*.5;yy=(np.arange(rows)+.5)/rows
    alpha=np.ones((rows,count))
    if style.get('line_pattern')==7:
        image=style.get('line_image',{})
        if not image:return []
        alpha*=_sample(image,dm[None,:]/period,yy[:,None])
    if style.get('brush_preset')==4:
        image=style.get('brush_image',{})
        if not image:return []
        alpha*=_sample(image,dm[None,:]/float(style.get('brush_stamp_spacing',24.)),yy[:,None])
        alpha*=style.get('brush_density',1.)
    if style.get('line_pattern')==7 and int(style.get('brush_preset',0)) in (1,2,3):
        from .stroke_presets import _noise
        brush=int(style['brush_preset']);threshold=1.-(1.-(0.,.10,.33,.16)[brush])*style.get('brush_density',1.)
        alpha*=_noise(dm[None,:]*.9,np.arange(rows)[:,None]+brush*41)>threshold
    levels=np.rint(np.clip(alpha,0,1)*LEVELS).astype(np.uint8)
    tangent=delta/length;normal=np.array([-tangent[1],tangent[0]])
    if phase is not None and phase[1]<phase[0]:tangent=-tangent;normal=-normal
    along,offset,keep=path_offsets(d,style)
    output=[]
    for level in np.unique(levels):
        if level==0:continue
        chosen=(levels==level)&keep[None,:]
        if int(style.get('line_pattern',0)) in (0,1,7):
            row,left=np.nonzero(chosen & ~np.pad(chosen[:,:-1],((0,0),(1,0))))
            end_row,right=np.nonzero(chosen & ~np.pad(chosen[:,1:],((0,0),(0,1))))
            indices=np.column_stack((left,right+1))
        else:
            row,col=np.nonzero(chosen);indices=np.column_stack((col,col+1))
        ts=u[indices];z=cam[0,2]+ts*(cam[1,2]-cam[0,2]) if camera['ortho'] else 1/((1-ts)/cam[0,2]+ts/cam[1,2])
        offsets=offset[indices]+height*(yy[row,None]-.5)
        xy=(p+ts[:,:,None]*delta+along[indices][:,:,None]*tangent+offsets[:,:,None]*normal)*scale
        local=np.empty((len(ts),2,3));local[:,:,2]=z
        if camera['ortho']:
            factor=camera['width']/camera['span'];local[:,:,:2]=(xy-[camera['width']/2,camera['height']/2])/[factor,-factor]
        else:local[:,:,:2]=(xy-[camera['width']/2,camera['height']/2])*z[:,:,None]/[camera['focal'],-camera['focal']]
        world=local@np.linalg.inv(camera['basis']).T+camera['eye'];output.append((world,source_interval[0]+ts*(source_interval[1]-source_interval[0]),('png',int(level))))
    return output
