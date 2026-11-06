"""Certified orientation signs for rejecting geometrically separated triangles.

The filter is the orient3d determinant/permanent bound. Ambiguous signs use
exact rational arithmetic on the input binary doubles, not a larger epsilon.
"""
from fractions import Fraction

_ERR=(7+56*2**-53)*2**-53


def orient3d_sign(a,b,c,d):
    ad=[float(a[i])-float(d[i]) for i in range(3)]
    bd=[float(b[i])-float(d[i]) for i in range(3)]
    cd=[float(c[i])-float(d[i]) for i in range(3)]
    safe=all(v==0 or 1e-70<=abs(v)<=1e70 for v in ad+bd+cd)
    if safe:
        bc1,bc2=bd[0]*cd[1],cd[0]*bd[1]
        ca1,ca2=cd[0]*ad[1],ad[0]*cd[1]
        ab1,ab2=ad[0]*bd[1],bd[0]*ad[1]
        determinant=ad[2]*(bc1-bc2)+bd[2]*(ca1-ca2)+cd[2]*(ab1-ab2)
        permanent=(abs(bc1)+abs(bc2))*abs(ad[2])+(abs(ca1)+abs(ca2))*abs(bd[2])+(abs(ab1)+abs(ab2))*abs(cd[2])
        bound=_ERR*permanent
        if determinant>bound:return 1
        if determinant< -bound:return -1
        if permanent==0:return 0
    ad=[Fraction(float(a[i]))-Fraction(float(d[i])) for i in range(3)]
    bd=[Fraction(float(b[i]))-Fraction(float(d[i])) for i in range(3)]
    cd=[Fraction(float(c[i]))-Fraction(float(d[i])) for i in range(3)]
    determinant=(ad[0]*(bd[1]*cd[2]-bd[2]*cd[1])-
                 ad[1]*(bd[0]*cd[2]-bd[2]*cd[0])+
                 ad[2]*(bd[0]*cd[1]-bd[1]*cd[0]))
    return 1 if determinant>0 else -1 if determinant<0 else 0


def strictly_separated(first,second):
    for vertices,plane in ((first,second),(second,first)):
        sign=orient3d_sign(vertices[0],plane[1],plane[2],plane[0])
        if sign and all(orient3d_sign(vertices[i],plane[1],plane[2],plane[0])==sign for i in (1,2)):
            return True
    return False


def orient3d_value(a,b,c,d):
    """Unnormalized plane determinant, with exact fallback before rounding."""
    ad=[float(a[i])-float(d[i]) for i in range(3)]
    bd=[float(b[i])-float(d[i]) for i in range(3)]
    cd=[float(c[i])-float(d[i]) for i in range(3)]
    if all(v==0 or 1e-70<=abs(v)<=1e70 for v in ad+bd+cd):
        bc1,bc2=bd[0]*cd[1],cd[0]*bd[1]
        ca1,ca2=cd[0]*ad[1],ad[0]*cd[1]
        ab1,ab2=ad[0]*bd[1],bd[0]*ad[1]
        determinant=ad[2]*(bc1-bc2)+bd[2]*(ca1-ca2)+cd[2]*(ab1-ab2)
        permanent=(abs(bc1)+abs(bc2))*abs(ad[2])+(abs(ca1)+abs(ca2))*abs(bd[2])+(abs(ab1)+abs(ab2))*abs(cd[2])
        if abs(determinant)>_ERR*permanent or permanent==0:return determinant
    ad=[Fraction(float(a[i]))-Fraction(float(d[i])) for i in range(3)]
    bd=[Fraction(float(b[i]))-Fraction(float(d[i])) for i in range(3)]
    cd=[Fraction(float(c[i]))-Fraction(float(d[i])) for i in range(3)]
    return float(ad[0]*(bd[1]*cd[2]-bd[2]*cd[1])-ad[1]*(bd[0]*cd[2]-bd[2]*cd[0])+ad[2]*(bd[0]*cd[1]-bd[1]*cd[0]))
