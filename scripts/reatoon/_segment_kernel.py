"""CPU segment clipping, depth sampling and premultiplied capsule composition."""
import math
import numpy as np
from numba import njit
from ._stroke_kernel import stroke
from ._visibility_kernel import is_occluded

# Ray-kernel revision 2. Updating the caller source invalidates Numba's disk
# cache, which does not track code changes in imported compiled callees.


@njit(cache=True,nogil=True)
def render(points,widths,biases,colors,only,enabled,depth,planes,visible,ss,
           ortho,span,focal,near,far,visibility=None,eye=None,inverse_basis=None,visibility_stats=None):
    h,w=depth.shape
    records=[]
    a=np.empty(3,np.float64);b=np.empty(3,np.float64)
    start=np.empty(2,np.float64);end=np.empty(2,np.float64)
    ray_origin=np.empty(3,np.float64);ray_direction=np.empty(3,np.float64)
    for index in range(len(points)):
        line_width=widths[index]
        if line_width<=0 or not enabled[index]:continue
        lo,hi=0.,1.
        dz=points[index,1,2]-points[index,0,2]
        if abs(dz)<1e-14:
            if points[index,0,2]<near or points[index,0,2]>far:continue
        else:
            t0=(near-points[index,0,2])/dz
            t1=(far-points[index,0,2])/dz
            lo=max(lo,min(t0,t1));hi=min(hi,max(t0,t1))
            if lo>hi:continue
        for axis in range(3):
            if abs(dz)<1e-14:
                a[axis]=points[index,0,axis]
                b[axis]=points[index,1,axis]
            else:
                delta=points[index,1,axis]-points[index,0,axis]
                a[axis]=points[index,0,axis]+delta*lo
                b[axis]=points[index,0,axis]+delta*hi
        factor_a=w/span if ortho else focal/a[2]
        factor_b=w/span if ortho else focal/b[2]
        px=w/2.+a[0]*factor_a;py=h/2.-a[1]*factor_a
        qx=w/2.+b[0]*factor_b;qy=h/2.-b[1]*factor_b
        dx,dy=qx-px,qy-py
        margin=line_width*ss/2+1
        lo,hi=0.,1.
        reject=False
        for clip in range(4):
            if clip==0:ca,cb=-dx,px+margin
            elif clip==1:ca,cb=dx,w+margin-px
            elif clip==2:ca,cb=-dy,py+margin
            else:ca,cb=dy,h+margin-py
            if abs(ca)<1e-14:
                if cb<0:reject=True;break
            elif ca<0:lo=max(lo,cb/ca)
            else:hi=min(hi,cb/ca)
            if lo>hi:reject=True;break
        if reject:continue
        xmin=max(math.floor(min(px+lo*dx,px+hi*dx)-margin),0)
        ymin=max(math.floor(min(py+lo*dy,py+hi*dy)-margin),0)
        xmax=min(math.ceil(max(px+lo*dx,px+hi*dx)+margin),w)
        ymax=min(math.ceil(max(py+lo*dy,py+hi*dy)+margin),h)
        if xmax<=xmin or ymax<=ymin:continue
        edge=np.zeros((ymax-ymin,xmax-xmin,4),np.float32)
        length=math.sqrt(dx*dx+dy*dy)
        count=max(1,int(math.ceil(length*(hi-lo)*1.5)))
        step=(hi-lo)/count
        run=False
        run_ax,run_ay,run_bx,run_by=0.,0.,0.,0.
        for k in range(count):
            t0=lo+k*step
            t1=hi if k+1==count else lo+(k+1)*step
            mid=(t0+t1)*.5
            x,y=px+mid*dx,py+mid*dy
            z=a[2]+mid*(b[2]-a[2]) if ortho else 1/((1-mid)/a[2]+mid/b[2])
            ix=min(max(int(math.floor(x)),0),w-1)
            iy=min(max(int(math.floor(y)),0),h-1)
            value=planes[iy,ix,0]*x+planes[iy,ix,1]*y+planes[iy,ix,2]
            surface=value if ortho else (1/value if value>0 else np.inf)
            if not math.isfinite(depth[iy,ix]):surface=np.inf
            front=z<=surface+biases[index]*max(1.,z)
            if visibility is not None and front and z>surface+256*np.finfo(np.float64).eps*max(1.,abs(z)):
                rx=(x-w/2)/(w/span if ortho else focal)
                ry=-(y-h/2)/(w/span if ortho else focal)
                for axis in range(3):
                    if ortho:
                        ray_origin[axis]=eye[axis]+rx*inverse_basis[0,axis]+ry*inverse_basis[1,axis]
                        ray_direction[axis]=inverse_basis[2,axis]
                    else:
                        ray_origin[axis]=eye[axis]
                        ray_direction[axis]=rx*inverse_basis[0,axis]+ry*inverse_basis[1,axis]+inverse_basis[2,axis]
                visibility_stats[0]+=1
                if is_occluded(ray_origin,ray_direction,near,z,visibility):
                    visibility_stats[1]+=1;front=False
            if not front:
                if run:
                    records.append((index,run_ax,run_ay,run_bx,run_by));run=False
                continue
            sx,sy=px+t0*dx,py+t0*dy
            ex,ey=px+t1*dx,py+t1*dy
            start[0]=sx-xmin;start[1]=sy-ymin
            end[0]=ex-xmin;end[1]=ey-ymin
            stroke(edge,start,end,line_width*ss,colors[index])
            if not run:
                run_ax,run_ay=sx/ss,sy/ss
                run=True
            run_bx,run_by=ex/ss,ey/ss
        if run:records.append((index,run_ax,run_ay,run_bx,run_by))
        if not only[index]:
            for y in range(ymax-ymin):
                for x in range(xmax-xmin):
                    inv=np.float32(1)-edge[y,x,3]
                    for c in range(4):
                        product=np.float32(visible[y+ymin,x+xmin,c]*inv)
                        visible[y+ymin,x+xmin,c]=edge[y,x,c]+product
    return records
