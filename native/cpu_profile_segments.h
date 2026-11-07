// Native batched profile stage derived from our own strict CPU segment stage.
static int profile_segment_range(const double* us,const double* luts,const int64_t* offsets,const uint8_t* alpha_profiles,const double* points,const double* widths,const double* biases,const double* colors,const uint8_t* only,const uint8_t* enabled,int64_t n,const double* depth,const double* planes,float* visible,int w,int h,int ss,int ortho,double span,double focal,double nearz,double farz,const rpvis::Context* context,const double* eye,const double* basis,SegmentResult* result,int rowlo,int rowhi) noexcept {
 try{*result={};std::vector<double> records;std::vector<float> edge;
 for(int64_t index=0;index<n;++index){double width=widths[index];if(width<=0||!enabled[index])continue;auto p=points+index*6;double lo=0,hi=1,dz=p[5]-p[2];
 if(std::abs(dz)<1e-14){if(p[2]<nearz||p[2]>farz)continue;}else{double t0=(nearz-p[2])/dz,t1=(farz-p[2])/dz;lo=std::max(lo,std::min(t0,t1));hi=std::min(hi,std::max(t0,t1));if(lo>hi)continue;}
 double a[3],b[3];for(int k=0;k<3;++k){if(std::abs(dz)<1e-14){a[k]=p[k];b[k]=p[3+k];}else{double delta=p[3+k]-p[k];a[k]=p[k]+delta*lo;b[k]=p[k]+delta*hi;}}
 double fa=ortho?w/span:focal/a[2],fb=ortho?w/span:focal/b[2],px=w/2.+a[0]*fa,py=h/2.-a[1]*fa,qx=w/2.+b[0]*fb,qy=h/2.-b[1]*fb,dx=qx-px,dy=qy-py,margin=width*ss/2+1;double original_fa=ortho?w/span:focal/p[2],original_fb=ortho?w/span:focal/p[5];
 double original_ax=w/2.+p[0]*original_fa,original_ay=h/2.-p[1]*original_fa;
 double original_dx=p[3]*original_fb-p[0]*original_fa,original_dy=-p[4]*original_fb+p[1]*original_fa;
 double original_den=std::max(original_dx*original_dx+original_dy*original_dy,1e-30);
 double ta=((px-original_ax)*original_dx+(py-original_ay)*original_dy)/original_den;
 double tb=((qx-original_ax)*original_dx+(qy-original_ay)*original_dy)/original_den;
 double du=us[index*2+1]-us[index*2],u0=us[index*2]+std::clamp(ta,0.,1.)*du,u1=us[index*2]+std::clamp(tb,0.,1.)*du;
 lo=0;hi=1;bool reject=false;
 for(int clip=0;clip<4;++clip){double ca,cb;if(clip==0){ca=-dx;cb=px+margin;}else if(clip==1){ca=dx;cb=w+margin-px;}else if(clip==2){ca=-dy;cb=py+margin;}else{ca=dy;cb=h+margin-py;}
 if(std::abs(ca)<1e-14){if(cb<0){reject=true;break;}}else if(ca<0)lo=std::max(lo,cb/ca);else hi=std::min(hi,cb/ca);if(lo>hi){reject=true;break;}}
 if(reject)continue;
 int xmin=int(std::max(std::floor(std::min(px+lo*dx,px+hi*dx)-margin),0.)),ymin=int(std::max(std::floor(std::min(py+lo*dy,py+hi*dy)-margin),0.)),xmax=int(std::min(std::ceil(std::max(px+lo*dx,px+hi*dx)+margin),double(w))),ymax=int(std::min(std::ceil(std::max(py+lo*dy,py+hi*dy)+margin),double(h)));
 if(xmax<=xmin||ymax<=ymin||ymax<=rowlo||ymin>=rowhi)continue;bool owns=ymin>=rowlo&&ymin<rowhi;bool touched=false;double length=std::sqrt(dx*dx+dy*dy);int count=std::max(1,int(std::ceil(length*(hi-lo)*1.5)));double step=(hi-lo)/count;bool run=false;double ax=0,ay=0,bx=0,by=0;
 auto record=[&](){
  if(owns)records.insert(records.end(),{double(index),ax,ay,bx,by});
  if(!only[index]){
   if(!touched){edge.assign(int64_t(ymax-ymin)*(xmax-xmin)*4,0);touched=true;}
   double row[7]={ax*ss-xmin,ay*ss-ymin,bx*ss-xmin,by*ss-ymin,colors[index*3],colors[index*3+1],colors[index*3+2]};
   double original[4]={px-xmin,py-ymin,qx-xmin,qy-ymin};auto off=offsets+index*4;
   rp_profile_runs(edge.data(),xmax-xmin,ymax-ymin,int64_t(xmax-xmin)*4,row,1,original,u0,u1,width*ss,(alpha_profiles[index]&2)?double(ss):0.,luts+off[0]*2,int(off[1]),luts+off[2]*2,int(off[3]));
  }
 };
 for(int k=0;k<count;++k){double t0=lo+k*step,t1=k+1==count?hi:lo+(k+1)*step,mid=(t0+t1)*.5,x=px+mid*dx,y=py+mid*dy,z=ortho?a[2]+mid*(b[2]-a[2]):1/((1-mid)/a[2]+mid/b[2]);
 int ix=std::min(std::max(int(std::floor(x)),0),w-1),iy=std::min(std::max(int(std::floor(y)),0),h-1);auto pi=int64_t(iy)*w+ix;double value=planes[pi*3]*x+planes[pi*3+1]*y+planes[pi*3+2],surface=ortho?value:(value>0?1/value:INFINITY);if(!std::isfinite(depth[pi]))surface=INFINITY;
 bool front=z<=surface+biases[index]*std::max(1.,z);
 if(context&&front&&z>surface+256*rpvis::epsilon*std::max(1.,std::abs(z))){double rx=(x-w/2.)/(ortho?w/span:focal),ry=-(y-h/2.)/(ortho?w/span:focal),origin[3],direction[3];
 for(int axis=0;axis<3;++axis){if(ortho){origin[axis]=eye[axis]+rx*basis[axis]+ry*basis[3+axis];direction[axis]=basis[6+axis];}else{origin[axis]=eye[axis];direction[axis]=rx*basis[axis]+ry*basis[3+axis]+basis[6+axis];}}
 if(owns)++result->checked;if(rpvis::occluded(origin,direction,nearz,z,*context)){if(owns)++result->hidden;front=false;}}
 if(!front){if(run){record();run=false;}continue;}
 double sx=px+t0*dx,sy=py+t0*dy,ex=px+t1*dx,ey=py+t1*dy;

 if(!run){ax=sx/ss;ay=sy/ss;run=true;}bx=ex/ss;by=ey/ss;}
 if(run)record();if(touched){for(int y=std::max(0,rowlo-ymin);y<std::min(ymax-ymin,rowhi-ymin);++y)for(int x=0;x<xmax-xmin;++x){auto e=edge.data()+(int64_t(y)*(xmax-xmin)+x)*4;auto v=visible+(int64_t(y+ymin)*w+x+xmin)*4;if(alpha_profiles[index]&1){if(e[3]>v[3])for(int c=0;c<4;++c)v[c]=e[c];}else{float inv=1.f-e[3];for(int c=0;c<4;++c){float product=float(v[c]*inv);v[c]=float(e[c]+product);}}}}
 }
 result->size=records.size()/5;if(!records.empty()){result->rows=new double[records.size()];std::copy(records.begin(),records.end(),result->rows);}return 0;
 }catch(...){return -1;}
}

