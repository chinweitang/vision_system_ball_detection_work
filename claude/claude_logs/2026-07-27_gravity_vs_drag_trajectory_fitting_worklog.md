# 2026-07-27 gravity vs drag trajectory fitting -- worklog

Task: claude/prompts/2026-07-27_1818_gravity_vs_drag_trajectory_fitting.md

Compare Model A (free gravity, free a), Model B (fixed gravity, linear fit),
Model C (fixed gravity + drag, nonlinear fit) on flight_01/flight_22
(2026_07_15_gym). Phase 0: consolidate fitting code into trajectory_fit.py.
Phase 1: K discovery. Phase 2: prediction-window sweep, 6 curves/flight.

## [setup] Read-first materials

- claude/claude_rules.md: solo project, direct-to-main commits (N/A here, no
  git). Section 4: exploratory/diagnostic work goes straight in, no
  pre-approval gate -- matches this task's "Phase 0 does not pause" framing.
  Data-protection rule: never overwrite/delete files under data/ or
  calibration_outputs/ without asking -- this task only READS existing data/
  files (registration_world_transform.npz, labels, tuned detections) and
  WRITES new script outputs elsewhere, so should not trigger this.
- context.md sec 5 (prediction): gravity + quadratic drag, least-squares fit
  to initial points, coupled 3D (drag depends on |V|), not Kalman-primary --
  matches Model C's spec exactly.
- context.md sec 4.6 (error budget) / Pattern A: fit first N frames -> predict
  -> compare to that flight's own later triangulated points, sweep N~5-25,
  predict to a *short* horizon not the full remaining arc -- this is exactly
  predict_sweep.py's existing methodology being extended, not replaced.
- Read predict_sweep.py, label_vs_detection.py, triangulate_flight.py, and
  flight_velocity_angle_binner.py (the 4th consumer of fit_constant_accel,
  named in the task's Phase 0 step 2) in full.
- Confirmed all needed data exists: registration_world_transform.npz under
  2026_07_15_gym/flight_binning/world_frame_validation/, flight_01 and
  flight_22 label CSVs (per-cam, frame_number,click1_x,...,centroid_x,
  centroid_y,... schema -- NOT the combined frame_index,cam,u,v schema
  label_vs_detection.load_points_csv expects), and tuned detections for both
  flights under data/detector_tuning/detections/03_.../2026_07_15_gym/.
- flight_01 labels: 28 rows/cam (frames 43-... roughly). flight_22: 94
  rows/cam -- much denser/longer track, good for the "full densely-labelled
  arc" Phase 1 requirement.

## [decision] Golden-output strategy for Phase 0 verification

The task's 4 before/after checks reference numbers "already established
earlier this session" in prior worklogs. This is a fresh session/conversation
with no access to those exact run artifacts, so instead: capture golden
output by running each of the 4 scripts UNMODIFIED right now (before moving
any code), then rerun after the refactor and diff against that same
just-captured golden output. This is a stronger check than matching
old-worklog numbers anyway (guarantees an apples-to-apples same-environment
comparison) and still satisfies the actual intent (refactor is
behavior-neutral). Noting this substitution explicitly per the "Considered
doing X, logging as I go" spirit.

- Found flight_01 already has combined-schema labels_uv.csv and
  analysis_3/detections_uv.csv (frame_index,cam,u,v) at the flight root --
  exactly what predict_sweep.py/label_vs_detection.py expect. flight_22 does
  NOT have these (only per-cam label CSVs + analysis_3 per-cam detections3
  CSVs) -- will need a small per-cam-to-combined adapter for flight_22 in
  Phase 1/2 scripts.

## [golden capture, pre-refactor] Phase 0 check 1/4: predict_sweep.py on flight_01

Ran predict_sweep.py on flight_01 (labels_uv.csv + analysis_3/detections_uv.csv,
calibration_outputs + 2026_07_15 extrinsics), output to a scratch dir (not
under data/). Ran clean, no gate failures. Full N=3..24 table + all plots
captured to /tmp/golden_pre/predict_sweep/predict_sweep.csv as the golden
baseline. Key checkpoints: gate accel_at_max_N ~9.9 m/s^2 (within 8-12 gate),
err_label trend slope non-positive (gate passed), gravity-aligned sanity
check passed (peak interior, negative quad coeff), world-vs-gravity-up angle
29.8 deg (within the 45 deg warn threshold, no warning printed).

## [golden capture, pre-refactor] Phase 0 check 2/4: label_vs_detection.py on flight_01

Same inputs. First run WITHOUT --force failed gate (a): K0/K1 focal lengths
~970-987 px vs expected 1500-1900 px -- this calibration_outputs intrinsics
file just doesn't match that gate's expected range (pre-existing condition,
unrelated to this task -- the gate's expected band looks tuned for a
different lens/session). Reran with --force (this is how analysis_3's
existing label_vs_detection_summary.txt in the repo must have been produced
too, since it shows the identical numbers below). Gate (c) reprojection
median 1.385 px also exceeds the 1.0 px expectation but continued via
--force; gate (d) |a|=9.732 m/s^2 within the hard band, outside nominal but
tolerated. Result: median mag=62.443mm, mean=70.153mm, SD=36.798mm,
RMS=79.218mm, p95=131.356mm, dx/dy/dz signed means +8.49/-38.31/-22.92mm --
matches the pre-existing data/.../flight_01/analysis_3/label_vs_detection_summary.txt
in the repo EXACTLY (median 62, mean 70, SD 37, RMS 79, p95 131, dx +8 dy -38
dz -23), confirming this really is a faithful "rerun of an existing analysis"
and a solid golden baseline.

## [golden capture, pre-refactor] Phase 0 check 3/4: triangulate_flight.py on flight_5

Ran on data/2026_07_21_gym/ball_flights/flight_5 (script's own default
extrinsics/tuned-detections dir, both 2026_07_21_gym). Result: baseline=
848.91mm, naive n=36 overall_rms=31.05mm (x=12.87 y=27.76 z=44.23),
paired_only identical (36 pairs, same as naive here), corrected n=36
overall_rms=31.01mm (x=12.85 y=27.71 z=44.17).

NOTE: task's prompt cites a previously-recorded "naive=29.71mm" for this same
flight from the sync-correction task's worklog -- my fresh run got 31.05mm,
not 29.71mm. Per the golden-output-strategy decision above, this isn't
treated as a red flag: the absolute match to a different session's numbers
was never the check being run here (data/detection files may have been
regenerated since, e.g. a later detector-tuning pass); the actual Phase-0
check is internal (this run vs. the SAME run after moving the code), not
cross-session number-matching. Logging the discrepancy for visibility, not
treating it as a gate failure.

## [golden capture, pre-refactor] Phase 0 check 4/4: flight_velocity_angle_binner.py 3-flight smoke test

Wrote a small scratch driver (not committed to src/) that imports
process_flight() directly and runs it on flight_1/flight_5/flight_65 in
2026_07_21_gym only (matching the original smoke-test technique from the
2026-07-25 worklog), redirecting log_append() to a throwaway scratch log file
so this verification run does NOT append to the real
2026-07-25_flight_velocity_angle_binner_worklog.md (that file belongs to a
different, already-completed task).

Result: flight_1 N=20 |a|=14.61 (flagged, outside nominal), N=30 |a|=10.78 ok
unflagged; flight_5 N=20 |a|=10.93 ok unflagged, N=30 |a|=9.43 flagged;
flight_65 N=20 |a|=8.39 flagged, N=30 |a|=9.39 flagged. The flagged rows
(flight_1 N=20, flight_5 N=30, flight_65 N=20, flight_65 N=30) match the
2026-07-25 worklog's recorded values EXACTLY (14.61/9.43/8.39/9.39, same
speed/elevation numbers) -- strong cross-session confirmation this script's
behavior hasn't drifted, and a solid golden baseline for the refactor check.

All 4 golden baselines captured. Proceeding to Phase 0 refactor: creating
trajectory_fit.py and updating the 4 consumer scripts.

## [blocker] scipy broken in this environment

Created trajectory_fit.py with Models A/B/C (fit_constant_accel,
fit_constant_accel_fixed_g, simulate_drag, fit_drag_given_k, fit_drag_free_k,
load_g_fixed). Model C needs scipy.integrate.solve_ivp + scipy.optimize.least_squares
(per task spec). Importing scipy failed hard: anaconda base env has scipy
1.7.3 against numpy 2.0.2 -- `ImportError: cannot import name 'Inf' from
numpy` (numpy 2.x removed the deprecated np.Inf alias that old scipy relies
on). Grepped the repo: scipy has never been imported anywhere else in src/,
so this isn't a "something else depends on the old pin" situation -- it's
just stale/broken.

Asked Chin Wei: upgrade scipy in-place vs. hand-roll RK4+LM to avoid touching
the shared env. Chose to upgrade. Ran `pip install -U scipy` ->
1.7.3 -> 1.13.1 (numpy<2.3,>=1.22.4 compatible). Reran load_g_fixed() as a
smoke test: up_vec=[0.0091, -0.9508, 0.3097], g_fixed=[-89.35, 9327.10,
-3038.64] mm/s^2, |g_fixed|=9810.00 -- exact match to the 9810 mm/s^2 target,
scipy imports clean now.

## [check] g_fixed sanity (task's stated "STOP if far from 9810" gate)

|g_fixed| = 9810.00 mm/s^2 exactly (by construction -- G_MAGNITUDE_MM_S2 is a
fixed constant multiplied into a unit vector, so this will always read 9810
as long as up_vec truly comes out unit-norm from the npz, which it does:
np.linalg.norm(up_vec) confirmed 1.0-normalized in load_g_fixed). Gate
passes; proceeding.

## [refactor] Moved fit_parabola_axis / fit_constant_accel / predict_at into trajectory_fit.py

- label_vs_detection.py: removed its own fit_parabola_axis def, now imports
  it from trajectory_fit.py (added the HERE/REPO_ROOT sys.path insert this
  file didn't previously have, matching predict_sweep.py's existing
  pattern).
- predict_sweep.py: removed its own fit_constant_accel/predict_at defs, now
  imports both from trajectory_fit.py; kept its label_vs_detection imports
  (load_points_csv, load_calib, triangulate) unchanged.
- flight_velocity_angle_binner.py: import switched from
  src.stereo.predict_sweep.fit_constant_accel to
  src.stereo.trajectory_fit.fit_constant_accel (one-line change, updated its
  header comment too).
- triangulate_flight.py: fit_quadratic_residual_rms's internal np.polyfit
  call replaced with the shared fit_constant_accel/predict_at (Model A).
  Verified numerically equivalent BEFORE swapping it in: synthetic 20-point
  noisy parabola, polyfit-per-axis residual vs shared-fit residual matched
  to ~1e-16 (float precision) on all 3 axes -- same polynomial family
  (p0 + v0*t + 0.5*a*t^2), just reparametrized from raw polyfit
  coefficients. Kept the t-centering (t - t.mean()) convention from the old
  code for numerical-solve stability, even though not strictly required for
  correctness.

## [verify] Phase 0 before/after checks: all 4 PASS, byte-identical

1. predict_sweep.py on flight_01: diff against golden CSV -> IDENTICAL (all
   N=3..24 rows, err_label_mm/err_det_mm/norm_a_label/norm_a_det).
2. label_vs_detection.py on flight_01: both label_vs_detection.csv and
   label_vs_detection_summary.txt -> IDENTICAL.
3. triangulate_flight.py on flight_5: stdout -> IDENTICAL, INCLUDING the
   polyfit->shared-fit swap in fit_quadratic_residual_rms (31.05/31.05/31.01mm
   overall RMS, unchanged) -- confirms the reconciliation is numerically
   silent in the real pipeline too, not just the synthetic check.
4. flight_velocity_angle_binner.py 3-flight smoke test: full stdout dict
   rows -> IDENTICAL.

All 4 match byte-for-byte. Per the task's own instruction ("proceed straight
into Phase 1 if all four match -- do not pause for a go-ahead"), continuing
directly into Phase 1 without stopping.

