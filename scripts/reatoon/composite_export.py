"""Explicit full-resolution raster composites inside SVG / standard EPS.

EPS has no general alpha/blend model. Preserve the CPU white-matte appearance
without claiming these embedded images are editable vector strokes.
"""
import base64,json,struct,zlib
from pathlib import Path
from xml.sax.saxutils import escape
import numpy as np

def rgb8(layer):
    rgba=np.asarray(layer)
    display=rgba[...,:3]+(1-rgba[...,3,None])
    return np.clip(np.rint(display*255),0,255).astype(np.uint8)

def png_bytes(rgb):
    h,w,c=rgb.shape
    def chunk(kind,value):return struct.pack('>I',len(value))+kind+value+struct.pack('>I',zlib.crc32(kind+value)&0xffffffff)
    raw=b''.join(b'\0'+row.tobytes() for row in rgb)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw,6))+chunk(b'IEND',b'')

def svg(path,rgb):
    h,w,_=rgb.shape;payload=base64.b64encode(png_bytes(rgb)).decode('ascii')
    metadata=dict(product='ReaPencil',representation='embedded-raster-composite',matte='white',native_resolution=[w,h],editable_vector=False)
    Path(path).write_text('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="%d" height="%d" viewBox="0 0 %d %d">\n<metadata>%s</metadata>\n<image x="0" y="0" width="%d" height="%d" xlink:href="data:image/png;base64,%s"/>\n</svg>\n'%(w,h,w,h,escape(json.dumps(metadata)),w,h,payload),encoding='utf8')

def eps(path,rgb):
    h,w,_=rgb.shape
    payload=base64.a85encode(zlib.compress(np.ascontiguousarray(rgb).tobytes(),6),wrapcol=100)+b'~>\n'
    header=('%%!PS-Adobe-3.0 EPSF-3.0\n%%%%BoundingBox: 0 0 %d %d\n%%%%LanguageLevel: 3\n%%%%ReaPencilRepresentation: FlattenedRasterComposite\n%%%%ReaPencilNativeResolution: %d %d\n%%%%ReaPencilMatte: white\ngsave\n%d %d scale\n%d %d 8 [%d 0 0 -%d 0 %d]\ncurrentfile /ASCII85Decode filter /FlateDecode filter false 3 colorimage\n'%(w,h,w,h,w,h,w,h,w,h,h)).encode('ascii')
    Path(path).write_bytes(header+payload+b'grestore\nshowpage\n%%EOF\n')
