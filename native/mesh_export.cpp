// Read-only evaluated mesh export. Maya API work remains on the calling thread.
#include <maya/MFnPlugin.h>
#include <maya/MPxCommand.h>
#include <maya/MSyntax.h>
#include <maya/MArgDatabase.h>
#include <maya/MSelectionList.h>
#include <maya/MDagPath.h>
#include <maya/MFnMesh.h>
#include <maya/MFnMeshData.h>
#include <maya/MMeshSmoothOptions.h>
#include <maya/MPointArray.h>
#include <maya/MFloatArray.h>
#include <maya/MIntArray.h>
#include <maya/MStringArray.h>
#include <maya/MMatrix.h>
#include <maya/MGlobal.h>
#include <maya/MDGModifier.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MFnSingleIndexedComponent.h>
#include <maya/MFnComponentListData.h>
#include <maya/MPlug.h>
#include <maya/MUintArray.h>
#include <maya/MDoubleArray.h>
#include <vector>
#include <stdexcept>
#include <fstream>
#include <filesystem>
#include <cstdint>
#include <cmath>
#include <algorithm>
#include <chrono>
#include <sstream>
#include <cstring>

// Maya commands execute serially on the main thread. The next export replaces
// this buffer; Python copies it before returning or evaluating another mesh.
static thread_local std::vector<char> exportBuffer;

