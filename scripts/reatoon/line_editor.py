"""Independent native Maya Line-list and Attribute Editor workflow."""
from .i18n import tr
from maya import cmds, mel
from . import line_graph as graph, maya_scene

WINDOW = 'revToonLineListWindow'
_rows = None
_contexts = {}
_window = None
_list = None
_priority_slider = None
_priority_spin = None
_selected_line = None
_aux_refresh = None
_name_job = None
_owns_ae_pin = False


def _safe(fn, *args):
    try:
        with maya_scene.undo_chunk('ReaPencil Line Editor'):
            return fn(*args)
    except Exception as error:
        cmds.warning('ReaPencil: ' + str(error))


def _active(node):
    return bool(cmds.getAttr(node + '.active'))


def _open(node):
    global _owns_ae_pin
    if not cmds.objExists(node):return
    # Focus the Attribute Editor independently of Maya's active selection.
    mel.eval('showEditorExact "' + node.replace('"', '\\"') + '";')
    if cmds.menuItem('AEautoUpdateMenuItem',exists=True) and not cmds.menuItem('AEautoUpdateMenuItem',query=True,checkBox=True):
        mel.eval('showEditorSetListType("auto");')
        _owns_ae_pin=True


def _release_pin(*_):
    global _owns_ae_pin
    if (_owns_ae_pin and cmds.menuItem('AEautoUpdateMenuItem',exists=True) and
            cmds.menuItem('AEautoUpdateMenuItem',query=True,checkBox=True)):
        mel.eval('showEditorSetListType("auto");')
    _owns_ae_pin=False


def _node(ctx):
    from maya.api import OpenMaya as om
    handle=ctx.get('handle')
    if handle is not None and handle.isAlive() and handle.isValid():
        ctx['node']=om.MFnDependencyNode(handle.object()).name()
    return ctx['node']


def _handle(node):
    from maya.api import OpenMaya as om
    selection=om.MSelectionList();selection.add(node)
    return om.MObjectHandle(selection.getDependNode(0))


def _rename_node(node,value):
    value=value.strip()
    if not value or any(c in value for c in '|.'):
        raise ValueError('Enter a node name without a DAG path or attribute suffix.')
    if ':' not in value and ':' in node:value=node.rsplit(':',1)[0]+':'+value
    return cmds.rename(node,':'+value.lstrip(':'),ignoreShape=True)


def _names_changed():
    from maya import utils
    def update():
        if _list is None:return
        refresh()
        for ctx in list(_contexts.values()):
            if cmds.columnLayout(ctx['root'],exists=True):_refresh(ctx)
    utils.executeDeferred(update)


def _line_item_changed(item):
    from PySide6 import QtCore
    node=item.data(QtCore.Qt.UserRole)
    if not cmds.objExists(node):return refresh()
    if item.text()!=node:
        from maya import utils
        value=item.text()
        def commit():
            try:renamed=_rename_node(node,value)
            except Exception:
                refresh(node)
                raise
            refresh(renamed);_open(renamed)
        utils.executeDeferred(lambda:_safe(commit))
    else:
        graph.set_active(node,item.checkState()==QtCore.Qt.Checked)


def _new_line():
    node = graph.create_line()
    refresh(node)
    _open(node)
    return node


def _delete_selected():
    global _selected_line
    nodes=([_selected_line] if _selected_line and cmds.objExists(_selected_line) else cmds.ls(selection=True, type='revToonLine') or [])
    _selected_line=None
    _release_pin()
    for node in nodes:
        graph.delete_line(node)
    refresh()
    from . import viewport
    viewport.request_refresh(graph_changed=True)


