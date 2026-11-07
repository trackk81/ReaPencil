"""Recognize a verified subset of saved brush profiles without flattening curves."""
import math
from functools import lru_cache
import numpy as np


def validate_profile(points):
    if not isinstance(points,(list,tuple)) or len(points)>256:raise ValueError('Curve requires at most 256 control points')
    rows=[]
    for point in points:
        if len(point)!=7:raise ValueError('Curve point requires type, two handles and position/value')
        row=tuple(float(v) for v in point)
        if not all(math.isfinite(v) for v in row) or row[0] not in (0,1,2,3):raise ValueError('Invalid curve point')
        if not 0<=row[3]<=1 or not 0<=row[4]<=1 or any(abs(row[i])>10 for i in (1,2,5,6)):raise ValueError('Curve coordinates outside range')
        rows.append(row)
    rows.sort(key=lambda row:row[3])
    if any(a[3]>=b[3] for a,b in zip(rows,rows[1:])):raise ValueError('Curve positions must be distinct')
    return [list(row) for row in rows]


@lru_cache(maxsize=128)
def _table(points,tolerance):
    rows=validate_profile(points)
    if not rows:return np.asarray([[0.,1.],[1.,1.]])
    knots=[(0.,rows[0][4])]
    if rows[0][3]>0:knots.append((rows[0][3],rows[0][4]))
    def handle(row,other,out):
        cp=np.asarray(row[3:5]);h=np.asarray(row[5:7] if out else row[1:3])
        if row[0]==0:return cp
        dx=h[0]-cp[0]
        if (out and dx<=0) or (not out and dx>=0):return np.asarray([cp[0],h[1]])
        bound=other[3];x=min(max(h[0],min(cp[0],bound)),max(cp[0],bound))
        return np.asarray([x,cp[1]+(h[1]-cp[1])*(x-cp[0])/dx])
    for left,right in zip(rows,rows[1:]):
        a=np.asarray(left[3:5]);d=np.asarray(right[3:5])
        if left[0]==right[0]==0:
            knots.append(tuple(d));continue
        b,c=handle(left,right,True),handle(right,left,False)
        stack=[(a,b,c,d,0)]
        while stack:
            p,q,r,s,depth=stack.pop();dx=s[0]-p[0]
            if dx<=1e-15:
                # Singular x tangents can collapse adjacent double x values.
                # Keep their bounded sub-quantization y interval, not a jump.
                if max(p[1],q[1],r[1],s[1])-min(p[1],q[1],r[1],s[1])>1e-4:
                    raise ValueError('Curve exceeds double precision near a vertical tangent')
                knots.append(tuple(s));continue
            slope=(s[1]-p[1])/dx
            error=max(abs(q[1]-p[1]-slope*(q[0]-p[0])),abs(r[1]-p[1]-slope*(r[0]-p[0])))
            if error<=tolerance:knots.append(tuple(s));continue
            if depth>=32 or len(knots)+len(stack)>65532:raise ValueError('Curve precision budget exceeded')
            pq=(p+q)*.5;qr=(q+r)*.5;rs=(r+s)*.5
            x=(pq+qr)*.5;y=(qr+rs)*.5;mid=(x+y)*.5
            stack.append((mid,y,rs,s,depth+1));stack.append((p,pq,x,mid,depth+1))
    if knots[-1][0]<1:knots.append((1.,knots[-1][1]))
    result=np.ascontiguousarray(knots,np.float64)
    x,indices,counts=np.unique(result[:,0],return_index=True,return_counts=True)
    if len(x)!=len(result):result=np.column_stack([x,np.add.reduceat(result[:,1],indices)/counts])
    result.setflags(write=False)
    return result


def profile_table(points,tolerance=1e-6):
    if not math.isfinite(tolerance) or tolerance<=0:raise ValueError('Curve tolerance must be positive and finite')
    return _table(tuple(tuple(row) for row in points),float(tolerance))


def evaluate_profile(points,coordinates):
    table=profile_table(points)
    return np.clip(np.interp(coordinates,table[:,0],table[:,1]),0.,1.)


def flat_linear_value(points):
    """Return a constant for a full-domain linear profile, otherwise None.

    Points are (handle_type, x, y). Bezier/Spline handles and missing data are
    intentionally not approximated by sampling or by just reading their ends.
    """
    try:
        rows=sorted((float(kind),float(x),float(y)) for kind,x,y in points)
    except (TypeError,ValueError):
        return None
    if len(rows)<2:return None
    if any(kind!=0 or not math.isfinite(x) or not math.isfinite(y) or
           not 0<=x<=1 or not 0<=y<=1 for kind,x,y in rows):return None
    rows.sort(key=lambda row:row[1])
    if rows[0][1]!=0 or rows[-1][1]!=1:return None
    if any(a[1]>=b[1] for a,b in zip(rows,rows[1:])):return None
    value=rows[0][2]
    if any(abs(y-value)>1e-7 for _,_,y in rows):return None
    return value



def stroke_tables(style):
    return profile_table(style.get('width_profile',[])),profile_table(style.get('alpha_profile',[]))


def maya_float_profile(points):
    """Pencil coordinate plugs are Maya float attributes, including MA reloads."""
    rows=validate_profile(points)
    return validate_profile([[row[0],*np.asarray(row[1:],np.float32).astype(np.float64).tolist()] for row in rows])
