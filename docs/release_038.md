# ReaPencil 0.8.38 — local candidate

The CPU distance editor can bind the single transform selected in Maya, without Pencil installed. Selection is pending until Apply; Cancel preserves the graph. Pending references survive rename and are validated again before mutation. Deleted/ambiguous selections are rejected.

Use camera depth explicitly returns that channel to its camera-distance calculation. Freeze retains the current world point. A persisted enabled state distinguishes these deliberate modes from a missing live reference, including editable referenced scenes where attributes cannot always be deleted. Message-only0.8.37 links continue to work.

Only the selection UI and binding state changed; native CPU math remains unchanged. No automatic installation or GitHub publication.