## [phase 1] Starting: adding Model B/C fitting functions to trajectory_fit.py (already done above, alongside load_g_fixed) -- next: drag_k_discovery.py
- [18:50:46] === drag_k_discovery.py: Phase 1 K discovery starting ===
- [18:50:46] g_fixed loaded: [  -89.35238335  9327.0996008  -3038.63936464], |g_fixed|=9810.00 mm/s^2
- [18:50:46] K estimate (physical, volleyball): K_SI~0.0308 (1/m) -> K_mm~3.075556e-05 (1/mm), sweep centered here (0.1x-5x)
- [18:50:46] flight_01: triangulated 27 labelled points [frames 43..69]
- [18:50:46] flight_01: n=27 labelled points, t span=0.433s -- starting Model A/B/C discovery
- [18:50:47] flight_01: K-sweep best K=4.464858e-05 1/mm, residual=17.76mm (range [3.08e-06,1.54e-04])
- [18:50:47] flight_01: Model C refined (free-K nonlinear fit) K=4.458347e-05 1/mm, residual=17.76mm
- [18:50:47] flight_22: triangulated 93 labelled points [frames 1..93]
- [18:50:47] flight_22: n=93 labelled points, t span=1.532s -- starting Model A/B/C discovery
- [18:50:51] flight_22: K-sweep best K=6.023847e-05 1/mm, residual=27.17mm (range [3.08e-06,1.54e-04])
- [18:50:51] flight_22: Model C refined (free-K nonlinear fit) K=6.186347e-05 1/mm, residual=27.14mm
- [18:50:51] K comparison: flight_01 K=4.458347e-05, flight_22 K=6.186347e-05, ratio=1.39x
- [18:50:51] Pooled joint fit: K=6.053818e-05 1/mm, combined_residual_rms=25.61mm (fit over 120 points across 2 flights, time origin = each flight's own first labelled frame, t=0 independently per flight)
- [18:50:51] === drag_k_discovery.py: Phase 1 K discovery complete ===

## [decision] Pooling implementation deviates from a literal single fit_drag_free_k call

Task step 7 says "pool both flights' points into one joint fit_drag_free_k
call". Read literally that would mean ONE shared (p0, v0, k) fit across both
flights' concatenated points -- but flight_01 and flight_22 are physically
unrelated arcs (different launch speed/direction/time), so a single p0/v0
forced across both would be physically meaningless and would NOT actually
answer "does one K work for both flights" (the real point of pooling) --
it would instead measure "can one straight-line-in-parameter-space ballistic
trajectory awkwardly pass through two unrelated arcs", a different and less
useful question. Implemented instead: joint_fit_shared_k() in
drag_k_discovery.py, which fits a SEPARATE (p0, v0) per flight but a SINGLE
shared k, minimizing the combined position residual across both flights'
points simultaneously (concatenated residual vector into one
least_squares call). This is the physically meaningful version of "pool for
a shared K" and still produces exactly one final K to carry into Phase 2, so
it satisfies the actual intent even though it's not the literal function
call named in the prompt. Flagging this explicitly rather than silently
picking the more sensible interpretation without saying so.

## [phase 1 results] Summary for Checkpoint 1

flight_01 (n=27 labelled points, frames 43-69, t span=0.433s):
  Model A (free gravity):   |a|=9.732 m/s^2, full-arc residual RMS=30.07 mm
  Model B (fixed gravity):  full-arc residual RMS=48.29 mm
  Model C (sweep best):     K=4.4649e-05 (1/mm), residual RMS=17.76 mm
  Model C (refined):        K=4.4583e-05 (1/mm), residual RMS=17.76 mm
  (sweep range [3.08e-06, 1.54e-04] 1/mm, i.e. 0.1x-5x the physical
  volleyball estimate K_mm~3.08e-05; best-K NOT at either sweep edge)

flight_22 (n=93 labelled points, frames 1-93, t span=1.532s):
  Model A (free gravity):   |a|=9.181 m/s^2, full-arc residual RMS=52.19 mm
  Model B (fixed gravity):  full-arc residual RMS=110.09 mm
  Model C (sweep best):     K=6.0238e-05 (1/mm), residual RMS=27.17 mm
  Model C (refined):        K=6.1863e-05 (1/mm), residual RMS=27.14 mm
  (best-K NOT at either sweep edge)

K agreement: flight_01 K=4.458e-05 vs flight_22 K=6.186e-05, ratio=1.39x --
well within the 3x "reasonable agreement" threshold I set, so pooled
automatically per decision #1 (no need to stop and ask).

Pooled (shared K, separate p0/v0 per flight, 120 points total): K=6.054e-05
(1/mm), combined residual RMS=25.61 mm.

**Full-arc residual pattern (NOT the decisive test, just this phase's own
diagnostic):** B is worse than A on both flights (fixing gravity removes a
free parameter that was silently absorbing some of the drag-shaped
deviation, so full-arc fit residual goes up) -- expected, and exactly why
Model C exists. C is dramatically better than both A and B on both flights
(17.76 vs 30.07/48.29 mm on flight_01; 27.17 vs 52.19/110.09 mm on
flight_22) -- adding drag captures real curvature that a pure parabola
(free or fixed-gravity) can't. This is a full-arc-fit signal only, NOT the
Phase 2 held-out prediction-error comparison the task is actually decided
by -- noting it here only as Phase 1's own finding, not conflating it with
the decisive test per the task's explicit instruction not to.

## [checkpoint 1 response] Chin Wei confirmed pooled K=6.054e-5, requested backfill

Requested: a results folder (data/trajectory_fit_comparison/), a CSV of the
FULL K-sweep grid (every candidate K + residual, for flight_01, flight_22,
AND pooled -- not saved to a file the first time, only summarized in the
log), a residual-vs-K plot per flight, and a bar chart comparing A/B/C
full-arc residual per flight. Then Phase 2 as originally specified, output
into the same folder.

Created data/trajectory_fit_comparison/{phase1,phase2}/ (new folder under
data/, not overwriting anything -- no data-protection concern).

Modified drag_k_discovery.py: discover_k_for_flight() now also returns the
full sweep_results list (every k tested + its residual) instead of just the
best point. Added write_k_sweep_outputs() (k_sweep.csv + residual_vs_K.png)
and write_model_comparison_outputs() (models_full_arc_residual.csv/.png).

Pooled-per-K grid derivation: the pooled model shares K but fits p0/v0
independently per flight (per the earlier design decision), so the
per-flight sweep's own per-K fit IS the per-flight-optimal fit at that K --
no need to resolve a joint optimization at every grid point. Pooled residual
at a given K = count-weighted RMS combining both flights' per-K residuals:
sqrt((n1*rms1^2 + n2*rms2^2)/(n1+n2)), same grid of K values (both flights
already use the identical np.linspace grid).
- [19:04:33] === drag_k_discovery.py: Phase 1 K discovery starting ===
- [19:04:33] g_fixed loaded: [  -89.35238335  9327.0996008  -3038.63936464], |g_fixed|=9810.00 mm/s^2
- [19:04:33] K estimate (physical, volleyball): K_SI~0.0308 (1/m) -> K_mm~3.075556e-05 (1/mm), sweep centered here (0.1x-5x)
- [19:04:33] flight_01: triangulated 27 labelled points [frames 43..69]
- [19:04:33] flight_01: n=27 labelled points, t span=0.433s -- starting Model A/B/C discovery
- [19:04:35] flight_01: K-sweep best K=4.464858e-05 1/mm, residual=17.76mm (range [3.08e-06,1.54e-04])
- [19:04:35] flight_01: Model C refined (free-K nonlinear fit) K=4.458347e-05 1/mm, residual=17.76mm
- [19:04:35] flight_22: triangulated 93 labelled points [frames 1..93]
- [19:04:35] flight_22: n=93 labelled points, t span=1.532s -- starting Model A/B/C discovery
- [19:04:40] flight_22: K-sweep best K=6.023847e-05 1/mm, residual=27.17mm (range [3.08e-06,1.54e-04])
- [19:04:41] flight_22: Model C refined (free-K nonlinear fit) K=6.186347e-05 1/mm, residual=27.14mm
- [19:04:41] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\k_sweep.csv (90 rows: 30 flight_01 + 30 flight_22 + 30 pooled)
- [19:04:41] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\residual_vs_K.png
- [19:04:41] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\models_full_arc_residual.csv
- [19:04:41] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\models_full_arc_residual.png
- [19:04:41] K comparison: flight_01 K=4.458347e-05, flight_22 K=6.186347e-05, ratio=1.39x
- [19:04:41] Pooled joint fit: K=6.053818e-05 1/mm, combined_residual_rms=25.61mm (fit over 120 points across 2 flights, time origin = each flight's own first labelled frame, t=0 independently per flight)
- [19:04:41] === drag_k_discovery.py: Phase 1 K discovery complete ===
- [19:06:31] === trajectory_model_prediction_sweep.py: Phase 2 starting ===
- [19:06:31] K_FIXED = 6.053818e-05 1/mm (Phase 1 pooled result, Checkpoint-1 approved)
- [19:06:31] g_fixed loaded: |g_fixed|=9810.00 mm/s^2
- [19:06:31] flight_01: Phase 2 prediction sweep starting
- [19:06:31] flight_01: label_common=27 frames, det_common=25 frames (tuned detections)
- [19:06:31] flight_01: target_frame=69, fit_frames=25 [44..68]
- [19:06:32] flight_01: sweep complete, 23 N-values, 0 convergence failures
- [19:06:32] flight_22: Phase 2 prediction sweep starting
- [19:06:32] flight_22: label_common=93 frames, det_common=89 frames (tuned detections)
- [19:06:32] flight_22: target_frame=93, fit_frames=89 [2..92]
- [19:06:42] flight_22: sweep complete, 87 N-values, 0 convergence failures
- [19:06:42] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep.csv
- [19:06:42] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep_flight_01.png
- [19:06:43] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep_flight_22.png
- [19:06:43] === trajectory_model_prediction_sweep.py: Phase 2 complete ===

## [phase 2 verify] Model A reproduction check (task's stated gate)

flight_01's err_A_label at N=19 = 19.2383mm -- matches predict_sweep.py's
own golden-run number (19.2mm at N=19, "min err_label" reported in that
run) almost exactly. Note: this Phase 2 script's fit_frames set (25 frames,
built from tuned detections) differs from predict_sweep.py's original
golden run (24 frames, built from stale analysis_3 detections per decision
#5) -- so exact byte-identical reproduction across the FULL curve isn't
expected or required (the two runs use different detection datasets that
produce a different label/det frame intersection), but the label-only
curve (which doesn't depend on which detections exist, only on which
frames survive the intersection) landing on the same value at the one N
where both runs happen to share the same window is a strong sanity check
that Model A's fitting logic itself is unchanged. No gate failure -- did
NOT stop.

## [phase 2 results] The decisive comparison

**flight_01** (target frame 69, N=3..25, lead time 400ms down to 17ms):
Model A (free gravity) is wildly unstable at low N (>10^4 mm at N<=4 on
both label and det), settles down and becomes competitive/occasionally
best only at N>=13 (short lead times <200ms) -- but noisily, with visible
spikes even at high N (e.g. N=20-21 jump back up). Models B and C are both
smooth, monotonically-decreasing-ish curves across the ENTIRE N range with
no wild low-N blowup. C sits at or below B almost everywhere (label and
det), i.e. adding drag on top of fixed gravity helps consistently, not just
at one N. At the largest N (shortest lead time), all three converge to a
similar ~50-100mm band.

**flight_22** (target frame 93, N=3..89, lead time up to 1500ms down to
17ms -- the longer, harder extrapolation case): the pattern is much
starker. Model A blows up to 10^4-10^5 mm at low N and has a large
secondary spike around N=44-46 (up to ~3x10^4 mm on the det curve) even at
moderate N -- badly unstable across most of the practically-useful (longer
lead time) range. Model B is flat and stable but its error plateaus around
700-1000mm for most of the range -- much worse than C. Model C is the
lowest curve (both label and det) across almost the ENTIRE N range,
including the long-lead-time region that matters operationally -- e.g. at
N=42 (t_extrap~800ms) C_label~170mm vs B_label~750mm and A in a wild spike;
C stays under 200mm from N~15 onward on the label curve. ONE exception: at
the very largest N (shortest lead time, N>=85, the least operationally
relevant regime), the det-curve ordering flips locally -- A_det (609.7mm
at N=89) briefly undercuts C_det (887.4mm) -- but this is the tail end of
the sweep, not the long-lead-time region the whole exercise is about.

**Direct answers:**
- Does fixing gravity alone help (A vs B)? Not on full-arc residual (Phase
  1 showed B worse there), but on held-out PREDICTION error (the actual
  test) -- yes, substantially, in STABILITY: B eliminates the wild
  low-to-mid-N blowups that plague A on both flights, at the cost of
  giving up A's occasional best-case low-error points at high N. B's
  absolute error level is not obviously better than A's at high N, but far
  more reliable across window sizes.
- Does drag help on top of fixed gravity (B vs C)? Yes, consistently -- C
  sits at or below B on both flights, both label and det curves, across
  nearly the entire N range, often by a large margin (e.g. flight_22 label
  at N=42: ~170mm vs ~750mm).
- Where does the full pipeline land (A vs C)? C dominates A across almost
  the entire practically-relevant range (longer lead times = lower N) on
  both flights, and matches or modestly beats A even at short lead times
  on flight_01. flight_22's det curve is the one place A briefly wins, but
  only at the shortest lead times (N>=85 of 89, t_extrap<100ms) -- the
  least useful regime for a robot needing enough reaction time.

## [continuation] RANSAC-robustified fitting (claude/prompts/2026-07-28_1118_ransac_robust_fitting.md)

New task, same worklog per instructions. Goal: add ransac_fit to
trajectory_fit.py, use it to test whether robust fitting fixes flight_22's
confirmed N~44-46 detected-points error spike (traced to the detector
picking up a hand). Scope limited to flight_01/flight_22 only, not
generalized to all flights (separate later task).

## [investigate] Locating the specific contaminated frames empirically

The task says the spike was traced "via the contact sheet" but the actual
contact sheet PNG for flight_22 is a huge (3000x34048px) grid, unreadable at
any practical resolution -- instead, identified the bad frames directly from
the triangulated det-track data (more principled anyway, and it's exactly
what RANSAC will do internally). First mapped N=44/45/46 to actual frame
numbers via fit_frames indexing: N=44 -> last_fit_frame=45, N=45->46,
N=46->47 -- so the newly-added frame at each of those steps is 45, 46, 47.
Then fit Model A (free gravity) on flight_22's FULL det track and sorted by
per-point residual: frames 44/45/47 residual 6.9-7.3 METERS, frame 46
residual 4.0m -- massively larger than the next-highest residual (~900mm at
frame 60). Confirms the contamination is exactly frames 44-47 (4 consecutive
frames), matching the task's N~44-46 spike almost exactly (the window that
newly includes these frames is where the fit -- and thus the prediction --
gets corrupted).

Side finding (NOT chasing this, out of scope per the task's explicit
boundary): frames 77/78/81 also show elevated residuals (~6.0-6.1m) on this
same full-track Model A fit -- a SECOND contamination cluster later in the
flight, distinct from the known N~44-46 case. Flagging for awareness/a
future task, not investigating further here.

## [implement] ransac_fit added to trajectory_fit.py

Added `ransac_n_iterations(min_samples, outlier_fraction, success_prob)` (standard
formula N=log(1-p)/log(1-(1-e)^s)) and `ransac_fit(t, xyz, fit_fn, predict_fn,
min_samples, inlier_threshold_mm, n_iterations, random_seed, frame_numbers)`.
Generic by design: fit_fn/predict_fn are closures the CALLER builds per model
(so ransac_fit itself never touches g_fixed/K/etc.), sample min_samples points,
fit, score every point's residual against inlier_threshold_mm, track the
largest inlier set, refit once on the winner. Returns params, residual_rms_mm,
n_inliers, accepted_frames, rejected_frames (actual frame numbers if
frame_numbers is passed).

min_samples chosen per model (task step 1's "more than bare minimum, room for
outliers within flight_01's 27 points"): A=6 (bare min 3/axis x well-conditioned
margin), B=6, C=8 (nonlinear, most margin per this session's own established
lesson re: low-N nonlinear instability from Phase 1). n_iterations computed
per min_samples at outlier_fraction=0.3 (conservative worst-case, well above
the ~8% (7/89) contamination actually seen on flight_22 -- picked before
knowing the true rate, so it's a real "worst case" not reverse-engineered),
success_prob=0.999: min_samples=6 -> 56 iterations, min_samples=8 -> 117.
random_seed=42, fixed and logged for reproducibility.

## [sanity test] ransac_fit correctly isolates flight_22's known contamination -- AND reveals a second issue

Ran ransac_fit with Model A's fit_fn/predict_fn on flight_22's FULL detected
track (89 points) at the task-specified 75mm threshold: rejected 38/89 points
(43%) -- WAY more than the ~7 known-contaminated frames. Investigated by
sorting ALL per-point residuals from a single free-fit (no RANSAC) over the
full 1.5s arc: residuals climb SMOOTHLY from ~32mm up to ~1013mm (frame 84),
THEN JUMP an order of magnitude to 3963-7508mm for exactly 7 frames: 44, 45,
46, 47 (the known N~44-46 cluster) AND 77, 78, 81 (the second cluster flagged
earlier as a side finding). This same smooth-climb-then-huge-gap pattern
holds for BOTH Model A and Model C's full-arc fit (checked both) -- so the 7
contaminated frames are trivially separable from genuine points at ANY
threshold between ~1013mm and ~3963mm, but 75mm is far too tight for a
SINGLE fit spanning the full 1.5s arc: it also flags ~30 genuinely-clean
points purely because a single global (p0,v0,[a or k]) trajectory
accumulates real spread over that much extrapolation distance from t=0 --
model-fit spread, not detector contamination.

**Decision (per task decision #2's explicit "adjust and note if evidence
suggests otherwise"):** use TWO different inlier thresholds, not one:
- Phase 2 (short local N-frame windows, matching the ~15-50mm clean-RMS
  regime decision #2 actually describes): keep the task's literal 75mm.
- Phase 1 (one fit over flight_22's FULL ~1.5s arc, a fundamentally
  different regime -- this threshold's job is only to separate the 7
  genuinely-contaminated frames from ~82 genuinely-clean ones, not to hold
  every point to short-window precision): use 1500mm, sitting centered in
  the empirically-confirmed gap (clean max ~1013mm, contaminated min
  ~3963mm, ~2.7x-3.9x margin either side).
Verified this doesn't just paper over flight_01: flight_01's own full-arc
Model A residual on its DETECTED track tops out at 91mm (median 27mm) -- so
1500mm accepts effectively all of flight_01's points too (as expected, no
known contamination there), while flight_22's 7 bad frames still sit ~2.6x
above it. Confirmed BEFORE writing this into the real Phase 1 script, not
discovered mid-run.

## [correction] Re-examined the threshold question -- reverting to a SINGLE 75mm threshold everywhere

Caught my own mistake before writing it into the real scripts: the investigation
above used flight_22's DETECTED track, but drag_k_discovery.py's Phase 1 (the
K-discovery script this RANSAC layer extends) only ever fits the LABELLED
track (triangulate_full_track uses the label LOADERS, not detections) -- so
the "1500mm Phase 1 threshold" conclusion was based on the wrong dataset for
what Phase 1 actually computes.

Checked flight_22's LABELLED full-arc Model A residuals directly: max is only
143.8mm (frame 91), median 39.8mm -- NO order-of-magnitude outlier cluster at
all. Makes physical sense: a human labeller clicking the ball's centroid
doesn't accidentally click a hand; the known contamination is a DETECTOR
failure mode, which only shows up in the DETECTED track. So Phase 1
(labelled-only) has nothing dramatic for RANSAC to find regardless of
threshold -- 75mm there will flag at most a handful of near-edge points
(where a single global parabola over the full 1.5s naturally fits worst),
not a real bug.

**Reverting to ONE threshold, 75mm, used everywhere (Phase 1 AND Phase 2),
matching the task's literal spec** -- the earlier "two thresholds" idea was
solving a problem (large full-arc spread on the DETECTED track) that only
actually arises in Phase 2, and only at the very largest N values (the
window approaching the full ~1.5s arc) -- which is BOTH the least
operationally-relevant regime (shortest lead time) AND not where the
confirmed N~44-46 bug lives. Any extra rejections 75mm causes there are a
legitimate, interpretable consequence of a single global model not fitting
a long noisy arc perfectly -- not a threshold miscalibration to paper over.
Keeping the investigation above in the log since it's genuinely useful
context (confirms WHY large-N det-curve RANSAC results may show more
rejections, if that's observed later), but the actual scripts will use
INLIER_THRESHOLD_MM = 75.0 uniformly, no per-phase special-casing.
- [11:30:50] === drag_k_discovery.py: Phase 1 K discovery starting ===
- [11:30:50] g_fixed loaded: [  -89.35238335  9327.0996008  -3038.63936464], |g_fixed|=9810.00 mm/s^2
- [11:30:50] K estimate (physical, volleyball): K_SI~0.0308 (1/m) -> K_mm~3.075556e-05 (1/mm), sweep centered here (0.1x-5x)
- [11:30:50] flight_01: triangulated 27 labelled points [frames 43..69]
- [11:30:50] flight_01: n=27 labelled points, t span=0.433s -- starting Model A/B/C discovery
- [11:30:51] flight_01: K-sweep best K=4.464858e-05 1/mm, residual=17.76mm (range [3.08e-06,1.54e-04])
- [11:30:51] flight_01: Model C refined (free-K nonlinear fit) K=4.458347e-05 1/mm, residual=17.76mm
- [11:30:51] flight_22: triangulated 93 labelled points [frames 1..93]
- [11:30:51] flight_22: n=93 labelled points, t span=1.532s -- starting Model A/B/C discovery
- [11:30:56] flight_22: K-sweep best K=6.023847e-05 1/mm, residual=27.17mm (range [3.08e-06,1.54e-04])
- [11:30:56] flight_22: Model C refined (free-K nonlinear fit) K=6.186347e-05 1/mm, residual=27.14mm
- [11:30:56] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\k_sweep.csv (90 rows: 30 flight_01 + 30 flight_22 + 30 pooled)
- [11:30:56] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\residual_vs_K.png
- [11:30:56] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\models_full_arc_residual.csv
- [11:30:56] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\models_full_arc_residual.png
- [11:30:56] flight_01: RANSAC starting -- inlier_threshold=75.0mm, seed=42, min_samples={'A': 6, 'B': 6, 'C': 8}, n_iterations={'A': 56, 'B': 56, 'C': 117}
- [11:30:56] flight_01 model A: RANSAC n_inliers=27/27, residual_rms=30.07mm, rejected_frames=[]
- [11:30:56] flight_01 model B: RANSAC n_inliers=26/27, residual_rms=46.96mm, rejected_frames=[69]
- [11:31:01] flight_01 model C: RANSAC n_inliers=27/27, residual_rms=30.77mm, rejected_frames=[]
- [11:31:03] flight_01: RANSAC-inlier K-sweep complete, 30/30 points, on 27 inlier points (of 27)
- [11:31:03] flight_22: RANSAC starting -- inlier_threshold=75.0mm, seed=42, min_samples={'A': 6, 'B': 6, 'C': 8}, n_iterations={'A': 56, 'B': 56, 'C': 117}
- [11:31:03] flight_22 model A: RANSAC n_inliers=80/93, residual_rms=40.43mm, rejected_frames=[1, 24, 42, 60, 82, 85, 87, 88, 89, 90, 91, 92, 93]
- [11:31:03] flight_22 model B: RANSAC n_inliers=60/93, residual_rms=47.82mm, rejected_frames=[1, 2, 3, 4, 33, 36, 42, 67, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93]
- [11:31:15] flight_22 model C: RANSAC n_inliers=88/93, residual_rms=41.07mm, rejected_frames=[1, 3, 82, 91, 93]
- [11:31:19] flight_22: RANSAC-inlier K-sweep complete, 30/30 points, on 88 inlier points (of 93)
- [11:31:19] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\k_sweep_ransac.csv (180 rows)
- [11:31:20] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\residual_vs_K_ransac.png
- [11:31:20] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\models_full_arc_residual_ransac.csv
- [11:31:20] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\models_full_arc_residual_ransac.png
- [11:31:20] K comparison: flight_01 K=4.458347e-05, flight_22 K=6.186347e-05, ratio=1.39x
- [11:31:20] Pooled joint fit: K=6.053818e-05 1/mm, combined_residual_rms=25.61mm (fit over 120 points across 2 flights, time origin = each flight's own first labelled frame, t=0 independently per flight)
- [11:31:20] === drag_k_discovery.py: Phase 1 K discovery complete ===

## [phase 1 RANSAC] Extended drag_k_discovery.py -- results

Added ransac_discover_for_flight() (runs ransac_fit per model A/B/C on the
flight's full LABELLED track, logs accepted/rejected frames; reuses Model
C's inlier set to rerun the plain K-sweep restricted to those inliers, per
decision #2 -- no full RANSAC at every grid point) and
write_ransac_outputs() (k_sweep_ransac.csv, residual_vs_K_ransac.png,
models_full_arc_residual_ransac.csv/.png -- all NEW files, existing plain
outputs untouched per decision #4). Reran the full script: total runtime
32s, well within budget.

**flight_01** (n=27 labelled points): Model A RANSAC 27/27 inliers (nothing
rejected, residual unchanged 30.07mm); Model B 26/27 (rejects frame 69 only,
residual 46.96 vs plain 48.29mm); Model C 27/27 (nothing rejected, residual
30.77mm vs plain-C-refined 17.76mm -- NOTE this "RANSAC C" uses flight_01's
OWN refined K as a FIXED reference model rather than refitting K, so it's
not directly comparable to the free-K-refined plain number; expected).

**flight_22** (n=93 labelled points): as anticipated in the correction note
above (labelled data has no real contamination -- the hand-pickup bug is a
DETECTOR failure mode, not a labelling one), NONE of the rejected frames
here are 44-47 (those aren't even labelled-track outliers) or 77/78/81.
Model A rejects 13/93, mostly clustered at the far tail (82, 85, 87-93) --
consistent with a free 9-param global fit degrading most at the extrapolated
ends of a long single window. Model B rejects 33/93 (over a third!) --
consistent with Phase 1's own plain-fit finding that B's full-arc residual
(110mm) is the worst of the three models on this flight, i.e. many
genuinely-clean points exceed 75mm simply because a fixed-gravity-only
model doesn't track a 1.5s real (drag-curved) arc well, not because they're
contaminated. Model C rejects only 5/93 (1, 3, 82, 91, 93) -- the cleanest,
consistent with C being the best-fitting model on the full arc. This is a
clean, expected pattern: model-fit-quality driven rejection on clean data,
NOT a sign RANSAC is broken -- and a useful independent confirmation that
Model C really is the best-conditioned model even by this different metric.

**No contamination-driven rejections in Phase 1 at all (as expected)** --
the confirmed bug lives entirely in Phase 2's detected-points curve, tested
next.

## [timing problem + fix] Model C RANSAC was ~30+ minutes projected -- reduced iteration count

Before building Phase 2's RANSAC extension, timed Model C's ransac_fit at
n_iterations=117 (the original e=0.3, p=0.999 formula output) on flight_22's
detected track at N=50/60/70/80/89: 9.5-14s PER (N) point. Phase 2 needs this
for ~87 N-values x 2 sources (label+det) x flight_22, plus flight_01 -- would
have projected to 30+ minutes, blowing past the task's explicit ~10 minute
budget by 3x+ (and the task says STOP and investigate past ~10 min, so
caught this BEFORE running the real sweep, not after a timeout).

Root cause: each RANSAC iteration for Model C is a FULL nonlinear
fit_drag_given_k call (its own internal scipy.least_squares convergence),
not a cheap closed-form fit like A/B -- so iteration count multiplies cost
far more steeply for C than the standard-formula derivation's iteration
count alone suggests.

Fix: lowered the formula's OWN inputs (not a hack around the formula) --
outlier_fraction 0.3 -> 0.15 (still ~2x the true known contamination rate on
flight_22, ~8% (7/89), so still a conservative worst-case assumption, just a
less extreme one than picked before that empirical number was in hand) and
success_prob 0.999 -> 0.99. Recomputed via the SAME ransac_n_iterations
formula: min_samples=6 -> 10 iterations (was 56), min_samples=8 -> 15 (was
117). Re-timed Model C at n_iterations=15 on the same N values: 0.8-1.5s per
point (~10x faster) -- projected full Phase 2 sweep now in the low single-
digit minutes. Verified BEFORE running the real sweep. Updated
RANSAC_OUTLIER_FRACTION/RANSAC_SUCCESS_PROB constants in trajectory_fit.py
(both drag_k_discovery.py and trajectory_model_prediction_sweep.py pull from
there, so this affects both -- rerunning drag_k_discovery.py next to keep
Phase 1's RANSAC results consistent with the new iteration counts).
- [11:35:06] === drag_k_discovery.py: Phase 1 K discovery starting ===
- [11:35:06] g_fixed loaded: [  -89.35238335  9327.0996008  -3038.63936464], |g_fixed|=9810.00 mm/s^2
- [11:35:06] K estimate (physical, volleyball): K_SI~0.0308 (1/m) -> K_mm~3.075556e-05 (1/mm), sweep centered here (0.1x-5x)
- [11:35:06] flight_01: triangulated 27 labelled points [frames 43..69]
- [11:35:06] flight_01: n=27 labelled points, t span=0.433s -- starting Model A/B/C discovery
- [11:35:07] flight_01: K-sweep best K=4.464858e-05 1/mm, residual=17.76mm (range [3.08e-06,1.54e-04])
- [11:35:07] flight_01: Model C refined (free-K nonlinear fit) K=4.458347e-05 1/mm, residual=17.76mm
- [11:35:07] flight_22: triangulated 93 labelled points [frames 1..93]
- [11:35:07] flight_22: n=93 labelled points, t span=1.532s -- starting Model A/B/C discovery
- [11:35:11] flight_22: K-sweep best K=6.023847e-05 1/mm, residual=27.17mm (range [3.08e-06,1.54e-04])
- [11:35:11] flight_22: Model C refined (free-K nonlinear fit) K=6.186347e-05 1/mm, residual=27.14mm
- [11:35:11] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\k_sweep.csv (90 rows: 30 flight_01 + 30 flight_22 + 30 pooled)
- [11:35:12] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\residual_vs_K.png
- [11:35:12] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\models_full_arc_residual.csv
- [11:35:12] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\models_full_arc_residual.png
- [11:35:12] flight_01: RANSAC starting -- inlier_threshold=75.0mm, seed=42, min_samples={'A': 6, 'B': 6, 'C': 8}, n_iterations={'A': 10, 'B': 10, 'C': 15}
- [11:35:12] flight_01 model A: RANSAC n_inliers=27/27, residual_rms=30.07mm, rejected_frames=[]
- [11:35:12] flight_01 model B: RANSAC n_inliers=26/27, residual_rms=46.96mm, rejected_frames=[69]
- [11:35:13] flight_01 model C: RANSAC n_inliers=27/27, residual_rms=30.77mm, rejected_frames=[]
- [11:35:15] flight_01: RANSAC-inlier K-sweep complete, 30/30 points, on 27 inlier points (of 27)
- [11:35:15] flight_22: RANSAC starting -- inlier_threshold=75.0mm, seed=42, min_samples={'A': 6, 'B': 6, 'C': 8}, n_iterations={'A': 10, 'B': 10, 'C': 15}
- [11:35:15] flight_22 model A: RANSAC n_inliers=80/93, residual_rms=40.43mm, rejected_frames=[1, 24, 42, 60, 82, 85, 87, 88, 89, 90, 91, 92, 93]
- [11:35:15] flight_22 model B: RANSAC n_inliers=51/93, residual_rms=46.29mm, rejected_frames=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 29, 30, 60, 79, 82, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93]
- [11:35:16] flight_22 model C: RANSAC n_inliers=88/93, residual_rms=41.07mm, rejected_frames=[1, 3, 82, 91, 93]
- [11:35:20] flight_22: RANSAC-inlier K-sweep complete, 30/30 points, on 88 inlier points (of 93)
- [11:35:20] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\k_sweep_ransac.csv (180 rows)
- [11:35:21] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\residual_vs_K_ransac.png
- [11:35:21] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\models_full_arc_residual_ransac.csv
- [11:35:21] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase1\models_full_arc_residual_ransac.png
- [11:35:21] K comparison: flight_01 K=4.458347e-05, flight_22 K=6.186347e-05, ratio=1.39x
- [11:35:21] Pooled joint fit: K=6.053818e-05 1/mm, combined_residual_rms=25.61mm (fit over 120 points across 2 flights, time origin = each flight's own first labelled frame, t=0 independently per flight)
- [11:35:21] === drag_k_discovery.py: Phase 1 K discovery complete ===

## [rerun] drag_k_discovery.py with reduced iteration counts

Reran (17s total, fast). A/B/C plain results identical (unaffected by
RANSAC constants). RANSAC results: flight_01 unchanged (A 27/27, B 26/27
rejects frame 69, C 27/27). flight_22: A unchanged (80/93, same 13 rejected
frames), C unchanged (88/93, same 5 rejected frames: 1,3,82,91,93) -- both
converge to the same answer even with 15 iterations instead of 117, since
the true inlier/outlier split is easy to find (linear/well-conditioned
fits, no real contamination to hide from). B's rejected set changed
somewhat (51/93 now vs 60/93 before, still rejecting mostly the same
regions -- frames 1-30ish and 79-93ish) -- expected sampling noise from
fewer random draws exploring a genuinely-ambiguous case (B's own full-arc
fit is the worst-conditioned of the three models on this flight, so which
exact points cross the 75mm line varies more with fewer iterations). Not a
concern: B was never the model this task is testing for contamination
detection (that's Model C, which is stable across both iteration counts).
Proceeding to build Phase 2's RANSAC extension.
- [11:37:13] === trajectory_model_prediction_sweep.py: Phase 2 starting ===
- [11:37:13] K_FIXED = 6.053818e-05 1/mm (Phase 1 pooled result, Checkpoint-1 approved)
- [11:37:13] g_fixed loaded: |g_fixed|=9810.00 mm/s^2
- [11:37:13] RANSAC config: inlier_threshold=75.0mm, min_samples={'A': 6, 'B': 6, 'C': 8}, n_iterations={'A': 10, 'B': 10, 'C': 15}, seed=42 (shared constants from trajectory_fit.py)
- [11:37:13] flight_01: Phase 2 prediction sweep starting
- [11:37:13] flight_01: label_common=27 frames, det_common=25 frames (tuned detections)
- [11:37:13] flight_01: target_frame=69, fit_frames=25 [44..68]
- [11:37:17] flight_01 N=14 model=A source=det: RANSAC rejected [51]
- [11:37:18] flight_01 N=15 model=A source=det: RANSAC rejected [57]
- [11:37:18] flight_01 N=16 model=A source=det: RANSAC rejected [51]
- [11:37:18] flight_01 N=16 model=B source=det: RANSAC rejected [51]
- [11:37:19] flight_01 N=17 model=B source=det: RANSAC rejected [57]
- [11:37:20] flight_01 N=17 model=C source=det: RANSAC rejected [57]
- [11:37:20] flight_01 N=18 model=A source=det: RANSAC rejected [57]
- [11:37:20] flight_01 N=18 model=B source=det: RANSAC rejected [51, 57]
- [11:37:21] flight_01 N=18 model=C source=det: RANSAC rejected [51, 57]
- [11:37:21] flight_01 N=19 model=A source=det: RANSAC rejected [54]
- [11:37:21] flight_01 N=19 model=B source=det: RANSAC rejected [57]
- [11:37:22] flight_01 N=19 model=C source=det: RANSAC rejected [57]
- [11:37:22] flight_01 N=20 model=B source=det: RANSAC rejected [57]
- [11:37:23] flight_01 N=20 model=C source=det: RANSAC rejected [57]
- [11:37:23] flight_01 N=21 model=A source=label: RANSAC rejected [44] <- includes KNOWN hand-pickup frame(s)
- [11:37:23] flight_01 N=21 model=B source=det: RANSAC rejected [51, 57]
- [11:37:24] flight_01 N=21 model=C source=det: RANSAC rejected [51, 57]
- [11:37:24] flight_01 N=22 model=A source=det: RANSAC rejected [57, 65]
- [11:37:24] flight_01 N=22 model=B source=label: RANSAC rejected [63]
- [11:37:24] flight_01 N=22 model=B source=det: RANSAC rejected [57]
- [11:37:25] flight_01 N=22 model=C source=det: RANSAC rejected [57]
- [11:37:25] flight_01 N=23 model=A source=label: RANSAC rejected [44] <- includes KNOWN hand-pickup frame(s)
- [11:37:25] flight_01 N=23 model=A source=det: RANSAC rejected [57]
- [11:37:25] flight_01 N=23 model=B source=det: RANSAC rejected [51, 57]
- [11:37:26] flight_01 N=23 model=C source=det: RANSAC rejected [57]
- [11:37:26] flight_01 N=24 model=A source=label: RANSAC rejected [44] <- includes KNOWN hand-pickup frame(s)
- [11:37:26] flight_01 N=24 model=A source=det: RANSAC rejected [60]
- [11:37:26] flight_01 N=24 model=B source=det: RANSAC rejected [57]
- [11:37:27] flight_01 N=24 model=C source=det: RANSAC rejected [51, 57]
- [11:37:27] flight_01 N=25 model=A source=det: RANSAC rejected [51, 57, 65]
- [11:37:27] flight_01 N=25 model=B source=label: RANSAC rejected [44] <- includes KNOWN hand-pickup frame(s)
- [11:37:27] flight_01 N=25 model=B source=det: RANSAC rejected [51, 57, 59, 68]
- [11:37:28] flight_01 N=25 model=C source=det: RANSAC rejected [57, 68]
- [11:37:28] flight_01: 22 (N, model, source) points had N < RANSAC's min_samples -- fell back to the plain fit (expected at low N, matches decision #1)
- [11:37:28] flight_01: sweep complete, 23 N-values, 0 plain + 0 RANSAC convergence failures
- [11:37:28] flight_22: Phase 2 prediction sweep starting
- [11:37:28] flight_22: label_common=93 frames, det_common=89 frames (tuned detections)
- [11:37:28] flight_22: target_frame=93, fit_frames=89 [2..92]
- [11:37:28] flight_22 N=6 model=B source=det: RANSAC FIT FAILED TO CONVERGE -- ransac_fit: no candidate model reached >= min_samples (6) inliers over 10 iterations -- skipping this point
- [11:37:28] flight_22 N=7 model=A source=det: RANSAC FIT FAILED TO CONVERGE -- ransac_fit: no candidate model reached >= min_samples (6) inliers over 10 iterations -- skipping this point
- [11:37:28] flight_22 N=7 model=B source=det: RANSAC FIT FAILED TO CONVERGE -- ransac_fit: no candidate model reached >= min_samples (6) inliers over 10 iterations -- skipping this point
- [11:37:28] flight_22 N=8 model=A source=det: RANSAC FIT FAILED TO CONVERGE -- ransac_fit: no candidate model reached >= min_samples (6) inliers over 10 iterations -- skipping this point
- [11:37:28] flight_22 N=8 model=B source=det: RANSAC FIT FAILED TO CONVERGE -- ransac_fit: no candidate model reached >= min_samples (6) inliers over 10 iterations -- skipping this point
- [11:37:29] flight_22 N=8 model=C source=det: RANSAC FIT FAILED TO CONVERGE -- ransac_fit: no candidate model reached >= min_samples (8) inliers over 15 iterations -- skipping this point
- [11:37:29] flight_22 N=9 model=A source=det: RANSAC rejected [3, 4, 7]
- [11:37:29] flight_22 N=9 model=B source=det: RANSAC rejected [2, 4, 7]
- [11:37:30] flight_22 N=9 model=C source=det: RANSAC FIT FAILED TO CONVERGE -- ransac_fit: no candidate model reached >= min_samples (8) inliers over 15 iterations -- skipping this point
- [11:37:30] flight_22 N=10 model=A source=det: RANSAC rejected [3, 4, 7]
- [11:37:30] flight_22 N=10 model=B source=det: RANSAC rejected [2, 4, 7]
- [11:37:30] flight_22 N=10 model=C source=det: RANSAC rejected [2, 7]
- [11:37:30] flight_22 N=11 model=A source=det: RANSAC rejected [3, 4, 7]
- [11:37:30] flight_22 N=11 model=B source=det: RANSAC rejected [2, 4, 7]
- [11:37:31] flight_22 N=11 model=C source=det: RANSAC rejected [2, 7]
- [11:37:31] flight_22 N=12 model=A source=det: RANSAC rejected [2, 4, 7]
- [11:37:31] flight_22 N=12 model=B source=det: RANSAC rejected [2, 4, 7]
- [11:37:32] flight_22 N=12 model=C source=det: RANSAC rejected [2, 7]
- [11:37:32] flight_22 N=13 model=A source=det: RANSAC rejected [2, 4, 7]
- [11:37:32] flight_22 N=13 model=B source=det: RANSAC rejected [2, 4, 7]
- [11:37:33] flight_22 N=13 model=C source=det: RANSAC rejected [2, 4, 7]
- [11:37:33] flight_22 N=14 model=A source=det: RANSAC rejected [3, 4, 7, 15]
- [11:37:33] flight_22 N=14 model=B source=det: RANSAC rejected [2, 7]
- [11:37:34] flight_22 N=14 model=C source=det: RANSAC rejected [2, 7]
- [11:37:34] flight_22 N=15 model=A source=det: RANSAC rejected [3, 4, 5, 8, 9]
- [11:37:34] flight_22 N=15 model=B source=det: RANSAC rejected [2, 4, 7, 9]
- [11:37:35] flight_22 N=15 model=C source=det: RANSAC rejected [2, 7]
- [11:37:35] flight_22 N=16 model=A source=det: RANSAC rejected [3, 4, 7, 15, 17]
- [11:37:35] flight_22 N=16 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16]
- [11:37:36] flight_22 N=16 model=C source=det: RANSAC rejected [2, 4, 7, 17]
- [11:37:36] flight_22 N=17 model=A source=det: RANSAC rejected [3, 4, 7, 17, 18]
- [11:37:36] flight_22 N=17 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18]
- [11:37:37] flight_22 N=17 model=C source=det: RANSAC rejected [2, 4, 7, 9, 18]
- [11:37:37] flight_22 N=18 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 19]
- [11:37:37] flight_22 N=18 model=B source=det: RANSAC rejected [2, 7, 17, 18]
- [11:37:38] flight_22 N=18 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18]
- [11:37:38] flight_22 N=19 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18]
- [11:37:38] flight_22 N=19 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18]
- [11:37:39] flight_22 N=19 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18]
- [11:37:39] flight_22 N=20 model=A source=det: RANSAC rejected [2, 4, 7, 17, 18, 20, 21]
- [11:37:39] flight_22 N=20 model=B source=det: RANSAC rejected [2, 7, 17, 18, 20, 21]
- [11:37:40] flight_22 N=20 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:37:40] flight_22 N=21 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:37:40] flight_22 N=21 model=B source=det: RANSAC rejected [2, 3, 7, 17, 18, 20, 21]
- [11:37:41] flight_22 N=21 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:37:41] flight_22 N=22 model=A source=det: RANSAC rejected [2, 4, 7, 16, 18, 21, 22]
- [11:37:41] flight_22 N=22 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:37:42] flight_22 N=22 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:37:42] flight_22 N=23 model=A source=det: RANSAC rejected [2, 4, 7, 9, 17, 18, 21]
- [11:37:42] flight_22 N=23 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:37:43] flight_22 N=23 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:37:43] flight_22 N=24 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:37:43] flight_22 N=24 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:37:44] flight_22 N=24 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:37:44] flight_22 N=25 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:37:45] flight_22 N=25 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:37:46] flight_22 N=25 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:37:46] flight_22 N=26 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:37:46] flight_22 N=26 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:37:47] flight_22 N=26 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:37:47] flight_22 N=27 model=A source=det: RANSAC rejected [2, 4, 7, 17, 18, 21]
- [11:37:47] flight_22 N=27 model=B source=label: RANSAC rejected [28]
- [11:37:47] flight_22 N=27 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:37:48] flight_22 N=27 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:37:48] flight_22 N=28 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:37:48] flight_22 N=28 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:37:50] flight_22 N=28 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:37:50] flight_22 N=29 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:37:50] flight_22 N=29 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:37:51] flight_22 N=29 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 23]
- [11:37:51] flight_22 N=30 model=A source=det: RANSAC rejected [2, 4, 7, 18, 21]
- [11:37:51] flight_22 N=30 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 23]
- [11:37:52] flight_22 N=30 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:37:52] flight_22 N=31 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 23]
- [11:37:52] flight_22 N=31 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:37:53] flight_22 N=31 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32]
- [11:37:53] flight_22 N=32 model=A source=det: RANSAC rejected [2, 4, 7, 16, 18, 21, 23]
- [11:37:53] flight_22 N=32 model=B source=det: RANSAC rejected [2, 4, 7, 14, 18, 21, 23]
- [11:37:55] flight_22 N=32 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:37:55] flight_22 N=33 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:37:55] flight_22 N=33 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:37:56] flight_22 N=33 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:37:56] flight_22 N=34 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35]
- [11:37:56] flight_22 N=34 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:37:57] flight_22 N=34 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:37:57] flight_22 N=35 model=A source=det: RANSAC rejected [2, 4, 7, 13, 14, 16, 18, 19, 21, 22]
- [11:37:57] flight_22 N=35 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:37:59] flight_22 N=35 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:37:59] flight_22 N=36 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 35, 37]
- [11:37:59] flight_22 N=36 model=B source=label: RANSAC rejected [36]
- [11:37:59] flight_22 N=36 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 23, 35]
- [11:38:00] flight_22 N=36 model=C source=det: RANSAC rejected [2, 4, 7, 18, 21, 23, 35]
- [11:38:00] flight_22 N=37 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 35]
- [11:38:00] flight_22 N=37 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35]
- [11:38:02] flight_22 N=37 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:38:02] flight_22 N=38 model=A source=det: RANSAC rejected [2, 4, 7, 8, 9, 18, 21, 35]
- [11:38:02] flight_22 N=38 model=B source=det: RANSAC rejected [2, 4, 7, 9, 18, 21, 35]
- [11:38:03] flight_22 N=38 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:38:03] flight_22 N=39 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35]
- [11:38:03] flight_22 N=39 model=B source=label: RANSAC rejected [24]
- [11:38:03] flight_22 N=39 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:38:05] flight_22 N=39 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:38:05] flight_22 N=40 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 35]
- [11:38:05] flight_22 N=40 model=B source=label: RANSAC rejected [24]
- [11:38:05] flight_22 N=40 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35]
- [11:38:06] flight_22 N=40 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:38:06] flight_22 N=41 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35]
- [11:38:06] flight_22 N=41 model=B source=label: RANSAC rejected [24]
- [11:38:06] flight_22 N=41 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:38:08] flight_22 N=41 model=C source=det: RANSAC rejected [2, 4, 7, 16, 18, 21, 35]
- [11:38:08] flight_22 N=42 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35]
- [11:38:08] flight_22 N=42 model=B source=label: RANSAC rejected [42]
- [11:38:08] flight_22 N=42 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35]
- [11:38:09] flight_22 N=42 model=C source=label: RANSAC rejected [42]
- [11:38:09] flight_22 N=42 model=C source=det: RANSAC rejected [2, 4, 7, 16, 18, 21, 35]
- [11:38:09] flight_22 N=43 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35, 44] <- includes KNOWN hand-pickup frame(s)
- [11:38:09] flight_22 N=43 model=B source=label: RANSAC rejected [3, 24]
- [11:38:09] flight_22 N=43 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44] <- includes KNOWN hand-pickup frame(s)
- [11:38:11] flight_22 N=43 model=C source=det: RANSAC rejected [2, 4, 7, 14, 18, 21, 35, 44] <- includes KNOWN hand-pickup frame(s)
- [11:38:11] flight_22 N=44 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45] <- includes KNOWN hand-pickup frame(s)
- [11:38:11] flight_22 N=44 model=B source=label: RANSAC rejected [24]
- [11:38:11] flight_22 N=44 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35, 44, 45] <- includes KNOWN hand-pickup frame(s)
- [11:38:13] flight_22 N=44 model=C source=det: RANSAC rejected [2, 6, 7, 14, 16, 18, 21, 35, 44, 45] <- includes KNOWN hand-pickup frame(s)
- [11:38:13] flight_22 N=45 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46] <- includes KNOWN hand-pickup frame(s)
- [11:38:13] flight_22 N=45 model=B source=label: RANSAC rejected [24]
- [11:38:13] flight_22 N=45 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35, 44, 45, 46] <- includes KNOWN hand-pickup frame(s)
- [11:38:15] flight_22 N=45 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46] <- includes KNOWN hand-pickup frame(s)
- [11:38:15] flight_22 N=46 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47] <- includes KNOWN hand-pickup frame(s)
- [11:38:15] flight_22 N=46 model=B source=label: RANSAC rejected [3, 24]
- [11:38:15] flight_22 N=46 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47] <- includes KNOWN hand-pickup frame(s)
- [11:38:16] flight_22 N=46 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47] <- includes KNOWN hand-pickup frame(s)
- [11:38:16] flight_22 N=47 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47] <- includes KNOWN hand-pickup frame(s)
- [11:38:16] flight_22 N=47 model=B source=label: RANSAC rejected [24]
- [11:38:16] flight_22 N=47 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48] <- includes KNOWN hand-pickup frame(s)
- [11:38:18] flight_22 N=47 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47] <- includes KNOWN hand-pickup frame(s)
- [11:38:18] flight_22 N=48 model=A source=det: RANSAC rejected [2, 4, 7, 9, 14, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47] <- includes KNOWN hand-pickup frame(s)
- [11:38:18] flight_22 N=48 model=B source=label: RANSAC rejected [24]
- [11:38:18] flight_22 N=48 model=B source=det: RANSAC rejected [2, 4, 7, 8, 9, 14, 17, 18, 21, 23, 32, 35, 44, 45, 46, 47] <- includes KNOWN hand-pickup frame(s)
- [11:38:19] flight_22 N=48 model=C source=label: RANSAC rejected [24]
- [11:38:20] flight_22 N=48 model=C source=det: RANSAC rejected [2, 4, 7, 18, 21, 35, 44, 45, 46, 47] <- includes KNOWN hand-pickup frame(s)
- [11:38:20] flight_22 N=49 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 22, 28, 29, 32, 35, 44, 45, 46, 47, 48] <- includes KNOWN hand-pickup frame(s)
- [11:38:20] flight_22 N=49 model=B source=label: RANSAC rejected [3]
- [11:38:20] flight_22 N=49 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50] <- includes KNOWN hand-pickup frame(s)
- [11:38:22] flight_22 N=49 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48] <- includes KNOWN hand-pickup frame(s)
- [11:38:22] flight_22 N=50 model=A source=det: RANSAC rejected [2, 7, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 50, 51] <- includes KNOWN hand-pickup frame(s)
- [11:38:22] flight_22 N=50 model=B source=label: RANSAC rejected [24]
- [11:38:22] flight_22 N=50 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51] <- includes KNOWN hand-pickup frame(s)
- [11:38:24] flight_22 N=50 model=C source=det: RANSAC rejected [2, 4, 7, 18, 21, 23, 35, 44, 45, 46, 47, 48, 50, 51] <- includes KNOWN hand-pickup frame(s)
- [11:38:24] flight_22 N=51 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52] <- includes KNOWN hand-pickup frame(s)
- [11:38:24] flight_22 N=51 model=B source=label: RANSAC rejected [24]
- [11:38:24] flight_22 N=51 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52] <- includes KNOWN hand-pickup frame(s)
- [11:38:26] flight_22 N=51 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52] <- includes KNOWN hand-pickup frame(s)
- [11:38:26] flight_22 N=52 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 20, 21, 23, 35, 44, 45, 46, 47, 50, 51, 52, 53] <- includes KNOWN hand-pickup frame(s)
- [11:38:26] flight_22 N=52 model=B source=label: RANSAC rejected [2, 3, 53]
- [11:38:26] flight_22 N=52 model=B source=det: RANSAC rejected [2, 3, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53] <- includes KNOWN hand-pickup frame(s)
- [11:38:27] flight_22 N=52 model=C source=label: RANSAC rejected [24]
- [11:38:28] flight_22 N=52 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53] <- includes KNOWN hand-pickup frame(s)
- [11:38:28] flight_22 N=53 model=A source=label: RANSAC rejected [54]
- [11:38:28] flight_22 N=53 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 49, 51, 53, 54] <- includes KNOWN hand-pickup frame(s)
- [11:38:28] flight_22 N=53 model=B source=label: RANSAC rejected [2, 3]
- [11:38:28] flight_22 N=53 model=B source=det: RANSAC rejected [2, 3, 4, 7, 14, 17, 18, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53] <- includes KNOWN hand-pickup frame(s)
- [11:38:28] flight_22 N=53 model=C source=label: RANSAC rejected [24]
- [11:38:29] flight_22 N=53 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53] <- includes KNOWN hand-pickup frame(s)
- [11:38:29] flight_22 N=54 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 41, 43, 44, 45, 46, 47, 48, 49, 51, 54] <- includes KNOWN hand-pickup frame(s)
- [11:38:29] flight_22 N=54 model=B source=label: RANSAC rejected [24]
- [11:38:29] flight_22 N=54 model=B source=det: RANSAC rejected [2, 3, 4, 7, 8, 9, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55] <- includes KNOWN hand-pickup frame(s)
- [11:38:31] flight_22 N=54 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 41, 44, 45, 46, 47, 48, 49, 51, 53, 54] <- includes KNOWN hand-pickup frame(s)
- [11:38:31] flight_22 N=55 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 49, 51, 54, 56] <- includes KNOWN hand-pickup frame(s)
- [11:38:31] flight_22 N=55 model=B source=label: RANSAC rejected [24]
- [11:38:31] flight_22 N=55 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 56] <- includes KNOWN hand-pickup frame(s)
- [11:38:33] flight_22 N=55 model=C source=det: RANSAC rejected [2, 4, 7, 18, 21, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55] <- includes KNOWN hand-pickup frame(s)
- [11:38:33] flight_22 N=56 model=A source=det: RANSAC rejected [2, 4, 7, 9, 14, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55] <- includes KNOWN hand-pickup frame(s)
- [11:38:33] flight_22 N=56 model=B source=label: RANSAC rejected [3, 24]
- [11:38:33] flight_22 N=56 model=B source=det: RANSAC rejected [2, 4, 7, 8, 9, 14, 17, 18, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55] <- includes KNOWN hand-pickup frame(s)
- [11:38:35] flight_22 N=56 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 57] <- includes KNOWN hand-pickup frame(s)
- [11:38:35] flight_22 N=57 model=A source=label: RANSAC rejected [42]
- [11:38:35] flight_22 N=57 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58] <- includes KNOWN hand-pickup frame(s)
- [11:38:35] flight_22 N=57 model=B source=label: RANSAC rejected [24]
- [11:38:35] flight_22 N=57 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55] <- includes KNOWN hand-pickup frame(s)
- [11:38:37] flight_22 N=57 model=C source=det: RANSAC rejected [2, 4, 7, 16, 18, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55] <- includes KNOWN hand-pickup frame(s)
- [11:38:37] flight_22 N=58 model=A source=label: RANSAC rejected [24]
- [11:38:37] flight_22 N=58 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 49, 51, 54, 56, 57, 59] <- includes KNOWN hand-pickup frame(s)
- [11:38:37] flight_22 N=58 model=B source=label: RANSAC rejected [24, 42]
- [11:38:37] flight_22 N=58 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 49, 51, 52, 53, 54, 56, 59] <- includes KNOWN hand-pickup frame(s)
- [11:38:39] flight_22 N=58 model=C source=det: RANSAC rejected [2, 4, 7, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59] <- includes KNOWN hand-pickup frame(s)
- [11:38:39] flight_22 N=59 model=A source=label: RANSAC rejected [42]
- [11:38:39] flight_22 N=59 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 22, 29, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60] <- includes KNOWN hand-pickup frame(s)
- [11:38:39] flight_22 N=59 model=B source=label: RANSAC rejected [2, 3, 24, 60]
- [11:38:39] flight_22 N=59 model=B source=det: RANSAC rejected [2, 4, 7, 8, 9, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60] <- includes KNOWN hand-pickup frame(s)
- [11:38:40] flight_22 N=59 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60] <- includes KNOWN hand-pickup frame(s)
- [11:38:41] flight_22 N=60 model=A source=label: RANSAC rejected [42]
- [11:38:41] flight_22 N=60 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 29, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 61] <- includes KNOWN hand-pickup frame(s)
- [11:38:41] flight_22 N=60 model=B source=label: RANSAC rejected [2, 3, 24, 58]
- [11:38:41] flight_22 N=60 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60] <- includes KNOWN hand-pickup frame(s)
- [11:38:42] flight_22 N=60 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60] <- includes KNOWN hand-pickup frame(s)
- [11:38:42] flight_22 N=61 model=A source=label: RANSAC rejected [24]
- [11:38:42] flight_22 N=61 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 49, 51, 53, 54, 56, 59, 61, 62] <- includes KNOWN hand-pickup frame(s)
- [11:38:42] flight_22 N=61 model=B source=label: RANSAC rejected [24, 25, 60, 62]
- [11:38:42] flight_22 N=61 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 23, 35, 44, 45, 46, 47, 48, 49, 51, 52, 53, 56, 59, 60, 62] <- includes KNOWN hand-pickup frame(s)
- [11:38:43] flight_22 N=61 model=C source=label: RANSAC rejected [24]
- [11:38:44] flight_22 N=61 model=C source=det: RANSAC rejected [2, 4, 7, 16, 18, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 61, 62] <- includes KNOWN hand-pickup frame(s)
- [11:38:44] flight_22 N=62 model=A source=label: RANSAC rejected [24, 62]
- [11:38:44] flight_22 N=62 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 49, 51, 53, 54, 56, 59, 61, 62, 63] <- includes KNOWN hand-pickup frame(s)
- [11:38:44] flight_22 N=62 model=B source=label: RANSAC rejected [2, 3, 24, 62]
- [11:38:44] flight_22 N=62 model=B source=det: RANSAC rejected [2, 4, 5, 7, 18, 21, 23, 35, 44, 45, 46, 47, 48, 49, 51, 52, 53, 54, 55, 56, 59, 60, 62, 63] <- includes KNOWN hand-pickup frame(s)
- [11:38:46] flight_22 N=62 model=C source=det: RANSAC rejected [2, 4, 7, 9, 16, 18, 21, 23, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62] <- includes KNOWN hand-pickup frame(s)
- [11:38:46] flight_22 N=63 model=A source=label: RANSAC rejected [42, 60]
- [11:38:46] flight_22 N=63 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 49, 51, 53, 54, 56, 57, 59, 61, 62, 63, 64] <- includes KNOWN hand-pickup frame(s)
- [11:38:46] flight_22 N=63 model=B source=label: RANSAC rejected [3, 24, 62, 63, 64]
- [11:38:46] flight_22 N=63 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 17, 18, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64] <- includes KNOWN hand-pickup frame(s)
- [11:38:47] flight_22 N=63 model=C source=label: RANSAC rejected [24]
- [11:38:49] flight_22 N=63 model=C source=det: RANSAC rejected [2, 4, 6, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64] <- includes KNOWN hand-pickup frame(s)
- [11:38:49] flight_22 N=64 model=A source=label: RANSAC rejected [36, 42]
- [11:38:49] flight_22 N=64 model=A source=det: RANSAC rejected [2, 4, 7, 14, 17, 18, 20, 21, 23, 35, 39, 41, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 61, 62, 64] <- includes KNOWN hand-pickup frame(s)
- [11:38:49] flight_22 N=64 model=B source=label: RANSAC rejected [2, 4, 12, 24, 42, 60]
- [11:38:49] flight_22 N=64 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 17, 18, 21, 23, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 63, 64, 65] <- includes KNOWN hand-pickup frame(s)
- [11:38:49] flight_22 N=64 model=C source=label: RANSAC rejected [24]
- [11:38:51] flight_22 N=64 model=C source=det: RANSAC rejected [2, 4, 7, 9, 17, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 57, 58, 60, 61] <- includes KNOWN hand-pickup frame(s)
- [11:38:51] flight_22 N=65 model=A source=label: RANSAC rejected [24]
- [11:38:51] flight_22 N=65 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 49, 51, 53, 54, 56, 57, 59, 61, 62, 63, 64, 65, 66] <- includes KNOWN hand-pickup frame(s)
- [11:38:51] flight_22 N=65 model=B source=label: RANSAC rejected [3, 24, 33, 36, 42, 60, 66]
- [11:38:51] flight_22 N=65 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 35, 41, 44, 45, 46, 47, 48, 49, 51, 53, 54, 56, 59, 62, 63, 64, 65, 66] <- includes KNOWN hand-pickup frame(s)
- [11:38:52] flight_22 N=65 model=C source=label: RANSAC rejected [24]
- [11:38:53] flight_22 N=65 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58, 60, 61, 64] <- includes KNOWN hand-pickup frame(s)
- [11:38:53] flight_22 N=66 model=A source=label: RANSAC rejected [24]
- [11:38:53] flight_22 N=66 model=A source=det: RANSAC rejected [2, 7, 14, 17, 18, 20, 21, 23, 26, 37, 39, 40, 41, 43, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 60, 61, 66, 67] <- includes KNOWN hand-pickup frame(s)
- [11:38:53] flight_22 N=66 model=B source=label: RANSAC rejected [24, 36, 42, 67]
- [11:38:53] flight_22 N=66 model=B source=det: RANSAC rejected [2, 4, 7, 14, 17, 18, 21, 23, 35, 39, 41, 44, 45, 46, 47, 48, 49, 51, 52, 53, 56, 59, 60, 62, 63, 64, 65, 66] <- includes KNOWN hand-pickup frame(s)
- [11:38:54] flight_22 N=66 model=C source=label: RANSAC rejected [24]
- [11:38:55] flight_22 N=66 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 57, 58, 60, 61, 66, 67] <- includes KNOWN hand-pickup frame(s)
- [11:38:55] flight_22 N=67 model=A source=label: RANSAC rejected [24]
- [11:38:55] flight_22 N=67 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 61, 62, 64, 65, 68] <- includes KNOWN hand-pickup frame(s)
- [11:38:55] flight_22 N=67 model=B source=label: RANSAC rejected [2, 3, 24, 36, 42, 67]
- [11:38:55] flight_22 N=67 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 34, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 68] <- includes KNOWN hand-pickup frame(s)
- [11:38:57] flight_22 N=67 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 68] <- includes KNOWN hand-pickup frame(s)
- [11:38:57] flight_22 N=68 model=A source=label: RANSAC rejected [24]
- [11:38:57] flight_22 N=68 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 66] <- includes KNOWN hand-pickup frame(s)
- [11:38:57] flight_22 N=68 model=B source=label: RANSAC rejected [2, 3, 4, 24, 36, 42, 67]
- [11:38:57] flight_22 N=68 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 23, 32, 35, 44, 45, 46, 47, 48, 49, 51, 52, 53, 55, 56, 59, 60, 62, 63, 64, 65, 66, 69] <- includes KNOWN hand-pickup frame(s)
- [11:38:59] flight_22 N=68 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58, 60, 61, 64, 67, 68, 69] <- includes KNOWN hand-pickup frame(s)
- [11:38:59] flight_22 N=69 model=A source=label: RANSAC rejected [24]
- [11:38:59] flight_22 N=69 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 64, 68, 70] <- includes KNOWN hand-pickup frame(s)
- [11:38:59] flight_22 N=69 model=B source=label: RANSAC rejected [2, 3, 24, 36, 42, 67, 69, 70]
- [11:38:59] flight_22 N=69 model=B source=det: RANSAC rejected [2, 4, 7, 8, 9, 14, 16, 17, 18, 21, 23, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 68, 69, 70] <- includes KNOWN hand-pickup frame(s)
- [11:39:01] flight_22 N=69 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70] <- includes KNOWN hand-pickup frame(s)
- [11:39:01] flight_22 N=70 model=A source=label: RANSAC rejected [42]
- [11:39:01] flight_22 N=70 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 68, 70] <- includes KNOWN hand-pickup frame(s)
- [11:39:01] flight_22 N=70 model=B source=label: RANSAC rejected [2, 3, 24, 36, 42, 60, 67, 69, 70, 71]
- [11:39:01] flight_22 N=70 model=B source=det: RANSAC rejected [2, 3, 4, 7, 8, 14, 16, 18, 21, 32, 34, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 57, 58, 60, 61, 67, 68, 69, 70, 71] <- includes KNOWN hand-pickup frame(s)
- [11:39:02] flight_22 N=70 model=C source=label: RANSAC rejected [3]
- [11:39:03] flight_22 N=70 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70] <- includes KNOWN hand-pickup frame(s)
- [11:39:03] flight_22 N=71 model=A source=label: RANSAC rejected [24]
- [11:39:03] flight_22 N=71 model=A source=det: RANSAC rejected [2, 4, 7, 8, 9, 14, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 64, 68, 70] <- includes KNOWN hand-pickup frame(s)
- [11:39:04] flight_22 N=71 model=B source=label: RANSAC rejected [2, 12, 19, 22, 24, 25, 26, 42, 70, 71, 72]
- [11:39:04] flight_22 N=71 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 49, 51, 52, 53, 54, 56, 59, 60, 62, 63, 64, 65, 66, 69, 70, 71, 72] <- includes KNOWN hand-pickup frame(s)
- [11:39:05] flight_22 N=71 model=C source=label: RANSAC rejected [42]
- [11:39:06] flight_22 N=71 model=C source=det: RANSAC rejected [2, 4, 7, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70] <- includes KNOWN hand-pickup frame(s)
- [11:39:06] flight_22 N=72 model=A source=label: RANSAC rejected [42, 72]
- [11:39:06] flight_22 N=72 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 22, 25, 28, 29, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 73] <- includes KNOWN hand-pickup frame(s)
- [11:39:06] flight_22 N=72 model=B source=label: RANSAC rejected [2, 3, 4, 24, 33, 36, 39, 40, 42, 43, 45, 46, 72, 73] <- includes KNOWN hand-pickup frame(s)
- [11:39:06] flight_22 N=72 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 22, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 66, 69, 70, 71, 72, 73] <- includes KNOWN hand-pickup frame(s)
- [11:39:07] flight_22 N=72 model=C source=label: RANSAC rejected [42]
- [11:39:08] flight_22 N=72 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 70, 73] <- includes KNOWN hand-pickup frame(s)
- [11:39:08] flight_22 N=73 model=A source=label: RANSAC rejected [3, 24, 26]
- [11:39:08] flight_22 N=73 model=A source=det: RANSAC rejected [2, 4, 7, 9, 14, 17, 18, 21, 23, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 60, 61, 64, 67, 68, 69, 70, 72, 73, 74] <- includes KNOWN hand-pickup frame(s)
- [11:39:08] flight_22 N=73 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 12, 24, 36, 42, 71, 72, 73, 74]
- [11:39:08] flight_22 N=73 model=B source=det: RANSAC rejected [2, 3, 4, 7, 8, 9, 14, 17, 18, 21, 23, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 60, 61, 64, 67, 68, 69, 70, 71, 72, 73, 74] <- includes KNOWN hand-pickup frame(s)
- [11:39:10] flight_22 N=73 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58, 60, 61, 64, 67, 68, 70] <- includes KNOWN hand-pickup frame(s)
- [11:39:10] flight_22 N=74 model=A source=label: RANSAC rejected [24, 42, 60]
- [11:39:10] flight_22 N=74 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 29, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58, 59, 60, 62, 63, 64, 65, 70, 73] <- includes KNOWN hand-pickup frame(s)
- [11:39:10] flight_22 N=74 model=B source=label: RANSAC rejected [2, 3, 4, 12, 24, 25, 42, 67, 69, 70, 71, 72, 73, 74, 75]
- [11:39:10] flight_22 N=74 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 8, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 71, 72, 73, 74, 75] <- includes KNOWN hand-pickup frame(s)
- [11:39:11] flight_22 N=74 model=C source=label: RANSAC rejected [24]
- [11:39:12] flight_22 N=74 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 73] <- includes KNOWN hand-pickup frame(s)
- [11:39:12] flight_22 N=75 model=A source=label: RANSAC rejected [2, 3, 24]
- [11:39:12] flight_22 N=75 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 22, 28, 29, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 68, 70, 73, 76] <- includes KNOWN hand-pickup frame(s)
- [11:39:12] flight_22 N=75 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 24, 33, 36, 39, 42, 43, 45, 73, 74, 75, 76] <- includes KNOWN hand-pickup frame(s)
- [11:39:12] flight_22 N=75 model=B source=det: RANSAC rejected [2, 4, 7, 8, 14, 16, 17, 18, 21, 23, 32, 34, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 71, 72, 73, 74, 75, 76] <- includes KNOWN hand-pickup frame(s)
- [11:39:14] flight_22 N=75 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 73, 76] <- includes KNOWN hand-pickup frame(s)
- [11:39:14] flight_22 N=76 model=A source=label: RANSAC rejected [2, 3, 24]
- [11:39:14] flight_22 N=76 model=A source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 68, 70, 73, 76, 77] <- includes KNOWN hand-pickup frame(s)
- [11:39:14] flight_22 N=76 model=B source=label: RANSAC rejected [12, 19, 22, 24, 25, 26, 33, 36, 42, 60, 67, 69, 71, 72, 73, 74, 75, 76, 77]
- [11:39:14] flight_22 N=76 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 13, 14, 16, 18, 21, 22, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 54, 55, 56, 59, 60, 62, 63, 64, 65, 66, 71, 73, 74, 75, 76, 77] <- includes KNOWN hand-pickup frame(s)
- [11:39:15] flight_22 N=76 model=C source=label: RANSAC rejected [42]
- [11:39:16] flight_22 N=76 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 71, 73, 77] <- includes KNOWN hand-pickup frame(s)
- [11:39:16] flight_22 N=77 model=A source=label: RANSAC rejected [3, 36, 42, 60]
- [11:39:16] flight_22 N=77 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 23, 35, 39, 41, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 64, 67, 68, 69, 70, 72, 74, 75, 76, 77, 78] <- includes KNOWN hand-pickup frame(s)
- [11:39:16] flight_22 N=77 model=B source=label: RANSAC rejected [2, 3, 4, 5, 12, 24, 36, 42, 71, 72, 73, 74, 75, 76, 77, 78]
- [11:39:16] flight_22 N=77 model=B source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 11, 14, 16, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 61, 62, 64, 68, 70, 72, 73, 74, 75, 76, 77, 78] <- includes KNOWN hand-pickup frame(s)
- [11:39:17] flight_22 N=77 model=C source=label: RANSAC rejected [78]
- [11:39:19] flight_22 N=77 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 60, 61, 64, 67, 68, 70, 76, 77, 78] <- includes KNOWN hand-pickup frame(s)
- [11:39:19] flight_22 N=78 model=A source=label: RANSAC rejected [12, 24, 26]
- [11:39:19] flight_22 N=78 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 23, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 51, 54, 56, 57, 59, 62, 63, 64, 65, 66, 71, 73, 77, 78] <- includes KNOWN hand-pickup frame(s)
- [11:39:19] flight_22 N=78 model=B source=label: RANSAC rejected [2, 3, 4, 5, 12, 24, 25, 36, 42, 67, 71, 72, 73, 74, 75, 76, 77, 78, 79]
- [11:39:19] flight_22 N=78 model=B source=det: RANSAC rejected [2, 3, 4, 7, 8, 9, 14, 16, 17, 18, 21, 23, 32, 33, 34, 35, 36, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 61, 62, 64, 68, 70, 72, 73, 74, 75, 76, 77, 78, 79] <- includes KNOWN hand-pickup frame(s)
- [11:39:20] flight_22 N=78 model=C source=label: RANSAC rejected [3]
- [11:39:21] flight_22 N=78 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 70, 73, 76, 77, 78] <- includes KNOWN hand-pickup frame(s)
- [11:39:21] flight_22 N=79 model=A source=label: RANSAC rejected [24, 72, 74, 80]
- [11:39:21] flight_22 N=79 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 17, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 63, 64, 65, 70, 73, 76, 77, 78, 80] <- includes KNOWN hand-pickup frame(s)
- [11:39:21] flight_22 N=79 model=B source=label: RANSAC rejected [2, 3, 4, 5, 12, 24, 36, 39, 42, 43, 45, 60, 67, 71, 73, 74, 75, 76, 77, 78, 79, 80] <- includes KNOWN hand-pickup frame(s)
- [11:39:21] flight_22 N=79 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 23, 32, 33, 34, 35, 36, 39, 44, 45, 46, 47, 48, 50, 51, 52, 53, 54, 55, 58, 59, 60, 62, 63, 64, 65, 70, 73, 74, 75, 76, 77, 78, 79, 80] <- includes KNOWN hand-pickup frame(s)
- [11:39:22] flight_22 N=79 model=C source=label: RANSAC rejected [3, 24]
- [11:39:23] flight_22 N=79 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 70, 73, 77, 78] <- includes KNOWN hand-pickup frame(s)
- [11:39:23] flight_22 N=80 model=A source=label: RANSAC rejected [24, 42, 60, 67, 71, 78, 79]
- [11:39:23] flight_22 N=80 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 71, 73, 75, 77, 78, 79, 81] <- includes KNOWN hand-pickup frame(s)
- [11:39:23] flight_22 N=80 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 24, 42, 74, 75, 76, 77, 78, 79, 80, 81]
- [11:39:23] flight_22 N=80 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 23, 32, 33, 34, 35, 36, 37, 39, 44, 45, 46, 47, 48, 50, 51, 52, 53, 54, 55, 58, 59, 60, 62, 64, 65, 70, 73, 74, 75, 76, 77, 78, 79, 80, 81] <- includes KNOWN hand-pickup frame(s)
- [11:39:24] flight_22 N=80 model=C source=label: RANSAC rejected [24]
- [11:39:25] flight_22 N=80 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 70, 71, 73, 77, 78, 81] <- includes KNOWN hand-pickup frame(s)
- [11:39:26] flight_22 N=81 model=A source=label: RANSAC rejected [36, 42, 60, 79, 80, 81, 82]
- [11:39:26] flight_22 N=81 model=A source=det: RANSAC rejected [3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 17, 18, 20, 21, 23, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 73, 77, 78, 81] <- includes KNOWN hand-pickup frame(s)
- [11:39:26] flight_22 N=81 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 24, 42, 60, 76, 77, 78, 79, 80, 81, 82]
- [11:39:26] flight_22 N=81 model=B source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 68, 70, 73, 76, 77, 78, 79, 80, 81, 82] <- includes KNOWN hand-pickup frame(s)
- [11:39:27] flight_22 N=81 model=C source=label: RANSAC rejected [24, 82]
- [11:39:28] flight_22 N=81 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 70, 71, 73, 76, 77, 78, 81] <- includes KNOWN hand-pickup frame(s)
- [11:39:28] flight_22 N=82 model=A source=label: RANSAC rejected [19, 22, 24, 25, 26, 80, 81, 82]
- [11:39:28] flight_22 N=82 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 70, 71, 73, 76, 77, 78, 81] <- includes KNOWN hand-pickup frame(s)
- [11:39:28] flight_22 N=82 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 19, 24, 42, 60, 76, 77, 78, 79, 80, 81, 82, 83]
- [11:39:28] flight_22 N=82 model=B source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 11, 14, 16, 18, 21, 32, 34, 35, 39, 41, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 58, 59, 60, 62, 63, 64, 65, 70, 71, 73, 77, 78, 79, 80, 81, 82, 83] <- includes KNOWN hand-pickup frame(s)
- [11:39:29] flight_22 N=82 model=C source=label: RANSAC rejected [24, 82]
- [11:39:30] flight_22 N=82 model=C source=det: RANSAC rejected [2, 4, 7, 9, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 73, 76, 77, 78, 80, 81] <- includes KNOWN hand-pickup frame(s)
- [11:39:30] flight_22 N=83 model=A source=label: RANSAC rejected [2, 3, 24, 25, 26, 82]
- [11:39:30] flight_22 N=83 model=A source=det: RANSAC rejected [2, 5, 6, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 70, 73, 76, 77, 78, 80, 81, 82, 83, 84] <- includes KNOWN hand-pickup frame(s)
- [11:39:30] flight_22 N=83 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 12, 24, 33, 36, 39, 40, 41, 42, 43, 45, 46, 51, 53, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84] <- includes KNOWN hand-pickup frame(s)
- [11:39:30] flight_22 N=83 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 22, 32, 33, 34, 35, 36, 44, 45, 46, 47, 48, 50, 51, 52, 53, 54, 55, 58, 59, 60, 62, 63, 64, 65, 70, 71, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84] <- includes KNOWN hand-pickup frame(s)
- [11:39:31] flight_22 N=83 model=C source=label: RANSAC rejected [24, 82]
- [11:39:32] flight_22 N=83 model=C source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 71, 73, 77, 78, 81] <- includes KNOWN hand-pickup frame(s)
- [11:39:33] flight_22 N=84 model=A source=label: RANSAC rejected [3, 24, 80, 81, 82, 83, 84, 85]
- [11:39:33] flight_22 N=84 model=A source=det: RANSAC rejected [2, 5, 7, 14, 16, 18, 21, 22, 25, 28, 29, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 71, 73, 77, 78, 81, 85] <- includes KNOWN hand-pickup frame(s)
- [11:39:33] flight_22 N=84 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 19, 20, 22, 24, 25, 26, 42, 51, 53, 60, 77, 78, 79, 80, 81, 82, 83, 84, 85]
- [11:39:33] flight_22 N=84 model=B source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 16, 18, 21, 22, 32, 35, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 71, 73, 77, 78, 81, 82, 83, 84, 85] <- includes KNOWN hand-pickup frame(s)
- [11:39:34] flight_22 N=84 model=C source=label: RANSAC rejected [24, 82]
- [11:39:35] flight_22 N=84 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 70, 73, 76, 77, 78, 80, 81, 84] <- includes KNOWN hand-pickup frame(s)
- [11:39:35] flight_22 N=85 model=A source=label: RANSAC rejected [24, 26, 82]
- [11:39:35] flight_22 N=85 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 22, 25, 28, 29, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 63, 64, 65, 70, 73, 76, 77, 78, 80, 81, 82, 83, 84] <- includes KNOWN hand-pickup frame(s)
- [11:39:35] flight_22 N=85 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 24, 36, 42, 43, 45, 46, 49, 51, 52, 53, 60, 67, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86] <- includes KNOWN hand-pickup frame(s)
- [11:39:35] flight_22 N=85 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 8, 10, 11, 13, 14, 16, 18, 21, 22, 25, 28, 29, 32, 34, 35, 36, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 58, 59, 60, 62, 63, 64, 65, 71, 73, 75, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86] <- includes KNOWN hand-pickup frame(s)
- [11:39:36] flight_22 N=85 model=C source=label: RANSAC rejected [3, 42, 82]
- [11:39:37] flight_22 N=85 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 73, 76, 77, 78, 80, 81, 84] <- includes KNOWN hand-pickup frame(s)
- [11:39:37] flight_22 N=86 model=A source=label: RANSAC rejected [12, 19, 22, 24, 25, 26, 82]
- [11:39:37] flight_22 N=86 model=A source=det: RANSAC rejected [2, 3, 5, 7, 14, 16, 18, 21, 22, 25, 27, 28, 29, 31, 32, 34, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58, 59, 60, 61, 62, 64, 68, 70, 73, 76, 77, 78, 80, 81, 82, 83, 84] <- includes KNOWN hand-pickup frame(s)
- [11:39:37] flight_22 N=86 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 19, 20, 22, 24, 25, 26, 42, 53, 60, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87]
- [11:39:37] flight_22 N=86 model=B source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 18, 19, 21, 22, 25, 28, 29, 32, 34, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 54, 55, 56, 58, 59, 60, 62, 63, 64, 65, 71, 73, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87] <- includes KNOWN hand-pickup frame(s)
- [11:39:38] flight_22 N=86 model=C source=label: RANSAC rejected [24, 82]
- [11:39:39] flight_22 N=86 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 70, 73, 77, 78, 81, 84] <- includes KNOWN hand-pickup frame(s)
- [11:39:39] flight_22 N=87 model=A source=label: RANSAC rejected [2, 3, 24, 25, 26, 78, 79, 85, 86, 87, 88]
- [11:39:39] flight_22 N=87 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 13, 14, 16, 18, 21, 22, 25, 27, 28, 29, 31, 32, 34, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 73, 76, 77, 78, 81, 84, 85, 88] <- includes KNOWN hand-pickup frame(s)
- [11:39:39] flight_22 N=87 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 29, 60, 67, 78, 79, 81, 82, 83, 84, 85, 86, 87, 88]
- [11:39:39] flight_22 N=87 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 8, 10, 11, 13, 14, 16, 18, 21, 22, 25, 29, 32, 35, 44, 45, 46, 47, 48, 49, 51, 52, 53, 54, 55, 56, 59, 60, 62, 63, 64, 65, 66, 69, 71, 72, 73, 74, 75, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88] <- includes KNOWN hand-pickup frame(s)
- [11:39:40] flight_22 N=87 model=C source=label: RANSAC rejected [3, 82]
- [11:39:42] flight_22 N=87 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 70, 73, 76, 77, 78, 80, 81, 84] <- includes KNOWN hand-pickup frame(s)
- [11:39:42] flight_22 N=88 model=A source=label: RANSAC rejected [12, 19, 22, 24, 25, 26, 42, 60, 81, 82]
- [11:39:42] flight_22 N=88 model=A source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 12, 17, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 71, 73, 77, 78, 81, 85, 86, 87, 88, 89] <- includes KNOWN hand-pickup frame(s)
- [11:39:42] flight_22 N=88 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 19, 24, 42, 45, 46, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 60, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89] <- includes KNOWN hand-pickup frame(s)
- [11:39:42] flight_22 N=88 model=B source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 16, 17, 18, 21, 35, 39, 41, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 62, 63, 64, 65, 66, 71, 73, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89] <- includes KNOWN hand-pickup frame(s)
- [11:39:43] flight_22 N=88 model=C source=label: RANSAC rejected [3, 24, 82]
- [11:39:44] flight_22 N=88 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 70, 73, 76, 77, 78, 81, 84, 88, 89] <- includes KNOWN hand-pickup frame(s)
- [11:39:44] flight_22 N=89 model=A source=label: RANSAC rejected [19, 22, 24, 25, 26, 60, 67, 78, 79, 85, 86, 87, 89]
- [11:39:44] flight_22 N=89 model=A source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 9, 10, 12, 13, 14, 16, 18, 21, 22, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 56, 59, 60, 62, 63, 64, 65, 66, 71, 73, 77, 78, 81, 84, 85, 86, 88, 89, 92] <- includes KNOWN hand-pickup frame(s)
- [11:39:44] flight_22 N=89 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 34, 60, 62, 64, 67, 79, 82, 85, 86, 87, 88, 89, 92]
- [11:39:44] flight_22 N=89 model=B source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 18, 21, 22, 32, 35, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 58, 59, 60, 61, 62, 63, 64, 65, 66, 71, 73, 77, 78, 81, 82, 83, 84, 85, 86, 87, 88, 89, 92] <- includes KNOWN hand-pickup frame(s)
- [11:39:45] flight_22 N=89 model=C source=label: RANSAC rejected [24, 82, 92]
- [11:39:46] flight_22 N=89 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 56, 59, 60, 62, 63, 64, 65, 66, 71, 73, 77, 78, 81, 85, 86, 88, 89, 92] <- includes KNOWN hand-pickup frame(s)
- [11:39:46] flight_22: 7 (N, model, source) RANSAC-fit points failed to converge (of 522 total)
- [11:39:46] flight_22: 22 (N, model, source) points had N < RANSAC's min_samples -- fell back to the plain fit (expected at low N, matches decision #1)
- [11:39:46] flight_22: sweep complete, 87 N-values, 0 plain + 7 RANSAC convergence failures
- [11:39:46] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep.csv
- [11:39:46] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep_ransac.csv
- [11:39:47] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep_flight_01.png
- [11:39:47] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep_ransac_flight_01.png
- [11:39:48] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep_flight_22.png
- [11:39:49] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep_ransac_flight_22.png
- [11:39:49] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep_ransac_zoom_flight_22.png
- [11:39:49] === trajectory_model_prediction_sweep.py: Phase 2 complete ===

