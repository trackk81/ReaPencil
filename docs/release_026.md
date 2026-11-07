# ReaPencil 0.8.26 — local candidate

Independent CPU brush width/alpha profiles, opacity and blend modes now support Merge Groups and color/depth render elements. Element visibility, edge-type and Line Set ID filters and element-only output apply to these effects. Color elements follow Pencil's premultiplied RGB convention; background color preserves coverage alpha.

SVG/EPS mixed-effect output embeds the finished CPU image at the requested resolution on a white matte. This preserves appearance but is **not editable vector artwork**. PNG retains coverage alpha. Ordinary opaque vector output stays on the existing path. EPS Illustrator editing metadata is not implemented.

Identical element filters reuse one CPU canvas. Conservative intersection culling also works with mixed-effect elements. CPU rendering, resolution and sampling remain unchanged.

Known limits: organic stroke continuity, irregular closed-loop phase and some width/AA differences from Pencil remain. Out-of-span profile handles, effect combinations with variation/taper/distance reduction, PLD and velocity remain unsupported. This is a local review candidate; it has not been installed automatically or published to GitHub.
