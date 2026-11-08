"""Optional GPU image-space preview, independent of the final CPU renderer."""
from .i18n import tr
import ctypes
from pathlib import Path
from maya import cmds

NAME='reaPencilFastPreview'
_library=None
_plugin=None
_panels={}
_edge_flags=(False,False)
_target_summary={}

def configure(width=1.5,crease=.25,color=(0.,0.,0.),antialias=True,hard_edges=False,crease_edges=False):
    global _edge_flags
    _edge_flags=(bool(hard_edges),bool(crease_edges))
    if _library is None:return
    _library.rp_fast_edge_options(int(hard_edges),int(crease_edges))
    shader=Path(__file__).parent/'shaders/fast_preview.ogsfx'
    rgb=(ctypes.c_float*3)(*color)
    _library.rp_fast_config(str(shader).encode('utf-8'),float(width),float(crease),rgb)
    if hasattr(_library,'rp_fast_antialias'):_library.rp_fast_antialias(int(antialias))

def register():
    global _library,_plugin
    if _library is not None:return
    from maya.api import OpenMayaRender as omr
    if omr.MRenderer.drawAPI()!=omr.MRenderer.kOpenGLCoreProfile:
        raise RuntimeError('Fast preview requires Viewport 2.0 OpenGL Core Profile; the precise viewport remains available.')
    if _library is None:
        root=Path(__file__).resolve().parents[2]
        path=root/'plug-ins'/str(cmds.about(version=True))/'reaPencilFast159.mll'
        if not path.is_file():raise RuntimeError('Fast preview module is unavailable for this Maya version')
        _plugin=cmds.loadPlugin(str(path),quiet=True)[0]
        cmds.pluginInfo(_plugin,e=True,autoload=False)
        _library=ctypes.CDLL(str(path))
        _library.rp_fast_config.argtypes=[ctypes.c_char_p,ctypes.c_float,ctypes.c_float,ctypes.POINTER(ctypes.c_float)]
        _library.rp_fast_config.restype=None
        _library.rp_fast_frames.restype=ctypes.c_uint
        _library.rp_fast_edge_options.argtypes=[ctypes.c_int,ctypes.c_int];_library.rp_fast_edge_options.restype=None
        _library.rp_fast_hard_count.restype=ctypes.c_uint;_library.rp_fast_crease_count.restype=ctypes.c_uint
        from . import fast_targets
        fast_targets._key=None;fast_targets._watching=False
    configure(**preferences())

def enable():
    from . import viewport
    register()
    configure(**preferences())
    was_precise=bool(cmds.ls(type=viewport.NODE_NAME))
    before=_library.rp_fast_frames()
    precise_panels={}
    try:
        # Detach precise panels before deleting their helper. Its renderer can
        # otherwise recreate the helper during disable()'s forced refresh,
        # rebuilding the whole scene immediately before switching to Fast.
        from .preview_renderers import NAME as PRECISE_NAME
        for panel in cmds.getPanel(type='modelPanel') or []:
            if cmds.modelEditor(panel,q=True,rendererOverrideName=True)==PRECISE_NAME:
                precise_panels[panel]=PRECISE_NAME
                cmds.modelEditor(panel,e=True,rendererOverrideName='')
        viewport.disable()
        for panel in cmds.getPanel(type='modelPanel') or []:
            previous=precise_panels.get(panel,cmds.modelEditor(panel,q=True,rendererOverrideName=True))
            if previous!=NAME:_panels[panel]=previous
            cmds.modelEditor(panel,e=True,rendererOverrideName=NAME)
        cmds.refresh(force=True)
        if _library.rp_fast_frames()==before:raise RuntimeError('Fast preview did not draw; check the graphics/shader messages in Script Editor.')
    except Exception:
        disable()
        for panel,previous in precise_panels.items():
            if cmds.modelPanel(panel,exists=True):cmds.modelEditor(panel,e=True,rendererOverrideName=previous)
        if was_precise:viewport.enable()
        raise
    return status()

def preferences():
    def get(name,default):return cmds.optionVar(q=name) if cmds.optionVar(exists=name) else default
    return dict(width=get('reaPencilFastWidth',1.5),crease=get('reaPencilFastCrease',.25),color=get('reaPencilFastColor',[0.,0.,0.]),antialias=bool(get('reaPencilFastAA',1)),hard_edges=bool(get('reaPencilFastHardEdges',0)),crease_edges=bool(get('reaPencilFastCreaseEdges',0)))

