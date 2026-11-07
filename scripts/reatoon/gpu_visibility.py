"""Conservative GPU whole-segment occlusion certificates.

A segment is rejected only when both endpoints lie strictly inside the shadow
of ONE triangle. A convex triangle shadow contains the entire joining segment.
No midpoint-only deletion, CPU ray fallback, or depth-bias tuning is used.
"""
import numpy as np
WORK_GROUP_SIZE=64
SOURCE=r'''
#pragma OPENCL FP_CONTRACT OFF
int rt_bounds_hit(float3 origin,float3 direction,float3 inverse,float3 margin,float3 box_lo,float3 box_hi) {
  float3 lo=nextafter(box_lo-margin,(float3)(-INFINITY));
  float3 hi=nextafter(box_hi+margin,(float3)(INFINITY));
  if(any((direction==0.f)&((origin<lo)|(origin>hi))))return 0;
  float3 a0=(lo-origin)*inverse,b0=(hi-origin)*inverse;
  float3 low=fmin(a0,b0),high=fmax(a0,b0);
  int3 finite=(direction!=0.f)&isfinite(inverse)&isfinite(low)&isfinite(high);
  float3 pad=16.f*0x1.0p-23f*fmax(fabs(low),fabs(high))+16.f*0x1.0p-126f;
  low=select((float3)(-INFINITY),low-pad,finite);
  high=select((float3)(INFINITY),high+pad,finite);
  float lower=fmax(0.f,fmax(low.x,fmax(low.y,low.z)));
  float upper=fmin(1.f,fmin(high.x,fmin(high.y,high.z)));
  return lower<=upper;
}
int rt_inside_shadow(double3 origin,double3 dir,double near_t,double3 a,double3 e,double3 f) {
 double hx=dir.y*f.z-dir.z*f.y,hy=dir.z*f.x-dir.x*f.z,hz=dir.x*f.y-dir.y*f.x;
 double det=e.x*hx+e.y*hy+e.z*hz;if(det==0.)return 0;
 double3 s=origin-a;double u=(s.x*hx+s.y*hy+s.z*hz)/det;
 if(u<=0.||u>=1.)return 0;
 double qx=s.y*e.z-s.z*e.y,qy=s.z*e.x-s.x*e.z,qz=s.x*e.y-s.y*e.x;
 double v=(dir.x*qx+dir.y*qy+dir.z*qz)/det;
 if(v<=0.||u+v>=1.)return 0;
 double t=(f.x*qx+f.y*qy+f.z*qz)/det;
 if(t<=near_t||t>=1.)return 0;
 double dp=0.,up=0.,vp=0.,tp=0.;
 for(int axis=0;axis<3;axis++){int j=(axis+1)%3,k=(axis+2)%3;
  dp+=fabs(e[axis])*(fabs(dir[j]*f[k])+fabs(dir[k]*f[j]));
  up+=fabs(s[axis])*(fabs(dir[j]*f[k])+fabs(dir[k]*f[j]));
  vp+=fabs(dir[axis])*(fabs(s[j]*e[k])+fabs(s[k]*e[j]));
  tp+=fabs(f[axis])*(fabs(s[j]*e[k])+fabs(s[k]*e[j]));}
 double gamma=64.*0x1.0p-52,de=gamma*dp,den=fabs(det)-de;if(den<=0.)return 0;
 double ue=(gamma*up+fabs(u)*de)/den,ve=(gamma*vp+fabs(v)*de)/den,te=(gamma*tp+fabs(t)*de)/den;
 double magnitude=fmax(1.,fmax(fmax(fabs(origin.x),fmax(fabs(origin.y),fabs(origin.z))),fmax(fabs(dir.x),fmax(fabs(dir.y),fabs(dir.z)))));
 double guard=256.*0x1.0p-52*magnitude/fmax(length(dir),0x1.0p-500);
 return u>ue&&v>ve&&(u+v+ue+ve)<1.&&t-te>near_t&&t+te+guard<1.;
}
int rt_same_triangle_shadow(double3 eye,double3 first,double3 last,double3 a,double3 b,double3 c) {
 // Four exact-sign halfspaces bound a convex triangle shadow volume.
 // Strict inequalities conservatively retain boundary/self-surface edges.
 double reference=rt_orient(eye,b,c,a);
 double x=rt_orient(first,b,c,a),y=rt_orient(last,b,c,a);
 if(reference==0.||x==0.||y==0.||(x>0.)==(reference>0.)||(y>0.)==(reference>0.))return 0;
 double3 vertices[3]={a,b,c};
 for(int k=0;k<3;k++) {
  int j=(k+1)%3,h=(k+2)%3;
  reference=rt_orient(vertices[h],vertices[k],vertices[j],eye);
  x=rt_orient(first,vertices[k],vertices[j],eye);y=rt_orient(last,vertices[k],vertices[j],eye);
  if(reference==0.||x==0.||y==0.||(x>0.)!=(reference>0.)||(y>0.)!=(reference>0.))return 0;
 }
 return 1;
}
__kernel void rt_occluded_segments(__global const double *vertices,__global const int *ids,
 __global const float4 *lows,__global const float4 *highs,__global const double4 *lines,
 __global const double *camera,__global int *blockers,int base,int count,double near,int reuse) {
 int sample=get_global_id(0);if(sample>=count)return;
 int previous=reuse?blockers[sample]:-1;blockers[sample]=-1;
 double3 eye=vload3(0,camera),forward=vload3(1,camera);
 double3 first=lines[2*sample].xyz,last=lines[2*sample+1].xyz;
 double3 da=first-eye,db=last-eye,mid=(first+last)*.5,dir=mid-eye;
 double za=dot(da,forward),zb=dot(db,forward),zm=dot(dir,forward);
 if(za<=near||zb<=near||zm<=near)return;
 // Previous blockers are hints only. Re-prove against the current camera,
 // endpoints AND current vertex positions, even when segment order changes.
 if(previous>=0){
  double3 a=vload3(ids[3*previous],vertices),b=vload3(ids[3*previous+1],vertices),c=vload3(ids[3*previous+2],vertices);
  if(dot(a-eye,forward)>near&&dot(b-eye,forward)>near&&dot(c-eye,forward)>near&&
     rt_inside_shadow(eye,da,near/za,a,b-a,c-a)&&rt_inside_shadow(eye,db,near/zb,a,b-a,c-a)&&
     rt_same_triangle_shadow(eye,first,last,a,b,c)){blockers[sample]=previous;return;}
 }
 // Float traversal encloses the entire double ray for t in [0,1]. Conversion
 // error expands every box; only the final guarded/exact proof can hide a line.
 float3 origin=convert_float3(eye),direction=convert_float3(dir);
 float3 margin=convert_float3_rtp(fabs(eye-convert_double3(origin))+fabs(dir-convert_double3(direction)));
 float3 inverse=(float3)(direction.x==0.f?0.f:1.f/direction.x,direction.y==0.f?0.f:1.f/direction.y,direction.z==0.f?0.f:1.f/direction.z);
 float3 first_dir=convert_float3(da),last_dir=convert_float3(db);
 float3 first_margin=convert_float3_rtp(fabs(eye-convert_double3(origin))+fabs(da-convert_double3(first_dir)));
 float3 last_margin=convert_float3_rtp(fabs(eye-convert_double3(origin))+fabs(db-convert_double3(last_dir)));
 float3 first_inv=select(1.f/first_dir,(float3)(0),first_dir==0.f);
 float3 last_inv=select(1.f/last_dir,(float3)(0),last_dir==0.f);
 int stack[32],pending=1;stack[0]=1;
 while(pending){int node=stack[--pending];if(highs[node].w<0)continue;
  if(!rt_bounds_hit(origin,direction,inverse,margin,lows[node].xyz,highs[node].xyz))continue;
  if(!rt_bounds_hit(origin,first_dir,first_inv,first_margin,lows[node].xyz,highs[node].xyz))continue;
  if(!rt_bounds_hit(origin,last_dir,last_inv,last_margin,lows[node].xyz,highs[node].xyz))continue;
  if(node<base){stack[pending++]=node*2;stack[pending++]=node*2+1;continue;}
  int triangle=node-base;
  double3 a=vload3(ids[3*triangle],vertices),b=vload3(ids[3*triangle+1],vertices),c=vload3(ids[3*triangle+2],vertices);
  // Keep near-clipped blockers instead of certifying against clipped-away geometry.
  if(dot(a-eye,forward)<=near||dot(b-eye,forward)<=near||dot(c-eye,forward)<=near)continue;
  if(!rt_inside_shadow(eye,dir,near/zm,a,b-a,c-a))continue;
  if(rt_inside_shadow(eye,da,near/za,a,b-a,c-a)&&rt_inside_shadow(eye,db,near/zb,a,b-a,c-a)&&rt_same_triangle_shadow(eye,first,last,a,b,c)){
   blockers[sample]=triangle;return;
  }
 }
}
#pragma OPENCL FP_CONTRACT ON
'''

