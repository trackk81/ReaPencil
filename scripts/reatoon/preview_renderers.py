"""Panel-local Maya Renderer menu entries for precise and fast previews."""
from maya import cmds,utils,mel
from maya.api import OpenMayaRender as render
NAME='reaPencilPreview'
_override=None
_pending=False

class Preview(render.MRenderOverride):
    def __init__(self):
        super().__init__(NAME)
        self.operations=[render.MSceneRender('ReaPencil_scene'),render.MHUDRender(),render.MPresentTarget('ReaPencil_present')]
        self.index=0
    def uiName(self):return 'ReaPencil Preview'
    def supportedDrawAPIs(self):return render.MRenderer.kOpenGLCoreProfile
    def startOperationIterator(self):self.index=0;return True
    def renderOperation(self):return self.operations[self.index] if self.index<len(self.operations) else None
    def nextRenderOperation(self):self.index+=1;return self.index<len(self.operations)
    def setup(self,destination):
        global _pending
        from . import fast_targets,viewport
        if fast_targets._watching:fast_targets._watching=False;viewport._scene_changed()
        clear=self.operations[0].clearOperation()
        clear.setClearColor(cmds.displayRGBColor('backgroundTop' if cmds.displayPref(q=True,displayGradient=True) else 'background',q=True)+[1.])
        clear.setClearColor2(cmds.displayRGBColor('backgroundBottom',q=True)+[1.])
        clear.setClearGradient(cmds.displayPref(q=True,displayGradient=True))
        clear.setOverridesColors(True)
        from . import viewport
        nodes=cmds.ls(type=viewport.NODE_NAME) or []
        if not _pending and (not nodes or not all(cmds.getAttr(n+'.linePreviewEnabled') for n in nodes)):
            _pending=True
            def create():
                global _pending
                try:
                    # A deferred request can outlive a switch to Fast/VP2.
                    if _override is not None and allowed(destination):viewport.enable(_from_renderer=True)
                finally:_pending=False
            utils.executeDeferred(create)

def register():
    global _override
    if _override is not None:return
    from . import fast_viewport
    fast_viewport.register()
    mel.eval('source "reaPencilPreviewOptionBox.mel"; source "reaPencilFastPreviewOptionBox.mel";')
    _override=Preview();render.MRenderer.registerOverride(_override)

def allowed(panel):
    if _override is None:return True
    return bool(cmds.modelPanel(panel,exists=True) and cmds.modelEditor(panel,q=True,rendererOverrideName=True)==NAME)

def select_precise():
    if _override is None:return
    for panel in cmds.getPanel(type='modelPanel') or []:cmds.modelEditor(panel,e=True,rendererOverrideName=NAME)

def unregister():
    global _override
    for panel in cmds.getPanel(type='modelPanel') or []:
        if cmds.modelEditor(panel,q=True,rendererOverrideName=True) in (NAME,'reaPencilFastPreview'):
            cmds.modelEditor(panel,e=True,rendererOverrideName='')
    if _override is not None:render.MRenderer.deregisterOverride(_override);_override=None
