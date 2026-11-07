"""CPU box filter, retaining NumPy float32 accumulation order."""
import numpy as np
from numba import njit

@njit(cache=True,nogil=True)
def down_float32(image,scale):
    h,w,c=image.shape
    out=np.empty((h//scale,w//scale,c),np.float32)
    for y in range(h//scale):
        for x in range(w//scale):
            for k in range(c):
                value=np.float32(0)
                for dy in range(scale):
                    for dx in range(scale):
                        value=np.float32(value+image[y*scale+dy,x*scale+dx,k])
                out[y,x,k]=value/(scale*scale)
    return out
