# ReaPencil 0.8.29 — local candidate

Import the verified constant Linear subset of PencilReductionSettings. A full-domain constant size curve multiplies CPU brush width, and a constant alpha curve multiplies brush opacity. Factors apply to visible/hidden base and dedicated brushes, preserving existing flat brush profiles and blend amounts. Converted settings persist without requiring Pencil at render time.

This does **not** implement distance-varying reduction curves. Nonconstant/non-Linear curves, object-reference mode and unverified raw unknown-node reduction data are reported as unsupported. Converting a live Pencil scene first is required for this new subset. Existing general width/AA differences from Pencil remain.

CPU rasterization and viewport code are unchanged. Mixed SVG/EPS retain the documented embedded-raster representation. No automatic installation or GitHub publication is performed.
