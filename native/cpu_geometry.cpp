// CPU-only bulk geometry kernels. No Maya calls, fast math, or shared scratch.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <numeric>
#include <vector>
#include <limits>
#include <thread>
#include <atomic>
#define API extern "C" __declspec(dllexport)
API int rp_facts(const double* v,const int64_t* tri,int64_t n,double* pos,double* low,double* high,double* norm,double* area,double* longest) noexcept {
 try {for(int64_t i=0;i<n;++i){
    double* p=pos+9*i;for(int j=0;j<3;++j)for(int a=0;a<3;++a)p[j*3+a]=v[tri[3*i+j]*3+a];
    double e[3],f[3],g[3],c[3];for(int a=0;a<3;++a){low[i*3+a]=std::min({p[a],p[3+a],p[6+a]});high[i*3+a]=std::max({p[a],p[3+a],p[6+a]});e[a]=p[3+a]-p[a];f[a]=p[6+a]-p[a];g[a]=p[6+a]-p[3+a];}
    c[0]=e[1]*f[2]-e[2]*f[1];c[1]=e[2]*f[0]-e[0]*f[2];c[2]=e[0]*f[1]-e[1]*f[0];
    area[i]=std::sqrt(c[0]*c[0]+c[1]*c[1]+c[2]*c[2]);for(int a=0;a<3;++a)norm[i*3+a]=area[i]>0?c[a]/area[i]:0;
    longest[i]=std::max({std::sqrt(e[0]*e[0]+e[1]*e[1]+e[2]*e[2]),std::sqrt(f[0]*f[0]+f[1]*f[1]+f[2]*f[2]),std::sqrt(g[0]*g[0]+g[1]*g[1]+g[2]*g[2])});
 }return 0;}catch(...){return -1;}
}
API int64_t rp_bvh(const double* lows,const double* highs,int64_t n,int64_t capacity,double* nl,double* nh,int64_t* children,int64_t* ranges,int64_t* order) noexcept {
 try {
    std::iota(order,order+n,0);std::fill(children,children+capacity*2,-1);std::fill(ranges,ranges+capacity*2,-1);
    struct Task{int64_t node,begin,end;int axes[3];int na;};std::vector<Task> stack;stack.push_back({0,0,n,{0,0,0},0});int64_t used=1;
    std::vector<double> centers(n*3);for(int64_t i=0;i<n*3;++i)centers[i]=(lows[i]+highs[i])*.5;
    while(!stack.empty()){
      Task t=stack.back();stack.pop_back();double cl[3],ch[3];
      for(int a=0;a<3;++a){nl[t.node*3+a]=cl[a]=std::numeric_limits<double>::infinity();nh[t.node*3+a]=ch[a]=-std::numeric_limits<double>::infinity();}
      for(int64_t j=t.begin;j<t.end;++j){auto i=order[j];for(int a=0;a<3;++a){nl[t.node*3+a]=std::min(nl[t.node*3+a],lows[i*3+a]);nh[t.node*3+a]=std::max(nh[t.node*3+a],highs[i*3+a]);cl[a]=std::min(cl[a],centers[i*3+a]);ch[a]=std::max(ch[a],centers[i*3+a]);}}
      auto less=[&](int64_t a,int64_t b){for(int k=0;k<t.na;++k){int ax=t.axes[k];double ca=centers[a*3+ax],cb=centers[b*3+ax];if(ca<cb)return true;if(ca>cb)return false;}return a<b;};
      if(t.end-t.begin<=16){if(t.na)std::sort(order+t.begin,order+t.end,less);ranges[t.node*2]=t.begin;ranges[t.node*2+1]=t.end;continue;}
      int axis=0;for(int a=1;a<3;++a)if(ch[a]-cl[a]>ch[axis]-cl[axis])axis=a;
      // A stable sort at each ancestor is exactly a lexicographic ordering
      // by the most recent distinct axes, then the original triangle ID.
      // Partition by that total order; only leaves need a full sort.
      int previous[3]={t.axes[0],t.axes[1],t.axes[2]},old=t.na;t.axes[0]=axis;t.na=1;
      for(int k=0;k<old;++k)if(previous[k]!=axis)t.axes[t.na++]=previous[k];
      std::nth_element(order+t.begin,order+t.begin+(t.end-t.begin)/2,order+t.end,less);
      auto left=used++,right=used++;if(used>capacity)return -1;auto mid=t.begin+(t.end-t.begin)/2;
      children[t.node*2]=left;children[t.node*2+1]=right;stack.push_back({right,mid,t.end,{t.axes[0],t.axes[1],t.axes[2]},t.na});stack.push_back({left,t.begin,mid,{t.axes[0],t.axes[1],t.axes[2]},t.na});
    }return used;
 }catch(...){return -1;}
}
API int64_t rp_edges(const double* v,const int64_t* flat,const int64_t* counts,int64_t nf,int64_t nc,const int64_t* mids,
 double* normals,double* centers,int64_t* pairs,int64_t* owners,int64_t* starts,int64_t* ec,double* dot,uint8_t* material) noexcept {
 try {
    std::vector<uint64_t> keys(nc);std::vector<int64_t> face(nc),order(nc);std::iota(order.begin(),order.end(),0);int64_t begin=0;
    for(int64_t f=0;f<nf;++f){
      double normal[3]={0,0,0},center[3]={0,0,0};
      for(int64_t j=0;j<counts[f];++j){auto k=begin+j;auto a=flat[k],b=flat[begin+(j+1)%counts[f]];const double* p=v+a*3;const double* q=v+b*3;
        normal[0]+=p[1]*q[2]-p[2]*q[1];normal[1]+=p[2]*q[0]-p[0]*q[2];normal[2]+=p[0]*q[1]-p[1]*q[0];
        for(int axis=0;axis<3;++axis)center[axis]+=p[axis];keys[k]=(uint64_t(std::min(a,b))<<32)|uint64_t(std::max(a,b));face[k]=f;
      }
      double length=std::sqrt(normal[0]*normal[0]+normal[1]*normal[1]+normal[2]*normal[2]);
      for(int a=0;a<3;++a){normals[f*3+a]=length>1e-12?normal[a]/length:(a==1?1.:0.);centers[f*3+a]=center[a]/counts[f];}begin+=counts[f];
    }
    std::stable_sort(order.begin(),order.end(),[&](int64_t a,int64_t b){return keys[a]<keys[b];});
    int64_t ne=0;
    for(int64_t j=0;j<nc;){int64_t end=j+1;auto key=keys[order[j]];while(end<nc&&keys[order[end]]==key)++end;
      pairs[ne*2]=int64_t(key>>32);pairs[ne*2+1]=int64_t(key&0xffffffffu);starts[ne]=j;ec[ne]=end-j;
      auto first=face[order[j]];double md=std::numeric_limits<double>::infinity();int64_t mi=mids[first],ma=mi;
      for(int64_t k=j;k<end;++k){auto f=face[order[k]];owners[k]=f;double d=normals[first*3]*normals[f*3]+normals[first*3+1]*normals[f*3+1]+normals[first*3+2]*normals[f*3+2];md=std::min(md,d);mi=std::min(mi,mids[f]);ma=std::max(ma,mids[f]);}
      dot[ne]=md;material[ne]=mi!=ma;++ne;j=end;
    }return ne;
 }catch(...){return -1;}
}

