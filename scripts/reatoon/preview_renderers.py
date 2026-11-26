"""Panel-local Maya Renderer menu entries for precise and fast previews."""
from maya import cmds,utils,mel
from maya.api import OpenMayaRender as render
NAME='reaPencilPreview'
_override=None
_pending=False

class AlphaSurface(render.MSceneRender):
    def renderFilterOverride(self):return self.kRenderShadedItems

class AlphaOverlay(render.MSceneRender):
    def preRender(self):
        from . import viewport_alpha_gpu
        if viewport_alpha_gpu._library is not None:viewport_alpha_gpu._library.rt_alpha_phase(0)
    def renderFilterOverride(self):return self.kRenderNonShadedItems
    def clearOperation(self):
        clear=super().clearOperation()
        clear.setMask(render.MClearOperation.kClearNone)
        return clear

class AlphaDepth(AlphaOverlay):
    def objectSetOverride(self):
        from maya.api import OpenMaya as om
        from . import viewport
        selected=om.MSelectionList()
        for node in cmds.ls(type=viewport.NODE_NAME,long=True) or []:selected.add(node)
        return selected
    def preRender(self):
        from . import viewport_alpha_gpu
        if viewport_alpha_gpu._library is not None:viewport_alpha_gpu._library.rt_alpha_phase(1)
    def postRender(self):
        from . import viewport_alpha_gpu
        if viewport_alpha_gpu._library is not None:viewport_alpha_gpu._library.rt_alpha_phase(0)

class Preview(render.MRenderOverride):
    def __init__(self):
        super().__init__(NAME)
        self.operations=[render.MSceneRender('ReaPencil_scene'),render.MHUDRender(),render.MPresentTarget('ReaPencil_present')]
        self.standard=list(self.operations)
        self.alpha=[AlphaSurface('ReaPencil_alpha_surface'),AlphaDepth('ReaPencil_alpha_depth'),AlphaOverlay('ReaPencil_alpha_overlay')]+self.standard[1:]
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
        live=viewport._gpu_scene
        # Transparent surfaces otherwise cover the inner half of their contour.
        # Keep the established single scene pass for non-alpha previews.
        self.operations=self.alpha if live and any(m.get('_gpu_alpha',{}).get('groups') for m in live.scene['meshes']) else self.standard
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
