"""Modeless surface drawing tool and passive Qt tablet-pressure observation.

No tablet driver, trust or global Maya preference is changed. Mouse input uses
full pressure; tablet events are observed only while our context is active.
"""
import time,math
from maya import cmds
from maya.api import OpenMayaUI as ui
from maya import OpenMayaUI as ui1
from PySide6 import QtCore,QtGui,QtWidgets
import shiboken6
from .numeric_slider import NumericSlider

_filter=None;_window=None;_pressure=1.;_tablet=False;_stamp=0.

def _text(en,ko):
    from . import i18n
    return en if i18n.language()=='en' else ko

class TabletFilter(QtCore.QObject):
    def eventFilter(self,obj,event):
        global _pressure,_tablet,_stamp
        kind=event.type()
        wanted=(QtCore.QEvent.TabletPress,QtCore.QEvent.TabletMove,QtCore.QEvent.TabletRelease,QtCore.QEvent.MouseButtonPress)
        if kind not in wanted:return False
        if cmds.currentCtx()!='reaPencilSurfaceDrawContext':return False
        # UI sliders and unrelated editors must not supply pen pressure.
        ancestor=obj;viewport=False
        while ancestor is not None:
            if 'modelPanel' in ancestor.objectName():viewport=True;break
            ancestor=ancestor.parent()
        if not viewport:return False
        if kind in wanted[:3]:
            if kind!=QtCore.QEvent.TabletRelease:
                _pressure=max(0.,min(1.,float(event.pressure())));_tablet=True;_stamp=time.monotonic()
        elif event.source()==QtCore.Qt.MouseEventNotSynthesized:
            _pressure=1.;_tablet=False;_stamp=0.
        return False

def install_tablet_filter():
    global _filter
    if _filter is None:
        app=QtWidgets.QApplication.instance()
        if app is not None:_filter=TabletFilter(app);app.installEventFilter(_filter)

def current_pressure():
    return _pressure if _tablet and time.monotonic()-_stamp<2. else 1.

class BrushPreview(QtWidgets.QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.setMinimumHeight(80);self.shape='uniform';self.width=8.
    def paintEvent(self,event):
        painter=QtGui.QPainter(self);painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(),QtGui.QColor(45,45,45))
        n=150;previous=None
        for i in range(n+1):
            t=i/n;point=QtCore.QPointF(12+(self.width_px()-24)*t,self.height()*.52+12*math.sin(t*math.pi*2))
            scale=1.
            if self.shape=='taper':scale=max(.05,min(1.,t/.15,(1-t)/.15))
            elif self.shape=='wedge':scale=.05+.95*t
            pen=QtGui.QPen(QtGui.QColor(225,225,225),max(.2,min(self.width,28)*scale),QtCore.Qt.SolidLine,QtCore.Qt.RoundCap)
            painter.setPen(pen)
            if previous is not None:painter.drawLine(previous,point)
            previous=point
    def width_px(self):return QtWidgets.QWidget.width(self)

