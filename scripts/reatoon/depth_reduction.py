"""Validated camera-depth Linear alpha contract from controlled source replay."""
import math

def validate(value):
    if not isinstance(value,(list,tuple)) or len(value) not in (0,4):raise ValueError('Alpha depth reduction requires start, end, first and last value')
    if not value:return []
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in value):raise ValueError('Alpha depth reduction requires finite numbers')
    start,end,first,last=map(float,value)
    if not 1<=start<end<=1000000 or not 0<=first<=1 or not 0<=last<=1:raise ValueError('Invalid alpha depth reduction range')
    return [start,end,first,last]

def factor(depth,value):
    parameters=validate(value)
    if not parameters:return 1.
    start,end,first,last=parameters
    return first+max(0.,min(1.,(depth-start)/(end-start)))*(last-first)


def linear_endpoints(rows):
    """Collapse only full-span, ordered Linear points on one straight line.

    A 1e-7 normalized-value tolerance covers stored float32 control-point
    quantization, not arbitrary piecewise curves. No source rows are mutated.
    """
    if not isinstance(rows,(list,tuple)) or not 2<=len(rows)<=256:return None
    try:
        if any(len(r)!=7 or r[0]!=0 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in r) for r in rows):return None
        if rows[0][3]!=0 or rows[-1][3]!=1:return None
        if any(not 0<=r[3]<=1 or not 0<=r[4]<=1 for r in rows):return None
        if any(a[3]>=b[3] for a,b in zip(rows,rows[1:])):return None
        first,last=rows[0][4],rows[-1][4]
        if any(abs(r[4]-(first+r[3]*(last-first)))>1e-7 for r in rows):return None
        return [float(first),float(last)]
    except (TypeError,ValueError,OverflowError):return None


def validate_origin(value):
    if not isinstance(value,(list,tuple)) or len(value) not in (0,3):raise ValueError('Reference origin requires three world coordinates')
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in value):raise ValueError('Reference origin requires finite numbers')
    return list(map(float,value))
