// Original preview-only procedural brush arithmetic. No Maya or CPU renderer API.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <exception>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

struct Result {
    uint64_t count=0;
    double* points=nullptr;
    double* u=nullptr;
    int64_t* source=nullptr;
    uint8_t* thin=nullptr;
    ~Result(){delete[] points;delete[] u;delete[] source;delete[] thin;}
};
struct Segment {double p[6],u[2];int64_t source;uint8_t thin;};
struct Node {double u,d,z,x,y,envelope,common;};
static thread_local std::string error;
template<class F> static void parallel(unsigned workers,F run){
    std::vector<std::thread> threads;
    struct Join {std::vector<std::thread>& threads;~Join(){for(auto& t:threads)if(t.joinable())t.join();}} join{threads};
    for(unsigned k=1;k<workers;++k)threads.emplace_back(run,k);run(0);
}
static double hash_noise(double x,double seed){double a=std::sin(x*127.1+seed*311.7)*43758.5453;return a-std::floor(a);}
static double noise(double x,double seed){double lo=std::floor(x),t=x-lo;t=t*t*(3-2*t);return (1-t)*hash_noise(lo,seed)+t*hash_noise(lo+1,seed);}
struct NoiseTable {
    double low=0.,seed=0.;std::vector<double> values;
    void init(double first,double last,double s){
        seed=s;low=std::floor(first);double high=std::floor(last)+1.;
        if(!std::isfinite(low)||!std::isfinite(high)||std::abs(low)>1e8||high-low<0||high-low>131072)return;
        values.resize(size_t(high-low+1));for(size_t i=0;i<values.size();++i)values[i]=hash_noise(low+double(i),seed);
    }
    double operator()(double x)const{
        double lo=std::floor(x),t=x-lo;t=t*t*(3-2*t);double index=lo-low;
        if(index>=0&&index+1<double(values.size())){size_t i=size_t(index);return (1-t)*values[i]+t*values[i+1];}
        return (1-t)*hash_noise(lo,seed)+t*hash_noise(lo+1,seed);
    }
};
struct Noises {
    NoiseTable envelope,common;std::array<NoiseTable,9> displacement,keep;
    Noises(double first,double last,int texture){
        envelope.init(first*.055,last*.055,texture*97);common.init(first*.12,last*.12,texture*73);
        int lanes=texture==1?7:texture==2?9:5;
        for(int lane=0;lane<lanes;++lane){displacement[lane].init(first*.65,last*.65,lane+texture*17);keep[lane].init(first*.9,last*.9,lane+texture*41);}
    }
};