# Keep the adaptive expansion kernel out of the normal traversal's register /
# local-memory footprint. Only ambiguous predicates take the exact GPU pass.
_start=SOURCE.index('__kernel void rt_occluded_segments')
_end=SOURCE.index('#pragma OPENCL FP_CONTRACT ON',_start)
_kernel=SOURCE[_start:_end]
_exact=_kernel.replace('rt_occluded_segments(', 'rt_occluded_segments_exact(').replace(
    'int base,int count,double near,int reuse)', '__global const int *samples,int base,int count,double near,int reuse)').replace(
    'int sample=get_global_id(0);if(sample>=count)return;', 'int work=get_global_id(0);if(work>=count)return;int sample=samples[work];')
_filtered=_kernel.replace('int previous=reuse?', 'int uncertain=0;int previous=reuse?').replace(
    'rt_same_triangle_shadow(eye,first,last,a,b,c)', 'rt_shadow_filtered(eye,first,last,a,b,c,&uncertain)')
_last=_filtered.rfind('\n}')
_filtered=_filtered[:_last]+'\n if(uncertain)blockers[sample]=-2;'+_filtered[_last:]
_helpers=r'''
double rt_orient_checked(double3 a,double3 b,double3 c,double3 d) {
 double3 ad=a-d,bd=b-d,cd=c-d;
 double bc1=bd.x*cd.y,bc2=cd.x*bd.y,ca1=cd.x*ad.y,ca2=ad.x*cd.y,ab1=ad.x*bd.y,ab2=bd.x*ad.y;
 double determinant=ad.z*(bc1-bc2)+bd.z*(ca1-ca2)+cd.z*(ab1-ab2);
 double permanent=(fabs(bc1)+fabs(bc2))*fabs(ad.z)+(fabs(ca1)+fabs(ca2))*fabs(bd.z)+(fabs(ab1)+fabs(ab2))*fabs(cd.z);
 double unit=0x1.0p-53,bound=(7.+56.*unit)*unit*permanent;
 return fabs(determinant)>bound||permanent==0.?determinant:NAN;
}
int rt_shadow_filtered(double3 eye,double3 first,double3 last,double3 a,double3 b,double3 c,int *uncertain) {
 double reference=rt_orient_checked(eye,b,c,a);
 double x=rt_orient_checked(first,b,c,a),y=rt_orient_checked(last,b,c,a);
 if(isnan(reference)||isnan(x)||isnan(y)){*uncertain=1;return 0;}
 if(reference==0.||x==0.||y==0.||(x>0.)==(reference>0.)||(y>0.)==(reference>0.))return 0;
 double3 vertices[3]={a,b,c};
 for(int k=0;k<3;k++) {
  int j=(k+1)%3,h=(k+2)%3;
  reference=rt_orient_checked(vertices[h],vertices[k],vertices[j],eye);
  x=rt_orient_checked(first,vertices[k],vertices[j],eye);y=rt_orient_checked(last,vertices[k],vertices[j],eye);
  if(isnan(reference)||isnan(x)||isnan(y)){*uncertain=1;return 0;}
  if(reference==0.||x==0.||y==0.||(x>0.)!=(reference>0.)||(y>0.)!=(reference>0.))return 0;
 }
 return 1;
}
'''
_indexed=_filtered.replace('rt_occluded_segments(', 'rt_occluded_segments_indexed(').replace(
    'int base,int count,double near,int reuse)', '__global const int *samples,int base,int count,double near,int reuse)').replace(
    'int sample=get_global_id(0);if(sample>=count)return;', 'int work=get_global_id(0);if(work>=count)return;int sample=samples[work];')
