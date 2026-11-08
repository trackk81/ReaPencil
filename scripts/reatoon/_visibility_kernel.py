"""CPU BVH ray checks for depth-buffer ambiguous line samples; no fast math."""
import numpy as np
from numba import njit

@njit(cache=True,inline='always')
def _box(origin,direction,low,high,near,far):
    for axis in range(3):
        if direction[axis]==0:
            if origin[axis]<low[axis] or origin[axis]>high[axis]:return False
        else:
            a=(low[axis]-origin[axis])/direction[axis]
            b=(high[axis]-origin[axis])/direction[axis]
            near=max(near,min(a,b));far=min(far,max(a,b))
            if near>far:return False
    return True

@njit(cache=True,nogil=True)
def is_occluded(origin,direction,near,limit,context):
    roots,lows,highs,children,ranges,order,triangles=context
    # Mesh trees and the optional root hierarchy each halve their input range.
    # Twice the packed node-count logarithm bounds their combined pending depth.
    stack=np.empty(2*int(np.log2(max(1,len(children))))+4,np.int64)
    magnitude=max(1.,max(abs(origin[0]),abs(origin[1]),abs(origin[2])),max(abs(direction[0]),abs(direction[1]),abs(direction[2]))*abs(limit))
    guard=256*np.finfo(np.float64).eps*magnitude
    far=limit-guard
    for root in roots:
        pending=1;stack[0]=root
        while pending:
            pending-=1;node=stack[pending]
            if not _box(origin,direction,lows[node],highs[node],near,far):continue
            if children[node,0]>=0:
                stack[pending]=children[node,0];stack[pending+1]=children[node,1];pending+=2
                continue
            for slot in range(ranges[node,0],ranges[node,1]):
                tri=triangles[order[slot]]
                ex=tri[1,0]-tri[0,0];ey=tri[1,1]-tri[0,1];ez=tri[1,2]-tri[0,2]
                fx=tri[2,0]-tri[0,0];fy=tri[2,1]-tri[0,1];fz=tri[2,2]-tri[0,2]
                dx,dy,dz=direction[0],direction[1],direction[2]
                hx=dy*fz-dz*fy;hy=dz*fx-dx*fz;hz=dx*fy-dy*fx
                det=ex*hx+ey*hy+ez*hz
                if det==0:continue
                sx=origin[0]-tri[0,0];sy=origin[1]-tri[0,1];sz=origin[2]-tri[0,2]
                u=(sx*hx+sy*hy+sz*hz)/det
                if u<0 or u>1:continue
                qx=sy*ez-sz*ey;qy=sz*ex-sx*ez;qz=sx*ey-sy*ex
                v=(dx*qx+dy*qy+dz*qz)/det
                if v<0 or u+v>1:continue
                t=(fx*qx+fy*qy+fz*qz)/det
                # Preserve the reference operation order, including summation
                # from zero, while avoiding per-triangle temporary arrays.
                det_permanent=0.;num_permanent=0.
                det_permanent+=abs(ex)*(abs(dy*fz)+abs(dz*fy))
                det_permanent+=abs(ey)*(abs(dz*fx)+abs(dx*fz))
                det_permanent+=abs(ez)*(abs(dx*fy)+abs(dy*fx))
                num_permanent+=abs(fx)*(abs(sy*ez)+abs(sz*ey))
                num_permanent+=abs(fy)*(abs(sz*ex)+abs(sx*ez))
                num_permanent+=abs(fz)*(abs(sx*ey)+abs(sy*ex))
                det_error=64*np.finfo(np.float64).eps*det_permanent
                denominator=abs(det)-det_error
                if denominator<=0:continue
                t_error=(64*np.finfo(np.float64).eps*num_permanent+abs(t)*det_error)/denominator
                if near<=t and t+t_error<far:return True
    return False

@njit(cache=True,nogil=True)
def visible(origins,directions,limits,near,roots,lows,highs,children,ranges,order,triangles):
    result=np.ones(len(limits),np.bool_)
    context=(roots,lows,highs,children,ranges,order,triangles)
    for sample in range(len(limits)):
        result[sample]=not is_occluded(origins[sample],directions[sample],near,limits[sample],context)
    return result
