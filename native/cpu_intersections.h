// Deterministic triangle query and filtered exact orient3d, IEEE double only.
#include <array>
struct RPQueryMesh {
 const double *low,*high;const int64_t *child,*ranges,*order;
 const double *tri,*triLow,*triHigh;const int64_t *indices,*owners;
 const double *normal,*area,*longest;const uint8_t *activeTri,*activeNode;
};
struct RPQueryResult {double* rows;int64_t size;int64_t counts[9];int code;};
static void twoDiff(double a,double b,double& x,double& e){x=a-b;double bv=a-x,av=x+bv;e=(a-av)+(bv-b);}
static void twoSum(double a,double b,double& x,double& e){x=a+b;double bv=x-a,av=x-bv;e=(a-av)+(b-bv);}
static void twoProduct(double a,double b,double& x,double& e){x=a*b;double c=134217729.*a,abig=c-a,ahi=c-abig,alo=a-ahi;c=134217729.*b;double bbig=c-b,bhi=c-bbig,blo=b-bhi;double e1=x-ahi*bhi,e2=e1-alo*bhi,e3=e2-ahi*blo;e=alo*blo-e3;}
static int grow(const double* expansion,int n,double value,double* result){double q=value;int count=0;for(int i=0;i<n;++i){double v,e;twoSum(q,expansion[i],v,e);q=v;if(e!=0)result[count++]=e;}if(q!=0||count==0)result[count++]=q;return count;}
static double exactOrient(const double* a,const double* b,const double* c,const double* d){
 double values[3][3][2];for(int r=0;r<3;++r)for(int k=0;k<3;++k){double coordinate=r==0?a[k]:r==1?b[k]:c[k];twoDiff(coordinate,d[k],values[r][k][0],values[r][k][1]);for(int j=0;j<2;++j){double x=values[r][k][j];if(x!=0&&(std::abs(x)<1e-70||std::abs(x)>1e70))return std::numeric_limits<double>::quiet_NaN();}}
 double v[256],w[256];double *ex=v,*scratch=w;int length=0;
 const int axes[6][3]={{0,1,2},{0,2,1},{1,0,2},{1,2,0},{2,0,1},{2,1,0}};const double signs[6]={1,-1,-1,1,1,-1};
 for(int term=0;term<6;++term)for(int i=0;i<2;++i){double x=values[0][axes[term][0]][i];if(x==0)continue;for(int j=0;j<2;++j){double y=values[1][axes[term][1]][j];if(y==0)continue;double xy,xyt;twoProduct(x,y,xy,xyt);for(int k=0;k<2;++k){double z=values[2][axes[term][2]][k];if(z==0)continue;double hi,lo,th,tl;twoProduct(xy,z,hi,lo);twoProduct(xyt,z,th,tl);double parts[4]={lo,hi,tl,th};for(double p:parts){double value=p*signs[term];if(value!=0){length=grow(ex,length,value,scratch);std::swap(ex,scratch);}}}}}
 double value=0;for(int i=0;i<length;++i)value+=ex[i];return value;
}
static double orient(const double* a,const double* b,const double* c,const double* d){
 double adx=a[0]-d[0],ady=a[1]-d[1],adz=a[2]-d[2],bdx=b[0]-d[0],bdy=b[1]-d[1],bdz=b[2]-d[2],cdx=c[0]-d[0],cdy=c[1]-d[1],cdz=c[2]-d[2];
 for(double x:{adx,ady,adz,bdx,bdy,bdz,cdx,cdy,cdz})if(x!=0&&(std::abs(x)<1e-70||std::abs(x)>1e70))return std::numeric_limits<double>::quiet_NaN();
 double bc1=bdx*cdy,bc2=cdx*bdy,ca1=cdx*ady,ca2=adx*cdy,ab1=adx*bdy,ab2=bdx*ady;
 double det=adz*(bc1-bc2)+bdz*(ca1-ca2)+cdz*(ab1-ab2);
 double permanent=(std::abs(bc1)+std::abs(bc2))*std::abs(adz)+(std::abs(ca1)+std::abs(ca2))*std::abs(bdz)+(std::abs(ab1)+std::abs(ab2))*std::abs(cdz);
 constexpr double epsilon=1.11022302462515654042e-16;double bound=(7+56*epsilon)*epsilon*permanent;
 if(det>bound||det< -bound)return det;if(permanent==0)return 0;return exactOrient(a,b,c,d);
}
static int section(const double* tri,const double* distances,double eps,double points[6][3]){
 int count=0;for(int k=0;k<3;++k){int next=(k+1)%3;double a=distances[k],b=distances[next];for(int mode=0;mode<2;++mode){bool valid=mode==0?a==0:((a<0&&b>0)||(a>0&&b<0));if(!valid)continue;double f=mode==0?0.:a/(a-b);double p[3];for(int axis=0;axis<3;++axis)p[axis]=tri[k*3+axis]+(tri[next*3+axis]-tri[k*3+axis])*f;
 bool unique=true;for(int j=0;j<count;++j){double x=p[0]-points[j][0],y=p[1]-points[j][1],z=p[2]-points[j][2],square=x*x;square+=y*y;square+=z*z;if(square<=eps*eps){unique=false;break;}}if(unique){for(int axis=0;axis<3;++axis)points[count][axis]=p[axis];++count;}}}return count;
}
static void query(const RPQueryMesh& a,const RPQueryMesh& b,bool same,double eps,int64_t cb,int64_t sb,RPQueryResult& r,std::vector<std::array<double,8>>& rows){
 std::vector<std::pair<int64_t,int64_t>> stack;stack.emplace_back(0,0);double da[3],db[3],direction[3],pa[6][3],pb[6][3];
 while(!stack.empty()){
 auto [na,nb]=stack.back();stack.pop_back();if(a.activeNode&&!a.activeNode[na])continue;if(b.activeNode&&!b.activeNode[nb])continue;++r.counts[0];
 bool overlap=true;for(int k=0;k<3;++k)if(a.low[na*3+k]>b.high[nb*3+k]+eps||b.low[nb*3+k]>a.high[na*3+k]+eps){overlap=false;break;}if(!overlap)continue;
 int64_t la=a.child[na*2],lb=b.child[nb*2];if(same&&na==nb&&la>=0){auto ra=a.child[na*2+1];stack.emplace_back(ra,ra);stack.emplace_back(la,ra);stack.emplace_back(la,la);continue;}
 if(la>=0||lb>=0){double ea=std::max({a.high[na*3]-a.low[na*3],a.high[na*3+1]-a.low[na*3+1],a.high[na*3+2]-a.low[na*3+2]}),eb=std::max({b.high[nb*3]-b.low[nb*3],b.high[nb*3+1]-b.low[nb*3+1],b.high[nb*3+2]-b.low[nb*3+2]});
 if(lb<0||(la>=0&&ea>=eb)){stack.emplace_back(a.child[na*2+1],nb);stack.emplace_back(la,nb);}else{stack.emplace_back(na,b.child[nb*2+1]);stack.emplace_back(na,lb);}continue;}
 for(int64_t oi=a.ranges[na*2];oi<a.ranges[na*2+1];++oi){auto ti=a.order[oi];if(a.activeTri&&!a.activeTri[ti])continue;int64_t begin=same&&na==nb?oi+1:b.ranges[nb*2];
 for(int64_t oj=begin;oj<b.ranges[nb*2+1];++oj){auto tj=b.order[oj];if(b.activeTri&&!b.activeTri[tj])continue;
 overlap=true;for(int k=0;k<3;++k)if(a.triLow[ti*3+k]>b.triHigh[tj*3+k]+eps||b.triLow[tj*3+k]>a.triHigh[ti*3+k]+eps){overlap=false;break;}if(!overlap)continue;++r.counts[1];
 if(same){bool adjacent=a.owners[ti]>=0&&a.owners[ti]==b.owners[tj];if(!adjacent)for(int i=0;i<3;++i)for(int j=0;j<3;++j)if(a.indices[ti*3+i]==b.indices[tj*3+j])adjacent=true;if(adjacent){++r.counts[2];continue;}}
 ++r.counts[3];if(a.area[ti]<=eps*std::max(a.longest[ti],eps)||b.area[tj]<=eps*std::max(b.longest[tj],eps)){++r.counts[5];continue;}
 const double *at=a.tri+ti*9,*bt=b.tri+tj*9,*an=a.normal+ti*3,*bn=b.normal+tj*3;
 for(int v=0;v<3;++v){da[v]=db[v]=0;for(int k=0;k<3;++k){da[v]+=(at[v*3+k]-bt[k])*bn[k];db[v]+=(bt[v*3+k]-at[k])*an[k];}}
 if(std::min({da[0],da[1],da[2]})>eps||std::max({da[0],da[1],da[2]})< -eps||std::min({db[0],db[1],db[2]})>eps||std::max({db[0],db[1],db[2]})< -eps){++r.counts[4];continue;}
 direction[0]=an[1]*bn[2]-an[2]*bn[1];direction[1]=an[2]*bn[0]-an[0]*bn[2];direction[2]=an[0]*bn[1]-an[1]*bn[0];double length=std::sqrt(direction[0]*direction[0]+direction[1]*direction[1]+direction[2]*direction[2]);
 if(std::max({std::abs(da[0]),std::abs(da[1]),std::abs(da[2])})<=eps&&std::max({std::abs(db[0]),std::abs(db[1]),std::abs(db[2])})<=eps){++r.counts[6];continue;}if(length<=1e-12){++r.counts[4];continue;}
 for(int v=0;v<3;++v){da[v]=orient(at+v*3,bt+3,bt+6,bt);db[v]=orient(bt+v*3,at+3,at+6,at);if(!std::isfinite(da[v])||!std::isfinite(db[v])){r.code=3;return;}}
 if(std::min({da[0],da[1],da[2]})>0||std::max({da[0],da[1],da[2]})<0||std::min({db[0],db[1],db[2]})>0||std::max({db[0],db[1],db[2]})<0){++r.counts[4];continue;}
 if(++r.counts[7]>cb){r.code=1;return;}for(double& x:direction)x/=length;int ca=section(at,da,eps,pa),cc=section(bt,db,eps,pb);if(!ca||!cc)continue;
 double mina=INFINITY,maxa=-INFINITY,minb=INFINITY,maxb=-INFINITY;
 for(int p=0;p<ca;++p){double v=0;for(int k=0;k<3;++k)v+=(pa[p][k]-pa[0][k])*direction[k];mina=std::min(mina,v);maxa=std::max(maxa,v);}
 for(int p=0;p<cc;++p){double v=0;for(int k=0;k<3;++k)v+=(pb[p][k]-pa[0][k])*direction[k];minb=std::min(minb,v);maxb=std::max(maxb,v);}
 double lo=std::max(mina,minb),hi=std::min(maxa,maxb);if(hi<lo-eps)continue;if(hi-lo<=eps){++r.counts[8];continue;}
 rows.push_back({pa[0][0]+lo*direction[0],pa[0][1]+lo*direction[1],pa[0][2]+lo*direction[2],pa[0][0]+hi*direction[0],pa[0][1]+hi*direction[1],pa[0][2]+hi*direction[2],double(ti),double(tj)});
 if(int64_t(rows.size())>sb){r.code=2;return;}
 }} }
}
API int rp_query(const RPQueryMesh* a,const RPQueryMesh* b,int same,double eps,int64_t cb,int64_t sb,RPQueryResult* result) noexcept {
 try{*result={};std::vector<std::array<double,8>> rows;query(*a,*b,same!=0,eps,cb,sb,*result,rows);result->size=rows.size();if(!rows.empty()){result->rows=new double[rows.size()*8];std::copy(reinterpret_cast<const double*>(rows.data()),reinterpret_cast<const double*>(rows.data())+rows.size()*8,result->rows);}return 0;}catch(...){return -1;}
}
API void rp_query_free(double* rows) noexcept {delete[] rows;}