_indexed=_indexed.replace('int reuse)', 'int reuse,__global const int *dirty)').replace(
    'int uncertain=0;', 'int restrict_dirty=blockers[sample]==-3;int uncertain=0;').replace(
    'if(highs[node].w<0)continue;', 'if(highs[node].w<0||(restrict_dirty&&!dirty[node]))continue;')
_hint=r'''
__kernel void rt_check_previous(__global const double *vertices,__global const int *ids,
 __global const double4 *lines,__global const double *camera,__global int *blockers,int count,double near,int static_prefix){
 int sample=get_global_id(0);if(sample>=count)return;
 int previous=blockers[sample];blockers[sample]=-1;
 if(previous<0){if(previous==-1&&sample<static_prefix)blockers[sample]=-3;return;}
 double3 eye=vload3(0,camera),forward=vload3(1,camera);
 double3 first=lines[2*sample].xyz,last=lines[2*sample+1].xyz,da=first-eye,db=last-eye;
 double za=dot(da,forward),zb=dot(db,forward);if(za<=near||zb<=near)return;
 double3 a=vload3(ids[3*previous],vertices),b=vload3(ids[3*previous+1],vertices),c=vload3(ids[3*previous+2],vertices);
 if(dot(a-eye,forward)<=near||dot(b-eye,forward)<=near||dot(c-eye,forward)<=near)return;
 int uncertain=0;
 if(rt_inside_shadow(eye,da,near/za,a,b-a,c-a)&&rt_inside_shadow(eye,db,near/zb,a,b-a,c-a)&&
    rt_shadow_filtered(eye,first,last,a,b,c,&uncertain))blockers[sample]=previous;
}
__kernel void rt_clip_segments(__global const double4 *lines,__global const double *matrix,
 __global int *blockers,int count,double margin_x,double margin_y){
 int i=get_global_id(0);if(i>=count)return;
 double4 p=lines[2*i],q=lines[2*i+1];
 double4 cx=(double4)(matrix[0],matrix[4],matrix[8],matrix[12]);
 double4 cy=(double4)(matrix[1],matrix[5],matrix[9],matrix[13]);
 double4 cw=(double4)(matrix[3],matrix[7],matrix[11],matrix[15]);
 double pw=dot(p,cw),qw=dot(q,cw);
 for(int axis=0;axis<2;axis++)for(int sign=-1;sign<=1;sign+=2){
  double4 plane=cw+sign*(axis==0?cx:cy);
  double4 magnitude=fabs(cw)+fabs(axis==0?cx:cy);
  double ep=64.*0x1.0p-52*dot(fabs(p),magnitude)+1.e-12;
  double eq=64.*0x1.0p-52*dot(fabs(q),magnitude)+1.e-12;
  double margin=axis==0?margin_x:margin_y;
  if(dot(p,plane)<-ep-margin*fabs(pw)&&dot(q,plane)<-eq-margin*fabs(qw)){
   blockers[i]=-5;return;
  }
 }
}
'''
SOURCE=SOURCE[:_start]+_exact+_helpers+_hint+_filtered+_indexed+'\n#pragma OPENCL FP_CONTRACT ON\n'
from .gpu_visibility_hints import SOURCE as _HINT_SOURCE
SOURCE+=_HINT_SOURCE

