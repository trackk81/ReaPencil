# ReaPencil 0.8.30 — local candidate

The constant Linear subset of PencilReductionSettings can now be recovered directly from verified original Maya 2025 MA/MB snapshots without Pencil installed. Recovery uses the observed node type, attribute aliases and UUID, reads only bounded numeric profile rows and never evaluates source scripts.

Both width and alpha factors apply to visible/hidden base and dedicated CPU brushes. This extends the live-node conversion in 0.8.29. Original unknown conversion and converted save/reopen have been checked in isolated Pencil-free Maya processes.

Nonconstant/non-Linear/reference-object reduction remains unsupported. Sparse child overrides, unknown-resaved source formats, animation/procedural inputs and later unsaved edits are outside verified recovery. Malformed or incomplete data is rejected rather than interpreted as a constant curve. Existing curve/width/AA and viewport limitations remain.

CPU rendering and sampling are unchanged. No automatic installation or GitHub publication is performed.
