"""Pure numeric surface-stroke evaluation and normal CPU-line submission."""
import hashlib
import numpy as np

def preview_samples(points):
    """Keep original bindings; omit only subpixel float-noise spans in VP2."""
    p=np.asarray(points,float);tolerance=max(1e-8,float(np.max(np.ptp(p,axis=0)))*1e-5,float(np.max(np.abs(p)))*np.finfo(np.float32).eps*8)
    keep=[0]
    for i in range(1,len(p)-1):
        if np.linalg.norm(p[i]-p[keep[-1]])>tolerance:keep.append(i)
    if len(keep)>1 and np.linalg.norm(p[-1]-p[keep[-1]])<=tolerance:keep.pop()
    keep.append(len(p)-1)
    return np.asarray(keep,np.int64)

def neighbor_points(points):
    """Skip sub-float triangle-boundary samples when forming GPU joins.

    Only genuine/effectively coincident path endpoints get round caps. A tiny
    intermediate segment must not masquerade as an endpoint and overpaint ink.
    """
    p=np.asarray(points,float);epsilon=max(1e-8,float(np.max(np.abs(p)))*np.finfo(np.float32).eps*8);before=[];after=[]
    for i in range(len(p)):
        j=max(0,i-1)
        while j>0 and np.linalg.norm(p[i]-p[j])<=epsilon:j-=1
        before.append(j)
        j=min(len(p)-1,i+1)
        while j<len(p)-1 and np.linalg.norm(p[i]-p[j])<=epsilon:j+=1
        after.append(j)
    return p[np.column_stack((np.asarray(before[:-1]),np.asarray(after[1:])))]

def topology_key(triangles):
    try:
        a=np.asarray(triangles,np.int64);counts=np.full(len(a),a.shape[1],np.int64);flat=a.ravel()
    except ValueError:
        counts=np.asarray([len(f) for f in triangles],np.int64);flat=np.asarray([v for f in triangles for v in f],np.int64)
    return hashlib.sha256(counts.tobytes()+flat.tobytes()).hexdigest()

def update(mesh,vertices):
    for stroke in mesh.get('_surface_strokes',[]):
        ids=np.asarray(stroke['ids'],np.int64);weights=np.asarray(stroke['weights'],np.float64)
        triangles=np.asarray(vertices,np.float64)[ids]
        stroke['points']=np.sum(triangles*weights[:,:,None],axis=1)
        normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
        stroke['normals']=normals/np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-30)

def for_pass(mesh,item):
    nodes=item.get('style_nodes',[])
    return [(stroke,nodes.index(stroke.get('_brush_style',stroke['style']))) for stroke in mesh.get('_surface_strokes',[])
            if stroke['line']==item['line'] and stroke.get('_brush_style',stroke['style']) in nodes]


def configure_passes(scene,passes,table,resolve):
    """Per-stroke pressure multiplies Line Set width, never changes its color.

    Frozen input arc coordinates keep pressure attached through camera motion
    and deformation. Uniform old/imported strokes retain the original path.
    """
    from .brush_profiles import evaluate_profile
    for mesh in scene.get('meshes',[]):
        for stroke in mesh.get('_surface_strokes',[]):
            stroke.pop('_brush_style',None)
            stroke.pop('_input_u',None)
            brush=stroke.get('brush',{})
            item=next((p for p in passes if p['line']==stroke['line']),None)
            if item is None:continue
            raw=dict(table.get(stroke['style'],{}));raw['_surface_stroke']=True
            scale=float(brush.get('width_scale',1.))
            if not np.isfinite(scale) or scale<0:continue
            raw['line_width']=float(raw.get('line_width',1.5))*scale
            shaped=brush.get('pressure') or brush.get('shape','uniform')!='uniform'
            if not shaped:
                key=stroke['style']+'#surface:'+str(scale)
                if key not in item['style_nodes']:item['styles'].append(resolve(raw));item['style_nodes'].append(key)
                stroke['_brush_style']=key
                if brush.get('preserve_domain') and len(brush.get('u',[]))==len(stroke['ids']):stroke['_input_u']=np.asarray(brush['u'],float)
                continue
            u=np.asarray(brush.get('u',[]),float);p=np.asarray(brush.get('pressure_values',[]),float)
            if len(u)!=len(stroke['ids']) or len(p)!=len(u) or len(u)<2 or not np.isfinite(u).all() or not np.isfinite(p).all():continue
            # Runtime profile format has256 control points. Preserve input
            # breakpoints where possible; quantify approximation when dense.
            x=np.unique(np.r_[np.linspace(0,1,128),u,.15,.85])
            if len(x)>256:x=np.linspace(0,1,256)
            def factor(t):
                value=np.ones_like(t)
                if brush.get('pressure'):
                    minimum=float(np.clip(brush.get('minimum',.1),0,1))
                    value*=minimum+(1-minimum)*np.clip(np.interp(t,u,p),0,1)
                shape=brush.get('shape','uniform')
                if shape=='taper':value*=np.interp(t,[0,.15,.85,1],[.05,1,1,.05])
                if shape=='wedge':value*=.05+.95*t
                return value
            base=raw.get('width_profile',[])
            y=factor(x)*evaluate_profile(base,x)
            raw.update(width_profile=[[0,float(t),float(v),float(t),float(v),float(t),float(v)] for t,v in zip(x,y)],pencil_profile_width=False)
            style=resolve(raw);key=stroke['node']+'#brush'
            item['styles'].append(style);item['style_nodes'].append(key);stroke['_brush_style']=key
            stroke['_input_u']=u
            probe=np.unique(np.r_[u,(u[:-1]+u[1:])*.5])
            stroke['_pressure_profile_error']=float(np.max(np.abs(np.interp(probe,x,y)-factor(probe)*evaluate_profile(base,probe))))

def append(scene,passes,segments):
    from .brush_channels import feature_styles
    for item in passes:
        for index,mesh in enumerate(scene['meshes']):
            offset=len(mesh['vertices'])
            for stroke,owner in for_pass(mesh,item):
                points=stroke['points'];pairs=np.column_stack((np.arange(len(points)-1),np.arange(1,len(points))))
                for style in feature_styles(item['styles'][owner],'selected'):
                    if hasattr(segments,'parts'):
                        segments._flush();part=dict(points=points[pairs],flags=np.full(len(pairs),64,np.uint8),settings=style,mesh=mesh['name'],mesh_index=index,line=item['line'],count=len(pairs),vertex_ids=pairs+offset)
                        if '_input_u' in stroke:part['profile_u']=stroke['_input_u'][pairs]
                        segments.parts.append(part);segments.count+=len(pairs)
                    else:
                        for a,b in pairs:
                            row=dict(a=points[a],b=points[b],features=['selected'],settings=style,mesh=mesh['name'],mesh_index=index,line=item['line'],_vertex_ids=(int(a+offset),int(b+offset)))
                            if '_input_u' in stroke:row['_profile_u']=stroke['_input_u'][[a,b]]
                            segments.append(row)
                offset+=len(points)
