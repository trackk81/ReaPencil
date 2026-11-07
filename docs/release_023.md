# ReaPencil 0.8.23 — local candidate

- Added Normal angle maximum to Line Set > Line Types and scene advanced settings.
- Pencil+ conversion now imports edgeNormalAngleMax instead of ignoring it, including saved MA/MB unknown-node recovery.
- CPU rendering and precise viewport paths use the interval minimum < normal angle <= maximum. Outline, hard-edge and other enabled line features remain independent.
- The default maximum of 180 degrees preserves older styles. Inverted or equal bounds select no normal-angle lines.

Validation: original Pencil+ and converted CPU renders in isolated Maya, 26 controlled hinge/range cases; Pencil-free MA/MB recovery and save/reopen; CPU and precise GPU tests; default horse-scene image hashes and timings.

Limitations: controlled shared-edge classification is verified, not full image equivalence. Original zero-degree coplanar triangulation lines can differ. Nonmanifold face selection and independent hidden-brush filters remain outside this change. Fast Preview continues to use its screen-space approximation and does not reproduce this exact normal-angle interval.

Alpha Cut Prepass remains removed. Final rendering remains CPU-based. This candidate is not automatically installed or published.
