# ReaPencil 0.8.32 — local candidate

Two-knot full-domain Linear camera-depth **size** reduction now changes CPU line radius per fragment. It combines with the depth alpha reduction introduced in 0.8.31, stroke profiles, opacity and blending in visible/hidden base or dedicated brushes. Original MA/MB numeric snapshots can supply these settings without Pencil installed.

The new varying-size path uses the source-calibrated radius and analytical coverage model. Legacy constant reduction scalar folds and existing converted settings retain their previous behavior and width/AA approximations. Default rendering without the new effect is unchanged.

Reference-object/non-Linear/multi-knot reduction and a dedicated editing UI remain unsupported. Existing original width/AA, corner/loop, singular-profile and viewport differences remain. Final rendering stays on CPU. Complex SVG/EPS remain embedded-raster outputs rather than editable vectors.

No automatic installation or GitHub publication is performed.
