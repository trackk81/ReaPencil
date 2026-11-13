"""Row-wise image postprocessing without changing CPU sample arithmetic."""
import struct,zlib,tempfile,shutil
from pathlib import Path
import numpy as np

def png_rows(path,width,height,channels,rows):
    def chunk(kind,value):
        return struct.pack('>I',len(value))+kind+value+struct.pack('>I',zlib.crc32(kind+value)&0xffffffff)
    # A single IDAT preserves the existing PNG representation. Compress row
    # groups incrementally, without retaining filtered/raw/full RGB copies.
    compressor=zlib.compressobj(6);count=0
    with tempfile.TemporaryFile() as compressed:
        for data in rows:
            values=np.clip(np.rint(np.asarray(data)*255),0,255).astype(np.uint8)
            if values.ndim!=3 or values.shape[1:]!=(width,channels):raise ValueError('PNG row shape mismatch')
            count+=len(values)
            raw=b''.join(b'\x00'+row.tobytes() for row in values)
            compressed.write(compressor.compress(raw))
        if count!=height:raise ValueError('PNG row count mismatch')
        compressed.write(compressor.flush());size=compressed.tell()
        if size>0xffffffff:raise ValueError('PNG compressed payload exceeds a single IDAT')
        compressed.seek(0);path=Path(path)
        with path.open('wb') as output:
            output.write(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6 if channels==4 else 2,0,0,0)))
            output.write(struct.pack('>I',size)+b'IDAT');crc=zlib.crc32(b'IDAT')
            while True:
                data=compressed.read(1024*1024)
                if not data:break
                output.write(data);crc=zlib.crc32(data,crc)
            output.write(struct.pack('>I',crc&0xffffffff));output.write(chunk(b'IEND',b''))

def scaled_png(path,image,scale,down,transform=None,post_filter=None):
    h,w,c=image.shape;out_h=h//scale;out_w=w//scale
    def rows():
        for y in range(0,out_h,16):
            end=min(y+16,out_h)
            first=max(0,y-1) if post_filter else y
            last=min(end+1,out_h) if post_filter else end
            values=down(image[first*scale:last*scale],scale,_full_size=image.size)
            if post_filter:
                values=post_filter(values)[y-first:end-first]
            yield transform(values) if transform is not None else values
    png_rows(path,out_w,out_h,c,rows())

def depth_png(path,depth,scale,camera,down):
    h,w=depth.shape;out_h=h//scale
    def rows():
        for y in range(0,out_h,16):
            values=depth[y*scale:min(y+16,out_h)*scale]
            image=np.where(np.isfinite(values),np.clip(1-(values-camera['near'])/(camera['far']-camera['near']),0,1),0)
            yield down(np.repeat(image[...,None],3,axis=2),scale)
    png_rows(path,w//scale,out_h,3,rows())
