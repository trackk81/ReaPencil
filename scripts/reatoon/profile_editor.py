"""Control-point editor for the CPU brush profiles (stored tangent handles)."""
from .i18n import tr
_dialogs=[]


def open_editor(node,key,getter=None,setter=None):
    from PySide6 import QtCore,QtGui,QtWidgets
    from maya import OpenMayaUI
    import shiboken6
    from . import line_graph
    from .brush_profiles import validate_profile,evaluate_profile
    window=OpenMayaUI.MQtUtil.mainWindow()
    parent=shiboken6.wrapInstance(int(window),QtWidgets.QWidget) if window else None
    dialog=QtWidgets.QDialog(parent);dialog.setWindowTitle(tr('Width profile (CPU)' if key=='width_profile' else 'Alpha profile (CPU)'))
    dialog.resize(820,480);layout=QtWidgets.QVBoxLayout(dialog)
    layout.addWidget(QtWidgets.QLabel(tr('Stored handles; empty curve = constant 1. CPU raster only.')))
    preview=QtWidgets.QLabel();preview.setMinimumHeight(110);layout.addWidget(preview)
    table=QtWidgets.QTableWidget(0,7);table.setHorizontalHeaderLabels(tr(['Type','Left X','Left Y','Position','Value','Right X','Right Y']));table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch);layout.addWidget(table)
    status=QtWidgets.QLabel();layout.addWidget(status)
    buttons=QtWidgets.QHBoxLayout();layout.addLayout(buttons)
    def add(row=None):
        if row is None:
            try:
                old=values();positions=sorted({0.,1.}|{p[3] for p in old})
                x=0. if not old else 1. if len(old)==1 and old[0][3]!=1 else sum(max(zip(positions,positions[1:]),key=lambda pair:pair[1]-pair[0]))/2
                y=float(evaluate_profile(old,[x])[0]);row=[0,x,y,x,y,x,y]
            except (ValueError,TypeError,AttributeError):row=[0,0,1,0,1,0,1]
        r=table.rowCount();table.insertRow(r)
        kind=QtWidgets.QComboBox();kind.addItems(tr(['Linear','Spline','Bezier','Break']));kind.setCurrentIndex(int(row[0]));table.setCellWidget(r,0,kind);kind.currentIndexChanged.connect(update)
        for c,v in enumerate(row[1:],1):table.setItem(r,c,QtWidgets.QTableWidgetItem(format(v,'.9g')))
    def values():
        return validate_profile([[table.cellWidget(r,0).currentIndex()]+[float(table.item(r,c).text()) for c in range(1,7)] for r in range(table.rowCount())])
    def update(*_):
        try:
            import numpy as np
            points=values();u=np.linspace(0,1,601);y=evaluate_profile(points,u)
            image=QtGui.QPixmap(760,110);image.fill(QtGui.QColor('#252525'));painter=QtGui.QPainter(image);painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setPen(QtGui.QPen(QtGui.QColor('#777777'),1));painter.drawRect(10,5,739,99)
            path=QtGui.QPainterPath();path.moveTo(10,104-float(y[0])*99)
            for x,v in zip(u[1:],y[1:]):path.lineTo(10+float(x)*739,104-float(v)*99)
            painter.setPen(QtGui.QPen(QtGui.QColor('#75bfe3'),2));painter.drawPath(path);painter.end();preview.setPixmap(image);status.clear()
        except (ValueError,TypeError,AttributeError) as error:status.setText(str(error))
    def remove():
        for row in sorted({item.row() for item in table.selectedItems()},reverse=True):table.removeRow(row)
        update()
    def apply():
        try:
            from .line_editor import _safe,_setting
            points=values()
            if setter is None:_safe(_setting,node,key,points)
            else:setter(points)
            dialog.accept()
        except (ValueError,TypeError,AttributeError) as error:status.setText(str(error))
    for label,callback in [('Add point',lambda:add()),('Remove selected',remove),('Reset to constant',lambda:(table.setRowCount(0),update())),('Apply',apply),('Cancel',dialog.reject)]:
        button=QtWidgets.QPushButton(tr(label));button.clicked.connect(lambda checked=False,fn=callback:fn());buttons.addWidget(button)
    for row in (getter() if getter is not None else line_graph.get_settings(node).get(key,[])):add(row)
    table.cellChanged.connect(update);update();_dialogs.append(dialog)
    dialog.finished.connect(lambda *_:_dialogs.remove(dialog) if dialog in _dialogs else None);dialog.show();return dialog
