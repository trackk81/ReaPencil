#pragma once
namespace rpalpha {
using Intervals=std::vector<std::pair<double,double>>;
inline Intervals intervals(const Scene* scene,int64_t triangle,const double* uv){
 if(!scene||scene->lookup[triangle]<0)return {{0.,1.}};
 int row=scene->lookup[triangle];const Mask& mask=scene->regions[scene->masks[row]];bool wrap=scene->wrap[row]!=0;
 double dx=uv[2]-uv[0],dy=uv[3]-uv[1];
 if(dx*dx+dy*dy<1e-28)return contains(mask,uv[0],uv[1],wrap)?Intervals{{0.,1.}}:Intervals{};
 int x0=wrap?int(std::floor(std::min(uv[0],uv[2]))):0,y0=wrap?int(std::floor(std::min(uv[1],uv[3]))):0;
 int x1=wrap?std::max(x0+1,int(std::ceil(std::max(uv[0],uv[2])))):1,y1=wrap?std::max(y0+1,int(std::ceil(std::max(uv[1],uv[3])))):1;
 if(int64_t(x1-x0)*(y1-y0)>256)throw std::runtime_error("Alpha UV tiling exceeds 256 tiles");
 std::vector<double> cuts{0.,1.};std::vector<int32_t> edges;
 for(int ty=y0;ty<y1;++ty){
  double ymin=std::min(uv[1],uv[3])-ty,ymax=std::max(uv[1],uv[3])-ty;
  if(ymax<0||ymin>1)continue;
  int low=std::max(0,std::min(int(mask.bins)-1,int(std::floor(ymin*mask.bins)))),high=std::max(0,std::min(int(mask.bins)-1,int(std::floor(ymax*mask.bins))));
  edges.assign(mask.ids+mask.starts[low],mask.ids+mask.starts[high+1]);std::sort(edges.begin(),edges.end());edges.erase(std::unique(edges.begin(),edges.end()),edges.end());
  for(int tx=x0;tx<x1;++tx)for(auto id:edges){
   auto e=mask.edges+4*id;double qx=e[2]-e[0],qy=e[3]-e[1],px=e[0]+tx-uv[0],py=e[1]+ty-uv[1],den=dx*qy-dy*qx;
   if(std::abs(den)<=1e-16)continue;double t=(px*qy-py*qx)/den,u=(px*dy-py*dx)/den;
   if(t>0&&t<1&&u>=0&&u<=1)cuts.push_back(t);
  }
 }
 std::sort(cuts.begin(),cuts.end());cuts.erase(std::unique(cuts.begin(),cuts.end()),cuts.end());Intervals out;
 for(size_t i=1;i<cuts.size();++i){double lo=cuts[i-1],hi=cuts[i],mid=(lo+hi)*.5;
  if(hi-lo<=1e-12||!contains(mask,uv[0]+mid*dx,uv[1]+mid*dy,wrap))continue;
  if(!out.empty()&&lo<=out.back().second+1e-12)out.back().second=hi;else out.emplace_back(lo,hi);
 }return out;
}
}
// Output holds row index and the surviving interval. Capacity retry is exact;
// a short buffer never returns a partial result to Python.
API int64_t rp_alpha_trim(const rpalpha::Scene* first,const rpalpha::Scene* second,const int64_t* triangles,const double* uv,int64_t count,double* output,int64_t capacity) noexcept {
 try {int64_t used=0;for(int64_t i=0;i<count;++i){
  auto a=rpalpha::intervals(first,triangles[i*2],uv+i*8),b=rpalpha::intervals(second,triangles[i*2+1],uv+i*8+4);
  for(auto x:a)for(auto y:b){double lo=std::max(x.first,y.first),hi=std::min(x.second,y.second);if(hi-lo<=1e-12)continue;
   if(used<capacity){output[used*3]=double(i);output[used*3+1]=lo;output[used*3+2]=hi;}++used;
  }
 }return used;}catch(...){return -1;}
}
