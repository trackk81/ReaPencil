"""Maya node drop and native texture-creation bridge for brush map controls."""
import json
from maya import cmds,mel
from .i18n import tr
from . import maya_brush_maps

_serial=0
_pending=None
_bindings={}


def navigation(control,attribute,create,connect,disconnect,attach):
    """Maya's native navigation hooks take MEL scripts, not Python callables."""
    for plug,entry in list(_bindings.items()):
        if not cmds.control(entry['control'],exists=True):del _bindings[plug]
    _bindings[attribute]=dict(control=control,create=create,connect=connect,disconnect=disconnect,attach=attach)
    mel.eval(r'''global proc reaPencilBrushMapConnect(string $source,string $destination) {
        string $code = ("from reatoon import brush_map_ui; brush_map_ui.native_drop(\"" + encodeString($source) + "\", \"" + encodeString($destination) + "\")");
        python($code);
    }''')
    def command(action):
        code='from reatoon import brush_map_ui; brush_map_ui.native_event('+repr(attribute)+','+repr(action)+')'
        return 'python('+json.dumps(code)+');'
    cmds.attrNavigationControlGrp(control,e=True,createNew=command('create'),
        connectToExisting=command('connect'),disconnect=command('disconnect'),
        connectAttrToDropped='reaPencilBrushMapConnect',connectNodeToDropped='reaPencilBrushMapConnect')


def native_event(attribute,action):
    entry=_bindings.get(attribute)
    if entry and cmds.control(entry['control'],exists=True):
        from .line_editor import _safe
        return _safe(entry[action])


def native_drop(source,attribute):
    entry=_bindings.get(attribute)
    if entry and cmds.control(entry['control'],exists=True):
        from .line_editor import _safe
        return _safe(lambda:entry['attach'](dropped_node([source])))


def dropped_node(messages):
    """Read Maya drag data as node names, never as executable MEL/Python."""
    nodes=[]
    for message in messages:
        value=str(message).strip()
        if not value or not cmds.objExists(value):continue
        if '.' in value:
            name,attribute=value.split('.',1)
            if attribute not in ('outColor','oc'):
                raise ValueError(tr('Drop the texture node or its outColor output.'))
            value=name
        matches=cmds.ls(value,long=True) or []
        if len(matches)!=1:raise ValueError(tr('Drop one Maya 2D texture node.'))
        if matches[0] not in nodes:nodes.append(matches[0])
    if len(nodes)!=1:raise ValueError(tr('Drop one Maya 2D texture node.'))
    validate_texture(nodes[0])
    return nodes[0]


def validate_texture(texture):
    maya_brush_maps.binding(texture,cmds)
    # Reject spatial maps here, before replacing a working connection.
    for node in cmds.listHistory(texture,pruneDagObjects=True) or [texture]:
        kind=cmds.nodeType(node)
        if kind in ('projection','place3dTexture') or cmds.getClassification(kind,satisfies='texture/3d'):
            raise ValueError(tr('Brush maps support UV-based Maya 2D textures; 3D and projection maps are not supported.'))


def show_in_hypershade(descriptor):
    """Reveal the connected texture and its inputs without changing the map."""
    if not descriptor.get('node') and not descriptor.get('uuid'):
        raise ValueError(tr('Connect a map before showing it in Hypershade.'))
    texture=maya_brush_maps.resolve_node(descriptor,cmds)
    mel.eval('HypershadeWindow;')
    panels=cmds.getPanel(scriptType='hyperShadePanel') or []
    if not panels:
        raise RuntimeError(tr('Could not open Hypershade.'))
    cmds.select(texture,replace=True)
    panel=json.dumps(panels[0])
    mel.eval('hyperShadePanelGraphCommand('+panel+', "showUpstream");')
    mel.eval('hyperShadePanelGraphCommand('+panel+', "rearrangeGraph");')
    return texture


def create_texture(control,callback):
    """Use Maya's creation UI, including its normal place2dTexture setup."""
    global _serial,_pending
    _serial+=1
    token=str(_serial)
    _pending=(token,control,callback)
    python='from reatoon import brush_map_ui; brush_map_ui.created("'+token+'", "%node")'
    command='python('+json.dumps(python)+')'
    mel.eval('createRenderNode "-textures" '+json.dumps(command)+' "";')
    # Show the supported native category first instead of the general file picker.
    mel.eval('global string $gCreateRenderNodeWindowTreeLister; '
             'treeLister -e -selectPath "Maya/2D Textures" $gCreateRenderNodeWindowTreeLister;')
    return token


def created(token,texture):
    global _pending
    if _pending is None or _pending[0]!=token:return
    _,control,callback=_pending;_pending=None
    if not cmds.control(control,exists=True):
        cmds.warning(tr('Brush editor was closed; the new texture was not connected.'));return
    from .line_editor import _safe
    return _safe(callback,texture)
