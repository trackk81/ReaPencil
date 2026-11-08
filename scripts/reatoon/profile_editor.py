"""Interactive width/alpha graph editor; independent UI, existing CPU contract."""
from . import i18n
_labels={'Flip curve':'곡선 좌우 반전','Symmetrize selected side':'선택한 쪽을 대칭 복제','Copy curve':'곡선 복사','Paste curve':'곡선 붙여넣기','Advanced control-point values':'고급 제어점 수치','Curve position':'곡선 위치','Curve value':'곡선 값','Click the curve to add a point. Drag points or handles. Ctrl-click selects multiple points. Delete removes selected points.':'곡선을 클릭해 점을 추가하고 점·핸들을 드래그하세요. Ctrl 클릭으로 다중 선택하고 Delete로 삭제합니다.','Apply saves the curve; Cancel leaves the scene unchanged. Stroke profiles affect normal preview and CPU rendering.':'적용하면 곡선을 저장하며 취소하면 장면은 유지됩니다. 획의 선폭·알파 곡선은 일반 프리뷰와 CPU 렌더에 적용됩니다.'}
i18n.STRINGS.update(_labels);i18n.ALIASES.update({v:k for k,v in _labels.items()});tr=i18n.tr
_axis={'X: stroke start (0) to end (1). Y: width or alpha multiplier.':'X: 획의 시작(0)~끝(1), Y: 선폭 또는 알파 배율입니다.','Curve positions must be distinct':'제어점의 X 위치는 서로 달라야 합니다.','Curve coordinates outside range':'제어점 좌표가 허용 범위를 벗어났습니다.','Invalid curve point':'제어점 값이 올바르지 않습니다.'}
i18n.STRINGS.update(_axis);i18n.ALIASES.update({v:k for k,v in _axis.items()})
_dialogs=[]

