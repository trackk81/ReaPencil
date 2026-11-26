"""Compact edge/brush editor; layout follows the installed Pencil UI contract.

ReaPencil keeps independent brush values on its line set. Navigation fields
open those values; they do not pretend to be shared Pencil brush nodes.
"""
import copy
import json
from maya import cmds
from .i18n import tr
from . import line_graph as graph, maya_scene, maya_brush_maps

LABEL_WIDTH=154
FEATURES=(('outline','outline','Outline'),('open','open_edges','Open edges'),
          ('intersection','intersections','Object intersections'),('hard','hard_edges','Hard edges'),
          ('material','material_boundaries','Material boundaries'),('selected','selected_edges','Stored selected edges'),
          ('crease','crease','Crease'),('wireframe','wireframe','All polygon edges'))
STATE='reaPencilBrushEditorState'
WINDOW='reaPencilSpecificBrushEditor'
_current=None


def _editor():
    from . import line_editor
    return line_editor


def _target(settings,hidden,feature=None):
    parent=settings.setdefault('hidden_style',{}) if hidden else settings
    return parent.setdefault('feature_brushes',{}).setdefault(feature,{}) if feature else parent


def _set(node,hidden,feature,key,value):
    if feature and feature not in _target(graph.get_settings(node),hidden).get('feature_brushes',{}):
        raise ValueError(tr('Enable Specific Brush Settings first.'))
    return _editor()._nested_setting(node,hidden,feature,key,value)


def _resolved(node,hidden=False,feature=None):
    from .brush_channels import BRUSH_KEYS
    values=maya_scene.load_settings()
    for line in cmds.listConnections(node+'.message',source=False,destination=True,type='revToonLine') or []:
        values.update(graph.get_settings(line));break
    values.update(graph.resolved_settings(node))
    if hidden:
        source=values.get('hidden_style',{})
        base=dict(values);base.update({k:maya_scene.DEFAULT_SETTINGS[k] for k in BRUSH_KEYS})
        base.update(line_color=values['hidden_color'],line_width=values['line_width'],feature_brushes={});base.update(source)
        values=base
    if feature:
        source=values.get('feature_brushes',{}).get(feature,{})
        base=dict(values);base.update({k:maya_scene.DEFAULT_SETTINGS[k] for k in BRUSH_KEYS})
        base.update(line_color=values['line_color'],line_width=values['line_width']);base.update(source)
        values=base
    return values


def _stored(node):
    return json.loads(cmds.getAttr(node+'.'+STATE) or '{}') if cmds.attributeQuery(STATE,node=node,exists=True) else {}


def set_specific(node,hidden,feature,enabled,values):
    """Turning a specific brush off must not destroy its edited values/maps."""
    settings=graph.get_settings(node);parent=_target(settings,hidden)
    brushes=parent.setdefault('feature_brushes',{});saved=_stored(node)
    slot=('hidden' if hidden else 'visible')+'_'+feature
    if enabled:
        if feature in brushes:return
        values=_resolved(node,hidden)
        brush=copy.deepcopy(saved.get(slot,dict(line_color=values['line_color'],line_width=values['line_width'])))
        for channel,desc in brush.get('brush_maps',{}).items():
            attr='reaPencilSavedMap_'+slot+'_'+channel
            if cmds.attributeQuery(attr,node=node,exists=True):
                linked=cmds.listConnections(node+'.'+attr,source=True,destination=False) or []
                if linked:
                    desc.update(node=linked[0],uuid=(cmds.ls(linked[0],uuid=True) or [''])[0])
                elif desc.get('uuid') or desc.get('node'):desc['uuid']='unconnected:'+node+'.'+attr
        brushes[feature]=brush
    else:
        if feature not in brushes:return
        if _current==(node,hidden,feature) and cmds.window(WINDOW,exists=True):cmds.deleteUI(WINDOW)
        saved[slot]=copy.deepcopy(brushes.pop(feature))
        for channel in ('color','width'):
            desc=saved[slot].get('brush_maps',{}).get(channel,{})
            attr='reaPencilSavedMap_'+slot+'_'+channel
            if not cmds.attributeQuery(attr,node=node,exists=True):
                if not desc:continue
                cmds.addAttr(node,longName=attr,attributeType='message',hidden=True)
            plug=node+'.'+attr
            for source in cmds.listConnections(plug,source=True,destination=False,plugs=True) or []:cmds.disconnectAttr(source,plug)
            if desc.get('node') or desc.get('uuid'):
                try:texture=maya_brush_maps.resolve_node(desc,cmds)
                except ValueError:continue
                cmds.connectAttr(texture+'.message',plug,force=True)
        if not cmds.attributeQuery(STATE,node=node,exists=True):cmds.addAttr(node,longName=STATE,dataType='string',hidden=True)
        cmds.setAttr(node+'.'+STATE,json.dumps(saved),type='string')
    graph.set_settings(node,settings)
    from . import viewport
    viewport.request_refresh(style_changed=True)


