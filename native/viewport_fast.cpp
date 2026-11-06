// Independent screen-space preview. Maya owns deformation and mesh drawing;
// this plugin never exports vertices or reads image/geometry buffers to the CPU.
#include <maya/MFnPlugin.h>
#include <maya/MViewport2Renderer.h>
#include <maya/MRenderTargetManager.h>
#include <maya/MShaderManager.h>
#include <maya/MFrameContext.h>
#include <maya/MGlobal.h>
#include <maya/MStateManager.h>
#include <memory>
#include <unordered_map>
#include <string>
using namespace MHWRender;
static std::string effect;
static float width=1.5f,crease=.25f,color[4]={0,0,0,1};
static unsigned frames=0;
extern "C" __declspec(dllexport) void rp_fast_config(const char* path,float w,float c,const float* rgb){effect=path;width=w;crease=c;for(int i=0;i<3;i++)color[i]=rgb[i];}
extern "C" __declspec(dllexport) unsigned rp_fast_frames(){return frames;}
struct Targets {
    MRenderTarget* surface[2]={nullptr,nullptr};
    MRenderTarget* output[2]={nullptr,nullptr};
    unsigned width=0,height=0;
    ~Targets(){auto renderer=MRenderer::theRenderer();if(!renderer)return;auto m=renderer->getRenderTargetManager();for(auto p:surface)if(p)m->releaseRenderTarget(p);if(output[0])m->releaseRenderTarget(output[0]);}
    bool resize(const MString& name,unsigned w,unsigned h){
        if(width==w&&height==h)return true;
        auto m=MRenderer::theRenderer()->getRenderTargetManager();
        MRenderTarget** slots[]={&surface[0],&surface[1],&output[0]};
        for(int i=0;i<3;i++){
            MRenderTargetDescription desc(name+"_"+i,w,h,1,i==1?kD24S8:kR8G8B8A8_UNORM,0,false);
            if(*slots[i]){if(!(*slots[i])->updateDescription(desc))return false;}
            else *slots[i]=m->acquireRenderTarget(desc);
            if(!*slots[i])return false;
        }
        output[1]=surface[1];width=w;height=h;return true;
    }
};
class Scene:public MSceneRender {
public:
    Targets* targets=nullptr;bool ui;
    Scene(bool overlay):MSceneRender(overlay?"ReaPencil_fast_controls":"ReaPencil_fast_surface"),ui(overlay){}
    MRenderTarget* const* targetOverrideList(unsigned& count)override{count=2;return ui?targets->output:targets->surface;}
    MSceneFilterOption renderFilterOverride()override{return ui?kRenderUIItems:kRenderShadedItems;}
    MClearOperation& clearOperation()override{mClearOperation.setMask(ui?MClearOperation::kClearNone:MClearOperation::kClearAll);return mClearOperation;}
};
class Composite:public MQuadRender {
public:
    Targets* targets=nullptr;MShaderInstance* program=nullptr;
    const MDepthStencilState* depth=nullptr;
    Composite():MQuadRender("ReaPencil_fast_contours"){}
    ~Composite(){if(depth)MStateManager::releaseDepthStencilState(depth);}
    const MDepthStencilState* depthStencilStateOverride()override{if(!depth){MDepthStencilStateDesc d;d.depthEnable=false;d.depthWriteEnable=false;depth=MStateManager::acquireDepthStencilState(d);}return depth;}
    MRenderTarget* const* targetOverrideList(unsigned& count)override{count=1;return targets->output;}
    const MShaderInstance* shader()override{if(program)++frames;return program;}
    MClearOperation& clearOperation()override{mClearOperation.setMask(MClearOperation::kClearNone);return mClearOperation;}
};
class HUD:public MHUDRender {
public:Targets* targets=nullptr;
    MRenderTarget* const* targetOverrideList(unsigned& count)override{count=2;return targets->output;}
};
class Present:public MPresentTarget {
public:Targets* targets=nullptr;
    Present():MPresentTarget("ReaPencil_fast_present"){setPresentDepth(true);}
    MRenderTarget* const* targetOverrideList(unsigned& count)override{count=2;return targets->output;}
};
class Fast:public MRenderOverride {
    Scene scene{false},ui{true};Composite composite;HUD hud;Present present;
    MRenderOperation* ops[5]={&scene,&composite,&ui,&hud,&present};
    std::unordered_map<std::string,std::unique_ptr<Targets>> destinations;
    int cursor=0;
public:
    Fast():MRenderOverride("reaPencilFastPreview"){}
    ~Fast(){if(composite.program&&MRenderer::theRenderer())MRenderer::theRenderer()->getShaderManager()->releaseShader(composite.program);}
    DrawAPI supportedDrawAPIs()const override{return kOpenGLCoreProfile;}
    MString uiName()const override{return "ReaPencil Fast Preview";}
    bool startOperationIterator()override{cursor=0;return true;}
    MRenderOperation* renderOperation()override{return cursor<5?ops[cursor]:nullptr;}
    bool nextRenderOperation()override{return ++cursor<5;}
    MStatus setup(const MString& destination)override{
        auto renderer=MRenderer::theRenderer();unsigned w,h;renderer->outputTargetSize(w,h);
        if(!w||!h||effect.empty())return MS::kFailure;
        auto& storage=destinations[destination.asChar()];if(!storage)storage=std::make_unique<Targets>();
        if(!storage->resize(MString("ReaPencil_fast_")+destination,w,h))return MS::kFailure;
        auto target=storage.get();scene.targets=ui.targets=composite.targets=hud.targets=present.targets=target;
        auto& shader=composite.program;
        if(!shader){shader=renderer->getShaderManager()->getEffectsFileShader(effect.c_str(),"Main");if(!shader){MGlobal::displayError("ReaPencil fast preview shader failed");return MS::kFailure;}}
        MRenderTargetAssignment source;source.target=target->surface[0];if(!shader->setParameter("sceneColor",source))return MS::kFailure;
        source.target=target->surface[1];if(!shader->setParameter("sceneDepth",source))return MS::kFailure;
        float pixels[2]={float(w),float(h)};shader->setParameter("imageSize",pixels);
        shader->setParameter("lineWidth",width);shader->setParameter("creaseThreshold",crease);shader->setParameter("lineColor",color);
        auto context=getFrameContext();if(!context)return MS::kFailure;
        shader->setParameter("inverseProjection",context->getMatrix(MFrameContext::kProjectionMtx).inverse());
        MFrameContext::BackgroundParams background;context->getBackgroundParameters(background);
        float first[4]={background.clearColor1.r,background.clearColor1.g,background.clearColor1.b,background.clearColor1.a};
        float second[4]={background.clearColor2.r,background.clearColor2.g,background.clearColor2.b,background.clearColor2.a};
        auto& clear=scene.clearOperation();clear.setOverridesColors(true);clear.setClearColor(first);clear.setClearColor2(second);clear.setClearGradient(background.displayGradient);
        return MS::kSuccess;
    }
};
static Fast* instance=nullptr;
MStatus initializePlugin(MObject object){MFnPlugin plugin(object,"ReaPencil independent project","0.8.9","Any");auto renderer=MRenderer::theRenderer();if(!renderer)return MS::kFailure;instance=new Fast();return renderer->registerOverride(instance);}
MStatus uninitializePlugin(MObject){auto renderer=MRenderer::theRenderer();if(renderer&&instance)renderer->deregisterOverride(instance);delete instance;instance=nullptr;return MS::kSuccess;}
