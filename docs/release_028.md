# ReaPencil 0.8.28 — local candidate

Make source-profile import diagnostics consistent for paired singular handles. An already-clamped handle pair and its out-of-span equivalent produce identical Pencil output; both now report the same unverified inverse limitation. Previously, the already-clamped representation could be imported as though fully supported.

This is a validation fix, not an implementation of singular-curve rendering parity. Supported forward out-of-span profiles from 0.8.27 remain supported. CPU rasterization, image sampling and viewport rendering are unchanged. Original closed-loop/corner/width differences and paired singular profile behavior still require investigation.

No automatic installation or GitHub publication is performed.
