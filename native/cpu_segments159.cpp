// CPU159: stable screen-band bins and bounded per-band scratch.
// CPU111 predicates, projection arithmetic and painter order are preserved.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <numeric>
#include <vector>
#include <limits>
#include <thread>
#include <chrono>
#include <atomic>
#define API extern "C" __declspec(dllexport)
#include "cpu_visibility.h"
struct Projected159 {int64_t index;double az,bz,px,py,dx,dy,lo,hi;int xmin,ymin,xmax,ymax;};
struct Profile159 {uint64_t samples=0,strokes=0,stroke_pixels=0,composite_pixels=0,ray_trees=0,cache_hits=0;};
thread_local Profile159 profile159;thread_local double last_profile159[9]={};
static void project159(const double* points,const double* widths,const uint8_t* enabled,int64_t n,int w,int h,int ss,int ortho,double span,double focal,double nearz,double farz,std::vector<Projected159>& out){
 for(int64_t index=0;index<n;++index){double width=widths[index];if(width<=0||!enabled[index])continue;auto p=points+index*6;double lo=0,hi=1,dz=p[5]-p[2];
 if(std::abs(dz)<1e-14){if(p[2]<nearz||p[2]>farz)continue;}else{double t0=(nearz-p[2])/dz,t1=(farz-p[2])/dz;lo=std::max(lo,std::min(t0,t1));hi=std::min(hi,std::max(t0,t1));if(lo>hi)continue;}
 double a[3],b[3];for(int k=0;k<3;++k){if(std::abs(dz)<1e-14){a[k]=p[k];b[k]=p[3+k];}else{double delta=p[3+k]-p[k];a[k]=p[k]+delta*lo;b[k]=p[k]+delta*hi;}}
 double fa=ortho?w/span:focal/a[2],fb=ortho?w/span:focal/b[2],px=w/2.+a[0]*fa,py=h/2.-a[1]*fa,qx=w/2.+b[0]*fb,qy=h/2.-b[1]*fb,dx=qx-px,dy=qy-py,margin=width*ss/2+1;lo=0;hi=1;bool reject=false;
 for(int clip=0;clip<4;++clip){double ca,cb;if(clip==0){ca=-dx;cb=px+margin;}else if(clip==1){ca=dx;cb=w+margin-px;}else if(clip==2){ca=-dy;cb=py+margin;}else{ca=dy;cb=h+margin-py;}
 if(std::abs(ca)<1e-14){if(cb<0){reject=true;break;}}else if(ca<0)lo=std::max(lo,cb/ca);else hi=std::min(hi,cb/ca);if(lo>hi){reject=true;break;}}
 if(reject)continue;
 int xmin=int(std::max(std::floor(std::min(px+lo*dx,px+hi*dx)-margin),0.)),ymin=int(std::max(std::floor(std::min(py+lo*dy,py+hi*dy)-margin),0.)),xmax=int(std::min(std::ceil(std::max(px+lo*dx,px+hi*dx)+margin),double(w))),ymax=int(std::min(std::ceil(std::max(py+lo*dy,py+hi*dy)+margin),double(h)));
 if(xmax<=xmin||ymax<=ymin)continue;
 out.push_back({index,a[2],b[2],px,py,dx,dy,lo,hi,xmin,ymin,xmax,ymax});
 }
}
struct Hit159 {const double* triangle=nullptr;int64_t node=0;};
static bool triangle_occludes159(const double* o,const double* d,double nearz,double farz,const double* t){
 double ex=t[3]-t[0],ey=t[4]-t[1],ez=t[5]-t[2],fx=t[6]-t[0],fy=t[7]-t[1],fz=t[8]-t[2];
 double dx=d[0],dy=d[1],dz=d[2],hx=dy*fz-dz*fy,hy=dz*fx-dx*fz,hz=dx*fy-dy*fx,det=ex*hx+ey*hy+ez*hz;if(det==0)return false;
 double sx=o[0]-t[0],sy=o[1]-t[1],sz=o[2]-t[2],u=(sx*hx+sy*hy+sz*hz)/det;if(u<0||u>1)return false;
 double qx=sy*ez-sz*ey,qy=sz*ex-sx*ez,qz=sx*ey-sy*ex,v=(dx*qx+dy*qy+dz*qz)/det;if(v<0||u+v>1)return false;
 double distance=(fx*qx+fy*qy+fz*qz)/det,dp=0,np=0;
 dp+=std::abs(ex)*(std::abs(dy*fz)+std::abs(dz*fy));dp+=std::abs(ey)*(std::abs(dz*fx)+std::abs(dx*fz));dp+=std::abs(ez)*(std::abs(dx*fy)+std::abs(dy*fx));
 np+=std::abs(fx)*(std::abs(sy*ez)+std::abs(sz*ey));np+=std::abs(fy)*(std::abs(sz*ex)+std::abs(sx*ez));np+=std::abs(fz)*(std::abs(sx*ey)+std::abs(sy*ex));
 double de=64*rpvis::epsilon*dp,den=std::abs(det)-de;if(den<=0)return false;double error=(64*rpvis::epsilon*np+std::abs(distance)*de)/den;
 if(nearz<=distance&&distance+error<farz)return true;
 return false;
}
static bool occluded159(const double* o,const double* d,double nearz,double limit,const rpvis::Context& c,Hit159& cache){
 // A balanced int64-indexed tree cannot exceed 64 levels.
 int64_t stack[128];double magnitude=std::max({1.,std::abs(o[0]),std::abs(o[1]),std::abs(o[2]),std::max({std::abs(d[0]),std::abs(d[1]),std::abs(d[2])})*std::abs(limit)});
 double farz=limit-256*rpvis::epsilon*magnitude;
 if(cache.triangle&&rpvis::box(o,d,c.low+cache.node*3,c.high+cache.node*3,nearz,farz)&&triangle_occludes159(o,d,nearz,farz,cache.triangle)){++profile159.cache_hits;return true;}
 ++profile159.ray_trees;for(int64_t root=0;root<c.nr;++root){int pending=1;stack[0]=c.roots[root];while(pending){auto node=stack[--pending];if(!rpvis::box(o,d,c.low+node*3,c.high+node*3,nearz,farz))continue;
 if(c.child[node*2]>=0){stack[pending++]=c.child[node*2];stack[pending++]=c.child[node*2+1];continue;}
 for(auto slot=c.ranges[node*2];slot<c.ranges[node*2+1];++slot){auto t=c.tri+c.order[slot]*9;
 if(triangle_occludes159(o,d,nearz,farz,t)){cache.triangle=t;cache.node=node;return true;}
 }}}return false;
}
void stroke_band159(float* layer,int first,int last,int* left,int* right,int w,int h,int64_t stride,double ax,double ay,double bx,double by,double width,const double* color){
 if(width<=0)return;double radius=width/2;
 int x0=int(std::max(std::floor(std::min(ax,bx)-radius-1),0.)),y0=int(std::max(std::floor(std::min(ay,by)-radius-1),0.));
 int x1=int(std::min(std::ceil(std::max(ax,bx)+radius+1),double(w-1))),y1=int(std::min(std::ceil(std::max(ay,by)+radius+1),double(h-1)));
 y0=std::max(y0,first);y1=std::min(y1,last-1);
 if(x1>=x0&&y1>=y0)profile159.stroke_pixels+=int64_t(x1-x0+1)*(y1-y0+1);++profile159.strokes;
 double vx=bx-ax,vy=by-ay,den=std::max(vx*vx+vy*vy,1e-15);
 for(int y=y0;y<=y1;++y)for(int x=x0;x<=x1;++x){double t=((x+.5-ax)*vx+(y+.5-ay)*vy)/den;t=std::min(std::max(t,0.),1.);
 double ex=x+.5-(ax+t*vx),ey=y+.5-(ay+t*vy),q=ex*ex+ey*ey;
 double outer=radius+.5,inner=radius-.5,alpha;
 // Avoid hypot only well beyond a clamp boundary. Fractional coverage keeps
 // the original hypot and subtraction, including all near-threshold cases.
 if(q>outer*outer*(1+64*rpvis::epsilon))alpha=0.;
 else if(inner>=0&&q<inner*inner*(1-64*rpvis::epsilon))alpha=1.;
 else alpha=std::min(std::max(radius+.5-std::hypot(ex,ey),0.),1.);auto p=layer+(y-first)*stride+x*4;
 if(alpha>p[3]){left[y-first]=std::min(left[y-first],x);right[y-first]=std::max(right[y-first],x+1);for(int k=0;k<3;++k)p[k]=float(color[k]*alpha);p[3]=float(alpha);}}
}
static int segment_range159(const std::vector<Projected159>& projected,const std::vector<size_t>& ids,const double* points,const double* widths,const double* biases,const double* colors,const uint8_t* only,const uint8_t* enabled,int64_t n,const double* depth,const double* planes,float* visible,int w,int h,int ss,int ortho,double span,double focal,double nearz,double farz,const rpvis::Context* context,const double* eye,const double* basis,SegmentResult* result,int rowlo,int rowhi) noexcept {
 try{*result={};std::vector<double> records;std::vector<float> edge;std::vector<int> left,right;
 // A previous triangle is only a hint: each current ray still passes the
 // original AABB and robust triangle predicates. Hash collisions are safe.
 // Bound each active worker to 4 MiB, independent of frame dimensions.
 std::vector<Hit159> hit_hints;size_t hint_mask=0;
 if(context){size_t cap=1;while(cap<size_t(rowhi-rowlo)*size_t(w)&&cap<262144)cap*=2;hit_hints.resize(cap);hint_mask=cap-1;}

 for(auto slot:ids){const auto& item=projected[slot];int64_t index=item.index;double width=widths[index];
 double a[3]={0,0,item.az},b[3]={0,0,item.bz},px=item.px,py=item.py,dx=item.dx,dy=item.dy,lo=item.lo,hi=item.hi;
 int xmin=item.xmin,ymin=item.ymin,xmax=item.xmax,ymax=item.ymax;
 int band_begin=std::max(0,rowlo-ymin),band_end=std::min(ymax-ymin,rowhi-ymin);
bool owns=ymin>=rowlo&&ymin<rowhi;bool touched=false;double length=std::sqrt(dx*dx+dy*dy);int count=std::max(1,int(std::ceil(length*(hi-lo)*1.5)));double step=(hi-lo)/count;bool run=false;double ax=0,ay=0,bx=0,by=0;
 auto record=[&](){if(owns)records.insert(records.end(),{double(index),ax,ay,bx,by});};
 for(int k=0;k<count;++k){double t0=lo+k*step,t1=k+1==count?hi:lo+(k+1)*step,mid=(t0+t1)*.5,x=px+mid*dx,y=py+mid*dy,z=ortho?a[2]+mid*(b[2]-a[2]):1/((1-mid)/a[2]+mid/b[2]);
 // Vector records belong to one band. Other bands need only samples whose
 // capsule can touch their pixels; use the original sample arithmetic and
 // an extra pixel margin so this rejection cannot trim coverage.
 if(!owns){double sy159=py+t0*dy,ey159=py+t1*dy,pad159=width*ss/2+2;
  if(std::max(sy159,ey159)+pad159<rowlo||std::min(sy159,ey159)-pad159>rowhi)continue;}
 ++profile159.samples;
 int ix=std::min(std::max(int(std::floor(x)),0),w-1),iy=std::min(std::max(int(std::floor(y)),0),h-1);auto pi=int64_t(iy)*w+ix;double value=planes[pi*3]*x+planes[pi*3+1]*y+planes[pi*3+2],surface=ortho?value:(value>0?1/value:INFINITY);if(!std::isfinite(depth[pi]))surface=INFINITY;
 bool front=z<=surface+biases[index]*std::max(1.,z);
 if(context&&front&&z>surface+256*rpvis::epsilon*std::max(1.,std::abs(z))){double rx=(x-w/2.)/(ortho?w/span:focal),ry=-(y-h/2.)/(ortho?w/span:focal),origin[3],direction[3];
 for(int axis=0;axis<3;++axis){if(ortho){origin[axis]=eye[axis]+rx*basis[axis]+ry*basis[3+axis];direction[axis]=basis[6+axis];}else{origin[axis]=eye[axis];direction[axis]=rx*basis[axis]+ry*basis[3+axis]+basis[6+axis];}}
 if(owns)++result->checked;if(occluded159(origin,direction,nearz,z,*context,hit_hints[size_t(pi)&hint_mask])){if(owns)++result->hidden;front=false;}}
 if(enabled[index]&2)front=!front;
 if(!front){if(run){record();run=false;}continue;}
 double sx=px+t0*dx,sy=py+t0*dy,ex=px+t1*dx,ey=py+t1*dy;
 if(!only[index]){if(!touched){edge.assign(int64_t(band_end-band_begin)*(xmax-xmin)*4,0);left.assign(band_end-band_begin,xmax-xmin);right.assign(band_end-band_begin,0);touched=true;}stroke_band159(edge.data(),band_begin,band_end,left.data(),right.data(),xmax-xmin,ymax-ymin,int64_t(xmax-xmin)*4,sx-xmin,sy-ymin,ex-xmin,ey-ymin,width*ss,colors+index*3);}
 if(!run){ax=sx/ss;ay=sy/ss;run=true;}bx=ex/ss;by=ey/ss;}
 if(run)record();if(touched){for(int y=std::max(0,rowlo-ymin);y<std::min(ymax-ymin,rowhi-ymin);++y)for(int x=(profile159.composite_pixels+=std::max(0,right[y-band_begin]-left[y-band_begin]),left[y-band_begin]);x<right[y-band_begin];++x){auto e=edge.data()+(int64_t(y-band_begin)*(xmax-xmin)+x)*4;auto v=visible+(int64_t(y+ymin)*w+x+xmin)*4;float inv=1.f-e[3];for(int c=0;c<4;++c){float product=float(v[c]*inv);v[c]=float(e[c]+product);}}}
 }
 result->size=records.size()/5;if(!records.empty()){result->rows=new double[records.size()];std::copy(records.begin(),records.end(),result->rows);}return 0;
 }catch(...){return -1;}
}