class BrushWindow(QtWidgets.QDialog):
    def __init__(self,shape,sets,parent):
        from . import surface_lines as sl,line_graph as graph
        super().__init__(parent);self.shape=shape;self.setObjectName('reaPencilSurfaceDrawing');self.setWindowTitle(_text('ReaPencil — Surface Brush (Test)','ReaPencil — 표면 브러시 (테스트)'));self.resize(480,620)
        self.setWindowFlag(QtCore.Qt.Tool,True);outer=QtWidgets.QVBoxLayout(self);outer.setContentsMargins(4,4,4,4);scroll=QtWidgets.QScrollArea();scroll.setWidgetResizable(True);scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff);body=QtWidgets.QWidget();layout=QtWidgets.QVBoxLayout(body);scroll.setWidget(body);outer.addWidget(scroll)
        label=QtWidgets.QLabel(shape);label.setWordWrap(True);layout.addWidget(label)
        form=QtWidgets.QFormLayout();layout.addLayout(form)
        self.sets=QtWidgets.QComboBox();self.sets.setObjectName('surfaceBrushLineSet');self.sets.addItems(sets);form.addRow(_text('Line Set','라인셋'),self.sets)
        self.width=NumericSlider();self.width.setObjectName('surfaceBrushWidth');self.width.setRange(.1,256.);self.width.setDecimals(2);self.width.setSuffix(' px');self.slider=self.width.slider;form.addRow(_text('New stroke width','새 선 굵기'),self.width)
        self.width.setToolTip(_text('Only affects strokes drawn next. Line Set width remains the overall scale.','이후에 그리는 선부터 적용합니다. 라인셋 선폭은 전체 배율 기준으로 유지됩니다.'))
        self.base_width=QtWidgets.QLabel();form.addRow(_text('Line Set base width','라인셋 기준 선폭'),self.base_width)
        self.shapes=QtWidgets.QComboBox();self.shapes.setObjectName('surfaceBrushShape')
        for en,ko,data in [('Round / Uniform','원형 · 일정','uniform'),('Round / Tapered ends','원형 · 양끝 가늘게','taper'),('Round / Wedge','원형 · 점점 굵게','wedge')]:self.shapes.addItem(_text(en,ko),data)
        form.addRow(_text('Stroke shape','브러시 모양'),self.shapes)
        self.preview=BrushPreview();layout.addWidget(self.preview)
        self.pressure=QtWidgets.QCheckBox(_text('Tablet pressure controls width','태블릿 필압으로 굵기 조절'));self.pressure.setObjectName('surfaceBrushPressure');form.addRow('',self.pressure)
        self.minimum=NumericSlider();self.minimum.setObjectName("surfaceBrushMinimum");self.minimum.setRange(0,100);self.minimum.setValue(sl._brush['minimum']*100);self.minimum.setSuffix(' %');form.addRow(_text('Minimum pressure width','최소 필압 굵기'),self.minimum)
        self.smoothing=NumericSlider();self.smoothing.setObjectName('surfaceBrushStabilization');self.smoothing.setRange(0,100);self.smoothing.setValue(sl._brush.get('stabilization_strength',30));self.smoothing.setSuffix(' %');self.stabilizer_slider=self.smoothing.slider;form.addRow(_text('Hand stabilization','손떨림 보정'),self.smoothing)
        self.catchup=QtWidgets.QCheckBox(_text('Catch up to endpoint on release','펜을 떼면 끝점 따라잡기'));self.catchup.setChecked(sl._brush.get('catchup',True));form.addRow('',self.catchup)
        self.eraser_radius=NumericSlider();self.eraser_radius.setObjectName('surfaceBrushEraserRadius');self.eraser_radius.setRange(1,200);self.eraser_radius.setValue(sl._eraser['radius']);self.eraser_radius.setSuffix(' px');form.addRow(_text('Eraser radius','지우개 반경'),self.eraser_radius)
        self.preview_aa=QtWidgets.QComboBox();self.preview_aa.setObjectName('surfacePreviewAA')
        for samples in (0,2,4,8):self.preview_aa.addItem(_text('Off','끄기') if samples==0 else str(samples)+_text(' samples','배'),samples)
        enabled=bool(cmds.getAttr('hardwareRenderingGlobals.multiSampleEnable'));samples=int(cmds.getAttr('hardwareRenderingGlobals.multiSampleCount')) if enabled else 0
        if self.preview_aa.findData(samples)<0:self.preview_aa.addItem(str(samples)+_text(' samples','배'),samples)
        self.preview_aa.setCurrentIndex(self.preview_aa.findData(samples));self.preview_aa.setToolTip(_text('Applies to the entire viewport. Higher values cost GPU time. CPU render sampling is unchanged.','뷰포트 전체에 적용됩니다. 값이 높으면 GPU 부하가 늘 수 있습니다. CPU 렌더 샘플링은 바뀌지 않습니다.'));form.addRow(_text('Viewport anti-aliasing','뷰포트 AA'),self.preview_aa);self.preview_aa.currentIndexChanged.connect(self.change_preview_aa)
        self.status=QtWidgets.QLabel();layout.addWidget(self.status)
        hint=QtWidgets.QLabel(_text('Width/shape/pressure affect new strokes. Color and alpha use the Line Set. Changing Line Set width scales all its strokes. Q exits; Ctrl+Z undoes.','굵기·모양·필압은 새 선부터 적용됩니다. 색상·알파는 라인셋을 따릅니다.\n라인셋 선폭 변경은 기존 선 전체에 적용됩니다. Q로 종료 · Ctrl+Z로 취소'));hint.setWordWrap(True);layout.addWidget(hint)
        start=QtWidgets.QPushButton(_text('Start drawing','선 그리기 시작'));start.setObjectName('surfaceBrushStart');layout.addWidget(start)
        erase=QtWidgets.QPushButton(_text('Start erasing this Line Set','현재 라인셋 지우개 시작'));erase.setObjectName('surfaceBrushEraser');layout.addWidget(erase)
        select=QtWidgets.QPushButton(_text('Select strokes on this mesh','이 메시의 그린 선 선택'));layout.addWidget(select)
        repair=QtWidgets.QPushButton(_text('Repair selected old mouse strokes','선택한 이전 직접 그리기 선 복구'));layout.addWidget(repair)
        start.clicked.connect(lambda:sl.begin(self.shape,self.sets.currentText()))
        erase.clicked.connect(self.start_eraser)
        select.clicked.connect(lambda:cmds.select([n for n in sl.nodes() if self.shape in (cmds.ls(cmds.listConnections(n+'.source',s=True,d=False,shapes=True) or [],long=True) or [])],replace=True))
        repair.clicked.connect(self.repair_legacy)
        self.width.valueChanged.connect(self.width_changed);self.sets.currentTextChanged.connect(self.load_set)
        for signal in (self.shapes.currentIndexChanged,self.pressure.toggled,self.minimum.valueChanged,self.smoothing.valueChanged,self.catchup.toggled):signal.connect(self.brush_changed)
        self.pressure.setChecked(sl._brush['pressure']);self.load_set();self.brush_changed()
        self.timer=QtCore.QTimer(self);self.timer.timeout.connect(self.update_status);self.timer.start(150)
    def load_set(self,*_):
        from . import line_graph as graph
        from . import surface_lines as sl
        _,resolved=sl.source_style(self.sets.currentText());base=resolved.get('line_width',1.5);self.base_width.setText(str(base)+' px')
        self.width.blockSignals(True);self.width.setValue(sl._brush.get('width') or base);self.width.blockSignals(False);sl._brush['width']=self.width.value()
        self.preview.width=self.width.value();self.preview.update()
    def width_changed(self,value):
        from . import surface_lines as sl
        sl._brush['width']=value
        self.preview.width=value;self.preview.update()
    def brush_changed(self,*_):
        from . import surface_lines as sl
        sl._brush.update(shape=self.shapes.currentData(),pressure=self.pressure.isChecked(),minimum=self.minimum.value()/100.,stabilization_strength=self.smoothing.value(),catchup=self.catchup.isChecked())
        self.preview.shape=self.shapes.currentData();self.preview.update();self.minimum.setEnabled(self.pressure.isChecked())
    def update_status(self):
        if cmds.currentCtx()=='reaPencilSurfaceEraseContext':
            self.status.setText(_text('Eraser: authored strokes in this mesh/Line Set · Ctrl+Z restores','지우개: 이 메시·라인셋에 직접 그린 선 · Ctrl+Z로 복구'));return
        if _tablet and time.monotonic()-_stamp<2.:self.status.setText(_text('Tablet pressure: ','태블릿 필압: ')+str(round(_pressure*100))+' %')
        else:self.status.setText(_text('Mouse: full width / waiting for tablet events','마우스: 최대 굵기 / 태블릿 필압 입력 대기'))
    def start_eraser(self):
        from . import surface_lines as sl,surface_eraser
        sl._eraser['radius']=self.eraser_radius.value();surface_eraser.begin(self.shape,self.sets.currentText(),sl._eraser['radius'])
    def change_preview_aa(self,*_):
        samples=self.preview_aa.currentData();cmds.setAttr('hardwareRenderingGlobals.multiSampleEnable',samples>0)
        if samples:cmds.setAttr('hardwareRenderingGlobals.multiSampleCount',samples)
        cmds.refresh(force=True)
    def repair_legacy(self):
        from . import surface_lines as sl
        message=_text('Only select strokes directly drawn with the old mouse tool. Imported/demo strokes were already correct and must not be repaired. Apply to selected stroke nodes? Undo is available.','이전 도구로 직접 그린 선만 선택하세요. 데모·가져오기 선은 정상 좌표이므로 복구하면 안 됩니다.\n선택한 선 노드를 복구할까요? Ctrl+Z로 취소할 수 있습니다.')
        if QtWidgets.QMessageBox.question(self,_text('Repair old drawings','이전 그리기 복구'),message,QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No,QtWidgets.QMessageBox.No)==QtWidgets.QMessageBox.Yes:
            try:sl.repair_selected_legacy_drawings()
            except ValueError as error:QtWidgets.QMessageBox.information(self,self.windowTitle(),str(error))

def show():
    global _window
    from . import line_graph as graph
    shapes=[]
    for n in cmds.ls(sl=True,long=True) or []:shapes.extend([n] if cmds.nodeType(n)=='mesh' else cmds.listRelatives(n,shapes=True,noIntermediate=True,fullPath=True,type='mesh') or [])
    if len(shapes)!=1:raise ValueError(_text('Select one polygon mesh first','먼저 폴리곤 메시 하나를 선택하세요'))
    sets=[s for l in graph.list_lines() for s in graph.list_sets(l)]
    if not sets:raise ValueError(_text('Create a ReaPencil Line Set first','먼저 ReaPencil 라인셋을 만드세요'))
    if _window is not None:_window.close();_window.deleteLater()
    parent=shiboken6.wrapInstance(int(ui1.MQtUtil.mainWindow()),QtWidgets.QWidget)
    _window=BrushWindow(shapes[0],sets,parent);_window.show();install_tablet_filter();return _window
