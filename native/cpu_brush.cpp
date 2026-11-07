// CPU profile rasterizer. Strict floating point; no Maya or GPU dependency.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <vector>
#include <thread>
#define API extern "C" __declspec(dllexport)
static double value(const double* lut,int n,double x) noexcept {
 if(x<=lut[0])return std::clamp(lut[1],0.,1.);
 if(x>=lut[2*n-2])return std::clamp(lut[2*n-1],0.,1.);
 int a=0,b=n-1;while(b-a>1){int m=(a+b)/2;if(lut[m*2]<=x)a=m;else b=m;}
 double t=(x-lut[a*2])/(lut[b*2]-lut[a*2]);
 return std::clamp(lut[a*2+1]+t*(lut[b*2+1]-lut[a*2+1]),0.,1.);
}
// Exact box average of a linear tent across a square subpixel footprint.
// The linear profile is inferred from controlled brush cross sections; this
// avoids losing narrow marks when their center misses every sample location.
static double positive_average(double t,double a,double b) noexcept {
 auto square=[](double x){return x>0?x*x:0.;};
 auto cube=[](double x){return x>0?x*x*x:0.;};
 if(a<b)std::swap(a,b);
 if(a<1e-12)return std::max(t,0.);
 if(t>=a+b)return t;
 if(t<=-a-b)return 0.;
 if(b<1e-3*a)return (square(t+a)-square(t-a))/(4*a);
 return (cube(t+a+b)-cube(t-a+b)-cube(t+a-b)+cube(t-a-b))/(24*a*b);
}
static double pencil_coverage(double radius,double distance,double a,double b) noexcept {
 if(distance-a-b>=radius)return 0.;
 if(radius>=1&&distance+a+b<=radius-1)return 1.;
 auto tent=[&](double r){return positive_average(distance+r,a,b)-2*positive_average(distance,a,b)+positive_average(distance-r,a,b);};
 return std::clamp(tent(radius)-(radius>1?tent(radius-1):0.),0.,1.);
}
// World-relative endpoints, with perspective-correct interpolation per fragment.
static double reference_distance(const double* r,double t) noexcept {
 t=std::clamp(t,0.,1.);double xyz[3];
 if(r[2])for(int k=0;k<3;++k)xyz[k]=r[3+k]+t*(r[6+k]-r[3+k]);
 else{double z=1/((1-t)/r[0]+t/r[1]);for(int k=0;k<3;++k)xyz[k]=z*((1-t)*r[3+k]/r[0]+t*r[6+k]/r[1]);}
 return std::hypot(xyz[0],xyz[1],xyz[2]);
}
static int profile_runs(float* image,int w,int h,int64_t stride,const double* runs,int64_t count,
 const double* original,double u0,double u1,double base,double smoothing,const double* wl,int nw,const double* al,int na,const double* depth_values=nullptr,const double* alpha_depth=nullptr,const double* width_depth=nullptr,const double* alpha_reference=nullptr,const double* width_reference=nullptr) noexcept {
 if(!image||!runs||!original||!wl||!al||w<=0||h<=0||nw<2||na<2||base<0)return -1;
 const double dx=original[2]-original[0],dy=original[3]-original[1],den=std::max(dx*dx+dy*dy,1e-30),radius=base*.5;
 for(int64_t k=0;k<count;++k){const double* p=runs+k*7;
  int x0=int(std::max(0.,std::floor(std::min(p[0],p[2])-radius-1)));
  int y0=int(std::max(0.,std::floor(std::min(p[1],p[3])-radius-1)));
  int x1=int(std::min(double(w-1),std::ceil(std::max(p[0],p[2])+radius+1)));
  int y1=int(std::min(double(h-1),std::ceil(std::max(p[1],p[3])+radius+1)));
  double vx=p[2]-p[0],vy=p[3]-p[1],rd=std::max(vx*vx+vy*vy,1e-30),length=std::sqrt(rd);
  for(int y=y0;y<=y1;++y){
   int left=x0,right=x1;
   if(std::abs(vy)>1e-20){
    double ta=(y+.5-radius-.5-p[1])/vy,tb=(y+.5+radius+.5-p[1])/vy;
    if(ta>tb)std::swap(ta,tb);
    if(tb<0||ta>1)continue;
    double xa=p[0]+std::clamp(ta,0.,1.)*vx,xb=p[0]+std::clamp(tb,0.,1.)*vx;
    left=std::max(left,int(std::floor(std::min(xa,xb)-radius-1)));
    right=std::min(right,int(std::ceil(std::max(xa,xb)+radius+1)));
   }
   for(int x=left;x<=right;++x){double px=x+.5,py=y+.5;
   double t=std::clamp(((px-p[0])*vx+(py-p[1])*vy)/rd,0.,1.);
   double cx=p[0]+t*vx,cy=p[1]+t*vy;
   double distance=std::hypot(px-cx,py-cy);if(distance>=radius+(smoothing>0?1.:.5))continue;
   // Project the pixel onto the full stroke, including beyond interior joins.
   // Clamping at each mesh edge would create alpha/width plateaus under caps.
   double ot=((px-original[0])*dx+(py-original[1])*dy)/den;
   double u=u0+(u1-u0)*ot,width=base*value(wl,nw,u);if(width<=0)continue;
   if(width_depth){double t=std::clamp(ot,0.,1.);
    double z=width_reference?reference_distance(width_reference,t):(width_depth[2]?width_depth[0]+t*(width_depth[1]-width_depth[0]):1/((1-t)/width_depth[0]+t/width_depth[1]));
    double q=std::clamp((z-width_depth[3])/(width_depth[4]-width_depth[3]),0.,1.);
    width*=width_depth[5]+q*(width_depth[6]-width_depth[5]);if(width<=0)continue;}
   double coverage;
   if(smoothing>0){
    double nx=-vy/length,ny=vx/length;
    bool startJoin=t==0&&u0>1e-10&&u0<1-1e-10&&std::hypot(p[0]-original[0],p[1]-original[1])<1e-8;
    bool endJoin=t==1&&u1>1e-10&&u1<1-1e-10&&std::hypot(p[2]-original[2],p[3]-original[3])<1e-8;
    if((t==0||t==1)&&!startJoin&&!endJoin&&distance>1e-15){nx=(px-cx)/distance;ny=(py-cy)/distance;}
    coverage=pencil_coverage(width*.5/smoothing,distance/smoothing,std::abs(nx)*.5/smoothing,std::abs(ny)*.5/smoothing);
   }else coverage=std::clamp(width*.5+.5-distance,0.,1.);
   coverage*=value(al,na,u);
   if(alpha_depth){double t=std::clamp(ot,0.,1.);
    double z=alpha_reference?reference_distance(alpha_reference,t):(alpha_depth[2]?alpha_depth[0]+t*(alpha_depth[1]-alpha_depth[0]):1/((1-t)/alpha_depth[0]+t/alpha_depth[1]));
    double q=std::clamp((z-alpha_depth[3])/(alpha_depth[4]-alpha_depth[3]),0.,1.);
    coverage*=alpha_depth[5]+q*(alpha_depth[6]-alpha_depth[5]);}
   float* out=image+int64_t(y)*stride+x*4;
   if(coverage>out[3]){
    if(depth_values){double t=std::clamp(ot,0.,1.),z=depth_values[4]?depth_values[0]+t*(depth_values[1]-depth_values[0]):1/((1-t)/depth_values[0]+t/depth_values[1]);
     double v=std::clamp(1-(z-depth_values[2])/(depth_values[3]-depth_values[2]),0.,1.);out[0]=out[1]=out[2]=float(v*coverage);
    }else{out[0]=float(p[4]*coverage);out[1]=float(p[5]*coverage);out[2]=float(p[6]*coverage);}out[3]=float(coverage);}
   }
  }
 }
 return 0;
}