def refresh(selected=None):
    global _selected_line
    if _list is None:
        return
    from PySide6 import QtCore, QtWidgets
    previous = selected or _selected_line
    previous_id=(_list.currentItem().data(QtCore.Qt.UserRole+1) if _list.currentItem() and not selected else None)
    _list.blockSignals(True)
    _list.clear()
    nodes = list(reversed(graph.list_lines()))
    for node in nodes:
        item = QtWidgets.QListWidgetItem(node, _list)
        item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEditable)
        item.setCheckState(QtCore.Qt.Checked if _active(node) else QtCore.Qt.Unchecked)
        item.setData(QtCore.Qt.UserRole, node)
        uid=cmds.ls(node,uuid=True)[0]
        item.setData(QtCore.Qt.UserRole+1,uid)
        if node == previous or uid==previous_id:
            _list.setCurrentItem(item)
            previous=node
    _list.blockSignals(False)
    _selected_line = previous if previous in nodes else None
    _sync_priority()
    if _aux_refresh:
        _aux_refresh()


def _sync_priority():
    enabled = bool(_selected_line and cmds.objExists(_selected_line))
    for control in (_priority_slider, _priority_spin):
        if control is not None:
            control.blockSignals(True)
            control.setEnabled(enabled)
            control.setValue(int(cmds.getAttr(_selected_line + '.renderPriority')) if enabled else 0)
            control.blockSignals(False)


def _priority(node, value):
    graph.set_priority(node, int(value))
    refresh(node)


def _line_selection():
    global _selected_line
    from PySide6 import QtCore
    item = _list.currentItem()
    _selected_line = item.data(QtCore.Qt.UserRole) if item else None
    _sync_priority()
    if _selected_line:
        _safe(_open, _selected_line)


def show():
    global _window, _list, _priority_slider, _priority_spin, _name_job
    from maya import OpenMayaUI
    from PySide6 import QtCore, QtWidgets
    from shiboken6 import wrapInstance, isValid
    if _window is not None and isValid(_window):
        _window.show()
        _window.raise_()
        refresh()
        return WINDOW
    main = wrapInstance(int(OpenMayaUI.MQtUtil.mainWindow()), QtWidgets.QWidget)
    _window = QtWidgets.QDialog(main)
    _window.finished.connect(_release_pin)
    _window.setObjectName(WINDOW)
    _window.setWindowTitle(tr('ReaPencil Line'))
    _window.setWindowFlags(QtCore.Qt.Window)
    _window.resize(440, 440)
    _window.setMinimumWidth(430)
    layout = QtWidgets.QVBoxLayout(_window)
    layout.setContentsMargins(6, 6, 6, 6)
    tabs = QtWidgets.QTabWidget()
    tabs.setUsesScrollButtons(False)
    page = QtWidgets.QWidget()
    body = QtWidgets.QVBoxLayout(page)
    body.setContentsMargins(5, 5, 5, 5)
    _list = QtWidgets.QListWidget()
    _list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
    _list.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked|QtWidgets.QAbstractItemView.EditKeyPressed)
    _list.setToolTip(tr('Click to edit without changing Maya selection. Double-click or F2 to rename.'))
    _list.setAlternatingRowColors(False)
    _list.setStyleSheet('QListWidget::item:selected { background: #527f9c; color: white; }')
    _list.itemSelectionChanged.connect(_line_selection)
    _list.itemClicked.connect(lambda item: _safe(_open,item.data(QtCore.Qt.UserRole)))
    _list.itemChanged.connect(lambda item: _safe(_line_item_changed,item))
    body.addWidget(_list, 1)
    row = QtWidgets.QHBoxLayout()
    for text, callback in [('Add Line', _new_line), ('Delete', _delete_selected), ('Refresh', refresh)]:
        button = QtWidgets.QPushButton(tr(text))
        button.setObjectName({'Add Line':'revToonAddLine','Delete':'revToonDeleteLine','Refresh':'revToonRefreshLines'}[text])
        button.clicked.connect(lambda checked=False, fn=callback: _safe(fn))
        row.addWidget(button)
    body.addLayout(row)
    priority_row = QtWidgets.QHBoxLayout()
    priority_row.addWidget(QtWidgets.QLabel(tr('Render Priority')))
    _priority_spin = QtWidgets.QSpinBox()
    _priority_spin.setRange(0, 99)
    _priority_spin.setFixedWidth(48)
    _priority_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    _priority_slider.setRange(0, 99)
    for control in (_priority_spin, _priority_slider):
        control.valueChanged.connect(lambda value: _safe(_priority, _selected_line, value) if _selected_line else None)
    priority_row.addWidget(_priority_spin)
    priority_row.addWidget(_priority_slider, 1)
    body.addLayout(priority_row)
    tabs.addTab(page, tr('ReaPencil Line'))
    from . import line_aux_ui
    global _aux_refresh
    _aux_refresh = line_aux_ui.add_tabs(tabs)
    layout.addWidget(tabs)
    import_button = QtWidgets.QPushButton(tr('Pencil+ 장면 가져오기 / 이전'))
    from . import menu_actions
    import_button.clicked.connect(lambda *_:_safe(menu_actions.import_pencil_scene))
    layout.addWidget(import_button)
    layout.addWidget(QtWidgets.QLabel(tr('메시 선택을 유지합니다. Objects +로 바로 추가할 수 있습니다.')))
    _window.show()
    if _name_job is None:_name_job=cmds.scriptJob(event=('NameChanged',_names_changed))
    refresh()
    return WINDOW


