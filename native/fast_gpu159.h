// Persistent authored-edge buffers. Camera frames change uniforms, never vertices.
#include <maya/MRenderUtilities.h>
#include <maya/MDrawContext.h>
#include "line_spatial159.h"
namespace fastGpu159 {
inline unsigned uploads=0,draws=0,builds=0;
struct Ref {unsigned mesh,edge;};
struct Batch {
 std::vector<Ref> refs;
 std::vector<float> points;
 std::unique_ptr<MVertexBuffer> vertices;
 std::unique_ptr<MIndexBuffer> indices;
 unsigned count=0;
 double low[3]={},high[3]={};
 bool ready=false;
};
struct Pipeline {
 std::vector<Batch> batches;std::vector<unsigned char> visibility;
 MShaderInstance* shader=nullptr;size_t signature=0;bool failed=false;
 const MBlendState* blend=nullptr;const MDepthStencilState* depth=nullptr;const MRasterizerState* raster=nullptr;
 ~Pipeline(){auto r=MRenderer::theRenderer();if(r&&shader)r->getShaderManager()->releaseShader(shader);if(blend)MStateManager::releaseBlendState(blend);if(depth)MStateManager::releaseDepthStencilState(depth);if(raster)MStateManager::releaseRasterizerState(raster);}
 void clear(){batches.clear();visibility.clear();signature=0;}
 bool program(){
  if(shader)return true;if(failed)return false;
  auto path=std::filesystem::path(effect).parent_path()/"fast_edges159.ogsfx";
  shader=MRenderer::theRenderer()->getShaderManager()->getEffectsFileShader(path.string().c_str(),"Main");
  if(!shader){failed=true;return false;}return true;
 }
 void update(std::vector<MarkedMesh>& meshes){
  for(auto& mesh:meshes){
   mesh.outputDirty=false;if(!mesh.path.isValid())continue;
   int divisions=mesh.smooth.level;bool changed=false;const double* points=nullptr;const float* floatPoints=nullptr;
   if(mesh.stamp->dirty||divisions<0){
    MFnMesh fn(mesh.path);fn.syncObject();if(fn.numVertices()!=mesh.vertices||fn.numEdges()!=mesh.edges){edgesDirty=true;continue;}
    MStatus status;points=fn.getRawDoublePoints(&status);if(!status||!points){points=nullptr;floatPoints=fn.getRawPoints(&status);if(!status||!floatPoints)continue;}++positionReads;
    divisions=0;MStatus ps;auto display=fn.findPlug("displaySmoothMesh",true,&ps);if(ps&&display.asInt()!=0)divisions=fn.findPlug("smoothLevel",true).asInt();
    if(mesh.smooth.level!=divisions){mesh.smooth.build(fn,divisions,mesh.pairs);mesh.worldReady=false;mesh.projectionReady=false;mesh.drawIndices.clear();++smoothBuilds;}
    changed=divisions&&mesh.smooth.ready&&mesh.smooth.update(fn,points,floatPoints,mesh.vertices);if(changed)++smoothUpdates;
    if(!divisions){
     if(!mesh.drawIndices.length()){mesh.baseVertices.clear();std::unordered_map<int,unsigned> remap;for(auto pair:mesh.pairs)for(int vertex:pair){auto e=remap.emplace(vertex,unsigned(remap.size()));if(e.second)mesh.baseVertices.push_back(vertex);mesh.drawIndices.append(e.first->second);}}
     mesh.basePoints.setLength(unsigned(mesh.baseVertices.size()));
     for(unsigned i=0;i<mesh.baseVertices.size();++i){int v=mesh.baseVertices[i]*3;mesh.basePoints[i]=MPoint(points?points[v]:floatPoints[v],points?points[v+1]:floatPoints[v+1],points?points[v+2]:floatPoints[v+2]);}
     changed=true;
    }
    mesh.stamp->dirty=false;
   }
   if(divisions&&!mesh.smooth.ready)continue;
   const auto& local=divisions?mesh.smooth.evaluated:mesh.basePoints;auto world=mesh.path.inclusiveMatrix();
   bool worldChanged=changed||!mesh.worldReady||world!=mesh.lastWorld;
   if(worldChanged){mesh.outputDirty=true;mesh.lastWorld=world;mesh.worldReady=true;mesh.world.setLength(local.length());
    for(unsigned i=0;i<local.length();++i){const auto& p=local[i];mesh.world[i]=MPoint(p.x*world[0][0]+p.y*world[1][0]+p.z*world[2][0]+world[3][0],p.x*world[0][1]+p.y*world[1][1]+p.z*world[2][1]+world[3][1],p.x*world[0][2]+p.y*world[1][2]+p.z*world[2][2]+world[3][2]);}}
   if(!mesh.drawIndices.length())for(auto pair:mesh.smooth.pairs){mesh.drawIndices.append(pair[0]);mesh.drawIndices.append(pair[1]);}
  }
 }
 void partition(const std::vector<MarkedMesh>& meshes){
  std::vector<Ref> refs;for(unsigned i=0;i<meshes.size();++i)if(meshes[i].worldReady)for(unsigned e=0;e<meshes[i].drawIndices.length()/2;++e)refs.push_back({i,e});
  auto order=lineSpatial159::stableMortonOrder(refs.size(),[&](size_t i){const auto& r=refs[i];const auto& m=meshes[r.mesh];const auto& a=m.world[m.drawIndices[2*r.edge]];const auto& b=m.world[m.drawIndices[2*r.edge+1]];return std::array<double,3>{(a.x+b.x)*.5,(a.y+b.y)*.5,(a.z+b.z)*.5};});
  batches.clear();constexpr size_t limit=131072;
  for(size_t first=0;first<order.size();first+=limit){batches.emplace_back();auto& b=batches.back();size_t n=std::min(limit,order.size()-first);b.refs.reserve(n);for(size_t j=0;j<n;++j)b.refs.push_back(refs[order[first+j]]);}
  visibility.clear();++builds;
 }
 bool draw(const MDrawContext& context,std::vector<MarkedMesh>& meshes){
  if(!program())return false;update(meshes);if(edgesDirty)return true;
  size_t next=1469598103934665603ull;for(const auto& m:meshes){next=(next^m.world.length())*1099511628211ull;next=(next^m.drawIndices.length())*1099511628211ull;}
  if(signature!=next){partition(meshes);signature=next;}
  MString panel,scope;context.renderingDestination(panel);MGlobal::executePythonCommand(MString("from reatoon import fast_targets; fast_targets.edge_scope('")+panel+"')",scope,false,false);
  std::vector<std::string> prefixes;std::istringstream stream(scope.asChar());std::string row;while(std::getline(stream,row))prefixes.push_back(row);
  std::vector<unsigned char> allowed(meshes.size());for(unsigned i=0;i<meshes.size();++i){const auto& m=meshes[i];if(!m.path.isValid()||!m.path.isVisible())continue;if(scope=="*"){allowed[i]=1;continue;}std::string name=m.path.fullPathName().asChar();for(const auto& p:prefixes)if(name==p||name.rfind(p+"|",0)==0){allowed[i]=1;break;}}
  bool membership=allowed!=visibility;visibility=allowed;
  MVertexBufferDescriptorList descriptors;shader->requiredVertexBuffers(descriptors);MVertexBufferDescriptor descriptor;
  bool havePosition=false;for(int i=0;i<descriptors.length();++i){descriptors.getDescriptor(i,descriptor);if(descriptor.semantic()==MGeometry::kPosition){havePosition=true;break;}}if(!havePosition||descriptor.dimension()!=3)return false;
  for(auto& batch:batches){
   bool dirty=!batch.ready;for(const auto& r:batch.refs)if(meshes[r.mesh].outputDirty){dirty=true;break;}
   if(dirty){
    batch.points.resize(batch.refs.size()*6);bool first=true;
    for(size_t i=0;i<batch.refs.size();++i){const auto& r=batch.refs[i];const auto& m=meshes[r.mesh];for(unsigned j=0;j<2;++j){const auto& p=m.world[m.drawIndices[r.edge*2+j]];double v[3]={p.x,p.y,p.z};for(int k=0;k<3;++k){float value=float(v[k]);batch.points[(i*2+j)*3+k]=value;if(first){batch.low[k]=batch.high[k]=value;}else{batch.low[k]=std::min(batch.low[k],double(value));batch.high[k]=std::max(batch.high[k],double(value));}}first=false;}}
    unsigned n=unsigned(batch.refs.size()*2);
    if(!batch.vertices){batch.vertices=std::make_unique<MVertexBuffer>(descriptor);auto p=batch.vertices->acquire(n,true);if(!p)return false;std::memcpy(p,batch.points.data(),batch.points.size()*sizeof(float));batch.vertices->commit(p);}
    else if(!batch.vertices->update(batch.points.data(),0,n,true))return false;
    ++uploads;
   }
   if(!batch.ready||membership){std::vector<unsigned> ids;ids.reserve(batch.refs.size()*2);for(unsigned i=0;i<batch.refs.size();++i)if(allowed[batch.refs[i].mesh]){ids.push_back(i*2);ids.push_back(i*2+1);}batch.count=unsigned(ids.size());if(batch.count){if(!batch.indices)batch.indices=std::make_unique<MIndexBuffer>(MGeometry::kUnsignedInt32);auto p=batch.indices->acquire(batch.count,true);if(!p)return false;std::memcpy(p,ids.data(),ids.size()*sizeof(unsigned));batch.indices->commit(p);}}
   batch.ready=true;
  }
  auto states=context.getStateManager();if(!states)return false;
  if(!blend){MBlendStateDesc b;b.targetBlends[0].blendEnable=true;b.targetBlends[0].sourceBlend=MBlendState::kSourceAlpha;b.targetBlends[0].destinationBlend=MBlendState::kInvSourceAlpha;blend=MStateManager::acquireBlendState(b);
   MDepthStencilStateDesc d;d.depthEnable=true;d.depthWriteEnable=false;d.depthFunc=MStateManager::kCompareLessEqual;depth=MStateManager::acquireDepthStencilState(d);MRasterizerStateDesc r;r.cullMode=MRasterizerState::kCullNone;raster=MStateManager::acquireRasterizerState(r);}
  auto oldBlend=states->getBlendState();auto oldDepth=states->getDepthStencilState();auto oldRaster=states->getRasterizerState();
  shader->setParameter("lineColor",color);shader->setParameter("lineWidth",width);
  bool ok=bool(shader->bind(context));if(ok)ok=bool(shader->activatePass(context,0));if(ok)shader->updateParameters(context);states->setBlendState(blend);states->setDepthStencilState(depth);states->setRasterizerState(raster);
  int x,y,w,h;context.getViewportDimensions(x,y,w,h);auto matrix=context.getMatrix(MFrameContext::kViewProjMtx);double vp[16];for(int i=0;i<16;++i)vp[i]=matrix[i/4][i%4];
  if(ok)for(auto& b:batches)if(b.count&&lineSpatial159::boundsVisible(b.low,b.high,vp,w,h,width)){if(!MRenderUtilities::drawSimpleMesh(const_cast<MDrawContext&>(context),*b.vertices,*b.indices,MGeometry::kLines,0,b.count)){ok=false;break;}++draws;}
  shader->unbind(context);states->setBlendState(oldBlend);states->setDepthStencilState(oldDepth);states->setRasterizerState(oldRaster);MStateManager::releaseBlendState(oldBlend);MStateManager::releaseDepthStencilState(oldDepth);MStateManager::releaseRasterizerState(oldRaster);
  return ok;
 }
};
}
