"""Compatibility bridge for old scene requires and existing Auto load settings."""
import os
from maya import cmds,utils
from maya.api import OpenMaya as om

def maya_useNewAPI():pass

def initializePlugin(plugin):
    path=globals().get('__file__',(lambda:None).__code__.co_filename)
    canonical=os.path.join(os.path.dirname(os.path.abspath(path)),'reaPencil.py')
    cmds.loadPlugin(canonical,quiet=True)
    from reatoon import __version__
    om.MFnPlugin(plugin,'ReaPencil compatibility bridge',__version__,'Any')
    if not cmds.about(batch=True):
        from reatoon.plugin_migration import migrate_autoload
        utils.executeDeferred(migrate_autoload)

def uninitializePlugin(plugin):pass