def close():
    global _rows, _window, _list, _selected_line, _aux_refresh, _name_job
    _release_pin()
    if _name_job is not None:
        if cmds.scriptJob(exists=_name_job):cmds.scriptJob(kill=_name_job)
        _name_job=None
    if _window is not None:
        try:
            _window.close()
            _window.deleteLater()
        except RuntimeError:
            pass
    _rows = _window = _list = _selected_line = None
    _aux_refresh = None
    _contexts.clear()


def _setting(node, key, value):
    values = graph.get_settings(node)
    values[key] = value
    graph.set_settings(node, values)


def _scene_setting(key, value):
    values = maya_scene.load_settings()
    values[key] = value
    maya_scene.save_settings(values)


def _selected_set(ctx):
    selected = cmds.textScrollList(ctx['sets'], query=True, selectItem=True) or []
    if not selected:
        raise ValueError('Select a Line Set first.')
    return selected[0]


def _refresh(ctx, selected=None):
    node = _node(ctx)
    if not cmds.objExists(node):
        return
    nodes = graph.list_sets(node)
    previous = cmds.textScrollList(ctx['sets'], query=True, selectItem=True) or []
    cmds.textScrollList(ctx['sets'], edit=True, removeAll=True)
    if nodes:
        cmds.textScrollList(ctx['sets'], edit=True, append=nodes,
                            selectItem=selected if selected in nodes else previous[0] if previous and previous[0] in nodes else nodes[0])
    _set_changed(ctx)


