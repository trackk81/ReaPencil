"""Maya renderer registry, Render View and batch adapters for ReaPencil.

The renderer identifier is ``revtoon``; module paths remain ``reatoon`` for
existing installations. Registration never selects a renderer or changes a scene.
The CPU backend writes PNG passes, SVG, EPS and a manifest. It is not IPR.
"""
from __future__ import annotations

import json
import math
import os
import re
import shlex
from pathlib import Path

from maya import cmds, mel

RENDERER = "revtoon"
UI_NAME = "ReaPencil"
_LAST_RESULT = None


def _attribute(name, fallback=None):
    return cmds.getAttr(name) if cmds.objExists(name) else fallback


def _safe_name(value):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' .') or 'untitled'


def _camera_shape(camera=None):
    if camera:
        found = cmds.ls(camera, long=True) or []
        if len(found) != 1:
            raise ValueError("Camera must resolve to exactly one Maya node: " + camera)
        name = found[0]
        if cmds.nodeType(name) == "transform":
            shapes = cmds.listRelatives(name, shapes=True, type="camera", fullPath=True) or []
            if len(shapes) != 1:
                raise ValueError("Transform must contain exactly one camera")
            return shapes[0]
        if cmds.nodeType(name) != "camera":
            raise ValueError("Not a camera: " + name)
        return name
    names = cmds.ls(type="camera", long=True) or []
    renderable = [name for name in names if cmds.getAttr(name + ".renderable")]
    if renderable:
        return renderable[0]
    raise ValueError("No renderable camera. Enable a camera in Render Settings or pass camera explicitly.")


def _output_prefix(camera, numbered=None):
    root = Path(cmds.workspace(query=True, rootDirectory=True))
    rule = cmds.workspace(fileRuleEntry="images") or "images"
    folder = Path(rule)
    if not folder.is_absolute():
        folder = root / folder
    scene_name = Path(cmds.file(query=True, sceneName=True) or "untitled").stem
    transform = (cmds.listRelatives(camera, parent=True, fullPath=True) or [camera])[0]
    camera_name = _safe_name(transform.rsplit('|', 1)[-1])
    layer = cmds.editRenderLayerGlobals(query=True, currentRenderLayer=True)
    prefix = _attribute("defaultRenderGlobals.imageFilePrefix", "") or scene_name
    has_camera = "<Camera>" in prefix or "%c" in prefix
    replacements = {"<Scene>": _safe_name(scene_name), "%s": _safe_name(scene_name),
                    "<Camera>": camera_name, "%c": camera_name,
                    "<RenderLayer>": _safe_name(layer), "<Layer>": _safe_name(layer),
                    "<RenderPass>": "beauty"}
    for token, replacement in replacements.items():
        prefix = prefix.replace(token, replacement)
    if re.search(r'<[^>]+>', prefix):
        raise ValueError("Unsupported output token; use <Scene>, <Camera>, <RenderLayer> or <Layer>.")
    # Always separate cameras, so multi-camera batch outputs cannot overwrite.
    if not has_camera:
        prefix += "_" + camera_name
    numbered = bool(_attribute("defaultRenderGlobals.animation", False)) if numbered is None else numbered
    if numbered:
        frame = float(cmds.currentTime(query=True))
        padding = max(1, min(12, int(_attribute("defaultRenderGlobals.extensionPadding", 4))))
        if frame.is_integer():
            suffix = ("-" if frame < 0 else "") + str(abs(int(frame))).zfill(padding)
        else:
            suffix = ("%.6f" % frame).rstrip('0').rstrip('.').replace('.', '_')
        prefix += "." + suffix
    path = Path(prefix)
    return str(path if path.is_absolute() else folder / path)


def _settings(width=None, height=None):
    from . import maya_scene
    settings = maya_scene.load_settings()
    settings['width'] = int(width if width and width > 0 else cmds.getAttr('defaultResolution.width'))
    settings['height'] = int(height if height and height > 0 else cmds.getAttr('defaultResolution.height'))
    aspect = float(_attribute('defaultResolution.pixelAspect', 1.0))
    if not math.isclose(aspect, 1., abs_tol=1e-6):
        raise ValueError('ReaPencil requires square pixels, not a square image. Pixel Aspect Ratio is %.6g. In the ReaPencil Render Settings tab click "Use square pixels"; this keeps Width/Height and corrects the device aspect ratio.' % aspect)
    if int(_attribute('defaultRenderGlobals.imageFormat', 32)) != 32:
        cmds.warning('ReaPencil writes PNG image passes; the Maya image-format setting is not used.')
    return maya_scene.validate_settings(settings)