def _check(label,value,callback,sub=False):
    row=cmds.rowLayout(numberOfColumns=2,adjustableColumn=2,columnWidth2=(LABEL_WIDTH,250))
    cmds.text(label='' if sub else tr(label),align='right',width=LABEL_WIDTH)
    control=cmds.checkBox(label=tr(label) if sub else '',value=bool(value),changeCommand=lambda v:_editor()._safe(callback,v))
    cmds.setParent(row);cmds.setParent('..')
    return control


def edge_fields(node,values,hidden=False,refresh=None):
    frame=cmds.frameLayout(label=tr('Edge'),collapsable=True,collapse=False)
    cmds.columnLayout(adjustableColumn=True,rowSpacing=2)
    specifics=values.get('feature_brushes',{})
    for feature,key,label in FEATURES:
        on=_check(label,values.get(key,False),lambda v,k=key:_set(node,hidden,None,k,v))
        children=cmds.columnLayout(adjustableColumn=True,rowSpacing=1,enable=bool(values.get(key,False)))
        def edge_toggle(v,k=key,child=children):
            _set(node,hidden,None,k,v);cmds.columnLayout(child,e=True,enable=bool(v))
        cmds.checkBox(on,e=True,changeCommand=lambda v,fn=edge_toggle:_editor()._safe(fn,v))
        if feature=='outline':_check('Use merge groups',values.get('merge_groups',True),lambda v:_set(node,hidden,None,'merge_groups',v),True)
        if feature=='intersection':_check('Self intersections',values.get('self_intersections',False),lambda v:_set(node,hidden,None,'self_intersections',v),True)
        enabled=feature in specifics
        flag=_check('Specific Brush Settings',enabled,lambda v:None,True)
        field=cmds.textFieldButtonGrp(label='',text=(tr(label)+' / '+tr('Brush Settings')) if enabled else tr('Use common brush'),
            editable=False,buttonLabel='▸',enable=enabled,adjustableColumn=2,columnWidth3=(LABEL_WIDTH,250,28),
            annotation=tr('Open the specific brush stored in this Line Set'),
            buttonCommand=lambda *_,f=feature:_editor()._safe(open_brush,node,hidden,f))
        def specific_toggle(v,f=feature,control=field,title=label,check=flag):
            try:set_specific(node,hidden,f,v,values)
            finally:
                active=f in _target(graph.get_settings(node),hidden).get('feature_brushes',{})
                cmds.checkBox(check,e=True,value=active)
                cmds.textFieldButtonGrp(control,e=True,enable=active,text=(tr(title)+' / '+tr('Brush Settings')) if active else tr('Use common brush'))
        cmds.checkBox(flag,e=True,changeCommand=lambda v,fn=specific_toggle:_editor()._safe(fn,v))
        if feature=='crease':
            _number(node,hidden,None,'crease_angle','Normal angle minimum',values['crease_angle'],0,180)
            _number(node,hidden,None,'crease_angle_max','Normal angle maximum',values['crease_angle_max'],0,180)
        cmds.setParent(children);cmds.setParent('..')
        cmds.separator(style='none',height=4)
    cmds.setParent(frame);cmds.setParent('..')


def _number(node,hidden,feature,key,label,value,low=0.,high=10.):
    bounds={'line_width':(.1,64.),'brush_size_scale':(0.,1.),'line_opacity':(0.,1.),
            'crease_angle':(0.,180.),'crease_angle_max':(0.,180.)}
    field_low,field_high=bounds.get(key,(low,10000.))
    return cmds.floatSliderGrp(label=tr(label),field=True,value=value,precision=3,
        minValue=field_low,maxValue=max(high,min(float(value),field_high)),fieldMinValue=field_low,fieldMaxValue=field_high,
        adjustableColumn=3,columnWidth3=(LABEL_WIDTH,64,180),
        changeCommand=lambda v:_editor()._safe(_set,node,hidden,feature,key,v))