def _set_changed(ctx):
    for key in ('objects', 'shaders'):
        cmds.textScrollList(ctx[key], edit=True, removeAll=True)
    selected = cmds.textScrollList(ctx['sets'], query=True, selectItem=True) or []
    for child in cmds.columnLayout(ctx['detail'], query=True, childArray=True) or []:
        cmds.deleteUI(child)
    cmds.setParent(ctx['detail'])
    if not selected:
        cmds.text(label=tr('Add a Line Set to edit its targets and brush.'), align='left')
        return
    node = selected[0]
    targets = graph.get_targets(node)
    for key in ('objects', 'shaders'):
        if targets.get(key):
            cmds.textScrollList(ctx[key], edit=True, append=targets[key])
    values = dict(maya_scene.DEFAULT_SETTINGS)
    values.update(graph.get_settings(ctx['node']))
    values.update(graph.get_settings(node))
    name_control=cmds.textFieldGrp(label=tr('Line Set Name'), text=node)
    ctx['set_name']=name_control
    cmds.textFieldGrp(name_control,edit=True,
                     changeCommand=lambda *_:_defer_rename_set(ctx,node,cmds.textFieldGrp(name_control,query=True,text=True)))
    cmds.checkBox(label=tr('On'), value=_active(node), changeCommand=lambda value: _safe(graph.set_active, node, value))
    _field(node,'lineset_id','Line Set ID (1–8)',values)
    tabs = cmds.tabLayout(innerMarginWidth=6, innerMarginHeight=5)
    visible = cmds.columnLayout(adjustableColumn=True)
    _feature_fields(node, values)
    _brush_fields(node, values)
    cmds.setParent(tabs)
    hidden = cmds.columnLayout(adjustableColumn=True)
    _field(node, 'hidden_lines', 'Draw hidden lines', values)
    _field(node, 'hidden_color', 'Hidden color', values)
    cmds.text(label=tr('Hidden lines use the same edge types and width.\nVP2 uses a dashed x-ray preview.'), align='left')
    cmds.setParent(tabs)
    detail = cmds.columnLayout(adjustableColumn=True)
    for key, label in [('distance_reduction','Distance reduction'),('width_variation','Width variation'),
                       ('taper','Taper'),('dash_length','Dash length'),('dash_gap','Dash gap (-1 = length)'),
                       ('connect_collinear_dashes','Connect collinear dashes (CPU)')]:
        _field(node, key, label, values)
    cmds.text(label=tr('Taper and variation are supported by offline rendering.\nVP2 shows constant width per edge.'), align='left')
    cmds.setParent(tabs)
    cmds.tabLayout(tabs, edit=True, tabLabel=tr([(visible,'Visible Lines'),(hidden,'Hidden Lines'),(detail,'Brush Details')]))


def _field(node, key, label, values):
    value = values[key]
    if isinstance(maya_scene.DEFAULT_SETTINGS[key], bool):
        cmds.checkBox(label=tr(label), value=value, changeCommand=lambda v: _safe(_setting,node,key,v))
    elif isinstance(value, (list, tuple)):
        control = cmds.colorSliderGrp(label=tr(label), rgbValue=value)
        callback=lambda *_: _safe(_setting,node,key,cmds.colorSliderGrp(control,query=True,rgbValue=True))
        cmds.colorSliderGrp(control, edit=True, changeCommand=callback,dragCommand=callback)
    elif isinstance(maya_scene.DEFAULT_SETTINGS[key], int):
        control = cmds.intFieldGrp(label=tr(label), numberOfFields=1, value1=value)
        cmds.intFieldGrp(control, edit=True, changeCommand=lambda *_: _safe(_setting,node,key,cmds.intFieldGrp(control,query=True,value1=True)))
    else:
        control = cmds.floatFieldGrp(label=tr(label), numberOfFields=1, value1=value, precision=3)
        callback=lambda *_: _safe(_setting,node,key,cmds.floatFieldGrp(control,query=True,value1=True))
        cmds.floatFieldGrp(control, edit=True, changeCommand=callback,dragCommand=callback)


def _feature_fields(node, values):
    frame = cmds.frameLayout(label=tr('Line Types'), collapsable=True, collapse=False)
    cmds.columnLayout(adjustableColumn=True)
    for key, label in [('outline','Outline'),('open_edges','Open edges'),('intersections','Object intersections'),
                       ('self_intersections','Self intersections'),('hard_edges','Hard edges'),
                       ('material_boundaries','Material boundaries'),('selected_edges','Stored selected edges'),
                       ('crease','Crease'),('wireframe','All polygon edges'),('merge_groups','Use merge groups')]:
        _field(node,key,label,values)
    _field(node,'crease_angle','Crease angle',values)
    cmds.setParent(frame)
    cmds.setParent('..')


def _brush_fields(node, values):
    frame = cmds.frameLayout(label=tr('Brush'), collapsable=True, collapse=False)
    cmds.columnLayout(adjustableColumn=True)
    _field(node,'line_color','Color',values)
    _field(node,'line_opacity','Opacity (CPU; one visible brush)',values)
    _field(node,'relative_line_size','Relative size (640 px width)',values)
    _field(node,'line_width','Size (pixels)',values)
    _field(node,'brush_size_scale','Width multiplier (CPU)',values)
    cmds.setParent(frame)
    cmds.setParent('..')


