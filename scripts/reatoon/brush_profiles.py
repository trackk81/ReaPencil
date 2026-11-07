"""Recognize a verified subset of saved brush profiles without flattening curves."""
import math


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
