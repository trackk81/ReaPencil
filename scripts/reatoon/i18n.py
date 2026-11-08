"""User preference localization; never translates node identifiers or attributes."""
from maya import cmds
from .ui_strings import STRINGS
OPTION='reaPencilLanguage'
ALIASES={v:k for k,v in STRINGS.items()}
ALIASES.update({'Alpha Boundary / 알파 경계선':'Alpha Boundary','끄기':'Disable live viewport lines','윤곽선':'Outline','열린 경계':'Open edges','하드 에지':'Hard edges','재질 경계':'Material boundaries','법선 각도':'Crease','모든 폴리곤 에지':'All polygon edges','라인셋에 저장한 선택 에지':'Stored selected edges'})
def _clean_korean(text):
    for suffix in (' · Edge detection',' · Brush Settings',' · Visible',' · Hidden',' · Detail',' · Material',' · Render',' · Legacy'):text=text.replace(suffix,'')
    for a,b in (('Attribute Editor','속성 편집기'),('Line Window','라인 창'),('Objects / Materials','오브젝트 / 재질'),('LineSet','라인셋'),('새 Line별','새 라인별'),('이전된 Line','이전된 라인')):text=text.replace(a,b)
    return text
for en,ko in list(STRINGS.items()):
    clean=_clean_korean(ko);STRINGS[en]=clean;ALIASES[clean]=en
def language():return cmds.optionVar(q=OPTION) if cmds.optionVar(exists=OPTION) else 'ko'
def tr(value):
    if isinstance(value,(list,tuple)):return type(value)(tr(v) for v in value)
    if not isinstance(value,str):return value
    key=ALIASES.get(value,value)
    if key not in STRINGS:
        for prefix in sorted(set(STRINGS)|set(ALIASES),key=len,reverse=True):
            if prefix.endswith((' ',': ','(')) and value.startswith(prefix):return tr(prefix)+tr(value[len(prefix):])
    if language()=='en':return key
    result=STRINGS.get(key,value)
    result=_clean_korean(result) if key in STRINGS else result
    return result

def set_language(value):
    if value not in ('en','ko'):raise ValueError(value)
    cmds.optionVar(stringValue=(OPTION,value));cmds.savePrefs(general=True)
    from . import ui
    ui.install_menu()
    # Translate existing dialogs in place, preserving edits and scene selection.
    from PySide6 import QtWidgets
    for root in QtWidgets.QApplication.allWidgets():
        if not (root.objectName().startswith(('reaToon','revToon','reaPencil')) or (root.isWindow() and root.windowTitle().startswith('ReaPencil'))):continue
        for widget in [root]+root.findChildren(QtWidgets.QWidget):
            if isinstance(widget,(QtWidgets.QLabel,QtWidgets.QAbstractButton)):widget.setText(tr(widget.text()))
            if isinstance(widget,QtWidgets.QGroupBox):widget.setTitle(tr(widget.title()))
            if widget.isWindow():widget.setWindowTitle(tr(widget.windowTitle()))
            if isinstance(widget,QtWidgets.QTabWidget):
                for i in range(widget.count()):widget.setTabText(i,tr(widget.tabText(i)))
            if isinstance(widget,QtWidgets.QTableWidget):
                for column in range(widget.columnCount()):
                    item=widget.horizontalHeaderItem(column)
                    if item is not None:item.setText(tr(item.text()))
            if isinstance(widget,QtWidgets.QComboBox) and all(widget.itemText(i) in set(STRINGS)|set(ALIASES)|{'FXAA'} for i in range(widget.count())):
                widget.blockSignals(True)
                for i in range(widget.count()):widget.setItemText(i,tr(widget.itemText(i)))
                widget.blockSignals(False)
            widget.setToolTip(tr(widget.toolTip()))
    from maya import mel
    mel.eval('refreshEditorTemplates;')

def show_settings():
    window='reaPencilSettings'
    if cmds.window(window,exists=True):cmds.deleteUI(window)
    cmds.window(window,title=tr('ReaPencil Settings'),widthHeight=(360,110),sizeable=False)
    cmds.columnLayout(adjustableColumn=True,rowSpacing=12)
    control=cmds.optionMenuGrp(label=tr('Language'),changeCommand=lambda v:set_language('en' if v=='English' else 'ko'))
    cmds.menuItem(label='English');cmds.menuItem(label='한국어')
    cmds.optionMenuGrp(control,e=True,select=1 if language()=='en' else 2)
    cmds.button(label=tr('Close'),command=lambda *_:cmds.deleteUI(window))
    cmds.showWindow(window)
