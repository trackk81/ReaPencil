# ReaPencil 0.8.22

- Removed the Alpha Cut Prepass checkbox and its guidance from Fast Preview settings, following reports of unwanted internal contours on opacity-textured foliage.
- Removed the plug-in setter and status field for this Maya setting. ReaPencil no longer offers or changes this setting.
- Kept the 0.8.21 live alpha-texture connection fixes, material-target diagnostics, CPU curve improvements and existing CPU final renderer.

Restart Maya after updating. If Alpha Cut Prepass was enabled previously, it remains a Maya scene setting. To disable it in that scene, run this in the MEL tab of Script Editor:

```mel
setAttr "hardwareRenderingGlobals.alphaCutPrepass" 0;
refresh -f;
```

Removing this control does not implement a new alpha contour algorithm or guarantee that every opacity-textured scene will show identical contours. CPU rendering and GPU shader/native binaries are unchanged from 0.8.21.
