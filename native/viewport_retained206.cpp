// Retained GPU line implementation under validation; CPU rendering is independent.
#define NOMINMAX
#include <windows.h>
#include <cstdint>
#include <thread>
#include <atomic>
#include <mutex>
#include <chrono>
#include <maya/MFnPlugin.h>
#include <maya/MDrawRegistry.h>
#include <maya/MPxSubSceneOverride.h>
#include <maya/MShaderManager.h>
#include <maya/MGlobal.h>
#include <maya/MDagPath.h>
#include <maya/MFrameContext.h>
#include <maya/MFnCamera.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MObjectHandle.h>
#include <maya/MStateManager.h>
#include <maya/MDrawContext.h>
#include <maya/MUIDrawManager.h>
#include <maya/MPointArray.h>
#include <maya/MTextureManager.h>
#include <maya/MRenderTargetManager.h>
#include <unordered_map>
#include <algorithm>
#include <stdexcept>
#include <vector>
#include <memory>
#include <cstring>
#include <sstream>
#include <string>
#include <cmath>
using namespace MHWRender;
struct ProfileRange {size_t first,count,slow;int64_t owner;};
struct ProfileData {std::vector<ProfileRange> ranges;std::vector<double> world;std::vector<int64_t> ids,flags;std::vector<float> normals,fixed;};
struct Group {ProfileData profile;std::vector<float> positions,a,neighbors;float width,color[4];unsigned style;int reuse=-1;MBoundingBox box;};
struct Style {bool surface=false,profiled=false;std::vector<float> table;unsigned nw=0,na=0,revision=0,uploaded=~0u;double angles[3]={-30,90,0};int outline=0;MTexture* texture=nullptr; MTexture* brushTexture=nullptr; std::vector<unsigned char> brush; unsigned brushWidth=0,brushHeight=0,brushRevision=0,brushUploaded=~0u; float brushParams[4]={0,1,1,24}; float brushScale=1,brushOpacity=1;float width=0,color[4]={0,0,0,1};float depth[4]={0,0,1,1};float alphaDepth[4]={0,0,1,1};};
static std::vector<Style> styles;
static unsigned activeStyle=0,styleVersion=0,profileBoundsVersion=0;
static bool profileFrustum=true;
extern "C" __declspec(dllexport) void rt_profile_frustum(int enabled){profileFrustum=enabled!=0;++profileBoundsVersion;}
struct LegacyGroup {
    MPointArray points;MColor color,hiddenColor;float width;bool hidden,dashed;
    LegacyGroup(const double* p,unsigned n,float w,const float* c,bool h,const float* hc,bool d):
        points(reinterpret_cast<const double(*)[4]>(p),n),color(c[0],c[1],c[2],1),hiddenColor(hc[0],hc[1],hc[2],1),width(w),hidden(h),dashed(d){}
};
using LegacyFrame=std::vector<LegacyGroup>;
static std::shared_ptr<LegacyFrame> legacyPending,legacyCurrent;
static bool retainedMode=true;
static std::vector<Group> groups;
static MMatrix vp;static int vw=0,vh=0;static unsigned version=0;
static std::string effect,profileEffect,surfaceEffect,surfaceProfileEffect,brushEffect;
extern "C" __declspec(dllexport) void rt_brush_effect(const char* path){brushEffect=path;}
extern "C" __declspec(dllexport) void rt_surface_effect(const char* base,const char* profiled){surfaceEffect=base;surfaceProfileEffect=profiled;}
using Coordinates=int(*)(const double*,const double*,const int64_t*,const int64_t*,const double*,int64_t,int,int,int,double,double,double*);
static Coordinates profileCoordinates=nullptr;
extern "C" __declspec(dllexport) void rt_profile_effect(const char* path,const wchar_t* library){
    profileEffect=path;if(profileCoordinates)return;auto module=LoadLibraryW(library);if(module)profileCoordinates=reinterpret_cast<Coordinates>(GetProcAddress(module,"rp_profile_coordinates"));
}
extern "C" __declspec(dllexport) void rt_style_profiles(unsigned id,int active,const float* table,unsigned nw,unsigned na,const double* angles,int outline){
    if(styles.size()<=id)styles.resize(size_t(id)+1);auto& s=styles[id];s.profiled=active!=0;s.nw=nw;s.na=na;s.outline=outline;
    std::copy(angles,angles+3,s.angles);size_t count=size_t(std::max(nw,na))*4;
    if(s.table.size()!=count||std::memcmp(s.table.data(),table,count*sizeof(float))){s.table.assign(table,table+count);++s.revision;}
}
static size_t lastGroup=0,lastStart=0;
extern "C" __declspec(dllexport) void rt_profile_metadata(const double* world,const int64_t* ids,const int64_t* flags,unsigned n){
    auto& g=groups.at(lastGroup);auto& p=g.profile;
    p.ranges.push_back({p.flags.size(),n,size_t(std::count_if(flags,flags+n,[](int64_t f){return !(f&(512|1024));})),int64_t(int(g.a[lastStart*4+3]+.5f)>>1)});
    p.world.insert(p.world.end(),world,world+size_t(n)*6);p.ids.insert(p.ids.end(),ids,ids+size_t(n)*2);p.flags.insert(p.flags.end(),flags,flags+n);
    p.normals.insert(p.normals.end(),g.a.begin()+lastStart*4,g.a.end());p.fixed.resize(p.flags.size()*2,0.f);
}
// Explicit drawing coordinates remain attached to the stroke, not camera tracing.
extern "C" __declspec(dllexport) void rt_profile_fixed(const float* u,unsigned n){
    auto& p=groups.at(lastGroup).profile;
    if(size_t(n)>p.flags.size())throw std::runtime_error("Invalid surface profile coordinates");
    std::copy(u,u+size_t(n)*2,p.fixed.end()-size_t(n)*2);
}
extern "C" __declspec(dllexport) void rt_style_brush(unsigned id,const float* params,float scale,float opacity,const unsigned char* mask,unsigned w,unsigned h){
    auto& s=styles.at(id);
    std::copy_n(params,4,s.brushParams);s.brushScale=scale;s.brushOpacity=opacity;
    size_t count=size_t(w)*h;
    if(s.brushWidth==w && s.brushHeight==h && (!count || std::equal(s.brush.begin(),s.brush.end(),mask)))return;
    s.brushWidth=w;s.brushHeight=h;
    if(count)s.brush.assign(mask,mask+count);else s.brush.clear();
    ++s.brushRevision;
}
static void uploadBrush(Style& s,MTextureManager* manager){
    if(s.brushUploaded==s.brushRevision)return;
    if(s.brushTexture){manager->releaseTexture(s.brushTexture);s.brushTexture=nullptr;}
    if(!s.brush.empty()){
        MTextureDescription d;d.setToDefault2DTexture();d.fWidth=s.brushWidth;d.fHeight=s.brushHeight;
        d.fFormat=kR8G8B8A8_UNORM;d.fBytesPerRow=s.brushWidth*4;d.fBytesPerSlice=d.fBytesPerRow*s.brushHeight;
        std::vector<unsigned char> rgba(s.brush.size()*4,255);
        for(size_t i=0;i<s.brush.size();++i)rgba[i*4+3]=s.brush[i];
        auto name=std::string("ReaPencil_brush_")+std::to_string(&s-styles.data())+"_"+std::to_string(s.brushRevision);
        s.brushTexture=manager->acquireTexture(name.c_str(),d,rgba.data(),false);
        if(!s.brushTexture)throw std::runtime_error("Brush texture allocation failed");
    }
    s.brushUploaded=s.brushRevision;
}
static void brushUniforms(MShaderInstance* shader,Style& s){
    if(s.brushParams[0]<=0||s.profiled||s.surface)return;
    shader->setParameter("brushParams",s.brushParams);
    shader->setParameter("brushScale",s.brushScale);
    shader->setParameter("brushOpacity",s.brushOpacity);
    MTextureAssignment a;a.texture=s.brushTexture;
    if(a.texture)shader->setParameter("brushTexture",a);
}
static void uploadProfiles(){
    auto manager=MRenderer::theRenderer()->getTextureManager();
    for(auto& s:styles){uploadBrush(s,manager);if(!s.profiled||s.uploaded==s.revision)continue;
        MTextureDescription d;d.setToDefault2DTexture();d.fWidth=1024;d.fHeight=(std::max(s.nw,s.na)+1023)/1024;
        d.fFormat=kR32G32B32A32_FLOAT;d.fBytesPerRow=1024*16;d.fBytesPerSlice=d.fBytesPerRow*d.fHeight;
        auto pixels=s.table;pixels.resize(size_t(d.fWidth)*d.fHeight*4);
        if(s.texture)manager->releaseTexture(s.texture);
        auto name=std::string("ReaPencil_profile_")+std::to_string(&s-styles.data())+"_"+std::to_string(s.revision);s.texture=manager->acquireTexture(name.c_str(),d,pixels.data(),false);if(!s.texture)throw std::runtime_error("Profile texture allocation failed");s.uploaded=s.revision;
    }
}
static void profileUniforms(MShaderInstance* shader,Style& s){
    if(!s.profiled)return;MTextureAssignment a;a.texture=s.texture;shader->setParameter("profileTexture",a);
    shader->setParameter("widthKnotCount",int(s.nw));shader->setParameter("alphaKnotCount",int(s.na));
}
extern "C" __declspec(dllexport) void rt_edge_positions(const double* vertices,const int* topology,unsigned count,double* points,float* normals){
    for(unsigned i=0;i<count;i++){
        const int* ids=topology+i*8;
        for(int endpoint=0;endpoint<2;endpoint++){
            const double* p=vertices+ids[endpoint]*3;
            for(int k=0;k<3;k++)points[i*6+endpoint*3+k]=p[k];
            float* n=normals+i*8+endpoint*4;const int* triangle=ids+2+endpoint*3;
            if(triangle[0]<0){n[0]=n[1]=n[2]=0;continue;}
            const double *a=vertices+triangle[0]*3,*b=vertices+triangle[1]*3,*c=vertices+triangle[2]*3;
            double u[3],v[3],q[3];for(int k=0;k<3;k++){u[k]=b[k]-a[k];v[k]=c[k]-a[k];}
            for(int k=0;k<3;k++)q[k]=u[(k+1)%3]*v[(k+2)%3]-u[(k+2)%3]*v[(k+1)%3];
            double length=std::max(1e-30,std::sqrt(q[0]*q[0]+q[1]*q[1]+q[2]*q[2]));
            for(int k=0;k<3;k++)n[k]=float(q[k]/length);
        }
    }
}
struct Scope {std::vector<float> values;unsigned revision=0,uploaded=~0u;MTexture* texture=nullptr;bool restrictive=false;};
static std::unordered_map<std::string,Scope> scopes;
static bool checkCenterDepth=true;
static bool allowMSAADepth=true;
extern "C" __declspec(dllexport) void rt_msaa_depth(int enabled){allowMSAADepth=enabled!=0;}
static int depthStatus=0;
static std::unordered_map<std::string,unsigned> drawDestinations;
extern "C" __declspec(dllexport) void rt_reset_draw_log(){drawDestinations.clear();}
extern "C" __declspec(dllexport) const char* rt_draw_log(){static std::string result;result.clear();for(auto& item:drawDestinations)result+=item.first+"="+std::to_string(item.second)+"\n";return result.c_str();}
extern "C" __declspec(dllexport) void rt_scope(const char* panel,const float* values,unsigned count){
    auto& scope=scopes[panel];
    if(scope.values.size()==count && !std::memcmp(scope.values.data(),values,count*sizeof(float)))return;
    scope.values.assign(values,values+count);scope.restrictive=std::any_of(values,values+count,[](float v){return v<.5f;});++scope.revision;
}
extern "C" __declspec(dllexport) void rt_depth_mode(int enabled){checkCenterDepth=enabled!=0;}
extern "C" __declspec(dllexport) int rt_depth_status(){return depthStatus;}
static void uploadScopes(){
    auto manager=MRenderer::theRenderer()->getTextureManager();
    for(auto& pair:scopes){auto& scope=pair.second;if(scope.uploaded==scope.revision)continue;
        if(!scope.restrictive){scope.uploaded=scope.revision;continue;}
        MTextureDescription description;description.setToDefault2DTexture();
        description.fWidth=std::min<unsigned>(4096,unsigned(scope.values.size()));
        if(!description.fWidth)continue;
        description.fHeight=(unsigned(scope.values.size())+description.fWidth-1)/description.fWidth;
        description.fFormat=kR32_FLOAT;description.fBytesPerRow=description.fWidth*sizeof(float);
        description.fBytesPerSlice=description.fBytesPerRow*description.fHeight;
        std::vector<float> pixels=scope.values;pixels.resize(description.fWidth*description.fHeight,0);
        if(scope.texture){MTextureDescription previous;scope.texture->textureDescription(previous);
            if(previous.fWidth!=description.fWidth || previous.fHeight!=description.fHeight){manager->releaseTexture(scope.texture);scope.texture=nullptr;}}
        if(scope.texture){if(!scope.texture->update(pixels.data(),false,description.fBytesPerRow))throw std::runtime_error("Scope texture update failed");}
        else scope.texture=manager->acquireTexture((std::string("ReaPencil_scope_")+pair.first+"_"+std::to_string(scope.revision)).c_str(),description,pixels.data(),false);
        if(!scope.texture)throw std::runtime_error("Scope texture allocation failed");
        scope.uploaded=scope.revision;
    }
}
static size_t passBegin=0;
struct SavedState {const MBlendState* blend;const MRasterizerState* raster;const MDepthStencilState* depth;};
static thread_local std::vector<SavedState> stateStack;
static const MBlendState* lineBlend=nullptr;
static const MRasterizerState* lineRaster=nullptr;
static const MDepthStencilState* lineDepth=nullptr;
static const MDepthStencilState* lineDepthManual=nullptr;
static void preDraw(MDrawContext& context,const MRenderItemList&,MShaderInstance* shader){
    MString destination;auto destinationKind=context.renderingDestination(destination);
    ++drawDestinations[std::to_string(int(destinationKind))+":"+destination.asChar()];
    auto scope=scopes.find(destination.asChar());if(scope==scopes.end())scope=scopes.find("__all__");
    bool scoped=scope!=scopes.end() && scope->second.restrictive && scope->second.texture;
    shader->setParameter("scopeEnabled",scoped);
    if(scoped){MTextureAssignment assignment;assignment.texture=scope->second.texture;shader->setParameter("scopeTexture",assignment);}
    auto currentDepth=context.getCurrentDepthRenderTarget();bool hasDepth=false;depthStatus=0;int depthSamples=1;
    if(currentDepth){MRenderTargetDescription description;currentDepth->targetDescription(description);depthSamples=int(description.multiSampleCount());
        if(description.multiSampleCount()<=1 || allowMSAADepth){
            MRenderTargetAssignment assignment;assignment.target=const_cast<MRenderTarget*>(currentDepth);
            hasDepth=bool(shader->setParameter("sceneDepthTexture",assignment));depthStatus=hasDepth?(description.multiSampleCount()>1?4:1):3;
        }else depthStatus=2;
    }
    shader->setParameter("sceneDepthSamples",depthSamples);shader->setParameter("hasSceneDepth",hasDepth);shader->setParameter("checkCenterDepth",checkCenterDepth);
    int x,y,w,h;context.getViewportDimensions(x,y,w,h);float origin[2]={float(x),float(y)};shader->setParameter("viewportOrigin",origin);
    auto projection=context.getMatrix(MFrameContext::kProjectionMtx);
    bool ortho=projection(3,3)>.5;auto eye=context.getTuple(ortho?MFrameContext::kViewDirection:MFrameContext::kViewPosition);
    if(eye.length()>=3){float value[4]={float(eye[0]),float(eye[1]),float(eye[2]),ortho?0.f:1.f};if(ortho)for(int i=0;i<3;i++)value[i]=-value[i];shader->setParameter("eyeVector",value);}
    shader->setParameter("planeMatrix",context.getMatrix(MFrameContext::kViewProjMtx).inverse().transpose());
    shader->updateParameters(context);
    auto manager=context.getStateManager();if(!manager)return;
    stateStack.push_back({manager->getBlendState(),manager->getRasterizerState(),manager->getDepthStencilState()});
    if(!lineBlend){
        MBlendStateDesc blend;blend.targetBlends[0].blendEnable=true;
        blend.targetBlends[0].sourceBlend=MBlendState::kSourceAlpha;
        blend.targetBlends[0].destinationBlend=MBlendState::kInvSourceAlpha;
        lineBlend=MStateManager::acquireBlendState(blend);
        MRasterizerStateDesc raster;raster.cullMode=MRasterizerState::kCullNone;raster.depthBias=0;raster.slopeScaledDepthBias=0;
        lineRaster=MStateManager::acquireRasterizerState(raster);
        MDepthStencilStateDesc depth;depth.depthEnable=true;depth.depthWriteEnable=false;depth.depthFunc=MStateManager::kCompareLessEqual;
        lineDepth=MStateManager::acquireDepthStencilState(depth);
        depth.depthFunc=MStateManager::kCompareAlways;
        lineDepthManual=MStateManager::acquireDepthStencilState(depth);
    }
    manager->setBlendState(lineBlend);manager->setRasterizerState(lineRaster);manager->setDepthStencilState(checkCenterDepth && hasDepth?lineDepthManual:lineDepth);
}
static void postDraw(MDrawContext& context,const MRenderItemList&,MShaderInstance*){
    auto manager=context.getStateManager();if(!manager||stateStack.empty())return;
    auto old=stateStack.back();stateStack.pop_back();
    manager->setBlendState(old.blend);manager->setRasterizerState(old.raster);manager->setDepthStencilState(old.depth);
    MStateManager::releaseBlendState(old.blend);MStateManager::releaseRasterizerState(old.raster);MStateManager::releaseDepthStencilState(old.depth);
}
extern "C" __declspec(dllexport) int rt_view_projection(double* p,int* w,int* h){
    for(int r=0;r<4;r++)for(int c=0;c<4;c++)p[r*4+c]=vp(r,c);*w=vw;*h=vh;return vw>0;
}
extern "C" __declspec(dllexport) void rt_effect(const char* path){effect=path;}
extern "C" __declspec(dllexport) void rt_mode(int value){retainedMode=value!=0;}
extern "C" __declspec(dllexport) void rt_begin(){groups.clear();passBegin=0;legacyPending=std::make_shared<LegacyFrame>();}
extern "C" __declspec(dllexport) int rt_add(const double* p,unsigned n,float width,const float* color,int hidden,const float* hiddenColor,int dashed){
    if(!legacyPending||!p||!color||!hiddenColor||n>2097152||n%2)return 0;
    try{legacyPending->emplace_back(p,n,width,color,hidden!=0,hiddenColor,dashed!=0);return 1;}
    catch(...){legacyPending.reset();return 0;}
}
extern "C" __declspec(dllexport) unsigned rt_group_count(){return unsigned(groups.size());}
extern "C" __declspec(dllexport) void rt_reuse(unsigned first,unsigned count){for(unsigned i=0;i<count;i++){groups.emplace_back();groups.back().reuse=int(first+i);}passBegin=groups.size();}
extern "C" __declspec(dllexport) void rt_begin_pass(){passBegin=groups.size();}
extern "C" __declspec(dllexport) void rt_style(unsigned id,float width,const float* color){
    if(styles.size()<=id)styles.resize(size_t(id)+1);activeStyle=id;
    auto& s=styles[id];if(s.width!=width)++profileBoundsVersion;s.width=width;for(int k=0;k<3;k++)s.color[k]=color[k];s.color[3]=1;++styleVersion;
}
extern "C" __declspec(dllexport) void rt_style_surface(unsigned id,int enabled){if(styles.size()<=id)styles.resize(size_t(id)+1);styles[id].surface=enabled!=0;}
extern "C" __declspec(dllexport) void rt_surface_neighbors(const double* points,unsigned count){
    auto& g=groups.at(lastGroup);for(size_t i=0;i<size_t(count)*6;i++)g.neighbors[lastStart*3+i]=float(points[i]);
}
extern "C" __declspec(dllexport) void rt_style_depth(unsigned id,const float* parameters){
    if(styles.size()<=id)styles.resize(size_t(id)+1);
    for(int k=0;k<4;k++)styles[id].depth[k]=parameters[k];++styleVersion;
}
extern "C" __declspec(dllexport) void rt_style_alpha_depth(unsigned id,const float* parameters){
    if(styles.size()<=id)styles.resize(size_t(id)+1);
    for(int k=0;k<4;k++)styles[id].alphaDepth[k]=parameters[k];++styleVersion;
}
extern "C" __declspec(dllexport) int rt_add_retained(const double* points,const float* normals,unsigned count,float width,const float* color){
    if(!count)return 1;
    try {
        Group* target=nullptr;
        for(size_t j=passBegin;j<groups.size();j++){
            auto& candidate=groups[j];
            if(candidate.style==activeStyle && candidate.positions.size()/6+count<=1048576){target=&candidate;break;}
        }
        if(!target){groups.emplace_back();target=&groups.back();target->style=activeStyle;target->width=width;for(int k=0;k<3;k++)target->color[k]=color[k];target->color[3]=1;}
        auto& g=*target;size_t start=g.positions.size()/3;lastGroup=size_t(target-groups.data());lastStart=start;
        g.positions.resize((start+size_t(count)*2)*3);g.a.resize((start+size_t(count)*2)*4);if(styles[activeStyle].surface)g.neighbors.resize(g.positions.size());
        double low[3]={points[0],points[1],points[2]},high[3]={points[0],points[1],points[2]};
        for(size_t i=0;i<size_t(count)*2;i++)for(int k=0;k<3;k++){
            double p=points[i*3+k];g.positions[(start+i)*3+k]=float(p);low[k]=std::min(low[k],p);high[k]=std::max(high[k],p);
        }
        std::memcpy(g.a.data()+start*4,normals,size_t(count)*8*sizeof(float));
        g.box.expand(MPoint(low[0],low[1],low[2]));g.box.expand(MPoint(high[0],high[1],high[2]));
        return 1;
    }catch(...){groups.clear();return 0;}
}
extern "C" __declspec(dllexport) void rt_end(){legacyCurrent=legacyPending;legacyPending.reset();++version;}
struct GPUGroup {
    std::vector<std::pair<MString,MVertexBuffer*>> streams;
    std::vector<std::unique_ptr<MVertexBuffer>> vertices;
    std::unique_ptr<MIndexBuffer> indices;MShaderInstance* shader=nullptr;
    std::atomic<bool> coordinatesDirty{false};ProfileData profile;std::vector<float> profileValues;size_t slowCount=0;MVertexBuffer* profileBuffer=nullptr;
    unsigned style=0,count=0,revision=0;MBoundingBox box;
    ~GPUGroup(){auto renderer=MRenderer::theRenderer();if(renderer&&shader)renderer->getShaderManager()->releaseShader(shader);}
};
struct GPUFrame {
    unsigned revision=~0u,styleRevision=~0u;
    std::vector<std::shared_ptr<GPUGroup>> groups;
};
static std::shared_ptr<GPUFrame> frameCache;
static MObjectHandle displayOwner;
static std::string coordinateDebug;
extern "C" __declspec(dllexport) const char* rt_profile_debug(){return coordinateDebug.c_str();}
static MMatrix profileView,profileProjection;static unsigned profileRevision=~0u;static int profileW=0,profileH=0;static unsigned profileBoundsStamp=~0u;
static bool profileVisibleBox(const MBoundingBox& box,const MMatrix& clip,const double* eye,float width){
    auto low=box.min(),high=box.max();double lo[3]={low.x,low.y,low.z},hi[3]={high.x,high.y,high.z};
    for(int k=0;k<3;k++){double guard=2e-6*std::max({1.,std::abs(lo[k]),std::abs(hi[k]),std::abs(eye[k])});lo[k]-=guard;hi[k]+=guard;}
    double mx=1+(std::max(0.f,width)+2.)/std::max(vw,1),my=1+(std::max(0.f,width)+2.)/std::max(vh,1);unsigned outside=63;
    for(int i=0;i<8;i++){auto q=MPoint(i&1?hi[0]:lo[0],i&2?hi[1]:lo[1],i&4?hi[2]:lo[2])*clip;
        double epsilon=1e-6*std::max({1.,std::abs(q.x),std::abs(q.y),std::abs(q.z),std::abs(q.w)});if(!std::isfinite(epsilon))return true;
        unsigned bad=0;if(q.w*mx+q.x< -epsilon)bad|=1;if(q.w*mx-q.x< -epsilon)bad|=2;if(q.w*my+q.y< -epsilon)bad|=4;if(q.w*my-q.y< -epsilon)bad|=8;if(q.w+q.z< -epsilon)bad|=16;if(q.w-q.z< -epsilon)bad|=32;outside&=bad;if(!outside)return true;
    }return false;
}
template<class Function> static void profileParallel(size_t count,Function function){
    std::atomic<size_t> next{0};std::atomic<bool> failed{false};std::exception_ptr error;std::mutex mutex;
    auto worker=[&](){try{while(!failed){size_t i=next.fetch_add(1);if(i>=count)break;function(i);}}catch(...){std::lock_guard<std::mutex> lock(mutex);error=std::current_exception();failed=true;}};
    unsigned threads=std::min<unsigned>(8,unsigned(count));std::vector<std::thread> workers;workers.reserve(threads);
    try{for(unsigned k=1;k<threads;k++)workers.emplace_back(worker);}catch(...){failed=true;for(auto& t:workers)t.join();throw;}
    worker();for(auto& t:workers)t.join();if(error)std::rethrow_exception(error);
}
static void updateCoordinates(const MFrameContext& context){
    using Clock=std::chrono::steady_clock;auto begin=Clock::now();
    auto cameraWorld=context.getCurrentCameraPath().inclusiveMatrix();auto view=cameraWorld.inverse(),projection=context.getMatrix(MFrameContext::kProjectionMtx);
    if(profileRevision==version&&profileBoundsStamp==profileBoundsVersion&&profileView==view&&profileProjection==projection&&profileW==vw&&profileH==vh)return;
    size_t count=0;for(auto& g:frameCache->groups)count+=g->slowCount;
    if(!count){profileView=view;profileProjection=projection;profileW=vw;profileH=vh;profileRevision=version;profileBoundsStamp=profileBoundsVersion;coordinateDebug="GPU independent strokes";return;}
    if(!profileCoordinates)throw std::runtime_error("CPU stroke coordinate library unavailable");
    double matrix[4][4];for(int r=0;r<4;r++)for(int c=0;c<4;c++)matrix[r][c]=view(r,c);
    auto position=MPoint(0,0,0)*cameraWorld;auto direction=MVector(0,0,1)*cameraWorld;
    double eye[3]={position.x,position.y,position.z},ray[3]={direction.x,direction.y,direction.z};
    bool ortho=projection(3,3)>.5;double focal=projection(0,0)*vw*.5,span=2/projection(0,0);
    struct Chunk {GPUGroup* group;size_t first,count,partition;std::vector<double> points,world,angles;std::vector<int64_t> keys,ids;std::vector<std::pair<GPUGroup*,size_t>> scatter;};
    struct Work {std::vector<size_t> chunks;size_t visible=0;MBoundingBox box;float width=0;bool active=true;};
    std::vector<Chunk> chunks;std::vector<Work> work;std::unordered_map<uint64_t,size_t> partitions;
    for(auto& block:frameCache->groups){auto& g=*block;if(!g.slowCount)continue;
        for(auto r:g.profile.ranges){if(!r.slow)continue;uint64_t key=(uint64_t(r.owner)<<32)|g.style;auto found=partitions.find(key);size_t index;
            if(found==partitions.end()){index=work.size();partitions.emplace(key,index);work.emplace_back();}else index=found->second;
            work[index].box.expand(g.box.min());work[index].box.expand(g.box.max());work[index].width=styles[g.style].width;
            for(size_t offset=0;offset<r.count;offset+=32768){work[index].chunks.push_back(chunks.size());chunks.emplace_back();auto& chunk=chunks.back();chunk.group=&g;chunk.partition=index;chunk.first=r.first+offset;chunk.count=std::min<size_t>(32768,r.count-offset);}
        }
    }
    size_t activeTasks=0;auto clip=view*projection;for(auto& task:work){task.active=!profileFrustum||profileVisibleBox(task.box,clip,eye,task.width);activeTasks+=task.active;}
    // Bound independent classification chunks so a single large mesh cannot
    // serialize camera updates. Reassemble complete key partitions for tracing.
    profileParallel(chunks.size(),[&](size_t index){auto& range=chunks[index];if(!work[range.partition].active)return;auto& g=*range.group;auto& p=g.profile;auto& style=styles[g.style];
        auto& points=range.points;auto& world=range.world;auto& angles=range.angles;auto& keys=range.keys;auto& ids=range.ids;auto& scatter=range.scatter;
        size_t reserve=std::min<size_t>(range.count,4096);points.reserve(reserve*6);world.reserve(reserve*6);angles.reserve(reserve*3);keys.reserve(reserve*4);ids.reserve(reserve*2);scatter.reserve(reserve);
            for(size_t i=range.first;i<range.first+range.count;i++){if(p.flags[i]&(512|1024))continue;auto v=p.world.data()+i*6;auto q=p.normals.data()+i*8;
                double sx=ortho?ray[0]:eye[0]-v[0],sy=ortho?ray[1]:eye[1]-v[1],sz=ortho?ray[2]:eye[2]-v[2];
                bool f0=q[0]*sx+q[1]*sy+q[2]*sz>0,f1=q[4]*sx+q[5]*sy+q[6]*sz>0;
                if((int(q[3]+.5f)&1)&&f0==f1)continue;
                double p0[6];for(int e=0;e<2;e++)for(int k=0;k<3;k++)p0[e*3+k]=v[e*3]*matrix[0][k]+v[e*3+1]*matrix[1][k]+v[e*3+2]*matrix[2][k]+matrix[3][k];
                if(p0[2]>=-1e-10||p0[5]>=-1e-10)continue;p0[2]=-p0[2];p0[5]=-p0[5];
                int64_t bits=(p.flags[i]&255)|(style.outline&&f0!=f1?4:0);
                points.insert(points.end(),p0,p0+6);world.insert(world.end(),v,v+6);
                keys.insert(keys.end(),{int64_t(int(q[3]+.5f)>>1),int64_t(g.style),0,bits});ids.insert(ids.end(),p.ids.begin()+i*2,p.ids.begin()+i*2+2);
                angles.insert(angles.end(),style.angles,style.angles+3);scatter.emplace_back(&g,i);
            }
    });
    auto classified=Clock::now();
    profileParallel(work.size(),[&](size_t index){auto& task=work[index];size_t n=0;for(auto ci:task.chunks)n+=chunks[ci].scatter.size();task.visible=n;if(!n)return;
        std::vector<double> points,world,angles;std::vector<int64_t> keys,ids;std::vector<std::pair<GPUGroup*,size_t>> scatter;
        points.reserve(n*6);world.reserve(n*6);angles.reserve(n*3);keys.reserve(n*4);ids.reserve(n*2);scatter.reserve(n);
        for(auto ci:task.chunks){auto& c=chunks[ci];points.insert(points.end(),c.points.begin(),c.points.end());world.insert(world.end(),c.world.begin(),c.world.end());angles.insert(angles.end(),c.angles.begin(),c.angles.end());keys.insert(keys.end(),c.keys.begin(),c.keys.end());ids.insert(ids.end(),c.ids.begin(),c.ids.end());scatter.insert(scatter.end(),c.scatter.begin(),c.scatter.end());}
        std::vector<double> u(n*2);if(profileCoordinates(points.data(),world.data(),keys.data(),ids.data(),angles.data(),int64_t(n),vw,vh,ortho,span,focal,u.data()))throw std::runtime_error("Stroke tracing failed");
        for(size_t i=0;i<n;i++){auto item=scatter[i];auto& values=item.first->profileValues;values[item.second*2]=float(u[i*2]);values[item.second*2+1]=float(u[i*2+1]);}
        for(auto ci:task.chunks)chunks[ci].group->coordinatesDirty=true;
    });
    auto traced=Clock::now();
    for(auto& g:frameCache->groups)if(g->profileBuffer&&g->coordinatesDirty.exchange(false)){auto& values=g->profileValues;auto data=g->profileBuffer->acquire(values.size(),true);if(!data)throw std::runtime_error("Stroke coordinate buffer unavailable");std::memcpy(data,values.data(),values.size()*sizeof(float));g->profileBuffer->commit(data);}
    size_t visible=0;for(auto& task:work)visible+=task.visible;
    std::ostringstream log;log<<"count="<<count<<" visible="<<visible<<" chunks="<<chunks.size()<<" partitions="<<work.size()<<" active="<<activeTasks<<" classify_ms="<<std::chrono::duration<double,std::milli>(classified-begin).count()<<" trace_ms="<<std::chrono::duration<double,std::milli>(traced-classified).count()<<" upload_ms="<<std::chrono::duration<double,std::milli>(Clock::now()-traced).count();coordinateDebug=log.str();
    profileView=view;profileProjection=projection;profileW=vw;profileH=vh;profileRevision=version;profileBoundsStamp=profileBoundsVersion;
}

