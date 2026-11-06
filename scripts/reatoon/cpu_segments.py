"""Compiled visible constant-style segment stage with explicit feature routing.

Returns None before mutation for unsupported styles, allowing the caller to
execute its complete reference stage. It never silently drops a feature.
"""
import numpy as np


def render_segments(segments,camera,depth,depth_planes,visible,hidden,ss,
                    group_image=None,elements=None,collect_vectors=True,visibility=None):
    if group_image is not None or elements:return None
    packed=hasattr(segments,'arrays')
    styles=segments.styles() if packed else {id(s['settings']):s['settings'] for s in segments}.values()
    for style in styles:
        if style.get('hidden_lines',False):return None
        if any(float(style.get(k,0))!=0 for k in
               ('dash_length','distance_reduction','width_variation','taper')):return None
    from .accelerator import enable
    enable()
    from ._segment_kernel import render
    count=len(segments)
    if packed:
        points,widths,biases,colors,only,enabled=segments.arrays()
    else:
        points=np.asarray([[s['a'],s['b']] for s in segments],np.float64).reshape(count,2,3)
        widths=np.asarray([max(0.,float(s['settings']['line_width'])) for s in segments])
        biases=np.asarray([float(s['settings']['depth_bias']) for s in segments])
        colors=np.clip(np.asarray([s['settings']['line_color'] for s in segments],np.float64).reshape(count,3),0,1)
        only=np.asarray([s['settings'].get('output_to_elements_only',False) for s in segments],np.bool_)
        enabled=np.asarray([bool(s['features']) for s in segments],np.bool_)
    points=(points-np.asarray(camera['eye'])) @ np.asarray(camera['basis']).T
    visibility_stats=np.zeros(2,np.int64)
    records=render(points,widths,biases,colors,only,enabled,depth,depth_planes,visible,
                   int(ss),bool(camera['ortho']),float(camera['span']),float(camera['focal']),
                   float(camera['near']),float(camera['far']),visibility,
                   np.asarray(camera['eye']),np.linalg.inv(camera['basis']).T,visibility_stats)
    vectors=[]
    visible_count=0
    for index,ax,ay,bx,by in records:
        if not only[index]:visible_count+=1
        if not collect_vectors:continue
        segment=segments[index]
        style=segment['settings']
        vectors.append(dict(visible=True,width=round(float(widths[index]),3),color=colors[index].tolist(),
                            a=[ax,ay],b=[bx,by],mesh=segment['mesh'],
                            features=segment['features'],settings=style))
    return dict(vectors=vectors,visible_segments=visible_count,hidden_segments=0,
                classified_edges=count,backend='numba-cpu-segments',
                visibility_refinement=dict(checked_samples=int(visibility_stats[0]),hidden_samples=int(visibility_stats[1])))