def show():
    window='reaPencilFastPreviewSettings'
    if cmds.window(window,exists=True):cmds.deleteUI(window)
    values=preferences()
    from . import fast_targets
    if _library is not None:fast_targets.sync()
    unused=_target_summary.get('unassigned_shader_targets',[])
    cmds.window(window,title=tr('ReaPencil — 고속 프리뷰'),widthHeight=(500,415 if unused else 375),sizeable=False)
    cmds.columnLayout(adjustableColumn=True,rowSpacing=8)
    cmds.text(label=tr('라인셋에 등록한 오브젝트와 재질에만 선을 표시합니다.'),align='left',wordWrap=True,height=30)
    if unused:cmds.text(label=tr('Materials with no assigned faces: ')+', '.join(unused),align='left',wordWrap=True,height=30)
    cmds.text(label=tr('정확한 교차선·개별 브러시 표현은 정밀 뷰포트와 CPU 렌더를 사용하세요.'),align='left',wordWrap=True,height=36)
    width=cmds.floatSliderGrp(label=tr('선 굵기'),field=True,minValue=.5,maxValue=5.,value=values['width'])
    crease=cmds.floatSliderGrp(label=tr('Screen contour sensitivity'),field=True,minValue=.02,maxValue=.8,value=values['crease'])
    color=cmds.colorSliderGrp(label=tr('선 색상'),rgbValue=values['color'])
    aa=cmds.optionMenuGrp(label=tr('Anti-aliasing'))
    cmds.menuItem(label=tr('Off'));cmds.menuItem(label='FXAA')
    cmds.optionMenuGrp(aa,e=True,select=2 if values['antialias'] else 1)
    hard=cmds.checkBox(label=tr('Hard edges'),value=values['hard_edges'])
    marked=cmds.checkBox(label=tr('Authored crease edges'),value=values['crease_edges'])
    def changed(*_):
        w=cmds.floatSliderGrp(width,q=True,value=True);c=cmds.floatSliderGrp(crease,q=True,value=True);rgb=cmds.colorSliderGrp(color,q=True,rgbValue=True)
        cmds.optionVar(floatValue=('reaPencilFastWidth',w));cmds.optionVar(floatValue=('reaPencilFastCrease',c));cmds.optionVar(clearArray='reaPencilFastColor')
        for v in rgb:cmds.optionVar(floatValueAppend=('reaPencilFastColor',v))
        enabled=cmds.optionMenuGrp(aa,q=True,select=True)==2;cmds.optionVar(intValue=('reaPencilFastAA',int(enabled)))
        h=cmds.checkBox(hard,q=True,value=True);e=cmds.checkBox(marked,q=True,value=True)
        cmds.optionVar(intValue=('reaPencilFastHardEdges',int(h)));cmds.optionVar(intValue=('reaPencilFastCreaseEdges',int(e)))
        configure(w,c,rgb,antialias=enabled,hard_edges=h,crease_edges=e);cmds.refresh(force=True)
    for control in (hard,marked):cmds.checkBox(control,e=True,changeCommand=changed)
    cmds.optionMenuGrp(aa,e=True,changeCommand=changed)
    for control in (width,crease):cmds.floatSliderGrp(control,e=True,changeCommand=changed,dragCommand=changed)
    cmds.colorSliderGrp(color,e=True,changeCommand=changed,dragCommand=changed)
    from .ui import _safe
    cmds.button(label=tr('닫기'),command=lambda *_:cmds.deleteUI(window));cmds.showWindow(window)
    return dict(window=window)

def disable():
    for panel in cmds.getPanel(type='modelPanel') or []:
        if cmds.modelEditor(panel,q=True,rendererOverrideName=True)==NAME:
            cmds.modelEditor(panel,e=True,rendererOverrideName=_panels.get(panel,''))
    _panels.clear()

def status():
    panels=[p for p in cmds.getPanel(type='modelPanel') or [] if cmds.modelEditor(p,q=True,rendererOverrideName=True)==NAME]
    return dict(state='ready',enabled=bool(panels),backend='screen_space_gpu',panels=panels,frames=_library.rp_fast_frames() if _library else 0,
                unassigned_shader_targets=list(_target_summary.get('unassigned_shader_targets',[])),scope='line-set objects and materials',intersections='screen-space approximation',renderer='CPU final render unchanged')

def shutdown():
    global _library,_plugin
    disable()
    if _plugin:cmds.unloadPlugin(_plugin)
    _library=None;_plugin=None
