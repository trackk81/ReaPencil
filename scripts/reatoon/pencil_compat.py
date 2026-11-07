"""Read-only Pencil+ interface snapshots for RevToon; original nodes stay intact.

Import is a current-frame snapshot, not a live Pencil evaluator. Unsupported
features are reported. No proprietary runtime or licensing logic is included.
"""
import json
import os
import re
from maya import cmds

SNAPSHOT_ATTR = 'revtoonPencilSnapshot'
MANAGED_ATTR = 'revtoonPencilManaged'
SOURCE_ATTR = 'revtoonPencilSourceUuid'
BAKED_SOURCE_ATTR = 'revtoonPencilBakedSourceUuid'
EDGE_KEYS = ('outline', 'open_edges', 'crease', 'material_boundaries',
             'selected_edges', 'wireframe', 'hard_edges', 'intersections',
             'self_intersections', 'hidden_lines')


def _get(node, attr, default=None):
    from . import pencil_unknown
    if pencil_unknown.is_unknown(node):return pencil_unknown.Reader(node).get(attr,default)
    try:
        value = cmds.getAttr(node + '.' + attr)
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], tuple):
            return list(value[0])
        return default if value is None else value
    except (RuntimeError, ValueError):
        return default


def _uuid(node):
    return (cmds.ls(node, uuid=True) or [node])[0]


def _incoming(node, attr):
    from . import pencil_unknown
    if pencil_unknown.is_unknown(node):return pencil_unknown.Reader(node).incoming(attr)
    return cmds.listConnections(node + '.' + attr, source=True, destination=False) or []


def _nodes(kind):
    from . import pencil_unknown
    live=(cmds.ls(type=kind,long=True) or []) if kind in cmds.allNodeTypes() else []
    for unknown in ('unknown','unknownDag','unknownTransform'):
        live.extend(n for n in cmds.ls(type=unknown,long=True) or [] if pencil_unknown.kind(n)==kind)
    return sorted(set(live))


def _indices(node,attr):
    from . import pencil_unknown
    if pencil_unknown.is_unknown(node):return pencil_unknown.Reader(node).indices(attr)
    return cmds.getAttr(node+'.'+attr,multiIndices=True) or []


def _brush_profile(node,prefix,report):
    if not _get(node,prefix+'Enable',False):return 1.,[]
    from .brush_profiles import flat_linear_value,maya_float_profile,profile_table
    from .pencil_unknown import saved_profile_points,is_unknown,Reader
    fields=('CurveType','LeftHandleX','LeftHandleY','ControlPointX','ControlPointY','RightHandleX','RightHandleY')
    rows=[]
    for index in _indices(node,prefix+'BezierControlPoints'):
        path=prefix+'BezierControlPoints[%d].'%index+prefix+'Bezier'
        rows.append([_get(node,path+attr,None) for attr in fields])
    truncated=False
    if is_unknown(node):
        reader=Reader(node)
        for index in reader.indices(prefix+'BezierControlPoints'):
            plug=reader.plug(prefix+'BezierControlPoints[%d]'%index)
            if plug is not None and not plug.isCompound:truncated=True
    if truncated or len(rows)<2 or any(None in row for row in rows):
        rows=saved_profile_points(node,prefix)
        if rows is not None:
            _issue(report,node,prefix+' compound curve recovered as a saved source-file snapshot by node UUID; animation/procedural inputs and later unsaved curve edits are not evaluated')
    try:
        if not rows:raise ValueError('Missing control points')
        rows=maya_float_profile(rows)
        for left,right in zip(rows,rows[1:]):
            if (left[0]!=0 and left[5]<left[3]) or (right[0]!=0 and right[1]>right[3]):
                raise ValueError('handles outside adjacent control points: original runtime evaluation is not verified')
            if left[0]!=0 and right[0]!=0 and left[5]>=right[3] and right[1]<=left[3]:
                # Already-clamped and out-of-span storage render identically in
                # source replay; both must have the same unsupported contract.
                raise ValueError('handles outside adjacent control points or at their opposing limits: paired crossing handles have an unverified singular inverse')
        if any((a[0]!=0 and a[5]>b[3]) or (b[0]!=0 and b[1]<a[3]) for a,b in zip(rows,rows[1:])):
            _issue(report,node,prefix+' out-of-span handle X limited to adjacent knots, preserving handle Y; paired singular crossings and backward-facing handles remain unsupported')
        profile_table(rows)
    except (TypeError,ValueError) as error:
        _issue(report,node,prefix+' curve was not converted: '+str(error));return 1.,[]
    value=flat_linear_value([(r[0],r[3],r[4]) for r in rows])
    if value is not None:return value,[]
    _issue(report,node,prefix+' varying curve imported for CPU raster: stored Linear/Spline/Bezier/Break handles; projected-angle corner links and loop direction imported; irregular/subdivided loop origins and exact directional ties remain approximate; viewport and vector parity remain unverified')
    return 1.,rows


