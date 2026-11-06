"""Native Maya line-set editor, independently implemented from observed workflow."""
from .i18n import tr
import os
import json
import traceback
from maya import cmds
from . import maya_scene

WINDOW = "reaToonWindow"
MENU = "reaToonMainMenu"
_controls = {}
_editing_set = None
_menu_watcher = None
LINE_KEYS = ("line_width", "line_color", "hidden_lines", "hidden_color", "outline", "open_edges", "crease", "crease_angle", "material_boundaries", "hard_edges", "selected_edges", "wireframe", "intersections", "self_intersections", "distance_reduction", "width_variation", "taper", "dash_length")


def _safe(function, *args):
    try:
        return function(*args)
    except Exception as error:
        traceback.print_exc()
        cmds.confirmDialog(title=tr("ReaPencil"), message=tr(str(error)), button=tr(["OK"]), icon="warning")


def remove_menu():
    global _menu_watcher
    if _menu_watcher is not None:
        _menu_watcher.stop()
        _menu_watcher=None
    if cmds.menu(MENU, exists=True):
        cmds.deleteUI(MENU)


def install_menu():
    global _menu_watcher
    # Deferred callbacks can arrive after unload.
    if not hasattr(cmds, "reaToonUI"):
        return
    from . import preview_renderers
    preview_renderers.register()
    remove_menu()
    cmds.menu(MENU, label=tr("ReaPencil"), parent="MayaWindow", tearOff=True)
    cmds.menuItem(label=tr("Open Line Window"), command=lambda *_: show())
    from . import menu_actions
    cmds.menuItem(label=tr("Pencil+ 장면 가져오기 / 이전"),command=lambda *_:_safe(menu_actions.import_pencil_scene))
    cmds.menuItem(label=tr("Add Selected Edges Node"), command=lambda *_: _safe(menu_actions.add_selected_edges))
    cmds.menuItem(label=tr("Delete Unused ReaPencil Nodes"), command=lambda *_: _safe(menu_actions.delete_unused))
    cmds.menuItem(label=tr("Add Render Settings Node"),annotation=tr("Enable Smooth Mesh and open scene render settings"), command=lambda *_: _safe(menu_actions.add_render_settings))
    from . import alpha_boundary
    cmds.menuItem(label=tr("Alpha Boundary"),command=lambda *_:_safe(alpha_boundary.show))
    cmds.menuItem(divider=True)
    from . import fast_viewport
    cmds.menuItem(label=tr("Use ReaPencil in Render Settings"), command=lambda *_: _safe(_select_renderer))
    cmds.menuItem(label=tr("Inspect Pencil+ compatibility"), command=lambda *_: _safe(_pencil_import, True))
    cmds.menuItem(label=tr("Import Pencil+ settings"), command=lambda *_: _safe(menu_actions.import_pencil_scene))
    cmds.menuItem(label=tr("Upgrade Existing ReaPencil Line Sets"),command=lambda *_:_safe(_upgrade_legacy))
    cmds.menuItem(label=tr("Assign converted Maya materials"), command=lambda *_: _safe(_pencil_import, False, True))
    cmds.menuItem(label=tr("Create toon material for selection"), command=lambda *_: _safe(maya_scene.create_toon_material))
    cmds.menuItem(divider=True)
    cmds.menuItem(label=tr("Renderer / Advanced Settings"), command=lambda *_: show_advanced())
    cmds.menuItem(divider=True)
    def updates():
        from . import update_ui
        return update_ui.show()
    cmds.menuItem(label=tr("업데이트 확인…"),command=lambda *_:_safe(updates))
    cmds.menuItem(label=tr("업데이트 설치…"),command=lambda *_:_safe(updates))
    from . import i18n
    cmds.menuItem(divider=True)
    cmds.menuItem(label=tr('ReaPencil Settings…'),command=lambda *_:i18n.show_settings())
    _menu_watcher=_AdjacentMenu()


