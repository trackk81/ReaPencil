// Independent public Maya Render View adapter. No image premultiplication.
#include <maya/MFnPlugin.h>
#include <maya/MPxCommand.h>
#include <maya/MArgList.h>
#include <maya/MRenderView.h>
#include <maya/MGlobal.h>
#include <fstream>
#include <filesystem>
#include <vector>

class DisplayImage : public MPxCommand {
public:
    static void* creator() { return new DisplayImage; }
    MStatus doIt(const MArgList& args) override {
        if(args.length()!=3) return MS::kInvalidParameter;
        MStatus status;
        MString filename=args.asString(0,&status); if(!status)return status;
        int width=args.asInt(1,&status); if(!status)return status;
        int height=args.asInt(2,&status); if(!status)return status;
        if(width<1||height<1||width>8192||height>8192||
            size_t(width)*height>16777216) return MS::kInvalidParameter;
        if(!MRenderView::doesRenderEditorExist())return MS::kFailure;
        try {
            size_t count=size_t(width)*height;
            std::ifstream stream(std::filesystem::path(filename.asWChar()),std::ios::binary|std::ios::ate);
            if(!stream||stream.tellg()!=std::streamoff(count*4))return MS::kInvalidParameter;
            stream.seekg(0);
            std::vector<unsigned char> bytes(count*4);
            if(!stream.read(reinterpret_cast<char*>(bytes.data()),bytes.size()))return MS::kFailure;
            std::vector<RV_PIXEL> pixels(count);
            for(int y=0;y<height;++y)for(int x=0;x<width;++x) {
                size_t src=(size_t(height-1-y)*width+x)*4;
                auto& pixel=pixels[size_t(y)*width+x];
                pixel.r=bytes[src];pixel.g=bytes[src+1];pixel.b=bytes[src+2];pixel.a=bytes[src+3];
            }
            status=MRenderView::startRender(width,height,false,true);
            if(!status)return status;
            status=MRenderView::updatePixels(0,width-1,0,height-1,pixels.data(),false);
            if(status)status=MRenderView::refresh(0,width-1,0,height-1);
            MStatus endStatus=MRenderView::endRender();
            return status?endStatus:status;
        } catch(const std::exception& error) {
            MGlobal::displayError(MString("RevToon image upload failed: ")+error.what());
            return MS::kFailure;
        }
    }
};
MStatus initializePlugin(MObject object) {
    MFnPlugin plugin(object,"RevToon","0.7.0","Any");
    return plugin.registerCommand("revToonDisplayImage",DisplayImage::creator);
}
MStatus uninitializePlugin(MObject object) {
    MFnPlugin plugin(object);return plugin.deregisterCommand("revToonDisplayImage");
}
