#pragma once
#include <array>
#include <map>
#include <cstring>
API int rp_alpha_edges222(const rpalpha::Scene* alpha,const int64_t* triangles,const int64_t* faces,
 const int64_t* pairs,const int64_t* owners,const int64_t* starts,const int64_t* counts,
 const int64_t* indices,int64_t count,const int64_t* map_order,const int64_t* map_triangles,
 const int64_t* begin,const int64_t* end,uint8_t* unmasked,AlphaTrim222* result) noexcept {
 try {
  *result={};std::map<std::array<uint64_t,5>,rpalpha::Intervals> cache;
  std::vector<double> out;std::vector<int64_t> covered;rpalpha::Intervals intervals;
  const int corners[3][2]={{0,1},{1,2},{2,0}};
  for(int64_t i=0;i<count;++i){
   auto edge=indices[i];unmasked[i]=0;covered.clear();intervals.clear();
   if(begin[i]==end[i]){unmasked[i]=1;continue;}
   for(auto slot=begin[i];slot<end[i];++slot)covered.push_back(faces[map_triangles[map_order[slot]/3]]);
   for(auto slot=starts[edge];slot<starts[edge]+counts[edge];++slot)
    if(std::find(covered.begin(),covered.end(),owners[slot])==covered.end()){unmasked[i]=1;break;}
   if(unmasked[i])continue;
   for(auto slot=begin[i];slot<end[i];++slot){
    auto entry=map_order[slot],triangle=map_triangles[entry/3];int row=alpha->lookup[triangle];
    int p=corners[entry%3][0],q=corners[entry%3][1];if(triangles[triangle*3+p]>triangles[triangle*3+q])std::swap(p,q);
    const auto* src=alpha->uv+row*6;double uv[4]={src[p*2],src[p*2+1],src[q*2],src[q*2+1]};
    std::array<uint64_t,5> key;std::memcpy(key.data(),uv,sizeof(uv));key[4]=uint64_t(alpha->masks[row])*2+uint64_t(alpha->wrap[row]!=0);
    auto found=cache.find(key);
    if(found==cache.end()){
     if(cache.size()>=4096)cache.erase(cache.begin());
     found=cache.emplace(key,rpalpha::intervals(alpha,triangle,uv)).first;
    }
    intervals.insert(intervals.end(),found->second.begin(),found->second.end());
   }
   std::sort(intervals.begin(),intervals.end());bool active=false;double lo=0,hi=0;
   for(auto interval:intervals){
    if(active&&interval.first<=hi+1e-12)hi=std::max(hi,interval.second);
    else {if(active)out.insert(out.end(),{double(edge),lo,hi});lo=interval.first;hi=interval.second;active=true;}
   }
   if(active)out.insert(out.end(),{double(edge),lo,hi});
  }
  if(!out.empty()){result->rows=new double[out.size()];std::copy(out.begin(),out.end(),result->rows);}
  result->size=int64_t(out.size()/3);return 0;
 }catch(...){return -1;}
}
