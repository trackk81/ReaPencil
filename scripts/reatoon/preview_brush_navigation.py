"""Reuse retained world buffers during navigation; finish exact coverage off-thread.

Only the UI thread reads Maya or uploads native buffers. One worker receives
owned immutable numeric snapshots; stale camera/geometry results are discarded.
"""
import copy,importlib.util,json,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np

OPTION='reaPencilPreviewBrushNavigation'
_source=None
_requests=[]
_building=None
_apply=None
_apply_index=0
_ready=None
_latest=None
_deadline=0.
_future=None
_executor=None
_timer=None
_revision=0
_worker_batch=None
_cache_seed=None
_failed=False
stats=dict(reused_frames=0,worker_runs=0,stale_results=0,applied=0)


def enabled():
    from maya import cmds
    return bool(cmds.optionVar(q=OPTION)) if cmds.optionVar(exists=OPTION) else True


def eligible(passes):
    # Clean brush keeps the line shape: Dash must retain navigation reuse too.
    return enabled() and any(int(s.get('brush_preset',0)) in (1,2,3) or s.get('line_pattern')==1 and not s.get('brush_preset') for p in (passes or []) for s in p['styles'])


def reset():
    global _source,_requests,_building,_apply,_ready,_latest,_revision,_failed,_future,_cache_seed
    retired=[]
    if _ready is not None:retired.append(_ready);stats['stale_results']+=1
    _revision+=1;_source=None;_requests=[];_building=None;_apply=None;_ready=None;_latest=None;_failed=False;_cache_seed=None
    if _future is not None and _future.done():retired.append(_future);_future=None;stats['stale_results']+=1
    elif _future is not None and _future.cancel():_future=None
    if retired:_dispose_later(retired)
    if _future is not None:_ensure_timer()
    elif _timer is not None:_timer.stop()


def at_exact(key):
    global _latest,_ready,_revision
    if _latest is not None or _ready is not None:
        retired=[_ready] if _ready is not None else []
        _revision+=1;_latest=None;_ready=None
        if retired:_dispose_later(retired)
        if _future is not None:_ensure_timer()
        elif _timer is not None:_timer.stop()


def observe(key):
    if _source is not None and _source!=key[:-1]:
        stats['source_invalidations']=stats.get('source_invalidations',0)+1
        reset()


def _frozen(a):
    if a is None:return None
    b=np.array(a,copy=True);b.setflags(write=False);return b


def ready_for(key):
    return _ready is not None and _ready[:2] == (key[:-1], key[-1])


def request_count():
    return len(_building) if _building is not None else 0


def requests(first, last):
    return _requests[first:last]


def begin(key,passes):
    global _building,_apply,_apply_index,_ready,_revision
    _revision+=1;_apply_index=0;_building=[] if eligible(passes) else None
    _apply=_ready[2] if _ready is not None and _ready[:2]==(key[:-1],key[-1]) else None
    _ready=None


def expansion(oracle,args,fixed):
    global _apply_index,_apply
    points,parameters,owners,styles,camera,vertices,flags,outline=args
    previous = _apply[_apply_index][0] if _apply is not None and _apply_index < len(_apply) else None
    if previous is not None and previous['points'] is points and previous['styles'] == styles:
        _apply_index += 1
        _building.append(previous)
        return _apply[_apply_index - 1][1]
    request=dict(points=_frozen(points),parameters=_frozen(parameters),owners=_frozen(owners),styles=copy.deepcopy(styles),vertices=_frozen(vertices),flags=_frozen(flags),outline=_frozen(outline),fixed=_frozen(fixed)) if _building is not None else None
    if request is not None:_building.append(request)
    if _apply is not None:
        index=_apply_index;_apply_index+=1
        if index<len(_apply):
            old,result=_apply[index]
            same=json.dumps(old['styles'],sort_keys=True)==json.dumps(styles,sort_keys=True)
            for name in ('points','parameters','owners','vertices','flags','outline','fixed'):
                current=fixed if name=='fixed' else args[{'points':0,'parameters':1,'owners':2,'vertices':5,'flags':6,'outline':7}[name]]
                same &= (old[name] is None and current is None) or (old[name] is not None and current is not None and np.array_equal(old[name],current))
            if same:return result
        # A changed intersection ordering or source invalidates exact replay.
        # Recompute this and subsequent requests, rather than using stale data.
        _apply=None;stats['replay_mismatch']=stats.get('replay_mismatch',0)+1
    return oracle(*args)


