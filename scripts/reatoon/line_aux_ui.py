"""Global Merge Groups / Render Elements tabs and their native AE editors."""
from .i18n import tr
from maya import cmds
from . import line_graph as graph, maya_scene

_ae = {}
_dialogs = []


def _safe(fn,*args):
    from .line_editor import _safe as invoke
    return invoke(fn,*args)


def _open(node):
    from .line_editor import _open as invoke
    return invoke(node)


def _choose_groups(parent,accept,refresh):
    from PySide6 import QtCore,QtWidgets
    dialog=QtWidgets.QDialog(parent)
    dialog.setWindowTitle(tr('Add Merge Groups'))
    dialog.setObjectName('revToonMergeGroupChooser')
    dialog.setWindowModality(QtCore.Qt.ApplicationModal)
    dialog.resize(500,420)
    layout=QtWidgets.QVBoxLayout(dialog)
    search=QtWidgets.QLineEdit()
    search.setPlaceholderText(tr('Filter object names'))
    selection_only=QtWidgets.QCheckBox(tr('Current Maya selection only'))
    listing=QtWidgets.QListWidget()
    listing.setObjectName('revToonExistingGroupChoices')
    listing.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
    def populate(*_):
        objects=[n for n in cmds.ls(type='objectSet',long=True) or [] if cmds.nodeType(n)=='objectSet']
        groups=[n for n in cmds.ls(type='transform',long=True) or []
                if cmds.listRelatives(n,allDescendents=True,type='mesh')]
        names=sorted(set(objects+groups)-set(graph.list_merge_groups()))
        if selection_only.isChecked():
            selected=set(cmds.ls(selection=True,long=True) or [])
            names=[n for n in names if n in selected]
        listing.clear()
        listing.addItems([n for n in names if search.text().lower() in n.lower()])
    search.textChanged.connect(populate)
    selection_only.toggled.connect(populate)
    layout.addWidget(search)
    layout.addWidget(selection_only)
    layout.addWidget(listing,1)
    buttons=QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok|QtWidgets.QDialogButtonBox.Cancel)
    def finish():
        result=_safe(accept,[item.text() for item in listing.selectedItems()])
        if result is not None:
            refresh(result[0] if result else None)
            dialog.accept()
    buttons.accepted.connect(finish)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    populate()
    _dialogs.append(dialog)
    dialog.finished.connect(lambda *_:_dialogs.remove(dialog) if dialog in _dialogs else None)
    dialog.show()


