"""Bounded-memory CPU brush layers: independent profiles, opacity and blending."""
import json
import numpy as np
from .brush_blend import composite
from .packed_segments import PackedSegments

def leaves(style):
    if '_brush_channels' not in style:return [style]
    return [s for channel in style['_brush_channels'] for s in [channel['settings'],*channel['brushes'].values()]]

def required(styles):
    independent=any('_brush_channels' in s for s in styles) or len(styles)>1
    return any(s.get('alpha_depth_reduction') or s.get('width_depth_reduction') or s.get('blend_mode',0)!=0 or
               (independent and (s.get('line_opacity',1.)!=1. or s.get('alpha_profile') or s.get('width_profile')))
               for parent in styles for s in leaves(parent))

def _subset(parts):
    value=PackedSegments();value.parts=parts;value.count=sum(p['count'] for p in parts)
    value.intersection_count=sum(p['count'] for p in parts if p.get('intersection'))
    return value

def reference_group(segments,camera,depth,planes,layer,ss,visibility=None,group_image=None,mesh_groups=None,depth_range=None,retain_coordinates=False,diagnostics=None):
    """Clipped/dashed profile fallback; never changes the coverage resolution."""
    from . import renderer as r
    from .profile_strokes import assign_coordinates,draw
    rows=assign_coordinates(segments,camera,r._project)
    if retain_coordinates:
        start=0
        for part in segments.parts:
            part['profile_u']=np.asarray([row.get('_profile_u',[0.,1.]) for row in rows[start:start+part['count']]],float);start+=part['count']
    total=0
    for row in rows:
        s=row['settings'];points=(np.asarray([row['a'],row['b']])-camera['eye'])@camera['basis'].T
        ends=r._clip_segment(points[0],points[1],camera['near'],camera['far'])
        if ends is None:continue
        a,b=ends;p,q=r._project(np.asarray(ends),camera)
        clipped=r._screen_clip(p,q,camera['width'],camera['height'],s['line_width']*ss/2+1)
        if clipped is None:continue
        lo,hi=clipped;length=np.linalg.norm(q-p);count=max(1,int(np.ceil(length*(hi-lo)*1.5)))
        ts=np.linspace(lo,hi,count+1);mid=(ts[:-1]+ts[1:])*.5;xy=p+mid[:,None]*(q-p)
        z=a[2]+mid*(b[2]-a[2]) if camera['ortho'] else 1/((1-mid)/a[2]+mid/b[2])
        surface=r._surface_depth_at(xy,depth,planes,camera);front=z<=surface+s['depth_bias']*np.maximum(1,z)
        if visibility is not None:
            from .cpu_visibility import visible_samples
            ids=np.flatnonzero(front & (z>surface+256*np.finfo(float).eps*np.maximum(1,np.abs(z))))
            if len(ids):front[ids]=visible_samples({'arguments':visibility},xy[ids],z[ids],camera)
        mask=~front if s.get('_visibility_mode')==-1 else front
        if group_image is not None and mesh_groups is not None and s.get('merge_groups',True) and mesh_groups[row['mesh_index']]>=0 and set(row['features']) and set(row['features'])<={'outline','open'}:
            delta=q-p;normal=np.array([-delta[1],delta[0]])/max(np.linalg.norm(delta),1e-12)*ss;both=[]
            for side in (-1,1):
                sample=np.floor(xy+normal*side).astype(int);valid=(sample[:,0]>=0)&(sample[:,1]>=0)&(sample[:,0]<camera['width'])&(sample[:,1]<camera['height'])
                match=np.zeros(len(mask),bool);match[valid]=group_image[sample[valid,1],sample[valid,0]]==mesh_groups[row['mesh_index']];both.append(match)
            merged=both[0]&both[1];mask&=~merged
            if diagnostics is not None:diagnostics['merge_suppressed_samples']=diagnostics.get('merge_suppressed_samples',0)+int(merged.sum())
        dash=s.get('dash_length',0)*ss
        if dash>0:
            gap=s.get('dash_gap',-1)*ss
            mask &= (np.floor(mid*length/dash).astype(np.int64)%2)==0 if gap<0 else (mid*length)%(dash+gap)<dash if gap>0 else True
        u=row.get('_profile_u',[0.,1.])
        if np.all(points[:,2]>0):
            original=r._project(points,camera);delta=original[1]-original[0];den=np.dot(delta,delta)
            if den>1e-20:
                t=np.clip((np.asarray([p,q])-original[0])@delta/den,0,1);u=u[0]+t*(u[1]-u[0])
        ends=np.asarray([p+lo*(q-p),p+hi*(q-p)]);margin=s['line_width']*ss/2+1
        low=np.maximum(np.floor(ends.min(0)-margin),0).astype(int)
        high=np.minimum(np.ceil(ends.max(0)+margin),[camera['width'],camera['height']]).astype(int)
        if np.any(high<=low):continue
        view=layer[low[1]:high[1],low[0]:high[0]];edge=np.zeros_like(view)
        from .cpu_brush import reference_vector
        total+=draw(edge,p,q,ts,mask,s['line_color'],s['line_width']*ss,s,u,low,ss,depth_values=[a[2],b[2],*depth_range,int(camera['ortho'])] if depth_range is not None else None,alpha_depth=[a[2],b[2],int(camera['ortho']),*s['alpha_depth_reduction']] if s.get('alpha_depth_reduction') else None,width_depth=[a[2],b[2],int(camera['ortho']),*s['width_depth_reduction']] if s.get('width_depth_reduction') else None,alpha_reference=reference_vector(a,b,camera,s.get('alpha_reduction_origin')),width_reference=reference_vector(a,b,camera,s.get('width_reduction_origin')))
        if s.get('width_profile') or s.get('alpha_profile') or s.get('alpha_depth_reduction') or s.get('width_depth_reduction'):
            from .profile_strokes import maximum_over
            maximum_over(view,edge)
        else:r._over(view,edge)
    return total