## [bug caught] known_bad_frames tag wasn't scoped to flight_22

While checking the log for confirmation that RANSAC rejects flight_22's
frames 44-47, noticed flight_01 ALSO logged "RANSAC rejected [44] <-
includes KNOWN hand-pickup frame(s)" (e.g. N=21/23/24/25, model A/B, label
source). This is a false positive: `known_bad_frames = {44,45,46,47}` in
run_flight() was a plain frame-number set applied regardless of which
flight -- but flight_01's own fit_frames happen to start at frame 44 (its
own first usable frame, [44..68]), coincidentally the same NUMBER as
flight_22's actual contamination frames, which are a completely different
flight/track. Not a RANSAC correctness bug (RANSAC is doing its job
correctly identifying whatever it identifies), purely a logging/tagging bug
in my own script. Fixing: only apply the known-bad-frame tag when
flight_name == "flight_22". Rerunning (fast, ~2.5 min) before trusting any
"confirmed known-bad-frame" claim in the checkpoint report.
- [11:40:59] === trajectory_model_prediction_sweep.py: Phase 2 starting ===
- [11:40:59] K_FIXED = 6.053818e-05 1/mm (Phase 1 pooled result, Checkpoint-1 approved)
- [11:40:59] g_fixed loaded: |g_fixed|=9810.00 mm/s^2
- [11:40:59] RANSAC config: inlier_threshold=75.0mm, min_samples={'A': 6, 'B': 6, 'C': 8}, n_iterations={'A': 10, 'B': 10, 'C': 15}, seed=42 (shared constants from trajectory_fit.py)
- [11:40:59] flight_01: Phase 2 prediction sweep starting
- [11:40:59] flight_01: label_common=27 frames, det_common=25 frames (tuned detections)
- [11:40:59] flight_01: target_frame=69, fit_frames=25 [44..68]
- [11:41:03] flight_01 N=14 model=A source=det: RANSAC rejected [51]
- [11:41:04] flight_01 N=15 model=A source=det: RANSAC rejected [57]
- [11:41:04] flight_01 N=16 model=A source=det: RANSAC rejected [51]
- [11:41:04] flight_01 N=16 model=B source=det: RANSAC rejected [51]
- [11:41:05] flight_01 N=17 model=B source=det: RANSAC rejected [57]
- [11:41:06] flight_01 N=17 model=C source=det: RANSAC rejected [57]
- [11:41:06] flight_01 N=18 model=A source=det: RANSAC rejected [57]
- [11:41:06] flight_01 N=18 model=B source=det: RANSAC rejected [51, 57]
- [11:41:07] flight_01 N=18 model=C source=det: RANSAC rejected [51, 57]
- [11:41:07] flight_01 N=19 model=A source=det: RANSAC rejected [54]
- [11:41:07] flight_01 N=19 model=B source=det: RANSAC rejected [57]
- [11:41:07] flight_01 N=19 model=C source=det: RANSAC rejected [57]
- [11:41:07] flight_01 N=20 model=B source=det: RANSAC rejected [57]
- [11:41:08] flight_01 N=20 model=C source=det: RANSAC rejected [57]
- [11:41:08] flight_01 N=21 model=A source=label: RANSAC rejected [44]
- [11:41:08] flight_01 N=21 model=B source=det: RANSAC rejected [51, 57]
- [11:41:09] flight_01 N=21 model=C source=det: RANSAC rejected [51, 57]
- [11:41:09] flight_01 N=22 model=A source=det: RANSAC rejected [57, 65]
- [11:41:09] flight_01 N=22 model=B source=label: RANSAC rejected [63]
- [11:41:09] flight_01 N=22 model=B source=det: RANSAC rejected [57]
- [11:41:10] flight_01 N=22 model=C source=det: RANSAC rejected [57]
- [11:41:10] flight_01 N=23 model=A source=label: RANSAC rejected [44]
- [11:41:10] flight_01 N=23 model=A source=det: RANSAC rejected [57]
- [11:41:10] flight_01 N=23 model=B source=det: RANSAC rejected [51, 57]
- [11:41:11] flight_01 N=23 model=C source=det: RANSAC rejected [57]
- [11:41:11] flight_01 N=24 model=A source=label: RANSAC rejected [44]
- [11:41:11] flight_01 N=24 model=A source=det: RANSAC rejected [60]
- [11:41:11] flight_01 N=24 model=B source=det: RANSAC rejected [57]
- [11:41:12] flight_01 N=24 model=C source=det: RANSAC rejected [51, 57]
- [11:41:12] flight_01 N=25 model=A source=det: RANSAC rejected [51, 57, 65]
- [11:41:12] flight_01 N=25 model=B source=label: RANSAC rejected [44]
- [11:41:12] flight_01 N=25 model=B source=det: RANSAC rejected [51, 57, 59, 68]
- [11:41:13] flight_01 N=25 model=C source=det: RANSAC rejected [57, 68]
- [11:41:13] flight_01: 22 (N, model, source) points had N < RANSAC's min_samples -- fell back to the plain fit (expected at low N, matches decision #1)
- [11:41:13] flight_01: sweep complete, 23 N-values, 0 plain + 0 RANSAC convergence failures
- [11:41:13] flight_22: Phase 2 prediction sweep starting
- [11:41:13] flight_22: label_common=93 frames, det_common=89 frames (tuned detections)
- [11:41:13] flight_22: target_frame=93, fit_frames=89 [2..92]
- [11:41:13] flight_22 N=6 model=B source=det: RANSAC FIT FAILED TO CONVERGE -- ransac_fit: no candidate model reached >= min_samples (6) inliers over 10 iterations -- skipping this point
- [11:41:13] flight_22 N=7 model=A source=det: RANSAC FIT FAILED TO CONVERGE -- ransac_fit: no candidate model reached >= min_samples (6) inliers over 10 iterations -- skipping this point
- [11:41:13] flight_22 N=7 model=B source=det: RANSAC FIT FAILED TO CONVERGE -- ransac_fit: no candidate model reached >= min_samples (6) inliers over 10 iterations -- skipping this point
- [11:41:13] flight_22 N=8 model=A source=det: RANSAC FIT FAILED TO CONVERGE -- ransac_fit: no candidate model reached >= min_samples (6) inliers over 10 iterations -- skipping this point
- [11:41:13] flight_22 N=8 model=B source=det: RANSAC FIT FAILED TO CONVERGE -- ransac_fit: no candidate model reached >= min_samples (6) inliers over 10 iterations -- skipping this point
- [11:41:14] flight_22 N=8 model=C source=det: RANSAC FIT FAILED TO CONVERGE -- ransac_fit: no candidate model reached >= min_samples (8) inliers over 15 iterations -- skipping this point
- [11:41:14] flight_22 N=9 model=A source=det: RANSAC rejected [3, 4, 7]
- [11:41:14] flight_22 N=9 model=B source=det: RANSAC rejected [2, 4, 7]
- [11:41:14] flight_22 N=9 model=C source=det: RANSAC FIT FAILED TO CONVERGE -- ransac_fit: no candidate model reached >= min_samples (8) inliers over 15 iterations -- skipping this point
- [11:41:14] flight_22 N=10 model=A source=det: RANSAC rejected [3, 4, 7]
- [11:41:14] flight_22 N=10 model=B source=det: RANSAC rejected [2, 4, 7]
- [11:41:15] flight_22 N=10 model=C source=det: RANSAC rejected [2, 7]
- [11:41:15] flight_22 N=11 model=A source=det: RANSAC rejected [3, 4, 7]
- [11:41:15] flight_22 N=11 model=B source=det: RANSAC rejected [2, 4, 7]
- [11:41:16] flight_22 N=11 model=C source=det: RANSAC rejected [2, 7]
- [11:41:16] flight_22 N=12 model=A source=det: RANSAC rejected [2, 4, 7]
- [11:41:16] flight_22 N=12 model=B source=det: RANSAC rejected [2, 4, 7]
- [11:41:17] flight_22 N=12 model=C source=det: RANSAC rejected [2, 7]
- [11:41:17] flight_22 N=13 model=A source=det: RANSAC rejected [2, 4, 7]
- [11:41:17] flight_22 N=13 model=B source=det: RANSAC rejected [2, 4, 7]
- [11:41:18] flight_22 N=13 model=C source=det: RANSAC rejected [2, 4, 7]
- [11:41:18] flight_22 N=14 model=A source=det: RANSAC rejected [3, 4, 7, 15]
- [11:41:18] flight_22 N=14 model=B source=det: RANSAC rejected [2, 7]
- [11:41:18] flight_22 N=14 model=C source=det: RANSAC rejected [2, 7]
- [11:41:18] flight_22 N=15 model=A source=det: RANSAC rejected [3, 4, 5, 8, 9]
- [11:41:18] flight_22 N=15 model=B source=det: RANSAC rejected [2, 4, 7, 9]
- [11:41:19] flight_22 N=15 model=C source=det: RANSAC rejected [2, 7]
- [11:41:19] flight_22 N=16 model=A source=det: RANSAC rejected [3, 4, 7, 15, 17]
- [11:41:19] flight_22 N=16 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16]
- [11:41:20] flight_22 N=16 model=C source=det: RANSAC rejected [2, 4, 7, 17]
- [11:41:20] flight_22 N=17 model=A source=det: RANSAC rejected [3, 4, 7, 17, 18]
- [11:41:20] flight_22 N=17 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18]
- [11:41:21] flight_22 N=17 model=C source=det: RANSAC rejected [2, 4, 7, 9, 18]
- [11:41:21] flight_22 N=18 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 19]
- [11:41:21] flight_22 N=18 model=B source=det: RANSAC rejected [2, 7, 17, 18]
- [11:41:22] flight_22 N=18 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18]
- [11:41:22] flight_22 N=19 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18]
- [11:41:22] flight_22 N=19 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18]
- [11:41:23] flight_22 N=19 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18]
- [11:41:23] flight_22 N=20 model=A source=det: RANSAC rejected [2, 4, 7, 17, 18, 20, 21]
- [11:41:23] flight_22 N=20 model=B source=det: RANSAC rejected [2, 7, 17, 18, 20, 21]
- [11:41:24] flight_22 N=20 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:41:24] flight_22 N=21 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:41:24] flight_22 N=21 model=B source=det: RANSAC rejected [2, 3, 7, 17, 18, 20, 21]
- [11:41:25] flight_22 N=21 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:41:25] flight_22 N=22 model=A source=det: RANSAC rejected [2, 4, 7, 16, 18, 21, 22]
- [11:41:25] flight_22 N=22 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:41:26] flight_22 N=22 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:41:26] flight_22 N=23 model=A source=det: RANSAC rejected [2, 4, 7, 9, 17, 18, 21]
- [11:41:26] flight_22 N=23 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:41:27] flight_22 N=23 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:41:27] flight_22 N=24 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:41:27] flight_22 N=24 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:41:28] flight_22 N=24 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:41:28] flight_22 N=25 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:41:28] flight_22 N=25 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:41:29] flight_22 N=25 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:41:29] flight_22 N=26 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:41:29] flight_22 N=26 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:41:30] flight_22 N=26 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:41:30] flight_22 N=27 model=A source=det: RANSAC rejected [2, 4, 7, 17, 18, 21]
- [11:41:30] flight_22 N=27 model=B source=label: RANSAC rejected [28]
- [11:41:30] flight_22 N=27 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:41:31] flight_22 N=27 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:41:31] flight_22 N=28 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:41:31] flight_22 N=28 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:41:33] flight_22 N=28 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:41:33] flight_22 N=29 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:41:33] flight_22 N=29 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:41:34] flight_22 N=29 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 23]
- [11:41:34] flight_22 N=30 model=A source=det: RANSAC rejected [2, 4, 7, 18, 21]
- [11:41:34] flight_22 N=30 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 23]
- [11:41:35] flight_22 N=30 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:41:35] flight_22 N=31 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 23]
- [11:41:35] flight_22 N=31 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:41:36] flight_22 N=31 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32]
- [11:41:36] flight_22 N=32 model=A source=det: RANSAC rejected [2, 4, 7, 16, 18, 21, 23]
- [11:41:36] flight_22 N=32 model=B source=det: RANSAC rejected [2, 4, 7, 14, 18, 21, 23]
- [11:41:37] flight_22 N=32 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:41:37] flight_22 N=33 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21]
- [11:41:37] flight_22 N=33 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:41:39] flight_22 N=33 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21]
- [11:41:39] flight_22 N=34 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35]
- [11:41:39] flight_22 N=34 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:41:40] flight_22 N=34 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:41:40] flight_22 N=35 model=A source=det: RANSAC rejected [2, 4, 7, 13, 14, 16, 18, 19, 21, 22]
- [11:41:40] flight_22 N=35 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:41:41] flight_22 N=35 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:41:41] flight_22 N=36 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 35, 37]
- [11:41:41] flight_22 N=36 model=B source=label: RANSAC rejected [36]
- [11:41:41] flight_22 N=36 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 23, 35]
- [11:41:42] flight_22 N=36 model=C source=det: RANSAC rejected [2, 4, 7, 18, 21, 23, 35]
- [11:41:42] flight_22 N=37 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 35]
- [11:41:42] flight_22 N=37 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35]
- [11:41:44] flight_22 N=37 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:41:44] flight_22 N=38 model=A source=det: RANSAC rejected [2, 4, 7, 8, 9, 18, 21, 35]
- [11:41:44] flight_22 N=38 model=B source=det: RANSAC rejected [2, 4, 7, 9, 18, 21, 35]
- [11:41:45] flight_22 N=38 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:41:45] flight_22 N=39 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35]
- [11:41:45] flight_22 N=39 model=B source=label: RANSAC rejected [24]
- [11:41:45] flight_22 N=39 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:41:46] flight_22 N=39 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:41:46] flight_22 N=40 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 35]
- [11:41:46] flight_22 N=40 model=B source=label: RANSAC rejected [24]
- [11:41:46] flight_22 N=40 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35]
- [11:41:47] flight_22 N=40 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:41:47] flight_22 N=41 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35]
- [11:41:47] flight_22 N=41 model=B source=label: RANSAC rejected [24]
- [11:41:47] flight_22 N=41 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35]
- [11:41:49] flight_22 N=41 model=C source=det: RANSAC rejected [2, 4, 7, 16, 18, 21, 35]
- [11:41:49] flight_22 N=42 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35]
- [11:41:49] flight_22 N=42 model=B source=label: RANSAC rejected [42]
- [11:41:49] flight_22 N=42 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35]
- [11:41:49] flight_22 N=42 model=C source=label: RANSAC rejected [42]
- [11:41:50] flight_22 N=42 model=C source=det: RANSAC rejected [2, 4, 7, 16, 18, 21, 35]
- [11:41:50] flight_22 N=43 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35, 44] <- includes KNOWN hand-pickup frame(s)
- [11:41:50] flight_22 N=43 model=B source=label: RANSAC rejected [3, 24]
- [11:41:50] flight_22 N=43 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44] <- includes KNOWN hand-pickup frame(s)
- [11:41:52] flight_22 N=43 model=C source=det: RANSAC rejected [2, 4, 7, 14, 18, 21, 35, 44] <- includes KNOWN hand-pickup frame(s)
- [11:41:52] flight_22 N=44 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45] <- includes KNOWN hand-pickup frame(s)
- [11:41:52] flight_22 N=44 model=B source=label: RANSAC rejected [24]
- [11:41:52] flight_22 N=44 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35, 44, 45] <- includes KNOWN hand-pickup frame(s)
- [11:41:53] flight_22 N=44 model=C source=det: RANSAC rejected [2, 6, 7, 14, 16, 18, 21, 35, 44, 45] <- includes KNOWN hand-pickup frame(s)
- [11:41:53] flight_22 N=45 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46] <- includes KNOWN hand-pickup frame(s)
- [11:41:53] flight_22 N=45 model=B source=label: RANSAC rejected [24]
- [11:41:53] flight_22 N=45 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35, 44, 45, 46] <- includes KNOWN hand-pickup frame(s)
- [11:41:55] flight_22 N=45 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46] <- includes KNOWN hand-pickup frame(s)
- [11:41:55] flight_22 N=46 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47] <- includes KNOWN hand-pickup frame(s)
- [11:41:55] flight_22 N=46 model=B source=label: RANSAC rejected [3, 24]
- [11:41:55] flight_22 N=46 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47] <- includes KNOWN hand-pickup frame(s)
- [11:41:57] flight_22 N=46 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47] <- includes KNOWN hand-pickup frame(s)
- [11:41:57] flight_22 N=47 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47] <- includes KNOWN hand-pickup frame(s)
- [11:41:57] flight_22 N=47 model=B source=label: RANSAC rejected [24]
- [11:41:57] flight_22 N=47 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48] <- includes KNOWN hand-pickup frame(s)
- [11:42:00] flight_22 N=47 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47] <- includes KNOWN hand-pickup frame(s)
- [11:42:00] flight_22 N=48 model=A source=det: RANSAC rejected [2, 4, 7, 9, 14, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47] <- includes KNOWN hand-pickup frame(s)
- [11:42:00] flight_22 N=48 model=B source=label: RANSAC rejected [24]
- [11:42:00] flight_22 N=48 model=B source=det: RANSAC rejected [2, 4, 7, 8, 9, 14, 17, 18, 21, 23, 32, 35, 44, 45, 46, 47] <- includes KNOWN hand-pickup frame(s)
- [11:42:01] flight_22 N=48 model=C source=label: RANSAC rejected [24]
- [11:42:03] flight_22 N=48 model=C source=det: RANSAC rejected [2, 4, 7, 18, 21, 35, 44, 45, 46, 47] <- includes KNOWN hand-pickup frame(s)
- [11:42:03] flight_22 N=49 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 22, 28, 29, 32, 35, 44, 45, 46, 47, 48] <- includes KNOWN hand-pickup frame(s)
- [11:42:03] flight_22 N=49 model=B source=label: RANSAC rejected [3]
- [11:42:03] flight_22 N=49 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50] <- includes KNOWN hand-pickup frame(s)
- [11:42:06] flight_22 N=49 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48] <- includes KNOWN hand-pickup frame(s)
- [11:42:06] flight_22 N=50 model=A source=det: RANSAC rejected [2, 7, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 50, 51] <- includes KNOWN hand-pickup frame(s)
- [11:42:06] flight_22 N=50 model=B source=label: RANSAC rejected [24]
- [11:42:06] flight_22 N=50 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51] <- includes KNOWN hand-pickup frame(s)
- [11:42:07] flight_22 N=50 model=C source=det: RANSAC rejected [2, 4, 7, 18, 21, 23, 35, 44, 45, 46, 47, 48, 50, 51] <- includes KNOWN hand-pickup frame(s)
- [11:42:07] flight_22 N=51 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52] <- includes KNOWN hand-pickup frame(s)
- [11:42:07] flight_22 N=51 model=B source=label: RANSAC rejected [24]
- [11:42:07] flight_22 N=51 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52] <- includes KNOWN hand-pickup frame(s)
- [11:42:09] flight_22 N=51 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52] <- includes KNOWN hand-pickup frame(s)
- [11:42:09] flight_22 N=52 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 20, 21, 23, 35, 44, 45, 46, 47, 50, 51, 52, 53] <- includes KNOWN hand-pickup frame(s)
- [11:42:09] flight_22 N=52 model=B source=label: RANSAC rejected [2, 3, 53]
- [11:42:09] flight_22 N=52 model=B source=det: RANSAC rejected [2, 3, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53] <- includes KNOWN hand-pickup frame(s)
- [11:42:10] flight_22 N=52 model=C source=label: RANSAC rejected [24]
- [11:42:11] flight_22 N=52 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53] <- includes KNOWN hand-pickup frame(s)
- [11:42:11] flight_22 N=53 model=A source=label: RANSAC rejected [54]
- [11:42:11] flight_22 N=53 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 49, 51, 53, 54] <- includes KNOWN hand-pickup frame(s)
- [11:42:11] flight_22 N=53 model=B source=label: RANSAC rejected [2, 3]
- [11:42:11] flight_22 N=53 model=B source=det: RANSAC rejected [2, 3, 4, 7, 14, 17, 18, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53] <- includes KNOWN hand-pickup frame(s)
- [11:42:11] flight_22 N=53 model=C source=label: RANSAC rejected [24]
- [11:42:12] flight_22 N=53 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53] <- includes KNOWN hand-pickup frame(s)
- [11:42:12] flight_22 N=54 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 41, 43, 44, 45, 46, 47, 48, 49, 51, 54] <- includes KNOWN hand-pickup frame(s)
- [11:42:12] flight_22 N=54 model=B source=label: RANSAC rejected [24]
- [11:42:13] flight_22 N=54 model=B source=det: RANSAC rejected [2, 3, 4, 7, 8, 9, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55] <- includes KNOWN hand-pickup frame(s)
- [11:42:14] flight_22 N=54 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 41, 44, 45, 46, 47, 48, 49, 51, 53, 54] <- includes KNOWN hand-pickup frame(s)
- [11:42:14] flight_22 N=55 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 49, 51, 54, 56] <- includes KNOWN hand-pickup frame(s)
- [11:42:14] flight_22 N=55 model=B source=label: RANSAC rejected [24]
- [11:42:14] flight_22 N=55 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 56] <- includes KNOWN hand-pickup frame(s)
- [11:42:16] flight_22 N=55 model=C source=det: RANSAC rejected [2, 4, 7, 18, 21, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55] <- includes KNOWN hand-pickup frame(s)
- [11:42:16] flight_22 N=56 model=A source=det: RANSAC rejected [2, 4, 7, 9, 14, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55] <- includes KNOWN hand-pickup frame(s)
- [11:42:16] flight_22 N=56 model=B source=label: RANSAC rejected [3, 24]
- [11:42:16] flight_22 N=56 model=B source=det: RANSAC rejected [2, 4, 7, 8, 9, 14, 17, 18, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55] <- includes KNOWN hand-pickup frame(s)
- [11:42:18] flight_22 N=56 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 57] <- includes KNOWN hand-pickup frame(s)
- [11:42:18] flight_22 N=57 model=A source=label: RANSAC rejected [42]
- [11:42:18] flight_22 N=57 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58] <- includes KNOWN hand-pickup frame(s)
- [11:42:18] flight_22 N=57 model=B source=label: RANSAC rejected [24]
- [11:42:18] flight_22 N=57 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55] <- includes KNOWN hand-pickup frame(s)
- [11:42:20] flight_22 N=57 model=C source=det: RANSAC rejected [2, 4, 7, 16, 18, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55] <- includes KNOWN hand-pickup frame(s)
- [11:42:20] flight_22 N=58 model=A source=label: RANSAC rejected [24]
- [11:42:20] flight_22 N=58 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 49, 51, 54, 56, 57, 59] <- includes KNOWN hand-pickup frame(s)
- [11:42:20] flight_22 N=58 model=B source=label: RANSAC rejected [24, 42]
- [11:42:20] flight_22 N=58 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 49, 51, 52, 53, 54, 56, 59] <- includes KNOWN hand-pickup frame(s)
- [11:42:22] flight_22 N=58 model=C source=det: RANSAC rejected [2, 4, 7, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59] <- includes KNOWN hand-pickup frame(s)
- [11:42:22] flight_22 N=59 model=A source=label: RANSAC rejected [42]
- [11:42:22] flight_22 N=59 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 22, 29, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60] <- includes KNOWN hand-pickup frame(s)
- [11:42:22] flight_22 N=59 model=B source=label: RANSAC rejected [2, 3, 24, 60]
- [11:42:22] flight_22 N=59 model=B source=det: RANSAC rejected [2, 4, 7, 8, 9, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60] <- includes KNOWN hand-pickup frame(s)
- [11:42:23] flight_22 N=59 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60] <- includes KNOWN hand-pickup frame(s)
- [11:42:23] flight_22 N=60 model=A source=label: RANSAC rejected [42]
- [11:42:24] flight_22 N=60 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 29, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 61] <- includes KNOWN hand-pickup frame(s)
- [11:42:24] flight_22 N=60 model=B source=label: RANSAC rejected [2, 3, 24, 58]
- [11:42:24] flight_22 N=60 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60] <- includes KNOWN hand-pickup frame(s)
- [11:42:25] flight_22 N=60 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60] <- includes KNOWN hand-pickup frame(s)
- [11:42:25] flight_22 N=61 model=A source=label: RANSAC rejected [24]
- [11:42:25] flight_22 N=61 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 49, 51, 53, 54, 56, 59, 61, 62] <- includes KNOWN hand-pickup frame(s)
- [11:42:25] flight_22 N=61 model=B source=label: RANSAC rejected [24, 25, 60, 62]
- [11:42:25] flight_22 N=61 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 23, 35, 44, 45, 46, 47, 48, 49, 51, 52, 53, 56, 59, 60, 62] <- includes KNOWN hand-pickup frame(s)
- [11:42:26] flight_22 N=61 model=C source=label: RANSAC rejected [24]
- [11:42:27] flight_22 N=61 model=C source=det: RANSAC rejected [2, 4, 7, 16, 18, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 61, 62] <- includes KNOWN hand-pickup frame(s)
- [11:42:27] flight_22 N=62 model=A source=label: RANSAC rejected [24, 62]
- [11:42:27] flight_22 N=62 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 49, 51, 53, 54, 56, 59, 61, 62, 63] <- includes KNOWN hand-pickup frame(s)
- [11:42:27] flight_22 N=62 model=B source=label: RANSAC rejected [2, 3, 24, 62]
- [11:42:27] flight_22 N=62 model=B source=det: RANSAC rejected [2, 4, 5, 7, 18, 21, 23, 35, 44, 45, 46, 47, 48, 49, 51, 52, 53, 54, 55, 56, 59, 60, 62, 63] <- includes KNOWN hand-pickup frame(s)
- [11:42:29] flight_22 N=62 model=C source=det: RANSAC rejected [2, 4, 7, 9, 16, 18, 21, 23, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62] <- includes KNOWN hand-pickup frame(s)
- [11:42:29] flight_22 N=63 model=A source=label: RANSAC rejected [42, 60]
- [11:42:29] flight_22 N=63 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 49, 51, 53, 54, 56, 57, 59, 61, 62, 63, 64] <- includes KNOWN hand-pickup frame(s)
- [11:42:29] flight_22 N=63 model=B source=label: RANSAC rejected [3, 24, 62, 63, 64]
- [11:42:29] flight_22 N=63 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 17, 18, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64] <- includes KNOWN hand-pickup frame(s)
- [11:42:30] flight_22 N=63 model=C source=label: RANSAC rejected [24]
- [11:42:31] flight_22 N=63 model=C source=det: RANSAC rejected [2, 4, 6, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64] <- includes KNOWN hand-pickup frame(s)
- [11:42:31] flight_22 N=64 model=A source=label: RANSAC rejected [36, 42]
- [11:42:31] flight_22 N=64 model=A source=det: RANSAC rejected [2, 4, 7, 14, 17, 18, 20, 21, 23, 35, 39, 41, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 61, 62, 64] <- includes KNOWN hand-pickup frame(s)
- [11:42:31] flight_22 N=64 model=B source=label: RANSAC rejected [2, 4, 12, 24, 42, 60]
- [11:42:31] flight_22 N=64 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 17, 18, 21, 23, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 63, 64, 65] <- includes KNOWN hand-pickup frame(s)
- [11:42:32] flight_22 N=64 model=C source=label: RANSAC rejected [24]
- [11:42:33] flight_22 N=64 model=C source=det: RANSAC rejected [2, 4, 7, 9, 17, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 57, 58, 60, 61] <- includes KNOWN hand-pickup frame(s)
- [11:42:33] flight_22 N=65 model=A source=label: RANSAC rejected [24]
- [11:42:33] flight_22 N=65 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 49, 51, 53, 54, 56, 57, 59, 61, 62, 63, 64, 65, 66] <- includes KNOWN hand-pickup frame(s)
- [11:42:33] flight_22 N=65 model=B source=label: RANSAC rejected [3, 24, 33, 36, 42, 60, 66]
- [11:42:33] flight_22 N=65 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 35, 41, 44, 45, 46, 47, 48, 49, 51, 53, 54, 56, 59, 62, 63, 64, 65, 66] <- includes KNOWN hand-pickup frame(s)
- [11:42:34] flight_22 N=65 model=C source=label: RANSAC rejected [24]
- [11:42:35] flight_22 N=65 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58, 60, 61, 64] <- includes KNOWN hand-pickup frame(s)
- [11:42:35] flight_22 N=66 model=A source=label: RANSAC rejected [24]
- [11:42:35] flight_22 N=66 model=A source=det: RANSAC rejected [2, 7, 14, 17, 18, 20, 21, 23, 26, 37, 39, 40, 41, 43, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 60, 61, 66, 67] <- includes KNOWN hand-pickup frame(s)
- [11:42:35] flight_22 N=66 model=B source=label: RANSAC rejected [24, 36, 42, 67]
- [11:42:35] flight_22 N=66 model=B source=det: RANSAC rejected [2, 4, 7, 14, 17, 18, 21, 23, 35, 39, 41, 44, 45, 46, 47, 48, 49, 51, 52, 53, 56, 59, 60, 62, 63, 64, 65, 66] <- includes KNOWN hand-pickup frame(s)
- [11:42:36] flight_22 N=66 model=C source=label: RANSAC rejected [24]
- [11:42:37] flight_22 N=66 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 57, 58, 60, 61, 66, 67] <- includes KNOWN hand-pickup frame(s)
- [11:42:37] flight_22 N=67 model=A source=label: RANSAC rejected [24]
- [11:42:37] flight_22 N=67 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 61, 62, 64, 65, 68] <- includes KNOWN hand-pickup frame(s)
- [11:42:37] flight_22 N=67 model=B source=label: RANSAC rejected [2, 3, 24, 36, 42, 67]
- [11:42:37] flight_22 N=67 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 34, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 68] <- includes KNOWN hand-pickup frame(s)
- [11:42:39] flight_22 N=67 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 68] <- includes KNOWN hand-pickup frame(s)
- [11:42:39] flight_22 N=68 model=A source=label: RANSAC rejected [24]
- [11:42:39] flight_22 N=68 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 66] <- includes KNOWN hand-pickup frame(s)
- [11:42:39] flight_22 N=68 model=B source=label: RANSAC rejected [2, 3, 4, 24, 36, 42, 67]
- [11:42:39] flight_22 N=68 model=B source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 23, 32, 35, 44, 45, 46, 47, 48, 49, 51, 52, 53, 55, 56, 59, 60, 62, 63, 64, 65, 66, 69] <- includes KNOWN hand-pickup frame(s)
- [11:42:41] flight_22 N=68 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58, 60, 61, 64, 67, 68, 69] <- includes KNOWN hand-pickup frame(s)
- [11:42:41] flight_22 N=69 model=A source=label: RANSAC rejected [24]
- [11:42:41] flight_22 N=69 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 64, 68, 70] <- includes KNOWN hand-pickup frame(s)
- [11:42:41] flight_22 N=69 model=B source=label: RANSAC rejected [2, 3, 24, 36, 42, 67, 69, 70]
- [11:42:41] flight_22 N=69 model=B source=det: RANSAC rejected [2, 4, 7, 8, 9, 14, 16, 17, 18, 21, 23, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 68, 69, 70] <- includes KNOWN hand-pickup frame(s)
- [11:42:43] flight_22 N=69 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70] <- includes KNOWN hand-pickup frame(s)
- [11:42:43] flight_22 N=70 model=A source=label: RANSAC rejected [42]
- [11:42:43] flight_22 N=70 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 68, 70] <- includes KNOWN hand-pickup frame(s)
- [11:42:43] flight_22 N=70 model=B source=label: RANSAC rejected [2, 3, 24, 36, 42, 60, 67, 69, 70, 71]
- [11:42:43] flight_22 N=70 model=B source=det: RANSAC rejected [2, 3, 4, 7, 8, 14, 16, 18, 21, 32, 34, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 57, 58, 60, 61, 67, 68, 69, 70, 71] <- includes KNOWN hand-pickup frame(s)
- [11:42:44] flight_22 N=70 model=C source=label: RANSAC rejected [3]
- [11:42:45] flight_22 N=70 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70] <- includes KNOWN hand-pickup frame(s)
- [11:42:45] flight_22 N=71 model=A source=label: RANSAC rejected [24]
- [11:42:45] flight_22 N=71 model=A source=det: RANSAC rejected [2, 4, 7, 8, 9, 14, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 64, 68, 70] <- includes KNOWN hand-pickup frame(s)
- [11:42:45] flight_22 N=71 model=B source=label: RANSAC rejected [2, 12, 19, 22, 24, 25, 26, 42, 70, 71, 72]
- [11:42:45] flight_22 N=71 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 49, 51, 52, 53, 54, 56, 59, 60, 62, 63, 64, 65, 66, 69, 70, 71, 72] <- includes KNOWN hand-pickup frame(s)
- [11:42:46] flight_22 N=71 model=C source=label: RANSAC rejected [42]
- [11:42:47] flight_22 N=71 model=C source=det: RANSAC rejected [2, 4, 7, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70] <- includes KNOWN hand-pickup frame(s)
- [11:42:47] flight_22 N=72 model=A source=label: RANSAC rejected [42, 72]
- [11:42:47] flight_22 N=72 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 22, 25, 28, 29, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 73] <- includes KNOWN hand-pickup frame(s)
- [11:42:47] flight_22 N=72 model=B source=label: RANSAC rejected [2, 3, 4, 24, 33, 36, 39, 40, 42, 43, 45, 46, 72, 73] <- includes KNOWN hand-pickup frame(s)
- [11:42:47] flight_22 N=72 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 22, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 66, 69, 70, 71, 72, 73] <- includes KNOWN hand-pickup frame(s)
- [11:42:48] flight_22 N=72 model=C source=label: RANSAC rejected [42]
- [11:42:49] flight_22 N=72 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 70, 73] <- includes KNOWN hand-pickup frame(s)
- [11:42:49] flight_22 N=73 model=A source=label: RANSAC rejected [3, 24, 26]
- [11:42:49] flight_22 N=73 model=A source=det: RANSAC rejected [2, 4, 7, 9, 14, 17, 18, 21, 23, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 60, 61, 64, 67, 68, 69, 70, 72, 73, 74] <- includes KNOWN hand-pickup frame(s)
- [11:42:49] flight_22 N=73 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 12, 24, 36, 42, 71, 72, 73, 74]
- [11:42:49] flight_22 N=73 model=B source=det: RANSAC rejected [2, 3, 4, 7, 8, 9, 14, 17, 18, 21, 23, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 60, 61, 64, 67, 68, 69, 70, 71, 72, 73, 74] <- includes KNOWN hand-pickup frame(s)
- [11:42:51] flight_22 N=73 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58, 60, 61, 64, 67, 68, 70] <- includes KNOWN hand-pickup frame(s)
- [11:42:51] flight_22 N=74 model=A source=label: RANSAC rejected [24, 42, 60]
- [11:42:51] flight_22 N=74 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 29, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58, 59, 60, 62, 63, 64, 65, 70, 73] <- includes KNOWN hand-pickup frame(s)
- [11:42:51] flight_22 N=74 model=B source=label: RANSAC rejected [2, 3, 4, 12, 24, 25, 42, 67, 69, 70, 71, 72, 73, 74, 75]
- [11:42:51] flight_22 N=74 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 8, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 71, 72, 73, 74, 75] <- includes KNOWN hand-pickup frame(s)
- [11:42:52] flight_22 N=74 model=C source=label: RANSAC rejected [24]
- [11:42:53] flight_22 N=74 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 73] <- includes KNOWN hand-pickup frame(s)
- [11:42:53] flight_22 N=75 model=A source=label: RANSAC rejected [2, 3, 24]
- [11:42:53] flight_22 N=75 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 22, 28, 29, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 68, 70, 73, 76] <- includes KNOWN hand-pickup frame(s)
- [11:42:53] flight_22 N=75 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 24, 33, 36, 39, 42, 43, 45, 73, 74, 75, 76] <- includes KNOWN hand-pickup frame(s)
- [11:42:53] flight_22 N=75 model=B source=det: RANSAC rejected [2, 4, 7, 8, 14, 16, 17, 18, 21, 23, 32, 34, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 71, 72, 73, 74, 75, 76] <- includes KNOWN hand-pickup frame(s)
- [11:42:55] flight_22 N=75 model=C source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 73, 76] <- includes KNOWN hand-pickup frame(s)
- [11:42:55] flight_22 N=76 model=A source=label: RANSAC rejected [2, 3, 24]
- [11:42:55] flight_22 N=76 model=A source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 68, 70, 73, 76, 77] <- includes KNOWN hand-pickup frame(s)
- [11:42:55] flight_22 N=76 model=B source=label: RANSAC rejected [12, 19, 22, 24, 25, 26, 33, 36, 42, 60, 67, 69, 71, 72, 73, 74, 75, 76, 77]
- [11:42:55] flight_22 N=76 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 13, 14, 16, 18, 21, 22, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 54, 55, 56, 59, 60, 62, 63, 64, 65, 66, 71, 73, 74, 75, 76, 77] <- includes KNOWN hand-pickup frame(s)
- [11:42:56] flight_22 N=76 model=C source=label: RANSAC rejected [42]
- [11:42:57] flight_22 N=76 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 71, 73, 77] <- includes KNOWN hand-pickup frame(s)
- [11:42:57] flight_22 N=77 model=A source=label: RANSAC rejected [3, 36, 42, 60]
- [11:42:57] flight_22 N=77 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 23, 35, 39, 41, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 64, 67, 68, 69, 70, 72, 74, 75, 76, 77, 78] <- includes KNOWN hand-pickup frame(s)
- [11:42:57] flight_22 N=77 model=B source=label: RANSAC rejected [2, 3, 4, 5, 12, 24, 36, 42, 71, 72, 73, 74, 75, 76, 77, 78]
- [11:42:57] flight_22 N=77 model=B source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 11, 14, 16, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 61, 62, 64, 68, 70, 72, 73, 74, 75, 76, 77, 78] <- includes KNOWN hand-pickup frame(s)
- [11:42:58] flight_22 N=77 model=C source=label: RANSAC rejected [78]
- [11:42:59] flight_22 N=77 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 60, 61, 64, 67, 68, 70, 76, 77, 78] <- includes KNOWN hand-pickup frame(s)
- [11:42:59] flight_22 N=78 model=A source=label: RANSAC rejected [12, 24, 26]
- [11:42:59] flight_22 N=78 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 23, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 51, 54, 56, 57, 59, 62, 63, 64, 65, 66, 71, 73, 77, 78] <- includes KNOWN hand-pickup frame(s)
- [11:42:59] flight_22 N=78 model=B source=label: RANSAC rejected [2, 3, 4, 5, 12, 24, 25, 36, 42, 67, 71, 72, 73, 74, 75, 76, 77, 78, 79]
- [11:42:59] flight_22 N=78 model=B source=det: RANSAC rejected [2, 3, 4, 7, 8, 9, 14, 16, 17, 18, 21, 23, 32, 33, 34, 35, 36, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 61, 62, 64, 68, 70, 72, 73, 74, 75, 76, 77, 78, 79] <- includes KNOWN hand-pickup frame(s)
- [11:43:00] flight_22 N=78 model=C source=label: RANSAC rejected [3]
- [11:43:02] flight_22 N=78 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 70, 73, 76, 77, 78] <- includes KNOWN hand-pickup frame(s)
- [11:43:02] flight_22 N=79 model=A source=label: RANSAC rejected [24, 72, 74, 80]
- [11:43:02] flight_22 N=79 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 17, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 63, 64, 65, 70, 73, 76, 77, 78, 80] <- includes KNOWN hand-pickup frame(s)
- [11:43:02] flight_22 N=79 model=B source=label: RANSAC rejected [2, 3, 4, 5, 12, 24, 36, 39, 42, 43, 45, 60, 67, 71, 73, 74, 75, 76, 77, 78, 79, 80] <- includes KNOWN hand-pickup frame(s)
- [11:43:02] flight_22 N=79 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 23, 32, 33, 34, 35, 36, 39, 44, 45, 46, 47, 48, 50, 51, 52, 53, 54, 55, 58, 59, 60, 62, 63, 64, 65, 70, 73, 74, 75, 76, 77, 78, 79, 80] <- includes KNOWN hand-pickup frame(s)
- [11:43:03] flight_22 N=79 model=C source=label: RANSAC rejected [3, 24]
- [11:43:04] flight_22 N=79 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 70, 73, 77, 78] <- includes KNOWN hand-pickup frame(s)
- [11:43:04] flight_22 N=80 model=A source=label: RANSAC rejected [24, 42, 60, 67, 71, 78, 79]
- [11:43:04] flight_22 N=80 model=A source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 71, 73, 75, 77, 78, 79, 81] <- includes KNOWN hand-pickup frame(s)
- [11:43:04] flight_22 N=80 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 24, 42, 74, 75, 76, 77, 78, 79, 80, 81]
- [11:43:04] flight_22 N=80 model=B source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 23, 32, 33, 34, 35, 36, 37, 39, 44, 45, 46, 47, 48, 50, 51, 52, 53, 54, 55, 58, 59, 60, 62, 64, 65, 70, 73, 74, 75, 76, 77, 78, 79, 80, 81] <- includes KNOWN hand-pickup frame(s)
- [11:43:05] flight_22 N=80 model=C source=label: RANSAC rejected [24]
- [11:43:06] flight_22 N=80 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 70, 71, 73, 77, 78, 81] <- includes KNOWN hand-pickup frame(s)
- [11:43:06] flight_22 N=81 model=A source=label: RANSAC rejected [36, 42, 60, 79, 80, 81, 82]
- [11:43:06] flight_22 N=81 model=A source=det: RANSAC rejected [3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 17, 18, 20, 21, 23, 32, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 73, 77, 78, 81] <- includes KNOWN hand-pickup frame(s)
- [11:43:06] flight_22 N=81 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 24, 42, 60, 76, 77, 78, 79, 80, 81, 82]
- [11:43:06] flight_22 N=81 model=B source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16, 17, 18, 20, 21, 23, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 68, 70, 73, 76, 77, 78, 79, 80, 81, 82] <- includes KNOWN hand-pickup frame(s)
- [11:43:07] flight_22 N=81 model=C source=label: RANSAC rejected [24, 82]
- [11:43:08] flight_22 N=81 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 23, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 70, 71, 73, 76, 77, 78, 81] <- includes KNOWN hand-pickup frame(s)
- [11:43:08] flight_22 N=82 model=A source=label: RANSAC rejected [19, 22, 24, 25, 26, 80, 81, 82]
- [11:43:08] flight_22 N=82 model=A source=det: RANSAC rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 70, 71, 73, 76, 77, 78, 81] <- includes KNOWN hand-pickup frame(s)
- [11:43:08] flight_22 N=82 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 19, 24, 42, 60, 76, 77, 78, 79, 80, 81, 82, 83]
- [11:43:08] flight_22 N=82 model=B source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 11, 14, 16, 18, 21, 32, 34, 35, 39, 41, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 58, 59, 60, 62, 63, 64, 65, 70, 71, 73, 77, 78, 79, 80, 81, 82, 83] <- includes KNOWN hand-pickup frame(s)
- [11:43:09] flight_22 N=82 model=C source=label: RANSAC rejected [24, 82]
- [11:43:10] flight_22 N=82 model=C source=det: RANSAC rejected [2, 4, 7, 9, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 73, 76, 77, 78, 80, 81] <- includes KNOWN hand-pickup frame(s)
- [11:43:10] flight_22 N=83 model=A source=label: RANSAC rejected [2, 3, 24, 25, 26, 82]
- [11:43:10] flight_22 N=83 model=A source=det: RANSAC rejected [2, 5, 6, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 70, 73, 76, 77, 78, 80, 81, 82, 83, 84] <- includes KNOWN hand-pickup frame(s)
- [11:43:10] flight_22 N=83 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 12, 24, 33, 36, 39, 40, 41, 42, 43, 45, 46, 51, 53, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84] <- includes KNOWN hand-pickup frame(s)
- [11:43:10] flight_22 N=83 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 22, 32, 33, 34, 35, 36, 44, 45, 46, 47, 48, 50, 51, 52, 53, 54, 55, 58, 59, 60, 62, 63, 64, 65, 70, 71, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84] <- includes KNOWN hand-pickup frame(s)
- [11:43:11] flight_22 N=83 model=C source=label: RANSAC rejected [24, 82]
- [11:43:13] flight_22 N=83 model=C source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 71, 73, 77, 78, 81] <- includes KNOWN hand-pickup frame(s)
- [11:43:13] flight_22 N=84 model=A source=label: RANSAC rejected [3, 24, 80, 81, 82, 83, 84, 85]
- [11:43:13] flight_22 N=84 model=A source=det: RANSAC rejected [2, 5, 7, 14, 16, 18, 21, 22, 25, 28, 29, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 71, 73, 77, 78, 81, 85] <- includes KNOWN hand-pickup frame(s)
- [11:43:13] flight_22 N=84 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 19, 20, 22, 24, 25, 26, 42, 51, 53, 60, 77, 78, 79, 80, 81, 82, 83, 84, 85]
- [11:43:13] flight_22 N=84 model=B source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 16, 18, 21, 22, 32, 35, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 71, 73, 77, 78, 81, 82, 83, 84, 85] <- includes KNOWN hand-pickup frame(s)
- [11:43:14] flight_22 N=84 model=C source=label: RANSAC rejected [24, 82]
- [11:43:15] flight_22 N=84 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 70, 73, 76, 77, 78, 80, 81, 84] <- includes KNOWN hand-pickup frame(s)
- [11:43:15] flight_22 N=85 model=A source=label: RANSAC rejected [24, 26, 82]
- [11:43:15] flight_22 N=85 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 14, 16, 18, 21, 22, 25, 28, 29, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 63, 64, 65, 70, 73, 76, 77, 78, 80, 81, 82, 83, 84] <- includes KNOWN hand-pickup frame(s)
- [11:43:15] flight_22 N=85 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 24, 36, 42, 43, 45, 46, 49, 51, 52, 53, 60, 67, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86] <- includes KNOWN hand-pickup frame(s)
- [11:43:15] flight_22 N=85 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 8, 10, 11, 13, 14, 16, 18, 21, 22, 25, 28, 29, 32, 34, 35, 36, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 58, 59, 60, 62, 63, 64, 65, 71, 73, 75, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86] <- includes KNOWN hand-pickup frame(s)
- [11:43:16] flight_22 N=85 model=C source=label: RANSAC rejected [3, 42, 82]
- [11:43:17] flight_22 N=85 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 73, 76, 77, 78, 80, 81, 84] <- includes KNOWN hand-pickup frame(s)
- [11:43:17] flight_22 N=86 model=A source=label: RANSAC rejected [12, 19, 22, 24, 25, 26, 82]
- [11:43:17] flight_22 N=86 model=A source=det: RANSAC rejected [2, 3, 5, 7, 14, 16, 18, 21, 22, 25, 27, 28, 29, 31, 32, 34, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58, 59, 60, 61, 62, 64, 68, 70, 73, 76, 77, 78, 80, 81, 82, 83, 84] <- includes KNOWN hand-pickup frame(s)
- [11:43:17] flight_22 N=86 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 19, 20, 22, 24, 25, 26, 42, 53, 60, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87]
- [11:43:17] flight_22 N=86 model=B source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 18, 19, 21, 22, 25, 28, 29, 32, 34, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 54, 55, 56, 58, 59, 60, 62, 63, 64, 65, 71, 73, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87] <- includes KNOWN hand-pickup frame(s)
- [11:43:18] flight_22 N=86 model=C source=label: RANSAC rejected [24, 82]
- [11:43:20] flight_22 N=86 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 70, 73, 77, 78, 81, 84] <- includes KNOWN hand-pickup frame(s)
- [11:43:20] flight_22 N=87 model=A source=label: RANSAC rejected [2, 3, 24, 25, 26, 78, 79, 85, 86, 87, 88]
- [11:43:20] flight_22 N=87 model=A source=det: RANSAC rejected [2, 3, 5, 6, 7, 13, 14, 16, 18, 21, 22, 25, 27, 28, 29, 31, 32, 34, 35, 44, 45, 46, 47, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 65, 70, 73, 76, 77, 78, 81, 84, 85, 88] <- includes KNOWN hand-pickup frame(s)
- [11:43:20] flight_22 N=87 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 29, 60, 67, 78, 79, 81, 82, 83, 84, 85, 86, 87, 88]
- [11:43:20] flight_22 N=87 model=B source=det: RANSAC rejected [2, 3, 5, 6, 7, 8, 10, 11, 13, 14, 16, 18, 21, 22, 25, 29, 32, 35, 44, 45, 46, 47, 48, 49, 51, 52, 53, 54, 55, 56, 59, 60, 62, 63, 64, 65, 66, 69, 71, 72, 73, 74, 75, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88] <- includes KNOWN hand-pickup frame(s)
- [11:43:21] flight_22 N=87 model=C source=label: RANSAC rejected [3, 82]
- [11:43:22] flight_22 N=87 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 58, 59, 60, 62, 64, 70, 73, 76, 77, 78, 80, 81, 84] <- includes KNOWN hand-pickup frame(s)
- [11:43:22] flight_22 N=88 model=A source=label: RANSAC rejected [12, 19, 22, 24, 25, 26, 42, 60, 81, 82]
- [11:43:22] flight_22 N=88 model=A source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 12, 17, 18, 21, 32, 35, 44, 45, 46, 47, 48, 50, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 71, 73, 77, 78, 81, 85, 86, 87, 88, 89] <- includes KNOWN hand-pickup frame(s)
- [11:43:22] flight_22 N=88 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 19, 24, 42, 45, 46, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 60, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89] <- includes KNOWN hand-pickup frame(s)
- [11:43:22] flight_22 N=88 model=B source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 16, 17, 18, 21, 35, 39, 41, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 62, 63, 64, 65, 66, 71, 73, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89] <- includes KNOWN hand-pickup frame(s)
- [11:43:23] flight_22 N=88 model=C source=label: RANSAC rejected [3, 24, 82]
- [11:43:24] flight_22 N=88 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 59, 60, 62, 63, 64, 65, 70, 73, 76, 77, 78, 81, 84, 88, 89] <- includes KNOWN hand-pickup frame(s)
- [11:43:24] flight_22 N=89 model=A source=label: RANSAC rejected [19, 22, 24, 25, 26, 60, 67, 78, 79, 85, 86, 87, 89]
- [11:43:24] flight_22 N=89 model=A source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 9, 10, 12, 13, 14, 16, 18, 21, 22, 32, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 56, 59, 60, 62, 63, 64, 65, 66, 71, 73, 77, 78, 81, 84, 85, 86, 88, 89, 92] <- includes KNOWN hand-pickup frame(s)
- [11:43:24] flight_22 N=89 model=B source=label: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 34, 60, 62, 64, 67, 79, 82, 85, 86, 87, 88, 89, 92]
- [11:43:24] flight_22 N=89 model=B source=det: RANSAC rejected [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 18, 21, 22, 32, 35, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 58, 59, 60, 61, 62, 63, 64, 65, 66, 71, 73, 77, 78, 81, 82, 83, 84, 85, 86, 87, 88, 89, 92] <- includes KNOWN hand-pickup frame(s)
- [11:43:26] flight_22 N=89 model=C source=label: RANSAC rejected [24, 82, 92]
- [11:43:27] flight_22 N=89 model=C source=det: RANSAC rejected [2, 4, 7, 14, 16, 18, 21, 35, 44, 45, 46, 47, 48, 51, 52, 53, 55, 56, 59, 60, 62, 63, 64, 65, 66, 71, 73, 77, 78, 81, 85, 86, 88, 89, 92] <- includes KNOWN hand-pickup frame(s)
- [11:43:27] flight_22: 7 (N, model, source) RANSAC-fit points failed to converge (of 522 total)
- [11:43:27] flight_22: 22 (N, model, source) points had N < RANSAC's min_samples -- fell back to the plain fit (expected at low N, matches decision #1)
- [11:43:27] flight_22: sweep complete, 87 N-values, 0 plain + 7 RANSAC convergence failures
- [11:43:27] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep.csv
- [11:43:27] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep_ransac.csv
- [11:43:27] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep_flight_01.png
- [11:43:28] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep_ransac_flight_01.png
- [11:43:28] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep_flight_22.png
- [11:43:29] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep_ransac_flight_22.png
- [11:43:29] wrote C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\trajectory_fit_comparison\phase2\prediction_sweep_ransac_zoom_flight_22.png
- [11:43:29] === trajectory_model_prediction_sweep.py: Phase 2 complete ===

