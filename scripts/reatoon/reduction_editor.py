"""Editor for CPU Linear distance reduction and reference-origin snapshots."""
from . import i18n
# A dialog module may be reloaded while Maya still holds an older UI catalog.
# Register its new button labels in that live catalog, including reverse lookup
# so switching languages preserves the existing dialog and its edited fields.
_measure_labels={
    'Depth reduction':'거리 감소',
    'Hidden depth reduction applies to CPU render.':'숨은 선의 거리 감소는 CPU 렌더에 적용됩니다.',
    'Camera depth: width and alpha reduction in normal preview and CPU render.':'카메라 깊이 기준입니다. 선폭·알파 감소는 일반 프리뷰와 CPU 렌더에 적용됩니다.',
    'Fill width range from selection':'선택 오브젝트로 선폭 거리 채우기',
    'Measure selected objects':'선택 오브젝트 깊이 측정',
    'Fill this range from the selected mesh vertices using the active viewport camera. Distances are in cm. Click Apply to save.':'현재 뷰포트 카메라 기준으로 선택한 메시의 시작·종료 거리를 채웁니다. 단위는 cm이며 적용을 눌러 저장합니다.',
}
i18n.STRINGS.update(_measure_labels)
i18n.ALIASES.update({ko:en for en,ko in _measure_labels.items()})
tr=i18n.tr
_dialogs=[]


