"""Sequential CPU capsule pixels. No fastmath, GPU or alpha-order changes."""
import math
import numpy as np
from numba import njit


@njit(cache=True,nogil=True)
def stroke(layer,a,b,width,color):
    if width<=0:return
    h,w=layer.shape[:2]
    radius=width/2
    x0=max(math.floor(min(a[0],b[0])-radius-1),0)
    y0=max(math.floor(min(a[1],b[1])-radius-1),0)
    x1=min(math.ceil(max(a[0],b[0])+radius+1),w-1)
    y1=min(math.ceil(max(a[1],b[1])+radius+1),h-1)
    if x1<x0 or y1<y0:return
    vx,vy=b[0]-a[0],b[1]-a[1]
    denom=max(vx*vx+vy*vy,1e-15)
    for y in range(y0,y1+1):
        for x in range(x0,x1+1):
            t=((x+.5-a[0])*vx+(y+.5-a[1])*vy)/denom
            t=min(max(t,0),1)
            dist=np.hypot(x+.5-(a[0]+t*vx),y+.5-(a[1]+t*vy))
            alpha=min(max(radius+.5-dist,0),1)
            if alpha>layer[y,x,3]:
                for c in range(3):layer[y,x,c]=color[c]*alpha
                layer[y,x,3]=alpha