def end(key,complete=True):
    global _source,_requests,_building,_apply,_latest,_cache_seed
    if _apply is not None:stats['applied']+=1
    _source=key[:-1] if _building and complete else None;_requests=(_building or []) if complete else [];_building=None;_apply=None;_latest=None
    if _source is not None:
        from . import preview_brush_batch
        _cache_seed=(_source,preview_brush_batch.connectivity_seed())
    else:_cache_seed=None


def reuse(key,passes,camera,destination=''):
    """True means keep the existing native buffers for this moving camera."""
    global _latest,_deadline
    if _failed or not eligible(passes) or _source!=key[:-1] or not _requests:return False
    if destination:
        # Native buffers are shared; independent cameras in a quad/floating
        # layout must keep the established per-destination exact path.
        from maya import cmds
        if sum(cmds.getPanel(typeOf=p)=='modelPanel' for p in (cmds.getPanel(visiblePanels=True) or []))>1:return False
    if _ready is not None and _ready[:2]==(key[:-1],key[-1]):return False
    if _latest is None or _latest[1]!=key[-1]:
        _latest=(key[:-1],key[-1],copy.deepcopy(camera));_deadline=time.monotonic()+.08
    stats['reused_frames']+=1
    _ensure_timer()
    return True


def _compute(revision,source,token,camera,requests):
    global _worker_batch
    start=time.perf_counter()
    if _worker_batch is None:
        # Separate module/cache instance: numeric worker never mutates the
        # main thread's connectivity cache during a scene/style invalidation.
        spec=importlib.util.spec_from_file_location('reatoon._navigation_batch',Path(__file__).with_name('preview_brush_batch.py'))
        _worker_batch=importlib.util.module_from_spec(spec);spec.loader.exec_module(_worker_batch)
    seed=_cache_seed
    if seed is not None and seed[0]==source:_worker_batch.seed_connectivity(seed[1])
    from .stroke_presets import active
    results=[]
    for q in requests:
        if camera is None or not any(active(q['styles'][int(i)]) for i in np.unique(q['owners'])):
            result=(q['points'],q['parameters'],q['owners'],q['vertices'],q['flags'],q['outline'],None)
        else:result=_worker_batch.retained(q['points'],q['parameters'],q['owners'],q['styles'],camera,q['flags'],q['outline'],q['fixed'])
        results.append((q,result))
    return revision,source,token,results,time.perf_counter()-start


def _ensure_timer():
    global _timer
    if _timer is None:
        from PySide6 import QtCore
        _timer=QtCore.QTimer();_timer.setInterval(16);_timer.timeout.connect(_poll)
    if not _timer.isActive():_timer.start()


def _poll():
    global _future,_executor,_ready,_failed
    if _future is not None and _future.done():
        future=_future;_future=None
        try:revision,source,token,results,seconds=future.result()
        except Exception as error:
            stats['error']=repr(error);_failed=True
            if _timer is not None:_timer.stop()
            return
        stats['worker_seconds']=seconds
        if revision==_revision and _source==source and _latest is not None and _latest[:2]==(source,token) and enabled() and _scene_current(source):
            _ready=(source,token,results)
            if _timer is not None:_timer.stop()
            # Do not call viewport.request_refresh: it invalidates geometry
            # generation, which would make this immutable result stale.
            from maya import cmds
            cmds.refresh(force=True)
            retired=[future,results];future=None;results=None;_dispose_later(retired)
            return
        stats['stale_results']+=1
        retired=[future,results];future=None;results=None;_dispose_later(retired)
    if _latest is None or _failed or not enabled():
        if _future is None and _timer is not None:_timer.stop()
        return
    if _future is None and time.monotonic()>=_deadline:
        if _executor is None:_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='ReaPencilBrush')
        source,token,camera=_latest
        _future=_executor.submit(_compute,_revision,source,token,camera,tuple(_requests));stats['worker_runs']+=1


def _scene_current(source):
    from . import viewport
    return viewport._registered and not viewport._exiting and viewport._generation==source[0]


def _dispose_later(payload):
    """Clear the sole large references on the numeric worker, not the UI.

    The caller boxes references and drops its own handles before submitting;
    clearing this list therefore releases even NumPy/native owners off-thread.
    """
    global _executor
    if _executor is None:_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='ReaPencilBrush')
    try:_executor.submit(_dispose,payload)
    except RuntimeError:payload.clear() # Pool is already shutting down.


def _dispose(payload):payload.clear()
