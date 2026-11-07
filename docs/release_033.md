# ReaPencil 0.8.33 — local candidate

Line Set > Brush Details > Depth reduction (CPU) now edits the implemented two-endpoint Linear camera-depth width/alpha reductions. Independent Hidden Lines has its own editor. English and Korean labels, per-channel enable, start/end distance and endpoint factors, atomic validation, cancel and one-step undo are supported.

The editor changes actual CPU render settings; it does not add non-Linear, reference-object or multi-knot reduction support. Existing scalar constant conversions retain their prior width approximation. Viewport reduction equivalence remains unsupported. Default CPU rendering and native DLL are unchanged from 0.8.32.

No automatic installation or GitHub publication performed.
