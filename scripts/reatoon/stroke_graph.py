"""Topology-aware collinear stroke connections for the CPU brush path.

Exact mesh vertex identities, rather than coordinate welding, prevent joining
disconnected coincident geometry. Corners, branches, styles and features split.
"""
import numpy as np


def connect_collinear(segments):
    records=list(segments)
    groups={}
    for i,record in enumerate(records):
        style=record['settings']
        if (not style.get('connect_collinear_dashes',False) or
            float(style.get('dash_length',0))<=0 or '_vertex_ids' not in record):
            continue
        key=(record.get('line'),record['mesh_index'],id(style),tuple(record['features']))
        groups.setdefault(key,[]).append(i)
    links={}
    for indices in groups.values():
        adjacency={}
        for i in indices:
            for v in records[i]['_vertex_ids']:adjacency.setdefault(v,[]).append(i)
        for v,edges in adjacency.items():
            if len(edges)!=2 or edges[0]==edges[1]:continue
            first,second=edges
            def outward(index):
                row=records[index]
                a,b=np.asarray(row['a']),np.asarray(row['b'])
                return b-a if row['_vertex_ids'][0]==v else a-b
            a,b=outward(first),outward(second)
            lengths=float(np.linalg.norm(a)*np.linalg.norm(b))
            if lengths>1e-24 and float(np.dot(a,b))/lengths < -1.+1e-12:
                links[first,v]=second;links[second,v]=first
    used=set();result=[]
    for i,row in enumerate(records):
        if i in used:continue
        used.add(i)
        if '_vertex_ids' not in row or not any((i,v) in links for v in row['_vertex_ids']):
            result.append(row);continue
        ends=list(row['_vertex_ids']);points=[row['a'],row['b']]
        for side in (0,1):
            edge=i
            while (edge,ends[side]) in links:
                nxt=links[edge,ends[side]]
                if nxt in used:break
                used.add(nxt);other=records[nxt]
                index=1 if other['_vertex_ids'][0]==ends[side] else 0
                ends[side]=other['_vertex_ids'][index]
                points[side]=other['b' if index else 'a']
                edge=nxt
        result.append(dict(row,a=points[0],b=points[1],_vertex_ids=tuple(ends)))
    return result
