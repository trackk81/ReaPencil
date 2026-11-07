"""Automatic opacity boundaries for viewport exports; never writes scene data."""
import os
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
    path=om.MSelectionList().add(shape).getDagPath(0)
    engines,_=om.MFnMesh(path).getConnectedShaders(path.instanceNumber())
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

def diagnostics():return dict(configurations=_configurations,discoveries=_discoveries,warnings=sorted(_warnings))
