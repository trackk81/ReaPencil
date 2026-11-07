# ReaPencil 0.8.24 — local candidate

- Added CPU per-type brushes for outline/open, hard edge, material boundary, normal angle, wireframe, stored selected edges and intersections. Each can have its own color, width and dash settings.
- Added independent CPU hidden-line filters, normal-angle bounds, base brush and per-type brushes in the Line Set Hidden Lines tab.
- Pencil+ conversion now imports connected per-type brushes and independent hidden filters/colors/widths. Saved MA/MB recovery also reads retained visible/hidden switch aliases when the original omits their compound leaves.
- Constant opaque hidden channels use a batched native CPU raster path. Hidden edges no longer unnecessarily disable conservative culling of visible intersections when hidden intersections are off.
- Existing default CPU render images, sample resolution and rendering method are preserved. Alpha Cut Prepass remains removed.

UI: Line Set > Visible Lines > Per-type brushes (CPU); Hidden Lines > Independent hidden settings (CPU).

Verified against original Pencil+ in isolated Maya control scenes, with MA/MB Pencil-free recovery/reopen, GUI edits and full horse-scene image/performance comparisons.

Limitations: these independent brushes are CPU features; viewport previews remain approximate. Opaque Normal composition is supported; per-type/hidden varying curves, other blend modes, maps, copies/distortion and complete brush equivalence are not implemented. Pencil+ Object-edge classification and source selected-edge-data conversion remain unsupported and are reported. Tested feature precedence is not a claim of every coincident-feature combination or pixel-identical widths/AA.

This local candidate is not automatically installed or published.
