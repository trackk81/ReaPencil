"""Filtered orient3d with exact floating expansions; no fast-math.

An unresolved extreme exponent range returns NaN for determinant values and
0 for uncertified signs. The segment kernel rejects unsupported value ranges
explicitly. Ordinary Maya-coordinate ambiguity uses floating expansions.
"""
import numpy as np
from numba import njit

_ERR=(7+56*2**-53)*2**-53
_SPLITTER=134217729.0


@njit(cache=True,inline='always')
def _two_diff(a,b):
    x=a-b
    bvirt=a-x
    avirt=x+bvirt
    return x,(a-avirt)+(bvirt-b)


@njit(cache=True,inline='always')
def _two_sum(a,b):
    x=a+b
    bvirt=x-a
    avirt=x-bvirt
    return x,(a-avirt)+(b-bvirt)


@njit(cache=True,inline='always')
def _two_product(a,b):
    x=a*b
    c=_SPLITTER*a;abig=c-a;ahi=c-abig;alo=a-ahi
    c=_SPLITTER*b;bbig=c-b;bhi=c-bbig;blo=b-bhi
    err1=x-ahi*bhi
    err2=err1-alo*bhi
    err3=err2-ahi*blo
    return x,alo*blo-err3


@njit(cache=True,inline='always')
def _grow(expansion,length,value,result):
    q=value;count=0
    for i in range(length):
        q,error=_two_sum(q,expansion[i])
        if error!=0:result[count]=error;count+=1
    if q!=0 or count==0:result[count]=q;count+=1
    return count


@njit(cache=True,nogil=True)
def _exact_value(a,b,c,d):
    values=np.empty((3,3,2),np.float64)
    for row in range(3):
        for axis in range(3):
            coordinate=a[axis] if row==0 else b[axis] if row==1 else c[axis]
            head,tail=_two_diff(coordinate,d[axis])
            if ((head!=0 and (abs(head)<1e-70 or abs(head)>1e70)) or
                (tail!=0 and (abs(tail)<1e-70 or abs(tail)>1e70))):return np.nan
            values[row,axis,0]=head;values[row,axis,1]=tail
    expansion=np.empty(256,np.float64);scratch=np.empty(256,np.float64)
    length=0
    # Six signed products in a·(b×c), each difference has head+tail.
    for term in range(6):
        if term==0:ax,by,cz,sign=0,1,2,1.
        elif term==1:ax,by,cz,sign=0,2,1,-1.
        elif term==2:ax,by,cz,sign=1,0,2,-1.
        elif term==3:ax,by,cz,sign=1,2,0,1.
        elif term==4:ax,by,cz,sign=2,0,1,1.
        else:ax,by,cz,sign=2,1,0,-1.
        for i in range(2):
            x=values[0,ax,i]
            if x==0:continue
            for j in range(2):
                y=values[1,by,j]
                if y==0:continue
                xy,xyt=_two_product(x,y)
                for k in range(2):
                    z=values[2,cz,k]
                    if z==0:continue
                    high,low=_two_product(xy,z)
                    th,tl=_two_product(xyt,z)
                    for part in range(4):
                        value=(low if part==0 else high if part==1 else tl if part==2 else th)*sign
                        if value==0:continue
                        length=_grow(expansion,length,value,scratch)
                        expansion,scratch=scratch,expansion
    value=0.
    for i in range(length):value+=expansion[i]
    return value


@njit(cache=True,nogil=True)
def orient3d_value(a,b,c,d):
    adx,ady,adz=a[0]-d[0],a[1]-d[1],a[2]-d[2]
    bdx,bdy,bdz=b[0]-d[0],b[1]-d[1],b[2]-d[2]
    cdx,cdy,cdz=c[0]-d[0],c[1]-d[1],c[2]-d[2]
    for value in (adx,ady,adz,bdx,bdy,bdz,cdx,cdy,cdz):
        if value!=0 and (abs(value)<1e-70 or abs(value)>1e70):return np.nan
    bc1,bc2=bdx*cdy,cdx*bdy
    ca1,ca2=cdx*ady,adx*cdy
    ab1,ab2=adx*bdy,bdx*ady
    determinant=adz*(bc1-bc2)+bdz*(ca1-ca2)+cdz*(ab1-ab2)
    permanent=(abs(bc1)+abs(bc2))*abs(adz)+(abs(ca1)+abs(ca2))*abs(bdz)+(abs(ab1)+abs(ab2))*abs(cdz)
    bound=_ERR*permanent
    if determinant>bound or determinant< -bound:return determinant
    if permanent==0:return 0.
    return _exact_value(a,b,c,d)


@njit(cache=True,nogil=True,inline='always')
def orient3d_sign(a,b,c,d):
    value=orient3d_value(a,b,c,d)
    return 1 if value>0 else -1 if value<0 else 0


@njit(cache=True,nogil=True)
def strictly_separated(a,b):
    first=orient3d_sign(a[0],b[1],b[2],b[0])
    if first and orient3d_sign(a[1],b[1],b[2],b[0])==first and orient3d_sign(a[2],b[1],b[2],b[0])==first:return True
    first=orient3d_sign(b[0],a[1],a[2],a[0])
    return bool(first and orient3d_sign(b[1],a[1],a[2],a[0])==first and orient3d_sign(b[2],a[1],a[2],a[0])==first)