class _AdjacentMenu:
    """Position our QAction without rebuilding or editing the Pencil+ menu."""
    def __init__(self):
        from maya import OpenMayaUI
        try:
            from PySide6 import QtCore,QtWidgets
            from shiboken6 import wrapInstance
        except ImportError:
            from PySide2 import QtCore,QtWidgets
            from shiboken2 import wrapInstance
        self.main=wrapInstance(int(OpenMayaUI.MQtUtil.mainWindow()),QtWidgets.QMainWindow)
        self.bar=self.main.menuBar()
        owner=self
        class Watch(QtCore.QObject):
            def eventFilter(self,obj,event):
                if event.type() in (QtCore.QEvent.ActionAdded,QtCore.QEvent.ActionChanged,QtCore.QEvent.ActionRemoved):
                    QtCore.QTimer.singleShot(0,owner.place)
                return False
        self.watch=Watch(self.bar)
        self.bar.installEventFilter(self.watch)
        self.active=True
        # Some third-party menus reorder their QAction after deferred startup
        # without a useful Maya event. A light UI-only check covers that case.
        self.timer=QtCore.QTimer(self.watch)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.place)
        self.timer.start()
        QtCore.QTimer.singleShot(0,self.place)

    def place(self):
        if not self.active:return
        actions=self.bar.actions()
        def label(action):return action.text().replace('&','').replace(' ','').lower()
        own=next((a for a in actions if label(a)=='reapencil'),None)
        pencil=next((a for a in actions if label(a).startswith('pencil+')),None)
        if own is None or pencil is None:return
        index=actions.index(pencil)
        if index+1<len(actions) and actions[index+1]==own:return
        self.bar.removeAction(own)
        actions=self.bar.actions()
        index=actions.index(pencil)
        self.bar.insertAction(actions[index+1] if index+1<len(actions) else None,own)

    def stop(self):
        self.active=False
        self.timer.stop()
        self.bar.removeEventFilter(self.watch)
        self.watch.deleteLater()


def show():
    from . import line_editor
    return line_editor.show()


def _upgrade_legacy():
    from . import line_graph,line_editor
    result=line_graph.migrate_legacy()
    line_editor.show()
    line_editor.refresh(result.get('line'))
    if result.get('line'):
        line_editor._open(result['line'])
    return result


def close():
    from . import line_editor
    line_editor.close()
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)
    if cmds.window('revToonCompatibilityReport', exists=True):
        cmds.deleteUI('revToonCompatibilityReport')
    _controls.clear()


def _values():
    values = maya_scene.load_settings()
    for key, (kind, control) in _controls.items():
        if _editing_set and key in LINE_KEYS:
            continue
        if kind == "bool":
            values[key] = cmds.checkBox(control, query=True, value=True)
        elif kind == "float":
            values[key] = cmds.floatFieldGrp(control, query=True, value1=True)
        elif kind == "int":
            values[key] = cmds.intFieldGrp(control, query=True, value1=True)
        elif kind == "color":
            values[key] = cmds.colorSliderGrp(control, query=True, rgbValue=True)
    return maya_scene.validate_settings(values)


def _save(*_):
    _persist()
    cmds.inViewMessage(amg="ReaPencil settings saved in this scene", pos="midCenter", fade=True)


def _line_set(*_):
    node = maya_scene.create_line_set(overrides=_editor_values())
    _refresh_sets(node)
    cmds.inViewMessage(amg="Created " + node + " with current line options", pos="midCenter", fade=True)


def _viewport_on(*_):
    from . import viewport
    if _controls:
        _persist()
    viewport.enable()
    state=viewport.status()
    if state.get('state')=='error':
        raise RuntimeError(state.get('error','Viewport initialization failed'))
    label=('GPU: '+state.get('device','OpenCL')) if state.get('backend') in ('opencl_gpu','retained_gpu','screen_space_gpu') else 'CPU'
    cmds.inViewMessage(amg='ReaPencil live lines enabled — '+label, pos='midCenter', fade=True)


def _viewport_off(*_):
    from . import viewport
    viewport.disable()


