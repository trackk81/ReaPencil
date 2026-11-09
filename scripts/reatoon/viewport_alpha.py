"""Automatic opacity boundaries for viewport exports; never writes scene data."""
import os
import json,hashlib
from collections import OrderedDict
import numpy as np
from pathlib import Path
from maya import cmds
from maya.api import OpenMaya as om
from . import alpha_boundary as alpha
OPTION='reaPencilPreviewAutoAlpha'
RESOLUTION='reaPencilPreviewAlphaResolution'
DEFAULT_RESOLUTION=2048
_warnings=set()
_discoveries=0
_configurations=0
_failures=OrderedDict()
_attempts=0
_failure_hits=0

def _signature(mesh,path,evaluated,config):
    """Failed export identity; UV/texture/topology edits must be retryable.

    Called only for a previously failed mesh or when remembering a new failure.
    World points are included because not all validation errors are UV-only.
    No scene mutation, native cache, or per-frame hashing of healthy meshes.
    """
    fn,owner=alpha._texture_fn(path,evaluated)
    digest=hashlib.sha256(json.dumps(config,sort_keys=True).encode('utf8'))
    for values in (mesh['vertices'],mesh['triangles'],mesh['triangle_faces'],
                   mesh['material_ids'],fn.getUVs(),*fn.getAssignedUVs()):
        a=np.ascontiguousarray(values)
        digest.update(str((a.shape,a.dtype.str)).encode('ascii'));digest.update(a.tobytes())
    for source in config['sources'].values():
        try:
            stat=os.stat(os.path.abspath(os.path.expandvars(source['path'])))
            digest.update(str((stat.st_size,stat.st_mtime_ns)).encode('ascii'))
        except OSError as error:digest.update(str(error).encode('utf8'))
    digest.update(str(evaluated['level']).encode('ascii'))
    return digest.digest()

def transform_mesh(mesh,path,evaluated,config):
    """Transactional viewport-only alpha with bounded invalid-input caching.

    Failed cutouts retain their whole evaluated surface, explicitly reported.
    CPU exports keep their strict alpha_boundary.transform_mesh contract.
    """
    global _attempts,_failure_hits
    key=om.MFnDependencyNode(path.node()).uuid().asString()
    previous=_failures.get(key)
    signature=None
    if previous is not None:
        try:signature=_signature(mesh,path,evaluated,config)
        except (ValueError,RuntimeError,OSError):signature=None
        if signature==previous[0]:
            _failure_hits+=1;_failures.move_to_end(key)
            mesh['viewport_alpha_fallback']=previous[1]
            return mesh
        del _failures[key]
    # transform_mesh changes nested line-pass dictionaries only after clipping.
    # Keep even a late validation failure from partially changing live metadata.
    candidate=dict(mesh)
    if 'line_passes' in mesh:candidate['line_passes']=[dict(p) for p in mesh['line_passes']]
    _attempts+=1
    try:alpha.transform_mesh(candidate,path,evaluated,config,_cell_cache={})
    except (ValueError,RuntimeError,OSError) as error:
        message=mesh['name']+': alpha boundary unavailable; preview uses the original surface. '+str(error)
        try:signature=_signature(mesh,path,evaluated,config)
        except (ValueError,RuntimeError,OSError):signature=None
        if signature is not None:_failures[key]=(signature,message)
        while len(_failures)>128:_failures.popitem(last=False)
        mesh['viewport_alpha_fallback']=message;_warn(message)
    else:mesh.clear();mesh.update(candidate)
    return mesh

def enabled():return bool(cmds.optionVar(q=OPTION)) if cmds.optionVar(exists=OPTION) else True

def resolution():
    value=int(cmds.optionVar(q=RESOLUTION)) if cmds.optionVar(exists=RESOLUTION) else DEFAULT_RESOLUTION
    return max(16,min(4096,value))

def _warn(error):
    text=str(error)
    if text not in _warnings:
        if len(_warnings)>256:_warnings.clear()
        _warnings.add(text);om.MGlobal.displayWarning('ReaPencil automatic viewport alpha: '+text)

def sources(shape):
    global _discoveries
    _discoveries+=1
    return alpha.material_sources(shape)

def dependencies(shape):
    # Watch graphs once, not per camera frame. Include all shaders so adding
    # a new opacity connection to an initially opaque material is detected.
    result=set()
    from .mesh_surface import mesh_function
    path=om.MSelectionList().add(shape).getDagPath(0)
    fn=mesh_function(path)
    if fn is None:return result
    engines,_=fn.getConnectedShaders(path.instanceNumber())
    for engine in engines:
        shaders=cmds.listConnections(om.MFnDependencyNode(engine).name()+'.surfaceShader',s=True,d=False) or []
        for shader in shaders:
            result.add(shader)
            for attr in ('opacity','transparency'):
                if not cmds.attributeQuery(attr,node=shader,exists=True):continue
                for root in cmds.listConnections(shader+'.'+attr,s=True,d=False) or []:
                    result.add(root);result.update(cmds.listHistory(root,pruneDagObjects=True) or [])
    return result

def configuration(shape):
    global _configurations
    _configurations+=1
    # Explicit settings (including a disabled setting) keep their original meaning.
    if cmds.attributeQuery(alpha.ATTRIBUTE,node=shape,exists=True):return alpha.configuration(shape)
    if not enabled():return None
    try:
        found=sources(shape)
        if not found:return None
        found={k:dict(v) for k,v in found.items()}
        for source in found.values():
            raw=os.path.expandvars(source['path'])
            if not os.path.isabs(raw):
                expanded=cmds.workspace(expandName=raw)
                if os.path.isfile(expanded):raw=expanded
            source['path']=raw
        config=dict(version=1,enabled=True,threshold=.5,resolution=resolution(),simplify=.25,sources=found)
        for source in found.values():alpha._cells(source,config)
        return config
    except (ValueError,OSError,RuntimeError) as error:
        _warn(error);return None

def diagnostics():return dict(configurations=_configurations,discoveries=_discoveries,warnings=sorted(_warnings),
                              transform_attempts=_attempts,failure_cache_hits=_failure_hits,cached_failures=len(_failures))
