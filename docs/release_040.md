# ReaPencil 0.8.40 — local review candidate

- Import exactly flat full-span Spline/Bezier/Break/mixed width distance reductions as actual CPU width multipliers, together with previously supported alpha; independent hidden/dedicated brushes and raw MA/MB recovery verified.
- Keep the alpha129 helper name as a compatibility wrapper. Bent handles, partial curves and general non-Linear distance profiles remain excluded.
- Rendering uses the existing constant-width path and retains its thin-line coverage approximation. This is not a fix for that existing discrepancy. Native rendering/defaults are unchanged.
- Prepared for local review only; no automatic install or GitHub publication.
