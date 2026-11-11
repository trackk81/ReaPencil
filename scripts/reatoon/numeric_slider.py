"""Precision number input paired with a full-width, synchronized slider."""
import math
from PySide6 import QtCore,QtWidgets

class NumericSlider(QtWidgets.QWidget):
    valueChanged=QtCore.Signal(float)
    sliderPressed=QtCore.Signal()
    sliderReleased=QtCore.Signal()
    def __init__(self,parent=None):
        super().__init__(parent)
        layout=QtWidgets.QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
        self.spin=QtWidgets.QDoubleSpinBox();self.spin.setDecimals(2);self.spin.setFixedWidth(100);self.spin.setKeyboardTracking(False)
        self.slider=QtWidgets.QSlider(QtCore.Qt.Horizontal);self.slider.setRange(0,10000);self.slider.setMinimumWidth(140)
        layout.addWidget(self.spin);layout.addWidget(self.slider,1)
        self.spin.valueChanged.connect(self._spin_changed);self.slider.valueChanged.connect(self._slide_changed)
        self.slider.sliderPressed.connect(self.sliderPressed);self.slider.sliderReleased.connect(self.sliderReleased)
        self.slider.installEventFilter(self)
        self._sync()
    def eventFilter(self,source,event):
        if source is self.slider:
            if event.type()==QtCore.QEvent.MouseButtonPress and event.button()==QtCore.Qt.LeftButton:
                # Qt may move the handle before emitting sliderPressed. Begin
                # the scene gesture before that first value change too.
                self.sliderPressed.emit()
            elif event.type()==QtCore.QEvent.MouseButtonRelease and event.button()==QtCore.Qt.LeftButton:
                # Groove clicks do not always emit QSlider.sliderReleased.
                QtCore.QTimer.singleShot(0,self.sliderReleased.emit)
        return super().eventFilter(source,event)
    def setObjectName(self,name):
        super().setObjectName(name);self.spin.setObjectName(name+'Number');self.slider.setObjectName(name+'Slider')
    def _position(self,value):
        low,high=self.spin.minimum(),self.spin.maximum();span=high-low
        if span<=0:return 0
        fraction=math.log1p((value-low)/5.)/math.log1p(span/5.) if span>300 else (value-low)/span
        return round(10000*max(0.,min(1.,fraction)))
    def _number(self,position):
        low,high=self.spin.minimum(),self.spin.maximum();span=high-low;fraction=position/10000.
        return low+5.*math.expm1(fraction*math.log1p(span/5.)) if span>300 else low+span*fraction
    def _sync(self):
        blocked=self.slider.blockSignals(True);self.slider.setValue(self._position(self.value()));self.slider.blockSignals(blocked)
        probe=self.value()+self.spin.singleStep()
        if probe>self.maximum():probe=max(self.minimum(),self.value()-self.spin.singleStep())
        step=max(1,abs(self._position(probe)-self._position(self.value())))
        self.slider.setSingleStep(step);self.slider.setPageStep(max(step,step*10))
    def _spin_changed(self,value):self._sync();self.valueChanged.emit(value)
    def _slide_changed(self,position):self.spin.setValue(self._number(position))
    def setRange(self,low,high):self.spin.setRange(low,high);self._sync()
    def setValue(self,value):self.spin.setValue(value);self._sync()
    def value(self):return self.spin.value()
    def minimum(self):return self.spin.minimum()
    def maximum(self):return self.spin.maximum()
    def setDecimals(self,value):self.spin.setDecimals(value);self._sync()
    def setSingleStep(self,value):self.spin.setSingleStep(value);self._sync()
    def setSuffix(self,value):self.spin.setSuffix(value)
    def isSliderDown(self):return self.slider.isSliderDown()