def render(segments,camera,depth,planes,visible,hidden,ss,visibility=None,compiled=True,group_image=None,mesh_groups=None,elements=()):
    # Equal element filters share a canvas; compose it once regardless of file format.
    unique_elements={}
    for element,layer in elements:unique_elements.setdefault(id(layer),(element,layer))
    elements=tuple(unique_elements.values())
    if not hasattr(segments,'parts'):
        packed=PackedSegments()
        from .renderer import EDGE_FEATURES
        for row in segments:
            flags=sum(1<<i for i,k in enumerate(EDGE_FEATURES) if k in row['features'])
            if 'intersection' in row['features']:flags|=128
            part=dict(points=np.asarray([[row['a'],row['b']]],float),flags=np.asarray([flags],np.uint8),settings=row['settings'],mesh=row['mesh'],mesh_index=row['mesh_index'],line=row.get('line'),count=1)
            if '_vertex_ids' in row:part['vertex_ids']=np.asarray([row['_vertex_ids']],np.int64)
            packed.parts.append(part);packed.count+=1
        segments=packed
    segments._flush();groups={};line_order={};identities={}
    for part in segments.parts:
        if 'records' in part:raise ValueError('Independent brush effects require packed CPU geometry')
        style=part['settings'];line=part.get('line');order=line_order.setdefault(line,len(line_order))
        hide=style.get('_visibility_mode')==-1
        sid=id(style)
        if sid not in identities:
            keys=('line_color','line_width','line_opacity','blend_mode','width_profile','alpha_profile','alpha_depth_reduction','width_depth_reduction','alpha_reduction_origin','width_reduction_origin','profile_direction','profile_split_angle','profile_loop_direction','pencil_profile_width','dash_length','dash_gap','depth_bias','output_to_elements_only')
            identities[sid]=(style.get('brush_key') or sid,json.dumps({k:style.get(k) for k in keys},sort_keys=True))
        key=(order,hide,identities[sid])
        if key not in groups:groups[key]=[]
        groups[key].append(part)
    canvas=np.zeros_like(visible);scratch=np.zeros_like(visible)
    stats=dict(classified_edges=0,visible_segments=0,hidden_segments=0,brush_layers=0,merge_suppressed_samples=0,element_brush_renders=0,segment_backend='native-cpu-brush-layers')
    def draw(parts,depth_range=None):
        # Draw every source brush into scratch; output-only flags govern its destination.
        cache={};prepared=[]
        for part in parts:
            style=part['settings'];sid=id(style)
            if sid not in cache:cache[sid]=dict(style,output_to_elements_only=False)
            prepared.append(dict(part,settings=cache[sid]))
        packed=_subset(prepared);scratch.fill(0);hide=prepared[0]['settings'].get('_visibility_mode')==-1
        if any(float(s.get(k,0))!=0 for s in packed.styles() for k in ('distance_reduction','width_variation','taper')):
            raise ValueError('Independent brush effects with reduction/variation/taper are not implemented')
        curves=any(s.get('width_profile') or s.get('alpha_profile') or s.get('alpha_depth_reduction') or s.get('width_depth_reduction') for s in packed.styles());batch=None
        if compiled and (curves or group_image is not None or depth_range is not None):
            from .cpu_brush import render_packed
            batch=render_packed(packed,camera,depth,planes,scratch,ss,visibility,union_coverage=curves,group_image=group_image,mesh_groups=mesh_groups,depth_range=depth_range,retain_coordinates=bool(elements))
            if curves:stats['profile_backend']='native-cpu-adaptive-bezier'
        elif compiled:
            from .cpu_segments import render_segments
            batch=render_segments(packed,camera,depth,planes,scratch,scratch if hide else None,ss,collect_vectors=False,visibility=visibility)
        if batch is None:
            diagnostic={};n=reference_group(packed,camera,depth,planes,scratch,ss,visibility,group_image,mesh_groups,depth_range,bool(elements),diagnostic)
            batch=dict(classified_edges=len(packed),visible_segments=0 if hide else n,hidden_segments=n if hide else 0,**diagnostic)
        for original,rendered in zip(parts,prepared):
            if 'profile_u' in rendered:original['profile_u']=rendered['profile_u']
        return batch
    def filter_parts(parts,element,hide):
        from .renderer import EDGE_FEATURES
        if not element['hidden_lines' if hide else 'visible_lines']:return []
        mask_bits=sum(1<<i for i,key in enumerate(EDGE_FEATURES) if key in element['edge_types'])
        if 'intersection' in element['edge_types']:mask_bits|=128
        selected=[]
        for part in parts:
            if int(part['settings'].get('lineset_id',1)) not in element['lineset_ids']:continue
            keep=(part['flags']&mask_bits)!=0
            if not np.any(keep):continue
            if np.all(keep):selected.append(part);continue
            item=dict(part,count=int(keep.sum()))
            for name in ('points','flags','vertex_ids','profile_u'):
                if name in item:item[name]=item[name][keep]
            selected.append(item)
        return selected
    ordered=sorted(groups,key=lambda k:(k[0],not k[1]))
    for key in ordered:
        parts=groups[key];style=parts[0]['settings'];hide=key[1]
        opacity=float(style.get('line_opacity',1.));mode=int(style.get('blend_mode',0))
        if opacity==0:continue
        batch=draw(parts)
        for name in ('classified_edges','merge_suppressed_samples'):stats[name]+=batch.get(name,0)
        if not style.get('output_to_elements_only',False):
            for name in ('visible_segments','hidden_segments'):stats[name]+=batch[name]
            composite(canvas,scratch,mode,opacity)
            target=hidden if hide else visible
            if target is not None:composite(target,scratch,mode,opacity)
        # Reuse the full brush image for elements accepting the entire group.
        reusable=[(element,layer) for element,layer in elements if element['output_element']=='color' and (selected:=filter_parts(parts,element,hide)) and len(selected)==len(parts) and all(a is b for a,b in zip(selected,parts))]
        for element,layer in reusable:composite(layer[0],scratch,mode,opacity)
        reused={id(element) for element,_ in reusable}
        for element,layer in elements:
            if id(element) in reused:continue
            selected=filter_parts(parts,element,hide)
            if not selected:continue
            depth_range=(element['z_min'],element['z_max']) if element['output_element']=='depth' else None
            draw(selected,depth_range);stats['element_brush_renders']+=1
            composite(layer[0],scratch,0 if depth_range is not None else mode,opacity)
        stats['brush_layers']+=1
    return canvas,stats