// Disjoint row bands retain exactly the original painter order at every pixel.
// A crossing edge keeps its original scratch coordinates and float32 arithmetic.
// Vector records and diagnostic counts belong to the band containing its top.
API int rp_profile_segments(const double* us,const double* luts,const int64_t* offsets,const uint8_t* alpha_profiles,const double* points,const double* widths,const double* biases,const double* colors,const uint8_t* only,const uint8_t* enabled,int64_t n,const double* depth,const double* planes,float* visible,int w,int h,int ss,int ortho,double span,double focal,double nearz,double farz,const rpvis::Context* context,const double* eye,const double* basis,SegmentResult* result) noexcept {
 unsigned workers=n>=10000?std::min(8u,std::max(1u,std::thread::hardware_concurrency())):1;
 struct Rows {std::vector<SegmentResult> data;Rows(unsigned n):data(n){}~Rows(){for(auto& r:data)delete[] r.rows;}};
 try{Rows parts(workers);
  std::vector<int> codes(workers);std::vector<std::thread> threads;
  auto run=[&](unsigned i){codes[i]=profile_segment_range(us,luts,offsets,alpha_profiles,points,widths,biases,colors,only,enabled,n,depth,planes,visible,w,h,ss,ortho,span,focal,nearz,farz,context,eye,basis,&parts.data[i],int(i*h/workers),int((i+1)*h/workers));};
  try{for(unsigned i=1;i<workers;++i)threads.emplace_back(run,i);}catch(...){for(auto& t:threads)t.join();throw;}run(0);for(auto& t:threads)t.join();
  *result={};int64_t size=0;for(unsigned i=0;i<workers;++i){if(codes[i])return -1;size+=parts.data[i].size;result->checked+=parts.data[i].checked;result->hidden+=parts.data[i].hidden;}
  struct Row {double value[5];};std::vector<Row> rows;rows.reserve(size);
  for(auto& r:parts.data)for(int64_t i=0;i<r.size;++i){Row row;std::copy(r.rows+i*5,r.rows+i*5+5,row.value);rows.push_back(row);}
  std::stable_sort(rows.begin(),rows.end(),[](const Row& a,const Row& b){return a.value[0]<b.value[0];});
  if(size){result->rows=new double[size*5];for(int64_t i=0;i<size;++i)std::copy(rows[i].value,rows[i].value+5,result->rows+i*5);}result->size=size;return 0;
 }catch(...){return -1;}
}

API void rp_profile_free(double* rows) noexcept {delete[] rows;}
