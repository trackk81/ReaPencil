"""Viewport-only performance preferences. Never save CPU renderer settings."""
from maya import cmds
WINDOW='reaPencilPreviewPerformance'
SMOOTH='reaPencilPreviewSmoothLines'
INTERSECTIONS='reaPencilPreviewIntersections'
PROFILES='reaPencilPreviewStrokeProfiles'
BRUSH_NAVIGATION='reaPencilPreviewBrushNavigation'

def alpha_failures():
    """Current preview diagnostics only; never rebuild or evaluate geometry."""
    from . import viewport
    live=viewport._gpu_scene
    if live is None:return []
    return [dict(name=m['name'],reason=m['viewport_alpha_fallback'])
            for m in live.scene['meshes'] if m.get('viewport_alpha_fallback')]

def show_alpha_failures():
    from . import i18n
    def label(en,ko):return en if i18n.language()=='en' else ko
    window='reaPencilPreviewAlphaFailures'
    if cmds.window(window,exists=True):cmds.deleteUI(window)
    cmds.window(window,title=label('Preview — Alpha Error Meshes','프리뷰 — 알파 오류 메시 목록'),widthHeight=(740,340))
    cmds.columnLayout(adjustableColumn=True,rowSpacing=8)
    cmds.text(label=label('These meshes use their original surfaces. Healthy alpha boundaries remain enabled.',
                         '문제 메시만 원래 표면으로 표시하며, 정상 메시의 알파 경계는 유지합니다.'),align='left',wordWrap=True)
    status=cmds.text(align='left')
    listing=cmds.textScrollList(allowMultiSelection=True,height=130)
    detail=cmds.scrollField(editable=False,wordWrap=True,height=85)
    rows=[]
    def chosen(*_):
        indices=cmds.textScrollList(listing,q=True,selectIndexedItem=True) or []
        return [rows[i-1] for i in indices]
    def details(*_):cmds.scrollField(detail,e=True,text='\n\n'.join(r['reason'] for r in chosen()))
    def select(*_):
        names=[r['name'] for r in chosen() if cmds.objExists(r['name'])]
        if names:cmds.select(names,replace=True)
    def refresh(*_):
        rows[:]=alpha_failures();cmds.textScrollList(listing,e=True,removeAll=True)
        if rows:cmds.textScrollList(listing,e=True,append=[r['name'] for r in rows],selectIndexedItem=1)
        cmds.text(status,e=True,label=label('%d affected mesh(es). Unchanged errors skip alpha recalculation.',
                                           '오류 메시 %d개. 같은 입력의 오류는 알파 재계산을 건너뜁니다.')%len(rows));details()
    cmds.textScrollList(listing,e=True,selectCommand=details,doubleClickCommand=select)
    cmds.button(label=label('Select meshes in the scene','장면에서 메시 선택'),command=select)
    cmds.button(label=label('Refresh list (no geometry rebuild)','목록 새로 고침 (지오메트리 재계산 없음)'),command=refresh)
    refresh();cmds.showWindow(window)
    return window
def value(name,default):return bool(cmds.optionVar(q=name)) if cmds.optionVar(exists=name) else bool(default)
def load():
    from . import maya_scene
    settings=maya_scene.load_settings().copy()
    settings['enabled_smooth_mesh']=value(SMOOTH,settings['enabled_smooth_mesh'])
    if not value(INTERSECTIONS,True):settings['intersections']=False;settings['self_intersections']=False
    return settings

def filter_passes(passes):
    if not value(PROFILES,True):
        for item in passes:
            for style in item['styles']:style['width_profile']=[];style['alpha_profile']=[]
    if not value(INTERSECTIONS,True):
        for item in passes:
            for style in item['styles']:style['intersections']=False;style['self_intersections']=False
    return passes

def rebuild():
    from . import viewport
    viewport._gpu_rebuild=True;viewport._smooth_rebuild_only=False
    viewport._gpu_graph_dirty=True
    viewport.request_refresh()
    cmds.refresh(force=True)

def set_option(name,enabled):
    from . import viewport_alpha
    if name not in (SMOOTH,INTERSECTIONS,PROFILES,BRUSH_NAVIGATION,viewport_alpha.OPTION):raise ValueError('Unknown viewport preference')
    cmds.optionVar(intValue=(name,int(bool(enabled))))
    if name==viewport_alpha.OPTION:
        from . import viewport
        viewport._watchers_stale=True
    if name in (PROFILES,BRUSH_NAVIGATION):
        if name==BRUSH_NAVIGATION:
            from . import preview_brush_navigation
            preview_brush_navigation.reset()
        from . import viewport
        viewport._gpu_style_dirty=True;viewport._generation+=1
        viewport.request_refresh();cmds.refresh(force=True)
    else:rebuild()

