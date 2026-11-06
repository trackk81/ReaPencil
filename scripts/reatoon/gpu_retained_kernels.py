"""Optional retained-display payloads; intersection predicates are unchanged."""
from .gpu_kernels import SOURCE as BASE
from .gpu_paged_kernels import SOURCE as PAGED

def payload(source,name,end):
    k=source[source.index('__kernel void '+name+'('):source.index(end,source.index('__kernel void '+name+'('))]
    k=k.replace('void '+name+'(', 'void retained_'+name+'(',1)
    brace=k.index('{');signature=k[:brace].rstrip()
    k=signature[:-1]+',__global float4 *outplanes) '+k[brace:]
    marker='output_mesh_pair[index]'
    start=k.index(marker);stop=k.index(';',start)+1
    k=k[:stop]+'\n        outplanes[2*index]=convert_float4((double4)(na,output_mesh_pair[index].x));outplanes[2*index+1]=convert_float4((double4)(nb,output_mesh_pair[index].y));'+k[stop:]
    return k

SOURCE=payload(BASE,'intersections','__kernel void preserve_cross(')+payload(PAGED,'page_intersections','__kernel void page_local_candidates(')
