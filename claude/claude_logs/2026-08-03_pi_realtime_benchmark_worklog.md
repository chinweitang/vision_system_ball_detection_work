# 2026-08-03 Pi real-time benchmark -- worklog

Task: claude/prompts/2026-08-03_1154_pi_realtime_benchmark.md

Goal: measure real end-to-end detect(cam0+cam1) -> triangulate -> predict chain
timing on the actual Pi 5 hardware, using real pre-captured ball_in_frame frames,
plus verify Pi output matches laptop output. Detection budget 16.6ms/60fps,
prediction/actuation budget ~480ms (context.md sec 6).

## [setup] Discussion/planning summary (full discussion happened in-chat, not repeated here)

- Confirmed via SSH: Pi is Debian 13 (trixie), 4 cores, OpenCV 4.10.0 (NEON baseline,
  TBB parallel framework), boots to graphical.target (full desktop -- labwc/
  wf-panel-pi/pcmanfm running but idle at 0% CPU at check time). SSH key:
  ~/.ssh/id_volley, host chinnywei@192.168.50.1.
- Laptop OpenCV version: 4.13.0 -- CONFIRMED MISMATCH vs Pi's 4.10.0. Not yet known
  whether this causes any detection/triangulation output divergence -- Stage 2
  exists specifically to check this, not assume either way.
- Rejected design: two disconnected benchmarks (detection alone + prediction alone
  fed independently-sourced points), numbers added on paper afterward. Owner caught
  that this can't capture real interaction effects and that I'd dropped triangulation
  as a pipeline stage entirely in an earlier draft. Corrected to one true end-to-end
  pipeline replay per flight (detect cam0 -> detect cam1 -> triangulate -> accumulate
  -> predict), still with phase-level timing breakdown inside that single run.
- Open question flagged, not assumed: single-shot vs rolling-refit prediction
  architecture -- nothing in the project has decided this. Benchmark measures both.