## [rerun verified] Phase 2 RANSAC results, post-bugfix

Total runtime ~2m36s (11:37:13-11:39:49 first run structure; rerun similar),
well within the 10-minute budget. 7 RANSAC convergence failures on
flight_22 (all at N=6-9, det source, models A/B/C -- window too small
relative to min_samples/threshold combination to find any valid candidate;
expected at the very low end, not a correctness issue, these fall through
to NaN in the CSV same as the plain-fit convergence-failure convention).

**Known-bad-frame verification (the direct answer to "did it work"):**
grepped the fresh log for flight_22's det-source rejections at N=43-50 (the
window where frames 44/45/46/47 enter) -- ALL THREE MODELS correctly flag
them, e.g. N=46 model=C: "rejected [2, 7, 14, 16, 18, 21, 32, 35, 44, 45,
46, 47]" -- all 4 known contamination frames present, confirmed at every N
from 43 (frame 44 enters) through 47+ (all 4 present) across A, B, AND C.
Zero false negatives (no case where a known-bad frame entered the window
but wasn't rejected).

**Did the spike shrink?** Dramatically -- checked prediction_sweep.csv vs
prediction_sweep_ransac.csv directly, N=40-50, flight_22 det source:
  N=44: A_plain=26058mm -> A_RANSAC=662mm; B_plain=3775mm -> B_RANSAC=694mm;
        C_plain=2953mm -> C_RANSAC=150mm
  N=46: A_plain=30934mm -> A_RANSAC=653mm; B_plain=5103mm -> B_RANSAC=694mm;
        C_plain=4078mm -> C_RANSAC=140mm
RANSAC's values at N=43-50 are essentially FLAT and match the clean N=42
baseline (A~660-920mm, B~670-700mm, C~117-164mm) -- the spike doesn't just
shrink, it's essentially eliminated, RANSAC-fit error at the contaminated
N's is indistinguishable from the surrounding clean N's. Visual confirmation
in prediction_sweep_ransac_zoom_flight_22.png: the massive dashed-line spike
in the right (det) panel has no counterpart in the solid RANSAC lines.

**Model A's low-N behavior (expected: unchanged per decision #1):**
checked flight_22 label source N=3-14: err_A_label_mm is BYTE-IDENTICAL
between plain and RANSAC at every one of these N (364548.6, 94185.9,
20409.5, 21357.9, 10147.9, 3347.2, 2830.0, 6708.5, 9337.1, 3282.8, 4351.2,
5325.0 mm -- exact match down to the last decimal printed). N=3,4,5 fall
back to the plain fit (below min_samples=6, RANSAC not applicable, logged
explicitly). N=6-14 DO run RANSAC but every point ends up counted as an
inlier -- Model A's low-N instability isn't a few discrete bad points
RANSAC can carve out, it's the whole fit being underdetermined, exactly as
decision #1 predicted. NOT a surprise -- confirms the expected null result.

**Surprisingly-many-rejected check:** counted rejected-frame-list lengths
across the whole sweep. flight_01: small everywhere (max 1-4 rejected,
mean ~1-1.6) -- unremarkable. flight_22 label source: also modest (max
3-43, but the 43-max is Model B echoing Phase 1's own finding that B's
full-arc fit is worst-conditioned on this flight -- consistent, not new).
flight_22 DET source at LARGE N (approaching the full ~1.5s arc): rejects a
LOT -- up to 45/89 (A), 56/89 (B), 35/89 (C) at the largest N values. This
is NOT new contamination -- it's the exact "full-arc model-fit spread
exceeds 75mm even for clean points" effect already diagnosed earlier in
this session (see the "sanity test" section above) showing up now inside
Phase 2's own largest-N windows, which are effectively the same full-arc
regime. Flagging clearly: this means RANSAC-C's det-curve numbers at the
VERY largest N (shortest lead time, <100ms, already the least
operationally-relevant regime per Phase 2's original findings) are noisier/
less trustworthy than at low-to-moderate N -- consistent with, not
contradicting, the confirmed-bug fix at N~44-47.

## [checkpoint] Reporting to Chin Wei now, per task's "STOP after Phase 1 +
Phase 2 RANSAC results" instruction -- waiting for direction before any
generalization beyond flight_01/flight_22.