def _rename_set(ctx, node, value):
    renamed = _rename_node(node, value)
    from maya import utils
    utils.executeDeferred(lambda:_refresh(ctx,renamed) if cmds.columnLayout(ctx['root'],exists=True) else None)
    return renamed


def _defer_rename_set(ctx,node,value):
    # Renaming can synchronously rebuild Maya's AE and delete the focused
    # QLineEdit. Commit only after its editingFinished/key event has returned.
    from maya import utils
    utils.executeDeferred(lambda:_safe(_rename_set,ctx,node,value))


def _prompt_rename_set(ctx):
    node=_selected_set(ctx)
    answer=cmds.promptDialog(title=tr('Rename Line Set'),message=tr('Name'),text=node,button=tr(['Rename','Cancel']),defaultButton=tr('Rename'),cancelButton=tr('Cancel'),dismissString=tr('Cancel'))
    if answer==tr('Rename'):return _defer_rename_set(ctx,node,cmds.promptDialog(query=True,text=True))


def _add_set(ctx):
    from maya.api import OpenMaya as om
    selection=om.MGlobal.getActiveSelectionList()
    try:node = graph.create_line_set(_node(ctx))
    finally:om.MGlobal.setActiveSelectionList(selection)
    _open(_node(ctx))
    _refresh(ctx,node)


def _remove_set(ctx):
    graph.delete_line_set(_selected_set(ctx))
    _refresh(ctx)


def _reorder(ctx, delta):
    node = _selected_set(ctx)
    nodes = graph.list_sets(ctx['node'])
    index = nodes.index(node)
    other = max(0,min(len(nodes)-1,index+delta))
    nodes[index],nodes[other] = nodes[other],nodes[index]
    graph.reorder_sets(ctx['node'],nodes)
    _refresh(ctx,node)


def _remove_targets(ctx, kind):
    selected = cmds.textScrollList(ctx[kind], query=True, selectItem=True) or []
    graph.remove_targets(_selected_set(ctx),selected,kind=kind)
    _set_changed(ctx)


def _add_selected(ctx,kind):
    """Add viewport selection as whole objects, keeping component selection too."""
    selected=cmds.ls(selection=True,long=True,objectsOnly=True) or []
    targets=[]
    for node in selected:
        if kind=='shaders':
            if cmds.attributeQuery('outColor',node=node,exists=True):targets.append(node)
        elif cmds.nodeType(node)=='mesh':
            targets.extend(cmds.listRelatives(node,parent=True,fullPath=True) or [node])
        elif cmds.nodeType(node)=='transform' and (cmds.listRelatives(node,shapes=True,type='mesh') or cmds.listRelatives(node,allDescendents=True,type='mesh')):
            targets.append(node)
    if not targets:return _chooser(ctx,kind)
    target=_selected_set(ctx)
    graph.add_targets(target,targets,kind=kind)
    _open(_node(ctx))
    for current in list(_contexts.values()):
        if _node(current)==_node(ctx) and cmds.columnLayout(current['root'],exists=True):_refresh(current,target)
    return targets


def _whole_object_paths(names):
    """Compare transform/shape aliases without treating partial faces as whole objects."""
    paths=set()
    for name in names:
        if '.' in name:continue
        for path in cmds.ls(name,long=True) or []:
            if cmds.nodeType(path)=='mesh':paths.update(cmds.listRelatives(path,parent=True,fullPath=True) or [path])
            else:paths.add(path)
    return paths


