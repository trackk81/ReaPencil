"""Bulk read-only Maya mesh evaluation through the optional native command.

Returns NumPy arrays and no selected-edge descendant mapping. Callers requiring
component provenance must retain the full smooth_geometry path.
"""
from pathlib import Path
import ctypes
import json
import numpy as np


_PLUGIN=Path(__file__).resolve().parents[2]/'plug-ins/2025/revToonMesh074.mll'

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


def read(path):
    return _decode(Path(path).read_bytes())


def _decode(payload):
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
    else:
        starts=np.cumsum(counts,dtype=np.int64)-counts
        polygons=[indices[start:start+count] for start,count in zip(starts,counts)]
    return dict(world_points=points,vertices=points,faces=polygons,face_counts=counts,face_indices=indices,
                triangles=tris,triangle_faces=triangle_faces,hard_edges=hard_edges,base_face_ids=provenance,
                level=level,base_face_count=base_faces,base_vertex_count=base_vertices,
                base_edge_count=base_edges,base_edge_children={})


def evaluate(path,divisions=0,output_path=None,purpose='render',uniform=False):
    """Evaluate a mesh path in Maya without modifying source mesh or selection."""
    from maya import cmds
    if purpose not in ('render','viewport'):
        raise ValueError('Geometry purpose must be render or viewport')
    load()
    name=path.fullPathName() if hasattr(path,'fullPathName') else str(path)
    if output_path is None:
        pointer,size,timings=json.loads(cmds.revToonExportMesh(mesh=name,divisions=int(divisions),purpose=purpose,uniform=bool(uniform),memory=True))
        if not 80<=size<=1024*1024*1024 or pointer<=0:raise ValueError('Invalid native mesh buffer')
        result=_decode(ctypes.string_at(pointer,size))
    else:
        timings=cmds.revToonExportMesh(mesh=name,divisions=int(divisions),output=str(output_path),purpose=purpose,uniform=bool(uniform),profile=True)
        result=read(output_path)
    result['native_timings']=timings
    result['uniform_style_provenance']=bool(uniform and divisions)
    return result
