"""CPU analytic depth-plane bounds, not sampled occlusion tests."""
import math
import numpy as np
from numba import njit


@njit(cache=True,nogil=True)
def surface_bounds(depth,planes,ortho,margin):
    h,w=depth.shape
    result=np.full((h,w),np.inf,np.float64)
    for y in range(h):
        y0=-margin if y==0 else float(y)
        y1=h+margin if y==h-1 else float(y+1)
        for x in range(w):
            if not math.isfinite(depth[y,x]):continue
            x0=-margin if x==0 else float(x)
            x1=w+margin if x==w-1 else float(x+1)
            a,b,c=planes[y,x]
            if not (math.isfinite(a) and math.isfinite(b) and math.isfinite(c)):continue
            guard=64*np.finfo(np.float64).eps*(abs(a)*max(abs(x0),abs(x1))+abs(b)*max(abs(y0),abs(y1))+abs(c)+1)
            if ortho:
                value=a*(x1 if a>=0 else x0)+b*(y1 if b>=0 else y0)+c
                result[y,x]=value+guard
            else:
                minimum=a*(x0 if a>=0 else x1)+b*(y0 if b>=0 else y1)+c-guard
                if minimum>0:result[y,x]=1/minimum+guard
    return result


@njit(cache=True,nogil=True)
def triangle_mask(vertices,triangles,bounds,ortho,span,focal,near,far,bias,margin,tolerance):
    h,w=bounds.shape
    mask=np.ones(len(triangles),np.bool_)
    counts=np.zeros(4,np.int64)
    for index,tri in enumerate(triangles):
        z0,z1,z2=vertices[tri[0],2],vertices[tri[1],2],vertices[tri[2],2]
        low_z=min(z0,z1,z2);high_z=max(z0,z1,z2)
        z_guard=10*tolerance+1e-8*max(1.,abs(low_z),abs(high_z))
        if not (math.isfinite(low_z) and math.isfinite(high_z)):
            counts[0]+=1;continue
        if high_z<near-z_guard or low_z>far+z_guard:
            mask[index]=False;counts[1]+=1;continue
        # Clipped triangles are kept intact; no near-plane approximation.
        if low_z<=near+z_guard or high_z>=far-z_guard:
            counts[0]+=1;continue
        xmin,ymin=np.inf,np.inf
        xmax,ymax=-np.inf,-np.inf
        valid=True
        for vertex in tri:
            factor=w/span if ortho else focal/vertices[vertex,2]
            x=w/2+vertices[vertex,0]*factor
            y=h/2-vertices[vertex,1]*factor
            if not (math.isfinite(x) and math.isfinite(y)):valid=False;break
            xmin=min(xmin,x);xmax=max(xmax,x)
            ymin=min(ymin,y);ymax=max(ymax,y)
        if not valid:counts[0]+=1;continue
        # Additional full-pixel guard includes rounding and boundary neighbours.
        # Depth tolerance is also projected conservatively at nearest depth.
        padding=1+z_guard*(w/span if ortho else focal/low_z)*(1+max(abs(xmin),abs(xmax),abs(ymin),abs(ymax))/max(focal,1))
        xmin-=padding;ymin-=padding;xmax+=padding;ymax+=padding
        if xmax< -margin or xmin>w+margin or ymax< -margin or ymin>h+margin:
            mask[index]=False;counts[2]+=1;continue
        x0=min(max(int(math.floor(xmin)),0),w-1)
        x1=min(max(int(math.floor(xmax)),0),w-1)
        y0=min(max(int(math.floor(ymin)),0),h-1)
        y1=min(max(int(math.floor(ymax)),0),h-1)
        nearest=low_z-z_guard-bias*max(1.,high_z+z_guard)
        hidden=True
        for y in range(y0,y1+1):
            for x in range(x0,x1+1):
                if not nearest>bounds[y,x]:hidden=False;break
            if not hidden:break
        if hidden:mask[index]=False;counts[3]+=1
        else:counts[0]+=1
    return mask,counts
