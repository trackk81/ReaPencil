// Cached sparse Catmull-Clark stencils for authored-edge positions only.
#include <opensubdiv/far/topologyDescriptor.h>
#include <opensubdiv/far/topologyRefinerFactory.h>
#include <opensubdiv/far/stencilTableFactory.h>
#include <maya/MFnDependencyNode.h>
#include <maya/MPlug.h>
#include <maya/MFloatArray.h>
#include <maya/MFnMeshData.h>
#include <algorithm>
#include <cmath>
#include "fast_edge_disk.h"
namespace edgeSmooth {
inline unsigned legacyMapped=0,legacyRejected=0,legacyEvaluations=0;
namespace Far=OpenSubdiv::Far; namespace Sdc=OpenSubdiv::Sdc;
struct Stencil {std::vector<int> ids;std::vector<float> weights;};
struct Cache {
 bool legacyStencils(MFnMesh& fn,MMeshSmoothOptions& options,const MIntArray& counts,const MIntArray& indices,const std::vector<std::array<int,2>>& marked,const MIntArray& mapped,bool broad=false){
  if(level>3)return false;
  std::string memoKey;auto add=[&](const auto* p,size_t n){memoKey.append(reinterpret_cast<const char*>(p),n);};
  int lengths[]={fn.numVertices(),int(counts.length()),int(indices.length()),int(mapped.length())};add(lengths,sizeof(lengths));add(&level,sizeof(level));for(int v:counts)add(&v,sizeof(v));for(int v:indices)add(&v,sizeof(v));for(int v:mapped)add(&v,sizeof(v));
  int settings[]={int(options.subdivisionType()),int(options.boundaryRule()),int(options.openSubdivVertexBoundary()),int(options.openSubdivCreaseMethod()),int(options.keepBorderEdge()),int(options.keepHardEdge()),int(options.openSubdivSmoothTriangles())};add(settings,sizeof(settings));float continuity=options.smoothness();add(&continuity,sizeof(continuity));
  MUintArray cids;MDoubleArray cweights;fn.getCreaseEdges(cids,cweights);unsigned creaseSize=cids.length();add(&creaseSize,sizeof(creaseSize));for(unsigned i=0;i<cids.length();++i){unsigned id=cids[i];double w=cweights[i];add(&id,sizeof(id));add(&w,sizeof(w));}int separator=-12345;add(&separator,sizeof(separator));fn.getCreaseVertices(cids,cweights);creaseSize=cids.length();add(&creaseSize,sizeof(creaseSize));for(unsigned i=0;i<cids.length();++i){unsigned id=cids[i];double w=cweights[i];add(&id,sizeof(id));add(&w,sizeof(w));}for(int e=0;e<fn.numEdges();++e){char hard=!fn.isEdgeSmooth(e);add(&hard,1);}
  static std::unordered_map<std::string,std::vector<Stencil>> memo;
  auto hit=memo.find(memoKey);if(hit!=memo.end()){stencils=hit->second;fallback=false;return true;}
  const int n=fn.numVertices();std::vector<std::unordered_set<int>> adjacency(n);int offset=0;
  for(int count:counts){for(int a=0;a<count;++a)for(int b=0;b<count;++b)adjacency[indices[offset+a]].insert(indices[offset+b]);offset+=count;}
  std::vector<std::unordered_set<int>> support(fallbackVertices.size());std::unordered_map<int,int> compact;for(unsigned i=0;i<fallbackVertices.size();++i)compact[fallbackVertices[i]]=int(i);
  // Uncreased Catmull-Clark gives a conservative sparse support for all
  // legacy crease weights. Union supports along each source edge; unlike a
  // broad face-neighborhood this avoids coloring unrelated source vertices.
  std::vector<int> cs(counts.begin(),counts.end()),vs(indices.begin(),indices.end());
  Far::TopologyDescriptor desc;desc.numVertices=n;desc.numFaces=int(cs.size());desc.numVertsPerFace=cs.data();desc.vertIndicesPerFace=vs.data();
  Sdc::Options sd;sd.SetVtxBoundaryInterpolation(Sdc::Options::VTX_BOUNDARY_EDGE_ONLY);
  Far::TopologyRefinerFactory<Far::TopologyDescriptor>::Options factory(Sdc::SCHEME_CATMARK,sd);
  std::unique_ptr<Far::TopologyRefiner> ref(Far::TopologyRefinerFactory<Far::TopologyDescriptor>::Create(desc,factory));if(!ref)return false;
  Far::TopologyRefiner::UniformOptions uniform(level);uniform.fullTopologyInLastLevel=true;ref->RefineUniform(uniform);
  Far::StencilTableFactory::Options opt;opt.generateIntermediateLevels=false;opt.generateOffsets=true;
  std::unique_ptr<const Far::StencilTable> table(Far::StencilTableFactory::Create(*ref,opt));if(!table)return false;
  unsigned cursor=0;for(auto edge:marked){
   std::vector<int> children;auto& base=ref->GetLevel(0);for(int e:base.GetVertexEdges(edge[0])){auto v=base.GetEdgeVertices(e);if(v[0]==edge[1]||v[1]==edge[1]){children.push_back(e);break;}}
   for(int l=0;l<level;++l){std::vector<int> next;for(int e:children)for(int c:ref->GetLevel(l).GetEdgeChildEdges(e))next.push_back(c);children.swap(next);}
   if(!broad){
    auto chain=[](const std::vector<std::array<int,2>>& edges){std::unordered_map<int,std::vector<int>> graph;for(auto p:edges){graph[p[0]].push_back(p[1]);graph[p[1]].push_back(p[0]);}int start=-1;for(auto& row:graph)if(row.second.size()==1&&(start<0||row.first<start))start=row.first;std::vector<int> result;if(start<0)return result;int prev=-1,current=start;for(size_t i=0;i<=edges.size();++i){result.push_back(current);int next=-1;for(int v:graph[current])if(v!=prev){next=v;break;}if(next<0)break;prev=current;current=next;}return result;};
    std::vector<std::array<int,2>> originalChildren,osdChildren;
    for(int i=0;i<(1<<level)*2&&cursor+unsigned(i+1)<mapped.length();i+=2)originalChildren.push_back({mapped[cursor+i],mapped[cursor+i+1]});
    for(int e:children){auto v=ref->GetLevel(level).GetEdgeVertices(e);osdChildren.push_back({v[0],v[1]});}
    auto mc=chain(originalChildren),oc=chain(osdChildren);if(mc.size()!=oc.size()||mc.empty())return false;
    // Orientation-free source support: each child can be at j or mirrored j.
    for(unsigned j=0;j<mc.size();++j){auto& group=support[compact[mc[j]]];for(unsigned k:{j,unsigned(mc.size()-1-j)}){auto stencil=table->GetStencil(oc[k]);for(int i=0;i<stencil.GetSize();++i)group.insert(stencil.GetVertexIndices()[i]);}}
    cursor+=unsigned((1<<level)*2);continue;
   }
   std::unordered_set<int> neighborhood;
   if(broad){neighborhood={edge[0],edge[1]};for(int l=0;l<level;++l){auto next=neighborhood;for(int v:neighborhood)next.insert(adjacency[v].begin(),adjacency[v].end());neighborhood.swap(next);}}
   for(int k=0;k<(1<<level)*2&&cursor<mapped.length();++k,++cursor){auto& group=support[compact[mapped[cursor]]];group.insert(neighborhood.begin(),neighborhood.end());}
  }
  std::vector<std::vector<int>> membership(n);for(unsigned i=0;i<support.size();++i)for(int v:support[i])membership[v].push_back(int(i));
  int words=(n+63)/64;std::vector<std::vector<unsigned long long>> used(support.size(),std::vector<unsigned long long>(words));std::vector<int> colors(n,-1),order(n);for(int i=0;i<n;++i)order[i]=i;std::sort(order.begin(),order.end(),[&](int a,int b){return membership[a].size()>membership[b].size();});int colorCount=0;
  for(int v:order){if(membership[v].empty())continue;std::vector<unsigned long long> forbidden(words);for(int group:membership[v])for(int w=0;w<words;++w)forbidden[w]|=used[group][w];int c=0;while(forbidden[c/64]&(1ull<<(c%64)))++c;colors[v]=c;colorCount=std::max(colorCount,c+1);for(int group:membership[v])used[group][c/64]|=1ull<<(c%64);}
  MObject inputOwner=MFnMeshData().create();MFnMesh copy;copy.copy(fn.object(),inputOwner);MPointArray basis;basis.setLength(n);std::vector<Stencil> candidate(support.size());options.setDivisions(level);options.setSmoothUVs(false);
  auto evaluate=[&](MPointArray& output){MObject owner=MFnMeshData().create();MStatus status;MObject object=copy.generateSmoothMesh(owner,&options,&status);if(!status)return false;MFnMesh smooth(object);return bool(smooth.getPoints(output,MSpace::kObject));};
  for(int batch=0;batch<colorCount;batch+=3){for(int v=0;v<n;++v)basis[v]=MPoint(colors[v]==batch?1.:0.,colors[v]==batch+1?1.:0.,colors[v]==batch+2?1.:0.);if(!copy.setPoints(basis,MSpace::kObject))return false;MPointArray values;if(!evaluate(values))return false;for(unsigned i=0;i<support.size();++i){MPoint p=values[fallbackVertices[i]];double component[3]={p.x,p.y,p.z};for(int v:support[i])if(colors[v]>=batch&&colors[v]<batch+3){double weight=component[colors[v]-batch];if(std::abs(weight)>1e-12){candidate[i].ids.push_back(v);candidate[i].weights.push_back(float(weight));}}}}
  // Verify the recovered sparse linear map on non-coincident random positions.
  for(int v=0;v<n;++v)basis[v]=MPoint(std::sin(v*.137),std::cos(v*.319),std::sin(v*.731));copy.setPoints(basis,MSpace::kObject);MPointArray oracle;if(!evaluate(oracle))return false;
  for(unsigned i=0;i<candidate.size();++i){MPoint p(0,0,0);double sum=0;auto& stencil=candidate[i];for(unsigned j=0;j<stencil.ids.size();++j){auto q=basis[stencil.ids[j]];double w=stencil.weights[j];p.x+=q.x*w;p.y+=q.y*w;p.z+=q.z*w;sum+=w;}auto q=oracle[fallbackVertices[i]];if(std::abs(sum-1)>2e-6||(p-q).length()>2e-6)return false;}
  if(memo.size()>128)memo.clear();memo[memoKey]=candidate;stencils.swap(candidate);fallback=false;return true;
 }
 int level=-1;std::vector<Stencil> stencils;std::vector<std::array<int,2>> pairs;
 std::vector<int> fallbackVertices;MPointArray evaluated;std::vector<double> last;bool ready=false,fallback=false;
 void clear(){level=-1;stencils.clear();pairs.clear();fallbackVertices.clear();last.clear();evaluated.clear();ready=false;fallback=false;}
 std::string diskKey(MFnMesh& fn,int divisions,const std::vector<std::array<int,2>>& marked){
  std::string key("ReaPencil146-Maya2025-plan2");MMeshSmoothOptions o;fn.getSmoothMeshDisplayOptions(o);MIntArray counts,indices;fn.getVertices(counts,indices);
  static std::string runtime=[](){std::string result;for(const wchar_t* module:{L"OpenMaya.dll",L"osdCPU.dll"}){wchar_t file[32768];if(GetModuleFileNameW(GetModuleHandleW(module),file,32768)){try{auto p=std::filesystem::path(file);auto size=std::filesystem::file_size(p);auto stamp=std::filesystem::last_write_time(p).time_since_epoch().count();edgeDisk::put(result,size);edgeDisk::put(result,stamp);}catch(...){}}}return result;}();key+=runtime;
  int fields[]={fn.numVertices(),fn.numEdges(),int(counts.length()),int(indices.length()),int(marked.size()),divisions,int(o.subdivisionType()),int(o.boundaryRule()),int(o.openSubdivVertexBoundary()),int(o.openSubdivCreaseMethod()),int(o.keepBorderEdge()),int(o.keepHardEdge()),int(o.openSubdivSmoothTriangles()),int(o.propEdgeHardness())};
  for(int v:fields)edgeDisk::put(key,v);float continuity=o.smoothness();edgeDisk::put(key,continuity);for(int v:counts)edgeDisk::put(key,v);for(int v:indices)edgeDisk::put(key,v);for(auto pair:marked)for(int v:pair)edgeDisk::put(key,v);
  for(int e=0;e<fn.numEdges();++e){unsigned char hard=!fn.isEdgeSmooth(e);edgeDisk::put(key,hard);}
  for(int type=0;type<2;++type){MUintArray ids;MDoubleArray values;if(type)fn.getCreaseVertices(ids,values);else fn.getCreaseEdges(ids,values);unsigned count=ids.length();edgeDisk::put(key,count);for(unsigned i=0;i<count;++i){unsigned id=ids[i];edgeDisk::put(key,id);edgeDisk::put(key,values[i]);}}
  return key;
 }
 bool loadDisk(const std::string& key,int sourceVertices){
  std::string data;if(!edgeDisk::read(key,data))return false;size_t offset=0;unsigned rows=0,edges=0;if(!edgeDisk::get(data,offset,rows)||rows>2000000||!edgeDisk::get(data,offset,edges)||edges>4000000)return false;
  if(size_t(rows)*12+size_t(edges)*8>data.size()-offset)return false;
  std::vector<Stencil> saved(rows);std::vector<std::array<int,2>> savedPairs(edges);
  for(auto& s:saved){unsigned n=0;if(!edgeDisk::get(data,offset,n)||n>unsigned(sourceVertices)||n>(data.size()-offset)/(sizeof(int)+sizeof(float)))return false;double sum=0;for(unsigned i=0;i<n;++i){int id;float w;if(!edgeDisk::get(data,offset,id)||!edgeDisk::get(data,offset,w)||id<0||id>=sourceVertices||!std::isfinite(w)||std::abs(w)>4)return false;s.ids.push_back(id);s.weights.push_back(w);sum+=w;}if(std::abs(sum-1)>1e-5)return false;}
  for(auto& p:savedPairs)for(int& v:p)if(!edgeDisk::get(data,offset,v)||v<0||unsigned(v)>=rows)return false;
  if(offset!=data.size())return false;stencils.swap(saved);pairs.swap(savedPairs);fallback=false;ready=true;evaluated.setLength(rows);++edgeDisk::hits;return true;
 }
 void storeDisk(const std::string& key){if(fallback||!ready)return;std::string data;unsigned rows=unsigned(stencils.size()),edges=unsigned(pairs.size());edgeDisk::put(data,rows);edgeDisk::put(data,edges);for(auto& s:stencils){unsigned n=unsigned(s.ids.size());edgeDisk::put(data,n);for(unsigned i=0;i<n;++i){edgeDisk::put(data,s.ids[i]);edgeDisk::put(data,s.weights[i]);}}for(auto p:pairs)for(int v:p)edgeDisk::put(data,v);edgeDisk::write(key,data);}
 bool build(MFnMesh& fn,int divisions,const std::vector<std::array<int,2>>& marked){
  clear();level=divisions;
  if(divisions<=0){ready=true;return true;}
  auto cacheKey=diskKey(fn,divisions,marked);if(loadDisk(cacheKey,fn.numVertices()))return true;
  MMeshSmoothOptions smooth;fn.getSmoothMeshDisplayOptions(smooth);
  MIntArray counts,indices;fn.getVertices(counts,indices);
  std::vector<int> cs(counts.begin(),counts.end()),vs(indices.begin(),indices.end());
  std::vector<int> creases,corners;std::vector<float> weights,cornerWeights;MUintArray ids;MDoubleArray sharp;
  fn.getCreaseEdges(ids,sharp);
  for(unsigned i=0;i<ids.length();++i){int2 p;fn.getEdgeVertices(ids[i],p);creases.push_back(p[0]);creases.push_back(p[1]);weights.push_back(float(sharp[i]));}
  fn.getCreaseVertices(ids,sharp);for(unsigned i=0;i<ids.length();++i){corners.push_back(ids[i]);cornerWeights.push_back(float(sharp[i]));}
  // Legacy Maya creases have different decay from OpenSubdiv. Keep their
  // exact native geometry; map topology once, only reevaluate after deformation.
  fallback=(smooth.subdivisionType()==MMeshSmoothOptions::kCatmullClark &&
    (std::any_of(weights.begin(),weights.end(),[](float v){return v>0;})||std::any_of(cornerWeights.begin(),cornerWeights.end(),[](float v){return v>0;})||smooth.keepHardEdge()||std::abs(smooth.smoothness()-1.f)>1e-6));
  if(fallback){
   MString command("from reatoon import fast_targets; fast_targets.smooth_edge_pairs('");command+=fn.fullPathName();command+="',[";
   for(auto pair:marked){command+="(";command+=pair[0];command+=",";command+=pair[1];command+="),";}command+="])";
   MIntArray values;if(!MGlobal::executePythonCommand(command,values,false,false))return false;
   std::unordered_map<int,int> compact;
   for(unsigned i=0;i+1<values.length();i+=2){std::array<int,2> pair;for(int j=0;j<2;++j){int v=values[i+j];auto entry=compact.emplace(v,int(fallbackVertices.size()));if(entry.second)fallbackVertices.push_back(v);pair[j]=entry.first->second;}pairs.push_back(pair);}evaluated.setLength(unsigned(fallbackVertices.size()));if(legacyStencils(fn,smooth,counts,indices,marked,values)||legacyStencils(fn,smooth,counts,indices,marked,values,true))++legacyMapped;else ++legacyRejected;ready=true;storeDisk(cacheKey);return true;
  }
  Far::TopologyDescriptor desc;desc.numVertices=fn.numVertices();desc.numFaces=fn.numPolygons();desc.numVertsPerFace=cs.data();desc.vertIndicesPerFace=vs.data();desc.numCreases=int(weights.size());desc.creaseVertexIndexPairs=creases.data();desc.creaseWeights=weights.data();desc.numCorners=int(corners.size());desc.cornerVertexIndices=corners.data();desc.cornerWeights=cornerWeights.data();
  Sdc::Options options;int boundary=int(smooth.openSubdivVertexBoundary());
  // Maya legacy keep-border uses the Catmull-Clark edge/corner boundary rule.
  if(smooth.subdivisionType()==MMeshSmoothOptions::kCatmullClark)boundary=smooth.keepBorderEdge()?1:2;
  options.SetVtxBoundaryInterpolation(boundary==0?Sdc::Options::VTX_BOUNDARY_NONE:boundary==1?Sdc::Options::VTX_BOUNDARY_EDGE_AND_CORNER:Sdc::Options::VTX_BOUNDARY_EDGE_ONLY);
  options.SetCreasingMethod(smooth.openSubdivCreaseMethod()==MMeshSmoothOptions::kChaikin?Sdc::Options::CREASE_CHAIKIN:Sdc::Options::CREASE_UNIFORM);
  options.SetTriangleSubdivision(smooth.openSubdivSmoothTriangles()?Sdc::Options::TRI_SUB_SMOOTH:Sdc::Options::TRI_SUB_CATMARK);
  Far::TopologyRefinerFactory<Far::TopologyDescriptor>::Options factory(Sdc::SCHEME_CATMARK,options);
  std::unique_ptr<Far::TopologyRefiner> refiner(Far::TopologyRefinerFactory<Far::TopologyDescriptor>::Create(desc,factory));if(!refiner)return false;
  Far::TopologyRefiner::UniformOptions uniform(divisions);uniform.fullTopologyInLastLevel=true;refiner->RefineUniform(uniform);
  std::vector<int> edges;auto& base=refiner->GetLevel(0);
  for(auto p:marked){auto es=base.GetVertexEdges(p[0]);for(int e:es){auto ev=base.GetEdgeVertices(e);if((ev[0]==p[0]&&ev[1]==p[1])||(ev[1]==p[0]&&ev[0]==p[1])){edges.push_back(e);break;}}}
  for(int l=0;l<divisions;++l){std::vector<int> next;auto& level=refiner->GetLevel(l);for(int e:edges)for(int child:level.GetEdgeChildEdges(e))next.push_back(child);edges.swap(next);}
  Far::StencilTableFactory::Options opts;opts.generateIntermediateLevels=false;opts.generateOffsets=true;
  std::unique_ptr<const Far::StencilTable> table(Far::StencilTableFactory::Create(*refiner,opts));if(!table)return false;
  std::unordered_map<int,int> compact;auto& final=refiner->GetLevel(divisions);
  for(int e:edges){auto ev=final.GetEdgeVertices(e);std::array<int,2> pair;for(int j=0;j<2;++j){int vertex=ev[j];auto found=compact.find(vertex);if(found==compact.end()){int id=int(stencils.size());compact[vertex]=id;auto s=table->GetStencil(vertex);Stencil stencil;for(int i=0;i<s.GetSize();++i){stencil.ids.push_back(s.GetVertexIndices()[i]);stencil.weights.push_back(s.GetWeights()[i]);}stencils.push_back(std::move(stencil));pair[j]=id;}else pair[j]=found->second;}pairs.push_back(pair);}
  evaluated.setLength(unsigned(stencils.size()));ready=true;storeDisk(cacheKey);return true;
 }
 bool update(MFnMesh& fn,const double* doubles,const float* floats,int count){
  bool changed=last.size()!=size_t(count*3);if(!changed)for(int i=0;i<count*3;++i)if(last[i]!=(doubles?doubles[i]:double(floats[i]))){changed=true;break;}
  if(!changed)return false;
  last.resize(size_t(count*3));for(int i=0;i<count*3;++i)last[i]=doubles?doubles[i]:double(floats[i]);
  if(fallback){++legacyEvaluations;MObject owner=MFnMeshData().create();MMeshSmoothOptions options;fn.getSmoothMeshDisplayOptions(options);options.setDivisions(level);options.setSmoothUVs(false);MStatus status;MObject object=fn.generateSmoothMesh(owner,&options,&status);if(!status){ready=false;return false;}MFnMesh smooth(object);MPointArray raw;smooth.getPoints(raw,MSpace::kObject);for(unsigned i=0;i<fallbackVertices.size();++i)evaluated[i]=raw[fallbackVertices[i]];return true;}
  for(unsigned i=0;i<stencils.size();++i){MPoint p(0,0,0);auto& s=stencils[i];for(unsigned j=0;j<s.ids.size();++j){int k=s.ids[j]*3;double w=s.weights[j];p.x+=last[k]*w;p.y+=last[k+1]*w;p.z+=last[k+2]*w;}evaluated[i]=p;}
  return true;
 }
};
}
