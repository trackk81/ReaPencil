"""GPU screen-space blocker hints. Every accepted hint gets the exact proof.

The raster image is never used as a visibility decision. Missing pixels,
coarse samples, large triangles and unsupported atomics take the normal BVH.
"""
SIZE=2048
SOURCE=r'''
#pragma OPENCL FP_CONTRACT OFF
#ifdef cl_khr_int64_extended_atomics
#pragma OPENCL EXTENSION cl_khr_int64_base_atomics : enable
#pragma OPENCL EXTENSION cl_khr_int64_extended_atomics : enable
float3 hint_project(double3 p,__global const double *view,int size) {
 float3 delta=convert_float3(p-vload3(0,view));
 float z=dot(delta,convert_float3(vload3(1,view)));
 return (float3)(size*.5f+dot(delta,convert_float3(vload3(2,view)))/z*view[12],
                 size*.5f+dot(delta,convert_float3(vload3(3,view)))/z*view[12],z);
}
float hint_cross(float2 a,float2 b){return a.x*b.y-a.y*b.x;}
__kernel void hint_clear(__global ulong *pixels,int n){int i=get_global_id(0);if(i<n)pixels[i]=~(ulong)0;}
__kernel void hint_raster(__global const double *vertices,__global const int *ids,__global const double *view,
 __global ulong *pixels,int n,int size,double near){
 int i=get_global_id(0);if(i>=n)return;
 float3 a=hint_project(vload3(ids[3*i],vertices),view,size);
 float3 b=hint_project(vload3(ids[3*i+1],vertices),view,size);
 float3 c=hint_project(vload3(ids[3*i+2],vertices),view,size);
 if(a.z<=near||b.z<=near||c.z<=near)return;
 float2 lower=fmin(a.xy,fmin(b.xy,c.xy)),upper=fmax(a.xy,fmax(b.xy,c.xy));
 if(any(!isfinite(lower))||any(!isfinite(upper))||any(lower>=size)||any(upper<0.f))return;
 int2 lo=convert_int2(fmax((float2)(0),floor(lower))),hi=convert_int2(fmin((float2)(size-1),floor(upper)));
 if((hi.x-lo.x+1)*(hi.y-lo.y+1)>4096)return; // Hint only; BVH remains complete.
 float area=hint_cross(b.xy-a.xy,c.xy-a.xy);if(area==0.f)return;
 for(int y=lo.y;y<=hi.y;y++)for(int x=lo.x;x<=hi.x;x++){
  float2 p=(float2)(x+.5f,y+.5f);
  float u=hint_cross(b.xy-p,c.xy-p)/area,v=hint_cross(c.xy-p,a.xy-p)/area,w=1.f-u-v;
  if(u<0.f||v<0.f||w<0.f)continue;
  float depth=1.f/(u/a.z+v/b.z+w/c.z);if(!isfinite(depth)||depth<=0.f)continue;
  ulong packed=((ulong)as_uint(depth)<<32)|(uint)i;
  atom_min((volatile __global ulong *)(pixels+y*size+x),packed);
 }
}
__kernel void hint_check(__global const double *vertices,__global const int *ids,__global const double4 *lines,
 __global const double *view,__global const ulong *pixels,__global int *blockers,int count,int size,double near){
 int sample=get_global_id(0);if(sample>=count||blockers[sample]>=0||blockers[sample]==-3||blockers[sample]==-5)return;
 double3 eye=vload3(0,view),forward=vload3(1,view),first=lines[2*sample].xyz,last=lines[2*sample+1].xyz;
 double3 da=first-eye,db=last-eye;double za=dot(da,forward),zb=dot(db,forward);if(za<=near||zb<=near)return;
 float3 projected=hint_project((first+last)*.5,view,size);
 if(any(!isfinite(projected))||projected.x<1||projected.x>=size-1||projected.y<1||projected.y>=size-1)return;
 int2 pixel=convert_int2(projected.xy);int previous=-1;
 for(int attempt=0;attempt<9;attempt++){
  int dx=attempt==0?0:((attempt-1)%3)-1,dy=attempt==0?0:((attempt-1)/3)-1;
  // Center first, then the eight neighbors (skip the duplicate center).
  if(attempt==5){dx=1;dy=1;}
  ulong packed=pixels[(pixel.y+dy)*size+pixel.x+dx];if(packed==~(ulong)0)continue;
  int triangle=(int)(uint)packed;if(triangle==previous)continue;previous=triangle;
  double3 a=vload3(ids[3*triangle],vertices),b=vload3(ids[3*triangle+1],vertices),c=vload3(ids[3*triangle+2],vertices);
  if(dot(a-eye,forward)<=near||dot(b-eye,forward)<=near||dot(c-eye,forward)<=near)continue;
  int uncertain=0;
  if(rt_inside_shadow(eye,da,near/za,a,b-a,c-a)&&rt_inside_shadow(eye,db,near/zb,a,b-a,c-a)&&
     rt_shadow_filtered(eye,first,last,a,b,c,&uncertain)){blockers[sample]=triangle;return;}
 }
}
#endif
#pragma OPENCL FP_CONTRACT ON
'''

def apply(gpu,points,count,result,camera,eye,forward):
    import numpy as np
    r=gpu.runtime
    if 'cl_khr_int64_extended_atomics' not in r.extensions:return False
    up=np.asarray(camera.get('up',[0,1,0]),np.float64)
    right=np.cross(forward,up);length=np.linalg.norm(right)
    if length<1e-10:return False
    right/=length;up=np.cross(right,forward)
    size=SIZE;scale=size*.5/np.tan(np.radians(float(camera.get('fov_y',60)))*.5)
    view=np.r_[eye,forward,right,up,scale]
    key=view.tobytes()
    if getattr(gpu,'hint_pixels',None) is None:
        required=size*size*8+view.nbytes
        if gpu.estimated_gpu_bytes+required>gpu.memory_budget:return False
        gpu.hint_pixels=gpu.buf(size*size*8);gpu.hint_view=gpu.buf(view)
        gpu.estimated_gpu_bytes+=required
        gpu.hint_key=None
    if gpu.hint_key!=key:
        r.write(gpu.hint_view,view)
        r.run('hint_clear',size*size,gpu.hint_pixels,size*size,local_size=64)
        r.run('hint_raster',gpu.triangle_count,gpu.vertices,gpu.triangles,gpu.hint_view,gpu.hint_pixels,
              gpu.triangle_count,size,float(camera.get('near',.1)),local_size=64)
        gpu.hint_key=key
    r.run('hint_check',count,gpu.vertices,gpu.triangles,points,gpu.hint_view,gpu.hint_pixels,result,
          count,size,float(camera.get('near',.1)),local_size=64)
    return True