def _select_renderer(*_):
    from . import render_integration
    render_integration.register()
    cmds.setAttr("defaultRenderGlobals.currentRenderer", "revtoon", type="string")
    cmds.inViewMessage(amg="Render Using: ReaPencil", pos="midCenter", fade=True)


def _maya_render(*_):
    from . import render_integration
    _persist()
    _select_renderer()
    cmds.waitCursor(state=True)
    try:
        result = render_integration.render_current()
        cmds.scrollField(_controls["status"][1], edit=True, text=str(result), insertionPosition=0)
    finally:
        cmds.waitCursor(state=False)


def _render(*_):
    values = _persist()
    camera = cmds.optionMenuGrp(_controls["camera"][1], query=True, value=True)
    output = cmds.textFieldButtonGrp(_controls["output"][1], query=True, text=True).strip()
    if not output:
        raise ValueError("Choose an output prefix first.")
    cmds.waitCursor(state=True)
    try:
        result = maya_scene.render_scene(output, camera, values)
        cmds.scrollField(_controls["status"][1], edit=True, text=str(result), insertionPosition=0)
    finally:
        cmds.waitCursor(state=False)


def _browse(*_):
    paths = cmds.fileDialog2(fileMode=0, caption="ReaPencil output prefix", fileFilter="PNG (*.png)")
    if paths:
        cmds.textFieldButtonGrp(_controls["output"][1], edit=True, text=os.path.splitext(paths[0])[0])


def _preset(export):
    if export:
        _persist()
    paths = cmds.fileDialog2(fileMode=0 if export else 1, caption="ReaPencil preset", fileFilter="JSON (*.json)")
    if not paths:
        return
    if export:
        maya_scene.save_preset(paths[0])
    else:
        maya_scene.load_preset(paths[0])
        show()


def _pencil_import(inspect_only=False, bake=False):
    from . import pencil_compat
    report = pencil_compat.bake_materials() if bake else pencil_compat.inspect_scene() if inspect_only else pencil_compat.import_scene()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if not inspect_only and report.get('status') == 'imported':
        if cmds.window(WINDOW,exists=True):cmds.deleteUI(WINDOW)
        _controls.clear()
        show()  # Do not let stale controls overwrite the imported settings.
    if cmds.window('revToonCompatibilityReport', exists=True):
        cmds.deleteUI('revToonCompatibilityReport')
    cmds.window('revToonCompatibilityReport', title=tr('Pencil+ import report'), widthHeight=(650, 500))
    cmds.columnLayout(adjustableColumn=True)
    cmds.text(label=tr('Original Pencil+ nodes are preserved. See unsupported items below.'), align='left')
    cmds.scrollField(editable=False, text=text, height=440, wordWrap=True)
    cmds.showWindow('revToonCompatibilityReport')
    return report


def _material(*_):
    shader = maya_scene.create_toon_material()
    cmds.select(shader, replace=True)
    cmds.showEditor(shader)




def _editor_values():
    values = {}
    for key in LINE_KEYS:
        kind, control = _controls[key]
        if kind == "bool":
            values[key] = cmds.checkBox(control, query=True, value=True)
        elif kind == "float":
            values[key] = cmds.floatFieldGrp(control, query=True, value1=True)
        elif kind == "color":
            values[key] = cmds.colorSliderGrp(control, query=True, rgbValue=True)
    return maya_scene.validate_settings(values, partial=True)


def _persist():
    values = _values()
    with maya_scene.undo_chunk("ReaPencil UI settings"):
        if _editing_set:
            if not cmds.objExists(_editing_set):
                raise ValueError("선택한 라인셋이 삭제되었습니다. 목록을 새로 고침하세요.")
            overrides = maya_scene._json_attr(_editing_set, "reaToonOverrides")
            overrides.update(_editor_values())
            maya_scene._json_attr(_editing_set, "reaToonOverrides", overrides)
        maya_scene.save_settings(values)
    return values