def add_tabs(tabs):
    from PySide6 import QtCore,QtWidgets
    from . import render_elements as elements
    merge=QtWidgets.QWidget()
    merge.setObjectName('revToonMergeGroupsTab')
    layout=QtWidgets.QVBoxLayout(merge)
    layout.setContentsMargins(5,5,5,5)
    layout.addWidget(QtWidgets.QLabel(tr('Global merge groups')))
    groups=QtWidgets.QListWidget()
    groups.setObjectName('revToonMergeGroupList')
    layout.addWidget(groups,1)
    row=QtWidgets.QHBoxLayout()
    add_group=QtWidgets.QPushButton(tr('Add Group'))
    add_group.setObjectName('revToonAddMergeGroup')
    delete_group=QtWidgets.QPushButton(tr('Delete Group'))
    refresh_group_button=QtWidgets.QPushButton(tr('Refresh'))
    row.addWidget(add_group);row.addWidget(delete_group);row.addWidget(refresh_group_button)
    layout.addLayout(row)
    layout.addWidget(QtWidgets.QLabel(tr('Objects in selected group')))
    members=QtWidgets.QListWidget()
    members.setObjectName('revToonMergeMemberList')
    members.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
    layout.addWidget(members,1)
    note=QtWidgets.QLabel(tr('Remove unregisters the group and preserves its objects.'))
    note.setWordWrap(True)
    layout.addWidget(note)
    def selected_group():
        if not groups.currentItem():raise ValueError('Select a Merge Group first.')
        return groups.currentItem().text()
    def refresh_members(*_):
        members.clear()
        if groups.currentItem():members.addItems(graph.get_merge_targets(selected_group()))
    def refresh_groups(selected=None):
        previous=selected or (groups.currentItem().text() if groups.currentItem() else None)
        groups.blockSignals(True)
        groups.clear();groups.addItems(graph.list_merge_groups())
        for i in range(groups.count()):
            if groups.item(i).text()==previous:groups.setCurrentRow(i)
        groups.blockSignals(False)
        refresh_members()
    def delete_current_group():
        graph.unregister_merge_group(selected_group())
        refresh_groups()
    groups.itemSelectionChanged.connect(refresh_members)
    def register_existing():
        _choose_groups(merge,lambda nodes:[graph.register_merge_group(node) for node in nodes],refresh_groups)
    add_group.setText(tr('Add…'))
    delete_group.setText(tr('Remove'))
    add_group.clicked.connect(lambda *_:_safe(register_existing))
    delete_group.clicked.connect(lambda *_:_safe(delete_current_group))
    refresh_group_button.clicked.connect(lambda *_:refresh_groups())
    tabs.addTab(merge,tr('Merge Groups'))

    element_page=QtWidgets.QWidget()
    element_page.setObjectName('revToonRenderElementsTab')
    layout=QtWidgets.QVBoxLayout(element_page)
    layout.setContentsMargins(5,5,5,5)
    heading=QtWidgets.QLabel(tr('Global render outputs — select to edit in Attribute Editor'))
    heading.setWordWrap(True)
    layout.addWidget(heading)
    listing=QtWidgets.QListWidget()
    listing.setObjectName('revToonRenderElementList')
    layout.addWidget(listing,1)
    row=QtWidgets.QHBoxLayout()
    add_line=QtWidgets.QPushButton(tr('Add Line'))
    add_line.setObjectName('revToonAddLineElement')
    add_eps=QtWidgets.QPushButton(tr('Add EPS'))
    add_eps.setObjectName('revToonAddEpsElement')
    add_pld=QtWidgets.QPushButton(tr('Add PLD'))
    add_pld.setEnabled(False)
    add_pld.setToolTip(tr('Proprietary PLD output is not supported.'))
    for button in (add_line,add_eps,add_pld):row.addWidget(button)
    layout.addLayout(row)
    delete=QtWidgets.QPushButton(tr('Delete selected element'))
    refresh_element_button=QtWidgets.QPushButton(tr('Refresh'))
    delete_row=QtWidgets.QHBoxLayout()
    delete_row.addWidget(delete,1);delete_row.addWidget(refresh_element_button)
    layout.addLayout(delete_row)
    utility=QtWidgets.QHBoxLayout()
    separate=QtWidgets.QCheckBox(tr('Separate Folders'))
    separate.setObjectName('revToonElementsSeparateFolders')
    separate.setChecked(True)
    separator=QtWidgets.QComboBox()
    separator.setObjectName('revToonElementsSeparator')
    separator.addItems(['_','-','.'])
    apply_all=QtWidgets.QPushButton(tr('Set to all nodes'))
    apply_all.setObjectName('revToonElementsSetAll')
    utility.addWidget(separate);utility.addWidget(separator);utility.addWidget(apply_all)
    layout.addLayout(utility)
    note=QtWidgets.QLabel(tr('PLD and motion-vector output are not supported.\nLine color/depth and EPS outputs use the saved element filters.'))
    note.setWordWrap(True)
    layout.addWidget(note)
    def refresh_elements(selected=None):
        previous=selected or (listing.currentItem().data(QtCore.Qt.UserRole) if listing.currentItem() else None)
        listing.blockSignals(True)
        listing.clear()
        for node in elements.list_elements():
            data=elements.get(node)
            item=QtWidgets.QListWidgetItem(node+' ['+data.get('kind','line').upper()+']',listing)
            item.setData(QtCore.Qt.UserRole,node)
            item.setFlags(item.flags()|QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if data.get('active',True) else QtCore.Qt.Unchecked)
            if node==previous:listing.setCurrentItem(item)
        listing.blockSignals(False)
    def set_active(item):
        _element_setting(item.data(QtCore.Qt.UserRole),'active',item.checkState()==QtCore.Qt.Checked)
    def create_element(kind):
        node=elements.create(kind=kind)
        refresh_elements(node)
        _open(node)
    def delete_element():
        if listing.currentItem():elements.delete(listing.currentItem().data(QtCore.Qt.UserRole))
        refresh_elements()
    listing.itemChanged.connect(lambda item:_safe(set_active,item))
    listing.itemClicked.connect(lambda item:_safe(_open,item.data(QtCore.Qt.UserRole)))
    add_line.clicked.connect(lambda *_:_safe(create_element,'line'))
    add_eps.clicked.connect(lambda *_:_safe(create_element,'eps'))
    delete.clicked.connect(lambda *_:_safe(delete_element))
    refresh_element_button.clicked.connect(lambda *_:refresh_elements())
    def set_all_nodes():
        for node in elements.list_elements():
            elements.set(node,dict(separate_folders=separate.isChecked(),separator=separator.currentText()))
        refresh_elements()
    apply_all.clicked.connect(lambda *_:_safe(set_all_nodes))
    tabs.addTab(element_page,tr('Render Elements'))
    def refresh_all():
        refresh_groups();refresh_elements()
    refresh_all()
    return refresh_all