API int rp_segments159(const double* points,const double* widths,const double* biases,const double* colors,const uint8_t* only,const uint8_t* enabled,int64_t n,const double* depth,const double* planes,float* visible,int w,int h,int ss,int ortho,double span,double focal,double nearz,double farz,const rpvis::Context* context,const double* eye,const double* basis,SegmentResult* result) noexcept {
 unsigned workers=n>=10000?std::min(8u,std::max(1u,std::thread::hardware_concurrency())):1;
 struct Rows {std::vector<SegmentResult> data;Rows(unsigned n):data(n){}~Rows(){for(auto& r:data)delete[] r.rows;}};
 unsigned bands=workers>1?std::min(32u,unsigned(h)):1;
 try{Rows parts(bands);
  auto timer159=std::chrono::steady_clock::now();
  std::vector<Profile159> profiles159(bands);
  std::vector<Projected159> projected;projected.reserve(size_t(std::min(n,int64_t(262144))));
  project159(points,widths,enabled,n,w,h,ss,ortho,span,focal,nearz,farz,projected);
  std::vector<std::vector<size_t>> bins(bands);
  for(size_t j=0;j<projected.size();++j){
   unsigned begin=unsigned(std::max(0,projected[j].ymin))*bands/h;
   unsigned end=std::min(bands,1+unsigned(std::max(0,projected[j].ymax))*bands/h);
   for(unsigned i=begin;i<end;++i)if(projected[j].ymax>int(i*h/bands)&&projected[j].ymin<int((i+1)*h/bands))bins[i].push_back(j);
  }

  double project_seconds159=std::chrono::duration<double>(std::chrono::steady_clock::now()-timer159).count();timer159=std::chrono::steady_clock::now();
  std::vector<int> codes(bands);std::vector<std::thread> threads;
  auto band=[&](unsigned i){profile159={};codes[i]=segment_range159(projected,bins[i],points,widths,biases,colors,only,enabled,n,depth,planes,visible,w,h,ss,ortho,span,focal,nearz,farz,context,eye,basis,&parts.data[i],int(i*h/bands),int((i+1)*h/bands));profiles159[i]=profile159;};
  std::atomic<unsigned> next159{0};auto run=[&](unsigned){for(;;){unsigned i=next159.fetch_add(1);if(i>=bands)break;band(i);}};
  try{for(unsigned i=1;i<workers;++i)threads.emplace_back(run,i);}catch(...){for(auto& t:threads)t.join();throw;}run(0);for(auto& t:threads)t.join();
  std::fill(last_profile159,last_profile159+9,0.);last_profile159[0]=project_seconds159;last_profile159[1]=std::chrono::duration<double>(std::chrono::steady_clock::now()-timer159).count();last_profile159[8]=double(projected.size());
  for(auto& p:profiles159){last_profile159[2]+=p.samples;last_profile159[3]+=p.strokes;last_profile159[4]+=p.stroke_pixels;last_profile159[5]+=p.composite_pixels;last_profile159[6]+=p.ray_trees;last_profile159[7]+=p.cache_hits;}
  *result={};int64_t size=0;for(unsigned i=0;i<bands;++i){if(codes[i])return -1;size+=parts.data[i].size;result->checked+=parts.data[i].checked;result->hidden+=parts.data[i].hidden;}
  struct Row {double value[5];};std::vector<Row> rows;rows.reserve(size);
  for(auto& r:parts.data)for(int64_t i=0;i<r.size;++i){Row row;std::copy(r.rows+i*5,r.rows+i*5+5,row.value);rows.push_back(row);}
  std::stable_sort(rows.begin(),rows.end(),[](const Row& a,const Row& b){return a.value[0]<b.value[0];});
  if(size){result->rows=new double[size*5];for(int64_t i=0;i<size;++i)std::copy(rows[i].value,rows[i].value+5,result->rows+i*5);}result->size=size;return 0;
 }catch(...){return -1;}
}

