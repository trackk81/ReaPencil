"""Viewport-only alpha contours on original triangles; no CPU cutout expansion.

A masked depth prepass handles occlusion between alpha cards. The final CPU renderer and
the precise polygon-cutout fallback never use this representation.
"""
import os
import ctypes as c
from functools import lru_cache
import numpy as np
from . import alpha_boundary as alpha

_library=None
OPTION='reaPencilPreviewGPUAlpha'
_allocated_bytes=0
MAX_TEXTURE_BYTES=256*1024*1024

def bind(lib):
    global _library
    _library=lib if all(hasattr(lib,name) for name in ('rt_add_alpha','rt_add_alpha_depth','rt_alpha_phase','rt_alpha_mask','rt_alpha_effect')) else None
    texture.cache_clear()
    if _library is None:return
    from pathlib import Path
    lib.rt_alpha_effect.argtypes=[c.c_char_p];lib.rt_alpha_effect.restype=None
    lib.rt_alpha_effect(str(Path(__file__).parent/'shaders/retained_alpha212.ogsfx').encode('utf8'))
    lib.rt_alpha_mask.argtypes=[c.c_void_p,c.c_uint,c.c_uint,c.c_float];lib.rt_alpha_mask.restype=c.c_int
    lib.rt_alpha_phase.argtypes=[c.c_int];lib.rt_alpha_phase.restype=None
    lib.rt_add_alpha.argtypes=[c.c_void_p,c.c_void_p,c.c_uint,c.c_int,c.c_uint];lib.rt_add_alpha.restype=c.c_int
    lib.rt_add_alpha_depth.argtypes=lib.rt_add_alpha.argtypes;lib.rt_add_alpha_depth.restype=c.c_int

def enabled():
    from maya import cmds
    from . import preview_settings,retained_viewport
    return (_library is not None and retained_viewport._mode=='retained'
            and not preview_settings.value(preview_settings.INTERSECTIONS,True)
            and cmds.optionVar(exists=OPTION) and bool(cmds.optionVar(q=OPTION)))

@lru_cache(maxsize=32)
def texture(path,modified,size,channel,invert,threshold,resolution):
    global _allocated_bytes
    from PySide6.QtGui import QImage
    from PySide6.QtCore import Qt
    image=QImage(path)
    if image.isNull():
        # Maya supports DDS foliage even when the Qt image plugins do not.
        from maya.api import OpenMaya as om
        decoded=om.MImage();decoded.readFromFile(path)
        w,h=decoded.getSize()
        pixels=np.ctypeslib.as_array(c.cast(int(decoded.pixels()),c.POINTER(c.c_ubyte)),shape=(h,w,4))
        image=QImage(pixels[::-1].copy().tobytes(),w,h,w*4,QImage.Format_RGBA8888).copy()
    if channel=='alpha' and not image.hasAlphaChannel():raise ValueError('Image has no alpha channel: '+path)
    if max(image.width(),image.height())>resolution:image=image.scaled(resolution,resolution,Qt.KeepAspectRatio,Qt.SmoothTransformation)
    image=image.convertToFormat(QImage.Format_RGBA8888)
    rgba=np.frombuffer(image.constBits(),np.uint8,count=image.sizeInBytes()).reshape(image.height(),image.bytesPerLine())[:,:image.width()*4].reshape(image.height(),image.width(),4)
    if channel=='luminance':values=rgba[:,:,:3]@np.array([.2126,.7152,.0722],np.float32)/255.
    else:values=rgba[:,:,dict(red=0,green=1,blue=2,alpha=3)[channel]].astype(np.float32)/255.
    if invert:values=1-values
    if np.all(values>=threshold):return -1
    values=np.ascontiguousarray(values[::-1],np.float32)
    if _allocated_bytes+values.nbytes>MAX_TEXTURE_BYTES:
        raise ValueError('GPU alpha texture cache is full; restart the preview session to reclaim it')
    result=_library.rt_alpha_mask(values.ctypes.data,image.width(),image.height(),threshold)
    if result<0:raise ValueError('Cannot allocate GPU alpha contour')
    _allocated_bytes+=values.nbytes
    return result

def mask(source,config):
    path=os.path.abspath(os.path.expandvars(source['path']));stat=os.stat(path)
    return texture(path,stat.st_mtime_ns,stat.st_size,source['channel'],bool(source.get('invert',False)),float(config['threshold']),int(config['resolution']))

