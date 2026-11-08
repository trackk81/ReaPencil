"""Generate a reviewed same-predicate CPU segment specialization from111 source."""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
s=(R/'native/cpu_visibility.h').read_text(encoding='utf8')
start=s.index('static int segment_range(');end=s.index('// Disjoint row bands',start)
reference=s[start:end]
loop=reference.index(' for(int64_t index=0;index<n;++index)')
projection_end=reference.index('bool owns=',loop)
projection=reference[loop:projection_end]
guard='if(xmax<=xmin||ymax<=ymin||ymax<=rowlo||ymin>=rowhi)continue;'
assert projection.endswith(guard)
project=projection[:-len(guard)]+'if(xmax<=xmin||ymax<=ymin)continue;\n out.push_back({index,a[2],b[2],px,py,dx,dy,lo,hi,xmin,ymin,xmax,ymax});\n }\n'
prepared=''' for(auto slot:ids){const auto& item=projected[slot];int64_t index=item.index;double width=widths[index];
 double a[3]={0,0,item.az},b[3]={0,0,item.bz},px=item.px,py=item.py,dx=item.dx,dy=item.dy,lo=item.lo,hi=item.hi;
 int xmin=item.xmin,ymin=item.ymin,xmax=item.xmax,ymax=item.ymax;
 int band_begin=std::max(0,rowlo-ymin),band_end=std::min(ymax-ymin,rowhi-ymin);
'''
special=reference[:loop]+prepared+reference[projection_end:]
special=special.replace('segment_range(', 'segment_range159(const std::vector<Projected159>& projected,const std::vector<size_t>& ids,',1)
special=special.replace('edge.assign(int64_t(ymax-ymin)*(xmax-xmin)*4,0)','edge.assign(int64_t(band_end-band_begin)*(xmax-xmin)*4,0)')
special=special.replace('rpvis::stroke(edge.data(),','stroke_band159(edge.data(),band_begin,band_end,')
special=special.replace('edge.data()+(int64_t(y)*(xmax-xmin)+x)*4','edge.data()+(int64_t(y-band_begin)*(xmax-xmin)+x)*4')
occlusion=s[s.index('bool occluded('):s.index('void stroke(float*')]
triangle=occlusion[occlusion.index(' double ex='):occlusion.index(' }}}return false;')]
triangle_helper='static bool triangle_occludes159(const double* o,const double* d,double nearz,double farz,const double* t){\n'+triangle.replace('continue;','return false;')+' return false;\n}\n'
occlusion=occlusion.replace(triangle,' if(triangle_occludes159(o,d,nearz,farz,t)){cache.triangle=t;cache.node=node;return true;}\n')
occlusion=occlusion.replace('bool occluded(', 'static bool occluded159(').replace('const Context& c)', 'const rpvis::Context& c,Hit159& cache)')
occlusion=occlusion.replace(' double farz=limit-256*epsilon*magnitude;',' double farz=limit-256*epsilon*magnitude;\n if(cache.triangle&&rpvis::box(o,d,c.low+cache.node*3,c.high+cache.node*3,nearz,farz)&&triangle_occludes159(o,d,nearz,farz,cache.triangle))return true;')
occlusion=occlusion.replace('if(!box(', 'if(!rpvis::box(')
occlusion=('struct Hit159 {const double* triangle=nullptr;int64_t node=0;};\n'+triangle_helper+occlusion).replace('*epsilon','*rpvis::epsilon')
occlusion=occlusion.replace('))return true;\n for(int64_t root=', ')){++profile159.cache_hits;return true;}\n ++profile159.ray_trees;for(int64_t root=')
special=special.replace('std::vector<float> edge;', '''std::vector<float> edge;
 // A previous triangle is only a hint: each current ray still passes the
 // original AABB and robust triangle predicates. Hash collisions are safe.
 // Bound each active worker to 4 MiB, independent of frame dimensions.
 std::vector<Hit159> hit_hints;size_t hint_mask=0;
 if(context){size_t cap=1;while(cap<size_t(rowhi-rowlo)*size_t(w)&&cap<262144)cap*=2;hit_hints.resize(cap);hint_mask=cap-1;}
''')
special=special.replace('rpvis::occluded(origin,direction,nearz,z,*context)','occluded159(origin,direction,nearz,z,*context,hit_hints[size_t(pi)&hint_mask])')
special=special.replace('for(int k=0;k<count;++k){double','for(int k=0;k<count;++k){double')
special=special.replace(' int ix=std::min', ''' // Vector records belong to one band. Other bands need only samples whose
 // capsule can touch their pixels; use the original sample arithmetic and
 // an extra pixel margin so this rejection cannot trim coverage.
 if(!owns){double sy159=py+t0*dy,ey159=py+t1*dy,pad159=width*ss/2+2;
  if(std::max(sy159,ey159)+pad159<rowlo||std::min(sy159,ey159)-pad159>rowhi)continue;}
 ++profile159.samples;
 int ix=std::min''')
