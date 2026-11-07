"""OpenCL kernels for viewport geometry only. Offline rendering never imports this."""
from .gpu_predicates import SOURCE as _PREDICATES
SOURCE = _PREDICATES + r'''
#pragma OPENCL EXTENSION cl_khr_fp64 : enable
double3 point(__global const double *v, int i) { return vload3(i,v); }
int overlaps(float3 a, float3 b, float3 c, float3 d, double eps) {
    float e=convert_float_rtp(eps);
    return all(a <= nextafter(d+e,(float3)(INFINITY))) && all(c <= nextafter(b+e,(float3)(INFINITY)));
}
__kernel void triangles(__global const double *v, __global const int *ids,
                        __global float4 *lo, __global float4 *hi,
                        __global double4 *normals, __global double2 *metrics, int n, int base) {
    int i=get_global_id(0); if(i>=base) return;
    if(i>=n) {lo[base+i]=(float4)(INFINITY);hi[base+i]=(float4)(-INFINITY);return;}
    double3 a=point(v,ids[3*i]), b=point(v,ids[3*i+1]), c=point(v,ids[3*i+2]);
    // Outward rounding keeps the float broad phase conservative. Narrow-phase
    // normals, distances and endpoints retain double precision.
    lo[base+i]=(float4)(convert_float3_rtn(fmin(a,fmin(b,c))),i);hi[base+i]=(float4)(convert_float3_rtp(fmax(a,fmax(b,c))),i);
    double3 nn=cross(b-a,c-a); double area=length(nn);
    normals[i]=(double4)(area>0?nn/area:(double3)(0),area);
    metrics[i]=(double2)(area,fmax(length(b-a),fmax(length(c-b),length(a-c))));
}
__kernel void dirty_leaves(__global const int *owners,__global const int *changed,__global int *dirty,int n,int base) {
    int i=get_global_id(0);if(i<base)dirty[base+i]=i<n?changed[owners[i]]:0;
}
__kernel void refit(__global float4 *lo, __global float4 *hi, int start,__global int *dirty) {
    int work=get_global_id(0);if(work>=start)return;
    int i=start+work;lo[i]=fmin(lo[2*i],lo[2*i+1]);hi[i]=fmax(hi[2*i],hi[2*i+1]);
    dirty[i]=dirty[2*i]|dirty[2*i+1];
}
int section(double3 a, double3 b, double3 c, double3 distances, double eps, double3 *out) {
    double3 v[3]={a,b,c}; double d[3]={distances.x,distances.y,distances.z};int count=0;
    for(int k=0;k<3;k++) {
        int j=(k+1)%3;
        for(int mode=0;mode<2;mode++) {
            int valid=mode==0?d[k]==0.:((d[k]<0. && d[j]>0.)||(d[k]>0. && d[j]<0.));
            if(!valid) continue;
            double3 p=mode==0?v[k]:v[k]+(v[j]-v[k])*(d[k]/(d[k]-d[j]));
            int unique=1;for(int h=0;h<count;h++) if(length(p-out[h])<=eps) unique=0;
            if(unique) out[count++]=p;
        }
    }
    return count;
}
__kernel void candidates(__global const int *ids,__global const int *owners,__global const int *faces,
 __global const float4 *lo,__global const float4 *hi,__global const int *modes,
 __global int2 *pairs,volatile __global int *counter,int n,int base,double eps,int capacity,__global const int *styles) {
    int i=get_global_id(0);if(i>=n)return;
    int3 a=vload3(i,ids);int mi=owners[i];
    int collected[8],count=0;
    int stack[32],size=1;stack[0]=1;
    while(size) {
        int node=stack[--size];
        if(hi[node].w<=i)continue;
        if(!overlaps(lo[base+i].xyz,hi[base+i].xyz,lo[node].xyz,hi[node].xyz,eps))continue;
        if(node<base){stack[size++]=2*node+1;stack[size++]=2*node;continue;}
        int j=node-base;if(j<=i||j>=n)continue;
        int mj=owners[j],self=mi==mj;
        int si=styles[i],sj=styles[j];
        if(!(si>=0 && modes[2*si+self]) && !(sj>=0 && modes[2*sj+self]))continue;
        if(self) {
            int3 b=vload3(j,ids);
            if(faces[i]==faces[j]||any(a==b.x)||any(a==b.y)||any(a==b.z))continue;
        }
        collected[count++]=j;
        if(count==8) {
            int k=atomic_add(counter,8);
            if(k>=capacity)return;
            for(int q=0;q<8;q++)if(k+q<capacity)pairs[k+q]=(int2)(i,collected[q]);
            count=0;
        }
    }
    if(count) {
        int k=atomic_add(counter,count);
        if(k>=capacity)return;
        for(int q=0;q<count;q++)if(k+q<capacity)pairs[k+q]=(int2)(i,collected[q]);
    }
}
__kernel void intersections(__global const double *v, __global const int *ids,
 __global const int *owners, __global const int *faces,
 __global const float4 *lo, __global const float4 *hi,
 __global const double4 *normals, __global const double2 *metrics,
 __global const int *modes, __global double4 *output, __global int *output_owner, __global int2 *output_mesh_pair,
 volatile __global int *counter, int n, int base, double eps, int capacity, __global const int2 *pairs,__global const int *styles,int output_start) {
    int work=get_global_id(0);if(work>=n) return;
    int i=pairs[work].x,j=pairs[work].y;
    int ia=ids[3*i],ib=ids[3*i+1],ic=ids[3*i+2],mi=owners[i];
    double3 a=point(v,ia),b=point(v,ib),c=point(v,ic),na=normals[i].xyz;
    if(metrics[i].x<=eps*fmax(metrics[i].y,eps)) return;
    do {
        int mj=owners[j],self=mi==mj;
        int si=styles[i],sj=styles[j];
        int yesi=si>=0 && modes[2*si+self],yesj=sj>=0 && modes[2*sj+self];
        int own=yesi?(yesj?min(si,sj):si):(yesj?sj:-1);if(own<0)continue;
        int ja=ids[3*j],jb=ids[3*j+1],jc=ids[3*j+2];
        if(self && (faces[i]==faces[j] || ia==ja||ia==jb||ia==jc||ib==ja||ib==jb||ib==jc||ic==ja||ic==jb||ic==jc)) continue;
        if(metrics[j].x<=eps*fmax(metrics[j].y,eps)) continue;
        double3 x=point(v,ja),y=point(v,jb),z=point(v,jc),nb=normals[j].xyz;
        double3 da=(double3)(dot(a-x,nb),dot(b-x,nb),dot(c-x,nb));
        double3 db=(double3)(dot(x-a,na),dot(y-a,na),dot(z-a,na));
        if(all(da>eps)||all(da<-eps)||all(db>eps)||all(db<-eps)) continue;
        double3 dir=cross(na,nb);double len=length(dir);
        if(len<=1e-12 || (all(fabs(da)<=eps) && all(fabs(db)<=eps))) continue;
        da=(double3)(rt_orient(a,y,z,x),rt_orient(b,y,z,x),rt_orient(c,y,z,x));
        db=(double3)(rt_orient(x,b,c,a),rt_orient(y,b,c,a),rt_orient(z,b,c,a));
        if(all(da>0.)||all(da<0.)||all(db>0.)||all(db<0.))continue;
        dir/=len;
        double3 pa[6],pb[6];int ca=section(a,b,c,da,eps,pa),cb=section(x,y,z,db,eps,pb);
        if(!ca||!cb) continue;
        double3 origin=pa[0];double amin=INFINITY,amax=-INFINITY,bmin=INFINITY,bmax=-INFINITY;
        for(int k=0;k<ca;k++) {double t=dot(pa[k]-origin,dir);amin=fmin(amin,t);amax=fmax(amax,t);}
        for(int k=0;k<cb;k++) {double t=dot(pb[k]-origin,dir);bmin=fmin(bmin,t);bmax=fmax(bmax,t);}
        double low=fmax(amin,bmin),high=fmin(amax,bmax);if(high-low<=eps) continue;
        int index=output_start+atomic_inc(counter);if(index>=capacity) continue;
        output[2*index]=(double4)(origin+low*dir,1);output[2*index+1]=(double4)(origin+high*dir,1);
        output_owner[index]=own;
        output_mesh_pair[index]=(int2)(min(mi,mj),max(mi,mj));
    }while(0);
}
__kernel void preserve_cross(__global const double4 *old_points,__global const int *old_owners,__global const int2 *old_pairs,
 __global double4 *points,__global int *owners,__global int2 *pairs,__global const int *indices,int n) {
 int i=get_global_id(0);if(i>=n)return;int source=indices[i];
 points[2*i]=old_points[2*source];points[2*i+1]=old_points[2*source+1];owners[i]=old_owners[source];pairs[i]=old_pairs[source];
}
__kernel void polygon_normals(__global const double *v, __global const int *vertices,
 __global const int2 *ranges,__global double4 *normals,__global double4 *centers,int count) {
    int i=get_global_id(0);if(i>=count)return;int2 r=ranges[i];double3 n=(double3)(0),center=(double3)(0);
    for(int j=0;j<r.y;j++) {double3 a=point(v,vertices[r.x+j]);double3 b=point(v,vertices[r.x+(j+1)%r.y]);n+=cross(a,b);center+=a;}
    double len=length(n);normals[i]=(double4)(len>1e-12?n/len:(double3)(0,1,0),0);
    centers[i]=(double4)(center/r.y,0);
}
__kernel void clear_outline_counts(__global int *counts,int count) {
    int i=get_global_id(0);if(i<count)counts[i]=0;
}
#pragma OPENCL FP_CONTRACT OFF
__kernel void triangle_outline_counts(__global const double *v,__global const int *triangles,
 __global const int *edge_indices,__global const double *camera,volatile __global int *counts,int count) {
    int i=get_global_id(0);if(i>=count)return;
    double3 a=point(v,triangles[3*i]),b=point(v,triangles[3*i+1]),c=point(v,triangles[3*i+2]);
    double3 view=camera[6]>0?-vload3(1,camera):vload3(0,camera)-a;
    double3 u=b-a,w=c-a;
    double nx=u.y*w.z-u.z*w.y,ny=u.z*w.x-u.x*w.z,nz=u.x*w.y-u.y*w.x;
    if((nx*view.x+ny*view.y)+nz*view.z>0) {
        atomic_inc(counts+edge_indices[3*i]);atomic_inc(counts+edge_indices[3*i+1]);atomic_inc(counts+edge_indices[3*i+2]);
    }
}
#pragma OPENCL FP_CONTRACT ON
__kernel void diagonal_outlines(__global const double *v,__global const int2 *pairs,
 __global const int *faces,__global const int *mesh_owners,__global const int *counts,int edge_count,
 __global const int *features,__global const int *styles,__global double4 *output,
 __global int *output_owner,volatile __global int *counter,__global int2 *output_meta,int count) {
    int i=get_global_id(0);if(i>=count)return;int style=styles[faces[i]];
    if(style<0||!(features[style]&4)||counts[edge_count+i]!=1)return;
    int index=atomic_inc(counter);int2 p=pairs[i];
    output[2*index]=(double4)(point(v,p.x),1);output[2*index+1]=(double4)(point(v,p.y),1);
    output_owner[index]=style;output_meta[index]=(int2)(mesh_owners[i],4);
}
__kernel void edges(__global const double *v,__global const int2 *pairs,
 __global const int2 *ranges,__global const int *adjacent,__global const int *metadata,
 __global const int *owners,__global const double4 *normals,__global const double4 *centers,
 __global const int *features,__global const double2 *crease,__global const double *camera,
 __global double4 *output,__global int *output_owner,volatile __global int *counter,__global const int *styles,__global const int *selected_styles,__global int2 *output_meta,__global const int *outline_counts,int count) {
    int i=get_global_id(0);if(i>=count)return;int owner=2147483647;int2 r=ranges[i];
    for(int k=0;k<r.y;k++){int s=styles[adjacent[r.x+k]];if(s>=0)owner=min(owner,s);}
    if(selected_styles[i]>=0)owner=min(owner,selected_styles[i]);
    if(owner==2147483647)return;
    int enabled=features[owner];
    double min_dot=1;
    if(enabled&8) {
        double3 nn=normals[adjacent[r.x]].xyz;
        for(int k=0;k<r.y;k++)min_dot=fmin(min_dot,dot(nn,normals[adjacent[r.x+k]].xyz));
    }
    int selected=selected_styles[i];
    int meta=(metadata[i]&~64)|((selected==-3?(metadata[i]&64):(selected==owner?64:0)));
    int front_count=(enabled&4)?outline_counts[i]:0;
    int flags=(enabled&1) | ((r.y==1)?(enabled&2):0) | ((front_count>0&&front_count<r.y&&r.y>1)?(enabled&4):0)
        | ((r.y>1 && min_dot<crease[owner].x-1e-8 && min_dot>=crease[owner].y-1e-8)?(enabled&8):0) | (meta&enabled);
    if(!flags) return;
    int index=atomic_inc(counter);int2 p=pairs[i];
    output[2*index]=(double4)(point(v,p.x),1);output[2*index+1]=(double4)(point(v,p.y),1);output_owner[index]=owner;
    output_meta[index]=(int2)(owners[i],flags);
}
// Screen-side visibility queries for Merge Groups. Only nearest-hit ownership
// is returned; topology, intersections and final CPU rendering are unchanged.
__kernel void nearest_mesh(__global const double *v,__global const int *ids,
 __global const int *owners,__global const float4 *lo,__global const float4 *hi,
 __global const double4 *origins,__global const double4 *directions,
 __global int *result,int base,int n,double near,double far) {
    int q=get_global_id(0);if(q>=n)return;
    double3 origin=origins[q].xyz,dir=directions[q].xyz;
    double closest=far;int owner=-1,stack[32],size=1;stack[0]=1;
    while(size) {
        int node=stack[--size];if(hi[node].w<0)continue;double lower=near,upper=closest;
        for(int axis=0;axis<3;axis++) {
            double o=origin[axis],d=dir[axis];
            if(fabs(d)<1e-15) {if(o<lo[node][axis]||o>hi[node][axis])upper=-1;}
            else {double a=(lo[node][axis]-o)/d,b=(hi[node][axis]-o)/d;lower=fmax(lower,fmin(a,b));upper=fmin(upper,fmax(a,b));}
        }
        if(lower>upper)continue;
        if(node<base){stack[size++]=2*node;stack[size++]=2*node+1;continue;}
        int i=node-base;
        double3 a=point(v,ids[3*i]),e1=point(v,ids[3*i+1])-a,e2=point(v,ids[3*i+2])-a;
        double3 p=cross(dir,e2);double det=dot(e1,p);if(fabs(det)<1e-14)continue;
        double inv=1/det;double3 t=origin-a;double u=dot(t,p)*inv;if(u<0||u>1)continue;
        double3 c=cross(t,e1);double w=dot(dir,c)*inv;if(w<0||u+w>1)continue;
        double distance=dot(e2,c)*inv;
        if(distance>=near&&distance<closest){closest=distance;owner=owners[i];}
    }
    result[q]=owner;
}
'''