API int rp_profile_runs(float* image,int w,int h,int64_t stride,const double* runs,int64_t count,const double* original,double u0,double u1,double base,double smoothing,const double* wl,int nw,const double* al,int na) noexcept {
 return profile_runs(image,w,h,stride,runs,count,original,u0,u1,base,smoothing,wl,nw,al,na);}
API int rp_profile_runs_depth(float* image,int w,int h,int64_t stride,const double* runs,int64_t count,const double* original,double u0,double u1,double base,double smoothing,const double* wl,int nw,const double* al,int na,const double* depth_values) noexcept {
 return profile_runs(image,w,h,stride,runs,count,original,u0,u1,base,smoothing,wl,nw,al,na,depth_values);}
API int rp_profile_runs_reduced(float* image,int w,int h,int64_t stride,const double* runs,int64_t count,const double* original,double u0,double u1,double base,double smoothing,const double* wl,int nw,const double* al,int na,const double* depth_values,const double* alpha_depth) noexcept {
 return profile_runs(image,w,h,stride,runs,count,original,u0,u1,base,smoothing,wl,nw,al,na,depth_values,alpha_depth);}
API int rp_profile_runs_depth_width(float* image,int w,int h,int64_t stride,const double* runs,int64_t count,const double* original,double u0,double u1,double base,double smoothing,const double* wl,int nw,const double* al,int na,const double* depth_values,const double* alpha_depth,const double* width_depth) noexcept {
 return profile_runs(image,w,h,stride,runs,count,original,u0,u1,base,smoothing,wl,nw,al,na,depth_values,alpha_depth,width_depth);}