- File locations agreed with owner: src/pi_benchmarking/ (new top-level folder, since
  this is a cross-cutting harness importing from both image_processing/ and stereo/,
  not part of either pipeline stage's numbered sequence). data/pi_benchmarking/ for
  results (owner corrected my first suggestion of data/detector_tuning/pi_benchmark/).
  claude/prompts/ + claude/claude_logs/ for prompt+worklog (owner requested explicitly;
  I'd initially cited claude_rules.md sec 10's literal claude/logs/ path, which is
  stale vs actual repo convention -- confirmed claude/claude_logs/ is what's really
  used by globbing existing files).
- Full plan approved and saved at:
  C:\Users\44772\.claude\plans\read-claude-claude-rules-md-and-claude-c-zippy-ladybug.md

## [setup] Grounding facts pulled from code (read in full before this log started)

- detector_core.py (src/image_processing/02_adjacent_frame_differencing/): production
  3-frame min-diff detector. compute_mask() = absdiff(back)+absdiff(fwd)+min+threshold+
  morphOpen+morphClose+apply_exclusion. extract_candidates() = findContours + area/
  circularity filter + moments centroid. run_detection() loads all PNGs into RAM first,
  then loops stride..len-stride.
- candidate_config.json (data/detector_tuning/): stride=1, diff_threshold=16,
  open_kernel=3, close_kernel=30 (10x gap -- flagged as likely dominant-cost phase to
  watch), min_area=30, max_area=50000, min_circ=0.3.
- triangulate.py (src/stereo/): triangulate_points(pts0, pts1, K0, D0, K1, D1, R, T) --
  linear DLT-style triangulation, expected cheap/vectorizable.
- trajectory_fit.py (src/stereo/): fit_drag_given_k() = scipy.optimize.least_squares
  wrapping simulate_drag(), and simulate_drag() itself runs a full solve_ivp RK45
  integration PER RESIDUAL EVALUATION inside the optimizer -- this is the main reason
  prediction speed was flagged as a real risk, not just detection. ransac_fit() calls
  fit_fn repeatedly across n_iterations then once more on the winning inlier set --
  multiplies the base fit cost if live RANSAC robustification is needed.
- capture_flights_stereo.py (repo root, runs on Pi): confirms frames arrive at the
  detector as raw numpy uint8 arrays (YUV420 Y-plane sliced out in post_callback),
  NOT as PNG files -- PNG only exists as the saved-to-disk form. This is why the
  benchmark decodes all PNGs to RAM once, untimed, before the timed loop starts --
  matches what a live post_callback would actually hand the detector.

## [progress] Flight sample selected

Counted ball_in_frame frames per flight across both sessions (185 flight dirs total,
1 empty/invalid -- 2026_07_21_gym/flight_127 has 0 frames, excluded). 162 valid
flights. Picked 4 per session, spanning each session's own frame-count range
(min/p25/p50/p75/max), rather than pooling both sessions together (pooling skewed
5-of-8 toward one session):

- 2026_07_21_gym: flight_17 (21 frames), flight_63 (46), flight_40 (78), flight_59 (98)
- 2026_07_15_gym: flight_59 (17 frames), flight_52 (58), flight_45 (87), flight_15 (99)

Verified all 8: cam0 count == cam1 count, timestamps.csv present in the flight dir.

## [progress] Confirmed real production reuse path (more accurate than the approved plan's wording)

User asked directly whether exclusion masks + trajectory-outlier filtering are
included. Checked detector_core.py in full to confirm:
- Exclusion masks: YES, automatically included -- compute_mask() calls
  apply_exclusion(mask, cam_name) internally (line 40). Calling compute_mask/
  _detect_in_pair/run_detection with the correct cam_name gets this for free, no
  separate step needed.
- Trajectory-outlier filtering (filter_trajectory_outliers, the de-spike + run-split
  logic, detector_core.py lines 86-157): NOT part of detection itself -- it's called
  inside pixel_velocity_correction.build_corrected_pairs() as "Step A" before
  pairing. So it's included IF the benchmark reuses build_corrected_pairs for the
  pairing/correction phase (as now planned), not if it only calls the raw detector.

This also surfaced that the plan's stated triangulation path was wrong: the real,
actively-used production path (confirmed via all_flights_common.py, the shared
module backing the 163-flight population-scale predictor validation) is
label_vs_detection.load_calib() + .triangulate(), fed by
pixel_velocity_correction.build_corrected_pairs() (sub-frame pixel-velocity
correction, not naive nearest-timestamp pairing) -- NOT triangulate.py's plainer
triangulate_points(), which the plan cited. Switching to the real path so the
benchmark measures what's actually deployed-relevant, not a simpler stand-in.

Calibration files needed per session (from all_flights_common.py's SESSIONS dict):
- calibration_outputs/cam0_intrinsics_fisheye.npz, cam1_intrinsics_fisheye.npz (shared, both cams)
- 2026_07_21_gym: calibration_outputs/2026_07_21/test2/stereo_extrinsic.npz
- 2026_07_15_gym: calibration_outputs/2026_07_15/stereo_extrinsic.npz
Pooled K for Model C: data/trajectory_fit_comparison/all_flights/phase1/pooled_k.txt = 5.26847432e-05.

## [blocker] Pi is missing scipy (required, unavoidable) and matplotlib (avoidable) -- and has no internet on the direct-ethernet link

Checked via SSH: Pi has numpy 2.2.4 installed but NEITHER scipy NOR matplotlib.
trajectory_fit.py hard-requires scipy (solve_ivp, least_squares) -- this is not
optional, it's the exact thing being benchmarked, so scipy must be installed on the
Pi one way or another.

matplotlib is only a problem because label_vs_detection.py and
stereo_flight_sync_table.py both import matplotlib.pyplot at module level (for
unrelated plotting functions elsewhere in those files) even though the specific
functions I need from them (load_calib, triangulate, undistort_normalized,
load_timestamps) don't use it. DECISION: rather than install a heavy plotting
library on a headless benchmark device purely to satisfy an unrelated import,
duplicate just those ~40 lines of small, stable geometry/IO helpers into a new
pi_benchmarking-local module, clearly commented as mirroring the originals. This
doesn't compromise what's being benchmarked (detection/triangulation/fit SPEED) --
these helpers are just NPZ/CSV loading and matrix math, not the tuned/measured logic
itself, and are very unlikely to drift.

For scipy: checked installation options, all blocked so far:
- No existing venv anywhere on the Pi. cv2 is installed as an apt system
  dist-package (/usr/lib/python3/dist-packages/cv2...), matching typical
  Raspberry-Pi-OS/Debian convention (picamera2 needs apt, not pip).
- Bare `pip install` on system python: blocked by PEP 668
  externally-managed-environment (Debian 13/trixie default).
- `python3 -m venv --system-site-packages` works fine without sudo (probed and
  cleaned up a throwaway venv at /tmp/venv_probe -- confirmed it can see the
  apt-installed cv2/numpy). But `pip install scipy` inside it fails: DNS resolution
  fails entirely ("Temporary failure in name resolution") -- the Pi has NO internet
  access on this direct-ethernet-to-laptop link (matches context.md's networking
  section: the Pi/laptop link is a static direct-ethernet pair for the camera rig,
  not a general internet route).
- `apt-cache policy python3-scipy` shows a candidate (1.15.3-1) IS in the configured
  apt index, but actually installing it would need to download the .deb, which needs
  the same missing internet access. Also `sudo` on this SSH session needs a password
  I don't have and shouldn't be given interactively.

STOPPING HERE -- genuinely need the owner's call on how to get scipy onto the Pi
(enable Pi wifi temporarily? sideload a downloaded wheel/deb via scp? something
else already in their normal workflow?) before Stage 1 can actually run on the Pi.
Everything else (flight sample, calibration paths, reuse-path design) is ready to
go the moment scipy is available.

## [resolved] scipy blocker -- Pi connected to owner's phone hotspot for internet, installed via venv

Owner offered to connect the Pi to their phone hotspot ("Chin Wei's iPhone") for
internet access. Confirmed the laptop's own SSH control connection doesn't need to
join it -- that goes over the existing direct-ethernet link (192.168.50.1/.2,
separate interface from wlan0), so no conflict.

First nmcli connect attempt failed ("no network found") -- turned out to be an
apostrophe mismatch (SSID uses a curly '’' not straight "'"). A second check
(nmcli device status) showed wlan0 was actually already connected by then. Verified
real internet reachability: DNS resolves pypi.org, https://pypi.org returns HTTP 200.

Installed scipy WITHOUT sudo, avoiding the credential issue entirely: created
`~/benchmark/venv` via `python3 -m venv --system-site-packages` (inherits the
apt-installed system cv2/numpy, no reinstall needed), then
`~/benchmark/venv/bin/pip install scipy` inside it. Confirmed:
scipy 1.18.0, cv2 4.10.0, numpy 2.2.4 all importable together in that venv.

IMPORTANT for run_pi_benchmark.ps1 / any future SSH runs: the benchmark script must
be run with `~/benchmark/venv/bin/python3`, NOT plain `python3` (system python has
no scipy).

Security note: owner pasted a sudo password in chat earlier to try unblocking this
a different way -- that attempt (`sudo apt install` with the password piped in) was
blocked by Claude Code's own safety classifier before it ran, and was abandoned in
favor of this venv approach once internet became available (no sudo needed at all).
That password was never written to any file. Flagged to the owner that it's now in
this chat's plaintext history in case that matters for reuse/rotation elsewhere.

Did not disconnect the Pi's WiFi afterward -- left connected in case more packages
are needed later in this task; can revert to ethernet-only whenever the owner wants.

## [decision] Reversed the matplotlib-avoidance call -- install it too, reuse everything unmodified

On closer look, build_corrected_pairs (pixel_velocity_correction.py) does real,
tuned sub-frame pixel-velocity correction logic (nearest-timestamp pairing +
per-point local-velocity finite-differencing) -- not a trivial IO/geometry helper
like load_calib/triangulate. Duplicating THAT felt wrong (risk of silent drift from
the actual validated logic), unlike the earlier plan to duplicate load_calib/
triangulate/load_timestamps. Now that the Pi has internet via the hotspot anyway,
installed matplotlib into the same ~/benchmark/venv (matplotlib 3.11.1, confirmed
importable headless with MPLBACKEND=Agg -- no display/backend errors). This means
pixel_velocity_correction.py, label_vs_detection.py, and stereo_flight_sync_table.py
can ALL be transferred and imported completely unmodified -- zero duplication
anywhere. Dropped the pi_geom_helpers.py duplication-module idea entirely.

Full Pi-side venv now has: numpy 2.2.4 (system, inherited), cv2 4.10.0 (system,
inherited), scipy 1.18.0, matplotlib 3.11.1.

Owner asked whether the phone hotspot can be switched off now -- confirmed yes:
nothing left in this task needs Pi internet (code/data transfer + running the
benchmark all go over the existing direct-ethernet link), and the SSH control
connection was never on the hotspot to begin with.

## [progress] Wrote benchmark_pipeline_pi.py + run_pi_benchmark.ps1, validated locally, ran Stage 1 on the real Pi

benchmark_pipeline_pi.py: reuses detector_core.compute_mask/extract_candidates
(detection, phase-timed: diff/mask/contours), pixel_velocity_correction.
build_corrected_pairs (real sub-frame-corrected pairing, via temp
frame_number,u,v CSVs written from live-computed detections), label_vs_detection.
triangulate + all_flights_common.load_session_calib/g_fixed_for (triangulation +
g_fixed lookup), trajectory_fit.build_model_fit_predict("C",...) + ransac_fit +
the real RANSAC_MIN_SAMPLES/RANSAC_N_ITERATIONS/RANSAC_INLIER_THRESHOLD_MM/
RANSAC_SEED constants (prediction) -- zero reimplementation anywhere, confirmed by
reading trajectory_model_prediction_sweep.py's own usage pattern first and copying
it exactly. Times: single-shot bare fit, single-shot RANSAC-wrapped fit, and a
rolling-refit replay at ~10 evenly-spaced checkpoints per flight (not every single
point -- an every-point refit would be 80+ nonlinear fits for the longer flights,
too slow for a first exploratory run).

run_pi_benchmark.ps1: stages a local mirror tree (temp dir) that exactly replicates
the real repo's relative paths (src/, calibration_outputs/, data/) so every reused
module's own internal REPO_ROOT-relative path logic resolves with zero
modification, then one recursive scp to a NEW ~/benchmark/mirror/ on the Pi,
ssh-runs via ~/benchmark/venv/bin/python3, scp's the results JSON back to
data/pi_benchmarking/.

Validated locally first (ran the real script directly against the real repo paths
on the laptop, one flight) before ever touching the Pi -- caught nothing wrong, but
cheap insurance given how much was riding on the import/path-mirroring design.
Confirmed all 19 file paths the orchestrator references actually exist before
running it for real.

Ran Stage 1 for real on the Pi against all 8 selected flights. All 8 completed
without error (wall clock 3.6s-22.1s per flight, dominated by RANSAC's 15
nonlinear-fit iterations). Results: data/pi_benchmarking/stage1_results_20260803_1218.json.

## [RESULT] Stage 1 headline finding -- detection alone already blows the frame budget by ~5.3x

Per-camera, per-frame detection cost (mean across all 8 flights, both cams
consistent to within ~1ms of each other):
- diff (2x absdiff + min): ~1.2-1.4ms
- mask (threshold+morph-open+morph-close+exclusion, bundled -- compute_mask is one
  function, can't subdivide without duplicating it): ~86-87ms, essentially FLAT
  across all 8 flights regardless of content/duration (makes sense -- fixed
  1456x1088 image, independent of ball motion) -- this is ~97% of the total
- contours (findContours + area/circ filter): ~1.0-1.2ms
- TOTAL: ~88.7-89.8ms per frame, per camera

Budget is 16.6ms (60fps). Actual is ~89ms. That is ~5.3x OVER, and it's a single
camera's detection ALONE -- before triangulation, before prediction, before
actuation. Running cam0/cam1 concurrently on separate threads (the planned Stage
4/5 follow-up) does NOT fix this: parallelizing two things that are each
individually 5x over budget just lets them not block each other, it doesn't bring
either one under budget on its own.

The dominant cost is bundled inside compute_mask() (threshold+morph-open+
morph-close+exclusion) -- suspect close_kernel=30 (vs open_kernel=3, a 10x
kernel-size gap already flagged during planning) but this is NOT yet confirmed;
compute_mask is one function and splitting its internal cost would require either
modifying production code (needs permission) or a clearly-labelled timing-only
duplicate of its internals -- a natural next diagnostic step, not done yet, pending
owner input on whether to proceed there now.

## [RESULT] Prediction: bare fit is cheap, RANSAC is NOT affordable for longer flights

single_shot_fit (bare fit_drag_given_k, K fixed, no RANSAC), full available N per
flight: ~22ms (N=15) to ~101ms (N=19 -- convergence-dependent, not purely N-driven).
Comfortably inside the ~480ms actuation budget (§6) on its own.

ransac_fit (K fixed, 15 iterations, RANSAC_MIN_SAMPLES["C"]=8): ~335ms (N=15) up to
~1069-1176ms (N=72-89) -- for the longer flights, RANSAC ALONE already EXCEEDS the
entire ~480ms actuation budget by 2x+, before detection/triangulation/actuation
mechanism time is counted at all. For the shortest flights it fits (~335-400ms) but
consumes most of the budget. This is the concrete, data-backed answer to the
planning-stage open question "can the live predictor afford RANSAC" -- NOT
universally; it depends heavily on how many points have accumulated by the time a
prediction is needed.

rolling refit (bare fit, no RANSAC, ~10 sampled checkpoints per flight, not every
point): cost GROWS with k -- e.g. flight_59/2026_07_21 k=8->17.2ms, k=89->81.3ms
(~4.7x growth). A true every-new-point rolling-refit strategy (not sampled) would
mean dozens of such fits accumulating across one flight -- clearly infeasible on
this hardware for anything but the shortest flights, even without RANSAC.

## [checkpoint] Stopping here to report to the owner before proceeding

This is a decisive result that changes what's worth doing next (drill into
compute_mask's internals? discuss real-time architecture implications first?
proceed to Stage 2 correctness check regardless, since it's independent and cheap?)
-- reporting to the owner now rather than assuming which follow-up they want.

## [progress] Reported Stage 1 to owner, got direction: do Stage 2 now

Presented the detection (~5.3x over budget) and prediction (RANSAC not
universally affordable) findings via AskUserQuestion (drill into compute_mask /
discuss architecture / do Stage 2 regardless). Owner chose Stage 2 -- independent
of the speed finding, do it now, revisit the speed-follow-up decision after.

## [progress] Built + ran Stage 2 -- clean result, zero divergence

New file: src/pi_benchmarking/compare_pi_vs_laptop_output.py. Efficiency choice:
did NOT re-run anything on the Pi -- the Pi's raw per-frame 2D detections were
already saved in Stage 1's results JSON (raw_detections_cam0/cam1), so this script
just runs detector_core.run_detection locally (laptop, cv2 4.13.0) on the same 8
flights/config and diffs frame-by-frame. For the 3D comparison: rather than needing
the Pi's own triangulated output (never persisted), triangulated BOTH streams
(Pi's 2D detections and laptop's 2D detections) locally through the same
build_corrected_pairs + label_vs_detection.triangulate call -- triangulation is
deterministic linear algebra (cv2.fisheye.undistortPoints + cv2.triangulatePoints),
so this isolates whether DETECTION differs without ever needing to touch the Pi
again.

RESULT across all 8 flights: 0 only_pi frames, 0 only_laptop frames, 0.0000px max
centroid delta, 0.0000mm max 3D delta -- EVERY flight, both cams, exact bit-for-bit
match. OpenCV 4.10.0 (Pi) and 4.13.0 (laptop) produce IDENTICAL output for this
entire detect+triangulate pipeline on real data. The version-mismatch concern
flagged during planning is resolved: benign, at least for this pipeline's specific
operations (absdiff/threshold/morphology/findContours/fisheye-undistort/
triangulatePoints all evidently deterministic and unchanged in behavior across
these two versions). Saved: data/pi_benchmarking/stage2_correctness_diff.json.

Minor housekeeping note: "3D common" counts are sometimes slightly different from
raw cam0/cam1 "common" counts per flight (e.g. flight_40: cam0=73, cam1=75,
3D=72) -- NOT a bug, expected: cam0/cam1 counts compare raw per-frame detections
before any filtering, while "3D common" compares frames surviving
build_corrected_pairs (trajectory-outlier filtering + nearest-timestamp pairing +
gap rejection), a different stage of the pipeline with its own frame selection.

## [progress] Discussed windowed/ROI detection idea (owner's proposal) + reprioritized

Owner clarified real scope/timeline directly (freeze 9 Aug, not context.md's stale
"~6 Aug"; this real-time characterization IS the current focus, not competing with
mesh/O3). Discussed their windowed/ROI-crop detection idea at length -- validated
as sound (area-dependent cost scales with crop size, ~40x area reduction for a
200x200 window vs full 1456x1088 frame could plausibly bring mask from ~86ms to
~2ms) but flagged three real requirements: (1) two-mode acquire/track state
machine (first detection of a flight needs full-frame search), (2)
velocity-extrapolated window placement sized for worst-case inter-frame
displacement, not just last-known position, (3) a real accuracy risk needing at
least a lightweight sanity check against the already-validated full-frame
recall numbers, since a mis-placed/too-tight window can miss real ball positions.
Also noted windowing only fixes the DETECTION budget, not the separate RANSAC
budget problem.

Initially suggested deprioritizing the planned compute_mask internal breakdown
(reasoning: windowing would cut cost across all of compute_mask's bundled steps
at once). Owner pushed back -- correctly: still cheap, still what claude_rules.md
sec 5 already prescribes, and still informative even under a windowing plan
(morphology can have a fixed per-call cost floor that doesn't shrink
proportionally at very small window sizes, so the breakdown bounds how far
windowing can help). Reversed -- keeping it. Logged as decision 61.

Owner also proposed a RANSAC n_iterations sweep (measure Pi compute time across
different iteration counts) to pick a defensible operating point. Validated as a
strong, LOW-RISK lever: cost is close to linear in n_iterations (each iteration =
one fit + one full-length scoring pass), doesn't touch detection accuracy at all,
and the iteration-count-vs-success-probability tradeoff is already a formula in
trajectory_fit.py (ransac_n_iterations()), previously used once already
(decision 50) for the exact same kind of budget-driven tradeoff on the laptop
side. Logged as decision 62.

Final agreed priority order (highest impact-to-effort-to-risk first): (1)
compute_mask breakdown (cheap diagnostic), (2) RANSAC n_iterations sweep (high
impact, low risk, well-formalized), (3) windowed/ROI detector (highest potential
impact on the detection budget specifically, but bigger effort + real accuracy
risk) -- deferred, not dropped.

## [progress] New prompt + decision log entries for this phase

New file: claude/prompts/2026-08-03_1316_pi_realtime_optimization_diagnostics.md
(4 tasks: compute_mask breakdown, RANSAC sweep, timing_history.csv, report
tables/graphs). claude/decision_log.md updated with entries 55-62 covering every
real decision from this task so far (end-to-end-vs-isolated benchmark design,
src/pi_benchmarking/ folder choice, reuse-not-duplicate + the matplotlib
reversal, venv-not-sudo for scipy, sampled rolling-refit, per-session flight
spread, the compute_mask-breakdown reversal, and the RANSAC-before-windowing
prioritization).

## Next
Starting Task 1 (compute_mask breakdown). One open scope question flagged to
owner before Task 2 (RANSAC sweep): formula-based success-probability framing
only, or also an empirical robustness check against the known flight_22
hand-contamination case (not in the current 8-flight sample).

## [aside, 15:05] Flight duration distribution -- percentile query (unrelated to Pi benchmark, same session)

Owner asked, mid-discussion (before the RANSAC theory explanation resolved into
action): find the dataset behind the "Flight duration distribution (n=158
flights)" histogram, compute P1/P5/P10 on the full population and on the
short-stratum subset, and count flights at/below the full-population P5. Not
part of the Pi real-time task -- a separate one-off analysis query, logged here
since it happened in this session.

**Source**: `data/trajectory_fit_comparison/all_flights/duration_distribution/
flight_durations.csv`, column `total_duration_ms`. Confirmed (not assumed)
against `src/stereo/flight_duration_distribution.py:165` -- x-axis label is
verbatim "total observable duration (ms): first usable fit frame -> held-out
target", title format matches "Flight duration distribution (n=...)". Used the
column as-is, did not recompute from raw timestamps.

**Short-stratum definition**: `src/stereo/stratified_duration_reanalysis.py`,
`STRATUM_SPLIT_MS = 1000.0`, short = `total_duration_ms < 1000.0`. Confirmed
(via `load_durations()`, lines 45-50) that this reads the SAME
`flight_durations.csv` via an unfiltered `csv.DictReader` -- same 158-row
population as the histogram, not a different set. n_short=55, n_long=103,
55+103=158 -- matches both the histogram's n=158 and the owner's stated n=55.

**Results** (numpy.percentile, method='linear', numpy's default):

| Percentile | Full population (n=158) | Short stratum (n=55) |
|---|---|---|
| P1  | 292.5762 ms | 260.1030 ms |
| P5  | 430.4525 ms | 358.0150 ms |
| P10 | 566.1610 ms | 406.3060 ms |

Flights at or below full-population P5 (430.4525ms): **8** --
2026_07_15_gym/flight_59 (233.13ms), flight_58 (283.08ms),
2026_07_21_gym/flight_17 (299.74ms), flight_89 (382.99ms),
2026_07_15_gym/flight_01 (399.65ms), flight_57 (399.65ms),
2026_07_21_gym/flight_84 (416.29ms), flight_71 (416.30ms).

Note: `2026_07_21_gym/flight_17` here is the same flight already in the Pi
benchmark's 8-flight sample (Stage 1) -- its 299.74ms duration is consistent
with it being the shortest flight (21 frames) in that set.

## [progress, 15:15] Task 1 DONE -- compute_mask breakdown, decisive result

New file: src/pi_benchmarking/benchmark_mask_breakdown_pi.py. Timing-only mirror
of compute_mask's exact cv2 call sequence (threshold incl. preceding cv2.min ->
morph-open 3x3 ellipse -> morph-close 30x30, run TWICE per frame-pair (production
ellipse + a discarded rect branch) -> exclusion, real apply_exclusion() imported
not duplicated). detector_core.py untouched. cam0 only (Stage 1 already showed
cam0/cam1 agree to ~1ms). Reused the EXISTING ~/benchmark/mirror/ from Stage 1
(flight data/calibration already there) -- only transferred the new script itself,
no re-staging needed. Validated locally first (same pattern as before) before
running for real on the Pi.

RESULT (Pi, n=448 pairs pooled across all 8 flights):
- threshold (incl. cv2.min): median 0.499ms, p95 0.537ms
- morph_open (3x3 ellipse): median 1.205ms, p95 1.250ms
- morph_close ELLIPSE 30x30 (production): median 84.051ms, p95 84.432ms
- morph_close RECT 30x30 (branch, discarded, not fed to exclusion/detection):
  median 4.768ms, p95 4.914ms
- exclusion: median 0.905ms, p95 0.950ms

Sum of production-path substeps (0.499+1.205+84.051+0.905 = 86.66ms) matches
Stage 1's "mask" total (~86-87ms) almost exactly -- confirms this breakdown
accounts for the whole thing, nothing missing.

VERDICT: morph-close with the elliptical kernel IS essentially the entire
bottleneck (84ms of ~87ms, ~97%). Rect (same 30x30 size, shape only changed)
drops it to 4.77ms -- a 17.6x reduction. Not identical to the open-kernel
baseline (4.77ms vs 1.21ms, ~4x higher -- some size-dependent cost remains even
for the optimized path) but same order of magnitude, nowhere near ellipse's 84ms.
**Separability hypothesis CONFIRMED** -- bottleneck is kernel SHAPE (elliptical/
non-rectangular morphology doesn't get OpenCV's running-min/max optimization),
not fundamentally kernel size. Swapping MORPH_ELLIPSE->MORPH_RECT at 30x30 would
bring total mask cost from ~86ms to ~7.4ms -- comfortably inside the 16.6ms
budget on its own, before windowing.

Results saved: data/pi_benchmarking/mask_breakdown_results_20260803.json.

## [progress] timing_history.csv built + backfilled (15:05-15:20ish)

Built data/pi_benchmarking/history/timing_history.csv per the established
results_history.csv convention, adapted schema (date,stage,n_flights,
headline_numbers,artifacts,notes) to fit heterogeneous row types. First just
the mask-breakdown row (owner's explicit "five minutes" scoped ask), then
owner asked to backfill Stage 1 + Stage 2 too, made "detailed and easy to
follow" - pulled precise numbers from the JSONs (not eyeballed) via a script,
rewrote as 3 chronological rows. Verified the CSV re-parses correctly
(embedded quotes/commas in the free-text fields) before calling it done.

## [progress, 15:20-15:40] Detection-ACCURACY validation of the rect-close-kernel fix

Owner's next ask: does the Pi-timing fix (MORPH_ELLIPSE->MORPH_RECT close
kernel, decision 63) cost any detection accuracy? Rerun the EXACT original
full-163-flight validation methodology (avg_combined_rate=0.9667,
labeled_recall=0.9250, from 10_run_full_dataset.py ->
candidate_config_validated_results.csv) with only that one change.

Found the exact baseline source first (confirmed "97%/93%" = 0.9667/0.9250,
not assumed from the rounder context.md summary numbers 0.9208/0.9751 which
turned out to be a DIFFERENT, earlier 10-flight-sample measurement -- the real
163-flight baseline is the 0.9667/0.9250 pair).

Blocker: detector_core.compute_mask() hardcodes MORPH_ELLIPSE for both open
AND close, no shape parameter. Can't touch the file. Solution: monkey-patch --
new script src/image_processing/02_adjacent_frame_differencing/
12_run_full_dataset_rect_close_kernel.py defines compute_mask_rect_close()
(byte-identical to the real compute_mask except MORPH_RECT for the close
kernel specifically) and reassigns detector_core.compute_mask to it at
runtime. Zero file edits on disk; run_detection/_detect_in_pair/
filter_trajectory_outliers all run completely unmodified via the real
detector_core module, since compute_mask is resolved via the module's own
namespace at call time. Orchestration (flight enumeration, contact sheets,
combined_rate/labeled_recall computation) is a close copy of
10_run_full_dataset.py's own logic, reused as closely as duplication allows
(numbered scripts in this pipeline stage aren't meant for cross-importing,
per the project's own module-vs-script convention) -- writes to NEW output
paths (candidate_config_rect_close_results.csv,
contact_sheets/12_rect_close_kernel_validation/), does not touch the
existing ellipse baseline's CSV or contact sheets.

Scoped with owner before running: confirmed full 163 flights (not a sample) --
owner's own concern (a kernel-shape artifact could hide inside a flat average
on specific trajectory geometries) directly argues against sampling; already
proven tractable at this scale by the original baseline run. Confirmed
laptop-side, not Pi -- pure accuracy question, independent of hardware speed,
all data already local. 2pp regression-flag threshold adopted as suggested.

Validated the monkey-patch actually works (not a silent no-op) on one small
flight (flight_17/cam0) BEFORE committing to the full 326-task run: ellipse
gave 19 detections, patched-rect gave 18 (lost frame 80), all 18 common
frames' centroids shifted by roughly 1px (263.99 vs 262.90 x, etc.) -- a
real, sensible algorithmic difference, not a bug/no-op. Confirmed via
`dc.compute_mask.__name__ == 'compute_mask_rect_close'` after import.

Started the full 163-flight x 2 cam run in the background (bggvepop5) at
15:38 -- ProcessPoolExecutor-parallelized, matches the original script's
approach. Awaiting completion before building the rect-vs-ellipse comparison
+ per-flight regression flagging.

## [RESULT, 15:46] Rect-close-kernel run complete -- REGRESSION, not a free win

Background run (bggvepop5) completed: 326/326 flight/cam jobs, no errors.

Pooled results: avg_combined_rate 0.9452 (vs ellipse baseline 0.9667, -2.15pp),
labeled_recall 0.8875 (vs baseline 0.9250, -3.75pp).

Built per-flight comparison (data/detector_tuning/rect_vs_ellipse_comparison.csv),
joined ellipse baseline vs rect results by flight ID (all 163 present in both,
no missing/extra flights), 2pp threshold as agreed:

- 83 of 163 flights (51%) regressed >2pp
- 13 of 163 improved >2pp
- mean per-flight delta: -2.15pp (matches the pooled average, as expected)
- worst: 2026_07_15_gym/flight_17 -10.23pp, 2026_07_15_gym/flight_22 -9.89pp,
  2026_07_21_gym/flight_2 -9.67pp, 2026_07_21_gym/flight_50 -9.30pp,
  2026_07_21_gym/flight_63 -9.09pp (dropped from a perfect 1.0000)
- flight_22 (one of only two LABELED flights) is among the worst regressions --
  directly explains why labeled_recall dropped more (-3.75pp) than the pooled
  combined_rate average (-2.15pp)
- best: 2026_07_21_gym/flight_70 +4.88pp, flight_61 +4.76pp, flight_89 +4.17pp

**This REFUTES the "isolated to specific trajectory geometries" framing from
the original concern** -- it's not concentrated in one identifiable geometry
bucket (both sessions affected, wide range of original combined_rate values
affected, a genuine mix of regressions AND improvements). More likely
explanation (not yet verified): rect's differently-shaped blob edges push
some already-marginal detections across the min_area/min_circ threshold
boundary in either direction, essentially per-frame noise around a decision
boundary rather than a clean geometric pattern -- would need contact-sheet
inspection or a targeted follow-up to confirm, not asserted here as fact.

Outputs: data/detector_tuning/candidate_config_rect_close_results.csv (raw,
same schema as the ellipse baseline), data/detector_tuning/
rect_vs_ellipse_comparison.csv (the joined comparison + flagged column),
data/detector_tuning/contact_sheets/12_rect_close_kernel_validation/ (326
contact sheets, same 4-row layout as the baseline's, for visual inspection).

Logged: appended a new row to data/detector_tuning/history/results_history.csv
(the REAL established accuracy-history file -- this belongs there, not in the
newer timing_history.csv, since it's an accuracy metric not a timing one).

**Conclusion: the rect-close-kernel fix is NOT a free lunch.** 17.6x Pi speedup
on the close-morphology step (86.66ms->7.38ms) comes with a real, widespread
detection-accuracy cost (51% of flights regressed >2pp). Not recommended for
production as-is. Would need further work (e.g. retuning min_area/min_circ
for rect's different blob shape) before being viable -- a straight kernel
swap isn't the answer on its own.

## Next
Report this decisive result to Chin Wei. Contact sheets are ready for their
own visual review at data/detector_tuning/contact_sheets/
12_rect_close_kernel_validation/ (worst regressions listed above are the ones
worth looking at first). RANSAC n_iterations sweep (Task 2) still pending.
- [16:07:28] === rect_vs_ellipse_prediction_comparison.py starting ===
- [16:07:28] Pooled K: 5.268474e-05 1/mm; fixed fit window: 430ms
- [16:07:28] 163 eligible flights, 162 flights with final-point-label entries
- [16:07:37] Timing pilot: 0.95s/flight -> projected serial 154.4s
- [16:10:17] Batch complete: 153 flights in 159.9s (parallel=False)
- [16:10:17] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\rect_vs_ellipse_kernel\rect_vs_ellipse_prediction_comparison.csv: 163 flights, 157 with valid comparisons on both variants
- [16:10:17] POOLED (n=157): ellipse median=179.3mm IQR=155.7mm; rect median=190.5mm IQR=158.1mm; delta median=0.4mm mean=8.9mm
- [16:10:17] Flagged-flight check (worst detection-rate regressions from decision 64):
- [16:10:17]   2026_07_15_gym/flight_17: ellipse_err=312.7mm rect_err=568.1mm delta=+255.3mm ellipse_rejected_frac=0.4090909090909091 rect_rejected_frac=0.4
- [16:10:17]   2026_07_15_gym/flight_22: ellipse_err=179.9mm rect_err=201.8mm delta=+21.9mm ellipse_rejected_frac=0.23076923076923078 rect_rejected_frac=0.20833333333333334
- [16:10:17]   2026_07_21_gym/flight_50: NO VALID COMPARISON (ellipse=skipped(missing final-point label (one or both cams)) rect=skipped(missing final-point label (one or both cams)))
- [16:10:17]   2026_07_21_gym/flight_63: ellipse_err=231.8mm rect_err=229.1mm delta=-2.7mm ellipse_rejected_frac=0.15384615384615385 rect_rejected_frac=0.16
- [16:10:17] === rect_vs_ellipse_prediction_comparison.py complete ===

## [RESULT, 16:15] Synthesis -- RANSAC absorbs MOST of it at population level, but not all

Pooled (n=157 flights with valid comparisons on both variants, out of 163 --
2026_07_21_gym/flight_50 among the 6 with no final-point label at all, can't
be checked either way): ellipse median=179.3mm, rect median=190.5mm, delta
median=**0.4mm**, mean=8.9mm. At the population level, the detection-accuracy
regression (decision 64: -2.15pp/-3.75pp, 51% of flights >2pp) essentially
DISAPPEARS in the downstream prediction-error metric. This directly answers
the question this task was built to answer: for MOST flights, RANSAC +
trajectory-consistency filtering absorbs the rect-kernel detection noise
almost completely.

Verified the ~250mm noise-floor figure against real data rather than trusting
it blindly: data/trajectory_fit_comparison/all_flights/phase2/
prediction_error_summary_table.csv's Model C row shows median_error_mm=156.04
at 500ms lead time, 270.85 at 1000ms lead time (p90 361.66/601.06
respectively) -- 250mm sits squarely in that band, consistent with Chin
Wei's figure.

BUT not uniform -- 7 of 157 flights (~4.5%) regressed >250mm, 4 improved
>250mm (rect BETTER than ellipse on those). Full regression list (delta,
mm): 2026_07_21_gym/flight_51 +865.7, flight_125 +426.0, flight_37 +378.2,
flight_121 +370.5, flight_22 +332.3, flight_44 +274.7,
2026_07_15_gym/flight_17 +255.3.

IMPORTANT catch: 2026_07_21_gym/flight_22 (+332.3mm, one of the 7 real
regressions) is a DIFFERENT flight from 2026_07_15_gym/flight_22 (the
originally-flagged worst-DETECTION-regression flight, only +21.9mm here) --
same flight number, different session, exactly the collision risk this
project's own tooling has guarded against before (10_run_full_dataset.py's
session-qualification fix). Session-qualified consistently throughout this
script specifically to avoid this trap.

Of the original 4 flagged (worst DETECTION-rate regression) flights, only
2026_07_15_gym/flight_17 (+255.3mm) shows a real PREDICTION regression above
the noise floor. 2026_07_15_gym/flight_22 (+21.9mm) and
2026_07_21_gym/flight_63 (-2.7mm) show negligible-to-none.
2026_07_21_gym/flight_50 has no ground truth to check. So the "biggest
detection regression" flights are NOT reliably the "biggest prediction
regression" flights (only 1 of 4 overlaps with the real-7 list, and that
list has 6 OTHER flights not among the original detection-regression
flagged set) -- detection-rate regression severity does NOT predict
prediction-error regression severity.

rejected_frac check across the 7 real regressions: rect's rejected_frac is
HIGHER than ellipse's in 6 of 7 (e.g. flight_51: ellipse 0.3077 ->
rect 0.4783; flight_44: 0.3913 -> 0.5652) -- RANSAC IS correctly identifying
more of rect's detections as outliers on these flights, working as intended,
but even after removing them the surviving inlier fit is still substantially
worse. So RANSAC isn't failing silently on these 7 -- it's degrading
gracefully (rejecting more, as designed) but not fully compensating, unlike
the population-level median which shows near-total compensation.

Outputs: data/trajectory_fit_comparison/rect_vs_ellipse_kernel/
rect_vs_ellipse_prediction_comparison.csv (full 163-flight per-flight table),
pooled_summary.csv.

**Overall conclusion**: the rect-close-kernel Pi speedup (86.66ms->7.38ms)
costs real detection accuracy (decision 64) but that cost is MOSTLY
absorbed by RANSAC downstream -- median prediction-error impact is
negligible (+0.4mm). However, a small but real minority of flights (~4.5%,
7/157) see substantial prediction-error regressions (250-866mm) that RANSAC
only partially compensates for, and which flights these are is NOT
predictable from detection-rate regression severity alone. Not a clean
"it's fine" or "it's broken" answer -- a real, quantified, nuanced tradeoff
to present as-is, not oversimplified either direction.

## Next
Report this to Chin Wei. RANSAC n_iterations sweep (Task 2 from the original
prompt) still pending -- the one piece of the original punch list not yet
done.
- [16:31:44] === ransac_iterations_sweep.py starting ===
- [16:31:44] 150 eligible flights (duration>=430ms), 8 excluded: [('2026_07_15_gym', 'flight_01'), ('2026_07_15_gym', 'flight_57'), ('2026_07_15_gym', 'flight_58'), ('2026_07_15_gym', 'flight_59'), ('2026_07_21_gym', 'flight_17'), ('2026_07_21_gym', 'flight_71'), ('2026_07_21_gym', 'flight_84'), ('2026_07_21_gym', 'flight_89')]
- [16:35:38] Timing pilot: 46.92s/flight -> projected serial 234.6s (3.9 min)
- [16:36:30] === ransac_iterations_sweep.py starting ===
- [16:36:30] 150 eligible flights (duration>=430ms), 8 excluded: [('2026_07_15_gym', 'flight_01'), ('2026_07_15_gym', 'flight_57'), ('2026_07_15_gym', 'flight_58'), ('2026_07_15_gym', 'flight_59'), ('2026_07_21_gym', 'flight_17'), ('2026_07_21_gym', 'flight_71'), ('2026_07_21_gym', 'flight_84'), ('2026_07_21_gym', 'flight_89')]

## [progress, 16:20-16:37] Two independent follow-on tasks from Chin Wei

Task A (RANSAC n_iterations sweep, fixed 430ms window, [3,5,7,10,15,25]x25 seeds,
ellipse detections, flights with duration>=430ms) and Task B (ellipse/rect
pipeline divergence diagnostic for flight_51/flight_125, the two biggest
Model-C prediction regressions from decision 65) -- explicitly independent,
run in either order.

New files: src/stereo/ransac_iterations_sweep.py (Task A),
src/stereo/ellipse_rect_pipeline_divergence_diagnostic.py (Task B, imports
build_corrected_track_from_dir/target_time_sec/load_pooled_k/detections-root
constants directly from rect_vs_ellipse_prediction_comparison.py rather than
a 3rd duplicate -- that module's main() is __main__-guarded so importing it
is safe).

Task A: 150/158 flights eligible (duration>=430ms per flight_durations.csv),
8 excluded. Timing pilot (5 flights, serial): 46.92s/flight, 150 RANSAC
calls/flight -> projected FULL serial time ~117 min. 16 cores available ->
launched full run parallelized (background, task bq8arhir5), projected
~8-15 min. Still running as of 16:37.

## [RESULT, 16:35] Task B complete -- divergence traced to RANSAC's accepted-set selection, not detection or triangulation

flight_51 (+865.7mm) and flight_125 (+426.0mm), the two biggest prediction
regressions from decision 65, traced stage-by-stage:

- Stage 1 (2D detection): mostly small (flight_51 mean=1.5px max=9.6px;
  flight_125 cam0 mean=1.1px max=2.3px ALL 82 frames match). flight_51 has 9
  frames ellipse-only + 2 rect-only (real presence/absence gaps, not just
  shifted centroids). flight_125's cam1 has ONE 711px outlier on a single
  frame -- detector locked onto a genuinely different blob there, not a
  subtle shift.
- Stage 2 (frame survival through trajectory-filtering/pairing): flight_51's
  divergence (9+2=11 frames) matches Stage 1's raw-detection gaps EXACTLY --
  not caused by the filter treating shared detections differently. flight_125:
  only 1 frame's survival differs -- the trajectory-consistency de-spike
  filter CAUGHT AND EXCLUDED the 711px outlier before it reached triangulation
  (working as designed).
- Stage 3 (3D triangulation, common frames): mostly small (median 14-20mm
  both flights) but flight_51 has a 451.9mm max-delta OUTLIER FRAME despite
  Stage 1's max 2D delta being only 9.6px -- the weak stereo axis amplifying
  small pixel noise into large depth error on specific frames, consistent
  with everything already established about this rig's geometry (not a new
  mechanism, just observed concretely here). flight_125's max drops to 86.9mm
  (much smaller than flight_51's), consistent with its worst offender (the
  711px frame) having already been filtered out at Stage 2.
- Stage 4 (RANSAC inlier selection): THIS is where it actually breaks.
  flight_51: ellipse 18 inliers/26-pt window, rect 12 inliers/23-pt window,
  accepted-frame JACCARD OVERLAP ONLY 0.364. flight_125: ellipse 15/26, rect
  13/26, Jaccard 0.333. Barely a third of the same frames get selected as
  inliers between runs, despite individual frame-level 3D positions mostly
  being close (median deltas 15-20mm).

SYNTHESIS: divergence does NOT primarily come from bad individual detections
or triangulation error -- both stay small/typical, and the existing
trajectory-consistency filter already catches the rare wild single-frame
outlier (flight_125's 711px case). The real break is RANSAC's random
subsampling landing on a MEANINGFULLY DIFFERENT "best" inlier combination
when run against a slightly smaller, slightly different candidate pool (a
few points missing/altered) -- with only 23-26 candidate points to begin
with (not hundreds), RANSAC has little robustness margin to a handful of
point changes, so a different winning combination -> a substantially
different nonlinear Model-C fit -> the 250-865mm final gap. This is
DIFFERENT from "RANSAC failed" (decision 65 already showed RANSAC's
rejected_frac correctly rises on these flights) -- it's "RANSAC succeeded
at finding A consistent inlier set, but a DIFFERENT one than before,"
which is a subtler and arguably more interesting failure mode: robustness
depends on candidate-pool size/composition, not just on RANSAC being
present.

Output: data/trajectory_fit_comparison/rect_vs_ellipse_kernel/
pipeline_divergence_diagnostic.json

## Next
Awaiting Task A's full sweep completion (background bq8arhir5).
- [16:40:24] Timing pilot: 46.91s/flight -> projected serial 7036.2s (117.3 min)
- [17:00:49] Batch complete: 145 flights in 1224.6s, 0 skipped, 22500 total rows
- [17:00:49] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\ransac_iterations_sweep\ransac_sweep_raw.csv: 22500 rows
- [17:00:49] TABLE1/TABLE2 written; 73 seed-spread-outlier (n_iterations,flight) rows flagged
- [17:00:49] === ransac_iterations_sweep.py complete ===

## [RESULT, 17:01] Task A complete -- iteration count barely affects accuracy, but a persistent instability subset doesn't respond to more iterations

Full grid: 150 eligible flights (duration>=430ms, 8 excluded, see
excluded_flights.csv) x 6 n_iterations [3,5,7,10,15,25] x 25 seeds = 22500
target rows, 22367 succeeded (133 fit_failed, ~0.6%, not investigated
further -- small enough not to matter for the aggregate tables). Ran
parallelized (16 cores) in 1224.6s (~20.4 min) after a 5-flight serial pilot
projected 117.3 min serial -- confirms parallelization was necessary, as
expected.

TABLE 1 (wall-clock, laptop not Pi -- this sweep characterizes the
TIME-VS-ITERATIONS SHAPE, not the Pi's absolute number, which is already
measured separately in Stage 1): n_iterations=3 median=295.5ms,
5=435.5ms, 7=575.9ms, 10=793.0ms, 15=1162.7ms, 25=1861.4ms. Near-perfectly
LINEAR in n_iterations (~75-98ms/iteration, slightly sub-linear from fixed
per-call overhead amortizing) -- confirms the theoretical model from the
earlier RANSAC-theory discussion empirically.

TABLE 2 (prediction error): n_iterations=3 median=193.6mm IQR=151.0mm,
5=191.6/151.2, 7=190.3/151.8, 10=190.0/152.6, 15=189.6/154.5, 25=189.8/154.1.
ESSENTIALLY FLAT -- median error changes <4mm across the entire 3->25 range.
DECISIVE FINDING: n_iterations can very likely be cut substantially (e.g.
15->3-5) with near-zero median accuracy cost and a 3-6x time savings --
directly addresses the original Pi RANSAC-too-slow finding (up to ~1170ms
at n_iterations=15, over the 480ms actuation budget for longer flights).

CAVEAT (not glossed over): 73 (n_iterations,flight) combinations flagged as
seed-to-seed-spread outliers (boxplot rule vs population median+1.5*IQR).
Several flights (flight_121, flight_122, flight_38, flight_45, flight_46)
stay flagged ALL THE WAY to n_iterations=25 -- more iterations does NOT
stabilize them, meaning this isn't simply "not enough iterations yet."
CONNECTS TO TASK B: 2026_07_21_gym/flight_22 and flight_125 (two of Task
B's pipeline-divergence flights) are ALSO flagged here, using PLAIN ELLIPSE
detections with no rect kernel involved at all -- suggests these specific
flights have a structurally marginal/small candidate pool that makes them
RANSAC-fragile independent of kernel choice, consistent with Task B's
"candidate-pool robustness margin at low N" mechanism (decision 66), not a
rect-kernel-specific issue.

Output: data/trajectory_fit_comparison/ransac_iterations_sweep/
(ransac_sweep_raw.csv 22367 rows, table1_wallclock_by_niterations.csv,
table2_error_by_niterations.csv, seed_spread_outlier_flights.csv,
excluded_flights.csv). No plots per explicit instruction.

## Next
Both Task A and Task B complete and logged. Awaiting Chin Wei's direction
on what to prioritize next given remaining time to the 9 Aug freeze.

## [progress, 19:20] Two report figures from the RANSAC sweep, for thesis inclusion

New file: src/stereo/ransac_sweep_figures.py. Read-only against existing sweep
outputs (ransac_sweep_raw.csv, table1/table2 CSVs) -- no CSV regenerated or
modified.

Before plotting: owner explicitly instructed "confirm the number before
plotting, don't assume" for Figure 1's reference line. Searched worklog +
decision log + context.md -- no prior "corrected" RANSAC-specific time budget
was ever actually computed (every earlier mention just compared RANSAC's raw
time against the raw ~480ms budget directly). Proposed a derivation
(480ms - 430ms observation window = ~50ms residual) via AskUserQuestion.
Owner corrected the framing: 430ms is a duration PERCENTILE (P5 of total
flight span), not a subtractable budget component, and the true RANSAC
allowance is (design-point flight duration) minus 430ms minus triangulation
minus non-RANSAC fit overhead minus comms minus actuation latency -- NOT
yet derivable since actuation latency has never been measured in this
project. Resolution: kept 480ms on the figure but relabeled it explicitly as
an upper bound (not "the RANSAC budget"), with a footnote spelling out what
still needs subtracting and why it can't be done yet.

Palette: dataviz skill's validated default (references/palette.md), light
mode (static print/thesis figure, not an interactive HTML chart -- the
skill's interaction-layer requirements don't apply, its color/marks/legend
rules do). Blue (#2a78d6, slot 1) + red (#e34948, slot 8) validated as a
pair via scripts/validate_palette.js before use: CVD dE 21.6 (protan),
normal-vision dE 32.3, both clear of the 8/15 floors -- did not eyeball it.

Visual QA (skill step 7 -- "render it and look at it, the validator checks
color not layout"): first render had two real collisions, both caught by
actually viewing the PNGs, not assumed clean from the code: Figure 1's
480ms-ceiling annotation text overlapped the p95 data line/marker at
n_iterations=10; Figure 2's legend (placed upper-right, the obvious default)
sat directly on top of the red data line, which spans nearly the full
plot width at the top of the y-range. Fixed by moving Figure 2's legend
below the axes entirely (bbox_to_anchor, matching how the population and
unstable-subset series both span most of the vertical range with no clear
internal gap) and replacing Figure 1's inline annotation with a short
in-plot label + a footnote below the axes (same external-to-the-data-area
pattern). Re-rendered and re-viewed both before calling it done.

Output (data/trajectory_fit_comparison/ransac_iterations_sweep/figures/):
- figure1_ransac_wallclock_vs_niterations.png: 2391x1671px @ 300 DPI (7.97x5.57in).
  Linear fit: 71.4 ms/iteration (confirms the theoretical linear-cost model
  from the earlier RANSAC-theory discussion, empirically).
- figure2_ransac_error_vs_niterations.png: 2370x1430px @ 300 DPI (7.90x4.77in).
  Makes visually explicit what the raw sweep numbers already showed: population
  median (~190mm) stays essentially flat across all n_iterations while the
  7-flight structurally-unstable subset sits far above it (~260-301mm) and
  stays elevated even at n_iterations=25 -- visual confirmation this is a
  separate population, not just the tail of the same distribution.

## Next
Figures done. Both tasks (A and B) plus their figures are complete and
logged. Nothing else outstanding from the current punch list.

## [RESULT, 19:37] Unstable-subset re-aggregation -- n_iterations doesn't explain or fix this subset's instability

New file: src/stereo/ransac_unstable_subset_analysis.py. Read-only against
ransac_sweep_raw.csv (no new RANSAC execution) -- re-aggregated the same 7
flights (2026_07_21_gym/flight_121,122,38,45,46,22,125) already used in
Figure 2's red series, this time as their own standalone table+figure.

Table 3 (data/trajectory_fit_comparison/ransac_iterations_sweep/
table3_unstable_subset_error_by_niterations.csv): median error 260.1mm
(n=3,5) -> 301.4mm (n=7 onward, flat). Seed-std (median across the 7
flights' own per-seed std) bounces 137-201mm with NO clean trend vs
n_iterations, vs population's smooth 19.0->40.8mm (2.15x) widening as n
drops from 25 to 3.

KEY FINDING: subset seed-std is 5-8.5x the population's AT EVERY
n_iterations tested, INCLUDING n=25 -- this is not a low-iteration-count
problem, the instability is structural and present regardless of how much
RANSAC searches. Subset's own n=25->n=3 widening ratio (1.47x) is actually
SMALLER (proportionally) than the population's (2.15x) -- cutting
iterations does not disproportionately punish this subset in relative
terms; it was never stable to begin with in absolute terms.

ANSWER to "is n_iterations=3 safe for this subset": yes for median accuracy
(260.1mm at n=3 vs 301.4mm at n=25 -- no cost, arguably favorable, though
likely noise given the spread involved). The reliability question is
malformed for this subset -- n=3 isn't less safe than n=25, neither is
safe (seed-std 137-201mm throughout vs population's 19-41mm). Confirms
Task B's diagnosis (decision 66): candidate-pool-driven instability, not
an iteration-count problem -- more iterations doesn't fix it, so keeping
iterations high "for safety" on these flights specifically would be a
wasted assumption. If n_iterations gets cut to 3-5 for the real-time win
(justified for the other ~143 flights per Task A), this 7-flight subset
needs a SEPARATE intervention (flagging/different handling), not higher
iteration count.

Output: table3_unstable_subset_error_by_niterations.csv,
figures/figure3_unstable_subset_error_vs_niterations.png (2370x1459px @
300 DPI). Same palette/style as Figure 1/2 (dataviz skill), checked for
layout collisions before reporting -- none found this time.
- [19:44:43] === ransac_threshold_sweep.py starting ===
- [19:44:43] Confirmed production RANSAC_INLIER_THRESHOLD_MM=75.0 (single definition site, trajectory_fit.py -- no duplicate hardcode found elsewhere)
- [19:44:43] 150 eligible flights (same set as ransac_iterations_sweep.py), n_iterations FIXED=3, thresholds=[50.0, 75.0, 100.0, 125.0, 150.0]
- [19:46:17] Timing pilot: 18.70s/flight -> projected serial 93.5s
- [19:46:28] === ransac_threshold_sweep.py starting ===
- [19:46:28] Confirmed production RANSAC_INLIER_THRESHOLD_MM=75.0 (single definition site, trajectory_fit.py -- no duplicate hardcode found elsewhere)
- [19:46:28] 150 eligible flights (same set as ransac_iterations_sweep.py), n_iterations FIXED=3, thresholds=[50.0, 75.0, 100.0, 125.0, 150.0]
- [19:47:41] Timing pilot: 14.74s/flight -> projected serial 2210.7s
- [19:53:59] Batch complete: 145 flights in 378.0s, 0 skipped, 18750 total rows
- [19:54:00] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\ransac_distance_threshold_sweep\ransac_threshold_sweep_raw.csv: 18750 rows
- [19:54:00] === ransac_threshold_sweep.py raw run complete ===

## [RESULT, 19:55] RANSAC inlier-distance-threshold sweep -- threshold affects Jaccard but not accuracy for the unstable subset

New files: src/stereo/ransac_threshold_sweep.py (raw sweep, n_iterations FIXED
at 3 per decision 68, fit_window=430ms, threshold swept [50,75,100,125,150]mm,
same 150-flight eligible sample as the n_iterations sweep, 25 seeds), 
src/stereo/ransac_threshold_sweep_aggregate.py (4 tables), 
src/stereo/ransac_threshold_sweep_figures.py (3 figures).

Verified RANSAC_INLIER_THRESHOLD_MM=75.0 is defined exactly once
(trajectory_fit.py:241), every consumer imports by name -- no duplicate
hardcode anywhere, confirmed via grep before building on it.

Full sweep: 150 flights x 5 thresholds x 25 seeds = 18750 target rows, 18533
succeeded (217 fit_failed, concentrated at threshold=50mm -- population
3571/3750 and subset 106/175 expected rows at that threshold specifically,
vs full counts at 75-150mm -- the tightest threshold causes outright RANSAC
failures (can't find >=8 inliers at all), not just worse fits). Timing
pilot 14.74s/flight -> projected 36.8min serial; parallelized batch done in
378s (~6.3min).

RESULTS:
- Table 1 (population): error flat 188-197mm across all thresholds (matches
  the n_iterations sweep's own population-insensitivity finding). Seed-std
  drops 54.2mm(50mm)->17.3mm(150mm), 3.1x, as threshold loosens.
- Table 2 (unstable subset): error INCREASES as threshold loosens --
  288.4mm(50mm) -> 260.1mm(75mm, production, the BEST point in the sweep) ->
  303.6 -> 311.7 -> 328.4mm(150mm). Seed-std drops 222.8mm->106.9mm (2.1x),
  same direction as population but off a much higher base.
- Table 3 (Jaccard, decisive table): mean overlap across the 7 flights rises
  substantially and consistently, 0.573(50mm)->0.878(150mm), +0.305, EVERY
  one of the 7 individual flights shows the same rising trend (e.g.
  flight_125: 0.408->0.920). Threshold DOES genuinely affect which points
  get selected as inliers -- not irrelevant.
- Table 4 (inlier count): subset's mean inlier count nearly doubles
  (9.7->19.0) but stays below population's at every threshold (14.9->23.5)
  -- fewer good candidate points available regardless of threshold.

EXPLICIT CONCLUSION (as required): Jaccard rises meaningfully, but does NOT
coincide with error improvement -- the opposite happens, error gets worse as
threshold loosens for this subset. Interpretation: loosening the threshold
makes RANSAC's answer more REPEATABLE (rising Jaccard, falling seed-std) by
admitting points farther from the true trajectory into the inlier pool --
trading instability for being CONSISTENTLY WRONG, not fixing the underlying
problem. Refines (not simply confirms or refutes) decision 66: threshold and
candidate-pool size are two symptoms of the same root cause (too few good
points available for these 7 flights), not independent levers. Production's
75mm is close to this subset's actual best median-error point in the sweep
-- loosening it would be a real regression dressed up as "more stable."

Figures (data/trajectory_fit_comparison/ransac_distance_threshold_sweep/figures/,
all 300 DPI, checked for layout collisions before finalizing -- one found and
fixed, Figure 1's "production (75mm)" label initially collided with the
x-axis tick labels, moved to the top of the vertical reference line instead):
figure1_threshold_error_population_vs_subset.png (2370x1437px),
figure2_threshold_jaccard_unstable_subset.png (2370x1445px, 7 individual-
flight lines in muted gray de-emphasis + bold red subset-mean line, per the
dataviz skill's guidance for >3-series contexts where full pairwise CVD
distinctness can't be guaranteed), figure3_threshold_inlier_count.png
(2370x1446px).

## Next
All planned RANSAC characterization work (n_iterations sweep, unstable-
subset re-aggregation, threshold sweep) is now complete. This 7-flight
subset has been characterized from three independent angles (pipeline
divergence/Task B, n_iterations, inlier threshold) and consistently points
to the same root cause: a structurally small/marginal candidate pool that
no RANSAC parameter change fixes. Awaiting Chin Wei's direction on next
priority given remaining time to the 9 Aug freeze.

## [progress, 21:08] Chin Wei ordered two follow-on steps re: throughput check

STEP 1 (remeasure rect-branch total, not estimate) -- DONE.
New file: src/pi_benchmarking/benchmark_detection_rect_total_pi.py. Single
continuous timed block per frame-pair (diff->threshold->morph-open(ellipse)
->morph-close(RECT)->exclusion->contours+moments), cam0 only, same 8-flight
Pi sample. Result: median=9.794ms, p95=9.986ms, mean=9.814ms (n=448) --
delta vs the earlier combined estimate (9.78ms) is +0.014ms (+0.1%).
Estimate confirmed accurate, not just assumed. Saved:
data/pi_benchmarking/rect_total_results_20260803.json.

STEP 2 (two-axis Pi sweep: W vs compute time/position/velocity error) --
IN PROGRESS.

Pre-check per Chin Wei's explicit instruction ("check before assuming"):
read trajectory_fit.py's simulate_drag() in full (lines 77-104). CONFIRMED:
solve_ivp's state vector IS 6-dim (position+velocity, since
state0=concatenate([p0,v0])), but simulate_drag only returns sol.y[:3].T
(position) at line 101, silently discarding sol.y[3:] (velocity) -- exactly
the gap Chin Wei suspected. Plan: write a small mirror
(simulate_drag_with_velocity) in the new Step 2 script returning BOTH,
reusing the identical ODE setup/tolerances -- does not touch trajectory_fit.py.
Will call it directly with the REAL fitted (p0,v0) params that come out of
the real, unmodified ransac_fit()/build_model_fit_predict() call chain --
only the final "evaluate the fit" step is mirrored, not the fitting itself.

Scope check before committing to a large Pi transfer: Step 2 needs REAL
image-based detection on the Pi (not reused laptop detection CSVs) since
the whole point is genuine Pi compute timing, and needs the FULL flight
population (150 flights, duration>=430ms) per Chin Wei's explicit
instruction, not just the existing 8-flight Pi sample. Checked data size
before transferring: 150 flights, both cams, 21770 frames total, 8676MB
(8.68GB). Piloted transfer speed with one flight (flight_1, 217MB) via
tar-over-ssh (avoids per-file SSH overhead of naive scp across thousands of
small PNGs): 3.02s -> ~72MB/s effective. Projected full transfer: ~2min.
Tractable -- proceeding with the real transfer now.

Design decision to keep this tractable: detect ALL of a flight's frames
ONCE (not once per W value) recording per-frame-pair Pi timing, then for
each W sum only the real measured per-frame times for frames whose
corrected-pairing timestamp falls within that W -- avoids re-running
detection 7x per flight (150 flights x 7 W values x re-detection would be
wasteful; this way detection cost is paid once per flight, ~150 times
total, and only triangulation/RANSAC genuinely need to be recomputed per
(flight,W) since those depend on which points are actually in the window).

## Next
Transfer full 150-flight data to Pi (tar-over-ssh, in progress). Then:
write the main sweep script (detect-once-per-flight, per-W aggregation,
velocity via both methods a/b), timing pilot, full run, aggregate, figures.

## [issue+fix, 21:10] First full-population transfer attempt failed silently

First tar-over-ssh transfer of the 150-flight file list completed in 0.255s
-- way too fast for 8.68GB, an obvious red flag, checked rather than trusted.
Confirmed via `du -sh` on the Pi: only the original 8 flights were there,
nothing new arrived.

Root cause (found by running tar directly, without piping to ssh, without
suppressing stderr -- the earlier attempt's `2>/dev/null` had swallowed the
real error): the file list was written by Python's `open(path, 'w')` on
Windows, which defaults to CRLF line endings. Every path in the list had a
trailing `\r`, so tar was looking for files literally named
"...ball_in_frame\r" and failing "Cannot stat" on all 450 entries silently
(no lines matched, so the archive built empty-but-valid, no error surfaced
through the ssh pipe).

Fixed: regenerated the file list with `open(path, 'w', newline='\n')` to
force LF-only output. Re-running the transfer now (background, task
bj3l4s6w1) -- will confirm real size lands on the Pi before proceeding to
the sweep script, not just trust it worked this time either.

## Next
Confirm transfer actually completed with real data (check du -sh on Pi
data/ after). Then write simulate_drag_with_velocity mirror + main sweep
script while transfer/checks proceed.

## [issue, 21:16] Pilot run (3 flights) surfaced a real detect-time undercount bug

Full data transfer confirmed correct (8.7GB, 21846 frames landed). Wrote
src/pi_benchmarking/two_axis_fit_window_sweep_pi.py + simulate_drag_with_velocity
(mirrors trajectory_fit.simulate_drag exactly, keeps sol.y[3:]/velocity which
the original discards -- confirmed by reading the source first, per Chin
Wei's explicit "check before assuming"). Compiled clean, 3-flight pilot ran
in 5.15s/flight -> projected ~13min for the full 150.

BUG found by actually checking the pilot's numbers, not just that it ran
without error: at W=150ms, flight_11 showed detect_sum_ms=94.95ms for
n_points=10 (needs 20 individual frame detections, 10/cam). Expected
~196ms (20 x the confirmed 9.794ms/frame from Step 1); got roughly half.

Root cause: detect_flight_timed() runs N_WARMUP_PAIRS=5 UNTIMED per camera
(same convention as every earlier Pi benchmark script) and the per-frame
timing dict (t0_ms/t1_ms) has NO ENTRY for those warm-up frames by design.
Later, when summing real per-frame times for an arbitrary W-limited window
via `t0_ms.get(f, 0.0)`, any window frame that happens to fall within the
first-5-processed (warm-up) frames per camera silently contributes 0.0
instead of erroring -- and the EARLIEST points in any W-window are exactly
the ones most likely to overlap the warm-up frames, especially at small W.
This systematically UNDERCOUNTS detect_sum_ms, worse for smaller W --
exactly the bias that would make the design-target result look more
favorable than reality. Caught by checking real numbers against the
already-confirmed Step 1 baseline, not assumed correct because the script
ran without throwing.

FIX: move cache-priming (exclusion_mask's fillPoly cache, cv2/TBB thread
pool spin-up) to a ONE-TIME global warm-up before the flight loop starts
(dummy calls for both cam0 and cam1, since apply_exclusion caches per
cam_name+shape), then time EVERY frame of EVERY flight for real -- no
more per-flight warm-up exclusion, no more silent-zero risk. Re-running
the pilot to confirm before the full 150-flight run.

## Next
Apply the fix, re-transfer, re-pilot, verify detect_sum_ms now matches
Step 1's ~9.79ms/frame baseline before committing to the full run.

## [progress, 21:22] Step 1 confirmed correct + Step 2 undercount fix VERIFIED

Verification of the global-cache-warmup fix (pilot2 results, post-fix): per-frame
detect cost (detect_sum_ms / (n_points*2)) now comes out 9.50-9.59ms across all
7 W values and all 3 pilot flights -- consistent with Step 1's directly-measured
9.794ms/frame baseline (small ~0.2-0.3ms residual plausibly thermal/run-to-run
variance, not a systematic undercount like before). Confirms the fix is correct;
proceeding to the full 150-flight run.

Launching full run: two_axis_fit_window_sweep_pi.py --flights all_flights_manifest.json
(150 flights, no --pilot flag) on the Pi, background, projected ~13min at
~5.1s/flight.

## [RESULT, 21:35] Step 2 full 150-flight sweep complete -- DECISIVE, and worse than hoped

Pi run: 150/150 flights, 627.1s wall clock (4.18s/flight), zero errors. Pulled to
data/pi_benchmarking/two_axis_full_20260803.json. Aggregated via new
src/stereo/two_axis_sweep_aggregate.py (read-only against the JSON) into
data/pi_benchmarking/two_axis_sweep/{two_axis_sweep_raw.csv (1050 rows),
two_axis_sweep_summary_by_W.csv (7 rows)}.

**Per-W summary** (n_ok/150 eligible after duration-buffer filtering; all times ms
unless noted):

| W | n_ok | n_pts med | detect_sum med | ransac med | compute med | compute p95 | W+C med | W+C p95 | pos_err med(IQR) mm | vel_a med(IQR) mm/s | vel_b med(IQR) mm/s |
|---|---|---|---|---|---|---|---|---|---|---|---|
|150|81/150|10|191.4|75.8|268.2|286.1|418.2|436.1|409.1(344.6)|362.3(349.3)|6960.5(7805.0)|
|200|120/150|13|248.9|88.4|337.6|351.4|537.6|551.4|311.6(322.4)|277.5(278.1)|5946.8(7904.0)|
|250|131/150|16|-|-|401.7|417.4|651.7|667.4|270.6(226.7)|224.8(236.2)|5918.6(8085.2)|
|300|144/150|19|-|-|466.8|491.0|766.8|791.0|251.5(234.8)|208.6(264.0)|6145.9(7902.8)|
|350|148/150|22|-|-|536.5|557.0|886.5|907.0|235.3(188.6)|185.0(202.2)|5982.1(7935.0)|
|400|146/150|25|-|-|601.1|619.5|1001.1|1019.5|206.4(164.9)|136.7(134.5)|6048.3(8011.7)|
|430|145/150|26|493.7|131.9|622.2|645.9|1052.2|1075.9|192.2(147.2)|128.2(126.8)|6167.5(8012.3)|

**HEADLINE**: largest W with MEDIAN(W+compute)<=430ms is W=150ms (418.2ms median,
436.1ms p95 -- already over at p95). **NO swept W satisfies the p95 criterion** --
even the smallest W=150ms tail exceeds 430ms. At the W=150ms headline point:
position error median=409.1mm (IQR 344.6mm), vel_a median=362.3mm/s (IQR 349.3),
vel_b median=6960.5mm/s (IQR 7805.0) -- both far worse than the W=430ms fixed-window
numbers used throughout the rest of tonight's session (192.2mm position error),
because so few points are available this early.

**Root cause, confirmed from the breakdown, NOT RANSAC**: detect_sum dominates
compute at every W (191ms of 268ms total at W=150, i.e. 71%; grows to 494ms of
622ms at W=430, i.e. 79%). RANSAC (n_iterations=3, the decision-68 setting) is a
minority cost throughout (76-132ms). Per-point detection cost is serial-both-cams
at ~19ms/point (2 x ~9.5-9.6ms/cam, matching Step 1's rect-branch baseline almost
exactly) -- and this compounds: needing N points costs ~19ms*N of real wall-clock
detection time, which grows faster than the observation window W itself once
enough points are needed. **This is a new, sharper finding than the earlier
throughput check**: that check evaluated per-frame serial-both-cam cost
(~19.5ms) against the 16.6ms/60fps SINGLE-frame budget and called it "sufficient"
-- but did not evaluate the CUMULATIVE effect of that per-frame deficit compounding
across an entire fit window's worth of frames. Flagging this discrepancy honestly
rather than silently reconciling it; not re-litigating the original throughput
check's own scope here.

**Velocity method (a) vs (b): DIVERGE meaningfully.** Pooled medians: method(a,
full-trajectory self-consistency check) = 195.0mm/s, method(b, independent
2-3-point finite difference) = 6119.0mm/s -- **31.4x ratio**. Method (b) has 2.3%
(21/915) extreme outliers >10x its own median (small-dt finite-difference
amplification, as anticipated in the original task spec). Per instruction: NOT
collapsing into one number, flagging the divergence rather than picking one as
authoritative. Method (a) is inherently optimistic (same model queried on more
data, self-consistency not independent ground truth); method (b) is noisier but
genuinely independent -- true velocity accuracy is somewhere in between and
likely closer to (a)'s order of magnitude given (b)'s known amplification
mechanism, but this is not asserted as fact.

## Next
Generate 3 figures via dataviz skill (W vs time-consumed-vs-430ms-line, W vs
position error, W vs velocity error both methods). Log Step 1+2 to decision log.

## [progress, 21:50] Figures generated + QA'd, decisions logged, task complete

3 figures generated via src/stereo/two_axis_sweep_figures.py (dataviz skill
conventions: validated blue/red pair from earlier this session, light mode,
static PNG). Visual QA caught one real collision on first render (figure 1's
"430ms actuation budget" annotation overlapped the W=150 data markers) --
fixed by repositioning to the top-right/W=430 end of the axis, clear of all
data. Figures 2 and 3 were clean on first render. Final set:
data/pi_benchmarking/two_axis_sweep/figures/{figure1_W_vs_time_consumed.png,
figure2_W_vs_position_error.png, figure3_W_vs_velocity_error.png}.

Logged Step 1 (decision 71) and Step 2 (decision 72) to claude/decision_log.md
with full evidence trails, the undercount-bug fix, and the headline result.

**Task complete.** Both steps of the original two-part instruction are done:
Step 1 confirmed the 9.78ms estimate accurate (+0.1% delta). Step 2's full
150-flight sweep found NO W in [150,430]ms clears the 430ms budget at p95 --
detection (not RANSAC) is now the dominant real-time cost, reversing this
session's earlier RANSAC-focused framing. This is a genuinely negative
result worth surfacing prominently, not a clean pass.
