"""OpenCL filtered orientation with an on-device floating-expansion fallback.

No CPU computation participates in a viewport predicate. The explicit fma
residuals and error-free sums require IEEE fp64 and disabled contraction.
"""
SOURCE=r'''
#pragma OPENCL EXTENSION cl_khr_fp64 : enable
#pragma OPENCL FP_CONTRACT OFF
void rt_two_diff(double a,double b,double *hi,double *lo) {
 double x=a-b,bv=a-x,av=x+bv;*hi=x;*lo=(a-av)+(bv-b);
}
void rt_two_sum(double a,double b,double *hi,double *lo) {
 double x=a+b,bv=x-a,av=x-bv;*hi=x;*lo=(a-av)+(b-bv);
}
int rt_grow(double *e,int n,double value,double *out) {
 double q=value;int count=0;
 for(int i=0;i<n;i++){double next,error;rt_two_sum(q,e[i],&next,&error);q=next;if(error!=0.)out[count++]=error;}
 if(q!=0.||count==0)out[count++]=q;
 return count;
}
double rt_orient_exact(double3 a,double3 b,double3 c,double3 d) {
 double values[18];double3 rows[3]={a,b,c};
 for(int r=0;r<3;r++)for(int k=0;k<3;k++)rt_two_diff(rows[r][k],d[k],&values[(r*3+k)*2],&values[(r*3+k)*2+1]);
 double left[256],right[256];double *expansion=left,*scratch=right;int length=0;
 for(int term=0;term<6;term++) {
  int ax,by,cz;double sign;
  if(term==0){ax=0;by=1;cz=2;sign=1.;}else if(term==1){ax=0;by=2;cz=1;sign=-1.;}
  else if(term==2){ax=1;by=0;cz=2;sign=-1.;}else if(term==3){ax=1;by=2;cz=0;sign=1.;}
  else if(term==4){ax=2;by=0;cz=1;sign=1.;}else{ax=2;by=1;cz=0;sign=-1.;}
  for(int i=0;i<2;i++){double x=values[ax*2+i];if(x==0.)continue;
   for(int j=0;j<2;j++){double y=values[(3+by)*2+j];if(y==0.)continue;
    double xy=x*y,xyt=fma(x,y,-xy);
    for(int k=0;k<2;k++){double z=values[(6+cz)*2+k];if(z==0.)continue;
     double high=xy*z,low=fma(xy,z,-high),th=xyt*z,tl=fma(xyt,z,-th);
     double parts[4]={low,high,tl,th};
     for(int p=0;p<4;p++){double v=parts[p]*sign;if(v==0.)continue;
      length=rt_grow(expansion,length,v,scratch);double *swap=expansion;expansion=scratch;scratch=swap;
     }
    }
   }
  }
 }
 double result=0.;for(int i=0;i<length;i++)result+=expansion[i];return result;
}
double rt_orient(double3 a,double3 b,double3 c,double3 d) {
 double3 ad=a-d,bd=b-d,cd=c-d;
 double bc1=bd.x*cd.y,bc2=cd.x*bd.y,ca1=cd.x*ad.y,ca2=ad.x*cd.y,ab1=ad.x*bd.y,ab2=bd.x*ad.y;
 double determinant=ad.z*(bc1-bc2)+bd.z*(ca1-ca2)+cd.z*(ab1-ab2);
 double permanent=(fabs(bc1)+fabs(bc2))*fabs(ad.z)+(fabs(ca1)+fabs(ca2))*fabs(bd.z)+(fabs(ab1)+fabs(ab2))*fabs(cd.z);
 double unit=0x1.0p-53,bound=(7.+56.*unit)*unit*permanent;
 if(fabs(determinant)>bound||permanent==0.)return determinant;
 return rt_orient_exact(a,b,c,d);
}
#pragma OPENCL FP_CONTRACT ON
'''