def _refresh_sets(selected=None):
    control = _controls['sets'][1]
    cmds.textScrollList(control, edit=True, removeAll=True)
    nodes = sorted(maya_scene._tagged('lineSet', 'objectSet'))
    cmds.textScrollList(control, edit=True, append=[tr('Scene defaults')] + nodes)
    cmds.textScrollList(control, edit=True, selectItem=selected if selected in nodes else tr('Scene defaults'))
    _select_set()


def _select_set(*_):
    global _editing_set
    selected = cmds.textScrollList(_controls['sets'][1], query=True, selectItem=True) or [tr('Scene defaults')]
    _editing_set = None if selected[0] == tr('Scene defaults') else selected[0]
    values = maya_scene.load_settings()
    if _editing_set:
        values.update(maya_scene._json_attr(_editing_set, 'reaToonOverrides'))
    for key in LINE_KEYS:
        kind, control = _controls[key]
        if kind == 'bool':
            cmds.checkBox(control, edit=True, value=values[key])
        elif kind == 'float':
            cmds.floatFieldGrp(control, edit=True, value1=values[key])
        elif kind == 'color':
            cmds.colorSliderGrp(control, edit=True, rgbValue=values[key])
    members = cmds.sets(_editing_set, query=True) or [] if _editing_set else []
    cmds.textScrollList(_controls['members'][1], edit=True, removeAll=True)
    if members:
        cmds.textScrollList(_controls['members'][1], edit=True, append=members)
    cmds.text(_controls['editing'][1], edit=True, label=tr('편집 대상: ' + (_editing_set or tr('Scene defaults'))))


def _membership(action):
    if not _editing_set:
        raise ValueError('먼저 실제 라인셋을 선택하세요.')
    if action == 'select':
        members = cmds.sets(_editing_set, query=True) or []
        cmds.select(members, replace=True) if members else cmds.select(clear=True)
        return
    if action == 'remove':
        members = cmds.textScrollList(_controls['members'][1], query=True, selectItem=True) or []
        if members:
            with maya_scene.undo_chunk('Remove line members'):
                cmds.sets(members, remove=_editing_set)
    else:
        # Reuse the scene API validation; the temporary set is removed in the same undo chunk.
        selection = cmds.ls(selection=True, long=True) or []
        with maya_scene.undo_chunk('Add line members'):
            temporary = maya_scene.create_line_set(name='revtoonMembershipValidation')
            try:
                members = cmds.sets(temporary, query=True) or []
                cmds.sets(members, addElement=_editing_set)
            finally:
                cmds.delete(temporary)
                cmds.select(selection, replace=True) if selection else cmds.select(clear=True)
    _select_set()


def _field(key, label, values):
    value = values[key]
    if isinstance(value, bool):
        _controls[key] = ('bool', cmds.checkBox(label=tr(label), value=value))
    elif isinstance(value, (list, tuple)):
        _controls[key] = ('color', cmds.colorSliderGrp(label=tr(label), rgbValue=value))
    elif isinstance(value, int):
        _controls[key] = ('int', cmds.intFieldGrp(label=tr(label), numberOfFields=1, value1=value))
    else:
        _controls[key] = ('float', cmds.floatFieldGrp(label=tr(label), numberOfFields=1, value1=value, precision=3))


def _frame(label, collapsed=False):
    frame = cmds.frameLayout(label=tr(label), collapsable=True, collapse=collapsed, marginWidth=8, marginHeight=6)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
    return frame


def _end_frame():
    cmds.setParent('..')
    cmds.setParent('..')


