# ReaPencil 0.8.27 — local candidate

Stored Bezier, Spline and Break profiles can now import forward-facing handles that extend beyond a neighboring control point. CPU evaluation limits handle X to the adjacent knot while preserving Y, following controlled Pencil runtime comparisons. This applies to independent width/alpha curves and hidden brushes, including opacity and blending.

Paired crossing handles with a singular inverse and backward-facing handles remain explicitly unsupported. Some profile samples and integrated widths still differ from Pencil. Original corner/loop/stroke continuity limits also remain.

Final rendering stays on CPU. Existing in-span curves and basic render images are preserved. Mixed SVG/EPS outputs retain the explicit embedded-raster representation introduced in 0.8.26; these are not editable vector strokes.

This is a local review candidate. No automatic installation or GitHub publication is performed.
