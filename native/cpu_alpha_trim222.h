#pragma once
#include <stdexcept>
#include "cpu_alpha_intervals219.h"
#include "cpu_parallel222.h"
struct AlphaTrim222 {double* rows=nullptr;int64_t size=0;};
namespace rpalpha {
inline Intervals intervals222(const Scene* scene,int64_t triangle,const double* uv){
 if(!scene||scene->lookup[triangle]<0)return {{0.,1.}};
 int row=scene->lookup[triangle];const Mask& mask=scene->regions[scene->masks[row]];bool wrap=scene->wrap[row]!=0;
 double dx=uv[2]-uv[0],dy=uv[3]-uv[1];
 if(dx*dx+dy*dy<1e-28)return contains(mask,uv[0],uv[1],wrap)?Intervals{{0.,1.}}:Intervals{};
 double xmin=std::min(uv[0],uv[2]),xmax=std::max(uv[0],uv[2]),ymin0=std::min(uv[1],uv[3]),ymax0=std::max(uv[1],uv[3]);
 int x0=wrap?int(std::floor(xmin)):0,y0=wrap?int(std::floor(ymin0)):0;
 int x1=wrap?std::max(x0+1,int(std::ceil(xmax))):1,y1=wrap?std::max(y0+1,int(std::ceil(ymax0))):1;
 if(int64_t(x1-x0)*(y1-y0)>256)throw std::runtime_error("Alpha UV tiling exceeds 256 tiles");
 std::vector<double> cuts{0.,1.};
 double pad=64*std::numeric_limits<double>::epsilon()*std::max({1.,std::abs(xmin),std::abs(xmax),std::abs(double(x0)),std::abs(double(x1))});
 for(int ty=y0;ty<y1;++ty){
  double ymin=ymin0-ty,ymax=ymax0-ty;if(ymax<0||ymin>1)continue;
  int low=std::max(0,std::min(int(mask.bins)-1,int(std::floor(ymin*mask.bins)))),high=std::max(0,std::min(int(mask.bins)-1,int(std::floor(ymax*mask.bins))));
  for(int bin=low;bin<=high;++bin){double boundary=double(bin)/mask.bins;for(auto at=mask.starts[bin];at<mask.starts[bin+1];++at){
   auto e=mask.edges+4*mask.ids[at];
   // Each edge is stored in every overlapping Y bin. Visit only its first
   // bin in this query, avoiding a large allocation/sort of duplicate IDs.
   if(bin>low&&std::min(e[1],e[3])<boundary)continue;
   for(int tx=x0;tx<x1;++tx){
    // Conservative interval rejection; the original crossing arithmetic
    // below still decides every touching/overlapping boundary.
    if(std::max(e[0],e[2])+tx<xmin-pad||std::min(e[0],e[2])+tx>xmax+pad)continue;
    double qx=e[2]-e[0],qy=e[3]-e[1],px=e[0]+tx-uv[0],py=e[1]+ty-uv[1],den=dx*qy-dy*qx;
    if(std::abs(den)<=1e-16)continue;double t=(px*qy-py*qx)/den,u=(px*dy-py*dx)/den;
    if(t>0&&t<1&&u>=0&&u<=1)cuts.push_back(t);
   }
  }}
 }
 std::sort(cuts.begin(),cuts.end());cuts.erase(std::unique(cuts.begin(),cuts.end()),cuts.end());Intervals out;
 for(size_t i=1;i<cuts.size();++i){double lo=cuts[i-1],hi=cuts[i],mid=(lo+hi)*.5;
  if(hi-lo<=1e-12||!contains(mask,uv[0]+mid*dx,uv[1]+mid*dy,wrap))continue;
  if(!out.empty()&&lo<=out.back().second+1e-12)out.back().second=hi;else out.emplace_back(lo,hi);
 }return out;
}
}
// Every input row is independent. Retain input and interval order when joining
// workers; never return truncated intervals or repeat a capacity-size pass.
API int rp_alpha_trim222(const rpalpha::Scene* first,const rpalpha::Scene* second,
 const int64_t* triangles,const double* uv,int64_t count,AlphaTrim222* result) noexcept {
 try {
  *result={};unsigned workers=count>=256?std::min(12u,std::max(1u,std::thread::hardware_concurrency())):1;
  std::vector<std::vector<double>> parts(workers);std::vector<int> failed(workers,0);
  auto run=[&](unsigned worker){try {
   auto& out=parts[worker];int64_t begin=count*worker/workers,end=count*(worker+1)/workers;
   for(int64_t i=begin;i<end;++i){
    auto a=rpalpha::intervals222(first,triangles[i*2],uv+i*8);
    if(a.empty())continue;
    auto b=rpalpha::intervals222(second,triangles[i*2+1],uv+i*8+4);
    for(auto x:a)for(auto y:b){double lo=std::max(x.first,y.first),hi=std::min(x.second,y.second);
     if(hi-lo>1e-12)out.insert(out.end(),{double(i),lo,hi});}
   }
  }catch(...){failed[worker]=1;}};
  rp222::parallel(workers,run);size_t size=0;
  for(unsigned i=0;i<workers;++i){if(failed[i])return -1;size+=parts[i].size();}
  if(size){result->rows=new double[size];size_t cursor=0;for(auto& part:parts){std::copy(part.begin(),part.end(),result->rows+cursor);cursor+=part.size();}}
  result->size=int64_t(size/3);return 0;
 }catch(...){return -1;}
}
API void rp_alpha_trim222_free(double* rows) noexcept {delete[] rows;}

