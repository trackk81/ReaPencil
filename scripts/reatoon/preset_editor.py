"""Line Set preset gallery. Selecting a card edits only its own settings."""
import json
from maya import cmds,OpenMayaUI
from PySide6 import QtCore,QtGui,QtWidgets
from shiboken6 import wrapInstance
from . import stroke_presets as presets,preset_library as library
from .numeric_slider import NumericSlider

_windows={}

def text(en,ko):
    from .i18n import language
    return en if language()=='en' else ko

def thumbnail(shape,brush,width=8.,period=20.,amplitude=3.,roughness=1.,density=1.,width_scale=1.,line_image=None,brush_image=None,brush_spacing=24.):
    import numpy as np
    from . import renderer
    image=QtGui.QImage(430,54,QtGui.QImage.Format_ARGB32);image.fill(QtGui.QColor(247,247,247))
    painter=QtGui.QPainter(image);painter.setRenderHint(QtGui.QPainter.Antialiasing)
    camera=renderer._camera(dict(position=[0,0,10],target=[0,0,0],projection='orthographic',ortho_width=430.),430,54)
    style=dict(line_pattern=shape,brush_preset=brush,pattern_period=period,pattern_amplitude=amplitude,line_width=width,brush_roughness=roughness,brush_density=density,brush_width_scale=width_scale,line_image=line_image or {},brush_image=brush_image or {},brush_stamp_spacing=brush_spacing)
    for points,parameters,thin in presets.expand([[-195,0,0],[195,0,0]],style,camera):
        xy=renderer._project((points-camera['eye'])@camera['basis'].T,camera)
        child=presets.variant_style(style,thin) if thin else style;color=QtGui.QColor(42,42,45);color.setAlphaF(child.get('line_opacity',1.))
        pen=QtGui.QPen(color,child['line_width'] if thin else width,QtCore.Qt.SolidLine,QtCore.Qt.RoundCap)
        painter.setPen(pen)
        for a,b in xy:painter.drawLine(QtCore.QPointF(*a),QtCore.QPointF(*b))
    painter.end();return QtGui.QPixmap.fromImage(image)