def _maps(node,hidden,feature):
    settings=graph.get_settings(node);parent=settings.get('hidden_style',{}) if hidden else settings
    return copy.deepcopy((parent.get('feature_brushes',{}).get(feature,{}) if feature else parent).get('brush_maps',{}))


def _save_map(node,hidden,feature,channel,changes):
    maps=_maps(node,hidden,feature)
    value=dict(enabled=False,node='',uuid='',amount=1.,uv_set='')
    value.update(maps.get(channel,{}));value.update(changes);maps[channel]=value
    _set(node,hidden,feature,'brush_maps',maps)
    return value


def map_fields(node,values,hidden,feature,channel):
    from . import brush_map_ui
    descriptor=values.get('brush_maps',{}).get(channel,{})
    label='Color map' if channel=='color' else 'Width map'
    enabled=bool(descriptor.get('enabled',False));controls={}
    def refresh():
        value=_maps(node,hidden,feature).get(channel,{})
        on=bool(value.get('enabled',False))
        cmds.checkBox(controls['on'],e=True,value=on)
        # Maya creates the native field lazily when the window is shown and
        # keeps its text synchronized with the message connection itself.
        cmds.floatSliderGrp(controls['amount'],e=True,value=value.get('amount',1.),enable=on)
    def attach(texture):
        brush_map_ui.validate_texture(texture)
        old=_maps(node,hidden,feature).get(channel,{})
        _save_map(node,hidden,feature,channel,maya_brush_maps.binding(texture,cmds,old.get('amount',1.),old.get('uv_set','')))
        refresh()
    def load(*_):
        paths=cmds.fileDialog2(fileMode=1,caption=tr('Load image'),fileFilter='Images (*.png *.jpg *.jpeg *.tif *.tiff *.exr *.tga *.bmp);;All files (*.*)')
        if paths:attach(maya_brush_maps.create_file_texture(paths[0],cmds))
    def connect(*_):
        selected=cmds.ls(selection=True,objectsOnly=True) or []
        if len(selected)!=1:raise ValueError(tr('Select one texture node'))
        attach(selected[0])
    def create(*_):
        return brush_map_ui.create_texture(controls['map'],attach)
    def navigate(*_):
        value=_maps(node,hidden,feature).get(channel,{})
        if not value.get('node') and not value.get('uuid'):return create()
        texture=maya_brush_maps.resolve_node(value,cmds)
        _editor()._open(texture)
    def hypershade(*_):
        return brush_map_ui.show_in_hypershade(_maps(node,hidden,feature).get(channel,{}))
    def toggle(on):
        value=_maps(node,hidden,feature).get(channel,{})
        if on and not(value.get('node') or value.get('uuid')):
            create();refresh();return
        _save_map(node,hidden,feature,channel,{'enabled':bool(on)});refresh()
    def disconnect(*_):
        _save_map(node,hidden,feature,channel,dict(enabled=False,node='',uuid=''));refresh()
    controls['on']=_check('Use color map' if channel=='color' else 'Use width map',enabled,toggle,True)
    # Use Maya's native connection field (also used by Pencil+). Hypershade's
    # native node payload is handled by its connection callbacks.
    attr='reaBrushMap_'+('hidden' if hidden else 'visible')+('_'+feature if feature else '')+'_'+channel
    if not cmds.attributeQuery(attr,node=node,exists=True):
        cmds.addAttr(node,longName=attr,attributeType='message',hidden=True)
    controls['map']=cmds.attrNavigationControlGrp(label=tr(label),attribute=node+'.'+attr,
        adjustableColumn=2,columnWidth3=(LABEL_WIDTH,250,28),
        annotation=tr('Middle-drag from Hypershade. Empty button: create a Maya map. Right-click: connection options.'))
    brush_map_ui.navigation(controls['map'],node+'.'+attr,create,connect,disconnect,attach)
    menu=cmds.popupMenu(parent=controls['map'],button=3)
    def uv_set(*_):
        current=_maps(node,hidden,feature).get(channel,{})
        answer=cmds.promptDialog(title=tr('UV set'),message=tr('UV set (blank = current)'),text=current.get('uv_set',''),button=[tr('Apply'),tr('Cancel')],defaultButton=tr('Apply'),cancelButton=tr('Cancel'),dismissString=tr('Cancel'))
        if answer==tr('Apply'):_save_map(node,hidden,feature,channel,{'uv_set':cmds.promptDialog(q=True,text=True).strip()})
    for title,callback in [('Create Maya map',create),('Connect selected texture',connect),('Load image',load),('Open map',navigate),('Show in Hypershade',hypershade),('Disconnect map',disconnect),('UV set',uv_set)]:
        cmds.menuItem(parent=menu,label=tr(title),command=lambda *_,fn=callback:_editor()._safe(fn))
    controls['amount']=cmds.floatSliderGrp(label=tr('Map opacity' if channel=='color' else 'Map amount'),field=True,minValue=0,maxValue=1,
        fieldMinValue=0,fieldMaxValue=1,value=descriptor.get('amount',1.),precision=3,enable=enabled,
        adjustableColumn=3,columnWidth3=(LABEL_WIDTH,64,180),
        changeCommand=lambda v:_editor()._safe(_save_map,node,hidden,feature,channel,{'amount':v}))
    refresh()
    return controls


