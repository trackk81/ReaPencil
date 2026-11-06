"""ReaPencil Maya command plug-in. Legacy reaToon commands remain compatible."""
import json
import os
import sys
from maya import cmds
from maya.api import OpenMaya as om

def maya_useNewAPI():
    pass

class RenderCommand(om.MPxCommand):
    @staticmethod
    def creator():
        return RenderCommand()
    @staticmethod
    def syntax_creator():
        syntax = om.MSyntax()
        syntax.addFlag('-c', '-camera', om.MSyntax.kString)
        syntax.addFlag('-o', '-output', om.MSyntax.kString)
        syntax.addFlag('-w', '-width', om.MSyntax.kLong)
        syntax.addFlag('-h', '-height', om.MSyntax.kLong)
        return syntax
    def doIt(self, args):
        from reatoon import maya_scene, render_integration
        parser = om.MArgDatabase(self.syntax(), args)
        camera = parser.flagArgumentString('-camera', 0) if parser.isFlagSet('-camera') else None
        if not parser.isFlagSet('-output'):
            width = parser.flagArgumentInt('-width', 0) if parser.isFlagSet('-width') else None
            height = parser.flagArgumentInt('-height', 0) if parser.isFlagSet('-height') else None
            result = render_integration.render_current(camera=camera, width=width, height=height)
        else:
            values = maya_scene.load_settings()
            for flag in ('width', 'height'):
                if parser.isFlagSet('-' + flag):
                    values[flag] = parser.flagArgumentInt('-' + flag, 0)
            result = maya_scene.render_scene(parser.flagArgumentString('-output', 0), camera, values)
        self.setResult(json.dumps(result, ensure_ascii=True))

class UICommand(om.MPxCommand):
    @staticmethod
    def creator():
        return UICommand()
    def doIt(self, args):
        if cmds.about(batch=True):
            raise RuntimeError('ReaPencil UI requires interactive Maya.')
        from reatoon import ui
        ui.show()

class ViewportCommand(om.MPxCommand):
    @staticmethod
    def creator():
        return ViewportCommand()
    @staticmethod
    def syntax_creator():
        syntax = om.MSyntax()
        syntax.addFlag('-en', '-enabled', om.MSyntax.kBoolean)
        syntax.addFlag('-st', '-status')
        return syntax
    def doIt(self, args):
        from reatoon import viewport
        parser = om.MArgDatabase(self.syntax(), args)
        if not parser.isFlagSet('-status'):
            enabled = parser.flagArgumentBool('-enabled', 0) if parser.isFlagSet('-enabled') else True
            viewport.enable() if enabled else viewport.disable()
        self.setResult(json.dumps(viewport.status(), ensure_ascii=True))

class PencilImportCommand(om.MPxCommand):
    @staticmethod
    def creator():
        return PencilImportCommand()
    @staticmethod
    def syntax_creator():
        syntax = om.MSyntax()
        syntax.addFlag('-dr', '-dryRun')
        syntax.addFlag('-bm', '-bakeMaterials')
        return syntax
    def doIt(self, args):
        from reatoon import pencil_compat
        parser = om.MArgDatabase(self.syntax(), args)
        if parser.isFlagSet('-dryRun') and parser.isFlagSet('-bakeMaterials'):
            raise ValueError('Choose dryRun or bakeMaterials, not both.')
        if parser.isFlagSet('-bakeMaterials'):
            result = pencil_compat.bake_materials()
        else:
            result = pencil_compat.inspect_scene() if parser.isFlagSet('-dryRun') else pencil_compat.import_scene()
        self.setResult(json.dumps(result, ensure_ascii=True))

_COMMANDS = [
    ('reaPencilRender', RenderCommand.creator, RenderCommand.syntax_creator),
    ('reaPencilUI', UICommand.creator, None),
    ('reaPencilViewport', ViewportCommand.creator, ViewportCommand.syntax_creator),
    ('reaPencilImportPencil', PencilImportCommand.creator, PencilImportCommand.syntax_creator),
    ('reaToonRender', RenderCommand.creator, RenderCommand.syntax_creator),
    ('revToonRender', RenderCommand.creator, RenderCommand.syntax_creator),
    ('reaToonUI', UICommand.creator, None),
    ('revToonUI', UICommand.creator, None),
    ('revToonViewport', ViewportCommand.creator, ViewportCommand.syntax_creator),
    ('revToonImportPencil', PencilImportCommand.creator, PencilImportCommand.syntax_creator),
]

def initializePlugin(plugin):
    from reatoon import viewport, render_integration, line_graph
    from . import __version__
    fn = om.MFnPlugin(plugin, 'ReaPencil independent project', __version__, 'Any')
    registered = []
    viewport_registered = False
    graph_registered = False
    try:
        for name, creator, syntax in _COMMANDS:
            if syntax:
                fn.registerCommand(name, creator, syntax)
            else:
                fn.registerCommand(name, creator)
            registered.append(name)
        line_graph.register(fn)
        graph_registered=True
        viewport.register(fn)
        viewport_registered = True
        render_integration.register()
    except Exception:
        try:
            render_integration.unregister()
        except Exception:
            pass
        if viewport_registered:
            viewport.unregister(fn)
        if graph_registered:
            line_graph.unregister(fn)
        for name in reversed(registered):
            fn.deregisterCommand(name)
        raise
    if not cmds.about(batch=True):
        from maya import utils
        from reatoon import ui
        utils.executeDeferred(ui.install_menu)

def uninitializePlugin(plugin):
    from reatoon import viewport, render_integration, line_graph
    if not cmds.about(batch=True):
        from reatoon import ui
        ui.close()
        ui.remove_menu()
        updater=sys.modules.get('reatoon.update_ui')
        if updater is not None:updater.close()
    from . import preview_renderers
    preview_renderers.unregister()
    render_integration.unregister()
    fn = om.MFnPlugin(plugin)
    viewport.unregister(fn)
    line_graph.unregister(fn)
    for name, _, _ in reversed(_COMMANDS):
        fn.deregisterCommand(name)
