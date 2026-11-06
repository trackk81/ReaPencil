"""Optional GPU image-space preview, independent of the final CPU renderer."""
import ctypes
from pathlib import Path
from maya import cmds

NAME='reaPencilFastPreview'
_library=None
_plugin=None
_panels={}

def configure(width=1.5,crease=.25,color=(0.,0.,0.)):
    if _library is None:return
    shader=Path(__file__).parent/'shaders/fast_preview.ogsfx'
    rgb=(ctypes.c_float*3)(*color)
    _library.rp_fast_config(str(shader).encode('utf-8'),float(width),float(crease),rgb)

def enable():
    global _library,_plugin
    from . import viewport
    from maya.api import OpenMayaRender as omr
    if omr.MRenderer.drawAPI()!=omr.MRenderer.kOpenGLCoreProfile:
        raise RuntimeError('Fast preview requires Viewport 2.0 OpenGL Core Profile; the precise viewport remains available.')
    if _library is None:
        root=Path(__file__).resolve().parents[2]
        path=root/'plug-ins'/str(cmds.about(version=True))/'reaPencilFast089.mll'
        if not path.is_file():raise RuntimeError('Fast preview module is unavailable for this Maya version')
        _plugin=cmds.loadPlugin(str(path),quiet=True)[0]
        cmds.pluginInfo(_plugin,e=True,autoload=False)
        _library=ctypes.CDLL(str(path))
        _library.rp_fast_config.argtypes=[ctypes.c_char_p,ctypes.c_float,ctypes.c_float,ctypes.POINTER(ctypes.c_float)]
        _library.rp_fast_config.restype=None
        _library.rp_fast_frames.restype=ctypes.c_uint
    configure(**preferences())
    was_precise=bool(cmds.ls(type=viewport.NODE_NAME))
    viewport.disable()
    before=_library.rp_fast_frames()
    try:
        for panel in cmds.getPanel(type='modelPanel') or []:
            previous=cmds.modelEditor(panel,q=True,rendererOverrideName=True)
            if previous!=NAME:_panels[panel]=previous
            cmds.modelEditor(panel,e=True,rendererOverrideName=NAME)
        cmds.refresh(force=True)
        if _library.rp_fast_frames()==before:raise RuntimeError('Fast preview did not draw; check the graphics/shader messages in Script Editor.')
    except Exception:
        disable()
        if was_precise:viewport.enable()
        raise
    return status()

def preferences():
    def get(name,default):return cmds.optionVar(q=name) if cmds.optionVar(exists=name) else default
    return dict(width=get('reaPencilFastWidth',1.5),crease=get('reaPencilFastCrease',.25),color=get('reaPencilFastColor',[0.,0.,0.]))

def show():
    window='reaPencilFastPreviewSettings'
    if cmds.window(window,exists=True):cmds.deleteUI(window)
    values=preferences();cmds.window(window,title='ReaPencil — 고속 프리뷰',widthHeight=(460,205),sizeable=False)
    cmds.columnLayout(adjustableColumn=True,rowSpacing=8)
    cmds.text(label='화면에 보이는 모든 표면에 적용하는 GPU 프리뷰입니다.',align='left')
    cmds.text(label='정확한 교차선·라인셋 표현은 정밀 뷰포트와 CPU 렌더를 사용하세요.',align='left')
    width=cmds.floatSliderGrp(label='선 굵기',field=True,minValue=.5,maxValue=5.,value=values['width'])
    crease=cmds.floatSliderGrp(label='면 꺾임 기준',field=True,minValue=.02,maxValue=.8,value=values['crease'])
    color=cmds.colorSliderGrp(label='선 색상',rgbValue=values['color'])
    def changed(*_):
        w=cmds.floatSliderGrp(width,q=True,value=True);c=cmds.floatSliderGrp(crease,q=True,value=True);rgb=cmds.colorSliderGrp(color,q=True,rgbValue=True)
        cmds.optionVar(floatValue=('reaPencilFastWidth',w));cmds.optionVar(floatValue=('reaPencilFastCrease',c));cmds.optionVar(clearArray='reaPencilFastColor')
        for v in rgb:cmds.optionVar(floatValueAppend=('reaPencilFastColor',v))
        configure(w,c,rgb);cmds.refresh(force=True)
    for control in (width,crease):cmds.floatSliderGrp(control,e=True,changeCommand=changed,dragCommand=changed)
    cmds.colorSliderGrp(color,e=True,changeCommand=changed,dragCommand=changed)
    from .ui import _safe
    cmds.button(label='고속 프리뷰 켜기',command=lambda *_:_safe(enable));cmds.showWindow(window)

def disable():
    for panel,previous in list(_panels.items()):
        if cmds.modelPanel(panel,exists=True) and cmds.modelEditor(panel,q=True,rendererOverrideName=True)==NAME:
            cmds.modelEditor(panel,e=True,rendererOverrideName=previous)
    _panels.clear()

def status():
    panels=[p for p in cmds.getPanel(type='modelPanel') or [] if cmds.modelEditor(p,q=True,rendererOverrideName=True)==NAME]
    return dict(state='ready',enabled=bool(panels),backend='screen_space_gpu',panels=panels,frames=_library.rp_fast_frames() if _library else 0,
                scope='all visible surfaces',intersections='screen-space approximation',renderer='CPU final render unchanged')

def shutdown():
    global _library,_plugin
    disable()
    if _plugin:cmds.unloadPlugin(_plugin)
    _library=None;_plugin=None
