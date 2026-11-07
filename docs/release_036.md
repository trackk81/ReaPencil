# ReaPencil 0.8.36 — local candidate

Full-domain Linear distance-varying width/alpha reduction can now use a referenced transform world-origin snapshot. CPU native fragments interpolate the actual 3D stroke position with perspective correction and evaluate Euclidean distance before coverage/compositing. Width and alpha may use distinct origins. Visible/hidden dedicated brushes, mixed output, saved original MA/MB conversion and CPU fallback receive the same data.

Reference origins are current-frame snapshots, not live node bindings: reimport after reference animation/edits. The editor displays world snapshot coordinates and clears the corresponding origin when disabling that reduction. Existing camera-depth behavior and old native API remain available.

Unresolved references, arbitrary non-Linear/bent/partial-domain reductions and viewport equivalence remain unsupported. Existing AA/width/corner/loop differences remain. No automatic install or GitHub publication.
