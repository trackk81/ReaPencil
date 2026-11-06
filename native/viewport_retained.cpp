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
#include <vector>
#include <memory>
#include <cstring>
#include <sstream>
#include <string>
using namespace MHWRender;
struct Group {std::vector<float> positions,a;float width,color[4];unsigned style;MBoundingBox box;};
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
static size_t passBegin=0;
struct SavedState {const MBlendState* blend;const MRasterizerState* raster;const MDepthStencilState* depth;};
static thread_local std::vector<SavedState> stateStack;
static const MBlendState* lineBlend=nullptr;
static const MRasterizerState* lineRaster=nullptr;
static const MDepthStencilState* lineDepth=nullptr;
static void preDraw(MDrawContext& context,const MRenderItemList&,MShaderInstance*){
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
        for(unsigned i=0;i<count;i++)for(unsigned endpoint=0;endpoint<2;endpoint++){
            auto source=size_t(i)*2+endpoint,index=start+source;
            for(int c=0;c<3;c++)g.positions[index*3+c]=float(points[source*3+c]);
            for(int c=0;c<4;c++)g.a[index*4+c]=normals[size_t(i)*8+endpoint*4+c];
            g.box.expand(MPoint(points[source*3],points[source*3+1],points[source*3+2]));
        }
        return 1;
    }catch(...){groups.clear();return 0;}
}
extern "C" __declspec(dllexport) void rt_end(){legacyCurrent=legacyPending;legacyPending.reset();++version;}
class Draw;
static Draw* activeDraw=nullptr;
class Draw:public MPxSubSceneOverride {
    MObjectHandle object;
    unsigned uploaded=~0u;
    std::vector<std::unique_ptr<MVertexBuffer>> vertices;
    std::vector<std::unique_ptr<MIndexBuffer>> indices;
    std::vector<MShaderInstance*> shaders;
    std::vector<unsigned> shaderStyles;
    unsigned uploadedStyle=~0u;
    std::shared_ptr<LegacyFrame> fallback;
    void clear(MSubSceneContainer& container){
        container.clear();vertices.clear();indices.clear();
        auto manager=MRenderer::theRenderer()->getShaderManager();
        for(auto s:shaders)manager->releaseShader(s);shaders.clear();shaderStyles.clear();uploadedStyle=~0u;
    }
    void failed(MSubSceneContainer& container){
        clear(container);uploaded=~0u;fallback.reset();
        MGlobal::displayWarning("ReaPencil: retained GPU allocation/shader unavailable; switching to the legacy GPU viewport.");
        MGlobal::executePythonCommand("import reatoon.retained_viewport as r; r._device_error='Retained GPU allocation/shader unavailable'; r.vp.request_refresh()",false,false);
    }
public:
    explicit Draw(const MObject& obj):MPxSubSceneOverride(obj),object(obj){}
    static MPxSubSceneOverride* create(const MObject& obj){return new Draw(obj);}
    DrawAPI supportedDrawAPIs()const override{return DrawAPI(kOpenGL|kOpenGLCoreProfile|kDirectX11);}
    bool hasUIDrawables()const override{return true;}
    bool areUIDrawablesDirty()const override{return true;}
    void addUIDrawables(MUIDrawManager& draw,const MFrameContext&)override{
        if(!fallback)return;
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
        if(!status||!enabled){fallback.reset();if(activeDraw==this)activeDraw=nullptr;return;}
        if(activeDraw && activeDraw!=this){clear(container);fallback.reset();return;}
        activeDraw=this;
        int x,y;context.getViewportDimensions(x,y,vw,vh);vp=context.getMatrix(MFrameContext::kViewProjMtx);
        auto path=context.getCurrentCameraPath();std::ostringstream code;
        code<<"import reatoon.retained_viewport as r; r.prepare('"<<path.fullPathName().asChar()<<"',"<<double(vw)/std::max(vh,1)<<","<<int(MRenderer::theRenderer()->drawAPI())<<")";
        status=MGlobal::executePythonCommand(code.str().c_str(),false,false);
        if(!status){clear(container);uploaded=~0u;fallback.reset();return;}
        if(!retainedMode){clear(container);uploaded=~0u;fallback=legacyCurrent;return;}
        fallback.reset();
        auto manager=MRenderer::theRenderer()->getShaderManager();
        if(uploaded!=version){
            clear(container);
            for(unsigned j=0;j<groups.size();j++){
                auto& g=groups[j];unsigned n=unsigned(g.positions.size()/3);if(!n)continue;
                auto shader=manager->getEffectsFileShader(effect.c_str(),"Main",nullptr,0,true,preDraw,postDraw);
                if(!shader){failed(container);return;}
                shader->setParameter("lineColor",g.color);shader->setParameter("lineWidth",g.width);
                auto item=MRenderItem::Create(MString("reaPencil_")+int(j),MRenderItem::DecorationItem,MGeometry::kLines);
                item->setDrawMode(MGeometry::kAll);item->enable(true);item->setShader(shader);container.add(item);shaders.push_back(shader);shaderStyles.push_back(g.style);
                MVertexBufferDescriptorList descriptors;shader->requiredVertexBuffers(descriptors);MVertexBufferArray streams;
                int channel=0;
                for(int i=0;i<descriptors.length();i++){
                    MVertexBufferDescriptor descriptor;descriptors.getDescriptor(i,descriptor);
                    bool position=descriptor.semantic()==MGeometry::kPosition;
                    const auto& values=position?g.positions:g.a;
                    auto buffer=std::make_unique<MVertexBuffer>(descriptor);
                    auto data=buffer->acquire(n,true);if(!data){failed(container);return;}
                    if(values.size()!=size_t(n)*descriptor.dimension()){MGlobal::displayError("ReaPencil shader stream dimension mismatch");return;}
                    std::memcpy(data,values.data(),values.size()*sizeof(float));buffer->commit(data);
                    MString name=position?"positions":"normalA";streams.addBuffer(name,buffer.get());vertices.push_back(std::move(buffer));
                }
                auto ib=std::make_unique<MIndexBuffer>(MGeometry::kUnsignedInt32);
                auto ids=static_cast<unsigned*>(ib->acquire(n,true));if(!ids){failed(container);return;}
                for(unsigned i=0;i<n;i++)ids[i]=i;ib->commit(ids);
                status=setGeometryForRenderItem(*item,streams,*ib,&g.box);indices.push_back(std::move(ib));
                if(!status){MGlobal::displayError("ReaPencil shader geometry binding failed");return;}
                std::vector<float>().swap(g.positions);std::vector<float>().swap(g.a);
            }
            uploaded=version;groups.clear();
        }
        auto cameraMatrix=path.inclusiveMatrix();MFnCamera camera(path);
        float eye[4];
        if(camera.isOrtho()){for(int i=0;i<3;i++)eye[i]=float(cameraMatrix[2][i]);eye[3]=0;}
        else{for(int i=0;i<3;i++)eye[i]=float(cameraMatrix[3][i]);eye[3]=1;}
        MMatrix planes=vp.inverse().transpose();
        for(auto shader:shaders){shader->setParameter("eyeVector",eye);shader->setParameter("planeMatrix",planes);}
        if(uploadedStyle!=styleVersion){
            for(size_t i=0;i<shaders.size();i++)if(shaderStyles[i]<styles.size()){
                auto& s=styles[shaderStyles[i]];shaders[i]->setParameter("lineColor",s.color);shaders[i]->setParameter("lineWidth",s.width);
            }
            uploadedStyle=styleVersion;
        }
        MGlobal::executePythonCommand("import reatoon.viewport as v; v._retained_probe_ready=True",false,false);
    }
    ~Draw(){if(activeDraw==this)activeDraw=nullptr;auto renderer=MRenderer::theRenderer();if(renderer)for(auto s:shaders)renderer->getShaderManager()->releaseShader(s);}
};
static const MString classification("drawdb/subscene/reaToonViewport"),registrant("ReaPencilRetainedGPU");
MStatus initializePlugin(MObject obj){
    MFnPlugin fn(obj,"ReaPencil independent project","0.8.4","Any");
    return MDrawRegistry::registerSubSceneOverrideCreator(classification,registrant,Draw::create);
}
MStatus uninitializePlugin(MObject){
    MStateManager::releaseBlendState(lineBlend);MStateManager::releaseRasterizerState(lineRaster);MStateManager::releaseDepthStencilState(lineDepth);
    lineBlend=nullptr;lineRaster=nullptr;lineDepth=nullptr;
    legacyCurrent.reset();legacyPending.reset();groups.clear();styles.clear();
    return MDrawRegistry::deregisterSubSceneOverrideCreator(classification,registrant);
}
