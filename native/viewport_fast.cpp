// Independent screen-space preview. Maya owns deformation and mesh drawing;
// Screen contours stay on GPU; optional authored-edge overlays fetch only marked meshes.
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
#include <sstream>
#include <unordered_set>
#include <maya/MObjectHandle.h>
#include <maya/MSelectionList.h>
#include <maya/MHWGeometry.h>
#include <maya/MFnSingleIndexedComponent.h>
#include <maya/MIntArray.h>
#include <maya/MFnMesh.h>
#include <maya/MItMeshEdge.h>
#include <maya/MUintArray.h>
#include <maya/MDoubleArray.h>
#include <maya/MUIDrawManager.h>
#include <maya/MPointArray.h>
#include <array>
#include <functional>
using namespace MHWRender;
static std::string effect;
static float width=1.5f,crease=.25f,color[4]={0,0,0,1};
static unsigned frames=0;
static MSelectionList selected;
static bool showHard=false,showCrease=false,edgesDirty=true;
static unsigned hardCount=0,creaseCount=0,edgeDraws=0;
extern "C" __declspec(dllexport) unsigned rp_fast_edge_draws(){return edgeDraws;}
extern "C" __declspec(dllexport) void rp_fast_edge_options(int hard,int crease){if(showHard!=bool(hard)||showCrease!=bool(crease))edgesDirty=true;showHard=hard;showCrease=crease;}
extern "C" __declspec(dllexport) void rp_fast_edges_dirty(){edgesDirty=true;}
extern "C" __declspec(dllexport) unsigned rp_fast_hard_count(){return hardCount;}
extern "C" __declspec(dllexport) unsigned rp_fast_crease_count(){return creaseCount;}
struct SelectionData {bool full=false;std::unordered_set<int> faces;std::unordered_map<unsigned,bool> decisions;};
static unsigned long long pathKey(const MDagPath& p){return (static_cast<unsigned long long>(MObjectHandle(p.node()).hashCode())<<32)|p.instanceNumber();}
static std::unordered_map<unsigned long long,SelectionData> selectedData;
extern "C" __declspec(dllexport) void rp_fast_targets(const char* text){
    edgesDirty=true;selected.clear();selectedData.clear();std::istringstream stream(text);std::string row;
    while(std::getline(stream,row))if(!row.empty())selected.add(row.c_str());
    for(unsigned i=0;i<selected.length();i++){
        MDagPath path;MObject part;selected.getDagPath(i,path,part);auto& data=selectedData[pathKey(path)];
        if(part.isNull())data.full=true;
        else {MIntArray ids;MFnSingleIndexedComponent(part).getElements(ids);for(unsigned j=0;j<ids.length();j++)data.faces.insert(ids[j]);}
    }
}
static bool targetAll=false;
extern "C" __declspec(dllexport) void rp_fast_all(int all){targetAll=all!=0;}
static int antialias=1;
extern "C" __declspec(dllexport) void rp_fast_antialias(int enabled){antialias=enabled;}
extern "C" __declspec(dllexport) void rp_fast_config(const char* path,float w,float c,const float* rgb){effect=path;width=w;crease=c;for(int i=0;i<3;i++)color[i]=rgb[i];}
extern "C" __declspec(dllexport) unsigned rp_fast_frames(){return frames;}
static std::function<void(MUIDrawManager&,const MFrameContext&)> drawMarked;
struct Targets {
    MRenderTarget* surface[2]={nullptr,nullptr};
    MRenderTarget* output[2]={nullptr,nullptr};
    MRenderTarget* final[2]={nullptr,nullptr};
    MRenderTarget* mask[2]={nullptr,nullptr};
    unsigned width=0,height=0;
    ~Targets(){auto renderer=MRenderer::theRenderer();if(!renderer)return;auto m=renderer->getRenderTargetManager();for(auto p:surface)if(p)m->releaseRenderTarget(p);if(output[0])m->releaseRenderTarget(output[0]);for(auto p:mask)if(p)m->releaseRenderTarget(p);}
    bool resize(const MString& name,unsigned w,unsigned h){
        if(width==w&&height==h)return true;
        auto m=MRenderer::theRenderer()->getRenderTargetManager();
        MRenderTarget** slots[]={&surface[0],&surface[1],&output[0],&mask[0],&mask[1]};
        for(int i=0;i<5;i++){
            MRenderTargetDescription desc(name+"_"+i,w,h,1,(i==1||i==4)?kD24S8:kR8G8B8A8_UNORM,0,false);
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
    bool hasUIDrawables()const override{return ui&&(showHard||showCrease);}
    void addPostUIDrawables(MUIDrawManager& draw,const MFrameContext& context)override{if(ui&&drawMarked)drawMarked(draw,context);}
    Scene(bool overlay):MSceneRender(overlay?"ReaPencil_fast_controls":"ReaPencil_fast_surface"),ui(overlay){}
    MRenderTarget* const* targetOverrideList(unsigned& count)override{count=2;return ui?targets->output:targets->surface;}
    MSceneFilterOption renderFilterOverride()override{return ui?kRenderUIItems:kRenderShadedItems;}
    MClearOperation& clearOperation()override{mClearOperation.setMask(ui?MClearOperation::kClearNone:MClearOperation::kClearAll);return mClearOperation;}
};
static void maskDraw(MDrawContext&,const MRenderItemList& items,MShaderInstance* shader){
    bool allowed=false;
    for(int j=0;j<items.length();j++){
        auto item=items.itemAt(j);auto path=item->sourceDagPath();if(!path.isValid())continue;
        auto found=selectedData.find(pathKey(path));if(found==selectedData.end())continue;
        auto& data=found->second;if(data.full){allowed=true;break;}
        auto shading=item->shadingComponent();if(shading.isNull())continue;
        unsigned hash=MObjectHandle(shading).hashCode();auto known=data.decisions.find(hash);
        bool matches=false;
        if(known!=data.decisions.end())matches=known->second;
        else {MIntArray faces;MFnSingleIndexedComponent(shading).getElements(faces);for(unsigned i=0;i<faces.length();i++)if(data.faces.count(faces[i])){matches=true;break;}if(data.decisions.size()>4096)data.decisions.clear();data.decisions[hash]=matches;}
        if(matches){allowed=true;break;}
    }
    shader->setParameter("maskAllowed",allowed);
}
class TargetMask:public MSceneRender {
public:
    Targets* targets=nullptr;MShaderInstance* program=nullptr;
    const MShaderInstance* shaderOverride()override{return program;}
    TargetMask():MSceneRender("ReaPencil_target_depth"){}
    MRenderTarget* const* targetOverrideList(unsigned& count)override{count=2;return targets->mask;}
    MSceneFilterOption renderFilterOverride()override{return kRenderOpaqueShadedItems;}
    const MSelectionList* objectSetOverride()override{return &selected;}
    MUint64 getObjectTypeExclusions()override{return selected.length()?kExcludeNurbsCurves|kExcludeLocators|kExcludeJoints:kExcludeAll;}
    MClearOperation& clearOperation()override{mClearOperation.setMask(MClearOperation::kClearAll);return mClearOperation;}
};
struct MarkedMesh {MDagPath path;int vertices=0,edges=0;std::vector<std::array<int,2>> pairs;};
class MarkedEdges:public MUserRenderOperation {
    std::vector<MarkedMesh> meshes;
public:
    Targets* targets=nullptr;MCameraOverride camera;
    const MCameraOverride* cameraOverride()override{return &camera;}
    MarkedEdges():MUserRenderOperation("ReaPencil_authored_edges"){}
    MRenderTarget* const* targetOverrideList(unsigned& count)override{count=2;return targets->final;}
    MStatus execute(const MDrawContext&)override{
        if(!edgesDirty)return MS::kSuccess;
        meshes.clear();hardCount=creaseCount=0;std::unordered_set<unsigned long long> done;
        for(unsigned i=0;i<selected.length();i++){
            MDagPath path;MObject part;selected.getDagPath(i,path,part);
            auto key=pathKey(path);if(!done.insert(key).second||!path.isValid())continue;
            auto data=selectedData.find(key);if(data==selectedData.end())continue;
            MFnMesh fn(path);MUintArray ids;MDoubleArray weights;std::unordered_set<int> creased;
            if(fn.getCreaseEdges(ids,weights))for(unsigned j=0;j<ids.length();j++)if(weights[j]>0)creased.insert(ids[j]);
            MarkedMesh mesh;mesh.path=path;mesh.vertices=fn.numVertices();mesh.edges=fn.numEdges();
            for(MItMeshEdge edge(path);!edge.isDone();edge.next()){
                bool hard=!edge.isSmooth(),crease=creased.count(edge.index())!=0;
                if(!(showHard&&hard)&&!(showCrease&&crease))continue;
                if(!data->second.full){MIntArray faces;edge.getConnectedFaces(faces);bool accepted=false;for(unsigned j=0;j<faces.length();j++)if(data->second.faces.count(faces[j]))accepted=true;if(!accepted)continue;}
                if(hard)++hardCount;if(crease)++creaseCount;
                mesh.pairs.push_back({edge.index(0),edge.index(1)});
            }
            if(!mesh.pairs.empty())meshes.push_back(std::move(mesh));
        }
        edgesDirty=false;return MS::kSuccess;
    }
    bool hasUIDrawables()const override{return false;}
    void addUIDrawables(MUIDrawManager& draw,const MFrameContext& context)override{
        MString panel,scope;context.renderingDestination(panel);
        MGlobal::executePythonCommand(MString("from reatoon import fast_targets; fast_targets.edge_scope('")+panel+"')",scope,false,false);
        std::vector<std::string> prefixes;std::istringstream stream(scope.asChar());std::string row;while(std::getline(stream,row))prefixes.push_back(row);
        ++edgeDraws;
        auto projection=context.getMatrix(MFrameContext::kViewProjMtx);auto inverse=projection.inverse();
        draw.beginDrawable(MUIDrawManager::kNonSelectable);draw.setColor(MColor(color[0],color[1],color[2],1));draw.setLineWidth(width);
        draw.setDepthPriority(MRenderItem::sDormantWireDepthPriority);
        for(auto& mesh:meshes){
            if(!mesh.path.isValid()||!mesh.path.isVisible())continue;
            if(scope!="*"){std::string path=mesh.path.fullPathName().asChar();bool allowed=false;for(auto& prefix:prefixes)if(path==prefix||path.rfind(prefix+"|",0)==0)allowed=true;if(!allowed)continue;}
            MFnMesh fn(mesh.path);fn.syncObject();if(fn.numVertices()!=mesh.vertices||fn.numEdges()!=mesh.edges){edgesDirty=true;continue;}MStatus status;const double* points=fn.getRawDoublePoints(&status);const float* floatPoints=nullptr;
            if(!status||!points){points=nullptr;floatPoints=fn.getRawPoints(&status);if(!status||!floatPoints)continue;}
            MMatrix bias;bias[3][2]=-4.0/16777215.0;auto matrix=mesh.path.inclusiveMatrix()*projection*bias*inverse;MPointArray output;
            for(auto pair:mesh.pairs)for(int vertex:pair){MPoint p=MPoint(points?points[vertex*3]:floatPoints[vertex*3],points?points[vertex*3+1]:floatPoints[vertex*3+1],points?points[vertex*3+2]:floatPoints[vertex*3+2])*matrix;p.cartesianize();output.append(p);}
            draw.lineList(output,false);
        }
        draw.endDrawable();
    }
};
class Composite:public MQuadRender {
public:
    Targets* targets=nullptr;MShaderInstance* program=nullptr;
    const MDepthStencilState* depth=nullptr;
    bool aa=false;
    Composite(bool filter=false):MQuadRender(filter?"ReaPencil_fast_antialias":"ReaPencil_fast_contours"),aa(filter){}
    ~Composite(){if(depth)MStateManager::releaseDepthStencilState(depth);}
    const MDepthStencilState* depthStencilStateOverride()override{if(!depth){MDepthStencilStateDesc d;d.depthEnable=false;d.depthWriteEnable=false;depth=MStateManager::acquireDepthStencilState(d);}return depth;}
    MRenderTarget* const* targetOverrideList(unsigned& count)override{count=1;return aa?targets->surface:targets->output;}
    const MShaderInstance* shader()override{if(program)++frames;return program;}
    MClearOperation& clearOperation()override{mClearOperation.setMask(MClearOperation::kClearNone);return mClearOperation;}
};
class HUD:public MHUDRender {
public:Targets* targets=nullptr;
    MRenderTarget* const* targetOverrideList(unsigned& count)override{count=2;return targets->final;}
};
class Present:public MPresentTarget {
public:Targets* targets=nullptr;
    Present():MPresentTarget("ReaPencil_fast_present"){setPresentDepth(true);}
    MRenderTarget* const* targetOverrideList(unsigned& count)override{count=2;return targets->final;}
};
class Fast:public MRenderOverride {
    Scene scene{false},ui{true};TargetMask mask;MarkedEdges edges;Composite composite,filter{true};HUD hud;Present present;
    MRenderOperation* ops[8]={&scene,&mask,&composite,&edges,&ui,&filter,&hud,&present};
    std::unordered_map<std::string,std::unique_ptr<Targets>> destinations;
    int cursor=0;
public:
    Fast():MRenderOverride("reaPencilFastPreview"){drawMarked=[this](MUIDrawManager& d,const MFrameContext& c){edges.addUIDrawables(d,c);};}
    ~Fast(){drawMarked=nullptr;if(MRenderer::theRenderer()){auto m=MRenderer::theRenderer()->getShaderManager();if(composite.program)m->releaseShader(composite.program);if(filter.program)m->releaseShader(filter.program);if(mask.program)m->releaseShader(mask.program);}}
    DrawAPI supportedDrawAPIs()const override{return kOpenGLCoreProfile;}
    MString uiName()const override{return "ReaPencil Fast Preview";}
    bool startOperationIterator()override{cursor=0;return true;}
    MRenderOperation* renderOperation()override{return cursor<8?ops[cursor]:nullptr;}
    bool nextRenderOperation()override{++cursor;if(cursor==1&&targetAll)++cursor;if(cursor==3&&!showHard&&!showCrease)++cursor;if(cursor==5&&!antialias)++cursor;return cursor<8;}
    MStatus setup(const MString& destination)override{
        if(!MGlobal::executePythonCommand("from reatoon import fast_targets; fast_targets.sync()",false,false))return MS::kFailure;
        auto renderer=MRenderer::theRenderer();unsigned w,h;renderer->outputTargetSize(w,h);
        if(!w||!h||effect.empty())return MS::kFailure;
        auto& storage=destinations[destination.asChar()];if(!storage)storage=std::make_unique<Targets>();
        if(!storage->resize(MString("ReaPencil_fast_")+destination,w,h))return MS::kFailure;
        auto target=storage.get();mask.targets=edges.targets=target;
        if(!mask.program)mask.program=renderer->getShaderManager()->getEffectsFileShader(effect.c_str(),"Mask",nullptr,0,true,maskDraw);
        if(!mask.program)return MS::kFailure;target->final[0]=antialias?target->surface[0]:target->output[0];target->final[1]=target->surface[1];scene.targets=ui.targets=composite.targets=filter.targets=hud.targets=present.targets=target;
        auto& shader=composite.program;
        if(!shader){shader=renderer->getShaderManager()->getEffectsFileShader(effect.c_str(),"Main");if(!shader){MGlobal::displayError("ReaPencil fast preview shader failed");return MS::kFailure;}}
        MRenderTargetAssignment source;source.target=target->surface[0];if(!shader->setParameter("sceneColor",source))return MS::kFailure;
        source.target=target->surface[1];if(!shader->setParameter("sceneDepth",source))return MS::kFailure;
        source.target=target->mask[1];if(!shader->setParameter("targetDepth",source))return MS::kFailure;
        shader->setParameter("targetAll",targetAll);
        float pixels[2]={float(w),float(h)};shader->setParameter("imageSize",pixels);
        shader->setParameter("lineWidth",width);shader->setParameter("creaseThreshold",crease);shader->setParameter("lineColor",color);
        if(antialias){
            if(!filter.program)filter.program=renderer->getShaderManager()->getEffectsFileShader(effect.c_str(),"AA");
            if(!filter.program)return MS::kFailure;
            MRenderTargetAssignment input;input.target=target->output[0];
            if(!filter.program->setParameter("sceneColor",input))return MS::kFailure;
            filter.program->setParameter("imageSize",pixels);
        }
        auto context=getFrameContext();if(!context)return MS::kFailure;edges.camera.mCameraPath=context->getCurrentCameraPath();
        shader->setParameter("inverseProjection",context->getMatrix(MFrameContext::kProjectionMtx).inverse());
        MFrameContext::BackgroundParams background;context->getBackgroundParameters(background);
        float first[4]={background.clearColor1.r,background.clearColor1.g,background.clearColor1.b,background.clearColor1.a};
        float second[4]={background.clearColor2.r,background.clearColor2.g,background.clearColor2.b,background.clearColor2.a};
        auto& clear=scene.clearOperation();clear.setOverridesColors(true);clear.setClearColor(first);clear.setClearColor2(second);clear.setClearGradient(background.displayGradient);
        return MS::kSuccess;
    }
};
static Fast* instance=nullptr;
MStatus initializePlugin(MObject object){MFnPlugin plugin(object,"ReaPencil independent project","0.8.13","Any");auto renderer=MRenderer::theRenderer();if(!renderer)return MS::kFailure;instance=new Fast();return renderer->registerOverride(instance);}
MStatus uninitializePlugin(MObject){auto renderer=MRenderer::theRenderer();if(renderer&&instance)renderer->deregisterOverride(instance);delete instance;instance=nullptr;return MS::kSuccess;}
