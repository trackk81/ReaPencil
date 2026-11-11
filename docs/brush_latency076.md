# Brush latency201 — local0.8.76 candidate

## Result

User requested shorter stopped-camera detailed-brush refresh in dd.mb, preserving CPU rendering and withholding GitHub publication. Owned Maya2025 PID15988/private preferences/staged package opened a scene copy; user session and source scene untouched.157 runtime files, local candidate only. Existing installed075 remains unchanged.

Final first refresh after navigation: 0.712s vs prior075 3.092s. Repeat Rough Ink 0.647–0.768s (median0.726s); Dry Brush 0.748s; Fine Scratch 0.610s. Same scene class, saved1.0/1.2px widths and997×693 viewport on RTX4070/Ryzen7900X. Poses/output segment counts vary, so ratios are indicative, not identical-pose sustained performance guarantees. The repeated trials produced~1.83–2.74M full detail segments; no lane/subdivision/opacity threshold was reduced.

Camera navigation remains cached and responsive: final60-pose refresh median6.97ms/p959.41ms, observed scheduled pose interval23.41ms (~42.7fps). Resuming during a worker: median7.55ms/p959.84ms, observed interval24.09ms (~41.5fps); old camera output rejected and latest detail applied after0.650s idle. Worst measured refresh in that final resume test was11.36ms. Initial prototypes were1.79s/1.27s; an intermediate fast-worker stale-result cleanup produced a long tail and was corrected before final tests.

## Implementation

Added original preview-only C++ helper reaPencilPreviewBrush201b.dll, ABI201, source native/preview_brush201.cpp. It implements the existing built-in solid-path brush arithmetic in double precision, same5/7/9 lanes, same1px subdivisions, hash/noise, coverage threshold, projected phase and reciprocal-depth reconstruction. Memoized integer noise hashes evaluate the same values without repeated sin calls; bounded lookup falls back to direct evaluation for wide phase ranges. Up to4 joined calculation threads only for larger inputs; no persistent native thread pool. Bounded allocations, finite-input guards and RAII/thread joining protect failure paths. Missing/unsupported helper falls back to the previous NumPy implementation, without partial-line output. Other shape/PNG combinations use their existing numerical path; no acceleration claim for those paths.

Native results use read-only array-owned allocation lifetimes, avoiding a large copy. Single-owner joins avoid redundant sorting/copying while mixed owners retain stable ordering. Integer connectivity prepared by the main path is captured as immutable seed data; the worker owns its independent cache mapping and always recomputes view-dependent lengths. Idle debounce200→80ms and completion polling40→16ms. Stale and consumed large result buffers are disposed on the numeric worker using a reference-transfer box, preventing UI deallocation spikes. Camera/scene revision validation, exact source replay checks and existing viewport-only option remain. New helper has no Maya or final CPU-renderer API; only the UI thread touches Maya and GPU upload.

Final first worker calculation 0.304s; detailed replay/upload prepare 181.93ms. Warm Rough workers~0.30s. Initial builds/style changes/animated geometry can still cost more; camera-moving detail remains temporarily anchored to the previous view, as in075, until exact-view completion. Multi-view/legacy limitations remain.

## Verification

Native numerical checks cover19 camera/brush/roughness/density cases including actual dd intersections, clipping and reversed phase. Mixed ordinary/PNG/brush metadata and fixed pressure agree; missing-helper fallback is exact. Near-plane fallback, empty clipping, invalid-phase rejection/recovery pass.101 native allocation releases and sliced-array ownership pass. Stale native data release was verified on a worker thread. Immutable connectivity seeding and independent cache clear pass. Camera/scene invalidation and replay/cancellation tests pass; actual pending-worker scene-node insertion rejected stale output and the probe was removed.

All175 current dd submission requests were compared against075 numerical output (~1.82M Scratch segments): count, owners, flags, facing/pressure metadata match; maximum absolute coordinate difference 3.88e-10 world units. Paired warm numerical work was6.33× faster for that snapshot. Actual same-view Rough comparison with the native helper disabled produced exactly2821227 segments in each path; mean RGBA difference0.000512/255, changed fraction0.001013%. No GPU pixel-identical claim.

CPU dd render SHA256 remains f226f3099dfd88f698ab8884f669d30655c6c5edb82ad4936a8bc7f06fbefb30, identical to the earlier golden. CPU renderer, stroke_presets.py, existing CPU/native brush libraries and all shaders are byte-identical to075. No CPU sampling or allocation behavior changed. Ordinary default-brush regression passed. User presets were not modified.

## Deliverable / limits

Changed: preview_brush_batch.py, preview_brush_navigation.py, new preview_brush_native.py, new preview-only DLL, __init__.py version. Exact compiled C++ source and a portable build script included. Prototype201.dll is deliberately excluded; final helper is201b. Local076 archive only; no automatic installation and no GitHub action. Large line widths, tall PNGs, other patterns, multi-view layouts, geometry animation and different devices/view sizes may retain higher cost. Full CPU active-brush code is unchanged; default dd CPU golden was replayed, not every advanced layer/vector combination. Next: user local candidate review/install request.
