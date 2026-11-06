"""Explicit launcher for the installed ReaPencil package.

launch(trust_install=True) trusts only this installation's plug-ins directory.
It does not disable Maya security or edit user preference files on disk.
"""
import json
from pathlib import Path


def launch(trust_install=False):
    from maya import cmds
    root = Path(__file__).resolve().parent.parent
    marker = root / 'reatoon-install.json'
    plugin = root / 'plug-ins' / 'reaPencil.py'
    if not marker.is_file() or not plugin.is_file():
        raise RuntimeError('Run tools/install.py first; launch from the installed Maya module.')
    metadata = json.loads(marker.read_text(encoding='utf-8'))
    if metadata.get('product') != 'ReaToon' or 'plug-ins/reaPencil.py' not in metadata.get('files', []):
        raise RuntimeError('This directory is not a recognized ReaPencil installation.')
    loaded_plugins=[Path(name).stem for name in cmds.pluginInfo(query=True,listPlugins=True) or []]
    for name in ('reaPencil','reaToon'):
        if name in loaded_plugins:
            active_version=cmds.pluginInfo(name,query=True,version=True)
            if active_version!=metadata.get('version'):
                raise RuntimeError('ReaPencil '+active_version+' is still loaded; installed version is '+str(metadata.get('version'))+
                                   '. Save your scene and restart Maya to activate the new UI and node types.')
    if trust_install:
        key = 'SafeModeAllowedlistPaths'
        existing = cmds.optionVar(query=key) if cmds.optionVar(exists=key) else []
        if isinstance(existing, str):
            existing = [existing]
        folder = plugin.parent.as_posix()
        normalized = {str(value).replace('\\', '/').rstrip('/').casefold() for value in existing or []}
        if folder.casefold() not in normalized:
            cmds.optionVar(stringValueAppend=(key, folder))
            updated = cmds.optionVar(query=key) if cmds.optionVar(exists=key) else []
            if isinstance(updated, str):
                updated = [updated]
            if folder.casefold() not in {str(value).replace('\\', '/').rstrip('/').casefold() for value in updated or []}:
                raise RuntimeError('Maya did not approve this trusted location. No plug-in was loaded. '
                                   'Use Preferences > Security > Plugins to trust only: ' + folder)
            print('ReaPencil: added this plug-in location to Maya trusted paths: ' + folder)
    loaded = cmds.loadPlugin(plugin.as_posix(), quiet=True)
    if not hasattr(cmds, 'revToonImportPencil'):
        raise RuntimeError('An older ReaPencil version is already loaded. Save your scene and restart Maya.')
    cmds.revToonUI()
    if 'reaToon' in loaded_plugins:
        from reatoon.plugin_migration import migrate_autoload
        migrate_autoload()
    return loaded
