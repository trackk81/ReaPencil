// Strict CPU equivalents of the conservative visibility and capsule kernels.
namespace rpvis {
constexpr double epsilon=std::numeric_limits<double>::epsilon();
struct Context {const int64_t *roots,*child,*ranges,*order;const double *low,*high,*tri;int64_t nr;};
bool box(const double* o,const double* d,const double* low,const double* high,double nearz,double farz){
 for(int a=0;a<3;++a){if(d[a]==0){if(o[a]<low[a]||o[a]>high[a])return false;}
 else{double x=(low[a]-o[a])/d[a],y=(high[a]-o[a])/d[a];nearz=std::max(nearz,std::min(x,y));farz=std::min(farz,std::max(x,y));if(nearz>farz)return false;}}return true;
}
bool occluded(const double* o,const double* d,double nearz,double limit,const Context& c){
 // A balanced int64-indexed tree cannot exceed 64 levels.
 int64_t stack[128];double magnitude=std::max({1.,std::abs(o[0]),std::abs(o[1]),std::abs(o[2]),std::max({std::abs(d[0]),std::abs(d[1]),std::abs(d[2])})*std::abs(limit)});
 double farz=limit-256*epsilon*magnitude;
 for(int64_t root=0;root<c.nr;++root){int pending=1;stack[0]=c.roots[root];while(pending){auto node=stack[--pending];if(!box(o,d,c.low+node*3,c.high+node*3,nearz,farz))continue;
 if(c.child[node*2]>=0){stack[pending++]=c.child[node*2];stack[pending++]=c.child[node*2+1];continue;}
 for(auto slot=c.ranges[node*2];slot<c.ranges[node*2+1];++slot){auto t=c.tri+c.order[slot]*9;
 double ex=t[3]-t[0],ey=t[4]-t[1],ez=t[5]-t[2],fx=t[6]-t[0],fy=t[7]-t[1],fz=t[8]-t[2];
 double dx=d[0],dy=d[1],dz=d[2],hx=dy*fz-dz*fy,hy=dz*fx-dx*fz,hz=dx*fy-dy*fx,det=ex*hx+ey*hy+ez*hz;if(det==0)continue;
 double sx=o[0]-t[0],sy=o[1]-t[1],sz=o[2]-t[2],u=(sx*hx+sy*hy+sz*hz)/det;if(u<0||u>1)continue;
 double qx=sy*ez-sz*ey,qy=sz*ex-sx*ez,qz=sx*ey-sy*ex,v=(dx*qx+dy*qy+dz*qz)/det;if(v<0||u+v>1)continue;
 double distance=(fx*qx+fy*qy+fz*qz)/det,dp=0,np=0;
 dp+=std::abs(ex)*(std::abs(dy*fz)+std::abs(dz*fy));dp+=std::abs(ey)*(std::abs(dz*fx)+std::abs(dx*fz));dp+=std::abs(ez)*(std::abs(dx*fy)+std::abs(dy*fx));
 np+=std::abs(fx)*(std::abs(sy*ez)+std::abs(sz*ey));np+=std::abs(fy)*(std::abs(sz*ex)+std::abs(sx*ez));np+=std::abs(fz)*(std::abs(sx*ey)+std::abs(sy*ex));
 double de=64*epsilon*dp,den=std::abs(det)-de;if(den<=0)continue;double error=(64*epsilon*np+std::abs(distance)*de)/den;
 if(nearz<=distance&&distance+error<farz)return true;
 }}}return false;
}
void stroke(float* layer,int w,int h,int64_t stride,double ax,double ay,double bx,double by,double width,const double* color){
 if(width<=0)return;double radius=width/2;
 int x0=int(std::max(std::floor(std::min(ax,bx)-radius-1),0.)),y0=int(std::max(std::floor(std::min(ay,by)-radius-1),0.));
 int x1=int(std::min(std::ceil(std::max(ax,bx)+radius+1),double(w-1))),y1=int(std::min(std::ceil(std::max(ay,by)+radius+1),double(h-1)));
 double vx=bx-ax,vy=by-ay,den=std::max(vx*vx+vy*vy,1e-15);
 for(int y=y0;y<=y1;++y)for(int x=x0;x<=x1;++x){double t=((x+.5-ax)*vx+(y+.5-ay)*vy)/den;t=std::min(std::max(t,0.),1.);
 double dist=std::hypot(x+.5-(ax+t*vx),y+.5-(ay+t*vy)),alpha=std::min(std::max(radius+.5-dist,0.),1.);auto p=layer+y*stride+x*4;
 if(alpha>p[3]){for(int k=0;k<3;++k)p[k]=float(color[k]*alpha);p[3]=float(alpha);}}
}
}
API void rp_stroke(float* out,int w,int h,int64_t stride,const double* a,const double* b,double width,const double* color) noexcept {rpvis::stroke(out,w,h,stride,a[0],a[1],b[0],b[1],width,color);}
template<class F> static void independent_rows(int height,int64_t pixels,F run) noexcept {
 if(pixels<1000000){run(0,height);return;}
 std::vector<std::thread> threads;
 try{threads.reserve(3);for(int i=1;i<4;++i)threads.emplace_back(run,i*height/4,(i+1)*height/4);run(0,height/4);for(auto& t:threads)t.join();}
 catch(...){for(auto& t:threads)if(t.joinable())t.join();run(0,height);}
}
API void rp_down(const float* in,float* out,int w,int h,int c,int scale) noexcept {
 auto run=[&](int begin,int end){for(int y=begin;y<end;++y)for(int x=0;x<w/scale;++x)for(int k=0;k<c;++k){float value=0;for(int dy=0;dy<scale;++dy)for(int dx=0;dx<scale;++dx)value=float(value+in[((int64_t(y*scale+dy)*w+x*scale+dx)*c)+k]);out[(int64_t(y)*(w/scale)+x)*c+k]=float(double(value)/(scale*scale));}};independent_rows(h/scale,int64_t(w)*h,run);
}
API void rp_active(const int64_t* child,const int64_t* ranges,const int64_t* order,const uint8_t* tri,uint8_t* nodes,int64_t n) noexcept {
 for(int64_t i=n;i-->0;){bool active=false;if(child[i*2]>=0)active=nodes[child[i*2]]||nodes[child[i*2+1]];else for(auto j=ranges[i*2];j<ranges[i*2+1];++j)if(tri[order[j]]){active=true;break;}nodes[i]=active;}
}
API void rp_surface(const double* depth,const double* planes,double* out,int w,int h,int ortho,double margin) noexcept {
 auto run=[&](int begin,int end){for(int y=begin;y<end;++y){double y0=y==0?-margin:double(y),y1=y==h-1?h+margin:double(y+1);for(int x=0;x<w;++x){auto i=int64_t(y)*w+x;out[i]=INFINITY;if(!std::isfinite(depth[i]))continue;
 double x0=x==0?-margin:double(x),x1=x==w-1?w+margin:double(x+1),a=planes[i*3],b=planes[i*3+1],c=planes[i*3+2];if(!(std::isfinite(a)&&std::isfinite(b)&&std::isfinite(c)))continue;
 double guard=64*rpvis::epsilon*(std::abs(a)*std::max(std::abs(x0),std::abs(x1))+std::abs(b)*std::max(std::abs(y0),std::abs(y1))+std::abs(c)+1);
 if(ortho)out[i]=a*(a>=0?x1:x0)+b*(b>=0?y1:y0)+c+guard;
 else{double minimum=a*(a>=0?x0:x1)+b*(b>=0?y0:y1)+c-guard;if(minimum>0)out[i]=1/minimum+guard;}}};};independent_rows(h,int64_t(w)*h,run);
}
API void rp_mask(const double* v,const int64_t* tris,int64_t n,const double* bounds,uint8_t* mask,int64_t* counts,int w,int h,int ortho,double span,double focal,double nearz,double farz,double bias,double margin,double tolerance) noexcept {
 for(int k=0;k<4;++k)counts[k]=0;
 for(int64_t i=0;i<n;++i){auto t=tris+i*3;mask[i]=1;double z0=v[t[0]*3+2],z1=v[t[1]*3+2],z2=v[t[2]*3+2],low=std::min({z0,z1,z2}),high=std::max({z0,z1,z2});
 double guard=10*tolerance+1e-8*std::max({1.,std::abs(low),std::abs(high)});if(!(std::isfinite(low)&&std::isfinite(high))){++counts[0];continue;}
 if(high<nearz-guard||low>farz+guard){mask[i]=0;++counts[1];continue;}if(low<=nearz+guard||high>=farz-guard){++counts[0];continue;}
 double xmin=INFINITY,ymin=INFINITY,xmax=-INFINITY,ymax=-INFINITY;bool valid=true;
 for(int k=0;k<3;++k){const double* p=v+t[k]*3;double f=ortho?w/span:focal/p[2],x=w/2.+p[0]*f,y=h/2.-p[1]*f;if(!(std::isfinite(x)&&std::isfinite(y))){valid=false;break;}xmin=std::min(xmin,x);xmax=std::max(xmax,x);ymin=std::min(ymin,y);ymax=std::max(ymax,y);}
 if(!valid){++counts[0];continue;}
 double padding=1+guard*(ortho?w/span:focal/low)*(1+std::max({std::abs(xmin),std::abs(xmax),std::abs(ymin),std::abs(ymax)})/std::max(focal,1.));xmin-=padding;ymin-=padding;xmax+=padding;ymax+=padding;
 if(xmax< -margin||xmin>w+margin||ymax< -margin||ymin>h+margin){mask[i]=0;++counts[2];continue;}
 int x0=int(std::min(std::max(std::floor(xmin),0.),double(w-1))),x1=int(std::min(std::max(std::floor(xmax),0.),double(w-1))),y0=int(std::min(std::max(std::floor(ymin),0.),double(h-1))),y1=int(std::min(std::max(std::floor(ymax),0.),double(h-1)));
 double nearest=low-guard-bias*std::max(1.,high+guard);bool hidden=true;
 for(int y=y0;y<=y1&&hidden;++y)for(int x=x0;x<=x1;++x)if(!(nearest>bounds[int64_t(y)*w+x])){hidden=false;break;}
 if(hidden){mask[i]=0;++counts[3];}else ++counts[0];}
}
struct SegmentResult {double* rows;int64_t size,checked,hidden;};
static int segment_range(const double* points,const double* widths,const double* biases,const double* colors,const uint8_t* only,const uint8_t* enabled,int64_t n,const double* depth,const double* planes,float* visible,int w,int h,int ss,int ortho,double span,double focal,double nearz,double farz,const rpvis::Context* context,const double* eye,const double* basis,SegmentResult* result,int rowlo,int rowhi) noexcept {
 try{*result={};std::vector<double> records;std::vector<float> edge;
 for(int64_t index=0;index<n;++index){double width=widths[index];if(width<=0||!enabled[index])continue;auto p=points+index*6;double lo=0,hi=1,dz=p[5]-p[2];
 if(std::abs(dz)<1e-14){if(p[2]<nearz||p[2]>farz)continue;}else{double t0=(nearz-p[2])/dz,t1=(farz-p[2])/dz;lo=std::max(lo,std::min(t0,t1));hi=std::min(hi,std::max(t0,t1));if(lo>hi)continue;}
 double a[3],b[3];for(int k=0;k<3;++k){if(std::abs(dz)<1e-14){a[k]=p[k];b[k]=p[3+k];}else{double delta=p[3+k]-p[k];a[k]=p[k]+delta*lo;b[k]=p[k]+delta*hi;}}
 double fa=ortho?w/span:focal/a[2],fb=ortho?w/span:focal/b[2],px=w/2.+a[0]*fa,py=h/2.-a[1]*fa,qx=w/2.+b[0]*fb,qy=h/2.-b[1]*fb,dx=qx-px,dy=qy-py,margin=width*ss/2+1;lo=0;hi=1;bool reject=false;
 for(int clip=0;clip<4;++clip){double ca,cb;if(clip==0){ca=-dx;cb=px+margin;}else if(clip==1){ca=dx;cb=w+margin-px;}else if(clip==2){ca=-dy;cb=py+margin;}else{ca=dy;cb=h+margin-py;}
 if(std::abs(ca)<1e-14){if(cb<0){reject=true;break;}}else if(ca<0)lo=std::max(lo,cb/ca);else hi=std::min(hi,cb/ca);if(lo>hi){reject=true;break;}}
 if(reject)continue;
 int xmin=int(std::max(std::floor(std::min(px+lo*dx,px+hi*dx)-margin),0.)),ymin=int(std::max(std::floor(std::min(py+lo*dy,py+hi*dy)-margin),0.)),xmax=int(std::min(std::ceil(std::max(px+lo*dx,px+hi*dx)+margin),double(w))),ymax=int(std::min(std::ceil(std::max(py+lo*dy,py+hi*dy)+margin),double(h)));
 if(xmax<=xmin||ymax<=ymin||ymax<=rowlo||ymin>=rowhi)continue;bool owns=ymin>=rowlo&&ymin<rowhi;bool touched=false;double length=std::sqrt(dx*dx+dy*dy);int count=std::max(1,int(std::ceil(length*(hi-lo)*1.5)));double step=(hi-lo)/count;bool run=false;double ax=0,ay=0,bx=0,by=0;
 auto record=[&](){if(owns)records.insert(records.end(),{double(index),ax,ay,bx,by});};
 for(int k=0;k<count;++k){double t0=lo+k*step,t1=k+1==count?hi:lo+(k+1)*step,mid=(t0+t1)*.5,x=px+mid*dx,y=py+mid*dy,z=ortho?a[2]+mid*(b[2]-a[2]):1/((1-mid)/a[2]+mid/b[2]);
 int ix=std::min(std::max(int(std::floor(x)),0),w-1),iy=std::min(std::max(int(std::floor(y)),0),h-1);auto pi=int64_t(iy)*w+ix;double value=planes[pi*3]*x+planes[pi*3+1]*y+planes[pi*3+2],surface=ortho?value:(value>0?1/value:INFINITY);if(!std::isfinite(depth[pi]))surface=INFINITY;
 bool front=z<=surface+biases[index]*std::max(1.,z);
 if(context&&front&&z>surface+256*rpvis::epsilon*std::max(1.,std::abs(z))){double rx=(x-w/2.)/(ortho?w/span:focal),ry=-(y-h/2.)/(ortho?w/span:focal),origin[3],direction[3];
 for(int axis=0;axis<3;++axis){if(ortho){origin[axis]=eye[axis]+rx*basis[axis]+ry*basis[3+axis];direction[axis]=basis[6+axis];}else{origin[axis]=eye[axis];direction[axis]=rx*basis[axis]+ry*basis[3+axis]+basis[6+axis];}}
 if(owns)++result->checked;if(rpvis::occluded(origin,direction,nearz,z,*context)){if(owns)++result->hidden;front=false;}}
 if(enabled[index]&2)front=!front;
 if(!front){if(run){record();run=false;}continue;}
 double sx=px+t0*dx,sy=py+t0*dy,ex=px+t1*dx,ey=py+t1*dy;
 if(!only[index]){if(!touched){edge.assign(int64_t(ymax-ymin)*(xmax-xmin)*4,0);touched=true;}rpvis::stroke(edge.data(),xmax-xmin,ymax-ymin,int64_t(xmax-xmin)*4,sx-xmin,sy-ymin,ex-xmin,ey-ymin,width*ss,colors+index*3);}
 if(!run){ax=sx/ss;ay=sy/ss;run=true;}bx=ex/ss;by=ey/ss;}
 if(run)record();if(touched){for(int y=std::max(0,rowlo-ymin);y<std::min(ymax-ymin,rowhi-ymin);++y)for(int x=0;x<xmax-xmin;++x){auto e=edge.data()+(int64_t(y)*(xmax-xmin)+x)*4;auto v=visible+(int64_t(y+ymin)*w+x+xmin)*4;float inv=1.f-e[3];for(int c=0;c<4;++c){float product=float(v[c]*inv);v[c]=float(e[c]+product);}}}
 }
 result->size=records.size()/5;if(!records.empty()){result->rows=new double[records.size()];std::copy(records.begin(),records.end(),result->rows);}return 0;
 }catch(...){return -1;}
}

