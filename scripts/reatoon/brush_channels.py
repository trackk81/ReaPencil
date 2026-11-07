"""CPU-only independent visible/hidden channels and feature brush routing."""
import numpy as np

FEATURES=('wireframe','open','outline','crease','material','hard','selected')
KEYS=('wireframe','open_edges','outline','crease','material_boundaries','hard_edges','selected_edges')
PRIORITY=('outline','open','intersection','hard','material','selected','crease','wireframe')
BRUSH_KEYS={'line_color','line_width','brush_size_scale','dash_length','dash_gap','line_opacity','blend_mode','brush_key','width_profile','alpha_profile','profile_direction','profile_split_angle','profile_loop_direction','pencil_profile_width','alpha_depth_reduction','width_depth_reduction','alpha_reduction_origin','width_reduction_origin'}
FILTER_KEYS=set(KEYS)|{'intersections','self_intersections','crease_angle','crease_angle_max','merge_groups'}

def validate_nested(value,validate,hidden=False):
    if not isinstance(value,dict):raise ValueError('Brush channels require an object')
    if hidden:
        extra=set(value)-(BRUSH_KEYS|FILTER_KEYS|{'feature_brushes'})
        if extra:raise ValueError('Unsupported hidden setting: '+str(sorted(extra)))
        return validate(value,partial=True)
    result={}
    for feature,brush in value.items():
        if feature not in PRIORITY or not isinstance(brush,dict) or set(brush)-BRUSH_KEYS:
            raise ValueError('Unsupported feature brush: '+str(feature))
        result[feature]=validate(brush,partial=True)
    return result

def prepare(raw,resolve):
    """Resolve pixel scaling separately for every brush; keep persisted data raw."""
    base={k:v for k,v in raw.items() if k not in ('feature_brushes','hidden_style')}
    channels=[]
    for hidden in (False,True):
        if hidden and not raw.get('hidden_lines'):continue
        values=dict(base)
        specifics=raw.get('feature_brushes',{})
        if hidden:
            if raw.get('hidden_style'):
                values.update(width_profile=[],alpha_profile=[],alpha_depth_reduction=[],width_depth_reduction=[],alpha_reduction_origin=[],width_reduction_origin=[],pencil_profile_width=True,profile_direction=-30.,profile_split_angle=90.,profile_loop_direction=0,brush_size_scale=1.,line_opacity=1.,blend_mode=0,brush_key="",dash_length=0.,dash_gap=-1.,taper=0.,width_variation=0.,distance_reduction=0.)
            values['line_color']=raw.get('hidden_color',[.5,.5,.6])
            values.update(raw.get('hidden_style',{}))
            specifics=values.pop('feature_brushes',{})
        values['hidden_lines']=hidden
        values['_visibility_mode']=-1 if hidden else 1
        values['hidden_color']=values['line_color']
        default=resolve(values)
        brushes={}
        for name,brush in specifics.items():
            selected=dict(values,width_profile=[],alpha_profile=[],pencil_profile_width=True,profile_direction=-30.,profile_split_angle=90.,profile_loop_direction=0,brush_size_scale=1.,line_opacity=1.,blend_mode=0,brush_key="",dash_length=0.,dash_gap=-1.,taper=0.,width_variation=0.,distance_reduction=0.)
            selected.update(brush);selected['hidden_color']=selected['line_color']
            brushes[name]=resolve(selected)
        channels.append(dict(settings=default,brushes=brushes))
    parent=resolve(base)
    parent['_brush_channels']=channels
    for key in FILTER_KEYS-set(('crease_angle','crease_angle_max')):
        parent[key]=any(c['settings'].get(key,False) for c in channels)
    parent['hidden_lines']=bool(raw.get('hidden_lines'))
    parent['line_width']=max([s['line_width'] for c in channels for s in [c['settings'],*c['brushes'].values()]],default=0.)
    return parent

def _groups(flags,channel):
    """One brush per edge. Outline/open is exclusive even when disabled."""
    remaining=flags!=0
    for feature in PRIORITY:
        if feature=='intersection':continue
        bit=1<<FEATURES.index(feature)
        chosen=remaining & ((flags&bit)!=0)
        if np.any(chosen):
            yield np.flatnonzero(chosen),channel['brushes'].get(feature,channel['brushes'].get('outline') if feature=='open' else None) or channel['settings']
            remaining[chosen]=False

def edge_groups(prepared,camera,parent,classify):
    for channel in parent['_brush_channels']:
        style=channel['settings']
        _,flags=classify(prepared,camera,dict(style,outline=True,open_edges=True))
        boundary=(flags&6)!=0
        flags[boundary]&=6
        if not style.get('outline'):flags&=np.uint8(255^4)
        if not style.get('open_edges'):flags&=np.uint8(255^2)
        for ids,brush in _groups(flags,channel):yield ids,flags,brush

def feature_styles(parent,feature,self_intersection=False):
    if '_brush_channels' not in parent:return [parent]
    key={'open':'open_edges','intersection':'self_intersections' if self_intersection else 'intersections'}.get(feature,feature)
    return [c['brushes'].get(feature,c['brushes'].get('outline') if feature=='open' else None) or c['settings']
            for c in parent['_brush_channels'] if c['settings'].get(key,False)]


def needs_hidden_intersections(style):
    if not style.get('hidden_lines'):return False
    if '_brush_channels' not in style:return True
    return any(c['settings'].get('_visibility_mode')==-1 and
               (c['settings'].get('intersections') or c['settings'].get('self_intersections'))
               for c in style['_brush_channels'])