// Expand shared contours directly into their final bounded coordinate buffer.
// Keep the three-term barycentric accumulation order used by NumPy einsum.
API int rp_alpha_points222(const double* source,const double* bary,int64_t size,
 int64_t first,int64_t count,double* output) noexcept {
 try {
  if(size<=0||first<0||count<0)return -1;
  unsigned workers=count>=32768?std::min(12u,std::max(1u,std::thread::hardware_concurrency())):1;
  auto run=[&](unsigned worker){for(int64_t i=count*worker/workers;i<count*(worker+1)/workers;++i){
   int64_t at=first+i;auto p=source+(at/size)*9;auto b=bary+(at%size)*6;auto out=output+i*6;
   for(int side=0;side<2;++side)for(int axis=0;axis<3;++axis){
    double value=b[side*3]*p[axis];value+=b[side*3+1]*p[3+axis];value+=b[side*3+2]*p[6+axis];out[side*3+axis]=value;
   }
  }};
  rp222::parallel(workers,run);return 0;
 }catch(...){return -1;}
}

API int rp_alpha_grid222(const rpalpha::Mask* mask,int64_t size,uint8_t* grid) noexcept {
 try {
  unsigned workers=std::min(12u,std::max(1u,std::thread::hardware_concurrency()));
  std::vector<int> failed(workers,0);
  auto run=[&](unsigned worker){try{std::vector<double> crossings;
   for(int64_t y=size*worker/workers;y<size*(worker+1)/workers;++y){
    crossings.clear();double yy=(double(y)+.5)/size;int64_t bin=std::min(mask->bins-1,int64_t(yy*mask->bins));
    for(auto at=mask->starts[bin];at<mask->starts[bin+1];++at){auto e=mask->edges+4*mask->ids[at];
     if((e[1]>yy)!=(e[3]>yy))crossings.push_back(e[0]+(yy-e[1])*(e[2]-e[0])/(e[3]-e[1]));}
    std::sort(crossings.begin(),crossings.end());size_t at=0;
    for(int64_t x=0;x<size;++x){double xx=(double(x)+.5)/size;while(at<crossings.size()&&crossings[at]<=xx)++at;grid[y*size+x]=uint8_t(at%2);}
   }
  }catch(...){failed[worker]=1;}};
  rp222::parallel(workers,run);for(auto code:failed)if(code)return -1;
  // IDs are repeated across bins. Their maximum gives the contiguous source
  // edge count; every valid edge is present in at least one clamped bin.
  int64_t count=0;for(int64_t at=0;at<mask->starts[mask->bins];++at)count=std::max(count,int64_t(mask->ids[at])+1);
  for(int64_t i=0;i<count;++i){auto e=mask->edges+i*4;
   int64_t x0=std::max(int64_t(0),int64_t(std::floor(std::min(e[0],e[2])*size-1e-8))),x1=std::min(size-1,int64_t(std::floor(std::max(e[0],e[2])*size+1e-8)));
   int64_t y0=std::max(int64_t(0),int64_t(std::floor(std::min(e[1],e[3])*size-1e-8))),y1=std::min(size-1,int64_t(std::floor(std::max(e[1],e[3])*size+1e-8)));
   if(x1<x0)continue;for(int64_t y=y0;y<=y1;++y)std::fill(grid+y*size+x0,grid+y*size+x1+1,uint8_t(2));
  }
  return 0;
 }catch(...){return -1;}
}