// Disjoint row bands retain exactly the original painter order at every pixel.
// A crossing edge keeps its original scratch coordinates and float32 arithmetic.
// Vector records and diagnostic counts belong to the band containing its top.
API int rp_segments(const double* points,const double* widths,const double* biases,const double* colors,const uint8_t* only,const uint8_t* enabled,int64_t n,const double* depth,const double* planes,float* visible,int w,int h,int ss,int ortho,double span,double focal,double nearz,double farz,const rpvis::Context* context,const double* eye,const double* basis,SegmentResult* result) noexcept {
 unsigned workers=n>=10000?std::min(8u,std::max(1u,std::thread::hardware_concurrency())):1;
 struct Rows {std::vector<SegmentResult> data;Rows(unsigned n):data(n){}~Rows(){for(auto& r:data)delete[] r.rows;}};
 try{Rows parts(workers);
  std::vector<int> codes(workers);std::vector<std::thread> threads;
  auto run=[&](unsigned i){codes[i]=segment_range(points,widths,biases,colors,only,enabled,n,depth,planes,visible,w,h,ss,ortho,span,focal,nearz,farz,context,eye,basis,&parts.data[i],int(i*h/workers),int((i+1)*h/workers));};
  try{for(unsigned i=1;i<workers;++i)threads.emplace_back(run,i);}catch(...){for(auto& t:threads)t.join();throw;}run(0);for(auto& t:threads)t.join();
  *result={};int64_t size=0;for(unsigned i=0;i<workers;++i){if(codes[i])return -1;size+=parts.data[i].size;result->checked+=parts.data[i].checked;result->hidden+=parts.data[i].hidden;}
  struct Row {double value[5];};std::vector<Row> rows;rows.reserve(size);
  for(auto& r:parts.data)for(int64_t i=0;i<r.size;++i){Row row;std::copy(r.rows+i*5,r.rows+i*5+5,row.value);rows.push_back(row);}
  std::stable_sort(rows.begin(),rows.end(),[](const Row& a,const Row& b){return a.value[0]<b.value[0];});
  if(size){result->rows=new double[size*5];for(int64_t i=0;i<size;++i)std::copy(rows[i].value,rows[i].value+5,result->rows+i*5);}result->size=size;return 0;
 }catch(...){return -1;}
}