def prepare(mesh,path,evaluated,config):
    fn,owner=alpha._texture_fn(path,evaluated)
    if fn.numVertices!=len(mesh['vertices']) or fn.numPolygons!=len(mesh['faces']):raise ValueError('Alpha UV topology differs from evaluated mesh')
    counts,vertices=fn.getVertices();counts=np.asarray(counts,np.int64);vertices=np.asarray(vertices,np.int64)
    uvcounts,uvids=fn.getAssignedUVs();uvcounts=np.asarray(uvcounts,np.int64);uvids=np.asarray(uvids,np.int64)
    coordinates=np.column_stack(fn.getUVs())
    faceids=np.repeat(np.arange(len(counts)),counts)
    validfaces=(counts==uvcounts)&(uvcounts>0)
    valid=validfaces[faceids]
    keys=faceids[valid]*fn.numVertices+vertices[valid]
    # Unassigned faces consume no entries in Maya's packed UV-id array.
    packedfaces=np.repeat(np.arange(len(uvcounts)),uvcounts)
    values=uvids[validfaces[packedfaces]]
    order=np.argsort(keys);keys=keys[order];values=values[order]
    tri=np.asarray(mesh['triangles'],np.int64);tf=np.asarray(mesh['triangle_faces'],np.int32)
    queries=tf[:,None]*fn.numVertices+tri;positions=np.searchsorted(keys,queries)
    good=np.all(positions<len(keys),axis=1)&validfaces[tf]
    if len(keys):good[good]&=np.all(keys[positions[good]]==queries[good],axis=1)
    else:good[:]=False
    uv=np.zeros((len(tri),3,2),np.float32)
    uv[good]=coordinates[values[positions[good]]]
    material=np.asarray(mesh['material_ids'])[tf];groups=[];used=np.zeros(len(counts),bool)
    for key,source in config['sources'].items():
        selected=good if key=='all' else good&(material==int(key))
        ids=np.flatnonzero(selected)
        if not len(ids):continue
        mapped=uv[ids]*np.asarray(source.get('repeat',[1,1]))+np.asarray(source.get('offset',[0,0]))
        if not source.get('wrap',True) and (mapped.min()<0 or mapped.max()>1):raise ValueError('Non-wrapping alpha UVs outside 0–1')
        mask_id=mask(source,config)
        if mask_id<0:continue  # Fully opaque textures keep ordinary mesh edges.
        groups.append(dict(triangles=ids,uv=np.ascontiguousarray(mapped,np.float32),mask=mask_id))
        used[tf[ids]]=True
    mesh['_gpu_alpha']=dict(groups=groups,faces=used,invalid_uv_triangles=int((~good).sum()))
    return mesh

def submit(mesh,face_styles,styles,offset,mesh_id,set_style,item=None):
    data=mesh.get('_gpu_alpha')
    if not data:return 0
    triangles=np.asarray(mesh['triangles']);tf=np.asarray(mesh['triangle_faces']);vertices=np.asarray(mesh['vertices'])
    count=0
    for group in data['groups']:
        ids=group['triangles'];owners=np.asarray(face_styles)[tf[ids]]
        for owner in np.unique(owners):
            draw_lines=owner>=0 and styles[owner].get('open_edges',False)
            selected=owners==owner;chosen=ids[selected];uv=group['uv'][selected]
            target=max(0,int(owner))
            if item is not None:target=item.get('_map_routes',{}).get(target,{}).get('open',target)
            style=styles[target]
            from . import preview_maps
            try:mapped=preview_maps.triangle_uv(mesh,chosen,style)
            except (ValueError,RuntimeError) as e:
                preview_maps.warn(e);mapped=None
                if item is not None:target=preview_maps.unmapped_style(item,target);style=styles[target]
            color=(c.c_float*3)(*style.get('line_color',[.04,.04,.07]))
            set_style(offset+target,float(style.get('line_width',1.5)),color)
            for first in range(0,len(chosen),131072):
                index=chosen[first:first+131072]
                points=np.ascontiguousarray(vertices[triangles[index]],np.float64)
                coords=np.ascontiguousarray(uv[first:first+131072],np.float32)
                add=_library.rt_add_alpha if draw_lines else _library.rt_add_alpha_depth
                if not add(points.ctypes.data,coords.ctypes.data,len(index),group['mask'],mesh_id+1):raise RuntimeError('Alpha viewport transfer failed')
                if mapped is not None:
                    values=np.ascontiguousarray(mapped[first:first+len(index)],np.float32)
                    _library.rt_map_uv_vertices(values.ctypes.data,len(index)*3)
                count+=len(index)
    return count
