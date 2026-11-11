"""Original procedural line/ink presets, shared by CPU and general Preview."""
import numpy as np

SHAPES=(('Solid (default)','실선 (기본)'),('Dashed','대시'),('Zigzag','지그재그'),('Wave','물결'),('Scallop','연속 아치'),('Hatching','사선 해칭'),('Loops','루프'),('PNG pattern','PNG 사용자 패턴'))
BRUSHES=(('Clean (default)','기본 브러시'),('Rough ink','거친 붓'),('Dry brush','드라이 브러시'),('Fine scratch','가는 스크래치'),('PNG brush','PNG 사용자 브러시'))
KEYS={'line_image','brush_image','brush_stamp_spacing','line_pattern','brush_preset','pattern_period','pattern_amplitude'}

def active(style):return bool(style.get('line_pattern',0) or style.get('brush_preset',0))

def patch(kind,index):
    index=int(index)
    if kind=='shape':
        if not 0<=index<len(SHAPES):raise ValueError('Unknown line shape preset')
        return dict(line_pattern=index,pattern_period=12. if index==5 else 16. if index==6 else 20.,pattern_amplitude=5. if index==6 else 3.,dash_length=0.,dash_gap=-1.)
    if kind=='brush':
        if not 0<=index<len(BRUSHES):raise ValueError('Unknown stroke brush preset')
        return dict(brush_preset=index,brush_roughness=1.,brush_density=1.,brush_width_scale=1.)
    raise ValueError('Unknown preset category')

def lanes(style):return (1,7,9,5,1)[int(style.get('brush_preset',0))]

def lane_style(style):
    result=dict(style,brush_preset=0,line_pattern=0)
    if style.get('brush_preset'):result['line_width']=style['line_width']/lanes(style)*1.12*(.55 if style.get('brush_preset')==3 else 1.)*style.get('brush_width_scale',1.)
    result.pop('_preset_owners',None)
    return result

def configure_passes(passes):
    for item in passes:
        for i,style in enumerate(list(item['styles'])):
            from . import png_pattern
            if png_pattern.is_image(style):
                style['_png_owners']=[]
                for level in range(1,png_pattern.LEVELS+1):
                    child=png_pattern.child_style(style,level);child['_preset_child']=True
                    style['_png_owners'].append(len(item['styles']));item['styles'].append(child)
                    if 'style_nodes' in item:item['style_nodes'].append(item['style_nodes'][i])
            elif style.get('brush_preset'):
                style['_preset_owners']=[]
                # One thin style is enough: texture is geometric coverage, not
                # an opacity approximation or a viewport-only color change.
                child=lane_style(style);child['_preset_child']=True
                style['_preset_owners'].append(len(item['styles']))
                item['styles'].append(child)
                if 'style_nodes' in item:item['style_nodes'].append(item['style_nodes'][i])

def _noise(x,seed):
    lo=np.floor(x);t=x-lo;t=t*t*(3-2*t)
    def h(v):return np.mod(np.sin(v*127.1+seed*311.7)*43758.5453,1.)
    return (1-t)*h(lo)+t*h(lo+1)

def domains(points,camera):
    """Accumulate projected length on degree-two chains; split at branches."""
    from .renderer import _project
    points=np.asarray(points,float);result=np.zeros((len(points),2));adjacency={};keys=[]
    cam=(points-camera['eye'])@camera['basis'].T
    xy=_project(np.where(np.abs(cam[:,:,2:3])<1e-12,cam+np.array([0,0,1e-12]),cam),camera)
    lengths=np.linalg.norm(xy[:,1]-xy[:,0],axis=1)
    for i,pair in enumerate(points):
        key=tuple(tuple(np.round(p,10)) for p in pair);keys.append(key)
        for v in key:adjacency.setdefault(v,[]).append(i)
    used=set()
    for i in range(len(points)):
        if i in used:continue
        chain=[(i,0,1)];used.add(i)
        for side in (0,1):
            current=i;end=side
            while True:
                v=keys[current][end];edges=adjacency[v]
                if len(edges)!=2:break
                other=edges[0] if edges[1]==current else edges[1]
                if other in used:break
                near=0 if keys[other][0]==v else 1;far=1-near
                used.add(other)
                if side==0:chain.insert(0,(other,far,near))
                else:chain.append((other,near,far))
                current,end=other,far
        if tuple(xy[chain[-1][0],chain[-1][2]])<tuple(xy[chain[0][0],chain[0][1]]):chain=[(k,b,a) for k,a,b in reversed(chain)]
        cursor=0.
        for k,a,b in chain:result[k,a]=cursor;cursor+=lengths[k];result[k,b]=cursor
    return result

def variant_style(style,variant):
    if isinstance(variant,tuple):
        from .png_pattern import child_style
        return child_style(style,variant[1])
    return lane_style(style)

def variant_owner(style,owner,variant):
    if isinstance(variant,tuple):return style['_png_owners'][variant[1]-1]
    return style['_preset_owners'][0] if variant else owner

def path_offsets(distance,style):
    pattern=int(style.get('line_pattern',0));period=float(style.get('pattern_period',20.));amp=float(style.get('pattern_amplitude',3.))
    q=distance/period;f=np.mod(q,1.);along=np.zeros_like(distance);offset=np.zeros_like(distance);keep=np.ones(len(distance)-1,bool)
    if pattern==1:keep=np.mod((distance[:-1]+distance[1:])*.5,period)<period*.6
    elif pattern==2:offset=amp*(1-4*np.abs(f-.5))
    elif pattern==3:offset=amp*np.sin(2*np.pi*q)
    elif pattern==4:offset=-amp*np.sin(np.pi*f)
    elif pattern==5:along=-period*.55*(f-.5);offset=amp*(2*f-1);keep=np.abs(np.diff(f))<.5
    elif pattern==6:along=period*.34*np.sin(2*np.pi*q);offset=amp*(1-np.cos(2*np.pi*q))
    return along,offset,keep

