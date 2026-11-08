"""Bulk read-only Maya mesh evaluation through the optional native command.

Returns NumPy arrays and no selected-edge descendant mapping. Callers requiring
component provenance must retain the full smooth_geometry path.
"""
from pathlib import Path
from collections.abc import Sequence
import ctypes
import json
import numpy as np


_PLUGIN=Path(__file__).resolve().parents[2]/'plug-ins/2025/revToonMesh074.mll'


class PolygonViews(tuple):
    """Immutable face views with the original contiguous corner buffer."""
    def __new__(cls,values,indices,counts):
        result=super().__new__(cls,values)
        result.flat_indices=indices
        result.counts=counts
        result.minimum_size=int(counts.min()) if len(counts) else 3
        result.cache_nbytes=indices.nbytes
        return result


class PackedPolygons(Sequence):
    """Render-only polygon sequence backed by the unchanged corner buffers."""
    def __init__(self,indices,counts):
        self.flat_indices=indices;self.counts=counts
        self.starts=np.cumsum(counts,dtype=np.int64)-counts
        self.minimum_size=int(counts.min()) if len(counts) else 3
        self.cache_nbytes=indices.nbytes+self.starts.nbytes
    def __len__(self):return len(self.counts)
    def __getitem__(self,index):
        if isinstance(index,slice):return [self[i] for i in range(*index.indices(len(self)))]
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        start=int(self.starts[index]);return self.flat_indices[start:start+int(self.counts[index])]
    def __iter__(self):
        for start,count in zip(self.starts,self.counts):yield self.flat_indices[start:start+count]
    def tolist(self):return [face.tolist() for face in self]

def load():
    from maya import cmds
    plugin=_PLUGIN
    if not plugin.is_file():
        raise RuntimeError('Native Maya mesh exporter is unavailable: '+str(plugin))
    if not cmds.pluginInfo(str(plugin),query=True,loaded=True):
        if cmds.pluginInfo('revToonMesh',query=True,loaded=True):
            raise RuntimeError('Save your work and restart Maya to activate the updated RevToon native mesh exporter.')
        cmds.loadPlugin(str(plugin),quiet=True)
    return plugin


def read(path,packed_faces=False):
    return _decode(Path(path).read_bytes(),packed_faces)


def _decode(payload,packed_faces=False):
    if len(payload)<80 or payload[:8]!=b'RTMESH01':raise ValueError('Invalid native mesh header')
    header=np.frombuffer(payload,dtype='<u8',count=9,offset=8)
    vertices,faces,corners,triangles,hard,base_faces,base_vertices,base_edges,level=map(int,header)
    size=8+9*8+vertices*24+(faces+corners+triangles*4+faces+hard*2)*4
    if len(payload)!=size:raise ValueError('Native mesh payload size mismatch')
    cursor=80
    def take(dtype,count):
        nonlocal cursor
        value=np.frombuffer(payload,dtype=dtype,count=count,offset=cursor)
        cursor+=value.nbytes
        return value
    points=take('<f8',vertices*3).reshape(-1,3)
    counts=take('<u4',faces);indices=take('<u4',corners)
    tris=take('<u4',triangles*3).reshape(-1,3);triangle_faces=take('<u4',triangles)
    provenance=take('<u4',faces);hard_edges=take('<u4',hard*2).reshape(-1,2)
    if int(counts.sum())!=corners:raise ValueError('Invalid native mesh polygon corners')
    if faces and np.all(counts==counts[0]):
        polygons=indices.reshape(faces,int(counts[0]))
    elif packed_faces:
        polygons=PackedPolygons(indices,counts)
    else:
        starts=np.cumsum(counts,dtype=np.int64)-counts
        polygons=PolygonViews((indices[start:start+count] for start,count in zip(starts,counts)),indices,counts)
    return dict(world_points=points,vertices=points,faces=polygons,face_counts=counts,face_indices=indices,
                triangles=tris,triangle_faces=triangle_faces,hard_edges=hard_edges,base_face_ids=provenance,
                level=level,base_face_count=base_faces,base_vertex_count=base_vertices,
                base_edge_count=base_edges,base_edge_children={})


def evaluate(path,divisions=0,output_path=None,purpose='render',uniform=False,exporter_ready=False):
    """Evaluate a mesh path in Maya without modifying source mesh or selection."""
    from maya import cmds
    if purpose not in ('render','viewport'):
        raise ValueError('Geometry purpose must be render or viewport')
    if not exporter_ready:load()
    name=path.fullPathName() if hasattr(path,'fullPathName') else str(path)
    if output_path is None:
        pointer,size,timings=json.loads(cmds.revToonExportMesh(mesh=name,divisions=int(divisions),purpose=purpose,uniform=bool(uniform),memory=True))
        if not 80<=size<=1024*1024*1024 or pointer<=0:raise ValueError('Invalid native mesh buffer')
        result=_decode(ctypes.string_at(pointer,size),packed_faces=purpose=='render')
    else:
        timings=cmds.revToonExportMesh(mesh=name,divisions=int(divisions),output=str(output_path),purpose=purpose,uniform=bool(uniform),profile=True)
        result=read(output_path,packed_faces=purpose=='render')
    result['native_timings']=timings
    result['uniform_style_provenance']=bool(uniform and divisions)
    return result
