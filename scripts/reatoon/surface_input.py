"""Numeric input stabilization and disk clipping for authored surface strokes."""
import numpy as np

def stabilize(previous,point,strength=0.,radius=0.):
    point=np.asarray(point,float)
    if previous is None:return point
    previous=np.asarray(previous,float);delta=point-previous;distance=float(np.linalg.norm(delta))
    lag=max(float(radius),30.*(float(np.clip(strength,0,100))/100.)**2)
    if lag<=0 or distance<=1e-12:return point
    return previous+delta*(-np.expm1(-distance/lag))

def outside_disk(points,center,radius,inside_visible=None):
    """Return polyline fragments as (source segment, screen-linear t) pairs."""
    p=np.asarray(points,float);center=np.asarray(center,float);radius=float(radius)
    if len(p)<2:return []
    result=[];current=[]
    def add(ref):
        if not current or abs((current[-1][0]+current[-1][1])-(ref[0]+ref[1]))>1e-10:current.append(ref)
    def finish():
        nonlocal current
        if len(current)>=2:result.append(current)
        current=[]
    for i,(a,b) in enumerate(zip(p[:-1],p[1:])):
        d=b-a;v=a-center;aa=float(d@d);bb=2*float(v@d);cc=float(v@v-radius*radius);cuts=[0.,1.]
        discriminant=bb*bb-4*aa*cc
        if aa>1e-20 and discriminant>0:
            root=np.sqrt(discriminant)
            cuts.extend(t for t in ((-bb-root)/(2*aa),(-bb+root)/(2*aa)) if 0<t<1)
        cuts=sorted(set(cuts))
        for lo,hi in zip(cuts[:-1],cuts[1:]):
            midpoint=a+d*((lo+hi)*.5)
            if float((midpoint-center)@(midpoint-center))>=radius*radius or (inside_visible is not None and not inside_visible(i,(lo+hi)*.5)):
                add((i,lo));add((i,hi))
            else:finish()
    finish();return result