def _element_setting(node,key,value):
    from . import render_elements as elements
    data=elements.get(node)
    data[key]=value
    elements.set(node,data)


def _scene_setting(key,value):
    data=maya_scene.load_settings()
    data[key]=value
    maya_scene.save_settings(data)


def _field(key,label,value,save,enabled=True):
    if isinstance(value,bool):
        return cmds.checkBox(label=tr(label),value=value,enable=enabled,changeCommand=lambda v:_safe(save,key,v))
    if isinstance(value,(list,tuple)):
        control=cmds.colorSliderGrp(label=tr(label),rgbValue=value,enable=enabled)
        cmds.colorSliderGrp(control,edit=True,changeCommand=lambda *_:_safe(save,key,cmds.colorSliderGrp(control,query=True,rgbValue=True)))
    elif isinstance(value,int):
        control=cmds.intFieldGrp(label=tr(label),numberOfFields=1,value1=value,enable=enabled)
        cmds.intFieldGrp(control,edit=True,changeCommand=lambda *_:_safe(save,key,cmds.intFieldGrp(control,query=True,value1=True)))
    elif isinstance(value,float):
        control=cmds.floatFieldGrp(label=tr(label),numberOfFields=1,value1=value,precision=8 if key=='intersection_tolerance' else 5,enable=enabled)
        cmds.floatFieldGrp(control,edit=True,changeCommand=lambda *_:_safe(save,key,cmds.floatFieldGrp(control,query=True,value1=True)))
    else:
        control=cmds.textFieldGrp(label=tr(label),text=str(value),enable=enabled)
        cmds.textFieldGrp(control,edit=True,changeCommand=lambda *_:_safe(save,key,cmds.textFieldGrp(control,query=True,text=True)))
    return control


def _choice(key,label,value,choices,save,disabled=()):
    control=cmds.optionMenuGrp(label=tr(label))
    values=[]
    for title,token in choices:
        cmds.menuItem(label=tr(title),enable=token not in disabled)
        values.append(token)
    cmds.optionMenuGrp(control,edit=True,select=values.index(value)+1 if value in values else 1,
        changeCommand=lambda *_:_safe(save,key,values[cmds.optionMenuGrp(control,query=True,select=True)-1]))
    return control


def _ae_editor(plug,kind,replace=False):
    parent=cmds.setParent(query=True)
    ctx=_ae.get((parent,kind))
    if replace and ctx and cmds.columnLayout(ctx,exists=True):
        for child in cmds.columnLayout(ctx,query=True,childArray=True) or []:cmds.deleteUI(child)
        cmds.setParent(ctx)
    else:
        ctx=cmds.columnLayout(adjustableColumn=True)
        _ae[(parent,kind)]=ctx
    node=plug.rsplit('.',1)[0]
    try:
        if kind=='settings':_build_settings(node)
        else:_build_element(node)
    finally:cmds.setParent(parent)


def settings_create(plug):_ae_editor(plug,'settings')
def settings_replace(plug):_ae_editor(plug,'settings',True)
def element_create(plug):_ae_editor(plug,'element')
def element_replace(plug):_ae_editor(plug,'element',True)


