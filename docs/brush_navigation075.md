# Brush navigation200 — local0.8.75 candidate

## Result and rendering contract

General Preview reuses the existing retained world-space brush buffers while the camera moves in a single model view. After200ms idle, one numeric background worker computes the same detailed per-view coverage used by074. The UI thread validates the immutable source requests and uploads the completed result. Brush detail is temporarily anchored to the previous view while navigating (zoom/orbit can change its apparent texture/spacing); stopping restores the current exact-view calculation. No sample, lane or opacity thresholds were reduced. CPU rendering is entirely unaffected.

New default-on Preview Performance option: **붓 스트로크 사용 중 카메라 이동 최적화** / Keep camera navigation smooth with brush strokes. Off uses the established synchronous exact-per-view path. This is a viewport preference, not saved line style/CPU settings. Quad/floating multiple visible model views and exceptional/deferred legacy paths retain the established exact behavior; they are not claimed faster. Geometry animation and the first/style-change build still pay their normal calculation cost. Pure PNG-only presets are outside this optimization; built-in brush-containing passes are supported.

## Actual Maya evidence

Owned Maya2025 PID54956/private prefs/staged package, copy of Downloads/dd.mb.170 render meshes,73863 triangles, full scene line sets at saved1.0/1.2px widths.997×693 viewport, RTX4070/Ryzen7900X.60 scripted orbit poses per family scheduled16ms apart. Final Rough Ink refresh median6.97ms/p958.63ms; observed pose interval median23.42ms (~42.7fps). Previous074 exact orbit median2382.58ms in the same scene class. These are actual Maya refresh timings and scripted input cadence, not a guarantee for all scenes/resolutions.

Final idle-current-view detail took3.09s (worker2.58s; UI upload/prepare187.79ms). Moving camera remains responsive while that work runs. A one-time upload can briefly pause the UI at idle. Resume-during-worker refresh median9.36ms/p9513.11ms, observed interval26.30ms (~38.0fps); stale camera result discarded and latest view applied. Dry/Scratch also passed60-pose navigation and exact idle restoration; see motion_dry.json/motion_scratch.json. Ordinary clean-brush regression median5.47ms.

GUI performance option localized, both states tested. Scene CPU settings and line-set JSON remain identical through toggling. Async idle vs strict reference changed0.000724% of pixels with mean RGBA difference0.000370; no pixel-identical GPU claim. Background and scalar main-thread numeric output are exactly equal for an actual dd intersection input (201274 generated segments). CPU default dd render SHA256 remains f226f3099dfd88f698ab8884f669d30655c6c5edb82ad4936a8bc7f06fbefb30, identical to the earlier golden.

## Safety and invalidation

Only main thread touches Maya/Qt/native upload. One bounded worker, no backlog of camera tasks. Requests own read-only arrays and deep-copied styles; worker uses an isolated connectivity-cache module. Camera/scene revisions tag results. Source arrays/metadata/styles/fixed pressure coordinates are checked before replay; mismatch recomputes rather than applying stale coverage. Geometry/style edits invalidate the source even on early style-only reuse. Actual scene-node insertion during a pending worker rejected its old result; test probe removed. Unit tests cover stale camera/scene, snapshot ownership, replay mismatch and cancellation. Reset/fallback dispose stale results; in-flight cleanup continues polling without starting another task. Native binaries, shaders, CPU renderer and installed074 are byte-identical.

Test harness notes: initial captures occurred while a Maya plugin security modal blocked the viewport (disabled/no-render samples rejected, not used). Exact staged/hash-recorded plugin warnings were allowed through Computer Use per prior authorization. First resume scheduling did not actually overlap a worker; corrected to wait for a running future. An ordinary-regression global name collided with another QA variable; rerun with local scope. Product candidate initially had an indentation error in a generated staging edit, corrected before plugin load/validation. These are retained as initial QA error logs; final evidence above passes.

## Deliverable and next work

Local075 candidate only; no install or GitHub publication. Changed runtime: __init__.py, retained_viewport.py, preview_settings.py, new preview_brush_navigation.py.155 runtime hashes/package manifest verified. User scene and sessions untouched. Initial/full builds still take seconds in a million-segment scene; multi-view/legacy/animated geometry performance is not solved. Next: user review and explicit local install request, then check preferred viewport size/device. A full GPU texture-brush path would be a separate improvement if exact continuously view-adapted detail is required during navigation.