def brush_fields(node,values,hidden=False,feature=None):
    frame=cmds.frameLayout(label=tr('Brush Settings'),collapsable=True,collapse=False)
    cmds.columnLayout(adjustableColumn=True,rowSpacing=3)
    _editor()._blend_menu(values['blend_mode'],lambda v:_editor()._safe(_set,node,hidden,feature,'blend_mode',v))
    _number(node,hidden,feature,'line_opacity','Brush opacity (CPU)',values['line_opacity'],0,1)
    color=cmds.colorSliderGrp(label=tr('Color'),rgbValue=values['line_color'],adjustableColumn=3,columnWidth3=(LABEL_WIDTH,64,180))
    cmds.colorSliderGrp(color,e=True,changeCommand=lambda *_:_editor()._safe(_set,node,hidden,feature,'line_color',cmds.colorSliderGrp(color,q=True,rgbValue=True)))
    map_fields(node,values,hidden,feature,'color')
    _number(node,hidden,feature,'line_width','Size (pixels)',values['line_width'],.01,20)
    map_fields(node,values,hidden,feature,'width')
    controls=cmds.frameLayout(label=tr('Brush Details'),collapsable=True,collapse=True)
    cmds.columnLayout(adjustableColumn=True,rowSpacing=3)
    _number(node,hidden,feature,'brush_size_scale','Width multiplier (CPU)',values['brush_size_scale'],0,1)
    for key,label in [('dash_length','Dash length'),('dash_gap','Dash gap (-1 = length)')]:
        _number(node,hidden,feature,key,label,values[key],-1 if key=='dash_gap' else 0,40)
    _editor()._nested_profile_fields(node,hidden,feature)
    if feature is None:
        _check('Relative size (640 px width)',values['relative_line_size'],lambda v:_set(node,hidden,None,'relative_line_size',v),True) if not hidden else None
        cmds.button(label=tr('Hidden depth reduction (CPU)' if hidden else 'Camera depth reduction'),command=lambda *_:_editor()._edit_reduction(node,hidden))
    cmds.setParent(controls);cmds.setParent('..')
    cmds.text(label=tr('Maps: Normal Preview / CPU · 2D UV 0–1'),align='left',height=20)
    cmds.setParent(frame);cmds.setParent('..')


def open_brush(node,hidden=False,feature=None):
    global _current
    if not cmds.objExists(node):return
    if feature and feature not in _target(graph.get_settings(node),hidden).get('feature_brushes',{}):return
    title=next((label for f,_,label in FEATURES if f==feature),'Brush')
    window=WINDOW
    if cmds.window(window,exists=True):cmds.deleteUI(window)
    cmds.window(window,title='ReaPencil — '+tr(title)+' / '+tr('Hidden Lines' if hidden else 'Visible Lines'),widthHeight=(570,430),sizeable=True)
    cmds.scrollLayout(childResizable=True)
    cmds.columnLayout(adjustableColumn=True,rowSpacing=4)
    cmds.text(label=node,align='left',height=22)
    brush_fields(node,_resolved(node,hidden,feature),hidden,feature)
    cmds.showWindow(window)
    _current=(node,hidden,feature)
    return window
