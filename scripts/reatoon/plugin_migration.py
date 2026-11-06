"""Carry an existing user's Auto load choice to the new entry point."""
def migrate_autoload():
    from maya import cmds
    if cmds.pluginInfo('reaToon',query=True,autoload=True):
        cmds.pluginInfo('reaPencil',edit=True,autoload=True)
        cmds.pluginInfo('reaToon',edit=True,autoload=False)
        cmds.pluginInfo(savePluginPrefs=True)