# Indexed variants share exactly the same predicates / output math. They only
# change which work items are visited after a subset of meshes deforms.
_a=SOURCE.index('__kernel void triangles(');_b=SOURCE.index('__kernel void dirty_leaves(',_a)
_tri=SOURCE[_a:_b].replace('void triangles(', 'void triangles_indexed(').replace(
    'int n, int base)', 'int n, int base,__global const int *work_ids,int work_count)').replace(
    'int i=get_global_id(0); if(i>=base) return;', 'int work=get_global_id(0);if(work>=work_count)return;int i=work_ids[work];')
_a=SOURCE.index('__kernel void polygon_normals(');_b=SOURCE.index('__kernel void clear_outline_counts(',_a)
_poly=SOURCE[_a:_b].replace('void polygon_normals(', 'void polygon_normals_indexed(').replace(
    'int count)', 'int count,__global const int *work_ids,int work_count)').replace(
    'int i=get_global_id(0);if(i>=count)return;', 'int work=get_global_id(0);if(work>=work_count)return;int i=work_ids[work];')
_a=SOURCE.index('__kernel void candidates(');_b=SOURCE.index('__kernel void intersections(',_a)
_candidates=SOURCE[_a:_b].replace('void candidates(', 'void candidates_indexed(').replace(
    '__global const int *styles)', '__global const int *styles,__global const int *work_ids,__global const int *changed,int work_count)').replace(
    'int i=get_global_id(0);if(i>=n)return;', 'int work=get_global_id(0);if(work>=work_count)return;int i=work_ids[work];').replace(
    'if(hi[node].w<=i)continue;', 'if(hi[node].w<0)continue;').replace(
    'if(j<=i||j>=n)continue;', 'if(j>=n||j==i||(changed[owners[j]]&&j<i))continue;').replace(
    '(int2)(i,collected[q])','(int2)(min(i,collected[q]),max(i,collected[q]))')
SOURCE+=_tri+_poly+_candidates
