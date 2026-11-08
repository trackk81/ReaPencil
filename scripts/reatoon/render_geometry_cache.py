"""Bounded CPU render geometry reuse with Maya dirty/attribute invalidation.

Every lookup forces the source outMesh and worldMatrix to evaluate first. The
entry owns callbacks on the shape and every DAG ancestor, so deformers,
subdivision settings, transforms, undo and direct edits invalidate it. Scene
replacement and plug-in unload release both arrays and callbacks.
"""
from collections import OrderedDict
from threading import Lock
from maya import cmds
from maya.api import OpenMaya as om
import numpy as np
from .native_mesh import PolygonViews,PackedPolygons

_ENTRIES=OrderedDict()
_SCENE=[]
_LIMIT=1024*1024*1024
_hits=_misses=0
_used=0
_BY_VALUE={}
_PENDING=set()
_PENDING_LOCK=Lock()


def _discard_value(entry):
    global _used
    value=entry['value']
    if value is not None:
        with _PENDING_LOCK:
            _BY_VALUE.pop(id(value),None);_PENDING.discard(id(value))
    _used-=entry['bytes'];entry['bytes']=0
    entry['value']=None;entry.pop('size_signature',None)


def geometry_changed(value):
    """Worker-safe notification; Maya callbacks/eviction stay on main thread."""
    with _PENDING_LOCK:
        if id(value) in _BY_VALUE:_PENDING.add(id(value))


def _remove(entry):
    for callback in entry['callbacks']:
        try:om.MMessage.removeCallback(callback)
        except RuntimeError:pass
    entry['callbacks']=[]
    _discard_value(entry)


def clear(*_):
    global _used
    for entry in _ENTRIES.values():_remove(entry)
    _ENTRIES.clear()
    _used=0
    from .intersections import clear_query_cache
    clear_query_cache()


def shutdown():
    clear()
    for callback in _SCENE:
        try:om.MMessage.removeCallback(callback)
        except RuntimeError:pass
    _SCENE.clear()


def stats():
    trim()
    return dict(hits=_hits,misses=_misses,entries=len(_ENTRIES),
                bytes=_used)


def _size(value,seen=None):
    if isinstance(value,(str,int,float,bool,type(None))):return 0
    seen=set() if seen is None else seen
    if id(value) in seen:return 0
    seen.add(id(value))
    if isinstance(value,(PolygonViews,PackedPolygons)):return value.cache_nbytes
    if isinstance(value,np.ndarray):return value.nbytes
    if isinstance(value,(bytes,bytearray)):return len(value)
    if isinstance(value,dict):return sum(_size(v,seen) for v in tuple(value.values()))
    if isinstance(value,(tuple,list)):return sum(_size(v,seen) for v in value)
    return 0


def evaluate(path,divisions,uniform=False,exporter_ready=False,global_smooth_type=None):
    global _hits,_misses,_used
    from . import native_mesh
    if not _SCENE:
        for event in (om.MSceneMessage.kBeforeNew,om.MSceneMessage.kBeforeOpen):
            _SCENE.append(om.MSceneMessage.addCallback(event,clear))
    # Flush upstream evaluation BEFORE checking callbacks' invalidation result.
    fn=om.MFnDependencyNode(path.node())
    fn.findPlug('outMesh',False).asMObject()
    fn.findPlug('worldMatrix',False).elementByLogicalIndex(path.instanceNumber()).asMObject()
    global_type=(cmds.optionVar(query='globalPolyDefaultSmoothDrawType') if global_smooth_type is None else global_smooth_type)
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
        def dirty(*_):_discard_value(entry)
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
    value=native_mesh.evaluate(path,divisions,purpose='render',uniform=uniform,exporter_ready=exporter_ready)
    entry['value']=value;entry['bytes']=_entry_size(entry);_used+=entry['bytes']
    with _PENDING_LOCK:_BY_VALUE[id(value)]=entry
    _ENTRIES.move_to_end(key)
    # Include derived edge/BVH arrays that may have been attached since lookup.
    trim(full=False)
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


def trim(full=True):
    """Audit once at frame boundaries; account notified growth during export.

    Scanning all preceding mesh dictionaries after every mesh was quadratic.
    The CPU preparation workers notify when they attach derived arrays. Only
    those entries need recounting between evaluations. The byte/count limits
    and main-thread callback cleanup are unchanged.
    """
    global _used
    with _PENDING_LOCK:
        pending=[_BY_VALUE[key] for key in _PENDING if key in _BY_VALUE]
        _PENDING.clear()
    if full:
        for key,entry in list(_ENTRIES.items()):
            if not entry['handle'].isValid() or not entry['handle'].isAlive():
                _remove(_ENTRIES.pop(key))
        pending=list(_ENTRIES.values())
    for entry in pending:
        old=entry['bytes'];new=_entry_size(entry);_used+=new-old
    while _ENTRIES and (_used>_LIMIT or len(_ENTRIES)>512):
        _,old=_ENTRIES.popitem(last=False);_remove(old)
