"""Scoped scene actions for the ReaPencil Maya menu.

Cleanup removes owned graph containers only, never their geometry or shaders.
"""
from .i18n import tr
import json
from maya import cmds, mel
from . import maya_scene, line_graph

OWNED_TARGET_ATTRIBUTE = 'revToonGraphOwned'


def _editable(node):
    return not cmds.referenceQuery(node, isNodeReferenced=True) and not any(cmds.lockNode(node, query=True, lock=True) or [])


def add_selected_edges(line=None):
    """Create a selected-edge LineSet, optionally under a supplied Line node."""
    selection = cmds.ls(selection=True, long=True, flatten=True) or []
    edges = cmds.filterExpand(selection, selectionMask=32, expand=True, fullPath=True) or []
    if not edges or len(edges) != len(selection):
        raise ValueError('폴리곤 에지만 선택하세요. 선택 에지를 새 라인셋에 저장합니다.')
    if line is not None and (not cmds.objExists(line) or cmds.nodeType(line) != line_graph.LineNode.TYPE):
        raise ValueError('The parent must be a ReaPencil Line node.')
    registered = cmds.allNodeTypes()
    if line_graph.LineNode.TYPE not in registered or line_graph.LineSetNode.TYPE not in registered:
        raise RuntimeError('ReaPencil graph nodes are not registered. Load the updated ReaPencil plugin first.')
    created = []
    cmds.undoInfo(openChunk=True, chunkName='ReaPencil selected edges')
    try:
        if line is None:
            line = line_graph.create_line(name='revToonSelectedEdgesLine')
            created.append(line)
        settings = {key: False for key in ('outline','open_edges','crease','material_boundaries',
                                          'hard_edges','wireframe','intersections','self_intersections','hidden_lines')}
        settings['selected_edges'] = True
        node = line_graph.create_line_set(line, name='revToonSelectedEdges', overrides=settings)
        created.append(node)
        line_graph.add_targets(node, edges, kind='objects')
    except Exception:
        cmds.undoInfo(closeChunk=True)
        if cmds.undoInfo(query=True, state=True):
            cmds.undo()
        raise
    else:
        cmds.undoInfo(closeChunk=True)
    finally:
        cmds.select(selection, replace=True)
    return {'line':line, 'line_set':node, 'edge_count':len(edges), 'created':created}


def add_render_settings():
    """Create/reuse scene settings, enable Smooth Mesh, and open its AE."""
    node = maya_scene.settings_node(create=True)
    cmds.setAttr(node+'.enabledSmoothMesh',True)
    if not cmds.about(batch=True):
        cmds.select(node,replace=True)
        mel.eval('showEditor ' + json.dumps(node) + ';')
    return node


def import_pencil_scene():
    """Explicit conversion entry point; original Pencil+ nodes remain intact."""
    from . import pencil_compat, line_editor
    report = pencil_compat.import_scene()
    if not cmds.about(batch=True):
        line_editor.show()
        imported=report.get('created_lines',[])+report.get('updated_lines',[])
        first=next((n for n in imported if cmds.objExists(n)),None)
        line_editor.refresh(first)
        if first:
            line_editor._open(first)
        window='revToonMigrationReport'
        if cmds.window(window,exists=True):
            cmds.deleteUI(window)
        cmds.window(window,title=tr('Pencil+ → ReaPencil 가져오기 결과'),widthHeight=(650,360))
        cmds.columnLayout(adjustableColumn=True)
        if report.get('status')=='no_pencil_nodes':
            summary='현재 장면에 Pencil+ 노드가 없습니다. Pencil+ 장면을 연 뒤 다시 실행하세요.'
        else:
            summary='Line: 새로 생성 %d / 갱신 %d\nLine Set: 새로 생성 %d / 갱신 %d' % (
                len(report.get('created_lines',[])),len(report.get('updated_lines',[])),
                len(report.get('created_line_sets',[])),len(report.get('updated_line_sets',[])))
        cmds.text(label=tr(summary),align='left',wordWrap=True,height=50)
        if report.get('runtime_missing'):
            cmds.text(label=tr('Pencil+ 없이 저장 데이터에서 %d개 노드를 읽었습니다.\n저장되지 않은 기본값은 Pencil+ 4.2.3 기준으로 복원합니다.' %
                      len(report.get('recovered_unknown_nodes',[]))),align='left',wordWrap=True,height=45)
        cmds.text(label=tr('원본 Pencil+ 노드와 기존 셰이더 연결은 유지됩니다.'),align='left',height=25)
        unsupported=report.get('unsupported',[])
        cmds.text(label=tr('미지원·확인 필요 항목: %d개 (상세 결과에서 확인)' % len(unsupported)),align='left',height=25)
        def edit_imported(*_):
            cmds.deleteUI(window)
            line_editor._open(first)
        cmds.button(label=tr('이전된 Line 편집'),enable=bool(first),command=edit_imported)
        cmds.frameLayout(label=tr('상세 결과 / 미지원 항목'),collapsable=True,collapse=True)
        cmds.scrollField(editable=False,wordWrap=True,text=json.dumps(report,ensure_ascii=False,indent=2),height=260)
        cmds.showWindow(window)
    return report



def _container_users(node):
    pairs = cmds.listConnections(node, source=False, destination=True,
                                 plugs=True, connections=True) or []
    users = []
    for source, destination in zip(pairs[::2], pairs[1::2]):
        # Maya adds this display-color link for component set membership.
        # Deleting the set only disconnects it; the target geometry survives.
        if source.endswith('.memberWireframeColor') and destination.endswith('.objectGrpColor'):
            continue
        users.append(destination)
    return users


def delete_unused():
    """Delete disconnected owned containers; keep empty Lines and all targets.

    A LineSet with any outgoing dependency is retained. An objectSet must have
    the explicit graph ownership marker and no outgoing dependency. Names are
    never treated as proof of ownership. Referenced/locked nodes are retained.
    """
    report = {'deleted':[], 'retained':[], 'scope':'orphan ReaPencil LineSets and explicitly owned target objectSets only'}
    selection = cmds.ls(selection=True, long=True) or []
    with maya_scene.undo_chunk('Delete unused ReaPencil containers'):
        for node in cmds.ls(type=line_graph.LineSetNode.TYPE) or []:
            if not _editable(node) or cmds.listConnections(node, source=False, destination=True):
                report['retained'].append(node)
                continue
            # Maya can cascade-delete connected message-source containers.
            # Detach reference links before deleting the orphan LineSet itself.
            for attr in ('objectTargets', 'shaderTargets'):
                pairs = cmds.listConnections(node+'.'+attr, source=True, destination=False,
                                             plugs=True, connections=True) or []
                for destination, source in zip(pairs[::2], pairs[1::2]):
                    cmds.disconnectAttr(source, destination)
            cmds.delete(node)
            report['deleted'].append(node)
        for node in cmds.ls(type='objectSet') or []:
            if not cmds.attributeQuery(OWNED_TARGET_ATTRIBUTE, node=node, exists=True):
                continue
            if not cmds.getAttr(node+'.'+OWNED_TARGET_ATTRIBUTE):
                continue
            if not _editable(node) or _container_users(node):
                report['retained'].append(node)
                continue
            cmds.delete(node)
            report['deleted'].append(node)
    surviving = [node for node in selection if cmds.objExists(node)]
    cmds.select(surviving, replace=True) if surviving else cmds.select(clear=True)
    return report
