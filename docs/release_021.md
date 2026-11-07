# ReaPencil 0.8.21

- Fast Preview settings now include **Alpha Cut Prepass (Maya)**. Enable it for opacity-textured objects whose cutout contours are missing. This is an explicit Maya viewport setting; final CPU rendering is unchanged.
- Fast Preview settings identify material targets that are not assigned to scene faces. Add the material actually assigned to the mesh to its Line Set.
- Material-derived alpha boundaries follow the assigned material's current texture connection and invalidate cached geometry when that connection changes. Explicit image overrides are preserved. RGB opacity textures connected to outTransparency support luminance masks.
- CPU variable width/alpha strokes now join corners using projected split angles, support clockwise/counterclockwise closed loops, and improve thin-stroke coverage and Pencil+ width matching.
- Original Maya float precision is preserved when recovering saved Pencil+ curve controls from MA/MB files.

Validation: isolated Maya 2025 alpha-scene GUI checks, live texture rewiring and CPU renders, original Pencil+ curve comparisons, and full horse-scene CPU benchmarks. Default-render image hashes are unchanged in the benchmark.

Limitations: some irregular/rotated closed-loop start phases still differ from Pencil+. Out-of-span source curve handles, all brush combinations and complete viewport/final-render equivalence remain outside verified compatibility. This release does not claim pixel-identical Pencil+ output.

After updating, restart Maya. In a model panel choose Renderer > ReaPencil Fast Preview > option box, then enable Alpha Cut Prepass (Maya) if needed. Only objects/materials assigned to the active Line Set receive targeted lines.