def _display_image(path):
    if cmds.about(batch=True):
        return False
    mel.eval('RenderViewWindow;')
    editor = 'renderView'
    if not cmds.renderWindowEditor(editor, exists=True):
        raise RuntimeError('Maya Render View editor could not be opened. Image saved at: ' + path)
    # Maya's PNG loader premultiplies RGB by alpha, making white-matte line
    # passes black. Upload the stored RGB and coverage independently instead.
    from pathlib import Path
    import tempfile
    from PySide6.QtGui import QImage
    native = Path(__file__).resolve().parents[2] / 'plug-ins' / cmds.about(version=True) / 'revToonImage.mll'
    if not cmds.pluginInfo('revToonImage', query=True, loaded=True):
        cmds.loadPlugin(str(native), quiet=True)
    image = QImage(str(path)).convertToFormat(QImage.Format_RGBA8888)
    if image.isNull():
        raise RuntimeError('Cannot decode rendered image: ' + str(path))
    with tempfile.NamedTemporaryFile(suffix='.rgba', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(bytes(image.constBits()))
    try:
        cmds.revToonDisplayImage(str(temporary), image.width(), image.height())
    finally:
        temporary.unlink(missing_ok=True)
    return True


def render_current(camera=None, width=None, height=None, display=True, output_prefix=None, auxiliary_outputs=False):
    """Render current time; return backend result, with beauty loaded in Render View.

    Native Maya globals supply camera, resolution and output prefix. CPU line and
    material options are read from the existing scene's ReaPencil settings node.
    """
    global _LAST_RESULT
    from . import maya_scene
    camera = _camera_shape(camera)
    settings = _settings(width, height)
    result = maya_scene.render_scene(output_prefix or _output_prefix(camera), camera, settings,
                                    auxiliary_outputs=auxiliary_outputs)
    result['render_view_displayed'] = _display_image(result['paths']['beauty']) if display else False
    _LAST_RESULT = result
    return result


def render_callback(width, height, shadows, glow, camera, options):
    """Six-argument signature used by Maya renderWithCurrentRenderer.mel."""
    # mayaPreviewRender supplies the layer it has already made current. This
    # standard option is supported by rendering that current layer, not an IPR
    # option that warrants a warning on every normal render.
    tokens = shlex.split(str(options or '').strip().strip('"'))
    if len(tokens)==2 and tokens[0] in ('-layer','-renderLayer'):
        current=cmds.editRenderLayerGlobals(query=True,currentRenderLayer=True)
        if tokens[1]!=current:
            raise ValueError('Render callback layer differs from current Maya layer: '+tokens[1])
    elif tokens:
        cmds.warning('ReaPencil renders the full frame; renderer-specific interactive options are ignored.')
    return render_current(camera or None, width, height, display=True)['paths']['beauty']


def _parse_batch_options(options):
    tokens = shlex.split(options or '', posix=True)
    result = {}
    aliases = {'-layer': 'layer', '-renderLayer': 'layer', '-camera': 'camera', '-cam': 'camera'}
    index = 0
    while index < len(tokens):
        flag = tokens[index]
        if flag not in aliases or index + 1 == len(tokens):
            raise ValueError('Unsupported ReaPencil batch option: ' + flag)
        result[aliases[flag]] = tokens[index + 1]
        index += 2
    return result


def batch_render(camera=None, options=''):
    """Render globals frame range/all renderable cameras in this Maya process.

    Batch Render in the Maya menu starts a separate Maya process through its
    standard batchRender command and our registered -r revtoon option string.
    This function is that process's actual rendering callback. Current time,
    render layer and renderer are restored on both success and error.
    """
    parsed = _parse_batch_options(options)
    camera = camera or parsed.get('camera')
    original_time = cmds.currentTime(query=True)
    original_renderer = _attribute('defaultRenderGlobals.currentRenderer', 'mayaSoftware')
    original_layer = cmds.editRenderLayerGlobals(query=True, currentRenderLayer=True)
    try:
        layer = parsed.get('layer')
        if layer and layer != original_layer:
            if not cmds.objExists(layer) or cmds.nodeType(layer) != 'renderLayer':
                raise ValueError('Unknown legacy render layer: ' + layer)
            cmds.editRenderLayerGlobals(currentRenderLayer=layer)
        if camera:
            cameras = [_camera_shape(camera)]
        else:
            cameras = [name for name in (cmds.ls(type='camera', long=True) or [])
                       if cmds.getAttr(name + '.renderable')]
            if not cameras:
                raise ValueError('No renderable camera for batch rendering.')
        animation = bool(_attribute('defaultRenderGlobals.animation', False))
        start = float(_attribute('defaultRenderGlobals.startFrame', original_time)) if animation else float(original_time)
        end = float(_attribute('defaultRenderGlobals.endFrame', original_time)) if animation else start
        step = float(_attribute('defaultRenderGlobals.byFrameStep', 1.)) if animation else 1.
        if not all(math.isfinite(value) for value in (start, end, step)) or step <= 0 or end < start:
            raise ValueError('Batch requires finite start <= end and positive by-frame step.')
        count = int(math.floor((end - start) / step + 1e-7)) + 1
        if count > 1000:
            raise ValueError('ReaPencil batch limit is 1000 frames per invocation.')
        results = []
        for index in range(count):
            frame = start + index * step
            cmds.currentTime(frame, edit=True)
            for cam in cameras:
                prefix = _output_prefix(cam, numbered=animation)
                if _attribute('defaultRenderGlobals.skipExistingFrames', False) and Path(prefix + '_manifest.json').is_file():
                    required = [prefix + '_' + suffix for suffix in
                                ('beauty.png', 'visible.png', 'hidden.png', 'depth.png', 'lines.svg', 'eps.eps')]
                    if all(Path(path).is_file() for path in required):
                        results.append({'frame': frame, 'camera': cam, 'skipped': True, 'output_prefix': prefix})
                        continue
                result = render_current(cam, display=False, output_prefix=prefix)
                results.append({'frame': frame, 'camera': cam, 'result': result})
        return results
    finally:
        if cmds.editRenderLayerGlobals(query=True, currentRenderLayer=True) != original_layer:
            cmds.editRenderLayerGlobals(currentRenderLayer=original_layer)
        cmds.currentTime(original_time, edit=True)
        if _attribute('defaultRenderGlobals.currentRenderer') != original_renderer:
            cmds.setAttr('defaultRenderGlobals.currentRenderer', original_renderer, type='string')


def command_render(options=''):
    return batch_render(options=options)


def _use_square_pixels(*_):
    """Keep the requested image dimensions and synchronize Maya's ratios.

    Direct attrControlGrp edits do not run the Common tab's resolution-change
    procedures. An old device ratio otherwise changes the computed pixel ratio.
    Called only by explicit resolution edits or the reset button, never render.
    """
    width=int(cmds.getAttr('defaultResolution.width'))
    height=int(cmds.getAttr('defaultResolution.height'))
    if width<=0 or height<=0:raise ValueError('Image width and height must be positive')
    cmds.setAttr('defaultResolution.lockDeviceAspectRatio',False)
    cmds.setAttr('defaultResolution.pixelAspect',1.)
    cmds.setAttr('defaultResolution.deviceAspectRatio',float(width)/height)


def _resolution_field(attribute,label):
    """Explicit edit callback; attrControlGrp's generated child bypasses cc."""
    field=cmds.intFieldGrp(label=label,numberOfFields=1,value1=int(cmds.getAttr(attribute)))
    def changed(*_):
        value=int(cmds.intFieldGrp(field,query=True,value1=True))
        if not 16<=value<=4096:
            cmds.intFieldGrp(field,edit=True,value1=int(cmds.getAttr(attribute)))
            raise ValueError('ReaPencil image dimensions must be between 16 and 4096 pixels')
        cmds.undoInfo(openChunk=True,chunkName='ReaPencil resolution')
        try:
            cmds.setAttr(attribute,value)
            _use_square_pixels()
        finally:cmds.undoInfo(closeChunk=True)
    cmds.intFieldGrp(field,edit=True,changeCommand=changed)
    # Common-tab edits, presets and Undo must also update this field.
    cmds.scriptJob(attributeChange=[attribute,lambda:cmds.intFieldGrp(field,edit=True,value1=int(cmds.getAttr(attribute)))],parent=field)
    return field


def _create_globals_tab():
    """ReaPencil-specific tab; Maya owns the standard Common tab hierarchy."""
    cmds.columnLayout(adjustableColumn=True)
    cmds.text(label='ReaPencil / 레아펜슬 — PNG + SVG + EPS', align='left')
    cmds.text(label='CPU reference renderer. Full frame only; no IPR or region render.', align='left')
    for attribute, label in [('defaultRenderGlobals.imageFilePrefix', 'File prefix'),
                             ('defaultResolution.width', 'Width'),
                             ('defaultResolution.height', 'Height'),
                             ('defaultResolution.pixelAspect', 'Pixel aspect (square = 1)'),
                             ('defaultRenderGlobals.animation', 'Animation'),
                             ('defaultRenderGlobals.startFrame', 'Start frame'),
                             ('defaultRenderGlobals.endFrame', 'End frame'),
                             ('defaultRenderGlobals.byFrameStep', 'Frame step'),
                             ('defaultRenderGlobals.extensionPadding', 'Frame padding'),
                             ('defaultRenderGlobals.skipExistingFrames', 'Skip existing frames')]:
        if attribute in ('defaultResolution.width','defaultResolution.height'):
            _resolution_field(attribute,label)
        else:
            cmds.attrControlGrp(attribute=attribute,label=label)
        if attribute=='defaultResolution.pixelAspect':
            cmds.button(label='Use square pixels',command=_use_square_pixels,
                        annotation='Keep Width/Height and set Pixel Aspect Ratio to 1.')
    cmds.separator(height=10, style='in')
    cmds.text(label='Renderable cameras (Batch renders all enabled cameras)', align='left')
    for camera in cmds.ls(type='camera', long=True) or []:
        cmds.attrControlGrp(attribute=camera + '.renderable', label=camera.rsplit('|', 1)[-1])
    cmds.button(label='Open ReaPencil line / material settings', command=lambda *_: _open_options())
    cmds.setParent('..')


def _open_options():
    from . import ui
    return ui.show()


def register():
    """Register the renderer and MEL callbacks without selecting it."""
    # encodeString on the MEL side protects quotes/backslashes in camera names.
    mel.eval(r'''
        global proc string revtoonRender(int $w, int $h, int $shadows, int $glow, string $camera, string $options) {
            python("import reatoon.render_integration");
            return python("reatoon.render_integration.render_callback(" + $w + "," + $h + "," + $shadows + "," + $glow + ",\"" + encodeString($camera) + "\",\"" + encodeString($options) + "\")");
        }
        global proc revtoonBatchRender(string $options) {
            python("import reatoon.render_integration");
            python("reatoon.render_integration.batch_render(options=\"" + encodeString($options) + "\")");
        }
        global proc revtoonCommandRender(string $options) {
            python("import reatoon.render_integration");
            python("reatoon.render_integration.command_render(\"" + encodeString($options) + "\")");
        }
        global proc string revtoonBatchOptions() { return " -r revtoon "; }
        global proc revtoonCreateGlobalsTab() {
            createMayaSoftwareCommonGlobalsTab();
        }
        global proc revtoonUpdateGlobalsTab() {
            updateMayaSoftwareCommonGlobalsTab();
        }
        global proc revtoonCreateOptionsTab() {
            python("import reatoon.render_integration");
            python("reatoon.render_integration._create_globals_tab()");
        }
        global proc revtoonUpdateOptionsTab() {}
    ''')
    already = cmds.renderer(RENDERER, query=True, exists=True)
    values = dict(rendererUIName=UI_NAME, renderProcedure='revtoonRender',
                  batchRenderProcedure='revtoonBatchRender', commandRenderProcedure='revtoonCommandRender',
                  batchRenderOptionsStringProcedure='revtoonBatchOptions', renderOptionsProcedure='unifiedRenderGlobalsWindow',
                  renderRegionProcedure='', iprRenderProcedure='')
    if already:
        cmds.renderer(RENDERER, edit=True, **values)
    else:
        cmds.renderer(RENDERER, **values)
        cmds.renderer(RENDERER, edit=True, addGlobalsNode='defaultRenderGlobals')
        cmds.renderer(RENDERER, edit=True, addGlobalsNode='defaultResolution')
        # Maya eagerly builds Common only for this exact built-in procedure
        # name. A forwarding wrapper stays lazy, so Arnold's renderer-change
        # callback can run before commonTabColumn exists.
        cmds.renderer(RENDERER, edit=True, addGlobalsTab=('Common', 'createMayaSoftwareCommonGlobalsTab', 'updateMayaSoftwareCommonGlobalsTab'))
    labels=cmds.renderer(RENDERER,query=True,globalsTabLabels=True) or []
    if 'ReaPencil' not in labels:
        cmds.renderer(RENDERER,edit=True,addGlobalsTab=('ReaPencil','revtoonCreateOptionsTab','revtoonUpdateOptionsTab'))
    return RENDERER


def unregister():
    if cmds.renderer(RENDERER, query=True, exists=True):
        if _attribute('defaultRenderGlobals.currentRenderer') == RENDERER:
            cmds.setAttr('defaultRenderGlobals.currentRenderer', 'mayaSoftware', type='string')
        cmds.renderer(RENDERER, edit=True, unregisterRenderer=True)
    if cmds.pluginInfo('revToonImage', query=True, loaded=True):
        cmds.unloadPlugin('revToonImage')
    for helper in ('revToonMesh074','revToonMesh'):
        if cmds.pluginInfo(helper, query=True, loaded=True):
            cmds.unloadPlugin(helper)