def open_editor(node,hidden=False):
    from PySide6 import QtWidgets
    from maya import cmds,OpenMayaUI
    from maya.api import OpenMaya as om
    import shiboken6
    from . import line_graph as graph,maya_scene,viewport
    from .depth_reduction import validate
    pointer=None if cmds.about(batch=True) else OpenMayaUI.MQtUtil.mainWindow()
    parent=shiboken6.wrapInstance(int(pointer),QtWidgets.QWidget) if pointer else None
    dialog=QtWidgets.QDialog(parent);dialog.setObjectName('reaPencilDepthReduction')
    dialog.setWindowTitle(tr('Hidden depth reduction (CPU)' if hidden else 'Depth reduction'))
    layout=QtWidgets.QVBoxLayout(dialog)
    note=QtWidgets.QLabel(tr('Hidden depth reduction applies to CPU render.' if hidden else 'Camera depth: width and alpha reduction in normal preview and CPU render.'))
    note.setWordWrap(True);layout.addWidget(note)
    measure_width_button=QtWidgets.QPushButton(tr('Fill width range from selection'));measure_width_button.setObjectName('measure_width_from_selection')
    measure_width_button.setToolTip(tr('Fill this range from the selected mesh vertices using the active viewport camera. Distances are in cm. Click Apply to save.'))
    layout.addWidget(measure_width_button)
    settings=graph.resolved_settings(node)
    if hidden:values=settings.get('hidden_style',{})
    else:
        lines=[n for n in (cmds.listConnections(node+'.message',source=False,destination=True) or []) if cmds.nodeType(n)==graph.LineNode.TYPE]
        values=graph.get_settings(lines[0]) if lines else {}
        values=dict(values,**settings)
    frozen={};pending={};camera_mode=set()
    def pending_name(handle):
        if not handle.isValid() or not handle.isAlive():raise ValueError(tr('Selected reference no longer exists.'))
        paths=om.MDagPath.getAllPathsTo(handle.object())
        if len(paths)!=1:raise ValueError(tr('Instanced reference transforms are ambiguous'))
        return paths[0].fullPathName()
    live={channel:graph.reduction_reference(node,channel,hidden) for channel in ('alpha','width')}
    if any(live.values()):note.setText(tr('Connected reference origins update for every CPU render.'))
    elif values.get('alpha_reduction_origin') or values.get('width_reduction_origin'):
        note.setText(tr('Reference origins are current-frame snapshots; reimport after changes.'))
    for key,title in [('width_depth_reduction','Width reduction'),('alpha_depth_reduction','Alpha reduction')]:
        group=QtWidgets.QGroupBox(tr(title));group.setObjectName(key);group.setCheckable(True)
        stored=validate(values.get(key,[]));group.setChecked(bool(stored));form=QtWidgets.QFormLayout(group)
        for name,label,value,minimum,maximum in zip(('start','end','first','last'),('Start distance','End distance','Start factor','End factor'),stored or [1.,100.,1.,0.],(1.,1.,0.,0.),(1000000.,1000000.,1.,1.)):
            field=QtWidgets.QDoubleSpinBox();field.setObjectName(name);field.setDecimals(6);field.setRange(minimum,maximum);field.setValue(value);form.addRow(tr(label),field)
        channel=key.split('_',1)[0];origin=values.get(channel+'_reduction_origin',[])
        label=QtWidgets.QLabel();label.setWordWrap(True)
        label.setText(tr('Reference snapshot (world): ')+', '.join(format(v,'.6g') for v in origin) if origin else tr('Camera depth'))
        if live[channel]:label.setText(tr('Live reference: ')+live[channel]+' | '+', '.join(format(v,'.6g') for v in origin))
        form.addRow(label)
        bind=QtWidgets.QPushButton(tr('Bind selected transform'));bind.setObjectName('bind_reference')
        use_camera=QtWidgets.QPushButton(tr('Use camera depth'));use_camera.setObjectName('camera_depth')
        freeze_button=QtWidgets.QPushButton(tr('Freeze current reference'));freeze_button.setObjectName('freeze_reference');freeze_button.setEnabled(bool(origin))
        def select_reference(*_,c=channel,display=label,freeze_control=freeze_button):
            try:
                if not cmds.objExists(node):raise ValueError(tr('Line Set no longer exists.'))
                selected=cmds.ls(selection=True,long=True) or []
                if len(selected)!=1 or '.' in selected[0]:raise ValueError(tr('Select one reference transform.'))
                point=graph._reference_world_origin(selected[0]);selection=om.MSelectionList();selection.add(selected[0])
                pending[c]=om.MObjectHandle(selection.getDependNode(0));frozen.pop(c,None);camera_mode.discard(c)
                display.setText(tr('Pending live reference: ')+selected[0]+' | '+', '.join(format(v,'.6g') for v in point));freeze_control.setEnabled(True);status.clear()
            except (RuntimeError,ValueError,TypeError) as error:status.setText(tr(str(error)))
        def camera(*_,c=channel,display=label,freeze_control=freeze_button):
            pending.pop(c,None);frozen.pop(c,None);camera_mode.add(c)
            display.setText(tr('Camera depth'));freeze_control.setEnabled(False);status.clear()
        def freeze(*_,c=channel,display=label,control=freeze_button):
            try:
                if not cmds.objExists(node):raise ValueError(tr('Line Set no longer exists.'))
                if c in pending:point=graph._reference_world_origin(pending_name(pending[c]))
                else:
                    latest=graph.resolved_settings(node);leaf=latest.get('hidden_style',{}) if hidden else latest;point=leaf.get(c+'_reduction_origin')
                if not point:raise ValueError(tr('No reference origin to freeze'))
                frozen[c]=list(point);pending.pop(c,None);camera_mode.discard(c)
                display.setText(tr('Reference snapshot (world): ')+', '.join(format(v,'.6g') for v in frozen[c]));control.setEnabled(False);status.clear()
            except (RuntimeError,ValueError,TypeError) as error:status.setText(tr(str(error)))
        measure=None
        if channel=='alpha':
            measure=QtWidgets.QPushButton(tr('Measure selected objects'));measure.setObjectName('measure_selection_depth')
            measure.setToolTip(tr('Fill this range from the selected mesh vertices using the active viewport camera. Distances are in cm. Click Apply to save.'))
        def measure_selection(*_,g=group,c=channel,display=label,freeze_control=freeze_button):
            try:
                from .selection_depth import measure_selected
                measured=measure_selected()
                # Update fields only after a successful, complete read-only measurement.
                g.findChild(QtWidgets.QDoubleSpinBox,'start').setValue(measured['start'])
                g.findChild(QtWidgets.QDoubleSpinBox,'end').setValue(measured['end'])
                g.setChecked(True);pending.pop(c,None);frozen.pop(c,None);camera_mode.add(c)
                freeze_control.setEnabled(False)
                display.setText(tr('Camera depth')+' | '+measured['camera'])
                status.setText(tr('Measured camera: ')+measured['camera']+' | '+format(measured['start'],'.6f')+' ~ '+format(measured['end'],'.6f')+' cm')
                if measured['padded']:status.setText(status.text()+' | '+tr('A small range was added because the selection has no depth span.'))
            except (RuntimeError,ValueError,TypeError) as error:status.setText(tr(str(error)))
        if measure is not None:measure.clicked.connect(measure_selection);form.addRow(measure)
        if channel=='width':measure_width_button.clicked.connect(measure_selection)
        bind.clicked.connect(select_reference);use_camera.clicked.connect(camera);freeze_button.clicked.connect(freeze)
        form.addRow(bind,use_camera);form.addRow(freeze_button)
        layout.addWidget(group)
    status=QtWidgets.QLabel();status.setObjectName('status');status.setWordWrap(True);layout.addWidget(status)
    buttons=QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Apply|QtWidgets.QDialogButtonBox.Cancel)
    buttons.button(QtWidgets.QDialogButtonBox.Apply).setText(tr('Apply'))
    buttons.button(QtWidgets.QDialogButtonBox.Cancel).setText(tr('Cancel'));layout.addWidget(buttons)
    def apply():
        try:
            if not cmds.objExists(node):raise ValueError(tr('Line Set no longer exists.'))
            current=graph.get_settings(node)
            if hidden and not current.get('hidden_style'):raise ValueError(tr('Enable independent hidden settings first.'))
            # Validate both before any mutation. Read latest graph to preserve unrelated edits.
            updated={}
            for key in ('width_depth_reduction','alpha_depth_reduction'):
                group=dialog.findChild(QtWidgets.QGroupBox,key)
                updated[key]=validate([group.findChild(QtWidgets.QDoubleSpinBox,n).value() for n in ('start','end','first','last')]) if group.isChecked() else []
            references={c:pending_name(handle) for c,handle in pending.items() if updated[c+'_depth_reduction']}
            for reference in references.values():graph._reference_world_origin(reference)
            target=current.setdefault('hidden_style',{}) if hidden else current
            target.update(updated)
            for channel,origin in frozen.items():target[channel+'_reduction_origin']=origin
            for channel in camera_mode:target[channel+'_reduction_origin']=[]
            for channel in ('alpha','width'):
                origin_key=channel+'_reduction_origin'
                if not updated[channel+'_depth_reduction'] and target.get(origin_key):target[origin_key]=[]
            with maya_scene.undo_chunk('ReaPencil Depth Reduction'):
                graph.set_settings(node,current)
                for channel in ('alpha','width'):
                    if channel in frozen or channel in camera_mode or not updated[channel+'_depth_reduction']:graph.clear_reduction_reference(node,channel,hidden)
                    elif channel in references:graph.bind_reduction_reference(node,channel,references[channel],hidden)
            viewport.request_refresh(style_changed=True)
            dialog.accept()
        except (ValueError,RuntimeError,TypeError) as error:status.setText(tr(str(error)))
    buttons.button(QtWidgets.QDialogButtonBox.Apply).clicked.connect(apply);buttons.rejected.connect(dialog.reject)
    _dialogs.append(dialog);dialog.finished.connect(lambda *_:_dialogs.remove(dialog) if dialog in _dialogs else None)
    dialog.resize(540,460);dialog.show();return dialog
