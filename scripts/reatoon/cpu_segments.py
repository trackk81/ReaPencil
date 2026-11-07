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
        if (style.get('hidden_lines',False) and style.get('_visibility_mode')!=-1) or style.get('width_profile') or style.get('alpha_profile'):return None
        if any(float(style.get(k,0))!=0 for k in
               ('dash_length','distance_reduction','width_variation','taper')):return None
    from .native_cpu import library,segments as render
    backend="native-cpu-segments"
    if library() is None:
        if any(s.get('_visibility_mode')==-1 for s in (segments.styles() if packed else [s['settings'] for s in segments])):return None
        from .accelerator import enable
        enable()
        from ._segment_kernel import render
        backend="numba-cpu-segments"
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
    channel_hidden=any(s.get('_visibility_mode')==-1 for s in (segments.styles() if packed else [r['settings'] for r in segments]))
    modes=np.empty(0,np.int8)
    if channel_hidden:
        if packed:
            modes=np.concatenate([np.asarray([r['settings'].get('_visibility_mode',0) for r in part['records']],np.int8) if 'records' in part else
                                  np.full(part['count'],part['settings'].get('_visibility_mode',0),np.int8) for part in segments.parts]) if len(segments) else np.empty(0,np.int8)
        else:modes=np.asarray([s['settings'].get('_visibility_mode',0) for s in segments],np.int8)
    if np.any(modes==-1):
        records=[];record_hidden=[]
        for is_hidden in (False,True):
            ids=np.flatnonzero((modes==-1)==is_hidden)
            if not len(ids):continue
            flags=enabled[ids].astype(np.uint8)
            if is_hidden:flags=np.where(flags!=0,np.uint8(3),np.uint8(0))
            counters=np.zeros(2,np.int64)
            rows=render(points[ids],widths[ids],biases[ids],colors[ids],only[ids],flags,depth,depth_planes,hidden if is_hidden else visible,
                        int(ss),bool(camera['ortho']),float(camera['span']),float(camera['focal']),
                        float(camera['near']),float(camera['far']),visibility,np.asarray(camera['eye']),np.linalg.inv(camera['basis']).T,counters)
            visibility_stats+=counters
            records.extend((int(ids[i]),ax,ay,bx,by) for i,ax,ay,bx,by in rows);record_hidden.extend([is_hidden]*len(rows))
    else:
        records=render(points,widths,biases,colors,only,enabled,depth,depth_planes,visible,
                       int(ss),bool(camera['ortho']),float(camera['span']),float(camera['focal']),
                       float(camera['near']),float(camera['far']),visibility,
                       np.asarray(camera['eye']),np.linalg.inv(camera['basis']).T,visibility_stats)
        record_hidden=[False]*len(records)
    vectors=[]
    visible_count=hidden_count=0
    for (index,ax,ay,bx,by),is_hidden in zip(records,record_hidden):
        if not only[index]:
            if is_hidden:hidden_count+=1
            else:visible_count+=1
        if not collect_vectors:continue
        segment=segments[index]
        style=segment['settings']
        vectors.append(dict(visible=not is_hidden,width=round(float(widths[index]),3),color=colors[index].tolist(),
                            a=[ax,ay],b=[bx,by],mesh=segment['mesh'],
                            features=segment['features'],settings=style))
    return dict(vectors=vectors,visible_segments=visible_count,hidden_segments=hidden_count,
                classified_edges=count,backend=backend,
                visibility_refinement=dict(checked_samples=int(visibility_stats[0]),hidden_samples=int(visibility_stats[1])))