def certify_buffer(gpu,points_buffer,count,camera,static_prefix=0):
    """Return blocking triangle IDs or -1; hidden-line styles must bypass this."""
    if not count:return np.empty(0,np.int32)
    if camera.get('projection','perspective')!='perspective':
        return np.full(count,-1,np.int32) # Explicit conservative keep for ortho.
    eye=np.asarray(camera['position'],np.float64)
    forward=np.asarray(camera['target'],np.float64)-eye
    forward/=np.linalg.norm(forward)
    import time
    start=time.perf_counter();r=gpu.runtime;buffers=[]
    stats=dict(previous_ms=0.,pending=count,exact=0,static_prefix=static_prefix)
    camera_key=(eye.tobytes(),forward.tobytes(),float(camera.get('near',.1)))
    if getattr(gpu,'visibility_history_camera',None)!=camera_key:static_prefix=0
    stats['static_prefix']=static_prefix
    try:
        history=getattr(gpu,'visibility_history',None)
        reuse=history is not None and history[0]==count
        if not reuse:
            if history is not None:history[1].close()
            gpu.visibility_history=(count,r.buffer(count*4))
        result=gpu.visibility_history[1]
        buffers=[r.buffer(np.r_[eye,forward])]
        if reuse:
            r.run('rt_check_previous',count,gpu.vertices,gpu.triangles,points_buffer,buffers[0],result,count,float(camera.get('near',.1)),int(static_prefix),local_size=WORK_GROUP_SIZE)
        clip=camera.get('viewport_clip')
        if clip is not None:
            if not reuse:r.write(result,np.full(count,-1,np.int32))
            matrix=r.buffer(np.asarray(clip['matrix'],np.float64));buffers.append(matrix)
            margin=float(clip.get('margin_pixels',8))
            r.run('rt_clip_segments',count,points_buffer,matrix,result,count,
                  2.*margin/max(1,clip['width']),2.*margin/max(1,clip['height']),local_size=WORK_GROUP_SIZE)
        if reuse or clip is not None:
            if getattr(gpu,'visibility_history_camera',None)!=camera_key:
                from .gpu_visibility_hints import apply
                stats['screen_hints']=apply(gpu,points_buffer,count,result,camera,eye,forward)
            previous=r.read(result,count,np.int32)
            pending=np.flatnonzero((previous<0)&(previous!=-5)).astype(np.int32)
            stats['frustum_culled']=int(np.count_nonzero(previous==-5))
            stats['previous_ms']=(time.perf_counter()-start)*1000;stats['pending']=len(pending)
            if len(pending):
                indices=r.buffer(pending);buffers.append(indices)
                r.run('rt_occluded_segments_indexed',len(pending),gpu.vertices,gpu.triangles,gpu.lo,gpu.hi,points_buffer,buffers[0],result,indices,gpu.base,len(pending),float(camera.get('near',.1)),0,gpu.dirty_nodes,local_size=WORK_GROUP_SIZE)
        else:
            r.run('rt_occluded_segments',count,gpu.vertices,gpu.triangles,gpu.lo,gpu.hi,points_buffer,buffers[0],result,gpu.base,count,float(camera.get('near',.1)),0,local_size=WORK_GROUP_SIZE)
        blockers=r.read(result,count,np.int32)
        uncertain=np.flatnonzero(blockers==-2).astype(np.int32)
        stats['traversal_ms']=(time.perf_counter()-start)*1000-stats['previous_ms'];stats['exact']=len(uncertain)
        exact_started=time.perf_counter()
        if len(uncertain):
            indices=r.buffer(uncertain);buffers.append(indices)
            r.run('rt_occluded_segments_exact',len(uncertain),gpu.vertices,gpu.triangles,gpu.lo,gpu.hi,points_buffer,buffers[0],result,indices,gpu.base,len(uncertain),float(camera.get('near',.1)),0,local_size=WORK_GROUP_SIZE)
            blockers=r.read(result,count,np.int32)
        gpu.visibility_history_camera=camera_key
        stats['exact_ms']=(time.perf_counter()-exact_started)*1000
        gpu.visibility_diagnostics=stats
        return blockers
    finally:
        for b in buffers:b.close()