API int rp_profile_runs_reference(float* image,int w,int h,int64_t stride,const double* runs,int64_t count,const double* original,double u0,double u1,double base,double smoothing,const double* wl,int nw,const double* al,int na,const double* depth_values,const double* alpha_depth,const double* width_depth,const double* alpha_reference,const double* width_reference) noexcept {
 return profile_runs(image,w,h,stride,runs,count,original,u0,u1,base,smoothing,wl,nw,al,na,depth_values,alpha_depth,width_depth,alpha_reference,width_reference);}

#include "cpu_visibility.h"
#include "cpu_profile_segments.h"
// Topology graph and profile direction in bulk; no coordinate welding.
#include <array>
#include <unordered_map>
API int rp_profile_coordinates(const double* points,const double* world,const int64_t* keys,const int64_t* vertices,const double* parameters,int64_t n,
 int w,int h,int ortho,double span,double focal,double* u) noexcept {
 try{
 struct Hash{size_t operator()(const std::array<int64_t,5>& a)const noexcept{size_t h=0;for(auto x:a)h^=std::hash<int64_t>{}(x)+0x9e3779b9+(h<<6)+(h>>2);return h;}};
 struct Adj{int64_t first=-1,second=-1;int count=0;};
 std::unordered_map<std::array<int64_t,5>,Adj,Hash> adjacency;adjacency.reserve(size_t(n));
 std::vector<double> xy(size_t(n)*4),lengths(size_t(n),0.);std::vector<int64_t> links(size_t(n)*2,-1);std::vector<uint8_t> used(size_t(n),0);
 for(int64_t i=0;i<n;++i){auto p=points+i*6;double fa=ortho?w/span:focal/p[2],fb=ortho?w/span:focal/p[5];auto q=xy.data()+i*4;
  q[0]=w/2.+p[0]*fa;q[1]=h/2.-p[1]*fa;q[2]=w/2.+p[3]*fb;q[3]=h/2.-p[4]*fb;lengths[i]=std::hypot(q[2]-q[0],q[3]-q[1]);
  if(vertices[i*2]<0||vertices[i*2+1]<0)continue;
  for(int s=0;s<2;++s){std::array<int64_t,5> key;std::copy(keys+i*4,keys+i*4+4,key.begin());key[4]=vertices[i*2+s];auto& a=adjacency[key];if(a.count==0)a.first=i*2+s;else if(a.count==1)a.second=i*2+s;++a.count;}
 }
 for(auto& item:adjacency){auto a=item.second;if(a.count!=2||a.first/2==a.second/2)continue;
  int64_t i=a.first/2,j=a.second/2;int si=int(a.first%2),sj=int(a.second%2);auto p=xy.data()+i*4;auto q=xy.data()+j*4;
  double x=p[(1-si)*2]-p[si*2],y=p[(1-si)*2+1]-p[si*2+1],xx=q[(1-sj)*2]-q[sj*2],yy=q[(1-sj)*2+1]-q[sj*2+1];
  double den=std::hypot(x,y)*std::hypot(xx,yy);
  if(den>1e-24){
   double turn=std::acos(std::clamp(double(float(-(x*xx+y*yy)/den)),-1.,1.))*180/3.14159265358979323846;
   if(turn<=parameters[i*3+1]+1e-8){links[a.first]=a.second;links[a.second]=a.first;}
  }
 }
 struct Edge{int64_t i;int from,to;};std::vector<Edge> chain,left;
 for(int64_t i=0;i<n;++i){if(used[i])continue;chain.clear();left.clear();used[i]=1;
  for(int side=0;side<2;++side){int64_t k=i;int end=side;
   while(links[k*2+end]>=0){int64_t next=links[k*2+end],j=next/2;int near=int(next%2),far=1-near;if(used[j])break;used[j]=1;
    if(side==0)left.push_back({j,far,near});else chain.push_back({j,near,far});k=j;end=far;
   }
  }
  std::vector<Edge> all;all.reserve(left.size()+chain.size()+1);for(auto it=left.rbegin();it!=left.rend();++it)all.push_back(*it);all.push_back({i,0,1});all.insert(all.end(),chain.begin(),chain.end());
  auto first=all.front(),last=all.back();double angle=double(float(parameters[i*3]*3.14159265358979323846/180));
  double cx=std::cos(angle),cy=std::sin(angle);
  bool closed=links[first.i*2+first.from]==last.i*2+last.to;
  bool reverse=false;
  if(closed){
   double area=0,mx=0,my=0;
   for(auto e:all){auto q=xy.data()+e.i*4;area+=q[e.from*2]*q[e.to*2+1]-q[e.to*2]*q[e.from*2+1];mx+=q[e.from*2];my+=q[e.from*2+1];}
   bool clockwise=parameters[i*3+2]==0;
   if((area>0)!=clockwise){std::reverse(all.begin(),all.end());for(auto& e:all)std::swap(e.from,e.to);}
   mx/=all.size();my/=all.size();size_t anchor=0;double best=INFINITY;
   // Independent deterministic seam rule. Rectangle behavior is replay-tested;
   // arbitrary loops and exact directional ties retain documented phase limits.
   for(size_t j=0;j<all.size();++j){auto q=xy.data()+all[j].i*4;double x=(q[0]+q[2])*.5-mx,y=(q[1]+q[3])*.5-my;
    double score=(x*cx+y*cy)*std::hypot(x,y);if(score<best){best=score;anchor=j;}}
   std::rotate(all.begin(),all.begin()+anchor,all.end());
  }else{
   double dx=xy[last.i*4+last.to*2]-xy[first.i*4+first.from*2],dy=xy[last.i*4+last.to*2+1]-xy[first.i*4+first.from*2+1];reverse=dx*cx+dy*cy<0;
  }
  double total=0;for(auto e:all)total+=lengths[e.i];double offset=0;total=std::max(total,1e-20);
  for(auto e:all){double lo=offset/total,hi=(offset+lengths[e.i])/total;u[e.i*2+e.from]=reverse?1-lo:lo;u[e.i*2+e.to]=reverse?1-hi:hi;offset+=lengths[e.i];}
 }
 return 0;
 }catch(...){return -1;}
}

#include "cpu_brush_blend.h"
