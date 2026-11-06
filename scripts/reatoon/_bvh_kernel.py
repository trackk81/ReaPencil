"""CPU compiled equivalent of the stable median AABB tree builder."""
import numpy as np
from numba import njit


@njit(cache=True, nogil=True)
def build(lows, highs):
    n=len(lows)
    capacity=2*(n//8+1)+1
    node_lows=np.empty((capacity,3),np.float64)
    node_highs=np.empty((capacity,3),np.float64)
    children=np.full((capacity,2),-1,np.int64)
    ranges=np.full((capacity,2),-1,np.int64)
    order=np.arange(n,dtype=np.int64)
    stack=np.empty((capacity,3),np.int64)
    stack[0]=[0,0,n]
    pending=1;used=1
    while pending:
        pending-=1
        node,start,end=stack[pending]
        low=np.full(3,np.inf);high=np.full(3,-np.inf)
        center_low=np.full(3,np.inf);center_high=np.full(3,-np.inf)
        for j in range(start,end):
            index=order[j]
            for axis in range(3):
                low[axis]=min(low[axis],lows[index,axis])
                high[axis]=max(high[axis],highs[index,axis])
                center=(lows[index,axis]+highs[index,axis])*.5
                center_low[axis]=min(center_low[axis],center)
                center_high[axis]=max(center_high[axis],center)
        node_lows[node]=low;node_highs[node]=high
        if end-start<=16:
            ranges[node]=[start,end]
            continue
        axis=np.argmax(center_high-center_low)
        centers=np.empty(end-start,np.float64)
        for j in range(start,end):
            index=order[j]
            centers[j-start]=(lows[index,axis]+highs[index,axis])*.5
        permutation=np.argsort(centers,kind='mergesort')
        part=order[start:end].copy()
        for j in range(end-start):order[start+j]=part[permutation[j]]
        middle=start+(end-start)//2
        left,right=used,used+1;used+=2
        children[node]=[left,right]
        stack[pending]=[right,middle,end]
        stack[pending+1]=[left,start,middle]
        pending+=2
    return node_lows[:used],node_highs[:used],children[:used],ranges[:used],order