class Gallery(QtWidgets.QDialog):
    def __init__(self,node,changed,parent):
        super().__init__(parent);self.node=node;self.changed=changed;self.cards={};self.user_combos={};self._thumb_cache={};self._png_key=None;self._drag_chunk=False;initial=self.values();self.selected={'shape':'builtin_shape_'+str(initial.get('line_pattern',0)),'brush':'builtin_brush_'+str(initial.get('brush_preset',0))};self._display_identity=None
        self.setObjectName('reaPencilStrokePresets');self.setWindowTitle(text('ReaPencil — Line / Brush presets','ReaPencil — 선 형태 / 브러시 프리셋'));self.resize(680,850)
        layout=QtWidgets.QVBoxLayout(self);target=QtWidgets.QLabel(node);target.setWordWrap(True);layout.addWidget(target)
        self.sample=QtWidgets.QLabel();self.sample.setAlignment(QtCore.Qt.AlignCenter);layout.addWidget(self.sample)
        tabs=QtWidgets.QTabWidget();self.tabs=tabs;layout.addWidget(tabs,1)
        for kind,names,heading in (('shape',presets.SHAPES,text('Line shape','선 형태')),('brush',presets.BRUSHES,text('Brush stroke','브러시 스트로크'))):
            scroll=QtWidgets.QScrollArea();scroll.setWidgetResizable(True);page=QtWidgets.QWidget();box=QtWidgets.QVBoxLayout(page)
            for i,name in enumerate(names):
                button=QtWidgets.QPushButton(text(*name));button.setObjectName('preset_'+kind+'_'+str(i));button.setCheckable(True);button.setMinimumHeight(72)
                values=presets.patch(kind,i)
                button.setIcon(QtGui.QIcon(thumbnail(i if kind=='shape' else 0,i if kind=='brush' else 0,1.6 if kind=='shape' else 10.,values.get('pattern_period',20.),values.get('pattern_amplitude',3.))))
                button.setIconSize(QtCore.QSize(330,48));button.clicked.connect(lambda checked=False,k=kind,index=i:self.apply(k,index));box.addWidget(button);self.cards[kind,i]=button
            box.addWidget(QtWidgets.QLabel(text('My presets','사용자 프리셋')))
            combo=QtWidgets.QComboBox();combo.setObjectName('userPreset_'+kind);combo.currentIndexChanged.connect(lambda index,k=kind:self.pick_user(k,index));box.addWidget(combo);self.user_combos[kind]=combo
            box.addStretch();scroll.setWidget(page);tabs.addTab(scroll,heading)
        image_row=QtWidgets.QHBoxLayout();self.png_load=QtWidgets.QPushButton();self.png_load.setObjectName('loadPresetPNG');self.png_load.setToolTip(text('PNG is embedded at up to512 pixels per side. Line Set color is used.','PNG는 한 변 최대512픽셀로 내장되며, 색상은 라인셋 설정을 사용합니다.'));self.png_load.clicked.connect(lambda:self.safe(self.import_png));image_row.addWidget(self.png_load)
        self.png_preview=QtWidgets.QLabel('PNG');self.png_preview.setFixedSize(48,48);self.png_preview.setAlignment(QtCore.Qt.AlignCenter);self.png_preview.setStyleSheet('background:#ddd;color:#333;border:1px solid #777');image_row.addWidget(self.png_preview)
        self.png_info=QtWidgets.QLabel();self.png_info.setTextFormat(QtCore.Qt.PlainText);self.png_info.setWordWrap(True);image_row.addWidget(self.png_info,1)
        self.png_mode=QtWidgets.QComboBox();self.png_mode.addItem(text('Auto mask','자동 인식'),'auto');self.png_mode.addItem(text('Alpha','투명도'),'alpha');self.png_mode.addItem(text('Dark ink','검정 잉크'),'dark');image_row.addWidget(self.png_mode)
        self.png_remove=QtWidgets.QPushButton(text('Clear PNG','PNG 제거'));self.png_remove.clicked.connect(lambda:self.safe(self.clear_png));image_row.addWidget(self.png_remove);layout.addLayout(image_row)
        form=QtWidgets.QFormLayout();self.family=QtWidgets.QComboBox();self.family.setObjectName('userPresetFamily');self.family.currentIndexChanged.connect(self.change_family);form.addRow(text('Edit shape / brush type','형태 / 브러시 종류 편집'),self.family)
        self.period=NumericSlider();self.period.setObjectName("pattern_period");self.period.setRange(2,10000);self.period.setSuffix(' px');form.addRow(text('Pattern spacing','패턴 간격'),self.period)
        self.amplitude=NumericSlider();self.amplitude.setObjectName("pattern_amplitude");self.amplitude.setRange(0,1000);self.amplitude.setSuffix(' px');form.addRow(text('Pattern height','패턴 높이'),self.amplitude);layout.addLayout(form)
        self.stamp=NumericSlider();self.stamp.setObjectName('brush_stamp_spacing');self.stamp.setRange(2,10000);self.stamp.setSuffix(' px');form.addRow(text('PNG brush repeat length','PNG 브러시 반복 길이'),self.stamp);self.stamp.valueChanged.connect(lambda value:self.update_values(dict(brush_stamp_spacing=value)))
        self.period.valueChanged.connect(lambda value:self.update_values(dict(pattern_period=value)))
        self.amplitude.valueChanged.connect(lambda value:self.update_values(dict(pattern_amplitude=value)))
        self.brush_controls={}
        for key,label,low,high in [('brush_roughness',text('Roughness','브러시 거칠기'),0,3),('brush_density',text('Ink density','브러시 잉크 밀도'),0,1),('brush_width_scale',text('Brush width multiplier','브러시 폭 배율'),.1,3)]:
            control=NumericSlider();control.setObjectName(key);control.setRange(low,high);control.setDecimals(2);control.setSingleStep(.05);control.valueChanged.connect(lambda value,k=key:self.update_values({k:value}));form.addRow(label,control);self.brush_controls[key]=control
        for control in (self.period,self.amplitude,self.stamp,*self.brush_controls.values()):
            control.sliderPressed.connect(self._start_numeric_drag);control.sliderReleased.connect(self._end_numeric_drag)
        # Name and library operations are separate from scene Undo. Saving a
        # preset never overwrites another Maya scene or a packaged definition.
        row=QtWidgets.QHBoxLayout();self.preset_name=QtWidgets.QLineEdit();self.preset_name.setObjectName('userPresetName');self.preset_name.setMaxLength(80);row.addWidget(QtWidgets.QLabel(text('Preset name','프리셋 이름')));row.addWidget(self.preset_name);layout.addLayout(row)
        actions=QtWidgets.QHBoxLayout();self.actions={}
        for key,label,callback in [('add',text('Add new','새 프리셋 추가'),self.add_preset),('save',text('Save edits','선택 프리셋 저장'),self.save_selected),('rename',text('Rename','이름 변경'),self.rename_selected),('delete',text('Delete / Reset','삭제 / 기본 복원'),self.delete_selected)]:
            button=QtWidgets.QPushButton(label);button.setObjectName('userPreset_'+key);button.clicked.connect(lambda checked=False,fn=callback:self.safe(fn));actions.addWidget(button);self.actions[key]=button
        layout.addLayout(actions)
        help=QtWidgets.QLabel(text('Controls edit the current Line Set. Save edits updates the selected preset in the current tab. Packaged presets can be customized and reset.','수치 변경은 현재 라인셋에 적용됩니다. 저장을 누르면 현재 탭에서 선택한 프리셋도 수정됩니다.\n기본 프리셋도 사용자 설정으로 편집할 수 있으며, 기본 복원으로 되돌립니다.'));help.setWordWrap(True);layout.addWidget(help)
        tabs.currentChanged.connect(lambda *_:self.refresh())
        hint=QtWidgets.QLabel(text('General Preview and CPU render. Fast Preview shows the basic line. Some advanced preview combinations omit patterns. Shape and brush combine; color, width and alpha stay in the Line Set.','일반 프리뷰 · CPU 렌더에 적용됩니다. 고속 프리뷰 및 일부 고급 설정 조합에서는 기본 선으로 표시됩니다.\n선 형태와 브러시를 조합할 수 있습니다. 색상·선폭·알파 설정은 유지됩니다.'));hint.setWordWrap(True);layout.addWidget(hint);self.refresh()
    def values(self):
        from . import surface_lines,maya_scene
        return dict(maya_scene.DEFAULT_SETTINGS,**surface_lines.source_style(self.node)[1])
    def refresh(self):
        values=self.values()
        self.family.blockSignals(True);self.family.clear()
        for name in (presets.SHAPES if self.kind()=='shape' else presets.BRUSHES):self.family.addItem(text(*name))
        self.family.setCurrentIndex(values['line_pattern' if self.kind()=='shape' else 'brush_preset']);self.family.blockSignals(False)
        items={v['id']:v for v in library.load()['items']}
        for (kind,i),card in self.cards.items():
            identity='builtin_'+kind+'_'+str(i);entry=items.get(identity);data=entry['settings'] if entry else presets.patch(kind,i)
            card.setChecked(identity==self.selected[kind]);card.setText(entry['name'] if entry else text(*(presets.SHAPES if kind=='shape' else presets.BRUSHES)[i]))
            signature=(kind,i,json.dumps(data,sort_keys=True))
            if signature not in self._thumb_cache:self._thumb_cache[signature]=QtGui.QIcon(thumbnail(data.get('line_pattern',0),data.get('brush_preset',0),1.6 if kind=='shape' else 10.,data.get('pattern_period',20.),data.get('pattern_amplitude',3.),data.get('brush_roughness',1.),data.get('brush_density',1.),data.get('brush_width_scale',1.),data.get('line_image',{}),data.get('brush_image',{}),data.get('brush_stamp_spacing',24.)))
            card.setIcon(self._thumb_cache[signature])
        for kind,combo in self.user_combos.items():
            combo.blockSignals(True);combo.clear();combo.addItem(text('Choose my preset','사용자 프리셋 선택'),None)
            for entry in items.values():
                if entry['kind']==kind and not entry['id'].startswith('builtin_'):combo.addItem(entry['name'],entry['id'])
            combo.setCurrentIndex(max(0,combo.findData(self.selected[kind])));combo.blockSignals(False)
        for key,control in (('pattern_period',self.period),('pattern_amplitude',self.amplitude),('brush_stamp_spacing',self.stamp)):
            control.blockSignals(True);control.setValue(values[key]);control.blockSignals(False)
        self.period.setEnabled(bool(values['line_pattern']));self.amplitude.setEnabled(values['line_pattern']>=2)
        for key,control in self.brush_controls.items():
            control.blockSignals(True);control.setValue(values[key]);control.setEnabled(bool(values['brush_preset']) and (key!='brush_roughness' or values['brush_preset']!=4));control.blockSignals(False)
        self.sample.setPixmap(thumbnail(values['line_pattern'],values['brush_preset'],max(1.,min(18.,values['line_width'])),values['pattern_period'],values['pattern_amplitude'],values['brush_roughness'],values['brush_density'],values['brush_width_scale'],values['line_image'],values['brush_image'],values['brush_stamp_spacing']))
        self.stamp.setEnabled(values['brush_preset']==4)
        self.update_png_slot(values)
        identity=self.selected[self.kind()];entry=items.get(identity)
        if identity!=self._display_identity:
            if entry:self.preset_name.setText(entry['name'])
            elif identity.startswith('builtin_'):
                kind=self.kind();i=int(identity.rsplit('_',1)[1]);self.preset_name.setText(text(*(presets.SHAPES if kind=='shape' else presets.BRUSHES)[i]))
            self._display_identity=identity
        self.actions['delete'].setEnabled(entry is not None)
    def update_values(self,patch):
        from . import line_graph,maya_scene,viewport
        if not cmds.objExists(self.node):self.close();return
        with maya_scene.undo_chunk('ReaPencil stroke preset'):
            value=line_graph.get_settings(self.node);value.update(patch);line_graph.set_settings(self.node,value)
        viewport.request_refresh();self.refresh()
    def _start_numeric_drag(self):
        if not self._drag_chunk:cmds.undoInfo(openChunk=True,chunkName='ReaPencil slider');self._drag_chunk=True
    def _end_numeric_drag(self):
        if self._drag_chunk:
            cmds.undoInfo(closeChunk=True);self._drag_chunk=False
    def closeEvent(self,event):
        self._end_numeric_drag();super().closeEvent(event)
    def kind(self):return 'shape' if self.tabs.currentIndex()==0 else 'brush'
    def safe(self,callback):
        try:return callback()
        except (ValueError,OSError) as error:QtWidgets.QMessageBox.warning(self,self.windowTitle(),str(error))
    def payload(self,kind):
        keys=library.SHAPE if kind=='shape' else library.BRUSH
        return {k:v for k,v in self.values().items() if k in keys}
    def apply(self,kind,index):
        identity='builtin_'+kind+'_'+str(index);previous=self.selected[kind];self.selected[kind]=identity
        entry=next((v for v in library.load()['items'] if v['id']==identity),None)
        image_key='line_image' if kind=='shape' else 'brush_image'
        if (kind=='shape' and index==7 or kind=='brush' and index==4) and not self.values().get(image_key) and entry is None:
            imported=self.safe(lambda:self.import_png(kind=kind))
            if imported is None:self.selected[kind]=previous;self.refresh()
            return imported
        self.update_values(entry['settings'] if entry else presets.patch(kind,index))
    def change_family(self,index):
        if index<0:return
        kind=self.kind();key='line_pattern' if kind=='shape' else 'brush_preset';image='line_image' if kind=='shape' else 'brush_image'
        if (kind=='shape' and index==7 or kind=='brush' and index==4) and not self.values().get(image):
            self.safe(self.import_png);self.refresh();return
        self.update_values({key:index})
    def update_png_slot(self,values):
        from . import png_pattern
        kind=self.kind();value=values['line_image' if kind=='shape' else 'brush_image']
        self.png_load.setText(text('Import line PNG','라인 PNG 불러오기') if kind=='shape' else text('Import brush PNG','브러시 PNG 불러오기'))
        self.png_remove.setEnabled(bool(value))
        if value:
            self.png_info.setText(value['name']+' · '+str(value['width'])+'×'+str(value['height'])+' · '+text(value['mode'],'투명도' if value['mode']=='alpha' else '검정 잉크'))
            identity=(kind,value['sha256'])
            if identity!=self._png_key:
                import numpy as np
                mask=png_pattern.mask(value);h,w=mask.shape;rgba=np.full((h,w,4),40,np.uint8);rgba[:,:,3]=mask
                image=QtGui.QImage(rgba.data,w,h,w*4,QtGui.QImage.Format_RGBA8888).copy();self.png_preview.setPixmap(QtGui.QPixmap.fromImage(image).scaled(46,46,QtCore.Qt.KeepAspectRatio,QtCore.Qt.SmoothTransformation));self._png_key=identity
        else:
            self.png_info.setText(text('Import a PNG motif or brush tip. Alpha or dark ink becomes coverage.','PNG 모양 또는 붓 이미지를 넣으세요. 투명도나 검정 부분을 사용합니다.'));self.png_preview.clear();self.png_preview.setText('PNG');self._png_key=None
    def import_png(self,filename=None,kind=None):
        from . import png_pattern
        kind=kind or self.kind()
        if not filename:filename=QtWidgets.QFileDialog.getOpenFileName(self,text('Import pattern PNG','패턴 PNG 불러오기'),'','PNG (*.png)')[0]
        if not filename:return
        image=png_pattern.load_png(filename,self.png_mode.currentData());aspect=image['width']/image['height'];values=self.values()
        if kind=='shape':patch=dict(line_pattern=7,line_image=image,pattern_period=40.,pattern_amplitude=max(.5,min(1000.,20./aspect)))
        else:patch=dict(brush_preset=4,brush_image=image,brush_stamp_spacing=max(2.,min(10000.,values['line_width']*aspect)),brush_width_scale=1.,brush_density=1.)
        if self.selected[kind].startswith('builtin_'):self.selected[kind]='builtin_'+kind+('_7' if kind=='shape' else '_4')
        self.update_values(patch);return image
    def clear_png(self):
        kind=self.kind();values=self.values();key='line_image' if kind=='shape' else 'brush_image';mode='line_pattern' if kind=='shape' else 'brush_preset';png_mode=7 if kind=='shape' else 4
        patch={key:{}}
        if values[mode]==png_mode:patch[mode]=0
        if self.selected[kind]=='builtin_'+kind+'_'+str(png_mode):self.selected[kind]='builtin_'+kind+'_0'
        self.update_values(patch)
    def pick_user(self,kind,index):
        identity=self.user_combos[kind].itemData(index)
        if not identity:return
        entry=next(v for v in library.load()['items'] if v['id']==identity);self.selected[kind]=identity;self.update_values(entry['settings'])
    def add_preset(self):
        kind=self.kind();entry=library.save(kind,self.preset_name.text(),self.payload(kind));self.selected[kind]=entry['id'];self.refresh();return entry
    def save_selected(self):
        kind=self.kind();entry=library.save(kind,self.preset_name.text(),self.payload(kind),self.selected[kind]);self.refresh();return entry
    def rename_selected(self):
        kind=self.kind();identity=self.selected[kind];entry=next((v for v in library.load()['items'] if v['id']==identity),None)
        if entry is None:
            index=int(identity.rsplit('_',1)[1]);values=presets.patch(kind,index)
        else:values=entry['settings']
        library.save(kind,self.preset_name.text(),values,identity);self.refresh()
    def delete_selected(self):
        kind=self.kind();identity=self.selected[kind]
        if QtWidgets.QMessageBox.question(self,self.windowTitle(),text('Delete this user preset or reset its packaged default? The current Line Set is kept.','사용자 프리셋을 삭제하거나 기본 프리셋을 복원할까요? 현재 라인셋은 유지됩니다.'),QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No,QtWidgets.QMessageBox.No)!=QtWidgets.QMessageBox.Yes:return
        library.remove(identity);self._display_identity=None
        if not identity.startswith('builtin_'):self.selected[kind]='builtin_'+kind+'_0'
        self.refresh()

def show(node,changed=None):
    if node in _windows:
        _windows[node].close();_windows[node].deleteLater()
    parent=wrapInstance(int(OpenMayaUI.MQtUtil.mainWindow()),QtWidgets.QWidget)
    window=Gallery(node,changed,parent);_windows[node]=window;window.show();return window