API void rp_segments159_free(double* rows) noexcept {delete[] rows;}
API void rp_segments159_stats(double* out) noexcept {std::copy(last_profile159,last_profile159+9,out);}

// An inactive triangle certifies every point on each of its three exact edges.
// Do not extrapolate this proof to unmatched polygon edges or other vertices.
API int rp_edge_mask159(const int64_t* pairs,int64_t np,const int64_t* tri,int64_t nt,const uint8_t* active,uint8_t* keep) noexcept {
 try {
  std::vector<std::pair<uint64_t,int64_t>> keys;keys.reserve(size_t(np));
  auto code=[](int64_t a,int64_t b){if(a>b)std::swap(a,b);return (uint64_t(a)<<32)|uint64_t(b);};
  for(int64_t i=0;i<np;++i){keep[i]=1;keys.emplace_back(code(pairs[i*2],pairs[i*2+1]),i);}
  std::sort(keys.begin(),keys.end());
  for(int64_t i=0;i<nt;++i)if(!active[i])for(int edge=0;edge<3;++edge){
   auto wanted=code(tri[i*3+edge],tri[i*3+(edge+1)%3]);
   auto p=std::lower_bound(keys.begin(),keys.end(),std::make_pair(wanted,int64_t(0)));
   for(;p!=keys.end()&&p->first==wanted;++p)keep[p->second]=0;
  }
  return 0;
 }catch(...){return -1;}
}