special=special.replace('if(run)record();if(touched){','if(run)record();if(touched){profile159.composite_pixels+=int64_t(band_end-band_begin)*(xmax-xmin);')
stroke=s[s.index('void stroke(float*'):s.index('\n}\nAPI void rp_stroke')]
stroke=stroke.replace('void stroke(float* layer,','void stroke_band159(float* layer,int first,int last,',1)
stroke=stroke.replace(' double vx=',' y0=std::max(y0,first);y1=std::min(y1,last-1);\n double vx=')
stroke=stroke.replace('layer+y*stride+x*4','layer+(y-first)*stride+x*4')
stroke=stroke.replace(' double vx=', ' if(x1>=x0&&y1>=y0)profile159.stroke_pixels+=int64_t(x1-x0+1)*(y1-y0+1);++profile159.strokes;\n double vx=')
stroke=stroke.replace('double dist=std::hypot(x+.5-(ax+t*vx),y+.5-(ay+t*vy)),alpha=std::min(std::max(radius+.5-dist,0.),1.);', '''double ex=x+.5-(ax+t*vx),ey=y+.5-(ay+t*vy),q=ex*ex+ey*ey;
 double outer=radius+.5,inner=radius-.5,alpha;
 // Avoid hypot only well beyond a clamp boundary. Fractional coverage keeps
 // the original hypot and subtraction, including all near-threshold cases.
 if(q>outer*outer*(1+64*rpvis::epsilon))alpha=0.;
 else if(inner>=0&&q<inner*inner*(1-64*rpvis::epsilon))alpha=1.;
 else alpha=std::min(std::max(radius+.5-std::hypot(ex,ey),0.),1.);''')
