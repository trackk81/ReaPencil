# ReaPencil 0.8.25 — local candidate

- Independent visible/per-type/hidden brushes now import and render stored Linear/Spline/Bezier/Break width and alpha profiles, brush opacity and all 16 Pencil+ blend-mode enum values.
- CPU brush layers apply opacity once to complete brush coverage. Blend colors use the observed white-matte RGB convention while retaining separate coverage alpha.
- Added CPU native profile rendering for hidden channels and a threaded CPU compositor. Layers reuse one scratch image instead of retaining an image per brush.
- Added independent curve editor buttons, opacity fields and named blend menus. Independent edits to snapshots sharing a source brush identity remain separate when their settings differ.
- Default rendering and sample resolution are unchanged. GPU viewport previews remain approximate; Alpha Cut Prepass remains removed.

Validation includes isolated original/candidate Maya renders for three color sets across 16 blend modes, width/alpha curves in independent visible/hidden channels, opacity plus curves, MA/MB recovery/reopen, GUI curve edits and full horse-scene CPU benchmarks.

Limits: stored out-of-span curve handles and irregular closed-loop start phases remain limited. These new mixed effects currently require CPU line-only PNG output; Merge Groups, render elements and SVG/EPS equivalents for the mixed effects are explicitly rejected or omitted rather than silently approximated. Reduction/variation/taper combined with these effects remain unsupported. No claim of complete original pixel equivalence or improved first-render time in every scene.

This local candidate is not automatically installed or published.