def open_editor(node,key,getter=None,setter=None):
    from PySide6 import QtCore,QtGui,QtWidgets
    from maya import OpenMayaUI,cmds
    import shiboken6
    from . import line_graph,maya_scene,viewport
    from .brush_profiles import validate_profile
    from .curve_canvas import CurveCanvas
    if key not in ('width_profile','alpha_profile'):raise ValueError('Unknown brush curve')
    pointer=None if cmds.about(batch=True) else OpenMayaUI.MQtUtil.mainWindow()
    parent=shiboken6.wrapInstance(int(pointer),QtWidgets.QWidget) if pointer else None
    dialog=QtWidgets.QDialog(parent);dialog.setObjectName('reaPencilProfileEditor');dialog.setWindowTitle(tr('Width profile' if key=='width_profile' else 'Alpha profile'));dialog.resize(640,370)
    layout=QtWidgets.QVBoxLayout(dialog);layout.setSpacing(6);toolbar=QtWidgets.QHBoxLayout();layout.addLayout(toolbar)
    source=getter() if getter else line_graph.get_settings(node).get(key,[])
    canvas=CurveCanvas(source);canvas.setToolTip(tr('Click the curve to add a point. Drag points or handles. Ctrl-click selects multiple points. Delete removes selected points.'));dialog.canvas=canvas
    def icon(kind):
        pixmap=QtGui.QPixmap(24,24);pixmap.fill(QtCore.Qt.transparent);p=QtGui.QPainter(pixmap);p.setRenderHint(QtGui.QPainter.Antialiasing);p.setPen(QtGui.QPen(QtGui.QColor('#e3e3e3'),1.5))
        path=QtGui.QPainterPath();path.moveTo(3,19)
        if kind==0:path.lineTo(21,5)
        elif kind in (1,2):path.cubicTo(8,19,12,3,21,5)
        elif kind==3:path.lineTo(11,7);path.lineTo(21,16)
        elif kind==4:path.moveTo(3,12);path.lineTo(21,12);path.moveTo(7,7);path.lineTo(3,12);path.lineTo(7,17);path.moveTo(17,7);path.lineTo(21,12);path.lineTo(17,17)
        else:path.moveTo(12,3);path.lineTo(12,21);path.moveTo(3,18);path.lineTo(8,6);path.lineTo(12,14);path.lineTo(16,6);path.lineTo(21,18)
        p.drawPath(path)
        if kind in (2,3):p.setPen(QtGui.QColor('#c8a55d'));p.drawLine(3,13,18,3);p.setBrush(QtGui.QColor('#e5a958'));p.drawEllipse(QtCore.QPointF(11,7),2.5,2.5)
        p.end();return QtGui.QIcon(pixmap)
    tools=[]
    for kind,label in enumerate(('Linear','Spline','Bezier','Break','Flip curve','Symmetrize selected side')):
        button=QtWidgets.QToolButton();button.setObjectName('curve_tool_'+str(kind));button.setIcon(icon(kind));button.setIconSize(QtCore.QSize(24,24));button.setToolTip(tr(label));toolbar.addWidget(button);tools.append(button)
        button.clicked.connect((lambda checked=False,k=kind:canvas.set_kind(k)) if kind<4 else (lambda:canvas.reverse()) if kind==4 else (lambda:canvas.symmetry()))
    toolbar.addStretch();layout.addWidget(canvas)
    row=QtWidgets.QHBoxLayout();layout.addLayout(row);fields={}
    for label in ('X','Y'):
        row.addWidget(QtWidgets.QLabel(label));field=QtWidgets.QDoubleSpinBox();field.setObjectName('curve_'+label.lower());field.setDecimals(6);field.setRange(0,1);field.setSingleStep(.01);field.setMaximumWidth(100);row.addWidget(field);fields[label]=field
    for label,callback in [('Copy curve',canvas.copy_curve),('Paste curve',canvas.paste_curve)]:
        button=QtWidgets.QPushButton(tr(label));button.setObjectName('copy_curve' if label=='Copy curve' else 'paste_curve');button.clicked.connect(lambda checked=False,fn=callback:fn());row.addWidget(button)
    row.addStretch();layout.addWidget(QtWidgets.QLabel(tr('X: stroke start (0) to end (1). Y: width or alpha multiplier.')));toggle=QtWidgets.QToolButton();toggle.setText(tr('Advanced control-point values'));toggle.setCheckable(True);toggle.setArrowType(QtCore.Qt.RightArrow);toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon);layout.addWidget(toggle)
    table=QtWidgets.QTableWidget(0,7);table.setObjectName('curve_values');table.setHorizontalHeaderLabels(tr(['Type','Left X','Left Y','Position','Value','Right X','Right Y']));table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch);table.setMaximumHeight(200);table.hide();layout.addWidget(table)
    def show_table(enabled):table.setVisible(enabled);toggle.setArrowType(QtCore.Qt.DownArrow if enabled else QtCore.Qt.RightArrow);dialog.adjustSize()
    toggle.toggled.connect(show_table)
    status=QtWidgets.QLabel();status.setObjectName('curve_status');status.setWordWrap(True);layout.addWidget(status)
    note=QtWidgets.QLabel(tr('Apply saves the curve; Cancel leaves the scene unchanged. Stroke profiles affect normal preview and CPU rendering.'));note.setWordWrap(True);layout.addWidget(note)
    controls=QtWidgets.QHBoxLayout();layout.addLayout(controls);guard=[False];table_error=['']
    def selection():
        enabled=bool(canvas.selected)
        for k,f in fields.items():
            f.blockSignals(True);f.setEnabled(enabled)
            if enabled:f.setValue(canvas.points[min(canvas.selected)][3 if k=='X' else 4])
            f.blockSignals(False)
        for button in tools[:4]:button.setEnabled(enabled)
        sides={canvas.points[i][3]<.5 for i in canvas.selected if canvas.points[i][3]!=.5};tools[5].setEnabled(len(sides)==1)
    def sync():
        if guard[0]:return
        guard[0]=True;table.blockSignals(True);table.setRowCount(len(canvas.points))
        for r,values in enumerate(canvas.points):
            combo=QtWidgets.QComboBox();combo.addItems(tr(['Linear','Spline','Bezier','Break']));combo.setCurrentIndex(int(values[0]));table.setCellWidget(r,0,combo);combo.currentIndexChanged.connect(table_changed)
            for c,value in enumerate(values[1:],1):table.setItem(r,c,QtWidgets.QTableWidgetItem(format(value,'.9g')))
        table.blockSignals(False);guard[0]=False;table_error[0]='';status.clear();selection()
    def table_changed(*_):
        if guard[0]:return
        try:
            values=validate_profile([[table.cellWidget(r,0).currentIndex()]+[float(table.item(r,c).text()) for c in range(1,7)] for r in range(table.rowCount())]);canvas.set_points(values)
        except (ValueError,TypeError,AttributeError) as error:table_error[0]=str(error);status.setText(tr(str(error)))
    def numeric():
        if not canvas.selected:return
        canvas.move_selected(fields['X'].value(),fields['Y'].value())
    fields['X'].editingFinished.connect(numeric);fields['Y'].editingFinished.connect(numeric);canvas.changed.connect(sync);canvas.selectionChanged.connect(selection);table.cellChanged.connect(table_changed)
    def apply():
        try:
            if table_error[0]:raise ValueError(table_error[0])
            points=validate_profile(canvas.points)
            with maya_scene.undo_chunk('ReaPencil Brush Curve'):
                if setter is not None:setter(points)
                else:
                    current=line_graph.get_settings(node);current[key]=points;line_graph.set_settings(node,current);viewport.request_refresh(style_changed=True)
            dialog.accept()
        except (ValueError,RuntimeError,TypeError) as error:status.setText(tr(str(error)))
    for label,name,callback in [('Add point','add_point',canvas.add_point),('Remove selected','remove_point',canvas.remove_selected),('Reset to constant','reset_curve',lambda:canvas.set_points([])),('Apply','apply_curve',apply),('Cancel','cancel_curve',dialog.reject)]:
        button=QtWidgets.QPushButton(tr(label));button.setObjectName(name);button.clicked.connect(lambda checked=False,fn=callback:fn());controls.addWidget(button)
    sync();_dialogs.append(dialog);dialog.finished.connect(lambda *_:_dialogs.remove(dialog) if dialog in _dialogs else None);dialog.show();return dialog
