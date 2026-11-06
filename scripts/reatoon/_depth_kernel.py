"""Serial, deterministic CPU depth kernel; no fast-math or pixel races."""
import math
import numpy as np
from numba import njit


@njit(cache=True,nogil=True)
def rasterize(vertices,triangles,depth,planes,owners,has_owners,mesh_index,
              ortho,span,focal,near,far):
    height,width=depth.shape
    first=np.empty((8,3),np.float64)
    second=np.empty((8,3),np.float64)
    projected=np.empty((3,2),np.float64)
    zs=np.empty(3,np.float64)
    count=0
    for triangle in triangles:
        for i in range(3):
            for axis in range(3):first[i,axis]=vertices[triangle[i],axis]
        size=3
        for clip in range(2):
            plane=near if clip==0 else far
            sign=1.0 if clip==0 else -1.0
            out_size=0
            if size==0:break
            a=size-1
            ina=sign*(first[a,2]-plane)>=0
            for b in range(size):
                inb=sign*(first[b,2]-plane)>=0
                if ina!=inb:
                    t=(plane-first[a,2])/(first[b,2]-first[a,2])
                    for axis in range(3):
                        second[out_size,axis]=first[a,axis]+(first[b,axis]-first[a,axis])*t
                    out_size+=1
                if inb:
                    for axis in range(3):second[out_size,axis]=first[b,axis]
                    out_size+=1
                a=b
                ina=inb
            first,second=second,first
            size=out_size
        for fan in range(1,size-1):
            count+=1
            for i in range(3):
                index=0 if i==0 else fan+i-1
                zs[i]=first[index,2]
                factor=width/span if ortho else focal/zs[i]
                projected[i,0]=width/2.0+first[index,0]*factor
                projected[i,1]=height/2.0-first[index,1]*factor
            ax,ay=projected[0,0],projected[0,1]
            bx,by=projected[1,0],projected[1,1]
            cx,cy=projected[2,0],projected[2,1]
            if not (math.isfinite(ax) and math.isfinite(ay) and math.isfinite(bx) and math.isfinite(by) and math.isfinite(cx) and math.isfinite(cy)):
                continue
            xmin=max(math.floor(min(ax,bx,cx)),0)
            ymin=max(math.floor(min(ay,by,cy)),0)
            xmax=min(math.ceil(max(ax,bx,cx)),width-1)
            ymax=min(math.ceil(max(ay,by,cy)),height-1)
            if xmin>xmax or ymin>ymax:continue
            den=(by-cy)*(ax-cx)+(cx-bx)*(ay-cy)
            if abs(den)<1e-12:continue
            va=zs[0] if ortho else 1.0/zs[0]
            vb=zs[1] if ortho else 1.0/zs[1]
            vc=zs[2] if ortho else 1.0/zs[2]
            plane_x=((va-vc)*(by-cy)+(vb-vc)*(cy-ay))/den
            plane_y=((va-vc)*(cx-bx)+(vb-vc)*(ax-cx))/den
            plane_c=vc-plane_x*cx-plane_y*cy
            for y in range(ymin,ymax+1):
                yy=y+.5
                for x in range(xmin,xmax+1):
                    xx=x+.5
                    u=((by-cy)*(xx-cx)+(cx-bx)*(yy-cy))/den
                    v=((cy-ay)*(xx-cx)+(ax-cx)*(yy-cy))/den
                    w=1-u-v
                    if u< -1e-8 or v< -1e-8 or w< -1e-8:continue
                    if ortho:z=u*zs[0]+v*zs[1]+w*zs[2]
                    else:
                        inv=u/zs[0]+v/zs[1]+w/zs[2]
                        if inv<=0:continue
                        z=1.0/inv
                    if z<depth[y,x]:
                        depth[y,x]=z
                        planes[y,x,0]=plane_x
                        planes[y,x,1]=plane_y
                        planes[y,x,2]=plane_c
                        if has_owners:owners[y,x]=mesh_index
    return count
