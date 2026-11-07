"""Projected collinear stroke coordinates and native CPU profile raster routing.

Only true mesh vertex identities join; branches/corners split conservatively.
Geometry, visibility sampling and painter order are not changed by the graph.
"""
import math
import numpy as np
from .brush_profiles import stroke_tables


def assign_coordinates(segments,camera,project):
    records=list(segments);groups={};xy={}
    for i,row in enumerate(records):
        style=row['settings']
        if not (style.get('width_profile') or style.get('alpha_profile')):continue
        points=(np.asarray([row['a'],row['b']])-camera['eye'])@camera['basis'].T
        # Clipping through the eye has no finite projected path length.
        if np.any(points[:,2]<=0):continue
        xy[i]=project(points,camera)
        if '_vertex_ids' in row:
            key=(row.get('line'),row['mesh_index'],id(style),tuple(row['features']))
            groups.setdefault(key,[]).append(i)
    links={}
    for indices in groups.values():
        adjacency={}
        for i in indices:
            for v in records[i]['_vertex_ids']:adjacency.setdefault(v,[]).append(i)
        for v,edges in adjacency.items():
            if len(edges)!=2 or edges[0]==edges[1]:continue
            i,j=edges
            def outward(k):
                r=records[k];points=np.asarray([r['a'],r['b']]);return points[1]-points[0] if r['_vertex_ids'][0]==v else points[0]-points[1]
            def screen_outward(k):
                r=records[k];points=xy[k];return points[1]-points[0] if r['_vertex_ids'][0]==v else points[0]-points[1]
            a,b=screen_outward(i),screen_outward(j);den=np.linalg.norm(a)*np.linalg.norm(b)
            if den>1e-24:
                turn=math.degrees(math.acos(float(np.clip(np.float32(-np.dot(a,b)/den),-1.,1.))))
                if turn<=float(records[i]['settings'].get('profile_split_angle',0.))+1e-8:
                    links[i,v]=j;links[j,v]=i

    used=set()
    for i in xy:
        if i in used:continue
        chain=[(i,0,1)];used.add(i)
        for side in (0,1):
            k=i;end=side
            while '_vertex_ids' in records[k]:
                v=records[k]['_vertex_ids'][end];nxt=links.get((k,v))
                if nxt is None or nxt in used:break
                used.add(nxt);near=records[nxt]['_vertex_ids'].index(v);far=1-near
                if side==0:chain.insert(0,(nxt,far,near))
                else:chain.append((nxt,near,far))
                k,end=nxt,far
        angle=float(np.float32(math.radians(float(records[i]['settings'].get('profile_direction',-30.)))))
        direction=np.asarray([math.cos(angle),math.sin(angle)])
        first,fa,_=chain[0];last,_,lb=chain[-1]
        closed=('_vertex_ids' in records[first] and '_vertex_ids' in records[last]
                and links.get((first,records[first]['_vertex_ids'][fa]))==last)
        reverse=False
        if closed:
            area=sum(float(np.cross(xy[k][a],xy[k][b])) for k,a,b in chain)
            clockwise=int(records[i]['settings'].get('profile_loop_direction',0))==0
            if (area>0)!=clockwise:chain=[(k,b,a) for k,a,b in reversed(chain)]
            center=np.mean([xy[k][a] for k,a,b in chain],axis=0)
            scores=[]
            for k,a,b in chain:
                v=(xy[k][0]+xy[k][1])*.5-center
                scores.append(float(np.dot(v,direction))*float(np.linalg.norm(v)))
            anchor=int(np.argmin(scores));chain=chain[anchor:]+chain[:anchor]
        else:
            start=xy[chain[0][0]][chain[0][1]];end=xy[chain[-1][0]][chain[-1][2]]
            reverse=np.dot(end-start,direction)<0
        total=sum(float(np.linalg.norm(xy[k][b]-xy[k][a])) for k,a,b in chain)
        offset=0.
        for k,a,b in chain:
            length=float(np.linalg.norm(xy[k][b]-xy[k][a]));lo=offset/max(total,1e-20);hi=(offset+length)/max(total,1e-20)
            u=[0.,0.];u[a]=1-lo if reverse else lo;u[b]=1-hi if reverse else hi
            records[k]=dict(records[k],_profile_u=u);offset+=length
    return records


def draw(layer,p,q,ts,mask,color,width,style,u,low,pixel_scale=1.):
    """Coalesce visible samples, then evaluate exact adaptive profiles per pixel."""
    from .cpu_brush import draw_runs
    indices=np.flatnonzero(mask)
    if not len(indices):return 0
    cuts=np.r_[0,np.flatnonzero(np.diff(indices)!=1)+1,len(indices)]
    runs=[]
    for lo,hi in zip(cuts[:-1],cuts[1:]):
        first,last=indices[lo],indices[hi-1]
        a=p+ts[first]*(q-p)-low;b=p+ts[last+1]*(q-p)-low
        runs.append([*a,*b,*color])
    w,a=stroke_tables(style)
    draw_runs(layer,runs,np.r_[p-low,q-low],u[0],u[1],width,w,a,smoothing=pixel_scale if '_profile_source_width' in style else 0.)
    return len(runs)


def maximum_over(target,source):
    mask=source[...,3]>target[...,3]
    target[mask]=source[mask]