def show():
    from . import i18n
    def label(en,ko):return en if i18n.language()=='en' else ko
    if cmds.window(WINDOW,exists=True):cmds.deleteUI(WINDOW)
    cmds.window(WINDOW,title=label('ReaPencil — Preview Performance','ReaPencil — 프리뷰 성능 설정'),widthHeight=(460,590),sizeable=False)
    cmds.columnLayout(adjustableColumn=True,rowSpacing=12)
    cmds.text(label=label('Viewport calculation only. Edit line styles in the Line Window.','뷰포트 계산 전용입니다. 선 스타일은 라인 창에서 편집하세요.'),align='left',wordWrap=True,height=36)
    cmds.checkBox('reaPencilPreviewSmoothControl',label=label('Smooth line geometry with the viewport mesh','뷰포트 메시의 스무스를 선에도 적용'),value=load()['enabled_smooth_mesh'],changeCommand=lambda v:set_option(SMOOTH,v))
    cmds.text(label=label('Off: use base-mesh lines while leaving mesh smooth display unchanged.','끄면 메시의 스무스 표시는 유지하고 선은 기본 메시로 계산합니다.'),align='left',wordWrap=True,height=32)
    cmds.checkBox('reaPencilPreviewIntersectionControl',label=label('Allow object/self intersections (slower)','교차선·자체 교차선 계산 허용 (속도 비용 있음)'),value=value(INTERSECTIONS,True),changeCommand=lambda v:set_option(INTERSECTIONS,v))
    cmds.checkBox('reaPencilPreviewProfileControl',label=label('Show stroke width and alpha profiles','선폭·알파 곡선 표시'),value=value(PROFILES,True),changeCommand=lambda v:set_option(PROFILES,v))
    cmds.text(label=label('Turn off to save stroke-connection work in complex scenes. CPU output is unchanged.','복잡한 장면에서 끄면 획 연결 계산을 줄입니다. CPU 렌더는 그대로 유지됩니다.'),align='left',wordWrap=True,height=32)
    cmds.checkBox('reaPencilPreviewBrushNavigationControl',label=label('Keep camera navigation smooth with brush strokes and dashes','붓 스트로크·대시 사용 중 카메라 이동 최적화'),value=value(BRUSH_NAVIGATION,True),changeCommand=lambda v:set_option(BRUSH_NAVIGATION,v))
    cmds.text(label=label('Reuse brush/dash detail while navigating; refresh the exact view after stopping. CPU output is unchanged.','이동 중 붓·대시 표시를 재사용하고 멈추면 현재 시점의 상세 표시로 갱신합니다. CPU 렌더는 유지됩니다.'),align='left',wordWrap=True,height=42)
    from . import viewport_alpha
    cmds.checkBox('reaPencilPreviewAutoAlphaControl',label=label('Detect alpha boundaries from materials','재질 알파 경계 자동 인식'),value=viewport_alpha.enabled(),changeCommand=lambda v:set_option(viewport_alpha.OPTION,v))
    cmds.button(label=label('List meshes with alpha errors','알파 오류 메시 목록'),command=lambda *_:show_alpha_failures())
    resolution=cmds.optionMenuGrp('reaPencilPreviewAlphaResolutionControl',label=label('Alpha boundary resolution','알파 경계 해상도'))
    current=viewport_alpha.resolution()
    choices=sorted(set((128,256,512,1024,2048,4096,current)))
    for n in choices:cmds.menuItem(label=str(n))
    cmds.optionMenuGrp(resolution,e=True,value=str(current))
    def alpha_resolution(*_):
        cmds.optionVar(intValue=(viewport_alpha.RESOLUTION,int(cmds.optionMenuGrp(resolution,q=True,value=True))));rebuild()
    cmds.optionMenuGrp(resolution,e=True,changeCommand=alpha_resolution)
    cmds.text(label=label('Lower resolution can remove thin leaves and change alpha outlines. Explicit Alpha Boundary settings on objects take precedence.','해상도가 낮으면 얇은 잎이 사라지고 알파 윤곽이 달라질 수 있습니다. 오브젝트에 적용한 알파 경계 설정이 우선합니다.'),align='left',wordWrap=True,height=42)
    cmds.button(label=label('Rebuild viewport geometry cache','뷰포트 지오메트리 캐시 다시 계산'),command=lambda *_:rebuild())
    cmds.text(label=label('Changes apply immediately. Final CPU rendering is unaffected.','변경 즉시 적용됩니다. 최종 CPU 렌더 설정은 바뀌지 않습니다.'),align='left',wordWrap=True,height=30)
    cmds.showWindow(WINDOW)
    return WINDOW


def filter_scene(scene):
    if value(INTERSECTIONS,True):return scene
    result=dict(scene)
    result['line_sets']={name:dict(style,intersections=False,self_intersections=False) for name,style in scene.get('line_sets',{}).items()}
    return result