def expand(points,style,camera,scale=1.,phase=None):
    """Return screen-designed world segments and their source parameters.

    Depth is interpolated in reciprocal perspective space. Pattern units are
    final output pixels, independent of CPU oversampling.
    """
    from . import png_pattern
    if png_pattern.is_image(style):return png_pattern.expand(points,style,camera,scale,phase,path_offsets)
    from .renderer import _project
    points=np.asarray(points,float);cam=(points-camera['eye'])@camera['basis'].T
    if np.any(cam[:,2]<=camera['near']):
        return [(points[None],np.array([[0.,1.]]),False)]
    screen=_project(cam,camera)/scale;delta=screen[1]-screen[0];length=float(np.linalg.norm(delta))
    if length<1e-8:return []
    tangent=delta/length;normal=np.array([-tangent[1],tangent[0]])
    pattern=int(style.get('line_pattern',0));texture=int(style.get('brush_preset',0));period=float(style.get('pattern_period',20.));amp=float(style.get('pattern_amplitude',3.))
    # Anchor at a consistent end, including reversed topology edges.
    reverse=(phase[1]<phase[0]) if phase is not None else tuple(screen[1])<tuple(screen[0])
    if reverse:normal=-normal;tangent=-tangent
    from .renderer import _screen_clip
    limits=_screen_clip(screen[0],screen[1],camera['width']/scale,camera['height']/scale,amp+period+style['line_width'])
    if limits is None:return []
    lo,hi=limits
    n=max(1,int(np.ceil(length*(hi-lo)/(1. if texture else min(1.,period/24.)))))
    u=np.linspace(lo,hi,n+1);distance=(phase[0]+u*(phase[1]-phase[0]))/scale if phase is not None else length*(1-u if reverse else u);q=distance/period;f=np.mod(q,1.)
    along,offset,keep=path_offsets(distance,style)
    output=[];count=lanes(style)
    for lane in range(count):
        disp=offset.copy();mask=keep.copy()
        if texture:
            width=float(style['line_width'])*(.55 if texture==3 else 1.)*style.get('brush_width_scale',1.);spacing=width/count
            envelope=.6+.4*_noise(distance*.055,texture*97)
            disp+=(lane-(count-1)/2)*spacing*envelope
            disp+=width*.13*style.get('brush_roughness',1.)*(_noise(distance*.65,lane+texture*17)-.5)
            disp+=width*.1*style.get('brush_roughness',1.)*(_noise(distance*.12,texture*73)-.5)
            threshold=1.-(1.-(0.,.10,.33,.16)[texture])*style.get('brush_density',1.)
            mid=(distance[:-1]+distance[1:])*.5
            mask&=_noise(mid*.9,lane+texture*41)>threshold
        xy=(screen[0]+u[:,None]*delta+along[:,None]*tangent+disp[:,None]*normal)*scale
        z=cam[0,2]+u*(cam[1,2]-cam[0,2]) if camera['ortho'] else 1/((1-u)/cam[0,2]+u/cam[1,2])
        local=np.empty((len(u),3));local[:,2]=z
        if camera['ortho']:
            factor=camera['width']/camera['span'];local[:,:2]=(xy-[camera['width']/2,camera['height']/2])/[factor,-factor]
        else:local[:,:2]=(xy-[camera['width']/2,camera['height']/2])*z[:,None]/[camera['focal'],-camera['focal']]
        world=local@np.linalg.inv(camera['basis']).T+camera['eye']
        pairs=np.stack((world[:-1],world[1:]),axis=1)[mask];parameters=np.column_stack((u[:-1],u[1:]))[mask]
        if len(pairs):output.append((pairs,parameters,bool(texture)))
    return output

def cpu_segments(segments,camera,scale):
    """Leave ordinary geometry packed and untouched; expand opted-in brushes."""
    from .packed_segments import PackedSegments
    from .renderer import EDGE_FEATURES
    if not any(active(s) for s in (segments.styles() if hasattr(segments,'styles') else [v['settings'] for v in segments])):return segments
    from .profile_strokes import assign_coordinates
    from .renderer import _project
    records=assign_coordinates(segments,camera,_project)
    groups={};distances={}
    for i,row in enumerate(records):
        if active(row['settings']):groups.setdefault((row['mesh_index'],id(row['settings'])),[]).append(i)
    for ids in groups.values():
        spans=domains([[records[i]['a'],records[i]['b']] for i in ids],camera)
        distances.update(zip(ids,spans))
    out=PackedSegments();cache={}
    for i,row in enumerate(records):
        style=row['settings']
        if not active(style):out.append(row);continue
        flags=128 if 'intersection' in row['features'] else sum(1<<EDGE_FEATURES.index(v) for v in row['features'])
        for points,t,thin in expand([row['a'],row['b']],style,camera,scale,distances[i]):
            child=cache.setdefault((id(style),thin),variant_style(style,thin))
            out._flush();part=dict(points=points,flags=np.full(len(points),flags,np.uint8),settings=child,mesh=row['mesh'],mesh_index=row['mesh_index'],line=row.get('line'),count=len(points))
            if '_profile_u' in row:
                a,b=row['_profile_u'];part['profile_u']=a+t*(b-a)
            out.parts.append(part);out.count+=len(points)
            if flags==128:part['intersection']=True;out.intersection_count+=len(points)
    return out