def certify(gpu,points,camera):
    points=np.asarray(points,np.float64).reshape(-1,4)
    buffer=gpu.runtime.buffer(points)
    try:return certify_buffer(gpu,buffer,len(points)//2,camera)
    finally:buffer.close()


def filter_segments(gpu,points,owners,styles,camera,return_mask=False):
    """Filter only visible-line styles; hidden-line groups bypass certification.

    The optional keep mask lets viewport integration retain aligned metadata.
    GPUScene must compile this module's SOURCE alongside its normal kernels.
    """
    if getattr(gpu,'paged',False):
        return gpu.filter_segments(points,owners,styles,camera,return_mask=return_mask)
    import time
    start=time.perf_counter()
    points=np.asarray(points,np.float64).reshape(-1,2,4)
    owners=np.asarray(owners,np.int32)
    if len(points)!=len(owners):raise ValueError('Segment/style owner count mismatch')
    keep=np.ones(len(points),np.bool_)
    allowed=np.asarray([not style.get('hidden_lines',False) for style in styles],np.bool_)
    if len(owners) and (owners.min()<0 or owners.max()>=len(allowed)):
        raise ValueError('Segment style owner is out of range')
    eligible=allowed[owners]
    report=dict(backend='opencl_gpu_shadow_certificate',input_segments=len(points),checked_segments=0,rejected_segments=0,hidden_style_bypass=int((~eligible).sum()))
    if camera.get('projection','perspective')!='perspective':report['orthographic_bypass']=True
    elif np.any(eligible):
        cache=getattr(gpu,'cross_cache',None)
        direct=bool(np.all(eligible) and cache is not None and np.shares_memory(points,cache[0]))
        blockers=(certify_buffer(gpu,gpu.cross_output,len(points),camera,getattr(gpu,'visibility_static_prefix',0)) if direct
                  else certify(gpu,points[eligible],camera))
        if direct:
            gpu.visibility_history_source=cache[0]
            gpu.visibility_last_blockers=blockers
            gpu.visibility_last_camera=gpu.visibility_history_camera
        report['resident_cross_buffer']=direct
        report['work']=getattr(gpu,'visibility_diagnostics',{})
        keep[eligible]=(blockers<0)&(blockers!=-5)
        report['checked_segments']=int(eligible.sum());report['rejected_segments']=int((~keep).sum())
    report['seconds']=time.perf_counter()-start
    result=(points[keep].reshape(-1,4),owners[keep],report)
    return (*result,keep) if return_mask else result