API int64_t rp_depth(const double* vertices,const int64_t* indices,int64_t n,double* depth,double* planes,void* owners,int owner_bytes,int64_t mesh_index,int w,int h,int ortho,double span,double focal,double nearz,double farz) noexcept {
 try {
    struct Tri{double ax,ay,bx,by,cx,cy,z[3],den,px,py,pc;int x0,y0,x1,y1;};
    std::vector<Tri> triangles;triangles.reserve(n);const int tile=64,tw=(w+tile-1)/tile,th=(h+tile-1)/tile;
    std::vector<std::vector<int64_t>> bins(tw*th);int64_t count=0;
    for(int64_t t=0;t<n;++t){
      double a[8][3],b[8][3];double (*first)[3]=a,(*second)[3]=b;
      for(int i=0;i<3;++i)for(int c=0;c<3;++c)first[i][c]=vertices[indices[t*3+i]*3+c];int size=3;
      bool inside=true;for(int i=0;i<3;++i)inside&=first[i][2]>=nearz&&first[i][2]<=farz;
      if(!inside)for(int clip=0;clip<2;++clip){double plane=clip==0?nearz:farz,sign=clip==0?1.:-1.;int out=0;if(!size)break;
        int ai=size-1;bool ina=sign*(first[ai][2]-plane)>=0;
        for(int bi=0;bi<size;++bi){bool inb=sign*(first[bi][2]-plane)>=0;
          if(ina!=inb){double f=(plane-first[ai][2])/(first[bi][2]-first[ai][2]);for(int c=0;c<3;++c)second[out][c]=first[ai][c]+(first[bi][c]-first[ai][c])*f;++out;}
          if(inb){for(int c=0;c<3;++c)second[out][c]=first[bi][c];++out;}ai=bi;ina=inb;
        }std::swap(first,second);size=out;
      }
      for(int fan=1;fan<size-1;++fan){++count;Tri tr{};double xy[3][2];
        for(int i=0;i<3;++i){int q=i==0?0:fan+i-1;tr.z[i]=first[q][2];double f=ortho?w/span:focal/tr.z[i];xy[i][0]=w/2.+first[q][0]*f;xy[i][1]=h/2.-first[q][1]*f;}
        tr.ax=xy[0][0];tr.ay=xy[0][1];tr.bx=xy[1][0];tr.by=xy[1][1];tr.cx=xy[2][0];tr.cy=xy[2][1];
        if(!(std::isfinite(tr.ax)&&std::isfinite(tr.ay)&&std::isfinite(tr.bx)&&std::isfinite(tr.by)&&std::isfinite(tr.cx)&&std::isfinite(tr.cy)))continue;
        double x0=std::max(std::floor(std::min({tr.ax,tr.bx,tr.cx})),0.),x1=std::min(std::ceil(std::max({tr.ax,tr.bx,tr.cx})),double(w-1));
        double y0=std::max(std::floor(std::min({tr.ay,tr.by,tr.cy})),0.),y1=std::min(std::ceil(std::max({tr.ay,tr.by,tr.cy})),double(h-1));
        if(x0>x1||y0>y1)continue;tr.x0=int(x0);tr.x1=int(x1);tr.y0=int(y0);tr.y1=int(y1);
        tr.den=(tr.by-tr.cy)*(tr.ax-tr.cx)+(tr.cx-tr.bx)*(tr.ay-tr.cy);if(std::abs(tr.den)<1e-12)continue;
        double va=ortho?tr.z[0]:1./tr.z[0],vb=ortho?tr.z[1]:1./tr.z[1],vc=ortho?tr.z[2]:1./tr.z[2];
        tr.px=((va-vc)*(tr.by-tr.cy)+(vb-vc)*(tr.cy-tr.ay))/tr.den;
        tr.py=((va-vc)*(tr.cx-tr.bx)+(vb-vc)*(tr.ax-tr.cx))/tr.den;tr.pc=vc-tr.px*tr.cx-tr.py*tr.cy;
        int64_t id=triangles.size();triangles.push_back(tr);
        for(int by=tr.y0/tile;by<=tr.y1/tile;++by)for(int bx=tr.x0/tile;bx<=tr.x1/tile;++bx)bins[by*tw+bx].push_back(id);
      }
    }
    std::atomic<int> next{0};auto run=[&](){for(;;){int bin=next.fetch_add(1,std::memory_order_relaxed);if(bin>=int(bins.size()))break;
      int ox=(bin%tw)*tile,oy=(bin/tw)*tile;
      for(auto id:bins[bin]){const Tri& t=triangles[id];int x0=std::max(t.x0,ox),x1=std::min(t.x1,ox+tile-1),y0=std::max(t.y0,oy),y1=std::min(t.y1,oy+tile-1);
        for(int y=y0;y<=y1;++y)for(int x=x0;x<=x1;++x){double xx=x+.5,yy=y+.5;
          double u=((t.by-t.cy)*(xx-t.cx)+(t.cx-t.bx)*(yy-t.cy))/t.den;
          double v=((t.cy-t.ay)*(xx-t.cx)+(t.ax-t.cx)*(yy-t.cy))/t.den;double k=1-u-v;
          if(u< -1e-8||v< -1e-8||k< -1e-8)continue;double z;
          if(ortho)z=u*t.z[0]+v*t.z[1]+k*t.z[2];else{double inv=u/t.z[0]+v/t.z[1]+k/t.z[2];if(inv<=0)continue;z=1./inv;}
          int64_t p=int64_t(y)*w+x;if(z<depth[p]){depth[p]=z;planes[p*3]=t.px;planes[p*3+1]=t.py;planes[p*3+2]=t.pc;if(owner_bytes==4)static_cast<int32_t*>(owners)[p]=int32_t(mesh_index);else if(owner_bytes==8)static_cast<int64_t*>(owners)[p]=mesh_index;}
        }
      }
    }};
    unsigned workers=n>=30000?std::min(8u,std::max(1u,std::thread::hardware_concurrency())):1;
    std::vector<std::thread> threads;try{for(unsigned i=1;i<workers;++i)threads.emplace_back(run);}catch(...){for(auto& thread:threads)thread.join();throw;}run();for(auto& thread:threads)thread.join();return count;
 }catch(...){return -1;}
}

#include "cpu_intersections.h"

#include "cpu_visibility.h"
