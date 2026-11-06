// Retained GPU line implementation under validation; CPU rendering is independent.
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
struct Group {std::vector<float> positions,a;float width,color[4];unsigned style;int reuse=-1;MBoundingBox box;};
struct Style {float width,color[4];};
static std::vector<Style> styles;
static unsigned activeStyle=0,styleVersion=0;
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
static std::string effect;
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
static void preDraw(MDrawContext& context,const MRenderItemList&,MShaderInstance* shader){
    MString destination;auto destinationKind=context.renderingDestination(destination);
    ++drawDestinations[std::to_string(int(destinationKind))+":"+destination.asChar()];
    auto scope=scopes.find(destination.asChar());if(scope==scopes.end())scope=scopes.find("__all__");
    bool scoped=scope!=scopes.end() && scope->second.restrictive && scope->second.texture;
    shader->setParameter("scopeEnabled",scoped);
    if(scoped){MTextureAssignment assignment;assignment.texture=scope->second.texture;shader->setParameter("scopeTexture",assignment);}
    auto currentDepth=context.getCurrentDepthRenderTarget();bool hasDepth=false;depthStatus=0;
    if(currentDepth){MRenderTargetDescription description;currentDepth->targetDescription(description);
        if(description.multiSampleCount()<=1){
            MRenderTargetAssignment assignment;assignment.target=const_cast<MRenderTarget*>(currentDepth);
            hasDepth=bool(shader->setParameter("sceneDepthTexture",assignment));depthStatus=hasDepth?1:3;
        }else depthStatus=2;
    }
    shader->setParameter("hasSceneDepth",hasDepth);shader->setParameter("checkCenterDepth",checkCenterDepth);
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
    }
    manager->setBlendState(lineBlend);manager->setRasterizerState(lineRaster);manager->setDepthStencilState(lineDepth);
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
    auto& s=styles[id];s.width=width;for(int k=0;k<3;k++)s.color[k]=color[k];s.color[3]=1;++styleVersion;
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
        auto& g=*target;size_t start=g.positions.size()/3;
        g.positions.resize((start+size_t(count)*2)*3);g.a.resize((start+size_t(count)*2)*4);
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
    unsigned style=0,count=0,revision=0;MBoundingBox box;
    ~GPUGroup(){auto renderer=MRenderer::theRenderer();if(renderer&&shader)renderer->getShaderManager()->releaseShader(shader);}
};
struct GPUFrame {
    unsigned revision=~0u,styleRevision=~0u;
    std::vector<std::shared_ptr<GPUGroup>> groups;
};
static std::shared_ptr<GPUFrame> frameCache;
static MObjectHandle displayOwner;
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
        try{updateFrame(container,context);}catch(...){failed(container);}
    }
    void updateFrame(MSubSceneContainer& container,const MFrameContext& context){
        if(!object.isValid()||!object.isAlive())return;
        MStatus status;auto enabled=MFnDependencyNode(object.object()).findPlug("linePreviewEnabled",true,&status).asBool();
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
        uploadScopes();
        auto manager=MRenderer::theRenderer()->getShaderManager();
        if(!frameCache || frameCache->revision!=version){
            auto next=std::make_shared<GPUFrame>();
            for(unsigned j=0;j<groups.size();j++){
                auto& g=groups[j];
                if(g.reuse>=0){if(!frameCache||unsigned(g.reuse)>=frameCache->groups.size())throw std::runtime_error("Invalid retained group reuse");next->groups.push_back(frameCache->groups[g.reuse]);continue;}
                unsigned n=unsigned(g.positions.size()/3);if(!n)continue;
                auto shader=manager->getEffectsFileShader(effect.c_str(),"Main",nullptr,0,true,preDraw,postDraw);
                if(!shader)throw std::runtime_error("Line shader allocation failed");
                auto block=std::make_shared<GPUGroup>();auto& gpu=*block;gpu.shader=shader;gpu.style=g.style;gpu.box=g.box;gpu.count=n;gpu.revision=version;
                shader->setParameter("lineColor",g.color);shader->setParameter("lineWidth",g.width);
                MVertexBufferDescriptorList descriptors;shader->requiredVertexBuffers(descriptors);
                for(int i=0;i<descriptors.length();i++){
                    MVertexBufferDescriptor descriptor;descriptors.getDescriptor(i,descriptor);
                    bool position=descriptor.semantic()==MGeometry::kPosition;
                    const auto& values=position?g.positions:g.a;
                    auto buffer=std::make_unique<MVertexBuffer>(descriptor);
                    auto data=buffer->acquire(n,true);if(!data)throw std::runtime_error("Vertex allocation failed");
                    if(values.size()!=size_t(n)*descriptor.dimension())throw std::runtime_error("Shader stream dimension mismatch");
                    std::memcpy(data,values.data(),values.size()*sizeof(float));buffer->commit(data);
                    MString name=position?"positions":"normalA";gpu.streams.emplace_back(name,buffer.get());gpu.vertices.push_back(std::move(buffer));
                }
                auto ib=std::make_unique<MIndexBuffer>(MGeometry::kUnsignedInt32);
                auto ids=static_cast<unsigned*>(ib->acquire(n,true));if(!ids)throw std::runtime_error("Index allocation failed");
                for(unsigned i=0;i<n;i++)ids[i]=i;ib->commit(ids);
                gpu.indices=std::move(ib);next->groups.push_back(block);
                std::vector<float>().swap(g.positions);std::vector<float>().swap(g.a);
            }
            next->revision=version;frameCache=std::move(next);groups.clear();
        }
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
            auto& s=styles[block->style];block->shader->setParameter("lineColor",s.color);block->shader->setParameter("lineWidth",s.width);
        }resources->styleRevision=styleVersion;}
        MGlobal::executePythonCommand("import reatoon.viewport as v; v._retained_probe_ready=True",false,false);
    }
    ~Draw()=default;
};
static const MString classification("drawdb/subscene/reaToonViewport"),registrant("ReaPencilRetainedGPU");
MStatus initializePlugin(MObject obj){
    MFnPlugin fn(obj,"ReaPencil independent project","0.8.8","Any");
    return MDrawRegistry::registerSubSceneOverrideCreator(classification,registrant,Draw::create);
}
MStatus uninitializePlugin(MObject){
    frameCache.reset();displayOwner=MObjectHandle();
    MStateManager::releaseBlendState(lineBlend);MStateManager::releaseRasterizerState(lineRaster);MStateManager::releaseDepthStencilState(lineDepth);
    lineBlend=nullptr;lineRaster=nullptr;lineDepth=nullptr;
    legacyCurrent.reset();legacyPending.reset();groups.clear();styles.clear();
    auto renderer=MRenderer::theRenderer();if(renderer){auto manager=renderer->getTextureManager();for(auto& pair:scopes)if(pair.second.texture)manager->releaseTexture(pair.second.texture);}
    scopes.clear();
    return MDrawRegistry::deregisterSubSceneOverrideCreator(classification,registrant);
}
