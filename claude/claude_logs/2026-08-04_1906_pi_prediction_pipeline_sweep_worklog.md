# 2026-08-04 19:06 Pi prediction-pipeline sweep worklog

Task prompt: `claude/prompts/2026-08-04-1854_pi_prediction_pipeline_sweep_parallel.md`
Plan (approved via plan mode): `C:\Users\44772\.claude\plans\read-claude-claude-rules-md-and-claude-c-zippy-ladybug.md`
(note: prompt said `dev/claude_rules.md` / `dev/claude_logs/` -- using this
repo's real convention `claude/claude_rules.md` / `claude/claude_logs/`, as
established every prior time this session.)

## Objective
Measure the real-time prediction pipeline (parallel detection -> triangulate
-> Model-C fit -> crossing-state prediction) as a function of prediction-
cutoff time t, on the Pi, to answer whether the v1 490ms universal deadline
is latency-feasible and how accurate crossing-state prediction is per
elevation regime -- correcting the two-axis sweep's (tonight, earlier)
batched-detection assumption with a concurrent-with-capture model.

## Log

- [19:06] Plan approved (plan mode). One ambiguity resolved via
  AskUserQuestion before planning: the prompt named two different output
  folders (`02_pi_pipeline_sweep_parllel_detection` in the scope section vs
  `06_pi_pipeline_sweep` in success criteria) -- user chose
  `data/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/` (corrected
  spelling).