def _chooser(ctx, kind):
    target = _selected_set(ctx)
    window = cmds.window(title=tr('Add ' + ('Objects' if kind=='objects' else 'Materials')), widthHeight=(420,440))
    cmds.columnLayout(adjustableColumn=True)
    filter_control = cmds.textField(placeholderText='Filter by name')
    selected_only = cmds.checkBox(label=tr('Current Maya selection only'), value=False)
    listing = cmds.textScrollList(allowMultiSelection=True,height=320)
    def populate(*_):
        query = cmds.textField(filter_control,query=True,text=True).lower()
        selection = cmds.ls(selection=True,long=True) or []
        if kind == 'shaders':
            registered = set(graph.get_targets(target)['shaders'])
            candidates = [n for n in (cmds.ls(materials=True) or []) if n not in registered]
            if cmds.checkBox(selected_only,query=True,value=True):
                candidates = [n for n in candidates if n in selection]
        elif cmds.checkBox(selected_only,query=True,value=True):
            candidates = selection
        else:
            candidates = sorted(set((cmds.listRelatives(m,parent=True,fullPath=True) or [m])[0]
                                    for m in cmds.ls(type='mesh',long=True) or []))
        if kind == 'objects':
            registered = _whole_object_paths(graph.get_targets(target)['objects'])
            candidates = [n for n in candidates if not (_whole_object_paths([n]) & registered)]
        cmds.textScrollList(listing,edit=True,removeAll=True)
        candidates = [n for n in candidates if query in n.lower()]
        if candidates:
            cmds.textScrollList(listing,edit=True,append=candidates)
    def accept(*_):
        chosen = cmds.textScrollList(listing,query=True,selectItem=True) or []
        graph.add_targets(target,chosen,kind=kind)
        cmds.deleteUI(window)
        # Adding message/SG links can rebuild Maya's AE input-node tabs while
        # the modal chooser closes. Return explicitly to the owning Line and
        # update the current controls, not widgets from the old AE instance.
        _open(ctx['node'])
        current=[value for value in _contexts.values() if value['node']==ctx['node']
                 and cmds.columnLayout(value['root'],exists=True)]
        if current:
            _refresh(current[-1],target)
    cmds.textField(filter_control,edit=True,textChangedCommand=populate)
    cmds.checkBox(selected_only,edit=True,changeCommand=populate)
    cmds.button(label=tr('Add selected'),command=lambda *_:_safe(accept))
    populate()
    cmds.showWindow(window)
    from maya import OpenMayaUI
    from PySide6 import QtCore, QtWidgets
    from shiboken6 import wrapInstance
    pointer = OpenMayaUI.MQtUtil.findWindow(window)
    if pointer:
        widget = wrapInstance(int(pointer), QtWidgets.QWidget)
        widget.setWindowModality(QtCore.Qt.ApplicationModal)
        widget.show()


def ae_create(plug):
    parent = cmds.setParent(query=True)
    root = cmds.columnLayout(adjustableColumn=True)
    ctx = {'node':plug.rsplit('.',1)[0],'root':root,'parent':parent}
    ctx['handle']=_handle(ctx['node'])
    _contexts[parent] = ctx
    try:
        _build_ae(ctx)
    finally:
        cmds.setParent(parent)


def ae_replace(plug):
    parent = cmds.setParent(query=True)
    ctx = _contexts.get(parent)
    if not ctx or not cmds.columnLayout(ctx['root'],exists=True):
        return ae_create(plug)
    ctx['node'] = plug.rsplit('.',1)[0]
    ctx['handle']=_handle(ctx['node'])
    for child in cmds.columnLayout(ctx['root'],query=True,childArray=True) or []:
        cmds.deleteUI(child)
    cmds.setParent(ctx['root'])
    try:
        _build_ae(ctx)
    finally:
        cmds.setParent(parent)


