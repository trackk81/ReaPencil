#pragma once
// CPU-only, shared by depth raster and exact visibility. The same simplified
// contours used for line boundaries define the opaque region (including holes).
namespace rpalpha {
struct Mask {const double* edges;const int64_t* starts;const int32_t* ids;int64_t bins;const uint8_t* grid;int64_t size;};
struct Scene {const int32_t* lookup;const double* uv;const int32_t* masks;const uint8_t* wrap;const Mask* regions;};
inline bool contains(const Mask& m,double x,double y,bool wrap){
 if(wrap){x-=std::floor(x);y-=std::floor(y);}
 if(x<0||x>1||y<0||y>1)return false;
 if(m.grid){int gx=std::min(int(m.size)-1,int(x*m.size)),gy=std::min(int(m.size)-1,int(y*m.size));auto state=m.grid[int64_t(gy)*m.size+gx];if(state!=2)return state!=0;}
 int bin=std::min(int(m.bins)-1,std::max(0,int(y*m.bins)));bool inside=false;
 for(auto i=m.starts[bin];i<m.starts[bin+1];++i){auto e=m.edges+4*m.ids[i];
  double dx=e[2]-e[0],dy=e[3]-e[1],cross=dx*(y-e[1])-dy*(x-e[0]);
  if(std::abs(cross)<=1e-12*(std::abs(dx)+std::abs(dy))&&x>=std::min(e[0],e[2])-1e-12&&x<=std::max(e[0],e[2])+1e-12&&y>=std::min(e[1],e[3])-1e-12&&y<=std::max(e[1],e[3])+1e-12)return true;
  if((e[1]>y)!=(e[3]>y))if(e[0]+(y-e[1])*dx/dy>x)inside=!inside;
 }return inside;
}
inline bool opaque(const Scene* s,int64_t triangle,double u,double v){
 if(!s)return true;int32_t k=s->lookup[triangle];if(k<0)return true;
 auto p=s->uv+6*k;double a=1-u-v;
 return contains(s->regions[s->masks[k]],a*p[0]+u*p[2]+v*p[4],a*p[1]+u*p[3]+v*p[5],s->wrap[k]!=0);
}
}