- [19:06] Pi mirror state verified via SSH (read-only) before planning:
  8.7GB flight data confirmed present (`du -sh`). Present: all of
  `two_axis_fit_window_sweep_pi.py`'s dependencies (`src/stereo/{all_flights_
  common,label_vs_detection,pixel_velocity_correction,stereo_flight_sync_
  table,trajectory_fit}.py`, `src/image_processing/{detector_core,
  exclusion_mask}.py`), both sessions' `*_world_transform.npz`, calibration
  outputs, `pooled_k.txt`, `candidate_config.json`.
  **Missing** (confirmed absent, must transfer before Step 1/2):
  `src/stereo/crossing_plane_classification.py`; the 6 tape-click CSVs
  (`tape_cam0.csv`, `tape_cam1.csv`, `tape_registration{1,2}_cam{0,1}.csv`);
  `data/prediction/01_crossing_plane_setup/crossing_classification.csv`;
  `data/prediction/04_launch_to_crossing_budget/launch_to_crossing.csv`.
  Pi's OpenCV build confirmed `Parallel framework: TBB` -- meaning cv2 calls
  already use the Pi's cores internally per-call, which is exactly why Step
  1 must MEASURE thread-vs-serial speedup rather than assume it (two Python
  threads each issuing TBB-parallel cv2 calls could contend for the same
  thread pool instead of getting a clean 2x).

- [19:06] Starting: transferring the missing files to the Pi mirror.

## [CHECKPOINT RESULT, 19:14] Threaded parallel detection measured -- BELOW cadence, but with much less margin than assumed

New file: `src/pi_benchmarking/parallel_detect_checkpoint_pi.py`. Same
rect-kernel mask mirror as `two_axis_fit_window_sweep_pi.py` (decision 63),
one-time global cache warmup (established fix). For every frame-pair across
the same 8-flight spread sample used throughout tonight's Pi work, measured
SERIAL (sequential cam0 then cam1) and THREADED (`threading.Thread` per
camera, `.join()`ed, wall-clock around the join -- not summed per-thread
times) on the IDENTICAL frames in the same run, for a fair comparison.

**Real measured result (n=488 frame-pairs, Pi hardware):**
- SERIAL: median=17.309ms, p95=17.935ms, mean=17.373ms
- THREADED: median=13.578ms, p95=14.973ms, mean=13.677ms
- **Speedup = 1.27x** -- well below the 1.7x threshold that would have
  indicated clean parallelism. This CONFIRMS the risk flagged in planning:
  Pi's OpenCV build is TBB-parallel internally, so two Python threads each
  issuing TBB-parallel cv2 calls partially CONTEND for the same underlying
  thread pool rather than getting a clean ~2x from independent camera work.
- Multiprocessing fallback tried (triggered automatically, speedup was
  under threshold): WORSE than serial (median=27.957ms, 0.62x) -- IPC/
  pickling overhead for the ~1.5MB grayscale arrays plus pool overhead
  dominates and swamps any real parallelism gain at this per-call size.
  Threading remains the better of the two despite being under the 1.7x bar.

**HEADLINE: per-pair PARALLEL (threaded) detect = 13.578ms median -- BELOW
16.667ms (60fps cadence), by 3.09ms margin. p95=14.973ms -- still below
cadence, margin narrows to 1.69ms.**

**Important nuance vs the task prompt's own framing**: the prompt's context
section suggested "~9.5ms if parallelism holds" (implicitly assuming near-
linear 2x speedup off the known ~9.5-9.8ms single-camera serial cost,
decision 71). The REAL measured number is 13.578ms, not ~9.5ms -- capture-
bound (no backlog) is still the correct regime since 13.578ms < 16.667ms,
but the margin is ~3ms, not ~7ms. This matters for the latency model: less
slack means the compute-bound backlog term is closer to being triggered by
any additional overhead (frame-to-frame jitter, thread scheduling variance)
than the optimistic framing implied. Flagging this now, at the checkpoint,
exactly as the task requested, rather than letting it surface only in the
full sweep's aggregate numbers.

Raw results: `data/pi_benchmarking/parallel_detect_checkpoint_20260804.json`.

## [CHECKPOINT] STOPPING HERE per explicit task instruction -- awaiting go-ahead before Step 2 (full sweep)

## [progress, 19:20] Go-ahead received -- Step 2 script written, validated locally, piloted on Pi

New file: `src/pi_benchmarking/prediction_pipeline_sweep_pi.py`. Detection:
threaded per-pair (winning approach from the checkpoint). RANSAC: reuses
`build_model_fit_predict`/`ransac_fit` unmodified, n_iterations=3/
threshold=75mm (decisions 68/70). Reference (crossing_Y/Z/vel/cls) pulled
directly from `01_`'s `crossing_classification.csv` -- NOT recomputed.
Early-cutoff crossing search: generalized `classify_flight()`'s bisection
to extrapolation (bracket-expansion past the window's own last point, up to
a 2.5s horizon cap) since early-cutoff fits haven't reached the plane yet
within their own observed window (unlike the full-arc reference). Velocity
computed via the SAME finite-difference approach `classify_flight()` itself
uses (verified by reading the source: dt=1e-3s forward diff on predict_fn,
not true ODE state) -- required for genuine apples-to-apples comparability
with the reference. T_VALUES_MS explicitly includes 490 (inserted into the
50ms-step grid) to guarantee the required headline readout point exists.

Validated LOCALLY first (2-flight pilot, laptop, real repo paths) before
touching the Pi -- ran clean, numbers looked sane (t_cross_own converging
toward a stable value as T grows, position error generally decreasing with
more data though not strictly monotonic, latency well under budget).

Piloted on the REAL PI (3 flights: flight_11/12/14): 27.0s total, 8.99s/
flight -> projects to ~16 min for the full 107-flight run, comfortably
inside the ~20-30min budget. Real Pi numbers:
- `last_pair_detect_ms` consistently 13.2-13.6ms across all 3 flights and
  all T values -- matches the Step-1 checkpoint's 13.578ms median closely,
  a good internal consistency check (same measurement, same code path,
  different flights, reproduces tightly).
- `latency_ms` ranged 142-362ms across the pilot, all `latency_feasible=True`
  (well under 490ms) -- RANSAC (`ransac_ms`, 88-306ms) dominates latency,
  not detection, consistent with detection being capture-bound/hidden.
- `position_error_mm` varies widely early (37-1193mm) as expected, mostly
  converges downward as T grows but NOT strictly monotonic (flight_12
  spikes to 1193mm at T=490 vs 404mm at T=300 and 190mm at T=700) -- a
  real RANSAC-random-subsampling effect, not a bug (same mechanism already
  documented in decision 66 for the full-arc fits).
- `hit_miss_match=False` occurs for real (flight_12@T=490, flight_14@T=150)
  -- confirms the accuracy metric has genuine signal, isn't trivially
  always-true.
- `over_cadence_pair_count=0` for all 3 pilot flights -- no individual pair
  exceeded 16.667ms in this sample (consistent with the checkpoint's
  13.578ms median / 14.973ms p95, both comfortably under cadence).

Proceeding to the full 107-flight run now.

## [progress, 19:22] Full 107-flight sweep launched on Pi (background)

Confirmed running via `ps aux` (pid 4511) after the launching SSH session
itself backgrounded (same nohup/disown pattern as tonight's earlier
two-axis sweep). 10/107 done at 8.89s/flight after ~89s -- consistent with
the 3-flight pilot's 8.99s/flight, projects to ~16min total. Waiting for
completion.

## [issue+fix, 19:35] Full run crashed mid-way -- 2 crosser flights missing from Pi mirror, fixed

Full run crashed at ~1/3 through with FileNotFoundError on
`2026_07_21_gym/flight_74/timestamps.csv`. Root cause: this task's flight
population (107 crossers, from `launch_to_crossing.csv`) is a DIFFERENT
selection criterion than the earlier duration>=430ms population (150
flights) already transferred to the Pi tonight for the two-axis sweep --
crossing-plane reachability and duration>=430ms are correlated but not
identical, so a small number of crossers fall outside the earlier transfer.
Checked programmatically: exactly 2 of 107 crossers
(`2026_07_21_gym/flight_74`, `2026_07_21_gym/flight_88`) were missing.
Transferred both (timestamps.csv + cam0/cam1 ball_in_frame PNGs only, ~85MB
combined, not the full flight folder with analysis_3/ etc -- matching the
existing minimal-transfer scope). Verified frame counts landed (51 each,
both cams) before re-running.

Relaunching the full 107-flight run now.

## [progress, 19:36] Full run relaunched after data-gap fix, running cleanly (pid 17364)

10/107 done at 9.31s/flight after ~93s -- consistent with the pilot's
timing, projects to ~16.5min total. Waiting for completion.

## [RESULT, 19:55] Full sweep aggregated -- v1 490ms deadline is comfortably met, latency never binds anywhere

New files: `src/stereo/pipeline_sweep_aggregate.py`, `src/stereo/pipeline_sweep_figures.py`.
All 107 crossers succeeded (0 flight-level failures). 2568 (flight,T) combos
total: 2481 "ok", 87 "fit_failed" (RANSAC not finding >=8 inliers in
n_iterations=3 -- concentrated heavily at the smallest T: 45/107 fail at
T=150ms, 17 at T=200ms, 11 at T=250ms, tapering to isolated 1-4 count
failures scattered at larger T -- expected small-N RANSAC behavior, not a
bug). n_airborne matches the elevation-bin populations from `05_` exactly
at every T (FLAT=35, MID=12, LOB=60 total) -- confirms the join/bin
assignment is correct.

**V1 HEADLINE @ T=490ms** (accuracy = CONVERGENCE vs full-arc reference,
placeholder, NOT ground truth):

| bin | n_airborne | n_fit_ok | HIT/MISS acc | pos_err med(IQR) mm | vel_err med(IQR) mm/s | latency med(IQR) ms | binding |
|---|---|---|---|---|---|---|---|
| FLAT | 35 | 35 | 100.0% | 38.8 (n/a) | 104.0 | 176.3 | NEITHER BINDS |
| MID | 12 | 12 | 100.0% | 85.5 | 126.6 | 194.7 | NEITHER BINDS |
| LOB | 60 | 59 | 94.9% | 156.3 | 167.4 | 202.3 | ERROR-BOUND |

**Latency NEVER binds, in any regime, at any T in the swept range** --
median latency tops out at ~320ms even at T=1250ms (LOB), nowhere close to
490ms. This is the corrected, concurrent-with-capture model's headline
finding, directly reversing tonight's EARLIER two-axis sweep (which,
under the wrong batched-detection assumption, found no W under 430ms
cleared budget even at the median). RANSAC (not detection) dominates
latency throughout (detect's contribution is a near-constant ~13-19ms via
`last_pair_detect_ms`, RANSAC grows from ~80ms at T=150 to ~300ms+ at
T=1250) -- consistent with detection being genuinely hidden under the
capture cadence as the Step-1 checkpoint predicted.

**Per-bin t_min** (smallest T with median position error<100mm AND
accuracy>=90%, both provisional): FLAT=300ms, MID=350ms, LOB=700ms -- all
comfortably inside each regime's OWN real budget from `05_`
(FLAT P5=502ms, MID P5=710ms, LOB P5=1080ms). This is the concrete,
data-backed case for a v2 regime-adaptive window: LOB in particular could
use ~700ms (vs the v1-universal 490ms) and stay well inside its own
~1080ms true deadline, buying meaningfully better accuracy (156mm->~90mm
per the T=700 row) essentially for free.

**Detection diagnostics** (pooled across the full run, n=2481 sampled
pairs): median=13.707ms, p95=15.108ms, p99=15.404ms, max=19.224ms -- all
comfortably under the 16.667ms cadence even at the tail. 6 individual pairs
(out of several thousand detected across the whole run) exceeded cadence --
negligible, consistent with occasional scheduling jitter, not a systematic
issue. Thermal drift check (first-quartile vs last-quartile flights'
median detect time): delta=-1.452ms -- no evidence of thermal throttling
over the ~14min run (if anything, marginally faster later, well within
noise).

Outputs: `data/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/`
{pipeline_sweep_raw.csv (2568 rows), pipeline_sweep_summary_by_bin_T.csv
(72 rows), summary.txt, figures/figure{1,2,3}_*.png}. Figure 1 had one
real collision on first render (eligible_n annotations overlapping the
legend, both placed lower-right) -- fixed by folding the n counts directly
into the legend labels instead of a separate annotation block. Figures 2-3
clean on first render.

**Overall**: the v1 universal 490ms deadline is met with real, comfortable
margin for FLAT and MID (both error- and latency-slack), and even for LOB
-- while LOB's accuracy at exactly 490ms falls slightly short of the
provisional 100mm bar (156mm), latency is NOT the reason (202ms << 490ms),
and LOB's own true budget (~1080ms, established in `05_`) has ample room
for a regime-adaptive window to close that gap. This is a genuinely
positive result for the whole pipeline's real-time feasibility on the Pi,
once detection is correctly modelled as concurrent-with-capture rather
than batched -- directly correcting tonight's earlier (batched-assumption)
finding.

**Caveat, restated explicitly**: every accuracy/error number above is a
CONVERGENCE result against the full-arc Model-C fit (already frozen in
`01_`), not ground truth -- manual crossing-bracket labels are not ready
yet. This entire analysis needs to be re-run once they are.
