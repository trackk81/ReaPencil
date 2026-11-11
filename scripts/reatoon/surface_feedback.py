"""Viewport-local brush cursor. No scene nodes or global cursor override."""
from maya import cmds
from maya.api import OpenMayaUI as ui
from PySide6 import QtCore,QtGui,QtWidgets
from shiboken6 import wrapInstance,isValid

_controller=None

class Ring(QtWidgets.QWidget):
    def __init__(self,parent):
        super().__init__(parent,QtCore.Qt.ToolTip|QtCore.Qt.FramelessWindowHint|QtCore.Qt.WindowTransparentForInput|QtCore.Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.diameter=1.
    def paintEvent(self,event):
        p=QtGui.QPainter(self);p.setRenderHint(QtGui.QPainter.Antialiasing)
        center=QtCore.QPointF(self.width()/2.,self.height()/2.);radius=self.diameter/2.
        p.setBrush(QtCore.Qt.NoBrush)
        for color,width in ((QtGui.QColor(0,0,0,220),3.),(QtGui.QColor(255,255,255,245),1.)):
            p.setPen(QtGui.QPen(color,width));p.drawEllipse(center,radius,radius)

class Controller(QtCore.QObject):
    def __init__(self):
        super().__init__();self.host=None;self.ring=None;self.original=None;self.explicit=False
        self.overridden=False
        self.timer=QtCore.QTimer(self);self.timer.timeout.connect(self.update);self.timer.start(16)
    def hide(self):
        if self.ring and isValid(self.ring):self.ring.hide()
        if self.host and isValid(self.host) and self.original is not None:
            if self.explicit:self.host.setCursor(self.original)
            else:self.host.unsetCursor()
        self.original=None
        if self.overridden:QtWidgets.QApplication.restoreOverrideCursor();self.overridden=False
    def update(self):
        from . import surface_lines as sl
        context=cmds.currentCtx()
        if context not in ('reaPencilSurfaceDrawContext','reaPencilSurfaceEraseContext'):
            self.hide();return
        view=ui.M3dView.active3dView();host=wrapInstance(int(view.widget()),QtWidgets.QWidget)
        if self.host is None or not isValid(self.host) or self.host!=host:
            self.hide()
            if self.ring and isValid(self.ring):self.ring.deleteLater()
            self.host=host;self.ring=Ring(host)
        pos=QtGui.QCursor.pos();widget=QtWidgets.QApplication.widgetAt(pos)
        if widget is None or (widget!=host and not host.isAncestorOf(widget)):
            self.hide();return
        if context=='reaPencilSurfaceEraseContext':
            from .surface_eraser import _state
            diameter=2.*_state.get('radius',20.)
        else:
            source=sl._draw.get('source_style',{});active=bool(sl._draw.get('ids'))
            options=sl._draw.get('brush',{}) if active else (sl._draw.get('brush_options') or sl._brush)
            diameter=(float(source.get('line_width',1.5))*options.get('width_scale',1.)) if active else (options.get('width') or source.get('line_width',1.5))
            diameter*=source.get('brush_size_scale',1.)
            if source.get('relative_line_size'):diameter*=view.portWidth()/640.
            if options.get('pressure'):
                from .surface_brush_ui import current_pressure
                diameter*=max(options.get('minimum',.1),current_pressure())
        ratio=host.devicePixelRatioF();diameter=max(.5,float(diameter))/ratio
        self.ring.diameter=diameter;size=max(9,int(diameter+8));point=pos
        self.ring.setGeometry(round(point.x()-size/2),round(point.y()-size/2),size,size)
        if self.original is None:
            self.explicit=host.testAttribute(QtCore.Qt.WA_SetCursor);self.original=host.cursor()
            host.setCursor(QtCore.Qt.BlankCursor)
        if not self.overridden:QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.BlankCursor);self.overridden=True
        self.ring.show();self.ring.raise_();self.ring.update();self.ring.repaint()

def install():
    global _controller
    if cmds.about(batch=True):return
    if _controller is None:_controller=Controller()
    _controller.update()

def update_now():
    if _controller is not None:_controller.update()
