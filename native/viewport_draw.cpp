// Native bulk endpoint transfer + VP2 draw adapter. Geometry is computed by
// OpenCL, offline rendering stays in the unchanged Python/NumPy CPU renderer.
#include <maya/MFnPlugin.h>
#include <maya/MGlobal.h>
#include <maya/MDrawRegistry.h>
#include <maya/MPxDrawOverride.h>
#include <maya/MUIDrawManager.h>
#include <maya/MFrameContext.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MPlug.h>
#include <maya/MPointArray.h>
#include <maya/MUserData.h>
#include <maya/MHWGeometry.h>
#include <maya/MMatrix.h>
#include <maya/MDagPath.h>
#include <memory>
#include <vector>
#include <string>
#include <sstream>
#include <cmath>

using namespace MHWRender;
struct Group {
    MPointArray points;
    MColor color, hiddenColor;
    float width;
    bool hidden, dashed;
    Group(const double* p, unsigned count, float w, const float* c, bool h, const float* hc, bool d)
        :points(reinterpret_cast<const double(*)[4]>(p),count),
         color(c[0],c[1],c[2],1),hiddenColor(hc[0],hc[1],hc[2],1),width(w),hidden(h),dashed(d){}
};
struct Frame {std::vector<Group> groups;};
static std::shared_ptr<Frame> pending, current;
static MMatrix viewProjection;
static int viewWidth=0,viewHeight=0;
extern "C" __declspec(dllexport) int rt_view_projection(double* matrix,int* width,int* height) {
    if(!matrix||!width||!height||viewWidth<=0||viewHeight<=0)return 0;
    for(int r=0;r<4;r++)for(int c=0;c<4;c++)matrix[4*r+c]=viewProjection(r,c);
    *width=viewWidth;*height=viewHeight;return 1;
}
// Called synchronously by our Python prepare callback on Maya's main thread.
// Addresses come only from owned contiguous NumPy arrays and are copied here.
extern "C" __declspec(dllexport) void rt_begin() {pending=std::make_shared<Frame>();}
extern "C" __declspec(dllexport) int rt_add(const double* points, unsigned count, float width,
    const float* color,int hidden,const float* hiddenColor,int dashed) {
    if(!pending||!points||!color||!hiddenColor||count>2097152||count%2||!std::isfinite(width))return 0;
    try {pending->groups.emplace_back(points,count,width,color,hidden!=0,hiddenColor,dashed!=0);return 1;}
    catch(...){pending.reset();return 0;}
}
extern "C" __declspec(dllexport) void rt_end() {current=pending;pending.reset();}
struct Data: MUserData {
    std::shared_ptr<Frame> frame;
    Data():MUserData(false){}
};
static std::string quoted(const MString& text) {
    std::string out="\"";
    for(char c:std::string(text.asChar())) {if(c=='\\'||c=='\"')out+='\\';out+=c;}
    return out+"\"";
}
class Draw:public MPxDrawOverride {
public:
    explicit Draw(const MObject& obj):MPxDrawOverride(obj,nullptr,true){}
    static MPxDrawOverride* create(const MObject& obj){return new Draw(obj);}
    DrawAPI supportedDrawAPIs()const override{return DrawAPI(kOpenGL|kOpenGLCoreProfile|kDirectX11);}
    bool hasUIDrawables()const override{return true;}
    bool isBounded(const MDagPath&,const MDagPath&)const override{return false;}
    bool disableInternalBoundingBoxDraw()const override{return true;}
    MMatrix transform(const MDagPath&,const MDagPath&)const override{return MMatrix::identity;}
    MUserData* prepareForDraw(const MDagPath& object,const MDagPath& camera,
                             const MFrameContext& context,MUserData* old)override {
        Data* data=dynamic_cast<Data*>(old);if(!data)data=new Data;
        MStatus status;
        bool enabled=MFnDependencyNode(object.node()).findPlug("linePreviewEnabled",true,&status).asBool();
        if(!status||!enabled){data->frame.reset();return data;}
        int x=0,y=0,w=1,h=1;context.getViewportDimensions(x,y,w,h);
        viewProjection=context.getMatrix(MFrameContext::kViewProjMtx,&status);
        viewWidth=status?w:0;viewHeight=status?h:0;
        std::ostringstream code;
        code<<"import reatoon.viewport as _rt_vp; _rt_vp._native_prepare("<<quoted(camera.fullPathName())<<","<<double(w)/std::max(h,1)<<")";
        status=MGlobal::executePythonCommand(MString(code.str().c_str()),false,false);
        data->frame=status?current:nullptr;
        return data;
    }
    void addUIDrawables(const MDagPath&,MUIDrawManager& draw,const MFrameContext&,const MUserData* input)override {
        auto data=dynamic_cast<const Data*>(input);if(!data||!data->frame)return;
        draw.beginDrawable(MUIDrawManager::kNonSelectable);
        bool anyHidden=false;for(auto& g:data->frame->groups)anyHidden|=g.hidden;
        if(anyHidden) {
            draw.beginDrawInXray();
            for(auto& g:data->frame->groups)if(g.hidden) {
                draw.setLineWidth(g.width);draw.setColor(g.hiddenColor);draw.setLineStyle(MUIDrawManager::kDashed);
                draw.mesh(MUIDrawManager::kLines,g.points);
            }
            draw.endDrawInXray();
        }
        for(auto& g:data->frame->groups) {
            draw.setLineWidth(g.width);draw.setColor(g.color);
            draw.setLineStyle(g.dashed?MUIDrawManager::kDashed:MUIDrawManager::kSolid);
            draw.setDepthPriority(MRenderItem::sDormantWireDepthPriority);
            draw.lineList(g.points,false);
        }
        draw.endDrawable();
    }
};
static const MString classification("drawdb/geometry/reaToonViewport");
static const MString registrant("RevToonNativeGPUTransfer");
MStatus initializePlugin(MObject object) {
    MFnPlugin plugin(object,"ReaPencil independent project","0.8.1","Any");
    return MDrawRegistry::registerDrawOverrideCreator(classification,registrant,Draw::create);
}
MStatus uninitializePlugin(MObject) {
    MStatus status=MDrawRegistry::deregisterDrawOverrideCreator(classification,registrant);
    current.reset();pending.reset();return status;
}
