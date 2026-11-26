"""Live Maya 2D brush textures, frozen once per CPU render.

Bindings are node UUIDs, not sampled colors. The snapshot evaluates the current
frame through Maya so file color management and place2dTexture remain active.
The CPU renderer uses a bounded 256 x 256 UV tile (0..1). Out-of-tile UVs,
3D/projection/UDIM textures are deliberately rejected instead of silently
producing an unrelated result. Placement is evaluated inside that tile.
"""
import copy
import math
import os
import numpy as np

RESOLUTION = 256
_KEYS = {'enabled', 'node', 'uuid', 'amount', 'uv_set'}


def validate(value):
    if not isinstance(value, dict) or set(value)-{'color', 'width'}:
        raise ValueError('Brush maps require color and/or width entries')
    result = {}
    for channel, descriptor in value.items():
        if not isinstance(descriptor, dict) or set(descriptor)-_KEYS:
            raise ValueError('Invalid '+channel+' brush map')
        item = dict(enabled=True, node='', uuid='', amount=1., uv_set='')
        item.update(descriptor)
        if not isinstance(item['enabled'], bool):
            raise ValueError('Brush map enabled must be boolean')
        for key in ('node', 'uuid', 'uv_set'):
            if not isinstance(item[key], str) or len(item[key]) > 1024 or any(c in item[key] for c in '\r\n\x00'):
                raise ValueError('Invalid brush map '+key)
        amount = item['amount']
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or not 0 <= amount <= 1:
            raise ValueError('Brush map amount must be between 0 and 1')
        item['amount'] = float(amount)
        result[channel] = item
    return result


def active(descriptor):
    return bool(descriptor and descriptor.get('enabled', True) and descriptor.get('amount', 1.) > 0)


def resolve_node(descriptor, cmds):
    """A renamed texture is recovered by UUID; stale UUID never binds a new node."""
    identity = descriptor.get('uuid', '')
    matches = cmds.ls(identity, long=True) if identity else []
    if not matches and not identity:
        matches = cmds.ls(descriptor.get('node', ''), long=True) if descriptor.get('node') else []
    if len(matches or []) != 1:
        raise ValueError('Brush map texture was deleted or is not connected: '+descriptor.get('node', ''))
    node = matches[0]
    if not cmds.attributeQuery('outColor', node=node, exists=True):
        raise ValueError('Brush map texture requires outColor: '+node)
    return node


def binding(node, cmds, amount=1., uv_set=''):
    if not cmds.objExists(node) or not cmds.attributeQuery('outColor', node=node, exists=True):
        raise ValueError('Select one 2D texture node with outColor')
    return dict(enabled=True, node=node, uuid=(cmds.ls(node, uuid=True) or [''])[0], amount=float(amount), uv_set=uv_set)


def _sample(node, cmds, resolution=RESOLUTION):
    history = cmds.listHistory(node, pruneDagObjects=True) or [node]
    for source in history:
        kind = cmds.nodeType(source)
        if kind in ('projection', 'place3dTexture') or (cmds.getClassification(kind, satisfies='texture/3d')):
            raise ValueError('Brush maps currently support UV-based 2D textures only: '+node)
        if kind == 'file':
            if cmds.attributeQuery('uvTilingMode', node=source, exists=True) and cmds.getAttr(source+'.uvTilingMode'):
                raise ValueError('UDIM brush maps are not supported yet: '+source)
            filename = cmds.getAttr(source+'.fileTextureName') or ''
            if not filename:
                raise ValueError('Brush map file has no image: '+source)
            expanded=cmds.workspace(expandName=os.path.expandvars(filename))
            if not os.path.isfile(expanded):
                raise ValueError('Brush map image was not found: '+expanded)
    axis = (np.arange(resolution, dtype=float)+.5)/resolution
    u, v = np.meshgrid(axis, axis)
    result = np.empty((resolution*resolution, 3), dtype=np.float32)
    for first in range(0, len(result), 4096):
        last = min(first+4096, len(result))
        values = cmds.colorAtPoint(node, output='RGB', u=u.ravel()[first:last].tolist(), v=v.ravel()[first:last].tolist())
        pixels = np.asarray(values, dtype=np.float32)
        if pixels.size != (last-first)*3 or not np.isfinite(pixels).all():
            raise ValueError('Maya could not evaluate the brush texture: '+node)
        result[first:last] = pixels.reshape(-1, 3)
    return dict(pixels=np.clip(result.reshape(resolution, resolution, 3), 0., 1.), repeat=False, uv_domain=[0.,0.,1.,1.],
                source=node, resolution=resolution, sampling='maya-uv-tile')


def freeze_settings_maps(settings, cmds, cache):
    """Return a copy; scene data gets texture IDs, persisted JSON stays untouched."""
    result = dict(settings)
    maps = settings.get('brush_maps', {})
    if maps:
        frozen = copy.deepcopy(maps)
        for channel, descriptor in frozen.items():
            if not active(descriptor):
                continue
            node = resolve_node(descriptor, cmds)
            texture_id = (cmds.ls(node, uuid=True) or [node])[0]
            if texture_id not in cache:
                cache[texture_id] = _sample(node, cmds)
            descriptor['texture_id'] = texture_id
            descriptor['node'] = node
        result['brush_maps'] = frozen
    if settings.get('feature_brushes'):
        result['feature_brushes'] = {key: freeze_settings_maps(value, cmds, cache) for key, value in settings['feature_brushes'].items()}
    if settings.get('hidden_style'):
        result['hidden_style'] = freeze_settings_maps(settings['hidden_style'], cmds, cache)
    return result


def freeze_scene_maps(scene, cmds, cache=None):
    cache = {} if cache is None else cache
    if 'settings' in scene:
        scene['settings'] = freeze_settings_maps(scene['settings'], cmds, cache)
    if scene.get('line_sets'):
        scene['line_sets'] = {key: freeze_settings_maps(value, cmds, cache) for key, value in scene['line_sets'].items()}
    if cache:
        scene['brush_map_textures'] = cache
    return scene


def create_file_texture(path, cmds):
    texture = cmds.shadingNode('file', asTexture=True, name='reaPencilBrushMap')
    placement = cmds.shadingNode('place2dTexture', asUtility=True, name='reaPencilBrushMapUV')
    for attribute in ('coverage', 'translateFrame', 'rotateFrame', 'mirrorU', 'mirrorV', 'stagger', 'wrapU', 'wrapV',
                      'repeatUV', 'offset', 'rotateUV', 'noiseUV', 'vertexUvOne', 'vertexUvTwo', 'vertexUvThree', 'vertexCameraOne'):
        cmds.connectAttr(placement+'.'+attribute, texture+'.'+attribute, force=True)
    cmds.connectAttr(placement+'.outUV', texture+'.uvCoord', force=True)
    cmds.connectAttr(placement+'.outUvFilterSize', texture+'.uvFilterSize', force=True)
    cmds.setAttr(texture+'.fileTextureName', path.replace('\\', '/'), type='string')
    return texture