def _build_ae(ctx):
    node = _node(ctx)
    active_control = cmds.checkBox(label=tr('Active'),value=_active(node),changeCommand=lambda v:_safe(graph.set_active,node,v))
    priority_control = cmds.intSliderGrp(label=tr('Render Priority'),field=True,minValue=0,maxValue=99,
                     value=cmds.getAttr(node+'.renderPriority'),changeCommand=lambda v:_safe(_priority,node,v))
    cmds.connectControl(active_control,node+'.active')
    cmds.connectControl(priority_control,node+'.renderPriority')
    form = cmds.formLayout(numberOfDivisions=300,height=230)
    for index,(key,label) in enumerate([('sets','Line Sets'),('objects','Objects'),('shaders','Materials')]):
        cmds.setParent(form)
        column = cmds.columnLayout(adjustableColumn=True,width=120)
        cmds.text(label=tr(label),align='left')
        ctx[key] = cmds.textScrollList(allowMultiSelection=key!='sets',height=164,width=120,
            selectCommand=(lambda *_:_safe(_set_changed,ctx)) if key=='sets' else lambda *_:None)
        if key=='sets':cmds.textScrollList(ctx[key],edit=True,doubleClickCommand=lambda *_:_safe(_prompt_rename_set,ctx))
        count = 4 if key=='sets' else 2
        row = cmds.rowLayout(numberOfColumns=count,adjustableColumn=1,
                             columnWidth=[(i+1,26) for i in range(count)])
        ctx['add_'+key] = cmds.button(label=tr('+'),width=26,annotation=tr('Add selected '+label+' (right-click to browse)'),command=(lambda *_:_safe(_add_set,ctx)) if key=='sets' else lambda _,k=key:_safe(_add_selected,ctx,k))
        if key!='sets':
            popup=cmds.popupMenu(parent=ctx['add_'+key],button=tr(3))
            cmds.menuItem(label=tr('Browse '+label+'…'),parent=popup,command=lambda _,k=key:_safe(_chooser,ctx,k))
        ctx['remove_'+key] = cmds.button(label=tr('−'),width=26,annotation=tr('Remove selected'),command=(lambda *_:_safe(_remove_set,ctx)) if key=='sets' else lambda _,k=key:_safe(_remove_targets,ctx,k))
        if key=='sets':
            ctx['move_up'] = cmds.button(label=tr('↑'),width=26,command=lambda *_:_safe(_reorder,ctx,-1))
            ctx['move_down'] = cmds.button(label=tr('↓'),width=26,command=lambda *_:_safe(_reorder,ctx,1))
        cmds.formLayout(form,edit=True,attachForm=[(column,'top',2),(column,'bottom',2)],
            attachPosition=[(column,'left',2,index*100),(column,'right',2,(index+1)*100)])
    cmds.setParent(ctx['root'])
    frame = cmds.frameLayout(label=tr('Line Size'),collapsable=True,collapse=False)
    cmds.columnLayout(adjustableColumn=True)
    cmds.radioButtonGrp(numberOfRadioButtons=2,labelArray2=tr(['Absolute (pixels)','Relative (unsupported)']),select=1,enable2=False)
    cmds.setParent(ctx['root'])
    frame = cmds.frameLayout(label=tr('Others'),collapsable=True,collapse=True)
    cmds.columnLayout(adjustableColumn=True)
    values = dict(maya_scene.DEFAULT_SETTINGS,**graph.get_settings(node))
    sampling = cmds.intFieldGrp(label=tr('Over Sampling (scene)'),numberOfFields=1,
                               value1=maya_scene.load_settings()['supersample'])
    cmds.intFieldGrp(sampling,edit=True,changeCommand=lambda *_:_safe(_scene_setting,'supersample',
        cmds.intFieldGrp(sampling,query=True,value1=True)))
    _field(node,'seed','Random Seed',values)
    output_control=cmds.checkBox(label=tr('Output to Render Elements Only'),value=cmds.getAttr(node+'.outputToRE'))
    cmds.connectControl(output_control,node+'.outputToRE')
    cmds.floatFieldGrp(label=tr('Offscreen distance (unsupported)'),numberOfFields=1,value1=0,enable=False)
    cmds.setParent(ctx['root'])
    frame = cmds.frameLayout(label=tr('Line Set'),collapsable=True,collapse=False)
    ctx['detail'] = cmds.columnLayout(adjustableColumn=True)
    _refresh(ctx)

