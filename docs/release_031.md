# ReaPencil 0.8.31 — local candidate

Two-knot, full-domain Linear **alpha** reduction now evaluates camera-space depth at CPU line fragments. Orthographic interpolation and reciprocal perspective depth apply before coverage selection/compositing, including hidden and dedicated brushes. Existing stroke profiles, opacity, blend modes, Merge Groups and color/depth elements share this path.

The import snapshot stores validated start/end and endpoint alpha values. Verified original MA/MB reduction snapshots also work without Pencil. This is an imported CPU setting; a dedicated reduction editing UI is not included yet.

Distance-varying size reduction, non-Linear curves, reference-object mode and unsupported source snapshot layouts remain excluded. Existing original width/AA/corner/loop differences remain. This does not change Fast Preview or precise viewport behavior. Final rendering stays on CPU; complex SVG/EPS output embeds the CPU image and is not editable vector artwork.

No automatic installation or GitHub publication is performed.
