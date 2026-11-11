# 0.8.77 local candidate: Dash + Rough Ink → Clean Preview

The Brush Stroke Clean preset intentionally retains the independent Dash line shape. Previously the remaining Dash style left both the batched procedural path and idle navigation reuse, invoking scalar Python expansion for every candidate on every camera frame. In dd.mb this froze each refresh for roughly9 seconds.

General Preview now batches Clean Dash with the original sample spacing, clipping, phase, owners and fixed profile domains. Camera navigation reuses retained world geometry and restores exact current-view detail after stopping, using the existing default-on viewport option. Solid Clean remains inactive. PNG and other clean shapes retain their established paths. CPU rendering/shared pattern arithmetic, existing native libraries and shaders are unchanged.

Actual owned Maya2025, dd.mb copy, 997×693 captured viewport: Clean transition 9.014s → 0.794s; subsequent navigation median refresh 6.57ms, p95 8.07ms, scripted timer interval 22.81ms (~43.8fps). Exact idle update 0.92s. These are scripted-refresh measurements, not a guarantee for all view sizes/hardware/scenes.

Transition with an already running Rough+Dash worker: 1.77s; following camera p95 24.69ms, exact Clean/Dash restored in 0.97s after motion. Stale worker output rejected. Disabling Dash while a worker is running, mixed styles and Undo/Redo pass.

175 real input requests / 445,251 segments: source metadata, positions and curve domains exactly equal to the old scalar path. Orthographic/perspective, near-plane, offscreen, reversed, period2–51.7, mixed owners, fixed pressure and prior brush/PNG/missing-helper regressions pass. Reference/candidate viewport images differ in only 6 pixels (mean channel difference 0.000464); mathematical geometry is identical. CPU beauty SHA256 remains `f226f3099dfd88f698ab8884f669d30655c6c5edb82ad4936a8bc7f06fbefb30`.

Installed0.8.76 and user Maya are untouched. This archive is a reviewable local candidate; no GitHub publication. Detailed evidence: validation/dashbrush203.