class Draw:public MPxSubSceneOverride {
    MObjectHandle object;
    std::shared_ptr<GPUFrame> resources;
    std::unordered_map<std::string,std::shared_ptr<LegacyFrame>> fallbacks;
    void clear(MSubSceneContainer& container){
        container.clear();resources.reset();
    }
    void failed(MSubSceneContainer& container){
        clear(container);frameCache.reset();fallbacks.clear();
        MGlobal::displayWarning("ReaPencil: retained GPU allocation/shader unavailable; switching to the legacy GPU viewport.");
        MGlobal::executePythonCommand("import reatoon.retained_viewport as r; r._device_error='Retained GPU allocation/shader unavailable'; r.vp.request_refresh()",false,false);
    }
public:
    explicit Draw(const MObject& obj):MPxSubSceneOverride(obj),object(obj){}
    static MPxSubSceneOverride* create(const MObject& obj){return new Draw(obj);}
    DrawAPI supportedDrawAPIs()const override{return DrawAPI(kOpenGL|kOpenGLCoreProfile|kDirectX11);}
    bool hasUIDrawables()const override{return true;}
    bool areUIDrawablesDirty()const override{return true;}
    void addUIDrawables(MUIDrawManager& draw,const MFrameContext& context)override{
        MString destination;context.renderingDestination(destination);auto found=fallbacks.find(destination.asChar());
        if(found==fallbacks.end() || !found->second)return;auto fallback=found->second;
        draw.beginDrawable(MUIDrawManager::kNonSelectable);
        bool hidden=false;for(auto& g:*fallback)hidden|=g.hidden;
        if(hidden){draw.beginDrawInXray();for(auto& g:*fallback)if(g.hidden){
            draw.setLineWidth(g.width);draw.setColor(g.hiddenColor);draw.setLineStyle(MUIDrawManager::kDashed);draw.mesh(MUIDrawManager::kLines,g.points);
        }draw.endDrawInXray();}
        for(auto& g:*fallback){draw.setLineWidth(g.width);draw.setColor(g.color);draw.setLineStyle(g.dashed?MUIDrawManager::kDashed:MUIDrawManager::kSolid);
            draw.setDepthPriority(MRenderItem::sDormantWireDepthPriority);draw.lineList(g.points,false);}
        draw.endDrawable();
    }
    bool requiresUpdate(const MSubSceneContainer&,const MFrameContext&)const override{return true;}
    void update(MSubSceneContainer& container,const MFrameContext& context)override{
        try{updateFrame(container,context);}catch(const std::exception& e){coordinateDebug=e.what();failed(container);}catch(...){coordinateDebug="Unknown native exception";failed(container);}
    }
    void updateFrame(MSubSceneContainer& container,const MFrameContext& context){
        if(!object.isValid()||!object.isAlive())return;
        MStatus status;auto enabled=MFnDependencyNode(object.object()).findPlug("linePreviewEnabled",true,&status).asBool();
        MString panel;context.renderingDestination(panel);int allowed=1;
        MGlobal::executePythonCommand(MString("import reatoon.preview_renderers as p; int(p.allowed('")+panel+"'))",allowed,false,false);
        enabled=enabled&&allowed;
        auto iterator=container.getIterator();
        while(auto item=iterator->next())item->enable(status&&enabled);
        iterator->destroy();
        if(!status||!enabled){fallbacks.clear();if(displayOwner==object)displayOwner=MObjectHandle();return;}
        if(!displayOwner.isValid()||!displayOwner.isAlive())displayOwner=object;
        if(displayOwner!=object){clear(container);fallbacks.clear();return;}
        int x,y;context.getViewportDimensions(x,y,vw,vh);vp=context.getMatrix(MFrameContext::kViewProjMtx);
        auto path=context.getCurrentCameraPath();MString destination;context.renderingDestination(destination);std::ostringstream code;
        code<<"import reatoon.retained_viewport as r; r.prepare('"<<path.fullPathName().asChar()<<"',"<<double(vw)/std::max(vh,1)<<","<<int(MRenderer::theRenderer()->drawAPI())<<",'"<<destination.asChar()<<"')";
        status=MGlobal::executePythonCommand(code.str().c_str(),false,false);
        if(!status){clear(container);fallbacks.clear();return;}
        if(!retainedMode){clear(container);frameCache.reset();fallbacks[destination.asChar()]=legacyCurrent;return;}
        fallbacks.clear();
        uploadScopes();uploadProfiles();
        auto manager=MRenderer::theRenderer()->getShaderManager();
        if(!frameCache || frameCache->revision!=version){
            auto next=std::make_shared<GPUFrame>();
            for(unsigned j=0;j<groups.size();j++){
                auto& g=groups[j];
                if(g.reuse>=0){if(!frameCache||unsigned(g.reuse)>=frameCache->groups.size())throw std::runtime_error("Invalid retained group reuse");next->groups.push_back(frameCache->groups[g.reuse]);continue;}
                unsigned n=unsigned(g.positions.size()/3);if(!n)continue;
                auto shader=manager->getEffectsFileShader((styles[g.style].surface?(styles[g.style].profiled?surfaceProfileEffect:surfaceEffect):(styles[g.style].profiled?profileEffect:(styles[g.style].brushParams[0]>0?brushEffect:effect))).c_str(),"Main",nullptr,0,true,preDraw,postDraw);
                if(!shader)throw std::runtime_error("Line shader allocation failed");
                auto block=std::make_shared<GPUGroup>();auto& gpu=*block;gpu.shader=shader;gpu.style=g.style;gpu.box=g.box;gpu.count=n;gpu.revision=version;gpu.profile=std::move(g.profile);gpu.slowCount=std::count_if(gpu.profile.flags.begin(),gpu.profile.flags.end(),[](int64_t f){return !(f&(512|1024));});profileUniforms(shader,styles[g.style]);brushUniforms(shader,styles[g.style]);
                shader->setParameter("lineColor",g.color);shader->setParameter("lineWidth",g.width);if(g.style<styles.size())shader->setParameter("widthDepthReduction",styles[g.style].depth);if(g.style<styles.size())shader->setParameter("alphaDepthReduction",styles[g.style].alphaDepth);
                MVertexBufferDescriptorList descriptors;shader->requiredVertexBuffers(descriptors);
                for(int i=0;i<descriptors.length();i++){
                    MVertexBufferDescriptor descriptor;descriptors.getDescriptor(i,descriptor);
                    bool position=descriptor.semantic()==MGeometry::kPosition;
                    bool coordinate=!position && descriptor.dimension()==1;
                    bool neighbor=!position && descriptor.dimension()==3;
                    std::vector<float> zero(coordinate?n:0,0);
                    if(coordinate)for(size_t k=0;k<gpu.profile.flags.size();k++)if(gpu.profile.flags[k]&512){zero[k*2]=-1;zero[k*2+1]=float(styles[g.style].angles[0]);}
                    if(coordinate)for(size_t k=0;k<gpu.profile.flags.size();k++)if(gpu.profile.flags[k]&1024){zero[k*2]=gpu.profile.fixed[k*2];zero[k*2+1]=gpu.profile.fixed[k*2+1];}
                    if(coordinate)gpu.profileValues=zero;
                    const auto& values=coordinate?zero:(neighbor?g.neighbors:(position?g.positions:g.a));
                    auto buffer=std::make_unique<MVertexBuffer>(descriptor);
                    auto data=buffer->acquire(n,true);if(!data)throw std::runtime_error("Vertex allocation failed");
                    if(values.size()!=size_t(n)*descriptor.dimension())throw std::runtime_error("Shader stream dimension mismatch");
                    std::memcpy(data,values.data(),values.size()*sizeof(float));buffer->commit(data);
                    MString name=coordinate?"strokeU":(neighbor?"inNeighbor":(position?"positions":"normalA"));if(coordinate)gpu.profileBuffer=buffer.get();gpu.streams.emplace_back(name,buffer.get());gpu.vertices.push_back(std::move(buffer));
                }
                auto ib=std::make_unique<MIndexBuffer>(MGeometry::kUnsignedInt32);
                auto ids=static_cast<unsigned*>(ib->acquire(n,true));if(!ids)throw std::runtime_error("Index allocation failed");
                for(unsigned i=0;i<n;i++)ids[i]=i;ib->commit(ids);
                gpu.indices=std::move(ib);next->groups.push_back(block);
                std::vector<float>().swap(g.neighbors);std::vector<float>().swap(g.positions);std::vector<float>().swap(g.a);
            }
            next->revision=version;frameCache=std::move(next);groups.clear();
        }
        updateCoordinates(context);
        if(resources!=frameCache){
            // Rebind even reused buffers: VP2 consolidates render-item state.
            // Skipping unchanged items can retain stale consolidated geometry.
            clear(container);resources=frameCache;
            for(size_t j=0;j<resources->groups.size();++j){auto& g=*resources->groups[j];
                auto item=MRenderItem::Create(MString("reaPencil_")+int(j),MRenderItem::DecorationItem,MGeometry::kLines);
                item->setDrawMode(MGeometry::kAll);item->enable(true);item->setShader(g.shader);container.add(item);
                MVertexBufferArray streams;for(auto& stream:g.streams)streams.addBuffer(stream.first,stream.second);
                if(!setGeometryForRenderItem(*item,streams,*g.indices,&g.box))throw std::runtime_error("Shader geometry binding failed");
            }
        }
        if(resources->styleRevision!=styleVersion){for(auto& block:resources->groups)if(block->style<styles.size()){
            auto& s=styles[block->style];profileUniforms(block->shader,s);brushUniforms(block->shader,s);block->shader->setParameter("lineColor",s.color);block->shader->setParameter("lineWidth",s.width);block->shader->setParameter("widthDepthReduction",s.depth);block->shader->setParameter("alphaDepthReduction",s.alphaDepth);
        }resources->styleRevision=styleVersion;}
        MGlobal::executePythonCommand("import reatoon.viewport as v; v._retained_probe_ready=True",false,false);
    }
    ~Draw()=default;
};
static const MString classification("drawdb/subscene/reaToonViewport"),registrant("ReaPencilRetainedGPU");
MStatus initializePlugin(MObject obj){
    MFnPlugin fn(obj,"ReaPencil independent project","0.8.10","Any");
    return MDrawRegistry::registerSubSceneOverrideCreator(classification,registrant,Draw::create);
}
MStatus uninitializePlugin(MObject){
    frameCache.reset();displayOwner=MObjectHandle();
    MStateManager::releaseBlendState(lineBlend);MStateManager::releaseRasterizerState(lineRaster);MStateManager::releaseDepthStencilState(lineDepth);MStateManager::releaseDepthStencilState(lineDepthManual);
    lineBlend=nullptr;lineRaster=nullptr;lineDepth=nullptr;lineDepthManual=nullptr;
    legacyCurrent.reset();legacyPending.reset();groups.clear();
    auto renderer=MRenderer::theRenderer();if(renderer){auto manager=renderer->getTextureManager();for(auto& pair:scopes)if(pair.second.texture)manager->releaseTexture(pair.second.texture);}
    for(auto& s:styles)if(renderer){if(s.texture)renderer->getTextureManager()->releaseTexture(s.texture);if(s.brushTexture)renderer->getTextureManager()->releaseTexture(s.brushTexture);}
    styles.clear();scopes.clear();
    return MDrawRegistry::deregisterSubSceneOverrideCreator(classification,registrant);
}
