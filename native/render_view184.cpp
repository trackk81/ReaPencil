// Maya Render View adapter with bounded row-strip conversion, straight RGB/A.
#include <maya/MFnPlugin.h>
#include <maya/MPxCommand.h>
#include <maya/MArgList.h>
#include <maya/MRenderView.h>
#include <maya/MGlobal.h>
#include <fstream>
#include <filesystem>
#include <vector>
#include <algorithm>
#include <limits>
class DisplayImage184 : public MPxCommand {
public:
 static void* creator(){return new DisplayImage184;}
 MStatus doIt(const MArgList& args) override {
  if(args.length()!=3)return MS::kInvalidParameter;
  MStatus status;auto filename=args.asString(0,&status);if(!status)return status;
  int width=args.asInt(1,&status);if(!status)return status;
  int height=args.asInt(2,&status);if(!status||width<1||height<1)return MS::kInvalidParameter;
  if(!MRenderView::doesRenderEditorExist())return MS::kFailure;
  bool started=false;
  try {
   const size_t count=size_t(width)*size_t(height);
   if(count>size_t(std::numeric_limits<std::streamoff>::max()/4))return MS::kInvalidParameter;
   std::ifstream stream(std::filesystem::path(filename.asWChar()),std::ios::binary|std::ios::ate);
   if(!stream||stream.tellg()!=std::streamoff(count*4))return MS::kInvalidParameter;
   const size_t rows=std::min(height,64);
   std::vector<unsigned char> bytes(size_t(width)*rows*4);
   std::vector<RV_PIXEL> pixels(size_t(width)*rows);
   status=MRenderView::startRender(width,height,false,true);if(!status)return status;started=true;
   for(int y=0;y<height;){
    const int n=std::min(64,height-y);
    stream.seekg(std::streamoff(size_t(height-y-n)*size_t(width)*4));
    if(!stream.read(reinterpret_cast<char*>(bytes.data()),std::streamsize(size_t(width)*n*4))){status=MS::kFailure;break;}
    for(int row=0;row<n;++row)for(int x=0;x<width;++x){
     size_t src=(size_t(n-1-row)*width+x)*4;auto& p=pixels[size_t(row)*width+x];
     p.r=bytes[src];p.g=bytes[src+1];p.b=bytes[src+2];p.a=bytes[src+3];
    }
    status=MRenderView::updatePixels(0,width-1,y,y+n-1,pixels.data(),false);if(!status)break;
    y+=n;
   }
   if(status)status=MRenderView::refresh(0,width-1,0,height-1);
   auto end=MRenderView::endRender();started=false;return status?end:status;
  } catch(const std::exception& error){
   if(started)MRenderView::endRender();
   MGlobal::displayError(MString("ReaPencil image upload failed: ")+error.what());return MS::kFailure;
  }
 }
};
MStatus initializePlugin(MObject object){MFnPlugin plugin(object,"ReaPencil","0.8.64","Any");return plugin.registerCommand("revToonDisplayImage",DisplayImage184::creator);}
MStatus uninitializePlugin(MObject object){MFnPlugin plugin(object);return plugin.deregisterCommand("revToonDisplayImage");}