def show_advanced():
    global _editing_set
    close()
    _editing_set = None
    values = maya_scene.load_settings()
    cmds.window(WINDOW, title=tr('ReaPencil — Renderer / Advanced Settings'), widthHeight=(680, 860), sizeable=True)
    cmds.scrollLayout(childResizable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=7)
    cmds.text(label=tr('ReaPencil  |  CPU 렌더 설정 · 이전 objectSet 작업 편집'), align='left', height=26)
    cmds.button(label=tr('Line Window / Attribute Editor 열기'),command=lambda *_:show())
    cmds.rowLayout(numberOfColumns=3, adjustableColumn=1)
    cmds.button(label=tr('뷰포트 라인 켜기'), command=lambda *_: _safe(_viewport_on))
    cmds.button(label=tr('끄기'), command=lambda *_: _safe(_viewport_off))
    cmds.button(label=tr('Maya 렌더러로 선택'), command=lambda *_: _safe(_select_renderer))
    cmds.setParent('..')
    _frame('장면 렌더 기본 설정')
    cmds.text(label=tr('새 Line별 설정과 Objects / Materials 대상은 Attribute Editor에서 편집합니다.'), align='left')
    for key,label in [('supersample','오버샘플링 (1–4)'),('seed','난수 시드')]:
        _field(key,label,values)
    _end_frame()
    _frame('이전 버전 objectSet 라인셋 · Legacy',collapsed=True)
    cmds.rowLayout(numberOfColumns=2, adjustableColumn=2)
    cmds.columnLayout(adjustableColumn=True, width=240)
    cmds.text(label=tr('라인셋 목록'), align='left')
    _controls['sets'] = ('list', cmds.textScrollList(height=140, allowMultiSelection=False, selectCommand=lambda *_: _safe(_select_set)))
    cmds.button(label=tr('선택한 오브젝트 / 에지로 새 라인셋'), command=lambda *_: _safe(_line_set))
    cmds.button(label=tr('목록 새로 고침'), command=lambda *_: _safe(_refresh_sets))
    cmds.setParent('..')
    cmds.columnLayout(adjustableColumn=True)
    cmds.text(label=tr('선택 라인셋의 오브젝트 / 에지'), align='left')
    _controls['members'] = ('list', cmds.textScrollList(height=140, allowMultiSelection=True))
    cmds.rowLayout(numberOfColumns=3, adjustableColumn=1)
    cmds.button(label=tr('현재 선택 추가'), command=lambda *_: _safe(_membership,'add'))
    cmds.button(label=tr('목록 항목 제외'), command=lambda *_: _safe(_membership,'remove'))
    cmds.button(label=tr('장면에서 선택'), command=lambda *_: _safe(_membership,'select'))
    cmds.setParent('..'); cmds.setParent('..'); cmds.setParent('..')
    cmds.text(label=tr('이 목록은 0.5 이전 objectSet 방식만 편집합니다. 새 Line 노드가 있으면 AE의 LineSet 순서와 Objects / Materials 대상이 적용됩니다.\n이전 방식에서는 이름순 마지막 셋이 우선합니다.'), align='left', wordWrap=True, height=38)
    _end_frame()
    _controls['editing'] = ('label', cmds.text(label=tr('편집 대상: 장면 기본값'), align='left', height=25))
    tabs = cmds.tabLayout(innerMarginWidth=8, innerMarginHeight=8)
    visible = cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
    _frame('선 종류 · Edge detection')
    for key,label in [('outline','윤곽선'),('open_edges','열린 경계'),('intersections','오브젝트 교차선'),('self_intersections','자기 교차선'),('hard_edges','하드 에지'),('material_boundaries','재질 경계'),('selected_edges','라인셋에 저장한 선택 에지'),('crease','법선 각도'),('wireframe','모든 폴리곤 에지')]:
        _field(key,label,values)
    _field('crease_angle','법선 각도 최소값 (도)',values)
    _end_frame()
    _frame('브러시 설정 · Brush Settings')
    _field('line_color','가시선 색',values)
    _field('line_width','선 두께 (픽셀)',values)
    _end_frame()
    cmds.setParent('..')
    hidden = cmds.columnLayout(adjustableColumn=True, rowSpacing=6)
    _field('hidden_lines','은선 표시',values)
    _field('hidden_color','은선 색',values)
    cmds.text(label=tr('은선의 선 종류와 두께는 가시선 설정을 공유합니다.\nPencil+의 독립 은선 브러시·종류별 브러시는 아직 지원하지 않습니다.'), align='left', wordWrap=True, height=48)
    cmds.setParent('..')
    brush = cmds.columnLayout(adjustableColumn=True, rowSpacing=6)
    for key,label in [('distance_reduction','거리별 두께 감소'),('width_variation','두께 변화 (0–1)'),('taper','에지 끝 가늘게 (0–1)'),('dash_length','점선 길이 (픽셀)')]:
        _field(key,label,values)
    cmds.text(label=tr('위 항목은 ReaPencil의 간소화된 스트로크 기능입니다.\n브러시 이미지·텍스처 맵·혼합 모드·원본 감소 곡선은 지원하지 않습니다.'), align='left', wordWrap=True, height=48)
    cmds.setParent('..')
    cmds.tabLayout(tabs, edit=True, tabLabel=tr(((visible,'가시선 · Visible'),(hidden,'은선 · Hidden'),(brush,'브러시 상세 · Detail'))))
    cmds.setParent('..')
    cmds.button(label=tr('현재 편집 대상에 적용 · 장면에 저장'), height=32, command=lambda *_: _safe(_save))
    _frame('재질 · Material', True)
    cmds.button(label=tr('선택에 툰 재질 생성 / 할당'), command=lambda *_: _safe(_material))
    cmds.text(label=tr('재질 색·임계값은 Attribute Editor에서 편집합니다. 텍스처와 그림자는 미지원입니다.'), align='left', wordWrap=True)
    _end_frame()
    _frame('Pencil+ 기존 장면 가져오기', True)
    cmds.button(label=tr('변환 가능 항목 분석'), command=lambda *_: _safe(_pencil_import,True))
    cmds.button(label=tr('설정 가져오기 · 원본 노드 보존'), command=lambda *_: _safe(_pencil_import,False))
    cmds.button(label=tr('Maya 램프 재질로 명시적으로 할당 전환'), command=lambda *_: _safe(_pencil_import,False,True))
    cmds.text(label=tr('현재 프레임 스냅샷입니다. 미지원 항목은 보고서에 표시됩니다. PLD는 미지원입니다.'), align='left', wordWrap=True)
    _end_frame()
    _frame('렌더 / 출력 · Render', True)
    _controls['camera'] = ('camera',cmds.optionMenuGrp(label=tr('카메라')))
    cameras=maya_scene.camera_names()
    for name in cameras:
        cmds.menuItem(label=name)
    if cameras:
        active=next((c for c in cameras if cmds.getAttr(c+'.renderable')),cameras[0])
        cmds.optionMenuGrp(_controls['camera'][1],edit=True,value=active)
    cmds.text(label=tr('라인 전용 출력 · 투명 배경 · 오브젝트 면 색상 제외'),align='left')
    for key,label in [('width','출력 너비'),('height','출력 높이'),('depth_bias','깊이 오차 보정')]:
        _field(key,label,values)
    output=os.path.join(cmds.workspace(query=True,rootDirectory=True),'images','revtoon')
    _controls['output']=('output',cmds.textFieldButtonGrp(label=tr('출력 경로 접두사'),buttonLabel=tr('찾기'),text=output,buttonCommand=_browse))
    cmds.button(label=tr('Maya 렌더 설정으로 현재 프레임 렌더'),command=lambda *_: _safe(_maya_render))
    cmds.button(label=tr('위 출력 경로에 렌더 · 같은 이름 파일 교체'),command=lambda *_: _safe(_render))
    cmds.rowLayout(numberOfColumns=2,adjustableColumn=1)
    cmds.button(label=tr('프리셋 내보내기'),command=lambda *_: _safe(_preset,True))
    cmds.button(label=tr('프리셋 가져오기'),command=lambda *_: _safe(_preset,False))
    cmds.setParent('..')
    _end_frame()
    _controls['status']=('status',cmds.scrollField(editable=False,height=65,wordWrap=True,text=tr('준비됨 · 선택한 라인셋의 값을 편집한 뒤 적용하세요.')))
    _refresh_sets()
    cmds.showWindow(WINDOW)
