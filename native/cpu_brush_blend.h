// Independent implementation inferred from controlled white-matte RGBA probes.
static void rgb_hsv(const double* c,double* h) noexcept {
 double hi=std::max({c[0],c[1],c[2]}),lo=std::min({c[0],c[1],c[2]}),d=hi-lo;
 h[2]=hi;h[1]=hi>0?d/hi:0;h[0]=0;
 if(d>1e-15){if(hi==c[0])h[0]=(c[1]-c[2])/d;else if(hi==c[1])h[0]=2+(c[2]-c[0])/d;else h[0]=4+(c[0]-c[1])/d;
 h[0]/=6;if(h[0]<0)h[0]+=1;}
}
static void hsv_rgb(const double* h,double* c) noexcept {
 double f=h[0]*6;int i=int(std::floor(f));f-=i;double p=h[2]*(1-h[1]),q=h[2]*(1-h[1]*f),t=h[2]*(1-h[1]*(1-f));
 switch(i%6){case 0:c[0]=h[2];c[1]=t;c[2]=p;break;case 1:c[0]=q;c[1]=h[2];c[2]=p;break;case 2:c[0]=p;c[1]=h[2];c[2]=t;break;
 case 3:c[0]=p;c[1]=q;c[2]=h[2];break;case 4:c[0]=t;c[1]=p;c[2]=h[2];break;default:c[0]=h[2];c[1]=p;c[2]=q;}
}
static double blend_component(double b,double s,int mode) noexcept {
 switch(mode){case 0:return s;case 1:return b+s;case 2:return b-s;case 3:return b*s;case 4:return b+s-b*s;
 case 5:return b<.5?2*b*s:1-2*(1-b)*(1-s);case 6:return s<.5?2*b*s:1-2*(1-b)*(1-s);
 case 7:{double d=b<=.25?((16*b-12)*b+4)*b:std::sqrt(std::max(0.,b));return s<=.5?b-(1-2*s)*b*(1-b):b+(2*s-1)*(d-b);}
 case 8:return std::min(b,s);case 9:return std::max(b,s);case 10:return std::abs(b-s);default:return b+s-2*b*s;}
}
API int rp_brush_composite(float* target,const float* source,int64_t n,int mode,double opacity) noexcept {
 if(n<0||mode<0||mode>15||!std::isfinite(opacity)||opacity<0||opacity>1)return -1;
 if(opacity==0)return 0;
 auto run=[&](int64_t begin,int64_t end){for(int64_t i=begin;i<end;++i){auto b=target+i*4;auto s=source+i*4;
 double sa=double(s[3])*opacity;if(sa<=0)continue;double ba=b[3],oa=sa+ba*(1-sa),back[3],color[3],mixed[3];
 for(int k=0;k<3;++k){back[k]=double(b[k])+1-ba;color[k]=double(s[k])/s[3];}
 if(mode>=12){double bh[3],sh[3];rgb_hsv(back,bh);rgb_hsv(color,sh);
 if(mode==12)sh[0]=bh[0];else if(mode==13)sh[1]=bh[1];else if(mode==14){sh[0]=bh[0];sh[1]=bh[1];}else sh[2]=bh[2];hsv_rgb(sh,mixed);
 }else for(int k=0;k<3;++k)mixed[k]=blend_component(back[k],color[k],mode);
 for(int k=0;k<3;++k)b[k]=float(std::clamp(back[k]*(1-sa)+mixed[k]*sa,0.,1.)-(1-oa));b[3]=float(oa);
 }};
 unsigned workers=n>=1000000?std::min(8u,std::max(1u,std::thread::hardware_concurrency())):1;
 try{std::vector<std::thread> threads;try{for(unsigned i=1;i<workers;++i)threads.emplace_back(run,i*n/workers,(i+1)*n/workers);}catch(...){for(auto& t:threads)t.join();return -1;}
 run(0,n/workers);for(auto& t:threads)t.join();return 0;}catch(...){return -1;}
}