def _flat_brush_profile(node,prefix,report):
    return _brush_profile(node,prefix,report)[0]


def _issue(report, node, feature):
    item = node + ': ' + feature
    if item not in report['unsupported']:
        report['unsupported'].append(item)


def _material(node, report):
    ramp = []
    for index in _indices(node,'gradation'):
        prefix = 'gradation[%d].gradation_' % index
        if not _get(node, prefix + 'On', True):
            continue
        interpolation = int(_get(node, prefix + 'Interp', 0))
        if interpolation not in (0, 1, 2, 3):
            _issue(report, node, 'unknown ramp interpolation; sampled as step')
            interpolation = 0
        ramp.append({'position': max(0., min(1., float(_get(node, prefix + 'Position', 0)))),
                     'color': _get(node, prefix + 'Color', [0.5]*3),
                     'interpolation': interpolation})
        if _get(node, prefix + 'SecondaryColorOn', False) or _get(node, prefix + 'BlendMode', 0) or _get(node, prefix + 'BlendAmount', 1) != 1:
            _issue(report, node, 'gradation secondary color/blending')
    ramp.sort(key=lambda item: item['position'])
    if not ramp:
        _issue(report, node, 'empty/disabled gradation; neutral fallback')
    for attr in ('bumpOn', 'reflectionOn', 'asGradationOffsetOn', 'hSpecularLevel'):
        if _get(node, attr, False):
            _issue(report, node, attr)
    if cmds.listConnections(node, source=True, destination=False):
        _issue(report, node, 'incoming shader networks are sampled at import frame, not reproduced')
    if any(_get(node, 'transparency', [0,0,0])):
        _issue(report, node, 'transparency')
    colors = [r['color'] for r in ramp] or [[.5]*3]
    return {'name': node, 'ramp': ramp, 'color': colors[len(colors)//2],
            'shadow_color': colors[0], 'highlight_color': colors[-1],
            'threshold': .45, 'highlight_threshold': .85, 'gradation_offset': 0., 'opacity': 1.}


def _targets(nodes, report, source):
    result = set()
    pending = list(nodes)
    seen = set()
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        if '.' in node:
            if '.f[' in node or '.e[' in node:
                result.update(cmds.ls(node, long=True, flatten=True) or [])
            else:
                _issue(report, source, 'unsupported component target: ' + node)
            continue
        kind = cmds.nodeType(node)
        if kind == 'objectSet':
            pending.extend(cmds.sets(node, query=True) or [])
        elif kind == 'mesh':
            result.update(cmds.ls(node, long=True) or [])
        elif kind == 'transform':
            result.update(cmds.listRelatives(node, allDescendents=True, type='mesh', fullPath=True) or [])
        else:
            _issue(report, source, 'unsupported target ' + node)
    return sorted(result)


def _material_targets(materials, report, source):
    """Legacy whole-mesh helper; graph import uses live shader connections.

    Partial-face coverage is explicitly skipped rather than widening the style
    to unrelated faces. RevToon currently has one line style per mesh.
    """
    whole, faces = set(), {}
    for material in materials:
        groups = [material] if cmds.nodeType(material) == 'shadingEngine' else cmds.listConnections(material, type='shadingEngine') or []
        for group in set(groups):
            for member in cmds.sets(group, query=True) or []:
                base = member.split('.', 1)[0]
                shapes = cmds.ls(base, long=True) or []
                if shapes and cmds.nodeType(shapes[0]) == 'transform':
                    shapes = cmds.listRelatives(shapes[0], shapes=True, noIntermediate=True, type='mesh', fullPath=True) or []
                shapes = [s for s in shapes if cmds.nodeType(s) == 'mesh']
                if '.' not in member:
                    whole.update(shapes)
                    continue
                match = re.search(r'\.f\[(\d+)(?::(\d+))?\]$', member)
                if not match:
                    _issue(report, source, 'unsupported material component: ' + member)
                    continue
                for shape in shapes:
                    faces.setdefault(shape, set()).update(range(int(match[1]), int(match[2] or match[1])+1))
    for shape, indices in faces.items():
        if shape in whole:
            continue
        count = int(cmds.polyEvaluate(shape, face=True))
        if len(indices) == count and min(indices, default=0) == 0 and max(indices, default=-1) == count-1:
            whole.add(shape)
        else:
            _issue(report, source, 'partial material face target skipped (one style per mesh): ' + shape)
    return sorted(whole)


def _shader_targets(materials, report, source):
    result = []
    # Keep imported material-based line sets attached after the explicit Maya
    # ramp conversion, including a later reimport of the saved Pencil nodes.
    baked={}
    for shader in cmds.ls('*.'+BAKED_SOURCE_ATTR,objectsOnly=True,recursive=True) or []:
        baked.setdefault(cmds.getAttr(shader+'.'+BAKED_SOURCE_ATTR),[]).append(shader)
    for material in materials:
        candidates = _incoming(material, 'surfaceShader') if cmds.nodeType(material) == 'shadingEngine' else [material]
        for node in candidates:
            from . import pencil_unknown
            if cmds.attributeQuery('outColor', node=node, exists=True) or pencil_unknown.kind(node)=='PencilMaterial':
                result.append(node)
                result.extend(baked.get(_uuid(node),[]))
            else:
                _issue(report, source, 'unsupported shader target: ' + node)
    return sorted(set(result))


def _channel_brush(brush,report):
    """Supported independent brush snapshot; unsupported detail stays explicit."""
    value=dict(line_color=_get(brush,'color',[0,0,0]),line_width=max(.1,min(64.,float(_get(brush,'size',1)))),
               line_opacity=float(_get(brush,'blendAmount',1.)),blend_mode=int(_get(brush,'blendMode',0)),brush_key=_uuid(brush))
    if not .1<=float(_get(brush,'size',1))<=64:_issue(report,brush,'Independent brush size clamped to 0.1..64 pixels')
    details=_incoming(brush,'brushDetails')
    if details:
        detail=details[0];scale,curve=_brush_profile(detail,'sr',report)
        value['brush_size_scale']=scale;value['width_profile']=curve
        alpha_scale,value['alpha_profile']=_brush_profile(detail,'sa',report)
        value['line_opacity']*=alpha_scale
        value.update(profile_direction=float(_get(detail,'stDirectionAngle',-30.)),profile_split_angle=float(_get(detail,'stLineSplitAngle',90.)),profile_loop_direction=int(_get(detail,'stLoopDirection',0)),pencil_profile_width=bool(curve or value['alpha_profile']))
        if _get(detail,'stLineType',0)==1:
            value.update(dash_length=float(_get(detail,'stLength',5.)),dash_gap=float(_get(detail,'stSpace',5.)))
            _issue(report,detail,'Independent brush dash length/space imported; connected dash phase remains approximate')
        if _get(detail,'diEnable',False) or _get(detail,'stLineCopy',1)!=1:
            _issue(report,detail,'independent brush distortion/copies are not reproduced')
    if _incoming(brush,'color') or _incoming(brush,'size'):
        _issue(report,brush,'Independent brush texture/procedural inputs sampled at current frame')
    return value


def _constant_reduction(lineset,prefix,channel,report,target=None):
    """Verified Linear snapshot; preserve scalar folds and explicit exclusions."""
    if not _get(lineset,prefix+channel+'ReductionOn',False):return 1.
    nodes=_incoming(lineset,prefix+channel+'Reduction')
    if not nodes:
        _issue(report,lineset,prefix+channel+' reduction enabled without a node; not reproduced');return 1.
    node=nodes[0]
    from . import pencil_unknown
    if pencil_unknown.kind(node)!='PencilReductionSettings':
        _issue(report,node,'Reduction curve on an unknown node is not verified; not reproduced');return 1.
    referenced=bool(_get(node,'rsReferObject',False))
    fields=('CurveType','LeftHandleX','LeftHandleY','ControlPointX','ControlPointY','RightHandleX','RightHandleY')
    rows=[[_get(node,'rsBezierControlPoints[%d].rsBezier'%index+field,None) for field in fields] for index in _indices(node,'rsBezierControlPoints')]
    if pencil_unknown.is_unknown(node):
        rows=pencil_unknown.saved_profile_points(node,'rs')
        if rows is None:
            _issue(report,node,'Saved reduction curve snapshot is unavailable; not reproduced');return 1.
        _issue(report,node,'Reduction curve recovered as a source-file snapshot by UUID; animation/procedural inputs and unsaved edits are not evaluated')
    from .brush_profiles import flat_linear_value
    try:value=flat_linear_value([(r[0],r[3],r[4]) for r in rows]) if rows and all(None not in r for r in rows) else None
    except (TypeError,ValueError):value=None
    flat_non_linear=False
    if value is None and channel in ('alpha','size'):
        from .brush_profiles import flat_reduction_value
        value=flat_reduction_value(rows)
        flat_non_linear=value is not None
    if value is None:
        from .depth_reduction import linear_endpoints,validate
        endpoints=linear_endpoints(rows)
        if target is not None and endpoints is not None:
            try:parameters=validate([_get(node,'rsStart',100.),_get(node,'rsEnd',1000.),*endpoints])
            except ValueError:parameters=[]
            if parameters:
                if referenced:
                    from .depth_reduction import validate_origin
                    references=_incoming(node,'rsObject')
                    paths=cmds.ls(references[0],long=True) if len(references)==1 else []
                    try:
                        if len(paths)!=1 or not cmds.objectType(paths[0],isAType='transform'):raise ValueError('Reference must be one transform')
                        from .line_graph import _reference_world_origin
                        origin=validate_origin(_reference_world_origin(paths[0]))
                    except (RuntimeError,ValueError,TypeError):
                        _issue(report,node,'Unresolved reference origin; distance reduction is not reproduced');return 1.
                    target[('alpha' if channel=='alpha' else 'width')+'_reduction_origin']=origin
                    report.setdefault('reference_bindings',[]).append(dict(source_line_set_uuid=_uuid(lineset),hidden='[1]' in prefix,channel='alpha' if channel=='alpha' else 'width',reference=paths[0]))
                    _issue(report,node,'Reference transform world origin imported with a live message binding and a stored fallback snapshot')
                target['alpha_depth_reduction' if channel=='alpha' else 'width_depth_reduction']=parameters
                _issue(report,node,prefix+channel+' Linear distance reduction imported for native CPU fragments')
                return 1.
        _issue(report,node,'Nonconstant or non-Linear distance reduction is not reproduced');return 1.
    _issue(report,node,prefix+channel+(' exact flat non-Linear reduction imported as an existing CPU multiplier; nonconstant handles are excluded' if flat_non_linear else ' constant Linear reduction imported as an existing CPU multiplier'))
    return value


def inspect_scene():
    """Return a JSON-serializable conversion plan without changing the scene."""
    from . import maya_scene
    report = {'version': 1, 'frame': cmds.currentTime(query=True), 'materials': {},
              'lines': [], 'line_sets': [], 'unsupported': [], 'limitations': [
                  'Current-frame snapshot: reimport after Pencil edits or animation changes.',
                  'Lighting, line width and shading are approximations; pixel parity is not guaranteed.',
                  'Original shading assignments are retained; Pencil viewport requires its runtime.',
                  'Unknown Pencil nodes use saved attributes and observed 4.2.3 defaults; unsupported procedural behavior is not evaluated.'],
              'settings': maya_scene.load_settings()}
    source_settings = _nodes('PencilRenderSetting')
    report['render_settings'] = [{'source':node,'source_uuid':_uuid(node),
                                  'enabled_smooth_mesh':bool(_get(node,'enabledSmoothMesh',False))}
                                 for node in source_settings]
    report['settings']['enabled_smooth_mesh'] = report['render_settings'][0]['enabled_smooth_mesh'] if source_settings else False
    if len({item['enabled_smooth_mesh'] for item in report['render_settings']}) > 1:
        _issue(report,'scene','multiple PencilRenderSetting values disagree; first Maya-listed node is used, matching menu selection')
    for node in _nodes('PencilMaterial'):
        report['materials'][_uuid(node)] = {'source': node, 'material': _material(node, report)}
    lines = sorted(_nodes('PencilLine'), key=lambda n: (_get(n, 'renderPriority', 0), n))
    active = [n for n in lines if _get(n, 'active', True)]
    if lines:
        report['settings'].update({key: False for key in EDGE_KEYS})
    if len({_get(line, 'overSampling', 2) for line in active}) > 1:
        _issue(report, 'scene', 'per-Line oversampling uses one global frame sampling value')
    for line in lines:
        relative_size = int(_get(line, 'lineSize', 1)) == 1
        report['settings']['supersample'] = max(1, min(4, int(_get(line, 'overSampling', 2))))
        report['settings']['seed'] = max(0, int(_get(line, 'randomSeed', 0)))
        report['lines'].append({'source': line, 'source_uuid': _uuid(line), 'output_to_elements_only': bool(_get(line, 'outputToRE', False)), 'active': bool(_get(line, 'active', True)),
                                'priority': int(_get(line, 'renderPriority', 0)),
                                'overrides': {'seed': report['settings']['seed'], 'relative_line_size': relative_size}})
        for index in _indices(line,'lineSets'):
            for node in _incoming(line, 'lineSets[%d]' % index):
                from . import pencil_unknown
                if pencil_unknown.kind(node) != 'PencilLineSet':
                    continue
                visible = 'lineData[0].'
                hidden = 'lineData[1].'
                mapping = {'outline':'edgeOutlineOn','open_edges':'edgeOutlineOpen',
                           'crease':'edgeNormalAngleOn','material_boundaries':'edgeMaterialOn',
                           'wireframe':'edgeWireframeOn','hard_edges':'edgeSmoothOn',
                           'intersections':'edgeIntersectionOn','self_intersections':'edgeSelfIntersection'}
                overrides = {key: bool(_get(node, visible+attr, False)) for key, attr in mapping.items()}
                overrides['open_edges'] &= overrides['outline']
                overrides['self_intersections'] &= overrides['intersections']
                overrides['selected_edges'] = False
                overrides['merge_groups'] = bool(_get(node, visible+'edgeOutlineMergeGroups', False))
                overrides['lineset_id'] = int(_get(node, 'id', 1))
                overrides['hidden_lines'] = any(_get(node, hidden+a, False) for a in mapping.values() if a.endswith('On'))
                overrides['crease_angle_max'] = float(_get(node, visible+'edgeNormalAngleMax', 180))
                overrides['crease_angle'] = float(_get(node, visible+'edgeNormalAngleMin', 40))
                for prefix, color_key in ((visible,'line_color'), (hidden,'hidden_color')):
                    brushes = _incoming(node, prefix+'brushSettings')
                    if brushes:
                        brush = brushes[0]
                        alpha_scale=1.
                        overrides[color_key] = _get(brush, 'color', [0,0,0])
                        if cmds.listConnections(brush,source=True,destination=False):
                            _issue(report,node,'brush maps/detail/animated inputs sampled or ignored')
                        if prefix == visible:
                            if not .1 <= float(_get(brush,'size',1)) <= 64:
                                _issue(report,node,'brush size clamped to 0.1..64 pixels')
                            overrides['line_width'] = max(.1, min(64., float(_get(brush, 'size', 1))))
                            details = _incoming(brush, 'brushDetails')
                            if details:
                                overrides['brush_size_scale'],overrides['width_profile']=_brush_profile(details[0],'sr',report)
                                alpha_scale,overrides['alpha_profile']=_brush_profile(details[0],'sa',report)
                                overrides['profile_direction']=float(_get(details[0],'stDirectionAngle',-30.))
                                overrides['profile_split_angle']=float(_get(details[0],'stLineSplitAngle',90.))
                                overrides['profile_loop_direction']=int(_get(details[0],'stLoopDirection',0))
                                overrides['pencil_profile_width']=bool(overrides['width_profile'] or overrides['alpha_profile'])
                            if details and _get(details[0], 'stLineType', 0) == 1:
                                detail = details[0]
                                overrides['dash_length'] = float(_get(detail, 'stLength', 5.))
                                overrides['dash_gap'] = float(_get(detail, 'stSpace', 5.))
                                # Only the zero split-angle fixture currently
                                # supports this partial connection mapping.
                                # Other source angles keep their prior output
                                # until corner/loop phase is implemented.
                                overrides['connect_collinear_dashes'] = float(_get(detail, 'stLineSplitAngle', 90.)) == 0.
                                _issue(report, detail, 'CPU dash length/space and collinear polygon connections imported; corner/loop phase, split-angle behavior, randomization and viewport parity are not reproduced')
                        if prefix==visible:
                            overrides['line_opacity']=float(_get(brush,'blendAmount',1.))*alpha_scale
                            overrides['blend_mode']=int(_get(brush,'blendMode',0))
                            overrides['brush_key']=_uuid(brush)
                if overrides['hidden_lines']:
                    h={key:bool(_get(node,hidden+attr,False)) for key,attr in mapping.items()}
                    h['open_edges'] &= h['outline'];h['self_intersections'] &= h['intersections']
                    h.update(selected_edges=False,crease_angle=float(_get(node,hidden+'edgeNormalAngleMin',40)),
                             crease_angle_max=float(_get(node,hidden+'edgeNormalAngleMax',180)),
                             merge_groups=bool(_get(node,hidden+'edgeOutlineMergeGroups',False)))
                    brushes=_incoming(node,hidden+'brushSettings')
                    if brushes:h.update(_channel_brush(brushes[0],report))
                    overrides['hidden_style']=h
                specific_types={'Outline':'outline','Intersection':'intersection','Smooth':'hard',
                                'Material':'material','Selected':'selected','NormalAngle':'crease','Wireframe':'wireframe'}
                for prefix in (visible,hidden):
                    target=overrides if prefix==visible else overrides.get('hidden_style',{})
                    specifics={}
                    for source,feature in specific_types.items():
                        if not _get(node,prefix+'edgeSpecific'+source+'On',False):continue
                        brushes=_incoming(node,prefix+'edge'+source)
                        if brushes:specifics[feature]=_channel_brush(brushes[0],report)
                        else:_issue(report,node,prefix+'edge'+source+': enabled brush has no connection; base brush is used')
                    if specifics:target['feature_brushes']=specifics
                    for channel,key in (('size','brush_size_scale'),('alpha','line_opacity')):
                        factor=_constant_reduction(node,prefix,channel,report,target)
                        if factor!=1.:
                            for brush in [target,*specifics.values()]:brush[key]=float(brush.get(key,1.))*factor
                    for attr in ('edgeObjectOn','edgeSelectedOn','edgeSpecificObjectOn'):
                        if _get(node,prefix+attr,False):_issue(report,node,prefix+attr+' is not reproduced')
                targets = _targets(_incoming(node,'objects'),report,node)
                report['line_sets'].append({'source':node,'source_uuid':_uuid(node),'line':line,
                                           'active': bool(_get(node, 'on', True)),
                                           'members':targets,'shaders':_shader_targets(_incoming(node, 'materials'), report, node), 'overrides':overrides})
    _inspect_extras(report)
    from . import pencil_unknown
    unknown=[n for kind in pencil_unknown.SCHEMA for n in _nodes(kind) if pencil_unknown.is_unknown(n)]
    report['runtime_missing']=bool(unknown)
    report['recovered_unknown_nodes']=unknown
    if unknown:
        report['limitations'].append('Default values not serialized by Maya are reconstructed using Pencil+ '+pencil_unknown.REFERENCE_VERSION+' attribute metadata.')
    report['status'] = 'ready' if lines or report['materials'] or report['merge_groups'] or report['elements'] or report['render_settings'] else 'no_pencil_nodes'
    return report



def _mark_source(node,key):
    if not cmds.attributeQuery(MANAGED_ATTR,node=node,exists=True):
        cmds.addAttr(node,longName=MANAGED_ATTR,attributeType='bool',defaultValue=True)
    if not cmds.attributeQuery(SOURCE_ATTR,node=node,exists=True):
        cmds.addAttr(node,longName=SOURCE_ATTR,dataType='string')
    cmds.setAttr(node+'.'+MANAGED_ATTR,True)
    cmds.setAttr(node+'.'+SOURCE_ATTR,key,type='string')


def import_scene():
    """Create owned settings/line-set snapshots; never rewrite Pencil nodes or SGs."""
    from . import maya_scene, line_graph
    report = inspect_scene()
    if report['status'] == 'no_pencil_nodes':
        return report
    maya_scene.validate_settings(report['settings'])
    for item in report['line_sets']:
        maya_scene.validate_settings(item['overrides'], partial=True)
    from . import render_elements
    for item in report.get('elements',[]):
        render_elements.validate(item['settings'])
    selection = cmds.ls(selection=True, long=True) or []
    cmds.undoInfo(openChunk=True, chunkName='Import Pencil snapshot into RevToon')
    try:
        managed = [n for n in cmds.ls('*.'+MANAGED_ATTR,objectsOnly=True,recursive=True) or []
                   if cmds.getAttr(n+'.'+MANAGED_ATTR)]
        by_key = {cmds.getAttr(n+'.'+SOURCE_ATTR):n for n in managed
                  if cmds.attributeQuery(SOURCE_ATTR,node=n,exists=True)}
        legacy_lines = [n for n in managed if cmds.nodeType(n)=='revToonLine'
                        and not cmds.attributeQuery(SOURCE_ATTR,node=n,exists=True)]
        lines = {}
        report['created_lines'], report['updated_lines'] = [], []
        report['created_line_sets'], report['updated_line_sets'] = [], []
        for item in report['lines']:
            key = 'line:'+item['source_uuid']
            node = by_key.get(key)
            if node is None and legacy_lines:
                node = legacy_lines.pop(0)
            if node is None:
                node = line_graph.create_line('revtoonPencilLine')
                report['created_lines'].append(node)
            else:
                report['updated_lines'].append(node)
            _mark_source(node,key)
            line_graph.set_active(node,item['active'])
            line_graph.set_priority(node,item['priority'])
            line_graph.set_settings(node,item['overrides'])
            if cmds.attributeQuery('outputToRE',node=node,exists=True):
                cmds.setAttr(node+'.outputToRE',item['output_to_elements_only'])
            lines[item['source']] = node
        ordered = {node:[] for node in lines.values()}
        for index,item in enumerate(report['line_sets']):
            parent = lines[item['line']]
            parent_key = cmds.getAttr(parent+'.'+SOURCE_ATTR)
            key = parent_key+':set:'+item['source_uuid']
            node = by_key.get(key)
            if node is None:
                legacy = [n for n in line_graph.list_sets(parent) if n in managed
                          and not cmds.attributeQuery(SOURCE_ATTR,node=n,exists=True)]
                node = legacy[0] if legacy else None
            if node is None:
                node = line_graph.create_line_set(parent,name='revtoonPencilLineSet_%06d'%index,
                                                 overrides=item['overrides'],position=None)
                report['created_line_sets'].append(node)
            else:
                report['updated_line_sets'].append(node)
            _mark_source(node,key)
            line_graph.set_settings(node,item['overrides'])
            bindings={(b['hidden'],b['channel']):b['reference'] for b in report.get('reference_bindings',[]) if b['source_line_set_uuid']==item['source_uuid']}
            for hidden in (False,True):
                for channel in ('alpha','width'):
                    reference=bindings.get((hidden,channel))
                    channel_settings=item['overrides'].get('hidden_style',{}) if hidden else item['overrides']
                    if reference and channel_settings.get(channel+'_depth_reduction'):line_graph.bind_reduction_reference(node,channel,reference,hidden)
                    else:line_graph.clear_reduction_reference(node,channel,hidden)
            line_graph.set_active(node,item['active'])
            targets = line_graph.get_targets(node)
            line_graph.remove_targets(node,targets['objects'])
            line_graph.remove_targets(node,targets['shaders'],kind='shaders')
            line_graph.add_targets(node,item['members'])
            line_graph.add_targets(node,item['shaders'],kind='shaders')
            ordered[parent].append(node)
        for parent, imported in ordered.items():
            remaining = [n for n in line_graph.list_sets(parent) if n not in imported]
            for node in remaining:
                if node in managed:
                    line_graph.set_active(node,False)
                    _issue(report,node,'source LineSet no longer connected; retained inactive')
            line_graph.reorder_sets(parent,imported+remaining)
        for node in managed:
            if cmds.nodeType(node)=='revToonLine' and node not in lines.values():
                line_graph.set_active(node,False)
                _issue(report,node,'source Line no longer present; retained inactive')
        _import_extras(report, by_key)
        snapshots = cmds.ls('*.'+SNAPSHOT_ATTR,objectsOnly=True,recursive=True) or []
        snapshot = snapshots[0] if snapshots else cmds.createNode('network', name='revtoonPencilCompatibility')
        maya_scene._json_attr(snapshot,SNAPSHOT_ATTR,{'version':1,'frame':report['frame'],'materials':report['materials']})
        maya_scene.save_settings(report['settings'])
        report['snapshot_node'] = snapshot
        report['status'] = 'imported'
    except Exception:
        cmds.undoInfo(closeChunk=True)
        if cmds.undoInfo(query=True,state=True):
            cmds.undo()
        raise
    else:
        cmds.undoInfo(closeChunk=True)
    finally:
        cmds.select(selection,replace=True) if selection else cmds.select(clear=True)
    return report


def material_override(node, warnings=None):
    """Cheap ordinary-material fast path; UUID survives source shader renames."""
    if node and cmds.attributeQuery('revtoonPencilBakedMaterial',node=node,exists=True):
        return json.loads(cmds.getAttr(node+'.revtoonPencilBakedMaterial'))
    if not node or cmds.nodeType(node) not in ('PencilMaterial', 'unknown', 'unknownDag'):
        return None
    uid = _uuid(node)
    for snapshot in cmds.ls('*.'+SNAPSHOT_ATTR,objectsOnly=True,recursive=True) or []:
        data = json.loads(cmds.getAttr(snapshot+'.'+SNAPSHOT_ATTR) or '{}')
        entry = data.get('materials',{}).get(uid)
        if entry:
            return dict(entry['material'])
    if warnings is not None:
        message = node + ': Pencil material has no RevToon snapshot; run Import Pencil first.'
        if message not in warnings:
            warnings.append(message)
    return None



def bake_materials():
    """Explicit opt-in: assign standard Maya rampShaders, preserving source nodes.

    Whole-object and per-face memberships are moved exactly as queried. Repeating
    the operation is a no-op once source shading groups no longer have members.
    """
    from . import maya_scene,line_graph
    plans = []
    for sg in cmds.ls(type='shadingEngine') or []:
        source = _incoming(sg, 'surfaceShader')
        if not source or cmds.attributeQuery('revtoonPencilBakedMaterial',node=source[0],exists=True):
            continue
        material = material_override(source[0])
        members = cmds.sets(sg,query=True) or []
        if material and members:
            plans.append((sg,source[0],members,material))
    result = {'status':'baked' if plans else 'no_pending_materials','materials':[],
              'limitations':['Standard Maya rampShader viewport is an approximation.',
                             'Original Pencil nodes remain; save a copy before removing original dependencies.']}
    selection = cmds.ls(selection=True,long=True) or []
    cmds.undoInfo(openChunk=True,chunkName='Bake Pencil snapshots to Maya ramp shaders')
    try:
        for sg,source,members,material in plans:
            shader=cmds.shadingNode('rampShader',asShader=True,name='revtoonPencilRamp')
            for index in cmds.getAttr(shader+'.color',multiIndices=True) or []:
                cmds.removeMultiInstance(shader+'.color[%d]' % index,b=True)
            for index,entry in enumerate(material.get('ramp') or [{'position':0.,'color':material['color'],'interpolation':0}]):
                prefix=shader+'.color[%d].color_' % index
                cmds.setAttr(prefix+'Position',entry['position'])
                cmds.setAttr(prefix+'Color',*entry['color'],type='double3')
                cmds.setAttr(prefix+'Interp',entry['interpolation'])
            maya_scene._json_attr(shader,'revtoonPencilBakedMaterial',material)
            cmds.addAttr(shader,longName=BAKED_SOURCE_ATTR,dataType='string')
            cmds.setAttr(shader+'.'+BAKED_SOURCE_ATTR,_uuid(source),type='string')
            target=cmds.sets(renderable=True,noSurfaceShader=True,empty=True,name='revtoonPencilRampSG')
            cmds.connectAttr(shader+'.outColor',target+'.surfaceShader')
            cmds.sets(members,edit=True,forceElement=target)
            for line_set in cmds.ls(type=line_graph.LineSetNode.TYPE) or []:
                if source in line_graph.get_targets(line_set)['shaders']:
                    line_graph.add_targets(line_set,[shader],kind='shaders')
            result['materials'].append({'source':source,'source_sg':sg,'shader':shader,'shading_group':target,'members':members})
    except Exception:
        cmds.undoInfo(closeChunk=True)
        if cmds.undoInfo(query=True,state=True):
            cmds.undo()
        raise
    else:
        cmds.undoInfo(closeChunk=True)
    finally:
        cmds.select(selection,replace=True) if selection else cmds.select(clear=True)
    return result



def _inspect_extras(report):
    report['merge_groups'] = []
    for node in cmds.ls('*.PencilMergeGroupTarget',objectsOnly=True,recursive=True) or []:
        if cmds.nodeType(node) not in ('transform','objectSet'):
            _issue(report,node,'unsupported merge group target type')
            continue
        report['merge_groups'].append({'source':node,'source_uuid':_uuid(node),'targets':[node]})
    report['elements'] = []
    edge_map = {'edgeOutline':'outline','edgeObject':None,'edgeIntersection':'intersection',
                'edgeSmoothingBoundary':'hard','edgeMaterialBoundary':'material',
                'edgeSelectedEdges':'selected','edgeNormalAngle':'crease','edgeWireframe':'wireframe'}
    for original,kind in [('PencilRenderElementsLine','line'),('PencilRenderElementsEps','eps'),('PencilRenderElementsPld','pld')]:
        for node in _nodes(original):
            settings={'active':bool(_get(node,'on',True)),'kind':kind,
                      'visible_lines':bool(_get(node,'visibleLines',True)),
                      'hidden_lines':bool(_get(node,'hiddenLines',True)),
                      'edge_types':[mapped for attr,mapped in edge_map.items() if mapped and _get(node,attr,True)],
                      'lineset_ids':[i for i in range(1,9) if _get(node,'linesetId%d'%i,True)],
                      'output_path_type':'custom' if _get(node,'outputPathType',0) else 'scene',
                      'output_file_name':str(_get(node,'outputFileName','<Scene>')),
                      'separate_folders':bool(_get(node,'separateFolders',True)),
                      'separator':['_','-','.'][max(0,min(2,int(_get(node,'separator',0))))]}
            if _get(node,'edgeOutline',True):
                settings['edge_types'].append('open')
            if settings['output_path_type']=='custom':
                folder,base=os.path.split(settings['output_file_name'])
                if folder:
                    settings['output_path']=folder
                    settings['output_file_name']=base
            if kind=='line':
                settings.update(output_element=['color','depth','velocity'][max(0,min(2,int(_get(node,'outputElement',0))))],
                                z_min=float(_get(node,'zMin',100)),z_max=float(_get(node,'zMax',300)),
                                max_velocity=float(_get(node,'maxVelocity',50)),
                                bg_color_enable=bool(_get(node,'bgColorEnable',False)),
                                bg_color=_get(node,'bgColor',[1,1,1]))
                if settings['output_element']=='velocity':
                    _issue(report,node,'Velocity element metadata preserved; motion-vector output unsupported')
            if kind=='eps':
                settings['file_type']='eps' if _get(node,'fileType',0) else 'ai_eps'
                if settings['file_type']=='ai_eps':
                    _issue(report,node,'Illustrator-specific EPS compatibility is not guaranteed')
            if kind=='pld':
                _issue(report,node,'PLD element metadata preserved; proprietary PLD encoding unsupported')
            if _get(node,'edgeObject',True):
                _issue(report,node,'Object edge classification has no exact RevToon equivalent')
            report['elements'].append({'source':node,'source_uuid':_uuid(node),'settings':settings})


def _import_extras(report,by_key):
    from . import line_graph,render_elements
    report['imported_merge_groups'], report['imported_elements'] = [], []
    for item in report.get('merge_groups',[]):
        key='merge:'+item['source_uuid']
        node=by_key.get(key)
        if node is None:
            node=line_graph.create_merge_group(name='revtoonPencilMergeGroup',targets=item['targets'])
        else:
            line_graph.remove_merge_targets(node,line_graph.get_merge_targets(node))
            line_graph.add_merge_targets(node,item['targets'])
        _mark_source(node,key)
        report['imported_merge_groups'].append(node)
    for item in report.get('elements',[]):
        key='element:'+item['source_uuid']
        node=by_key.get(key)
        if node is None:
            node=render_elements.create(kind=item['settings']['kind'],name='revtoonPencilElement')
        render_elements.set(node,item['settings'])
        _mark_source(node,key)
        report['imported_elements'].append(node)
