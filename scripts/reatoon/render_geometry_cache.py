"""Bounded CPU render geometry reuse with Maya dirty/attribute invalidation.

Every lookup forces the source outMesh and worldMatrix to evaluate first. The
entry owns callbacks on the shape and every DAG ancestor, so deformers,
subdivision settings, transforms, undo and direct edits invalidate it. Scene
replacement and plug-in unload release both arrays and callbacks.
"""
from collections import OrderedDict
from maya import cmds
from maya.api import OpenMaya as om
import numpy as np

_ENTRIES=OrderedDict()
_SCENE=[]
_LIMIT=1024*1024*1024
_hits=_misses=0


def _remove(entry):
    for callback in entry['callbacks']:
        try:om.MMessage.removeCallback(callback)
        except RuntimeError:pass
    entry['callbacks']=[]
    entry['value']=None


def clear(*_):
    for entry in _ENTRIES.values():_remove(entry)
    _ENTRIES.clear()
    from .intersections import clear_query_cache
    clear_query_cache()


def shutdown():
    clear()
    for callback in _SCENE:
        try:om.MMessage.removeCallback(callback)
        except RuntimeError:pass
    _SCENE.clear()


def stats():
    return dict(hits=_hits,misses=_misses,entries=len(_ENTRIES),
                bytes=sum(_entry_size(e) for e in _ENTRIES.values()))


def _size(value,seen=None):
    seen=set() if seen is None else seen
    if id(value) in seen:return 0
    seen.add(id(value))
    if isinstance(value,np.ndarray):return value.nbytes
    if isinstance(value,(bytes,bytearray)):return len(value)
    if isinstance(value,dict):return sum(_size(v,seen) for v in tuple(value.values()))
    if isinstance(value,(tuple,list)):return sum(_size(v,seen) for v in value)
    return 0


def evaluate(path,divisions,uniform=False):
    global _hits,_misses
    from . import native_mesh
    if not _SCENE:
        for event in (om.MSceneMessage.kBeforeNew,om.MSceneMessage.kBeforeOpen):
            _SCENE.append(om.MSceneMessage.addCallback(event,clear))
    # Flush upstream evaluation BEFORE checking callbacks' invalidation result.
    fn=om.MFnDependencyNode(path.node())
    fn.findPlug('outMesh',False).asMObject()
    fn.findPlug('worldMatrix',False).elementByLogicalIndex(path.instanceNumber()).asMObject()
    global_type=cmds.optionVar(query='globalPolyDefaultSmoothDrawType')
    key=(path.fullPathName(),int(divisions),global_type,bool(uniform))
    entry=_ENTRIES.get(key)
    if entry is not None and not (entry['handle'].isValid() and entry['handle'].object()==path.node()):
        _remove(_ENTRIES.pop(key));entry=None
    if entry is not None and entry['value'] is not None:
        _hits+=1;_ENTRIES.move_to_end(key)
        return entry['value']
    _misses+=1
    if entry is None:
        entry=dict(handle=om.MObjectHandle(path.node()),callbacks=[],value=None,bytes=0)
        def dirty(*_):entry['value']=None;entry['bytes']=0
        try:
            current=om.MDagPath(path)
            while current.length():
                entry['callbacks'].append(om.MNodeMessage.addNodeDirtyCallback(current.node(),dirty))
                def changed(message,plug,other,client,callback=dirty):
                    if message & (om.MNodeMessage.kAttributeSet | om.MNodeMessage.kConnectionMade | om.MNodeMessage.kConnectionBroken):callback()
                entry['callbacks'].append(om.MNodeMessage.addAttributeChangedCallback(current.node(),changed))
                current.pop()
        except Exception:
            _remove(entry);raise
        _ENTRIES[key]=entry
    value=native_mesh.evaluate(path,divisions,purpose='render',uniform=uniform)
    entry['value']=value;entry['bytes']=_size(value)
    _ENTRIES.move_to_end(key)
    # Include derived edge/BVH arrays that may have been attached since lookup.
    trim()
    return value


def _entry_size(entry):
    value=entry['value']
    if value is None:return 0
    # Derived edge/BVH dictionaries are attached atomically. Recount only when
    # those objects change, rather than walking every preceding mesh per export.
    signature=tuple((key,id(part)) for key,part in tuple(value.items()))
    if entry.get('size_signature')!=signature:
        entry['bytes']=_size(value);entry['size_signature']=signature
    return entry['bytes']


def trim():
    for key,entry in list(_ENTRIES.items()):
        if not entry['handle'].isValid() or not entry['handle'].isAlive():
            _remove(_ENTRIES.pop(key))
    used=sum(_entry_size(e) for e in _ENTRIES.values())
    while _ENTRIES and (used>_LIMIT or len(_ENTRIES)>512):
        _,old=_ENTRIES.popitem(last=False);used-=_entry_size(old);_remove(old)