def _build_settings(node):
    values=maya_scene.load_settings()
    control=cmds.checkBox(label=tr('Smooth Mesh'),value=cmds.getAttr(node+'.enabledSmoothMesh'))
    cmds.connectControl(control,node+'.enabledSmoothMesh')
    cmds.text(label=tr('메시의 Smooth Mesh Preview / 렌더 분할 설정을 사용합니다.'),align='left',wordWrap=True,height=30)
    frame=cmds.frameLayout(label=tr('Additional scene render settings'),collapsable=True,collapse=True)
    cmds.columnLayout(adjustableColumn=True)
    for key,label in [('width','Width'),('height','Height'),('supersample','Over Sampling'),
                      ('background','Background'),('seed','Random Seed'),
                      ('depth_bias','Depth Bias'),('intersection_tolerance','Intersection Tolerance')]:
        _field(key,label,values[key],_scene_setting)
    cmds.separator(height=10)
    cmds.text(label=tr('These values are saved in the scene and used by ReaPencil rendering.'),align='left',wordWrap=True)
    from . import viewport
    cmds.button(label=tr('Enable live viewport lines'),command=lambda *_:_safe(viewport.enable))
    cmds.button(label=tr('Disable live viewport lines'),command=lambda *_:_safe(viewport.disable))
    cmds.setParent(frame);cmds.setParent('..')


def _build_element(node):
    from . import render_elements as elements
    data=elements.get(node)
    save=lambda key,value:_element_setting(node,key,value)
    _field('active','Active',data.get('active',True),save)
    cmds.text(label=tr('Output kind: '+data.get('kind','line').upper()),align='left')
    if data.get('kind')=='pld':
        cmds.text(label=tr('PLD is preserved for inspection; proprietary PLD output is unsupported.'),align='left',wordWrap=True)
    _choice('output_path_type','Output folder',data.get('output_path_type','scene'),[('Scene','scene'),('Custom','custom')],save)
    _field('output_path','Custom folder',data.get('output_path',''),save)
    _field('output_file_name','File name',data.get('output_file_name',''),save)
    _field('separate_folders','Separate folders',data.get('separate_folders',True),save)
    _choice('separator','Separator',data.get('separator','_'),[('_','_'),('-','-'),('.','.')],save)
    if data.get('kind')=='eps':
        _choice('file_type','File type',data.get('file_type','eps'),[('EPS','eps'),('Adobe Illustrator EPS','ai_eps')],save)
    else:
        _choice('output_element','Output element',data.get('output_element','color'),
                [('Line Color','color'),('Z Depth','depth'),('Velocity (unsupported)','velocity')],save,disabled=('velocity',))
        _field('z_min','Z Min',float(data.get('z_min',100)),save)
        _field('z_max','Z Max',float(data.get('z_max',300)),save)
        _field('max_velocity','Max Velocity (unsupported)',float(data.get('max_velocity',50)),save,False)
    _field('bg_color_enable','Background enabled',data.get('bg_color_enable',False),save)
    _field('bg_color','Background color',data.get('bg_color',[1,1,1]),save)
    _field('visible_lines','Visible lines',data.get('visible_lines',True),save)
    _field('hidden_lines','Hidden lines',data.get('hidden_lines',True),save)
    frame=cmds.frameLayout(label=tr('Line Types'),collapsable=True,collapse=False)
    cmds.columnLayout(adjustableColumn=True)
    edge_types=[('outline','Outline'),('open','Open edges'),('intersection','Intersections'),
                ('hard','Hard edges'),('material','Material boundaries'),
                ('selected','Selected edges'),('crease','Crease'),('wireframe','Wireframe')]
    selected=set(data.get('edge_types',[k for k,_ in edge_types]))
    def toggle_edge(key,value):
        current=elements.get(node)
        enabled=set(current.get('edge_types',[]))
        enabled.add(key) if value else enabled.discard(key)
        _element_setting(node,'edge_types',[k for k,_ in edge_types if k in enabled])
    for key,label in edge_types:_field(key,label,key in selected,toggle_edge)
    cmds.setParent(frame);cmds.setParent('..')
    frame=cmds.frameLayout(label=tr('Line Set IDs'),collapsable=True,collapse=False)
    cmds.rowLayout(numberOfColumns=8)
    def toggle_id(index,value):
        selected=set(elements.get(node).get('lineset_ids',list(range(1,9))))
        selected.add(index) if value else selected.discard(index)
        _element_setting(node,'lineset_ids',sorted(selected))
    for index in range(1,9):
        cmds.checkBox(label=tr(str(index)),value=index in data.get('lineset_ids',list(range(1,9))),
                      changeCommand=lambda v,i=index:_safe(toggle_id,i,v))
    cmds.setParent(frame);cmds.setParent('..')
