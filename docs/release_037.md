# ReaPencil 0.8.37 — local candidate

New Pencil reference-origin imports now retain real Maya message connections. CPU scene export resolves the current transform world origin on each render, following animation, rename and parenting without reimport. Independent visible/hidden width and alpha connections are supported. Serialized snapshots remain as fallback if a binding disappears, with a warning; old snapshot-only scenes keep their existing behavior until reimported.

The editor labels live references and can freeze the current point on Apply, cancel without changes, or disconnect a disabled reduction. Freeze/disconnect participates in Undo.

Namespaced settings discovery now finds imported Rea render settings while preserving root host settings priority. Maya's host render globals/camera gate are still retained on scene import.

Native CPU rendering is unchanged from0.8.36. Unresolved/instanced references and arbitrary non-Linear/bent/partial curves remain outside the supported live import subset. No automatic installation or GitHub publication.