static void check(MStatus s) {if(!s)throw std::runtime_error(s.errorString().asChar());}
static MPlug plug(MFnDependencyNode& node,const char* name) {
    MStatus status;MPlug value=node.findPlug(name,false,&status);check(status);return value;
}
static int subdivisionType(MFnMesh& source) {
    if(plug(source,"useGlobalSmoothDrawType").asBool()) {
        int value=0;check(MGlobal::executeCommand("optionVar -q globalPolyDefaultSmoothDrawType",value));
        const int types[]={0,2,3};
        if(value<0||value>2)throw std::runtime_error("Invalid global subdivision type");
        return types[value];
    }
    return plug(source,"smoothDrawType").asInt();
}
static bool legacyCreases(MFnMesh& source,const MString& purpose) {
    if(purpose!="render"||subdivisionType(source)!=0)return false;
    MUintArray ids;MDoubleArray values;
    if(source.getCreaseEdges(ids,values))for(unsigned i=0;i<values.length();++i)if(values[i]>0)return true;
    values.clear();ids.clear();
    if(source.getCreaseVertices(ids,values))for(unsigned i=0;i<values.length();++i)if(values[i]>0)return true;
    return false;
}
static MObject legacySmooth(MFnMesh& source,MObject inputOwner,int divisions,MObject& outputOwner) {
    // Do not call doIt: the evaluation node must never join the scene DG.
    MStatus status;MDGModifier modifier;
    MObject object=modifier.createNode("polySmoothFace",&status);check(status);
    MFnDependencyNode node(object,&status);check(status);
    check(plug(node,"inputPolymesh").setMObject(inputOwner));
    MFnSingleIndexedComponent componentFn;
    MObject component=componentFn.create(MFn::kMeshPolygonComponent,&status);check(status);
    check(componentFn.setCompleteData(source.numPolygons()));
    MFnComponentListData list;MObject components=list.create(&status);check(status);check(list.add(component));
    check(plug(node,"inputComponents").setMObject(components));
    for(const char* name:{"useInputComp","maya65Above","maya2008Above","useOsdBoundaryMethods","osdIndependentUVChannels"})check(plug(node,name).setBool(true));
    check(plug(node,"method").setInt(0));check(plug(node,"divisions").setInt(divisions));
    check(plug(node,"subdivisionType").setInt(subdivisionType(source)));
    check(plug(node,"continuity").setDouble(plug(source,"continuity").asDouble()));
    for(const char* name:{"boundaryRule","keepMapBorders","osdVertBoundary","osdFvarBoundary","osdCreaseMethod"})check(plug(node,name).setInt(plug(source,name).asInt()));
    for(const char* name:{"propagateEdgeHardness","keepBorder","keepHardEdge","osdFvarPropagateCorners","osdSmoothTriangles"})check(plug(node,name).setBool(plug(source,name).asBool()));
    check(plug(node,"smoothUVs").setBool(false));
    MObject output=plug(node,"output").asMObject(&status);check(status);
    MFnMeshData data;outputOwner=data.create(&status);check(status);
    MFnMesh copy;MObject result=copy.copy(output,outputOwner,&status);check(status);return result;
}
template<class T> static void write(std::ofstream& out,const std::vector<T>& v) {
    if(!v.empty())out.write(reinterpret_cast<const char*>(v.data()),v.size()*sizeof(T));
}
static std::vector<uint32_t> ints(const MIntArray& input) {
    std::vector<uint32_t> out(input.length());
    for(unsigned i=0;i<input.length();++i){if(input[i]<0)throw std::runtime_error("Negative mesh index");out[i]=input[i];}
    return out;
}
class ExportMesh: public MPxCommand {
public:
    static void* creator(){return new ExportMesh;}
    static MSyntax syntax(){MSyntax s;s.addFlag("-m","-mesh",MSyntax::kString);s.addFlag("-d","-divisions",MSyntax::kLong);s.addFlag("-o","-output",MSyntax::kString);s.addFlag("-p","-purpose",MSyntax::kString);s.addFlag("-u","-uniform",MSyntax::kBoolean);s.addFlag("-mem","-memory",MSyntax::kBoolean);s.addFlag("-pr","-profile",MSyntax::kBoolean);return s;}
    bool isUndoable()const override{return false;}
    MStatus doIt(const MArgList& args)override {
        try {
            // MArgDatabase retains syntax storage: keep it alive through every flag query.
            MStatus status;MSyntax commandSyntax=syntax();MArgDatabase db(commandSyntax,args,&status);check(status);
            auto started=std::chrono::steady_clock::now();
            MDoubleArray timings;auto mark=[&](){timings.append(std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count());};
            MString meshName,filename,purpose="render";int divisions=0;
            check(db.getFlagArgument("-m",0,meshName));
            bool memory=false,profile=false;if(db.isFlagSet("-mem"))check(db.getFlagArgument("-mem",0,memory));if(db.isFlagSet("-pr"))check(db.getFlagArgument("-pr",0,profile));
            if(!memory)check(db.getFlagArgument("-o",0,filename));
            if(db.isFlagSet("-d"))check(db.getFlagArgument("-d",0,divisions));
            if(db.isFlagSet("-p"))check(db.getFlagArgument("-p",0,purpose));
            bool uniform=false;if(db.isFlagSet("-u"))check(db.getFlagArgument("-u",0,uniform));
            if(purpose!="render"&&purpose!="viewport")throw std::runtime_error("Invalid geometry purpose");
            if(divisions<0||divisions>8)throw std::runtime_error("Invalid subdivision level");
            MSelectionList selection;check(selection.add(meshName));MDagPath path;check(selection.getDagPath(0,path));
            if(path.node().hasFn(MFn::kTransform))check(path.extendToShape());
            MFnMesh source(path,&status);check(status);
            MIntArray baseCounts,baseIndices;check(source.getVertices(baseCounts,baseIndices));
            const uint64_t baseFaces=source.numPolygons(),baseVertices=source.numVertices(),baseEdges=source.numEdges();
            MObject copyOwner,smoothOwner,evaluated=source.object();MString uvSet;
            if(divisions) {
                uint64_t expected=baseIndices.length();for(int i=1;i<divisions;++i)expected*=4;
                if(expected>2000000)throw std::runtime_error("Subdivision exceeds the 2 million faces per-mesh budget");
                MFnMeshData data;
                MMeshSmoothOptions directOptions;check(source.getSmoothMeshDisplayOptions(directOptions));directOptions.setDivisions(divisions);directOptions.setSmoothUVs(false);
                if(uniform&&!legacyCreases(source,purpose)) {
                    smoothOwner=data.create(&status);check(status);
                    evaluated=source.generateSmoothMesh(smoothOwner,&directOptions,&status);check(status);
                } else {
                copyOwner=data.create(&status);check(status);
                MFnMesh copier;MObject copyObject=copier.copy(source.object(),copyOwner,&status);check(status);
                MFnMesh copy(copyObject,&status);check(status);MStringArray sets;check(copy.getUVSetNames(sets));
                if(uniform)for(unsigned i=0;i<sets.length();++i)check(copy.clearUVs(&sets[i]));
                if(!uniform) {
                if(!sets.length())throw std::runtime_error("No UV set for subdivision provenance");uvSet=sets[0];
                check(copy.clearUVs(&uvSet));MFloatArray u,v;MIntArray uvIds;
                u.setLength(baseIndices.length());v.setLength(baseIndices.length());uvIds.setLength(baseIndices.length());
                unsigned cursor=0;for(unsigned f=0;f<baseCounts.length();++f)for(int c=0;c<baseCounts[f];++c){u[cursor]=float(f);v[cursor]=float(c);uvIds[cursor]=cursor;++cursor;}
                check(copy.setUVs(u,v,&uvSet));check(copy.assignUVs(baseCounts,uvIds,&uvSet));
                }
                MMeshSmoothOptions options;check(source.getSmoothMeshDisplayOptions(options));options.setDivisions(divisions);options.setSmoothUVs(false);
                if(legacyCreases(source,purpose))evaluated=legacySmooth(source,copyOwner,divisions,smoothOwner);
                else {smoothOwner=data.create(&status);check(status);evaluated=copy.generateSmoothMesh(smoothOwner,&options,&status);check(status);}
                }
            }
            mark();
            MFnMesh fn(evaluated,&status);check(status);
            MPointArray points;check(fn.getPoints(points,MSpace::kObject));MMatrix matrix=path.inclusiveMatrix(&status);check(status);
            std::vector<double> xyz(points.length()*3);for(unsigned i=0;i<points.length();++i){MPoint p=points[i]*matrix;xyz[i*3]=p.x;xyz[i*3+1]=p.y;xyz[i*3+2]=p.z;}
            mark();
            MIntArray counts,indices,triCounts,triIndices;check(fn.getVertices(counts,indices));check(fn.getTriangles(triCounts,triIndices));
            mark();
            std::vector<uint32_t> provenance(counts.length());
            if(divisions&&!uniform) {
                MIntArray uvCounts,uvIds;MFloatArray u,v;check(fn.getAssignedUVs(uvCounts,uvIds,&uvSet));check(fn.getUVs(u,v,&uvSet));
                if(uvCounts.length()!=counts.length())throw std::runtime_error("Subdivision provenance face count differs");
                unsigned cursor=0;
                for(unsigned f=0;f<counts.length();++f){
                    if(uvCounts[f]!=counts[f]||counts[f]<1)throw std::runtime_error("Missing subdivision provenance corners");
                    double original=std::nearbyint(double(u[uvIds[cursor]]));
                    if(!std::isfinite(original)||original<0||original>=baseFaces)throw std::runtime_error("Invalid subdivision source face");
                    float id=float(original);double ulp=double(std::nextafter(id,INFINITY))-id;
                    double tolerance=std::max(1e-6,std::min(.125,4*std::abs(ulp)));
                    for(int c=0;c<counts[f];++c){double value=u[uvIds[cursor++]];if(!std::isfinite(value)||std::nearbyint(value)!=original||std::abs(value-original)>tolerance)throw std::runtime_error("Mixed subdivision source face");}
                    provenance[f]=uint32_t(original);
                }
            } else for(unsigned f=0;f<counts.length();++f)provenance[f]=divisions?0:f;
            mark();
            std::vector<uint32_t> triangleFaces;triangleFaces.reserve(triIndices.length()/3);
            for(unsigned f=0;f<triCounts.length();++f)for(int t=0;t<triCounts[f];++t)triangleFaces.push_back(f);
            std::vector<uint32_t> hard;for(int e=0;e<fn.numEdges();++e)if(!fn.isEdgeSmooth(e,&status)){check(status);int2 pair;check(fn.getEdgeVertices(e,pair));hard.push_back(pair[0]);hard.push_back(pair[1]);}
            mark();
            const char magic[8]={'R','T','M','E','S','H','0','1'};
            std::vector<uint64_t> header={points.length(),counts.length(),indices.length(),triIndices.length()/3,hard.size()/2,baseFaces,baseVertices,baseEdges,uint64_t(divisions)};
            if(memory){
                exportBuffer.resize(80+xyz.size()*8+(counts.length()+indices.length()+triIndices.length()+triangleFaces.size()+provenance.size()+hard.size())*4);
                size_t cursor=0;auto append=[&](const void* ptr,size_t bytes){if(bytes)std::memcpy(exportBuffer.data()+cursor,ptr,bytes);cursor+=bytes;};
                append(magic,8);append(header.data(),72);append(xyz.data(),xyz.size()*8);
                for(const MIntArray* array:{&counts,&indices,&triIndices}){auto converted=ints(*array);append(converted.data(),converted.size()*4);}
                for(const auto* array:{&triangleFaces,&provenance,&hard})append(array->data(),array->size()*4);
                mark();std::ostringstream result;result.precision(17);result<<"["<<reinterpret_cast<uintptr_t>(exportBuffer.data())<<","<<exportBuffer.size()<<",[";
                for(unsigned i=0;i<timings.length();++i){if(i)result<<",";result<<timings[i];}result<<"]]";setResult(MString(result.str().c_str()));
            }else{
                std::ofstream out(std::filesystem::u8path(filename.asUTF8()),std::ios::binary|std::ios::trunc);
                if(!out)throw std::runtime_error("Cannot open mesh output");out.write(magic,8);
                write(out,header);write(out,xyz);write(out,ints(counts));write(out,ints(indices));write(out,ints(triIndices));write(out,triangleFaces);write(out,provenance);write(out,hard);
                out.close();if(!out)throw std::runtime_error("Mesh output write failed");mark();if(profile)setResult(timings);else setResult(filename);
            }
            return MS::kSuccess;
        } catch(const std::exception& e){MGlobal::displayError(MString("RevToon native mesh export: ")+e.what());return MS::kFailure;}
    }
};
MStatus initializePlugin(MObject obj){MFnPlugin plugin(obj,"RevToon independent project","0.7.4","Any");return plugin.registerCommand("revToonExportMesh",ExportMesh::creator,ExportMesh::syntax);}
MStatus uninitializePlugin(MObject obj){MFnPlugin plugin(obj);return plugin.deregisterCommand("revToonExportMesh");}