stroke=stroke.replace('int first,int last,', 'int first,int last,int* left,int* right,')
stroke=stroke.replace('if(alpha>p[3]){', 'if(alpha>p[3]){left[y-first]=std::min(left[y-first],x);right[y-first]=std::max(right[y-first],x+1);')
special=special.replace('std::vector<float> edge;', 'std::vector<float> edge;std::vector<int> left,right;')
special=special.replace('touched=true;', 'left.assign(band_end-band_begin,xmax-xmin);right.assign(band_end-band_begin,0);touched=true;')
special=special.replace('edge.data(),band_begin,band_end,', 'edge.data(),band_begin,band_end,left.data(),right.data(),')
special=special.replace('profile159.composite_pixels+=int64_t(band_end-band_begin)*(xmax-xmin);', '')
special=special.replace('for(int x=0;x<xmax-xmin;++x){auto e=', 'for(int x=(profile159.composite_pixels+=std::max(0,right[y-band_begin]-left[y-band_begin]),left[y-band_begin]);x<right[y-band_begin];++x){auto e=')
wrapper=s[s.index('API int rp_segments('):]
wrapper=wrapper.replace('API int rp_segments(', 'API int rp_segments159(',1)
wrapper=wrapper.replace('try{Rows parts(workers);','''try{Rows parts(workers);
  auto timer159=std::chrono::steady_clock::now();
  std::vector<Profile159> profiles159(workers);
  std::vector<Projected159> projected;projected.reserve(size_t(std::min(n,int64_t(262144))));
  project159(points,widths,enabled,n,w,h,ss,ortho,span,focal,nearz,farz,projected);
  std::vector<std::vector<size_t>> bins(workers);
  for(size_t j=0;j<projected.size();++j)for(unsigned i=0;i<workers;++i)
   if(projected[j].ymax>int(i*h/workers)&&projected[j].ymin<int((i+1)*h/workers))bins[i].push_back(j);
''')
wrapper=wrapper.replace('segment_range(points,','segment_range159(projected,bins[i],points,')
wrapper=wrapper.replace('std::vector<int> codes(workers);','double project_seconds159=std::chrono::duration<double>(std::chrono::steady_clock::now()-timer159).count();timer159=std::chrono::steady_clock::now();\n  std::vector<int> codes(workers);')
wrapper=wrapper.replace('auto run=[&](unsigned i){codes[i]=','auto run=[&](unsigned i){profile159={};codes[i]=')
wrapper=wrapper.replace('int((i+1)*h/workers));};','int((i+1)*h/workers));profiles159[i]=profile159;};')
wrapper=wrapper.replace('  *result={};int64_t size=0;', '''  std::fill(last_profile159,last_profile159+9,0.);last_profile159[0]=project_seconds159;last_profile159[1]=std::chrono::duration<double>(std::chrono::steady_clock::now()-timer159).count();last_profile159[8]=double(projected.size());
  for(auto& p:profiles159){last_profile159[2]+=p.samples;last_profile159[3]+=p.strokes;last_profile159[4]+=p.stroke_pixels;last_profile159[5]+=p.composite_pixels;last_profile159[6]+=p.ray_trees;last_profile159[7]+=p.cache_hits;}
  *result={};int64_t size=0;''')
# Many smaller independent bands keep dense portions of a city from leaving
# most workers idle. A band still owns its pixels and preserves painter order.
wrapper=wrapper.replace('try{Rows parts(workers);', 'unsigned bands=workers>1?std::min(32u,unsigned(h)):1;\n try{Rows parts(bands);')
wrapper=wrapper.replace('profiles159(workers)', 'profiles159(bands)').replace('bins(workers)', 'bins(bands)').replace('codes(workers)', 'codes(bands)')
wrapper=wrapper.replace('for(size_t j=0;j<projected.size();++j)for(unsigned i=0;i<workers;++i)\n   if(projected[j].ymax>int(i*h/workers)&&projected[j].ymin<int((i+1)*h/workers))bins[i].push_back(j);', '''for(size_t j=0;j<projected.size();++j){
   unsigned begin=unsigned(std::max(0,projected[j].ymin))*bands/h;
   unsigned end=std::min(bands,1+unsigned(std::max(0,projected[j].ymax))*bands/h);
   for(unsigned i=begin;i<end;++i)if(projected[j].ymax>int(i*h/bands)&&projected[j].ymin<int((i+1)*h/bands))bins[i].push_back(j);
  }''')
wrapper=wrapper.replace('int(i*h/workers),int((i+1)*h/workers)', 'int(i*h/bands),int((i+1)*h/bands)')
wrapper=wrapper.replace('auto run=[&](unsigned i)', 'auto band=[&](unsigned i)')
wrapper=wrapper.replace('  try{for(unsigned i=1;i<workers;', '''  std::atomic<unsigned> next159{0};auto run=[&](unsigned){for(;;){unsigned i=next159.fetch_add(1);if(i>=bands)break;band(i);}};
  try{for(unsigned i=1;i<workers;''')
wrapper=wrapper.replace('size=0;for(unsigned i=0;i<workers;', 'size=0;for(unsigned i=0;i<bands;')
out='''// CPU159: stable screen-band bins and bounded per-band scratch.
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
'''+project+'}\n'+occlusion+stroke+'\n'+special+wrapper+'\nAPI void rp_segments159_free(double* rows) noexcept {delete[] rows;}\nAPI void rp_segments159_stats(double* out) noexcept {std::copy(last_profile159,last_profile159+9,out);}\n'
out+='''
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
'''
(R/'native/cpu_segments159.cpp').write_text(out,encoding='utf8')
