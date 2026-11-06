"""Bounded cross-page queries using exactly the existing triangle predicates."""
from .gpu_kernels import SOURCE as GEOMETRY

SOURCE=r'''
__kernel void page_gather_edges(__global const double4 *points,__global const int *owners,
 __global const int2 *meta,__global const int *indices,__global double4 *output,
 __global int *outowners,__global int2 *outmeta,int n){
 int i=get_global_id(0);if(i>=n)return;int j=indices[i];
 output[2*i]=points[2*j];output[2*i+1]=points[2*j+1];outowners[i]=owners[j];outmeta[i]=meta[j];
}
__kernel void page_candidates(__global const float4 *alo,__global const float4 *ahi,
 __global const float4 *blo,__global const float4 *bhi,__global const int *astyles,
 __global const int *bstyles,__global const int *modes,__global int2 *pairs,
 volatile __global int *counter,int abase,int bbase,int bn,int first,int count,
 int capacity,double eps) {
 int work=get_global_id(0);if(work>=count)return;int i=first+work;
 int stack[32],pending=1;stack[0]=1;
 while(pending){int node=stack[--pending];if(bhi[node].w<0)continue;
  if(!overlaps(alo[abase+i].xyz,ahi[abase+i].xyz,blo[node].xyz,bhi[node].xyz,eps))continue;
  if(node<bbase){stack[pending++]=2*node;stack[pending++]=2*node+1;continue;}
  int j=node-bbase;if(j>=bn)continue;
  int sa=astyles[i],sb=bstyles[j];
  if(!(sa>=0&&modes[2*sa])&&!(sb>=0&&modes[2*sb]))continue;
  int k=atomic_inc(counter);if(k<capacity)pairs[k]=(int2)(i,j);
 }
}
'''
start=GEOMETRY.index('__kernel void intersections(')
end=GEOMETRY.index('__kernel void preserve_cross(',start)
kernel=GEOMETRY[start:end].replace('void intersections(', 'void page_intersections(')
kernel=kernel.replace('int output_start)', '''int output_start,
 __global const double *bv,__global const int *bids,__global const int *bowners,
 __global const double4 *bnormals,__global const double2 *bmetrics,__global const int *bstyles)''')
kernel=kernel.replace('int mj=owners[j],self=mi==mj;', 'int mj=bowners[j],self=0;')
kernel=kernel.replace('sj=styles[j]', 'sj=bstyles[j]')
kernel=kernel.replace('int ja=ids[3*j],jb=ids[3*j+1],jc=ids[3*j+2];',
                      'int ja=bids[3*j],jb=bids[3*j+1],jc=bids[3*j+2];')
kernel=kernel.replace('metrics[j]', 'bmetrics[j]').replace('normals[j]', 'bnormals[j]')
kernel=kernel.replace('point(v,ja)','point(bv,ja)').replace('point(v,jb)','point(bv,jb)').replace('point(v,jc)','point(bv,jc)')
kernel=kernel.replace('(int2)(min(mi,mj),max(mi,mj))','(int2)(mi,mj)')
SOURCE+=kernel
start=GEOMETRY.index('__kernel void candidates(')
end=GEOMETRY.index('__kernel void intersections(',start)
SOURCE+=GEOMETRY[start:end].replace('void candidates(', 'void page_local_candidates(').replace(
    '__global const int *styles)', '__global const int *styles,int first,int count_work)').replace(
    'int i=get_global_id(0);if(i>=n)return;', 'int work=get_global_id(0);if(work>=count_work)return;int i=first+work;')
start=GEOMETRY.index('__kernel void nearest_mesh(')
end=GEOMETRY.index('\n}',start)+2
SOURCE+=GEOMETRY[start:end].replace('void nearest_mesh(', 'void page_nearest_mesh(').replace(
    'double near,double far)', 'double near,double far,__global double *depth)').replace(
    'result[q]=owner;', 'result[q]=owner;depth[q]=closest;')