static void calculate(const double* points,const double* phase,const double* c,const Noises& lookup,uint64_t first,uint64_t last,std::vector<Segment>& out){
    const int texture=int(c[31]),lanes=texture==1?7:texture==2?9:5;
    const double width=c[27]*(texture==3?.55:1.)*c[28],spacing=width/lanes,rough=c[29];
    const double threshold=1.-(1.-(texture==1?.10:texture==2?.33:.16))*c[30];
    const double margin=c[32]+c[33]+c[27],factor=c[21]/c[23];
    if(!std::isfinite(width))throw std::runtime_error("Invalid preview brush width");
    out.reserve(size_t(std::min(uint64_t(262144),(last-first)*16)));
    for(uint64_t id=first;id<last;++id){
        double cam[2][3],screen[2][2];
        for(int e=0;e<2;++e)for(int k=0;k<3;++k){
            cam[e][k]=0.;for(int j=0;j<3;++j)cam[e][k]+=(points[id*6+e*3+j]-c[j])*c[3+k*3+j];
            if(!std::isfinite(cam[e][k]))throw std::runtime_error("Invalid preview projection");
        }
        if(cam[0][2]<=c[25]||cam[1][2]<=c[25]){
            Segment s{};std::copy_n(points+id*6,6,s.p);s.u[1]=1.;s.source=int64_t(id);s.thin=0;out.push_back(s);continue;
        }
        for(int e=0;e<2;++e){double f=c[26]?factor:c[24]/cam[e][2];screen[e][0]=c[21]/2+cam[e][0]*f;screen[e][1]=c[22]/2-cam[e][1]*f;}
        const double dx=screen[1][0]-screen[0][0],dy=screen[1][1]-screen[0][1],length=std::sqrt(dx*dx+dy*dy);
        if(!std::isfinite(length))throw std::runtime_error("Invalid preview edge length");
        if(length<1e-8)continue;
        double lo=0.,hi=1.;bool valid=true;
        const double aa[4]={-dx,dx,-dy,dy},bb[4]={screen[0][0]+margin,c[21]+margin-screen[0][0],screen[0][1]+margin,c[22]+margin-screen[0][1]};
        for(int k=0;k<4;++k){if(std::abs(aa[k])<1e-14){if(bb[k]<0){valid=false;break;}}else if(aa[k]<0)lo=std::max(lo,bb[k]/aa[k]);else hi=std::min(hi,bb[k]/aa[k]);if(lo>hi){valid=false;break;}}
        if(!valid)continue;
        const double samples=std::ceil(length*(hi-lo));
        if(!std::isfinite(samples)||samples>2000000)throw std::runtime_error("Preview brush sample budget exceeded");
        const uint64_t n=std::max(uint64_t(1),uint64_t(samples));
        const double step=(hi-lo)/double(n),sign=phase[id*2+1]<phase[id*2]?-1.:1.;
        const double nx=-dy/length*sign,ny=dx/length*sign;
        std::vector<Node> nodes(size_t(n+1));
        for(uint64_t j=0;j<=n;++j){
            Node& v=nodes[size_t(j)];v.u=j==n?hi:lo+double(j)*step;
            v.d=phase[id*2]+v.u*(phase[id*2+1]-phase[id*2]);
            v.z=c[26]?cam[0][2]+v.u*(cam[1][2]-cam[0][2]):1/((1-v.u)/cam[0][2]+v.u/cam[1][2]);
            v.x=screen[0][0]+v.u*dx;v.y=screen[0][1]+v.u*dy;
            if(!std::isfinite(v.d)||!std::isfinite(v.z))throw std::runtime_error("Invalid preview brush coordinates");
            v.envelope=.6+.4*lookup.envelope(v.d*.055);
            v.common=width*.1*rough*(lookup.common(v.d*.12)-.5);
        }
        for(int lane=0;lane<lanes;++lane){
            std::vector<double> displacement(size_t(n+1));
            for(uint64_t j=0;j<=n;++j){const Node& v=nodes[size_t(j)];double d=(lane-(lanes-1)/2.)*spacing*v.envelope;d+=width*.13*rough*(lookup.displacement[lane](v.d*.65)-.5);displacement[size_t(j)]=d+v.common;}
            for(uint64_t j=0;j<n;++j){
                if(lookup.keep[lane]((nodes[size_t(j)].d+nodes[size_t(j+1)].d)*.5*.9)<=threshold)continue;
                Segment s{};s.source=int64_t(id);s.thin=1;
                for(int e=0;e<2;++e){
                    const Node& v=nodes[size_t(j+e)];s.u[e]=v.u;
                    const double x=v.x+displacement[size_t(j+e)]*nx,y=v.y+displacement[size_t(j+e)]*ny;
                    const double local[3]={c[26]?(x-c[21]/2)/factor:(x-c[21]/2)*v.z/c[24],c[26]?(y-c[22]/2)/(-factor):(y-c[22]/2)*v.z/(-c[24]),v.z};
                    for(int k=0;k<3;++k){double world=0.;for(int a=0;a<3;++a)world+=local[a]*c[12+a*3+k];s.p[e*3+k]=world+c[k];}
                }
                out.push_back(s);
            }
            if(out.size()>8000000)throw std::runtime_error("Preview brush output budget exceeded");
        }
    }
}

extern "C" __declspec(dllexport) int rb_version(){return 201;}
extern "C" __declspec(dllexport) const char* rb_error(){return error.c_str();}
extern "C" __declspec(dllexport) void rb_free(Result* r){delete r;}
extern "C" __declspec(dllexport) Result* rb_expand(const double* points,uint64_t count,const double* phase,const double* config){
    try{
        error.clear();if(!points||!phase||!config||count>2000000)throw std::runtime_error("Invalid preview brush input");
        const unsigned workers=count>=4096?4:1;
        double first=0.,last=0.;
        for(uint64_t i=0;i<count*2;++i){if(!std::isfinite(phase[i])||std::abs(phase[i])>1e100)throw std::runtime_error("Invalid preview phase");first=std::min(first,phase[i]);last=std::max(last,phase[i]);}
        const Noises lookup(first,last,int(config[31]));
        std::array<std::vector<Segment>,4> chunks;
        std::array<std::exception_ptr,4> errors;
        auto run=[&](unsigned k){try{calculate(points,phase,config,lookup,count*k/workers,count*(k+1)/workers,chunks[k]);}catch(...){errors[k]=std::current_exception();}};
        parallel(workers,run);
        for(unsigned k=0;k<workers;++k)if(errors[k])std::rethrow_exception(errors[k]);
        std::unique_ptr<Result> result(new Result());std::array<uint64_t,4> offsets{};
        for(unsigned k=0;k<workers;++k){offsets[k]=result->count;result->count+=chunks[k].size();}
        if(result->count>8000000)throw std::runtime_error("Preview brush output budget exceeded");
        result->points=new double[size_t(result->count*6)];result->u=new double[size_t(result->count*2)];result->source=new int64_t[size_t(result->count)];result->thin=new uint8_t[size_t(result->count)];
        auto copy=[&](unsigned k){for(size_t j=0;j<chunks[k].size();++j){const Segment& s=chunks[k][j];uint64_t at=offsets[k]+j;std::copy_n(s.p,6,result->points+at*6);std::copy_n(s.u,2,result->u+at*2);result->source[at]=s.source;result->thin[at]=s.thin;}};
        for(unsigned k=0;k<workers;++k)copy(k);
        return result.release();
    }catch(const std::exception& e){error=e.what();return nullptr;}catch(...){error="Preview brush compute failed";return nullptr;}
}
