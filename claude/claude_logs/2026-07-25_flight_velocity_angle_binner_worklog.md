# 2026-07-25 — Flight velocity/angle binner worklog

Task: compute initial launch speed + elevation angle for every flight in
`data/2026_07_21_gym/ball_flights`, plot the distribution (speed vs angle,
marginal histograms), so Chin Wei can choose stratified hand-labelling bins
(Link B, context.md §4.9) from real data. Deliverable = the distribution, NOT
chosen bins. Two checkpoints: (1) world-frame registration validation, (2) full
batch + plots.

Related: reuses `src/stereo/label_vs_detection.py` (triangulate, load_calib),
`src/stereo/predict_sweep.py` (fit_constant_accel, gravity cross-check),
`src/image_processing/02_adjacent_frame_differencing/detector_core.py`
(filter_trajectory_outliers), `src/registration/world_frame_precision_single.py`
(guardrail checks). Not modifying any of these.

---

## [start] Setup

- Read `claude/claude_rules.md` (logging conventions, data-protection rules —
  never overwrite/delete under `data/` or `calibration_outputs/`) and
  `claude/context.md` in full (§4.5 detection pipeline, §4.8 calibration/
  world-frame, §4.9 arc capture/Link B, §8 data strategy).
- Confirmed: `data/2026_07_21_gym/ball_flights/` has 150 flight folders
  (flight_1 .. flight_150 roughly). `data/2026_07_21_gym/world_registration/`
  has `cam0/` and `cam1/` subfolders (need to check for the 4 candidate images:
  img_0031-0034).
- Next: read the 5 scripts to reuse, log a summary of each before writing code.

## [reading scripts] Summary of reusable pieces

- `label_vs_detection.py`: `load_calib(calib_dir, extrinsics_path)` loads K0/D0/K1/D1/R/T
  (R,T map cam0->cam1). `triangulate(uv0, uv1, K0, D0, K1, D1, P0, P1)` does
  fisheye undistort (`cv2.fisheye.undistortPoints`) + `cv2.triangulatePoints`,
  returns Nx3 in cam0 frame (mm). `fit_parabola_axis(t, p)` is the raw per-axis
  least-squares fit p0,v0,a. P0=[I|0], P1=[R|T]. Will import `triangulate`,
  `load_calib`, `fit_parabola_axis` directly.
- `predict_sweep.py`: `fit_constant_accel(t, xyz)` calls `fit_parabola_axis` per
  axis, returns (p0,v0,a) as 3-vectors -- this is the exact function named in
  the task. Also has the gravity-vs-world-up cross-check pattern (angle between
  fit-derived "up" = -a/|a| and a world "up" vector, >45 deg = warning) -- will
  replicate this comparison, not copy the script itself, since it's entangled
  with that script's own N-sweep/plotting flow. Imports
  `from src.stereo.world_registration import solve_world_frame, world_transform`
  for its OWN world-frame display plots -- note this is a DIFFERENT world-frame
  method than `world_frame_precision_single.py` (see finding below).
- `world_frame_precision_single.py`: guardrail pipeline for world-frame
  precision. STEP 1 builds world axes from (a) a MANUALLY CLICKED vertical-line
  CSV (V_top/V_bottom pixel coords, via the separate interactive tool
  `label_vertical_line.py`) triangulated to get `up_vec`, and (b) the stereo
  extrinsics baseline `T` to get `baseline_dir`; X_world/Y_world/Z_world are
  then built orthonormally. STEP 2 guardrails: (a) angle(baseline_dir, up_vec)
  ~= 90 deg (rig square side-on check), (b) weak axis must be Y_world (largest
  corner-residual spread axis check). STEP 3 triangulates the checkerboard's 77
  corners, Umeyama-fits to the known grid (`umeyama_alignment`, SVD-based), and
  reports RMS residual projected onto each world axis (X=person->rebounder
  STRONG, Y=width WEAK, Z=vertical STRONG) as the precision numbers.
- `detector_core.py`: `filter_trajectory_outliers(detections, max_speed_px_per_frame=80.0,
  min_run_length=2, max_passes=5)` de-spikes single implausible-jump points then
  splits into runs at remaining implausible jumps, keeps runs >= min_run_length.
  Operates on `{frame_number: (u,v)}` dicts -- exactly the shape produced by
  reading a `*_detections3.csv`. Will import directly, unmodified.
- `src/stereo/world_registration.py` (checked because `predict_sweep.py`
  imports it under that name, NOT `src/registration/`): `solve_world_frame(image_path, K, D)`
  detects a checkerboard in a SINGLE cam0 image and solves its pose via
  `cv2.solvePnP`, deriving world axes purely from the checkerboard's own
  row/column pixel geometry (empirically detects which raw corner-order edge is
  image-left vs image-right, and which raw row is image-top vs image-bottom) --
  assumes the board's ROWS run vertically in real space (board held upright,
  not lying flat) so that row-direction = world up/down. Self-contained: no
  manual clicking, no vertical-line CSV. Returns (R_wc, T_wc);
  `world_transform(pts, R_wc, T_wc)` maps cam0-frame points to world frame
  (x=left-right, y=bottom-up, z=into-board).

## [blocker found] world_frame_precision_single.py needs data that doesn't exist for this session

`world_frame_precision_single.py`'s guardrails require a vertical-line CSV
(`vertical_camN.csv`, point_id/u/v for V_top/V_bottom) produced by manually
clicking two points on a real vertical edge, via the INTERACTIVE GUI tool
`label_vertical_line.py` (cv2.imshow + mouse callbacks -- requires a human
clicking on a rendered window, not scriptable non-interactively).

Searched the whole repo: the only vertical-line CSVs that exist are
`data/2026_07_12_session/validation/results/world_frame/vertical_cam{0,1}.csv`
-- a DIFFERENT session. Per context.md §4.8, world-registration is per-session
and does NOT survive across sessions/mountings (unlike extrinsics) -- so that
CSV is not valid for `2026_07_21_gym`. `data/2026_07_21_gym/world_registration/`
contains only the 4 checkerboard images (img_0031-0034 across
registration1/registration2) and nothing else -- no vertical-line data, no
`results/` subfolder.

Viewed img_0031.png (cam0 and cam1, registration1): a person holds a
checkerboard roughly upright/vertical on a chair, gym wall/climbing-wall
background. Board orientation looks consistent with
`world_registration.py`'s `solve_world_frame()` assumption (rows run
vertically) -- that function is self-contained and needs no manual click.

This is a genuine blocker, not a guessable default: I cannot perform the
interactive clicking myself (no way to render/click a GUI window in this
environment), and eyeballing pixel coordinates from the image myself would be
far less precise than a real human click-and-zoom -- and this feeds the "up"
reference for every one of ~150 flights' angle numbers, so silently
substituting a low-confidence guess is exactly the kind of thing to flag
rather than plow through. Asking the user how to proceed (see next entry)
rather than picking silently, per claude_rules.md §11 ("missing context needed
to even start") and this task's own "IF you think something else should be
done... STOP... ask first" instruction.

**Decision (user, via question):** Use `solve_world_frame()` instead of the
manually-clicked vertical line. Will still run the REUSABLE guardrail checks
from `world_frame_precision_single.py` (baseline-perpendicular-to-up angle
check, weak-axis-must-be-width check, Umeyama corner-residual precision per
world axis) unmodified -- just swap the source of `up_vec` from a manual click
to `solve_world_frame()`'s checkerboard-row-geometry solve.

Derivation for `up_vec` in camera-frame coords from `solve_world_frame`'s
(R_wc, T_wc): `world_registration.py` defines world = solved.copy();
world[:,1] = -solved[:,1], where solved = (X_cam - T_wc) @ R_wc. A unit step in
world +y ("up") is a unit step of -1 in solved_y, which back-transforms via
R_wc's orthogonality to `up_vec_cam = -R_wc[:, 1]`. This exact formula is
already used (and validated) in `predict_sweep.py`'s own gravity-vs-world-up
cross-check (`world_up_in_cam = -R_wc[:, 1]`), so it's not a new derivation --
confirms via an existing, working piece of this codebase.

Next: read `src/stereo/triangulate.py` and
`src/calibration/extrinsic/solve_extrinsic.py` (both imported by
`world_frame_precision_single.py`, needed for the corner-residual precision
step) before writing the validation script.

- `src/stereo/triangulate.py`: `triangulate_points(pts0, pts1, K0, D0, K1, D1, R, T)`
  -- same fisheye-undistort + `cv2.triangulatePoints` logic as
  `label_vs_detection.triangulate`, just takes R,T directly instead of
  pre-built P0/P1. Used by `world_frame_precision_single.py`, so reused here
  too for the checkerboard-corner precision step, to match that script's
  logic exactly.
- `src/calibration/extrinsic/solve_extrinsic.py`: `PATTERN_SIZE=(7,11)`,
  `SQUARE_SIZE_MM=67.5`, `OBJP` (known 77-corner grid in board-frame mm),
  `detect_corners(gray)` (SB detector, falls back to classic+subpix),
  `load_intrinsics(path, label)`. All imported directly for the corner
  detection + known-grid comparison in the world-frame validation script.

## [built] src/registration/world_frame_validate_2026_07_21.py

New script (not modifying any existing file). For each of registration1
(img_0031/img_0032) and registration2 (img_0033/img_0034) independently:
1. `solve_world_frame(cam0_image, K0, D0)` -> R_wc, T_wc -> `up_vec = -R_wc[:,1]`
   (camera-frame vector for world "up"; derivation logged above, matches
   `predict_sweep.py`'s own formula).
2. Guardrail (a), reused from `world_frame_precision_single.py` STEP 2a:
   angle(baseline_dir, up_vec) ~= 90 deg, tol 10 deg (baseline_dir = normalized
   T from `calibration_outputs/2026_07_21/test2/stereo_extrinsic.npz`, same
   extrinsics for both registrations since extrinsics survive the session).
3. Build X_world/Y_world/Z_world orthonormally (same construction as that
   script's STEP 1c).
4. Triangulate the checkerboard's 77 corners (both cams,
   `triangulate_points`), Umeyama-fit to the known grid (`umeyama_alignment`,
   imported unmodified), project residuals onto world axes -> per-axis RMS.
5. Guardrail (b), reused from STEP 2b: largest-residual-spread axis must be
   Y_world (the rig's weak/depth axis) -- confirms the up_vec/baseline_dir
   construction is self-consistent.
6. Pick the candidate with PASS + lowest overall RMS as the registration's
   winner; if both candidates in a registration fail either guardrail, stop
   (exit 1) rather than silently choosing one.

Extra top-level gate before any candidate is checked: baseline |T| from
`test2/stereo_extrinsic.npz` must be within 10% of the nominal 850 mm (loose
gate -- catches a badly wrong extrinsics file, not a QA number), matching this
task's "Unexpected: STOP" condition for a wildly-off baseline.

Outputs to `data/2026_07_21_gym/flight_binning/world_frame_validation/`
(new folder, nothing existing touched): `world_frame_validation_report.txt`
(full stdout) and `registration{1,2}_world_transform.npz` (R_wc, T_wc, up_vec,
X_world, Y_world, Z_world, img_stem) for reuse by the batch script.

## [ran] World-frame validation results

```
Extrinsics: calibration_outputs/2026_07_21/test2/stereo_extrinsic.npz
  baseline |T| = 848.91 mm (expect ~850 mm)  -- 0.13% off nominal, fine.

registration1 / img_0031: PASS
  angle(baseline_dir, up_vec) = 89.56 deg (tol 10)
  board mean depth (cam0 Z) = 2603 mm
  overall 3D RMS residual = 2.36 mm  (X=0.23, Y=2.33 [weak], Z=0.25 mm)
  largest-spread axis = Y_world (correct)

registration1 / img_0032: PASS
  angle(baseline_dir, up_vec) = 89.57 deg
  board mean depth = 2602 mm
  overall 3D RMS residual = 2.38 mm  (X=0.23, Y=2.36 [weak], Z=0.25 mm)
  largest-spread axis = Y_world (correct)

  -> registration1 WINNER: img_0031 (marginally lower RMS, 2.36 vs 2.38 mm --
     both essentially identical/excellent, this is a photo-finish not a real
     quality gap)

registration2 / img_0033: PASS
  angle(baseline_dir, up_vec) = 89.51 deg
  board mean depth = 2790 mm
  overall 3D RMS residual = 1.73 mm  (X=0.26, Y=1.69 [weak], Z=0.28 mm)
  largest-spread axis = Y_world (correct)

registration2 / img_0034: PASS
  angle(baseline_dir, up_vec) = 89.51 deg
  board mean depth = 2790 mm
  overall 3D RMS residual = 1.73 mm  (X=0.26, Y=1.69 [weak], Z=0.27 mm)
  largest-spread axis = Y_world (correct)

  -> registration2 WINNER: img_0034 (tied with img_0033 to the mm; img_0034
     picked as the min() by a negligible sub-mm margin)
```

All 4 candidates PASS both guardrails -- no forced stop needed. Checkerboard
pose reprojection error (solve_world_frame's own internal QA, separate from
the guardrails above) was excellent across all 4: median 0.076-0.125 px, max
0.319-0.378 px.

Note for the report: board depth for registration was ~2.6-2.8 m (much closer
than the ~5 m ball-flight stand-off). This only affects R_wc's rotation
(up_vec derivation), not a translation/position measurement, and the
reprojection error at that depth is already sub-0.4 px, so this is not treated
as a concern -- flagging for transparency, not as a guardrail failure.

Saved: `world_frame_validation_report.txt`,
`registration1_world_transform.npz` (img_0031), `registration2_world_transform.npz`
(img_0034), all under `data/2026_07_21_gym/flight_binning/world_frame_validation/`.

## [CHECKPOINT 1] Reporting to user, waiting for go-ahead before any per-flight angle computation.

User said "continue" -- proceeding to Step 4 (batch script).

## [survey] ball_flights folder structure

`data/2026_07_21_gym/ball_flights/` has 149 flight_N folders (flight_1 ..
flight_149) plus one stray `detection_rate_summary.csv` at the top level (not
a flight, ignored). Per-flight layout: `cam0/`, `cam1/` (raw frames),
`timestamps.csv`, `analysis_3/flight_N_cam{0,1}_detections3.csv` (schema:
`frame_number,u,v` -- no `cam` column, since cam0/cam1 are already separate
files; different from `label_vs_detection.py`'s `frame_index,cam,u,v` label
schema).

**23 flights (flight_127 .. flight_149) have NO `analysis_3/` folder at all**
-- these will be skipped with reason "missing analysis_3/detections3 csv" for
both N rows, not silently dropped. 126 flights (flight_1..126) have detections
to work with. Registration boundary (<=60 -> registration1, >60 ->
registration2) falls entirely within this range: flights 1-60 (60 flights) use
registration1, flights 61-126 (66 flights) use registration2 (flights
127-149, all in the "no analysis_3" group, would have used registration2 too,
but are skipped regardless).

## [built] src/stereo/flight_velocity_angle_binner.py

New batch script. Per flight:
1. Load `flight_N_cam{0,1}_detections3.csv` into `{frame_number: (u,v)}` dicts.
2. Run `filter_trajectory_outliers()` (imported from `detector_core.py`,
   unmodified, default params) on each camera's dict INDEPENDENTLY (per task
   step 4 -- catches the arm/hand-selection bug before pairing, not after).
3. Pair by `frame_number` intersection of the two filtered sets (matches
   `label_vs_detection.py`/`predict_sweep.py`'s own `set(a) & set(b)` pattern
   -- naive/no sync correction, as decided).
4. Take the earliest `max(N_VALUES)=10` paired frames as `fit_frames`,
   triangulate via `triangulate()` (imported from `label_vs_detection.py`,
   unmodified), anchor t=0 at `fit_frames[0]` (matches `predict_sweep.py`'s
   `t0_frame` convention).
5. For each N in (5, 10): window = `fit_frames[:min(N, len(fit_frames))]`
   (adjusted down, logged, if the flight has fewer than N usable frames -- per
   task decision #4); skip that row if the adjusted window still has < 3
   points (`predict_sweep.py`'s own N>=3 minimum gate, value reused not
   imported since it's inline in that script, not a named constant).
6. Fit via `fit_constant_accel()` (imported from `predict_sweep.py`,
   unmodified) on the window -> (p0, v0, a). `|a|` plausibility gate: reused
   `ACCEL_HARD_LO/HI = 5.0/20.0 m/s^2` (imported directly from
   `label_vs_detection.py` -- these ARE named module constants, importable
   verbatim) -- outside this range, skip the row ("implausible |a|,
   triangulation/fit chain likely broken"); flag (don't skip) if outside the
   softer `ACCEL_NOMINAL_LO/HI = 9.8/11.0` band but inside the hard one.
7. Registration selection: flight_id <= 60 -> registration1, else
   registration2; load that registration's `Z_world` (=`up_vec`) from the
   Checkpoint-1 `_world_transform.npz` files.
8. `speed_m_s = |v0|/1000`, `elevation_deg = degrees(arcsin(dot(v0,Z_world)/|v0|))`.
9. Gravity cross-check (reused from `predict_sweep.py`'s own logic, not
   copied verbatim since it's entangled with that script's N-sweep/plotting --
   replicated the comparison itself): `fit_up = -a/|a|`,
   `diff_deg = degrees(arccos(dot(fit_up, Z_world)))`; flag if > 45 deg (same
   threshold value `predict_sweep.py` uses inline for its own
   fit-vs-world-up check).
10. Write ALL attempted (flight, N) rows to CSV (including skipped ones, with
    a `status`/`flag_reason` column) -- not just survivors, so the CSV is a
    complete audit trail of what was attempted and why anything didn't make
    it into the distribution.

Script appends live to THIS worklog file as it runs (`log_append()`, matching
claude_rules.md §10's own example pattern) -- logs every skip/flag
immediately, plus periodic progress every 20 flights, so nothing is batched to
the end.

Outputs: `data/2026_07_21_gym/flight_binning/flight_velocity_angle.csv` +
plots (new folder, already created at Checkpoint 1 for the world-frame
validation outputs; nothing existing under `data/2026_07_21_gym/` touched).

## [running] Batch script execution log (appended live by the script itself)

## [smoke test] 3-flight dry run before the full batch

Ran `process_flight()` directly on flight_1, flight_5, flight_65 to catch bugs
before the full 149-flight run (this itself appended live log lines above,
via the script's own `log_append()` -- working as designed). All three
code paths exercised: flight_1 and flight_5 both SKIPPED at both N (wildly
implausible |a| = 40-76 m/s^2 at low N); flight_65 produced OK rows at both N
with sensible-looking numbers (speed ~6.3-6.5 m/s, elev ~6-7 deg) and one
flagged row (crosscheck diff 45.2 deg, just over the 45 threshold). Confirmed
the full pipeline runs end-to-end without crashing before committing to the
full run.

## [ran] Full batch: all 149 flight folders

Ran in well under a minute (fast, as expected -- I/O-bound on a handful of
detections per flight, not a heavy sweep). Wrote
`data/2026_07_21_gym/flight_binning/flight_velocity_angle.csv` (298 rows =
149 flights x 2 N values) and 4 plots.

**Aggregate counts:** 136/298 rows "ok" (45.6%), 162/298 "skipped" (54.4%).
Of the 136 ok rows, 123 (90%) carry a flag_reason (not skipped, just
annotated). Skip reasons: 68 implausible-accel (hard gate [5,20] m/s^2), 48
too-few-paired-frames (< 3 after per-camera filtering), 46 missing
analysis_3/detections3 csv (= the 23 known-missing flights x 2 N).

This crossed the task's own stated "large fraction failing" red flag
("Unexpected: STOP... would suggest a bug in the batch script itself, not
noisy individual flights") on a first read, so I stopped to diagnose before
treating the batch as done, rather than presenting it as a clean result.

**Diagnosis 1 -- implausible-accel skips are an N-size effect, not a bug:**
split by N_requested: 55/68 implausible-accel skips are at N=5, only 13/68 at
N=10. This is exactly the noise-sensitivity pattern `predict_sweep.py`
already documents for its own N-sweep (low-N constant-accel fits can be wild,
e.g. its own example of |a|~440 m/s^2 at N=3) -- fewer points means a less
constrained quadratic fit. Not a script bug signature; it's the expected
shape of the problem, and is exactly why the task asked for 2 N values in the
first place (decision #4) -- this IS the sensitivity being surfaced.

**Diagnosis 2 -- "too few paired frames" flights have genuinely disjoint raw
frame_numbers between cameras, not an over-aggressive filter:** checked the 8
flights with exactly 0 paired frames (19, 22, 42, 47, 51, 117, 124, 126) --
`filter_trajectory_outliers()` removed NOTHING for any of them (filt0==raw0,
filt1==raw1 in every case checked); the raw detection counts themselves were
already sparse (2-11 detections across the whole flight per camera) and the
raw frame_number SETS have zero exact intersection even though their RANGES
overlap (e.g. flight_19: cam0 detected at frames [88,92,99,104,111,113,116,
119], cam1 at [72,90,93,106] -- overlapping range, no exact matches). This is
a real, structural limitation of the naive same-frame_number pairing this
task specified (decision: "naive index pairing is fine here... sync
correction not needed") when per-camera detection is this sparse -- not a
filter or script bug. Flagged as a real finding for the user, not silently
absorbed.

**Diagnosis 3 -- the dominant flag ("outside nominal accel band") is a tight
QA band flagging real-world noise/drag, not a red flag on its own:** 107/136
ok rows are outside the [9.8,11.0] m/s^2 NOMINAL band (vs. the [5,20] HARD
gate that actually skips) -- that nominal band is near-pure-gravity, and real
throws have drag + detector noise on top, so most real fits landing outside
a +/-0.6 m/s^2 window around exactly 9.8-11.0 is expected, not alarming. The
more diagnostically meaningful flag is the gravity-crosscheck disagreement
(>45 deg vs the validated world "up"): 30/136 ok rows (22%), which is a
real minority worth surfacing (could indicate the arm/hand
candidate-selection bug corrupting some early-frame fits, per the task's own
hypothesis) but not a majority-invalidating problem.

**Conclusion:** not treating this as the "bug in the batch script" STOP
condition -- the pattern is explained by (a) genuine low-N fit noise (exactly
what N=5 vs N=10 comparison was FOR), (b) a structural naive-pairing +
sparse-detection interaction (real, explicitly out-of-scope-to-fix this
task), and (c) an intentionally strict QA band that flags rather than
excludes. Proceeding to report all of this transparently at Checkpoint 2
rather than either silently hiding the rates or wrongly aborting a
correctly-functioning batch.

**Summary stats (ok rows):**
N=5:  n=47   speed 3.74-10.12 m/s (mean 6.43)   elevation -51.1 to +57.7 deg (mean 11.2)
N=10: n=89   speed 3.06-10.43 m/s (mean 6.69)   elevation -63.4 to +54.7 deg (mean 2.7)
registration1: 57 ok rows, registration2: 79 ok rows.

Plots: `distribution_N5.png`, `distribution_N10.png` (joint scatter + marginal
histograms, flagged points red triangles), `distribution_overlay_histograms.png`
(N=5 vs N=10 speed/angle histograms overlaid), `distribution_N_sensitivity.png`
(per-flight line from its N=5 point to its N=10 point, n=46 flights with both
surviving -- most moves are modest, a handful are large). All viewed and
confirmed rendering correctly.

## [CHECKPOINT 2] Reporting full distribution, skip/flag breakdown, and
N-sensitivity to user. No bin edges proposed or applied. Waiting for next
instruction.

## [redirect] User: rerun detector with the tuned config, binner used stale analysis_3

User pointed to `claude/claude_logs/2026-07-23_ball_detection_rate_tuning_worklog.md`
(a DIFFERENT, earlier session's log -- detector tuning, not this task) --
confirms `analysis_3` (what the binner just ran against) is the OLD/untuned
default config (thresh=20, open_k=7, min_area=200, no exclusion mask v4,
avg_combined_rate 0.151-0.277 on this session's data), not the tuned config
(`data/detector_tuning/candidate_config.json`: stride=1, thresh=16, open_k=3,
close_k=30, min_area=30, max_area=50000, min_circ=0.3 + exclusion_mask.py v4
[12 zones] + trajectory filter max_speed=80/min_run=2, validated
avg_combined_rate=0.9667 full-dataset). The full-dataset production run
(`10_run_full_dataset.py`, prior session) already validated this config
dataset-wide but only wrote AGGREGATE stats + contact-sheet PNGs -- never the
raw per-frame (frame_number,u,v) CSVs the binner needs as input. User asked
where the new CSVs should live: per-flight `analysis_4` subfolders, or a
centralized folder.

**Answered with a recommendation, not a fresh open question**: the prior
session already decided this exact question for this exact config (see that
worklog's "Full-dataset production run" section) -- scattering 149
`analysis_4` folders across `2026_07_21_gym` was explicitly rejected in favor
of centralizing under `data/detector_tuning/`, which is where this config's
contact sheets and validated-results CSV already live. Recommended mirroring
that: `data/detector_tuning/detections/03_stride1_thresh16_openk3_area30_circ0.3/`
-- same STAGE folder name as the existing contact_sheets stage folder, so
sibling artifacts for this config stay discoverable together. Proceeding with
this (strong precedent, user can redirect).

## [built] src/image_processing/02_adjacent_frame_differencing/11_generate_detections_csv.py

New script (next number in that pipeline stage's convention). Scoped to
`2026_07_21_gym` only (that's all the binner consumes -- not re-running
`2026_07_15_gym` since nothing downstream needs it right now). Reuses
`detector_core.run_detection()` (RAW output, no `filter_trajectory_outliers()`
at this stage -- matches `analysis_3`'s own raw convention, since the binner
already applies that filter itself as an independent step) with
`candidate_config.json` loaded the same way `07`/`08`/`09`/`10` do (duplicated
`load_config()`, not centralized -- matches established convention).
Exclusion mask v4 is applied automatically inside `run_detection()` ->
`compute_mask()` -> `apply_exclusion()`, no extra wiring needed. Parallelized
per (flight,cam) via `ProcessPoolExecutor`, same pattern as
`10_run_full_dataset.py`. Output: `flight_N_camX_detections.csv`
(frame_number,u,v schema, matching `analysis_3`) in
`data/detector_tuning/detections/03_stride1_thresh16_openk3_area30_circ0.3/`.

## [ran] Detection CSV generation -- 252/252 written

126 flights x 2 cams found (same 126 as had `analysis_3` before -- flights
127-149 still have no raw `ball_in_frame` frame data at all, not just missing
analysis, so they'll still be skipped by the binner; not a regression). All
252 CSVs written successfully, no errors.

## [next] Repointing flight_velocity_angle_binner.py at the new detections and re-running

## [rerun] flight_velocity_angle_binner.py against the tuned-detector CSVs -- unexpected regression

Repointed the binner (`DETECTIONS_DIR`, `process_flight`'s `cam0_csv`/`cam1_csv`,
skip-reason text) at the new
`data/detector_tuning/detections/03_stride1_thresh16_openk3_area30_circ0.3/`
CSVs -- purely a path change, no logic change. Re-ran across all 149 flights.

**Result was WORSE, not better, on the metric that matters for this task**:
55/298 ok rows (18.4%, down from 136/298=45.6% before), 197/298 implausible-
accel skips (66%, up from 68/298=23%). "Too few paired frames" skips dropped
to ZERO (expected/good -- the tuned detector's much higher combined_rate
means no more flights with disjoint raw frame numbers between cams). But the
implausible-accel gate is now failing MUCH more often, which is the opposite
of what improving the underlying detector should do -- stopped to diagnose
before treating this as the new final answer, rather than just handing over a
visibly-worse distribution.

**Diagnosis**: compared raw detections old vs new for sample flights (65, 1,
5) -- the new detector's early-flight detections are NOT corrupted by
arm/hand artifacts (my first hypothesis, given the tuning worklog's own
documented concern about exactly this) -- they're dense, smooth,
frame-by-frame real ball trajectories, clearly BETTER raw data. The actual
cause is different: computed the real-time SPAN covered by "first 10 paired
frames" (`fit_frames_all[:10]`) across 30 flights under the new detector --
**every single one spans almost exactly 149.9 ms** (9 frame-gaps at the
~16.65 ms frame period), because the new detector's ~97% combined_rate means
paired frames are now nearly consecutive integers. Under the OLD sparse
detector, the same "first 10 paired frames" spanned a much more variable and
often longer real time (166-350 ms in the small sample checked), because
detection gaps meant 10 kept detections were spread across more actual
frames/time.

A ~150 ms window is too short to reliably resolve the ~9.8 m/s^2 gravity
curvature against detector/triangulation noise for a constant-acceleration
fit (the quadratic term's contribution to position over 150 ms is only
~110 mm, comparable to real detection/triangulation noise) -- so the fitted
`|a|` becomes very noisy and frequently blows the [5,20] m/s^2 plausibility
gate. This is NOT a detector-quality regression; it's the frame-COUNT
windowing (`N=5`/`N=10` as raw point counts, decision #4 in the original
task) silently changing MEANING now that detector density is ~3x higher --
the same N now covers much less real time than it did against the old,
sparser detector it was implicitly tuned against.

**Verified the mechanism directly**: swept N (frame count) from 10 to 45
across the same 30-flight sample with the new detector: N=10 -> 9 ok/21
implausible; **N=20 -> 29 ok/0 implausible**; N=30 -> 28 ok/0 implausible;
N=45 -> 17 ok/0 implausible (fewer flights have 45 usable frames at all, but
zero implausible among those that do). Confirms the mechanism cleanly and
gives a clear, evidenced path forward -- but changing N from (5,10) to
something like (20,30) is a real methodology change to the original task's
decision #4, not a bug fix I should just silently apply and re-run again.
Stopping to report this finding and ask how to proceed, rather than picking
new N values unilaterally.

**User decision**: switch N_VALUES to (20, 30) -- the empirically-verified
values from the diagnostic above.

## [changed] N_VALUES: (5,10) -> (20,30)

Updated `flight_velocity_angle_binner.py`: `N_VALUES = [20, 30]` with a
comment explaining why (references the diagnostic above). Also generalized
`make_overlay_histograms()` and `make_sensitivity_plot()`, which had N=5/N=10
hardcoded into their color-mapping and pairing logic -- now derive
labels/colors from `N_VALUES` directly so the script isn't silently wrong if
N_VALUES changes again later.

## [rerun] Final run at N=20/N=30 against the tuned-detector CSVs

**251/298 ok rows (84.2%, up from 55/298=18.4% at N=5/10)**, only 47 skipped:
46 missing-detections-csv (the same unavoidable flights 127-149), and just
**1** implausible-accel skip (down from 197) -- confirms the diagnosis was
correct and complete. 168/251 (67%) still carry a flag, but now dominated
(150/168) by the tight nominal-accel band (expected, same reasoning as the
first run -- real drag+noise vs a near-pure-gravity band); the gravity
crosscheck flag dropped to only 10/251 (4%, down from 22% at N=5/10) --
consistent with longer, better-constrained windows producing fit-derived "up"
vectors that agree much better with the validated world "up".

**Distribution (N=20):** n=125, speed 6.01-10.45 m/s (mean 7.71), elevation
-17.5 to +65.0 deg (mean 33.7). **N=30:** n=126, speed 6.03-10.46 m/s (mean
7.69), elevation -17.5 to +68.2 deg (mean 33.4). Registration split: 119 ok
rows registration1, 132 registration2.

**Shape is now visibly bimodal and physically sensible** (viewed
`distribution_N20.png`): a lower cluster around -10 to +20 deg elevation
(flatter/driven throws) and a dense, distinct cluster around 45-65 deg
(high-arcing throws) -- consistent with a mixed pepper-drill throw set
(receives/sets vs hits, context.md SS6). `distribution_N_sensitivity.png`
shows N=20->N=30 connector lines are mostly SHORT (stable) across both
clusters, confirming N=20/30 is a much better-conditioned choice than N=5/10
was.

## [CHECKPOINT 2, re-reported] Full distribution at the corrected config +
N values reported to user. No bin edges proposed or applied.

## [user follow-up] Explain skips/flags + add 2026_07_15_gym

User asked 3 things, answered directly (no code needed):
1. Why 47 skipped -- confirmed by checking: flights 127-149 in
   `2026_07_21_gym` have EMPTY `ball_in_frame` folders (never curated),
   matches user's own guess.
2. What "flag" means -- explained the 3 independent thresholds: nominal-accel
   band [9.8,11.0] (soft, just annotates -- dominant flag, expected given real
   drag+noise), gravity-crosscheck >45 deg (soft, more diagnostic, now only
   4% of ok rows), and the ACTUAL skip gate |a| outside [5,20] (hard,
   distinguished from the other two which never skip).
3. flight_112's |a|=17.24 -- inside the hard gate, just outside the tight
   nominal band; physically plausible for gravity+drag on a fast/flat throw,
   not a bug.

Then asked to also bin `2026_07_15_gym` flights, "for those with the
ball_in_frame separated" -- read as "flights that already have ball_in_frame
curation done" (reinforcing point 1 above), not a request for a new
session-separation feature -- but adding a `session` column to the output CSV
anyway as a low-cost, clearly-useful addition (context.md treats library vs
gym data differently; worth keeping visible).

**Investigated 2026_07_15_gym's available data before building anything:**
- `calibration_outputs/2026_07_15/stereo_extrinsic.npz` exists (own
  extrinsics for this session) -- baseline |T|=851.60 mm (0.19% off nominal
  850, healthy). No separate intrinsics file for this session (confirms
  intrinsics are shared/camera-hardware-level, not per-session, as expected).
- World-registration candidates:
  `data/2026_07_15_gym/world_registration&rebounder_registration/{cam0,cam1}/
  img_{0026,0028,0029,0030}.png` -- FOUR candidates, but only ONE registration
  for the whole session (no mid-session world-frame change like
  2026_07_21_gym's registration1/2 split -- nothing in context.md or the data
  suggests one). Pre-existing corner-debug images only for img_0029/img_0030
  (not 0026/0028) -- inconclusive evidence of an earlier partial
  investigation; validating all 4 anyway rather than trusting an ambiguous
  partial artifact.
- Confirmed `validation/cam0/img_0026.png` and `world_registration&rebounder_
  registration/cam0/img_0026.png` are DIFFERENT files despite the same
  number (different captures) -- kept these folders separate, didn't
  conflate them.
- 37 flights in `2026_07_15_gym/ball_flights` have populated `ball_in_frame`
  (some nested under subfolders like "2 ball contacts ground before plane/
  flight_01", "1 not full flight/flight_16" -- same nesting pattern
  `10_run_full_dataset.py` already handled for this exact session).

## [built] src/registration/world_frame_validate_2026_07_15.py

Same method/guardrails as `world_frame_validate_2026_07_21.py` (imports the
same reused functions, not duplicated logic beyond path/structure
differences), adapted for ONE registration group (not two) with 4 candidates.
Output: `data/2026_07_15_gym/flight_binning/world_frame_validation/
world_frame_validation_report.txt` + `registration_world_transform.npz`.

## [ran] 2026_07_15_gym world-frame validation

`img_0026`/`img_0028`: checkerboard NOT detected in either cam -- explains
why only img_0029/img_0030 had pre-existing corner-debug images (someone
already found the same thing earlier, consistent evidence not a coincidence).
`img_0029`: PASS but noticeably worse (overall RMS 5.18 mm, board depth 5560
mm, baseline_up_angle 87.42 deg -- still within the 10 deg guardrail
tolerance but the largest deviation from 90 seen so far). `img_0030`: PASS,
clean (overall RMS 1.32 mm, board depth 2677 mm, baseline_up_angle 89.75
deg). **WINNER: img_0030** -- clear margin, not a photo-finish like
2026_07_21_gym's registration1 was.

## [next] Generating tuned-detector detection CSVs for 2026_07_15_gym (37 flights)

## [ran] 2026_07_15_gym detection CSVs

Generalized `11_generate_detections_csv.py` to take `--session` (was
2026_07_21_gym-only), session-subfoldered output (`.../<STAGE>/<session>/`),
and a same-session basename-collision guard (raises instead of silently
overwriting) instead of assuming no collision. Reorganized the EXISTING
2026_07_21_gym CSVs (mine from this session, safe to move) into
`.../<STAGE>/2026_07_21_gym/` for symmetry -- verified count unchanged (252)
after the move. Ran for `2026_07_15_gym`: 37 flights x 2 cams, 74/74 CSVs
written, no errors.

## [user mid-turn] Output location correction

User flagged (correctly) that `data/2026_07_21_gym/flight_binning/` is the
wrong place for output that now spans both sessions. Moved the
CROSS-SESSION artifacts (flight_velocity_angle.csv + distribution plots) to
a new top-level `data/flight_binning/` (sibling to both session folders and
`data/detector_tuning/`) -- matches claude_rules.md SS7's "own clearly-named
folder" convention for artifacts that don't belong to one session. Deleted
the stale N5/N10 plots left over from the pre-N-fix run while moving (mine,
superseded, not needed). World-frame validation OUTPUTS correctly stay
per-session where they already were
(`data/<session>/flight_binning/world_frame_validation/`) -- registration
genuinely is a per-session concept, unlike the binning result itself.

## [refactored] flight_velocity_angle_binner.py -- multi-session

Rewrote for both sessions. Key changes:
- `SESSIONS` dict: per-session extrinsics path, detections dir, world-frame
  dir, and registration name(s) (2026_07_21_gym has two --
  registration1/registration2, boundary by flight number <=60; 2026_07_15_gym
  has one -- "registration", no boundary logic needed).
- Flight list now comes from WHICHEVER detection CSVs actually exist in each
  session's `detections_dir` (intersection of cam0/cam1 stems), not from
  re-walking the raw ball_flights tree -- since a flight only gets a CSV if
  `11_generate_detections_csv.py`'s `find_flight_dirs` found populated
  `ball_in_frame` data for it. This means flights lacking curation (like
  2026_07_21_gym's 127-149) are no longer written as explicit per-row
  "skipped, missing csv" CSV entries -- they're simply not enumerated at all,
  logged once as a per-session flight count instead. Simpler and avoids
  re-deriving 2026_07_15_gym's nested-folder enumeration a second time (it's
  already correctly resolved once, in the detections folder's filenames).
- Added a `session` column to the output CSV (every row) -- addresses "keep
  them distinguishable" per the earlier reasoning (context.md treats
  library/gym data differently), without needing separate binning runs.
- New plot: `distribution_by_session.png` (speed vs angle, colored by
  session, at the larger N) -- lets the user see whether library vs gym
  throws occupy different regions before combining them for bin-edge
  decisions.
- Calibration (K0/D0/K1/D1) loaded per-session (comes out identical --
  intrinsics are shared hardware-level, not per-session -- but R/T differ,
  so `load_calib` must be called with each session's own extrinsics path).

## [ran] Multi-session batch -- final result

**324/326 ok rows (99.4%), only 2 skipped** (1 per session, both "too few
paired frames" on one specific flight each). Session breakdown (ok rows):
`2026_07_21_gym` 251, `2026_07_15_gym` 73. Per-session distribution at N=20:
2026_07_21_gym n=125, speed [6.01,10.45] mean 7.71, elevation [-17.5,65.0]
mean 33.7; 2026_07_15_gym n=37, speed [5.79,10.78] mean 7.68, elevation
[-29.1,65.7] mean 38.5 -- broadly similar ranges/means between sessions, not
wildly different populations.

Viewed `distribution_by_session.png`: the two sessions interleave within the
same two-cluster shape (flat throws ~-20 to +20 deg, high-arc cluster ~45-65
deg) rather than occupying separate regions -- library (2026_07_15, purple)
has fewer points and slightly extends the low-angle/high-speed corner, but
doesn't look like a qualitatively different population. Reasonable to combine
for bin-edge purposes, though the `session` column is there if anyone wants
to check per-session coverage before finalizing bins.

## [CHECKPOINT 2, final] Multi-session distribution reported. No bin edges
proposed or applied.

Editing MY OWN script from earlier this session (not a pre-existing file
needing permission) to read from
`data/detector_tuning/detections/03_stride1_thresh16_openk3_area30_circ0.3/
{flight_id}_camX_detections.csv` instead of
`analysis_3/{flight_id}_camX_detections3.csv`. Old CSV/plot outputs under
`data/2026_07_21_gym/flight_binning/` will be overwritten by design (this
task's own re-run, not someone else's data) -- new run supersedes the
analysis_3-based one now that we know analysis_3 was stale.
- [15:53:21] flight_1 N=5: SKIPPED -- implausible |a|=67.95 m/s^2 (hard gate [5.0,20.0])
- [15:53:21] flight_1 N=10: SKIPPED -- implausible |a|=75.62 m/s^2 (hard gate [5.0,20.0]) (adjusted from 10 -> 6, flight has fewer usable frames)
- [15:53:21] flight_65 N=5: FLAGGED -- |a|=14.95 outside nominal band [9.8,11.0]; gravity crosscheck diff=45.2 deg > 45.0 (speed=6.54 m/s, elev=6.8 deg)
- [15:53:21] flight_65 N=10: FLAGGED -- |a|=11.97 outside nominal band [9.8,11.0]; adjusted from 10 -> 9, flight has fewer usable frames (speed=6.34 m/s, elev=6.2 deg)
- [15:53:21] flight_5 N=5: SKIPPED -- implausible |a|=53.96 m/s^2 (hard gate [5.0,20.0])
- [15:53:21] flight_5 N=10: SKIPPED -- implausible |a|=39.41 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] === flight_velocity_angle_binner.py: batch run starting ===
- [15:53:46] loaded world transforms: registration1 up_vec from img_0031, registration2 up_vec from img_0034
- [15:53:46] found 149 flight folders under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights
- [15:53:46] flight_1 N=5: SKIPPED -- implausible |a|=67.95 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_1 N=10: SKIPPED -- implausible |a|=75.62 m/s^2 (hard gate [5.0,20.0]) (adjusted from 10 -> 6, flight has fewer usable frames)
- [15:53:46] flight_2 N=5: SKIPPED -- implausible |a|=20.27 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_2 N=10: FLAGGED -- |a|=12.23 outside nominal band [9.8,11.0]; gravity crosscheck diff=54.6 deg > 45.0 (speed=8.70 m/s, elev=-7.2 deg)
- [15:53:46] flight_3 N=5: SKIPPED -- implausible |a|=47.95 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_3 N=10: FLAGGED -- |a|=9.56 outside nominal band [9.8,11.0] (speed=9.50 m/s, elev=0.8 deg)
- [15:53:46] flight_4: SKIPPED (both N) -- only 2 paired frames after filtering (raw cam0=7, cam1=4, filtered cam0=7, cam1=4)
- [15:53:46] flight_5 N=5: SKIPPED -- implausible |a|=53.96 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_5 N=10: SKIPPED -- implausible |a|=39.41 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_6 N=5: FLAGGED -- |a|=13.73 outside nominal band [9.8,11.0]; gravity crosscheck diff=45.8 deg > 45.0 (speed=7.94 m/s, elev=1.8 deg)
- [15:53:46] flight_6 N=10: FLAGGED -- |a|=12.57 outside nominal band [9.8,11.0] (speed=7.96 m/s, elev=3.2 deg)
- [15:53:46] flight_7 N=5: SKIPPED -- implausible |a|=23.51 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_7 N=10: FLAGGED -- |a|=9.41 outside nominal band [9.8,11.0] (speed=8.05 m/s, elev=-11.9 deg)
- [15:53:46] flight_8 N=5: SKIPPED -- implausible |a|=28.24 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_8 N=10: FLAGGED -- |a|=12.20 outside nominal band [9.8,11.0] (speed=7.50 m/s, elev=-7.3 deg)
- [15:53:46] flight_9 N=5: SKIPPED -- implausible |a|=97.87 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_10 N=5: SKIPPED -- implausible |a|=48.25 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_10 N=10: FLAGGED -- |a|=8.34 outside nominal band [9.8,11.0]; gravity crosscheck diff=46.6 deg > 45.0 (speed=8.77 m/s, elev=-9.3 deg)
- [15:53:46] flight_11 N=5: SKIPPED -- implausible |a|=22.49 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_11 N=10: FLAGGED -- |a|=9.74 outside nominal band [9.8,11.0] (speed=6.04 m/s, elev=-12.8 deg)
- [15:53:46] flight_12 N=5: SKIPPED -- implausible |a|=55.73 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_12 N=10: FLAGGED -- |a|=11.12 outside nominal band [9.8,11.0] (speed=8.35 m/s, elev=-6.4 deg)
- [15:53:46] flight_13 N=5: SKIPPED -- implausible |a|=123.54 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_13 N=10: FLAGGED -- |a|=17.49 outside nominal band [9.8,11.0] (speed=8.08 m/s, elev=0.2 deg)
- [15:53:46] flight_14 N=5: SKIPPED -- implausible |a|=20.28 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_14 N=10: FLAGGED -- |a|=18.55 outside nominal band [9.8,11.0] (speed=7.68 m/s, elev=4.7 deg)
- [15:53:46] flight_15 N=5: FLAGGED -- |a|=14.91 outside nominal band [9.8,11.0] (speed=8.14 m/s, elev=11.0 deg)
- [15:53:46] flight_15 N=10: FLAGGED -- adjusted from 10 -> 9, flight has fewer usable frames (speed=7.93 m/s, elev=8.3 deg)
- [15:53:46] flight_16 N=5: SKIPPED -- implausible |a|=36.93 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_16 N=10: FLAGGED -- |a|=13.21 outside nominal band [9.8,11.0] (speed=8.28 m/s, elev=-5.1 deg)
- [15:53:46] flight_17 N=5: FLAGGED -- |a|=15.00 outside nominal band [9.8,11.0]; gravity crosscheck diff=62.4 deg > 45.0 (speed=10.12 m/s, elev=-23.1 deg)
- [15:53:46] flight_17 N=10: SKIPPED -- implausible |a|=38.89 m/s^2 (hard gate [5.0,20.0]) (adjusted from 10 -> 7, flight has fewer usable frames)
- [15:53:46] flight_18: SKIPPED (both N) -- only 2 paired frames after filtering (raw cam0=5, cam1=5, filtered cam0=5, cam1=5)
- [15:53:46] flight_19: SKIPPED (both N) -- only 0 paired frames after filtering (raw cam0=8, cam1=4, filtered cam0=8, cam1=4)
- [15:53:46] flight_20 N=5: SKIPPED -- implausible |a|=47.91 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_20 N=10: FLAGGED -- |a|=9.20 outside nominal band [9.8,11.0]; adjusted from 10 -> 8, flight has fewer usable frames (speed=7.21 m/s, elev=-0.7 deg)
- [15:53:46] progress: 20/149 flights processed
- [15:53:46] flight_21 N=10: FLAGGED -- adjusted from 10 -> 8, flight has fewer usable frames (speed=7.06 m/s, elev=49.5 deg)
- [15:53:46] flight_22: SKIPPED (both N) -- only 0 paired frames after filtering (raw cam0=7, cam1=5, filtered cam0=7, cam1=5)
- [15:53:46] flight_23 N=5: FLAGGED -- |a|=11.69 outside nominal band [9.8,11.0] (speed=6.97 m/s, elev=46.3 deg)
- [15:53:46] flight_23 N=10: FLAGGED -- adjusted from 10 -> 9, flight has fewer usable frames (speed=6.81 m/s, elev=43.8 deg)
- [15:53:46] flight_24 N=5: FLAGGED -- |a|=9.19 outside nominal band [9.8,11.0]; adjusted from 5 -> 3, flight has fewer usable frames (speed=4.57 m/s, elev=27.4 deg)
- [15:53:46] flight_24 N=10: FLAGGED -- |a|=9.19 outside nominal band [9.8,11.0]; adjusted from 10 -> 3, flight has fewer usable frames (speed=4.57 m/s, elev=27.4 deg)
- [15:53:46] flight_25 N=5: FLAGGED -- |a|=13.93 outside nominal band [9.8,11.0] (speed=7.94 m/s, elev=48.0 deg)
- [15:53:46] flight_25 N=10: FLAGGED -- adjusted from 10 -> 9, flight has fewer usable frames (speed=7.54 m/s, elev=42.1 deg)
- [15:53:46] flight_26 N=5: FLAGGED -- |a|=12.03 outside nominal band [9.8,11.0]; adjusted from 5 -> 3, flight has fewer usable frames (speed=6.80 m/s, elev=32.9 deg)
- [15:53:46] flight_26 N=10: FLAGGED -- |a|=12.03 outside nominal band [9.8,11.0]; adjusted from 10 -> 3, flight has fewer usable frames (speed=6.80 m/s, elev=32.9 deg)
- [15:53:46] flight_27 N=5: FLAGGED -- |a|=5.85 outside nominal band [9.8,11.0]; gravity crosscheck diff=162.6 deg > 45.0 (speed=5.15 m/s, elev=-40.7 deg)
- [15:53:46] flight_27 N=10: FLAGGED -- adjusted from 10 -> 8, flight has fewer usable frames (speed=4.63 m/s, elev=-36.4 deg)
- [15:53:46] flight_28 N=5: FLAGGED -- |a|=8.59 outside nominal band [9.8,11.0] (speed=4.81 m/s, elev=20.9 deg)
- [15:53:46] flight_28 N=10: FLAGGED -- |a|=8.70 outside nominal band [9.8,11.0] (speed=4.58 m/s, elev=24.9 deg)
- [15:53:46] flight_29 N=5: SKIPPED -- implausible |a|=57.03 m/s^2 (hard gate [5.0,20.0]) (adjusted from 5 -> 3, flight has fewer usable frames)
- [15:53:46] flight_29 N=10: SKIPPED -- implausible |a|=57.03 m/s^2 (hard gate [5.0,20.0]) (adjusted from 10 -> 3, flight has fewer usable frames)
- [15:53:46] flight_30: SKIPPED (both N) -- only 2 paired frames after filtering (raw cam0=12, cam1=9, filtered cam0=12, cam1=9)
- [15:53:46] flight_31 N=5: SKIPPED -- implausible |a|=89.06 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_31 N=10: FLAGGED -- |a|=8.66 outside nominal band [9.8,11.0] (speed=3.73 m/s, elev=4.3 deg)
- [15:53:46] flight_32: SKIPPED (both N) -- only 1 paired frames after filtering (raw cam0=10, cam1=9, filtered cam0=10, cam1=9)
- [15:53:46] flight_33 N=5: FLAGGED -- |a|=9.09 outside nominal band [9.8,11.0] (speed=3.74 m/s, elev=12.5 deg)
- [15:53:46] flight_33 N=10: FLAGGED -- |a|=11.68 outside nominal band [9.8,11.0]; gravity crosscheck diff=62.3 deg > 45.0 (speed=4.49 m/s, elev=2.5 deg)
- [15:53:46] flight_34 N=5: SKIPPED -- implausible |a|=49.84 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_34 N=10: FLAGGED -- |a|=9.56 outside nominal band [9.8,11.0] (speed=3.55 m/s, elev=-20.2 deg)
- [15:53:46] flight_35 N=5: FLAGGED -- |a|=9.70 outside nominal band [9.8,11.0] (speed=7.28 m/s, elev=46.9 deg)
- [15:53:46] flight_35 N=10: FLAGGED -- |a|=9.70 outside nominal band [9.8,11.0]; adjusted from 10 -> 6, flight has fewer usable frames (speed=7.28 m/s, elev=47.0 deg)
- [15:53:46] flight_36 N=10: FLAGGED -- adjusted from 10 -> 5, flight has fewer usable frames (speed=4.01 m/s, elev=-7.7 deg)
- [15:53:46] flight_37 N=5: SKIPPED -- implausible |a|=68.04 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_37 N=10: FLAGGED -- |a|=8.82 outside nominal band [9.8,11.0] (speed=3.06 m/s, elev=-1.8 deg)
- [15:53:46] flight_38 N=5: SKIPPED -- implausible |a|=22.48 m/s^2 (hard gate [5.0,20.0])
- [15:53:46] flight_38 N=10: FLAGGED -- |a|=16.96 outside nominal band [9.8,11.0] (speed=5.63 m/s, elev=-63.4 deg)
- [15:53:46] flight_39 N=5: FLAGGED -- |a|=14.69 outside nominal band [9.8,11.0]; gravity crosscheck diff=82.8 deg > 45.0 (speed=5.02 m/s, elev=5.6 deg)
- [15:53:46] flight_39 N=10: FLAGGED -- |a|=14.69 outside nominal band [9.8,11.0]; gravity crosscheck diff=82.8 deg > 45.0; adjusted from 10 -> 5, flight has fewer usable frames (speed=5.02 m/s, elev=5.6 deg)
- [15:53:46] flight_40: SKIPPED (both N) -- only 1 paired frames after filtering (raw cam0=12, cam1=7, filtered cam0=12, cam1=7)
- [15:53:46] progress: 40/149 flights processed
- [15:53:46] flight_41 N=5: FLAGGED -- gravity crosscheck diff=105.1 deg > 45.0 (speed=6.22 m/s, elev=-36.3 deg)
- [15:53:46] flight_41 N=10: FLAGGED -- |a|=9.26 outside nominal band [9.8,11.0] (speed=3.75 m/s, elev=-25.6 deg)
- [15:53:46] flight_42: SKIPPED (both N) -- only 0 paired frames after filtering (raw cam0=11, cam1=10, filtered cam0=11, cam1=10)
- [15:53:46] flight_43 N=5: FLAGGED -- |a|=9.44 outside nominal band [9.8,11.0]; adjusted from 5 -> 3, flight has fewer usable frames (speed=4.11 m/s, elev=-16.7 deg)
- [15:53:46] flight_43 N=10: FLAGGED -- |a|=9.44 outside nominal band [9.8,11.0]; adjusted from 10 -> 3, flight has fewer usable frames (speed=4.11 m/s, elev=-16.7 deg)
- [15:53:47] flight_44: SKIPPED (both N) -- only 1 paired frames after filtering (raw cam0=5, cam1=2, filtered cam0=5, cam1=2)
- [15:53:47] flight_45 N=10: FLAGGED -- adjusted from 10 -> 5, flight has fewer usable frames (speed=4.45 m/s, elev=-0.9 deg)
- [15:53:47] flight_46 N=5: SKIPPED -- implausible |a|=28.57 m/s^2 (hard gate [5.0,20.0]) (adjusted from 5 -> 3, flight has fewer usable frames)
- [15:53:47] flight_46 N=10: SKIPPED -- implausible |a|=28.57 m/s^2 (hard gate [5.0,20.0]) (adjusted from 10 -> 3, flight has fewer usable frames)
- [15:53:47] flight_47: SKIPPED (both N) -- only 0 paired frames after filtering (raw cam0=10, cam1=2, filtered cam0=10, cam1=2)
- [15:53:47] flight_48: SKIPPED (both N) -- only 2 paired frames after filtering (raw cam0=5, cam1=6, filtered cam0=5, cam1=6)
- [15:53:47] flight_49: SKIPPED (both N) -- only 2 paired frames after filtering (raw cam0=11, cam1=8, filtered cam0=11, cam1=8)
- [15:53:47] flight_50: SKIPPED (both N) -- only 2 paired frames after filtering (raw cam0=15, cam1=7, filtered cam0=15, cam1=7)
- [15:53:47] flight_51: SKIPPED (both N) -- only 0 paired frames after filtering (raw cam0=0, cam1=4, filtered cam0=0, cam1=4)
- [15:53:47] flight_52 N=5: SKIPPED -- implausible |a|=31.47 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_52 N=10: SKIPPED -- implausible |a|=26.33 m/s^2 (hard gate [5.0,20.0]) (adjusted from 10 -> 8, flight has fewer usable frames)
- [15:53:47] flight_53 N=5: SKIPPED -- implausible |a|=77.42 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_53 N=10: FLAGGED -- |a|=8.08 outside nominal band [9.8,11.0]; adjusted from 10 -> 9, flight has fewer usable frames (speed=3.79 m/s, elev=16.0 deg)
- [15:53:47] flight_54 N=5: FLAGGED -- |a|=12.43 outside nominal band [9.8,11.0] (speed=6.16 m/s, elev=28.1 deg)
- [15:53:47] flight_54 N=10: FLAGGED -- |a|=11.94 outside nominal band [9.8,11.0]; adjusted from 10 -> 6, flight has fewer usable frames (speed=6.20 m/s, elev=27.5 deg)
- [15:53:47] flight_55: SKIPPED (both N) -- only 1 paired frames after filtering (raw cam0=8, cam1=7, filtered cam0=8, cam1=7)
- [15:53:47] flight_56 N=5: SKIPPED -- implausible |a|=23.54 m/s^2 (hard gate [5.0,20.0]) (adjusted from 5 -> 4, flight has fewer usable frames)
- [15:53:47] flight_56 N=10: SKIPPED -- implausible |a|=23.54 m/s^2 (hard gate [5.0,20.0]) (adjusted from 10 -> 4, flight has fewer usable frames)
- [15:53:47] flight_57 N=5: FLAGGED -- |a|=13.85 outside nominal band [9.8,11.0]; adjusted from 5 -> 4, flight has fewer usable frames (speed=4.90 m/s, elev=21.1 deg)
- [15:53:47] flight_57 N=10: FLAGGED -- |a|=13.85 outside nominal band [9.8,11.0]; adjusted from 10 -> 4, flight has fewer usable frames (speed=4.90 m/s, elev=21.1 deg)
- [15:53:47] flight_58 N=5: FLAGGED -- |a|=7.17 outside nominal band [9.8,11.0] (speed=5.35 m/s, elev=-51.1 deg)
- [15:53:47] flight_58 N=10: FLAGGED -- |a|=7.86 outside nominal band [9.8,11.0]; adjusted from 10 -> 6, flight has fewer usable frames (speed=5.37 m/s, elev=-49.8 deg)
- [15:53:47] flight_59: SKIPPED (both N) -- only 2 paired frames after filtering (raw cam0=9, cam1=2, filtered cam0=9, cam1=2)
- [15:53:47] flight_60 N=5: SKIPPED -- implausible |a|=38.88 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_60 N=10: FLAGGED -- |a|=8.36 outside nominal band [9.8,11.0] (speed=4.99 m/s, elev=-57.0 deg)
- [15:53:47] progress: 60/149 flights processed
- [15:53:47] flight_61 N=5: SKIPPED -- implausible |a|=84.26 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_61 N=10: FLAGGED -- |a|=8.72 outside nominal band [9.8,11.0] (speed=7.28 m/s, elev=-9.1 deg)
- [15:53:47] flight_62 N=5: SKIPPED -- implausible |a|=52.45 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_62 N=10: FLAGGED -- |a|=9.32 outside nominal band [9.8,11.0] (speed=8.86 m/s, elev=-3.1 deg)
- [15:53:47] flight_63 N=5: SKIPPED -- implausible |a|=40.16 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_63 N=10: FLAGGED -- |a|=13.66 outside nominal band [9.8,11.0]; gravity crosscheck diff=70.9 deg > 45.0; adjusted from 10 -> 9, flight has fewer usable frames (speed=9.02 m/s, elev=-6.1 deg)
- [15:53:47] flight_64 N=5: FLAGGED -- |a|=18.66 outside nominal band [9.8,11.0]; gravity crosscheck diff=65.3 deg > 45.0 (speed=7.83 m/s, elev=7.0 deg)
- [15:53:47] flight_65 N=5: FLAGGED -- |a|=14.95 outside nominal band [9.8,11.0]; gravity crosscheck diff=45.2 deg > 45.0 (speed=6.54 m/s, elev=6.8 deg)
- [15:53:47] flight_65 N=10: FLAGGED -- |a|=11.97 outside nominal band [9.8,11.0]; adjusted from 10 -> 9, flight has fewer usable frames (speed=6.34 m/s, elev=6.2 deg)
- [15:53:47] flight_66 N=5: SKIPPED -- implausible |a|=54.22 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_66 N=10: FLAGGED -- |a|=8.46 outside nominal band [9.8,11.0] (speed=7.27 m/s, elev=-2.3 deg)
- [15:53:47] flight_67 N=5: FLAGGED -- |a|=13.31 outside nominal band [9.8,11.0] (speed=8.77 m/s, elev=-13.2 deg)
- [15:53:47] flight_67 N=10: FLAGGED -- |a|=13.22 outside nominal band [9.8,11.0]; adjusted from 10 -> 6, flight has fewer usable frames (speed=8.80 m/s, elev=-13.0 deg)
- [15:53:47] flight_68 N=5: SKIPPED -- implausible |a|=111.55 m/s^2 (hard gate [5.0,20.0]) (adjusted from 5 -> 4, flight has fewer usable frames)
- [15:53:47] flight_68 N=10: SKIPPED -- implausible |a|=111.55 m/s^2 (hard gate [5.0,20.0]) (adjusted from 10 -> 4, flight has fewer usable frames)
- [15:53:47] flight_69 N=10: FLAGGED -- adjusted from 10 -> 9, flight has fewer usable frames (speed=8.51 m/s, elev=7.6 deg)
- [15:53:47] flight_70 N=5: FLAGGED -- |a|=12.91 outside nominal band [9.8,11.0] (speed=9.15 m/s, elev=2.7 deg)
- [15:53:47] flight_70 N=10: FLAGGED -- |a|=9.54 outside nominal band [9.8,11.0] (speed=9.11 m/s, elev=-0.0 deg)
- [15:53:47] flight_71 N=5: FLAGGED -- |a|=16.57 outside nominal band [9.8,11.0] (speed=7.46 m/s, elev=-14.2 deg)
- [15:53:47] flight_71 N=10: FLAGGED -- |a|=13.29 outside nominal band [9.8,11.0] (speed=7.67 m/s, elev=-15.5 deg)
- [15:53:47] flight_72 N=5: FLAGGED -- gravity crosscheck diff=47.6 deg > 45.0 (speed=8.49 m/s, elev=-2.0 deg)
- [15:53:47] flight_72 N=10: FLAGGED -- |a|=8.93 outside nominal band [9.8,11.0]; adjusted from 10 -> 8, flight has fewer usable frames (speed=8.09 m/s, elev=-1.6 deg)
- [15:53:47] flight_73 N=5: SKIPPED -- implausible |a|=152.59 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_73 N=10: FLAGGED -- |a|=12.51 outside nominal band [9.8,11.0]; adjusted from 10 -> 8, flight has fewer usable frames (speed=7.79 m/s, elev=-1.2 deg)
- [15:53:47] flight_74 N=5: SKIPPED -- implausible |a|=28.32 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_74 N=10: FLAGGED -- |a|=18.25 outside nominal band [9.8,11.0]; gravity crosscheck diff=65.0 deg > 45.0; adjusted from 10 -> 9, flight has fewer usable frames (speed=8.02 m/s, elev=-4.5 deg)
- [15:53:47] flight_75 N=5: SKIPPED -- implausible |a|=100.26 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_75 N=10: FLAGGED -- |a|=8.13 outside nominal band [9.8,11.0]; adjusted from 10 -> 9, flight has fewer usable frames (speed=6.93 m/s, elev=-13.0 deg)
- [15:53:47] flight_76 N=5: SKIPPED -- implausible |a|=36.59 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_76 N=10: FLAGGED -- |a|=8.64 outside nominal band [9.8,11.0] (speed=7.25 m/s, elev=-8.9 deg)
- [15:53:47] flight_77 N=5: SKIPPED -- implausible |a|=74.27 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_77 N=10: FLAGGED -- |a|=8.34 outside nominal band [9.8,11.0]; adjusted from 10 -> 9, flight has fewer usable frames (speed=7.44 m/s, elev=-6.3 deg)
- [15:53:47] flight_78 N=5: FLAGGED -- |a|=16.31 outside nominal band [9.8,11.0] (speed=8.95 m/s, elev=7.9 deg)
- [15:53:47] flight_78 N=10: FLAGGED -- |a|=13.61 outside nominal band [9.8,11.0] (speed=9.00 m/s, elev=5.4 deg)
- [15:53:47] flight_79 N=5: SKIPPED -- implausible |a|=169.65 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_79 N=10: FLAGGED -- gravity crosscheck diff=75.0 deg > 45.0 (speed=10.09 m/s, elev=-7.0 deg)
- [15:53:47] flight_80 N=5: SKIPPED -- implausible |a|=27.49 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_80 N=10: FLAGGED -- |a|=7.43 outside nominal band [9.8,11.0]; adjusted from 10 -> 8, flight has fewer usable frames (speed=8.95 m/s, elev=-8.6 deg)
- [15:53:47] progress: 80/149 flights processed
- [15:53:47] flight_81 N=5: SKIPPED -- implausible |a|=33.35 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_82 N=5: SKIPPED -- implausible |a|=46.03 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_82 N=10: FLAGGED -- |a|=13.77 outside nominal band [9.8,11.0]; gravity crosscheck diff=52.8 deg > 45.0 (speed=9.05 m/s, elev=-7.1 deg)
- [15:53:47] flight_83 N=5: SKIPPED -- implausible |a|=35.79 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_83 N=10: FLAGGED -- |a|=14.85 outside nominal band [9.8,11.0] (speed=9.29 m/s, elev=7.0 deg)
- [15:53:47] flight_84 N=5: SKIPPED -- implausible |a|=79.68 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_84 N=10: FLAGGED -- |a|=15.34 outside nominal band [9.8,11.0]; gravity crosscheck diff=62.7 deg > 45.0 (speed=9.92 m/s, elev=-10.8 deg)
- [15:53:47] flight_85 N=5: SKIPPED -- implausible |a|=143.69 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_85 N=10: SKIPPED -- implausible |a|=23.82 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_86 N=5: SKIPPED -- implausible |a|=33.04 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_86 N=10: FLAGGED -- |a|=13.75 outside nominal band [9.8,11.0]; gravity crosscheck diff=71.4 deg > 45.0 (speed=10.43 m/s, elev=-6.5 deg)
- [15:53:47] flight_87 N=5: SKIPPED -- implausible |a|=40.09 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_87 N=10: FLAGGED -- |a|=18.52 outside nominal band [9.8,11.0]; gravity crosscheck diff=52.4 deg > 45.0 (speed=8.64 m/s, elev=0.8 deg)
- [15:53:47] flight_88 N=5: SKIPPED -- implausible |a|=23.93 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_88 N=10: FLAGGED -- |a|=11.72 outside nominal band [9.8,11.0] (speed=8.51 m/s, elev=10.3 deg)
- [15:53:47] flight_89 N=5: FLAGGED -- |a|=13.46 outside nominal band [9.8,11.0] (speed=9.53 m/s, elev=-17.6 deg)
- [15:53:47] flight_89 N=10: FLAGGED -- |a|=11.99 outside nominal band [9.8,11.0]; adjusted from 10 -> 8, flight has fewer usable frames (speed=9.63 m/s, elev=-16.9 deg)
- [15:53:47] flight_90 N=5: FLAGGED -- |a|=9.06 outside nominal band [9.8,11.0]; gravity crosscheck diff=46.8 deg > 45.0 (speed=8.29 m/s, elev=6.0 deg)
- [15:53:47] flight_90 N=10: FLAGGED -- |a|=9.23 outside nominal band [9.8,11.0]; adjusted from 10 -> 8, flight has fewer usable frames (speed=8.04 m/s, elev=7.9 deg)
- [15:53:47] flight_91 N=5: FLAGGED -- |a|=13.98 outside nominal band [9.8,11.0] (speed=5.76 m/s, elev=45.5 deg)
- [15:53:47] flight_92 N=5: SKIPPED -- implausible |a|=23.54 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_92 N=10: FLAGGED -- |a|=7.50 outside nominal band [9.8,11.0]; adjusted from 10 -> 6, flight has fewer usable frames (speed=3.92 m/s, elev=-6.8 deg)
- [15:53:47] flight_93 N=5: FLAGGED -- adjusted from 5 -> 4, flight has fewer usable frames (speed=6.89 m/s, elev=44.0 deg)
- [15:53:47] flight_93 N=10: FLAGGED -- adjusted from 10 -> 4, flight has fewer usable frames (speed=6.89 m/s, elev=44.0 deg)
- [15:53:47] flight_94 N=5: SKIPPED -- implausible |a|=27.87 m/s^2 (hard gate [5.0,20.0])
- [15:53:47] flight_94 N=10: SKIPPED -- implausible |a|=27.87 m/s^2 (hard gate [5.0,20.0]) (adjusted from 10 -> 5, flight has fewer usable frames)
- [15:53:47] flight_95 N=5: FLAGGED -- |a|=13.80 outside nominal band [9.8,11.0]; adjusted from 5 -> 3, flight has fewer usable frames (speed=7.49 m/s, elev=49.6 deg)
- [15:53:47] flight_95 N=10: FLAGGED -- |a|=13.80 outside nominal band [9.8,11.0]; adjusted from 10 -> 3, flight has fewer usable frames (speed=7.49 m/s, elev=49.6 deg)
- [15:53:47] flight_96 N=5: FLAGGED -- |a|=14.30 outside nominal band [9.8,11.0]; gravity crosscheck diff=48.6 deg > 45.0; adjusted from 5 -> 3, flight has fewer usable frames (speed=4.96 m/s, elev=15.3 deg)
- [15:53:47] flight_96 N=10: FLAGGED -- |a|=14.30 outside nominal band [9.8,11.0]; gravity crosscheck diff=48.6 deg > 45.0; adjusted from 10 -> 3, flight has fewer usable frames (speed=4.96 m/s, elev=15.3 deg)
- [15:53:47] flight_97 N=10: FLAGGED -- |a|=9.63 outside nominal band [9.8,11.0] (speed=5.35 m/s, elev=41.7 deg)
- [15:53:47] flight_98 N=5: FLAGGED -- |a|=9.38 outside nominal band [9.8,11.0]; adjusted from 5 -> 4, flight has fewer usable frames (speed=3.95 m/s, elev=-14.3 deg)
- [15:53:47] flight_98 N=10: FLAGGED -- |a|=9.38 outside nominal band [9.8,11.0]; adjusted from 10 -> 4, flight has fewer usable frames (speed=3.95 m/s, elev=-14.3 deg)
- [15:53:47] flight_99 N=5: SKIPPED -- implausible |a|=94.99 m/s^2 (hard gate [5.0,20.0]) (adjusted from 5 -> 4, flight has fewer usable frames)
- [15:53:47] flight_99 N=10: SKIPPED -- implausible |a|=94.99 m/s^2 (hard gate [5.0,20.0]) (adjusted from 10 -> 4, flight has fewer usable frames)
- [15:53:47] flight_100 N=5: FLAGGED -- |a|=11.33 outside nominal band [9.8,11.0] (speed=7.17 m/s, elev=49.3 deg)
- [15:53:47] flight_100 N=10: FLAGGED -- |a|=11.33 outside nominal band [9.8,11.0]; adjusted from 10 -> 5, flight has fewer usable frames (speed=7.17 m/s, elev=49.3 deg)
- [15:53:47] progress: 100/149 flights processed
- [15:53:47] flight_101: SKIPPED (both N) -- only 2 paired frames after filtering (raw cam0=16, cam1=9, filtered cam0=16, cam1=9)
- [15:53:47] flight_102 N=5: FLAGGED -- |a|=8.53 outside nominal band [9.8,11.0] (speed=4.88 m/s, elev=38.6 deg)
- [15:53:47] flight_102 N=10: FLAGGED -- |a|=8.69 outside nominal band [9.8,11.0]; adjusted from 10 -> 6, flight has fewer usable frames (speed=4.97 m/s, elev=38.8 deg)
- [15:53:48] flight_103: SKIPPED (both N) -- only 2 paired frames after filtering (raw cam0=15, cam1=6, filtered cam0=15, cam1=6)
- [15:53:48] flight_104 N=5: FLAGGED -- |a|=18.78 outside nominal band [9.8,11.0]; gravity crosscheck diff=45.2 deg > 45.0 (speed=7.45 m/s, elev=57.7 deg)
- [15:53:48] flight_104 N=10: FLAGGED -- |a|=9.54 outside nominal band [9.8,11.0] (speed=6.64 m/s, elev=54.7 deg)
- [15:53:48] flight_105: SKIPPED (both N) -- only 1 paired frames after filtering (raw cam0=10, cam1=10, filtered cam0=10, cam1=10)
- [15:53:48] flight_106 N=5: FLAGGED -- |a|=8.91 outside nominal band [9.8,11.0] (speed=5.55 m/s, elev=46.1 deg)
- [15:53:48] flight_106 N=10: FLAGGED -- |a|=8.88 outside nominal band [9.8,11.0]; adjusted from 10 -> 6, flight has fewer usable frames (speed=5.54 m/s, elev=46.2 deg)
- [15:53:48] flight_107 N=5: SKIPPED -- implausible |a|=52.11 m/s^2 (hard gate [5.0,20.0]) (adjusted from 5 -> 4, flight has fewer usable frames)
- [15:53:48] flight_107 N=10: SKIPPED -- implausible |a|=52.11 m/s^2 (hard gate [5.0,20.0]) (adjusted from 10 -> 4, flight has fewer usable frames)
- [15:53:48] flight_108 N=10: FLAGGED -- adjusted from 10 -> 5, flight has fewer usable frames (speed=6.22 m/s, elev=38.3 deg)
- [15:53:48] flight_109 N=5: FLAGGED -- |a|=9.32 outside nominal band [9.8,11.0]; adjusted from 5 -> 4, flight has fewer usable frames (speed=4.85 m/s, elev=24.1 deg)
- [15:53:48] flight_109 N=10: FLAGGED -- |a|=9.32 outside nominal band [9.8,11.0]; adjusted from 10 -> 4, flight has fewer usable frames (speed=4.85 m/s, elev=24.1 deg)
- [15:53:48] flight_110 N=5: SKIPPED -- implausible |a|=38.80 m/s^2 (hard gate [5.0,20.0])
- [15:53:48] flight_111 N=5: FLAGGED -- |a|=15.30 outside nominal band [9.8,11.0]; gravity crosscheck diff=46.8 deg > 45.0 (speed=5.16 m/s, elev=6.8 deg)
- [15:53:48] flight_111 N=10: FLAGGED -- gravity crosscheck diff=54.4 deg > 45.0 (speed=4.73 m/s, elev=3.3 deg)
- [15:53:48] flight_112 N=5: SKIPPED -- implausible |a|=172.16 m/s^2 (hard gate [5.0,20.0]) (adjusted from 5 -> 3, flight has fewer usable frames)
- [15:53:48] flight_112 N=10: SKIPPED -- implausible |a|=172.16 m/s^2 (hard gate [5.0,20.0]) (adjusted from 10 -> 3, flight has fewer usable frames)
- [15:53:48] flight_113 N=5: FLAGGED -- |a|=19.72 outside nominal band [9.8,11.0]; gravity crosscheck diff=49.1 deg > 45.0; adjusted from 5 -> 3, flight has fewer usable frames (speed=5.16 m/s, elev=-43.2 deg)
- [15:53:48] flight_113 N=10: FLAGGED -- |a|=19.72 outside nominal band [9.8,11.0]; gravity crosscheck diff=49.1 deg > 45.0; adjusted from 10 -> 3, flight has fewer usable frames (speed=5.16 m/s, elev=-43.2 deg)
- [15:53:48] flight_114 N=5: SKIPPED -- implausible |a|=64.63 m/s^2 (hard gate [5.0,20.0])
- [15:53:48] flight_114 N=10: FLAGGED -- |a|=14.39 outside nominal band [9.8,11.0]; gravity crosscheck diff=56.9 deg > 45.0; adjusted from 10 -> 8, flight has fewer usable frames (speed=4.83 m/s, elev=5.6 deg)
- [15:53:48] flight_115 N=5: SKIPPED -- implausible |a|=87.97 m/s^2 (hard gate [5.0,20.0])
- [15:53:48] flight_115 N=10: FLAGGED -- |a|=17.83 outside nominal band [9.8,11.0]; gravity crosscheck diff=84.8 deg > 45.0 (speed=5.79 m/s, elev=1.4 deg)
- [15:53:48] flight_116 N=5: SKIPPED -- implausible |a|=23.44 m/s^2 (hard gate [5.0,20.0])
- [15:53:48] flight_116 N=10: FLAGGED -- |a|=9.54 outside nominal band [9.8,11.0] (speed=4.17 m/s, elev=-35.4 deg)
- [15:53:48] flight_117: SKIPPED (both N) -- only 0 paired frames after filtering (raw cam0=12, cam1=4, filtered cam0=12, cam1=4)
- [15:53:48] flight_118: SKIPPED (both N) -- only 1 paired frames after filtering (raw cam0=9, cam1=7, filtered cam0=9, cam1=7)
- [15:53:48] flight_119 N=5: SKIPPED -- implausible |a|=63.71 m/s^2 (hard gate [5.0,20.0])
- [15:53:48] flight_119 N=10: FLAGGED -- |a|=8.63 outside nominal band [9.8,11.0] (speed=4.63 m/s, elev=-11.4 deg)
- [15:53:48] flight_120 N=10: FLAGGED -- |a|=11.41 outside nominal band [9.8,11.0]; adjusted from 10 -> 6, flight has fewer usable frames (speed=5.84 m/s, elev=-45.7 deg)
- [15:53:48] progress: 120/149 flights processed
- [15:53:48] flight_121 N=10: FLAGGED -- adjusted from 10 -> 5, flight has fewer usable frames (speed=6.90 m/s, elev=45.0 deg)
- [15:53:48] flight_122 N=5: FLAGGED -- |a|=6.92 outside nominal band [9.8,11.0] (speed=4.34 m/s, elev=-36.8 deg)
- [15:53:48] flight_122 N=10: FLAGGED -- |a|=8.59 outside nominal band [9.8,11.0]; adjusted from 10 -> 6, flight has fewer usable frames (speed=4.22 m/s, elev=-33.0 deg)
- [15:53:48] flight_123: SKIPPED (both N) -- only 1 paired frames after filtering (raw cam0=7, cam1=11, filtered cam0=7, cam1=11)
- [15:53:48] flight_124: SKIPPED (both N) -- only 0 paired frames after filtering (raw cam0=5, cam1=6, filtered cam0=5, cam1=6)
- [15:53:48] flight_125 N=5: SKIPPED -- implausible |a|=60.18 m/s^2 (hard gate [5.0,20.0])
- [15:53:48] flight_125 N=10: FLAGGED -- |a|=15.51 outside nominal band [9.8,11.0]; gravity crosscheck diff=89.5 deg > 45.0 (speed=4.49 m/s, elev=-10.7 deg)
- [15:53:48] flight_126: SKIPPED (both N) -- only 0 paired frames after filtering (raw cam0=2, cam1=1, filtered cam0=2, cam1=1)
- [15:53:48] flight_127: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_128: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_129: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_130: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_131: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_132: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_133: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_134: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_135: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_136: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_137: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_138: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_139: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_140: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] progress: 140/149 flights processed
- [15:53:48] flight_141: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_142: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_143: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_144: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_145: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_146: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_147: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_148: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] flight_149: SKIPPED (both N) -- missing analysis_3/detections3 csv
- [15:53:48] batch loop complete: 149 flights processed, 298 rows written
- [15:53:48] wrote CSV -> C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\flight_binning\flight_velocity_angle.csv (298 rows)
- [15:53:48] summary: 136 ok rows, 162 skipped rows, 123 flagged (of the ok rows), out of 298 total attempted rows
- [15:53:48] plotted distribution_N5.png (47 points, 39 flagged)
- [15:53:48] plotted distribution_N10.png (89 points, 84 flagged)
- [15:53:49] plotted distribution_overlay_histograms.png
- [15:53:49] plotted distribution_N_sensitivity.png
- [15:53:49] === flight_velocity_angle_binner.py: batch run complete ===
- [16:04:56] === flight_velocity_angle_binner.py: batch run starting ===
- [16:04:57] loaded world transforms: registration1 up_vec from img_0031, registration2 up_vec from img_0034
- [16:04:57] found 149 flight folders under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights
- [16:04:57] flight_1 N=5: SKIPPED -- implausible |a|=179.43 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_1 N=10: FLAGGED -- |a|=12.79 outside nominal band [9.8,11.0] (speed=8.27 m/s, elev=58.1 deg)
- [16:04:57] flight_2 N=5: SKIPPED -- implausible |a|=84.08 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_2 N=10: FLAGGED -- |a|=14.48 outside nominal band [9.8,11.0]; gravity crosscheck diff=69.5 deg > 45.0 (speed=9.40 m/s, elev=-8.1 deg)
- [16:04:57] flight_3 N=5: FLAGGED -- |a|=14.50 outside nominal band [9.8,11.0]; gravity crosscheck diff=71.3 deg > 45.0 (speed=10.54 m/s, elev=4.7 deg)
- [16:04:57] flight_3 N=10: SKIPPED -- implausible |a|=25.71 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_4 N=5: SKIPPED -- implausible |a|=282.12 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_4 N=10: SKIPPED -- implausible |a|=49.35 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_5 N=5: SKIPPED -- implausible |a|=43.36 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_5 N=10: FLAGGED -- |a|=18.54 outside nominal band [9.8,11.0] (speed=7.84 m/s, elev=3.3 deg)
- [16:04:57] flight_6 N=5: SKIPPED -- implausible |a|=98.58 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_6 N=10: SKIPPED -- implausible |a|=25.45 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_7 N=5: SKIPPED -- implausible |a|=111.32 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_7 N=10: SKIPPED -- implausible |a|=25.19 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_8 N=5: SKIPPED -- implausible |a|=79.49 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_8 N=10: SKIPPED -- implausible |a|=79.38 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_9 N=5: SKIPPED -- implausible |a|=29.71 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_9 N=10: FLAGGED -- |a|=13.99 outside nominal band [9.8,11.0]; gravity crosscheck diff=50.9 deg > 45.0 (speed=9.04 m/s, elev=4.1 deg)
- [16:04:57] flight_10 N=5: SKIPPED -- implausible |a|=35.21 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_10 N=10: SKIPPED -- implausible |a|=41.32 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_11 N=5: SKIPPED -- implausible |a|=85.51 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_11 N=10: SKIPPED -- implausible |a|=24.20 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_12 N=5: SKIPPED -- implausible |a|=94.31 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_12 N=10: SKIPPED -- implausible |a|=31.09 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_13 N=5: SKIPPED -- implausible |a|=161.45 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_13 N=10: SKIPPED -- implausible |a|=38.78 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_14 N=5: SKIPPED -- implausible |a|=48.77 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_14 N=10: FLAGGED -- |a|=18.25 outside nominal band [9.8,11.0]; gravity crosscheck diff=60.1 deg > 45.0 (speed=8.97 m/s, elev=1.6 deg)
- [16:04:57] flight_15 N=5: SKIPPED -- implausible |a|=40.01 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_15 N=10: FLAGGED -- |a|=17.72 outside nominal band [9.8,11.0]; gravity crosscheck diff=54.2 deg > 45.0 (speed=8.12 m/s, elev=17.3 deg)
- [16:04:57] flight_16 N=5: SKIPPED -- implausible |a|=218.28 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_16 N=10: SKIPPED -- implausible |a|=58.64 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_17 N=5: SKIPPED -- implausible |a|=65.15 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_17 N=10: SKIPPED -- implausible |a|=54.35 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_18 N=5: SKIPPED -- implausible |a|=258.44 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_18 N=10: SKIPPED -- implausible |a|=49.69 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_19 N=5: SKIPPED -- implausible |a|=301.00 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_19 N=10: FLAGGED -- |a|=15.66 outside nominal band [9.8,11.0]; gravity crosscheck diff=68.6 deg > 45.0 (speed=7.46 m/s, elev=18.1 deg)
- [16:04:57] flight_20 N=5: SKIPPED -- implausible |a|=145.10 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_20 N=10: SKIPPED -- implausible |a|=39.92 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] progress: 20/149 flights processed
- [16:04:57] flight_21 N=5: SKIPPED -- implausible |a|=84.32 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_21 N=10: SKIPPED -- implausible |a|=66.24 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_22 N=5: SKIPPED -- implausible |a|=45.58 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_22 N=10: SKIPPED -- implausible |a|=31.38 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_23 N=5: SKIPPED -- implausible |a|=282.94 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_23 N=10: SKIPPED -- implausible |a|=22.57 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_24 N=5: SKIPPED -- implausible |a|=70.93 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_24 N=10: SKIPPED -- implausible |a|=32.00 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_25 N=5: SKIPPED -- implausible |a|=171.98 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_25 N=10: FLAGGED -- |a|=17.77 outside nominal band [9.8,11.0] (speed=9.86 m/s, elev=41.8 deg)
- [16:04:57] flight_26 N=5: SKIPPED -- implausible |a|=36.76 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_26 N=10: SKIPPED -- implausible |a|=39.85 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_27 N=5: SKIPPED -- implausible |a|=423.15 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_27 N=10: SKIPPED -- implausible |a|=23.00 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_28 N=5: SKIPPED -- implausible |a|=225.21 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_28 N=10: SKIPPED -- implausible |a|=25.06 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_29 N=5: SKIPPED -- implausible |a|=42.97 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_29 N=10: FLAGGED -- |a|=14.74 outside nominal band [9.8,11.0] (speed=7.10 m/s, elev=61.4 deg)
- [16:04:57] flight_30 N=5: SKIPPED -- implausible |a|=194.10 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_30 N=10: SKIPPED -- implausible |a|=24.60 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_31 N=5: SKIPPED -- implausible |a|=341.91 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_31 N=10: SKIPPED -- implausible |a|=24.39 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_32 N=5: SKIPPED -- implausible |a|=59.43 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_32 N=10: FLAGGED -- |a|=17.59 outside nominal band [9.8,11.0]; gravity crosscheck diff=65.6 deg > 45.0 (speed=7.02 m/s, elev=56.9 deg)
- [16:04:57] flight_33 N=5: SKIPPED -- implausible |a|=403.09 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_33 N=10: SKIPPED -- implausible |a|=152.44 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_34 N=5: SKIPPED -- implausible |a|=165.54 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_34 N=10: SKIPPED -- implausible |a|=28.74 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_35 N=5: SKIPPED -- implausible |a|=255.95 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_35 N=10: SKIPPED -- implausible |a|=36.92 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_36 N=5: SKIPPED -- implausible |a|=112.67 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_36 N=10: SKIPPED -- implausible |a|=43.89 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_37 N=5: SKIPPED -- implausible |a|=196.00 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_37 N=10: FLAGGED -- |a|=12.24 outside nominal band [9.8,11.0] (speed=7.47 m/s, elev=60.1 deg)
- [16:04:57] flight_38 N=5: SKIPPED -- implausible |a|=117.53 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_38 N=10: SKIPPED -- implausible |a|=22.23 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_39 N=5: SKIPPED -- implausible |a|=189.86 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_39 N=10: SKIPPED -- implausible |a|=55.52 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_40 N=5: SKIPPED -- implausible |a|=145.88 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_40 N=10: FLAGGED -- |a|=11.78 outside nominal band [9.8,11.0] (speed=7.00 m/s, elev=46.2 deg)
- [16:04:57] progress: 40/149 flights processed
- [16:04:57] flight_41 N=5: SKIPPED -- implausible |a|=112.21 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_41 N=10: FLAGGED -- |a|=16.69 outside nominal band [9.8,11.0]; gravity crosscheck diff=48.5 deg > 45.0 (speed=7.19 m/s, elev=58.9 deg)
- [16:04:57] flight_42 N=5: SKIPPED -- implausible |a|=91.64 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_42 N=10: FLAGGED -- |a|=17.34 outside nominal band [9.8,11.0]; gravity crosscheck diff=46.3 deg > 45.0 (speed=6.63 m/s, elev=56.4 deg)
- [16:04:57] flight_43 N=5: SKIPPED -- implausible |a|=75.10 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_43 N=10: SKIPPED -- implausible |a|=37.37 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_44 N=5: SKIPPED -- implausible |a|=226.65 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_44 N=10: SKIPPED -- implausible |a|=23.88 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_45 N=5: SKIPPED -- implausible |a|=148.53 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_45 N=10: SKIPPED -- implausible |a|=40.13 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_46 N=5: SKIPPED -- implausible |a|=33.65 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_46 N=10: SKIPPED -- implausible |a|=33.82 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_47 N=5: SKIPPED -- implausible |a|=51.56 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_47 N=10: FLAGGED -- |a|=11.12 outside nominal band [9.8,11.0]; gravity crosscheck diff=61.1 deg > 45.0 (speed=7.29 m/s, elev=50.2 deg)
- [16:04:57] flight_48 N=5: SKIPPED -- implausible |a|=161.79 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_48 N=10: FLAGGED -- |a|=11.55 outside nominal band [9.8,11.0]; gravity crosscheck diff=58.3 deg > 45.0 (speed=8.11 m/s, elev=41.5 deg)
- [16:04:57] flight_49 N=5: SKIPPED -- implausible |a|=63.43 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_49 N=10: FLAGGED -- |a|=11.12 outside nominal band [9.8,11.0]; gravity crosscheck diff=65.7 deg > 45.0 (speed=6.68 m/s, elev=47.5 deg)
- [16:04:57] flight_50 N=5: SKIPPED -- implausible |a|=148.57 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_50 N=10: SKIPPED -- implausible |a|=21.85 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_51 N=5: SKIPPED -- implausible |a|=76.62 m/s^2 (hard gate [5.0,20.0])
- [16:04:57] flight_51 N=10: SKIPPED -- implausible |a|=28.47 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_52 N=5: SKIPPED -- implausible |a|=417.62 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_52 N=10: FLAGGED -- |a|=12.83 outside nominal band [9.8,11.0]; gravity crosscheck diff=67.1 deg > 45.0 (speed=8.12 m/s, elev=53.0 deg)
- [16:04:58] flight_53 N=5: SKIPPED -- implausible |a|=77.24 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_53 N=10: SKIPPED -- implausible |a|=28.60 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_54 N=5: SKIPPED -- implausible |a|=26.85 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_54 N=10: FLAGGED -- |a|=17.19 outside nominal band [9.8,11.0]; gravity crosscheck diff=49.7 deg > 45.0 (speed=7.97 m/s, elev=34.0 deg)
- [16:04:58] flight_55 N=5: SKIPPED -- implausible |a|=212.61 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_55 N=10: SKIPPED -- implausible |a|=51.16 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_56 N=5: SKIPPED -- implausible |a|=69.42 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_56 N=10: SKIPPED -- implausible |a|=22.84 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_57 N=5: FLAGGED -- |a|=19.60 outside nominal band [9.8,11.0]; gravity crosscheck diff=144.4 deg > 45.0 (speed=6.18 m/s, elev=52.3 deg)
- [16:04:58] flight_57 N=10: SKIPPED -- implausible |a|=29.89 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_58 N=5: SKIPPED -- implausible |a|=333.19 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_58 N=10: SKIPPED -- implausible |a|=25.44 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_59 N=5: SKIPPED -- implausible |a|=22.15 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_59 N=10: SKIPPED -- implausible |a|=28.55 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_60 N=5: SKIPPED -- implausible |a|=161.52 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_60 N=10: SKIPPED -- implausible |a|=26.21 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] progress: 60/149 flights processed
- [16:04:58] flight_61 N=5: SKIPPED -- implausible |a|=87.34 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_61 N=10: SKIPPED -- implausible |a|=35.18 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_62 N=5: SKIPPED -- implausible |a|=183.66 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_62 N=10: SKIPPED -- implausible |a|=24.50 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_63 N=5: SKIPPED -- implausible |a|=220.40 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_63 N=10: SKIPPED -- implausible |a|=39.06 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_64 N=5: SKIPPED -- implausible |a|=47.70 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_64 N=10: FLAGGED -- |a|=9.56 outside nominal band [9.8,11.0] (speed=7.05 m/s, elev=13.1 deg)
- [16:04:58] flight_65 N=5: SKIPPED -- implausible |a|=44.30 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_65 N=10: FLAGGED -- gravity crosscheck diff=77.6 deg > 45.0 (speed=7.13 m/s, elev=4.7 deg)
- [16:04:58] flight_66 N=5: SKIPPED -- implausible |a|=88.19 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_66 N=10: FLAGGED -- |a|=12.88 outside nominal band [9.8,11.0]; gravity crosscheck diff=58.5 deg > 45.0 (speed=7.69 m/s, elev=-1.2 deg)
- [16:04:58] flight_67 N=5: SKIPPED -- implausible |a|=78.01 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_67 N=10: FLAGGED -- gravity crosscheck diff=54.2 deg > 45.0 (speed=9.05 m/s, elev=-10.3 deg)
- [16:04:58] flight_68 N=5: SKIPPED -- implausible |a|=31.68 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_68 N=10: FLAGGED -- |a|=17.50 outside nominal band [9.8,11.0]; gravity crosscheck diff=73.5 deg > 45.0 (speed=9.13 m/s, elev=8.8 deg)
- [16:04:58] flight_69 N=5: FLAGGED -- |a|=19.51 outside nominal band [9.8,11.0] (speed=9.07 m/s, elev=11.0 deg)
- [16:04:58] flight_69 N=10: FLAGGED -- |a|=12.18 outside nominal band [9.8,11.0]; gravity crosscheck diff=58.1 deg > 45.0 (speed=9.00 m/s, elev=10.2 deg)
- [16:04:58] flight_70 N=5: SKIPPED -- implausible |a|=126.71 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_70 N=10: FLAGGED -- |a|=11.46 outside nominal band [9.8,11.0]; gravity crosscheck diff=64.5 deg > 45.0 (speed=9.37 m/s, elev=1.3 deg)
- [16:04:58] flight_71 N=5: SKIPPED -- implausible |a|=72.71 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_71 N=10: FLAGGED -- |a|=8.74 outside nominal band [9.8,11.0] (speed=6.90 m/s, elev=-12.2 deg)
- [16:04:58] flight_72 N=5: SKIPPED -- implausible |a|=107.76 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_72 N=10: SKIPPED -- implausible |a|=34.37 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_73 N=5: SKIPPED -- implausible |a|=82.90 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_73 N=10: SKIPPED -- implausible |a|=22.03 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_74 N=5: SKIPPED -- implausible |a|=199.34 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_74 N=10: FLAGGED -- |a|=11.59 outside nominal band [9.8,11.0]; gravity crosscheck diff=73.3 deg > 45.0 (speed=9.00 m/s, elev=9.5 deg)
- [16:04:58] flight_75 N=5: SKIPPED -- implausible |a|=92.82 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_75 N=10: FLAGGED -- |a|=18.33 outside nominal band [9.8,11.0]; gravity crosscheck diff=75.9 deg > 45.0 (speed=7.45 m/s, elev=4.9 deg)
- [16:04:58] flight_76 N=5: SKIPPED -- implausible |a|=69.46 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_76 N=10: SKIPPED -- implausible |a|=31.62 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_77 N=5: SKIPPED -- implausible |a|=62.08 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_77 N=10: SKIPPED -- implausible |a|=25.70 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_78 N=5: SKIPPED -- implausible |a|=141.75 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_78 N=10: FLAGGED -- |a|=11.55 outside nominal band [9.8,11.0] (speed=8.44 m/s, elev=6.4 deg)
- [16:04:58] flight_79 N=5: FLAGGED -- |a|=16.83 outside nominal band [9.8,11.0]; gravity crosscheck diff=84.1 deg > 45.0 (speed=10.12 m/s, elev=-5.1 deg)
- [16:04:58] flight_79 N=10: FLAGGED -- |a|=8.09 outside nominal band [9.8,11.0] (speed=9.89 m/s, elev=-3.3 deg)
- [16:04:58] flight_80 N=5: SKIPPED -- implausible |a|=40.10 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_80 N=10: FLAGGED -- |a|=15.93 outside nominal band [9.8,11.0] (speed=8.66 m/s, elev=-5.1 deg)
- [16:04:58] progress: 80/149 flights processed
- [16:04:58] flight_81 N=5: SKIPPED -- implausible |a|=94.19 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_81 N=10: FLAGGED -- |a|=9.12 outside nominal band [9.8,11.0] (speed=9.85 m/s, elev=-6.8 deg)
- [16:04:58] flight_82 N=5: SKIPPED -- implausible |a|=100.98 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_82 N=10: FLAGGED -- |a|=14.73 outside nominal band [9.8,11.0] (speed=9.15 m/s, elev=0.4 deg)
- [16:04:58] flight_83 N=5: SKIPPED -- implausible |a|=57.78 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_83 N=10: SKIPPED -- implausible |a|=27.57 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_84 N=5: SKIPPED -- implausible |a|=52.57 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_84 N=10: SKIPPED -- implausible |a|=20.25 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_85 N=5: SKIPPED -- implausible |a|=166.36 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_85 N=10: FLAGGED -- |a|=9.45 outside nominal band [9.8,11.0] (speed=9.63 m/s, elev=5.9 deg)
- [16:04:58] flight_86 N=5: SKIPPED -- implausible |a|=44.14 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_87 N=5: SKIPPED -- implausible |a|=47.70 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_87 N=10: SKIPPED -- implausible |a|=28.55 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_88 N=5: SKIPPED -- implausible |a|=46.30 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_88 N=10: SKIPPED -- implausible |a|=50.07 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_89 N=5: SKIPPED -- implausible |a|=46.14 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_89 N=10: FLAGGED -- |a|=14.41 outside nominal band [9.8,11.0]; gravity crosscheck diff=64.8 deg > 45.0 (speed=9.99 m/s, elev=-12.2 deg)
- [16:04:58] flight_90 N=5: SKIPPED -- implausible |a|=70.99 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_90 N=10: FLAGGED -- |a|=13.97 outside nominal band [9.8,11.0] (speed=7.79 m/s, elev=10.4 deg)
- [16:04:58] flight_91 N=5: SKIPPED -- implausible |a|=46.87 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_91 N=10: SKIPPED -- implausible |a|=40.54 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_92 N=5: SKIPPED -- implausible |a|=309.42 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_92 N=10: SKIPPED -- implausible |a|=31.10 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_93 N=5: SKIPPED -- implausible |a|=209.35 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_93 N=10: SKIPPED -- implausible |a|=44.58 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_94 N=5: SKIPPED -- implausible |a|=150.36 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_94 N=10: FLAGGED -- |a|=13.49 outside nominal band [9.8,11.0] (speed=7.84 m/s, elev=56.0 deg)
- [16:04:58] flight_95 N=5: SKIPPED -- implausible |a|=112.81 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_95 N=10: FLAGGED -- |a|=12.68 outside nominal band [9.8,11.0]; gravity crosscheck diff=59.5 deg > 45.0 (speed=7.51 m/s, elev=52.5 deg)
- [16:04:58] flight_96 N=5: SKIPPED -- implausible |a|=174.34 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_96 N=10: SKIPPED -- implausible |a|=29.71 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_97 N=5: SKIPPED -- implausible |a|=235.52 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_97 N=10: SKIPPED -- implausible |a|=20.49 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_98 N=5: SKIPPED -- implausible |a|=29.05 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_98 N=10: FLAGGED -- |a|=11.04 outside nominal band [9.8,11.0] (speed=6.96 m/s, elev=54.1 deg)
- [16:04:58] flight_99 N=5: SKIPPED -- implausible |a|=29.24 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_99 N=10: FLAGGED -- |a|=11.84 outside nominal band [9.8,11.0]; gravity crosscheck diff=46.7 deg > 45.0 (speed=6.75 m/s, elev=49.4 deg)
- [16:04:58] flight_100 N=5: SKIPPED -- implausible |a|=140.20 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_100 N=10: SKIPPED -- implausible |a|=65.18 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] progress: 100/149 flights processed
- [16:04:58] flight_101 N=5: SKIPPED -- implausible |a|=196.26 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_101 N=10: SKIPPED -- implausible |a|=46.23 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_102 N=5: SKIPPED -- implausible |a|=109.85 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_102 N=10: FLAGGED -- |a|=15.28 outside nominal band [9.8,11.0] (speed=7.01 m/s, elev=49.4 deg)
- [16:04:58] flight_103 N=5: SKIPPED -- implausible |a|=42.06 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_103 N=10: SKIPPED -- implausible |a|=35.20 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_104 N=5: SKIPPED -- implausible |a|=36.74 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_104 N=10: FLAGGED -- |a|=19.39 outside nominal band [9.8,11.0]; gravity crosscheck diff=63.4 deg > 45.0 (speed=6.58 m/s, elev=59.4 deg)
- [16:04:58] flight_105 N=5: SKIPPED -- implausible |a|=89.97 m/s^2 (hard gate [5.0,20.0])
- [16:04:58] flight_105 N=10: SKIPPED -- implausible |a|=55.07 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_106 N=5: SKIPPED -- implausible |a|=232.09 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_106 N=10: SKIPPED -- implausible |a|=31.55 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_107 N=5: SKIPPED -- implausible |a|=149.21 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_107 N=10: SKIPPED -- implausible |a|=57.32 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_108 N=5: SKIPPED -- implausible |a|=146.24 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_108 N=10: FLAGGED -- |a|=11.82 outside nominal band [9.8,11.0] (speed=6.78 m/s, elev=54.5 deg)
- [16:04:59] flight_109 N=5: SKIPPED -- implausible |a|=95.99 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_109 N=10: FLAGGED -- |a|=11.94 outside nominal band [9.8,11.0] (speed=7.29 m/s, elev=52.1 deg)
- [16:04:59] flight_110 N=5: SKIPPED -- implausible |a|=132.75 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_110 N=10: SKIPPED -- implausible |a|=84.32 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_111 N=5: SKIPPED -- implausible |a|=171.94 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_111 N=10: SKIPPED -- implausible |a|=72.47 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_112 N=5: SKIPPED -- implausible |a|=175.69 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_112 N=10: SKIPPED -- implausible |a|=63.75 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_113 N=5: SKIPPED -- implausible |a|=277.49 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_113 N=10: SKIPPED -- implausible |a|=81.94 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_114 N=5: SKIPPED -- implausible |a|=250.13 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_114 N=10: FLAGGED -- |a|=19.91 outside nominal band [9.8,11.0] (speed=6.72 m/s, elev=54.1 deg)
- [16:04:59] flight_115 N=5: SKIPPED -- implausible |a|=142.70 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_115 N=10: SKIPPED -- implausible |a|=23.39 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_116 N=5: SKIPPED -- implausible |a|=111.05 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_116 N=10: FLAGGED -- |a|=7.41 outside nominal band [9.8,11.0] (speed=6.31 m/s, elev=58.5 deg)
- [16:04:59] flight_117 N=5: SKIPPED -- implausible |a|=101.08 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_117 N=10: SKIPPED -- implausible |a|=46.04 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_118 N=5: SKIPPED -- implausible |a|=360.38 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_118 N=10: SKIPPED -- implausible |a|=21.06 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_119 N=5: SKIPPED -- implausible |a|=114.25 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_119 N=10: SKIPPED -- implausible |a|=31.10 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_120 N=5: SKIPPED -- implausible |a|=85.44 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_120 N=10: SKIPPED -- implausible |a|=32.87 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] progress: 120/149 flights processed
- [16:04:59] flight_121 N=5: SKIPPED -- implausible |a|=50.71 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_121 N=10: FLAGGED -- |a|=7.73 outside nominal band [9.8,11.0] (speed=7.53 m/s, elev=54.4 deg)
- [16:04:59] flight_122 N=5: SKIPPED -- implausible |a|=159.22 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_123 N=5: SKIPPED -- implausible |a|=20.20 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_123 N=10: SKIPPED -- implausible |a|=26.65 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_124 N=5: SKIPPED -- implausible |a|=32.57 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_124 N=10: SKIPPED -- implausible |a|=37.03 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_125 N=5: SKIPPED -- implausible |a|=39.71 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_125 N=10: FLAGGED -- |a|=17.11 outside nominal band [9.8,11.0] (speed=7.88 m/s, elev=50.2 deg)
- [16:04:59] flight_126 N=5: SKIPPED -- implausible |a|=54.82 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_126 N=10: SKIPPED -- implausible |a|=24.34 m/s^2 (hard gate [5.0,20.0])
- [16:04:59] flight_127: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_128: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_129: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_130: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_131: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_132: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_133: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_134: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_135: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_136: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_137: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_138: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_139: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_140: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] progress: 140/149 flights processed
- [16:04:59] flight_141: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_142: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_143: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_144: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_145: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_146: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_147: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_148: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] flight_149: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:04:59] batch loop complete: 149 flights processed, 298 rows written
- [16:04:59] wrote CSV -> C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\flight_binning\flight_velocity_angle.csv (298 rows)
- [16:04:59] summary: 55 ok rows, 243 skipped rows, 53 flagged (of the ok rows), out of 298 total attempted rows
- [16:04:59] plotted distribution_N5.png (4 points, 4 flagged)
- [16:04:59] plotted distribution_N10.png (51 points, 49 flagged)
- [16:05:00] plotted distribution_overlay_histograms.png
- [16:05:00] plotted distribution_N_sensitivity.png
- [16:05:00] === flight_velocity_angle_binner.py: batch run complete ===
- [16:11:21] === flight_velocity_angle_binner.py: batch run starting ===
- [16:11:21] loaded world transforms: registration1 up_vec from img_0031, registration2 up_vec from img_0034
- [16:11:21] found 149 flight folders under C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\ball_flights
- [16:11:21] flight_1 N=20: FLAGGED -- |a|=14.61 outside nominal band [9.8,11.0] (speed=8.24 m/s, elev=59.6 deg)
- [16:11:21] flight_2 N=20: FLAGGED -- |a|=9.20 outside nominal band [9.8,11.0] (speed=8.77 m/s, elev=-7.2 deg)
- [16:11:21] flight_2 N=30: FLAGGED -- |a|=9.13 outside nominal band [9.8,11.0] (speed=8.85 m/s, elev=-6.0 deg)
- [16:11:21] flight_3 N=30: FLAGGED -- |a|=9.29 outside nominal band [9.8,11.0] (speed=9.95 m/s, elev=5.3 deg)
- [16:11:21] flight_4 N=20: FLAGGED -- |a|=11.37 outside nominal band [9.8,11.0]; gravity crosscheck diff=49.7 deg > 45.0 (speed=8.25 m/s, elev=-5.1 deg)
- [16:11:21] flight_4 N=30: FLAGGED -- |a|=8.86 outside nominal band [9.8,11.0] (speed=7.94 m/s, elev=-4.9 deg)
- [16:11:21] flight_5 N=30: FLAGGED -- |a|=9.43 outside nominal band [9.8,11.0] (speed=8.05 m/s, elev=-1.1 deg)
- [16:11:21] flight_6 N=20: FLAGGED -- |a|=15.52 outside nominal band [9.8,11.0] (speed=8.28 m/s, elev=8.3 deg)
- [16:11:21] flight_7 N=20: FLAGGED -- |a|=11.80 outside nominal band [9.8,11.0] (speed=7.95 m/s, elev=-10.0 deg)
- [16:11:21] flight_7 N=30: FLAGGED -- |a|=9.60 outside nominal band [9.8,11.0]; adjusted from 30 -> 28, flight has fewer usable frames (speed=7.93 m/s, elev=-9.9 deg)
- [16:11:21] flight_8 N=30: FLAGGED -- |a|=9.24 outside nominal band [9.8,11.0] (speed=8.10 m/s, elev=-2.8 deg)
- [16:11:21] flight_9 N=30: FLAGGED -- |a|=9.30 outside nominal band [9.8,11.0] (speed=8.73 m/s, elev=3.7 deg)
- [16:11:21] flight_10 N=20: FLAGGED -- |a|=9.52 outside nominal band [9.8,11.0] (speed=8.65 m/s, elev=-3.3 deg)
- [16:11:21] flight_10 N=30: FLAGGED -- |a|=8.91 outside nominal band [9.8,11.0] (speed=8.54 m/s, elev=-3.7 deg)
- [16:11:21] flight_11 N=20: FLAGGED -- |a|=9.76 outside nominal band [9.8,11.0] (speed=6.47 m/s, elev=22.7 deg)
- [16:11:21] flight_12 N=20: FLAGGED -- |a|=9.32 outside nominal band [9.8,11.0] (speed=8.32 m/s, elev=4.6 deg)
- [16:11:21] flight_12 N=30: FLAGGED -- |a|=9.04 outside nominal band [9.8,11.0] (speed=8.31 m/s, elev=4.2 deg)
- [16:11:21] flight_13 N=20: FLAGGED -- |a|=11.83 outside nominal band [9.8,11.0] (speed=8.15 m/s, elev=9.4 deg)
- [16:11:21] flight_13 N=30: FLAGGED -- |a|=9.67 outside nominal band [9.8,11.0] (speed=8.36 m/s, elev=9.2 deg)
- [16:11:21] flight_14 N=20: FLAGGED -- |a|=9.56 outside nominal band [9.8,11.0] (speed=8.02 m/s, elev=2.3 deg)
- [16:11:21] flight_14 N=30: FLAGGED -- |a|=9.44 outside nominal band [9.8,11.0] (speed=8.18 m/s, elev=1.8 deg)
- [16:11:21] flight_15 N=20: FLAGGED -- |a|=11.06 outside nominal band [9.8,11.0] (speed=8.54 m/s, elev=17.3 deg)
- [16:11:21] flight_16 N=20: FLAGGED -- |a|=9.64 outside nominal band [9.8,11.0] (speed=9.02 m/s, elev=-1.1 deg)
- [16:11:21] flight_16 N=30: FLAGGED -- |a|=9.35 outside nominal band [9.8,11.0] (speed=9.02 m/s, elev=-1.4 deg)
- [16:11:21] flight_17 N=20: FLAGGED -- |a|=11.76 outside nominal band [9.8,11.0]; adjusted from 20 -> 19, flight has fewer usable frames (speed=10.12 m/s, elev=-17.5 deg)
- [16:11:21] flight_17 N=30: FLAGGED -- |a|=11.76 outside nominal band [9.8,11.0]; adjusted from 30 -> 19, flight has fewer usable frames (speed=10.12 m/s, elev=-17.5 deg)
- [16:11:21] flight_18 N=20: FLAGGED -- |a|=11.47 outside nominal band [9.8,11.0] (speed=6.17 m/s, elev=33.3 deg)
- [16:11:21] flight_18 N=30: FLAGGED -- |a|=9.53 outside nominal band [9.8,11.0] (speed=6.37 m/s, elev=29.2 deg)
- [16:11:21] flight_19 N=20: FLAGGED -- |a|=11.45 outside nominal band [9.8,11.0]; gravity crosscheck diff=53.8 deg > 45.0 (speed=6.90 m/s, elev=20.0 deg)
- [16:11:21] flight_20 N=20: FLAGGED -- |a|=9.77 outside nominal band [9.8,11.0] (speed=7.55 m/s, elev=11.4 deg)
- [16:11:21] flight_20 N=30: FLAGGED -- |a|=9.12 outside nominal band [9.8,11.0] (speed=7.64 m/s, elev=11.3 deg)
- [16:11:21] progress: 20/149 flights processed
- [16:11:21] flight_21 N=20: FLAGGED -- |a|=8.71 outside nominal band [9.8,11.0] (speed=7.14 m/s, elev=51.4 deg)
- [16:11:21] flight_21 N=30: FLAGGED -- |a|=9.55 outside nominal band [9.8,11.0] (speed=7.26 m/s, elev=51.4 deg)
- [16:11:21] flight_22 N=20: FLAGGED -- |a|=14.66 outside nominal band [9.8,11.0] (speed=7.66 m/s, elev=51.4 deg)
- [16:11:21] flight_22 N=30: FLAGGED -- |a|=11.47 outside nominal band [9.8,11.0] (speed=7.48 m/s, elev=49.6 deg)
- [16:11:21] flight_24 N=20: FLAGGED -- |a|=11.10 outside nominal band [9.8,11.0] (speed=6.85 m/s, elev=50.8 deg)
- [16:11:21] flight_24 N=30: FLAGGED -- |a|=9.35 outside nominal band [9.8,11.0] (speed=6.71 m/s, elev=49.3 deg)
- [16:11:21] flight_25 N=20: FLAGGED -- |a|=13.54 outside nominal band [9.8,11.0] (speed=9.34 m/s, elev=45.9 deg)
- [16:11:21] flight_25 N=30: FLAGGED -- |a|=12.32 outside nominal band [9.8,11.0] (speed=9.10 m/s, elev=46.6 deg)
- [16:11:21] flight_26 N=20: FLAGGED -- |a|=11.63 outside nominal band [9.8,11.0] (speed=7.01 m/s, elev=58.1 deg)
- [16:11:21] flight_26 N=30: FLAGGED -- |a|=9.28 outside nominal band [9.8,11.0] (speed=6.76 m/s, elev=56.9 deg)
- [16:11:21] flight_27 N=20: FLAGGED -- |a|=9.65 outside nominal band [9.8,11.0] (speed=6.80 m/s, elev=46.5 deg)
- [16:11:21] flight_28 N=30: FLAGGED -- |a|=8.93 outside nominal band [9.8,11.0] (speed=6.30 m/s, elev=48.4 deg)
- [16:11:21] flight_29 N=20: FLAGGED -- |a|=11.59 outside nominal band [9.8,11.0] (speed=7.42 m/s, elev=57.5 deg)
- [16:11:21] flight_30 N=20: FLAGGED -- |a|=11.47 outside nominal band [9.8,11.0] (speed=6.51 m/s, elev=61.4 deg)
- [16:11:21] flight_31 N=20: FLAGGED -- |a|=11.24 outside nominal band [9.8,11.0] (speed=6.77 m/s, elev=54.0 deg)
- [16:11:21] flight_33 N=20: SKIPPED -- implausible |a|=26.37 m/s^2 (hard gate [5.0,20.0])
- [16:11:21] flight_33 N=30: FLAGGED -- |a|=13.73 outside nominal band [9.8,11.0] (speed=8.71 m/s, elev=45.5 deg)
- [16:11:21] flight_34 N=30: FLAGGED -- |a|=9.65 outside nominal band [9.8,11.0] (speed=6.68 m/s, elev=55.3 deg)
- [16:11:21] flight_35 N=20: FLAGGED -- |a|=16.93 outside nominal band [9.8,11.0] (speed=8.73 m/s, elev=59.7 deg)
- [16:11:21] flight_35 N=30: FLAGGED -- |a|=11.12 outside nominal band [9.8,11.0] (speed=8.63 m/s, elev=55.0 deg)
- [16:11:21] flight_36 N=20: FLAGGED -- |a|=11.90 outside nominal band [9.8,11.0] (speed=8.17 m/s, elev=49.8 deg)
- [16:11:21] flight_36 N=30: FLAGGED -- |a|=11.24 outside nominal band [9.8,11.0] (speed=8.02 m/s, elev=50.5 deg)
- [16:11:21] flight_37 N=30: FLAGGED -- |a|=11.42 outside nominal band [9.8,11.0] (speed=7.61 m/s, elev=57.2 deg)
- [16:11:21] flight_38 N=20: FLAGGED -- |a|=11.83 outside nominal band [9.8,11.0] (speed=7.96 m/s, elev=65.0 deg)
- [16:11:21] flight_38 N=30: FLAGGED -- |a|=12.09 outside nominal band [9.8,11.0] (speed=7.94 m/s, elev=68.2 deg)
- [16:11:21] flight_39 N=20: FLAGGED -- |a|=9.64 outside nominal band [9.8,11.0] (speed=7.00 m/s, elev=55.1 deg)
- [16:11:21] progress: 40/149 flights processed
- [16:11:21] flight_41 N=20: FLAGGED -- |a|=11.70 outside nominal band [9.8,11.0] (speed=7.72 m/s, elev=55.7 deg)
- [16:11:21] flight_42 N=20: FLAGGED -- gravity crosscheck diff=48.0 deg > 45.0 (speed=6.68 m/s, elev=51.1 deg)
- [16:11:21] flight_43 N=30: FLAGGED -- |a|=11.90 outside nominal band [9.8,11.0] (speed=7.70 m/s, elev=54.4 deg)
- [16:11:21] flight_44 N=20: FLAGGED -- |a|=14.59 outside nominal band [9.8,11.0] (speed=7.15 m/s, elev=54.1 deg)
- [16:11:21] flight_44 N=30: FLAGGED -- |a|=11.05 outside nominal band [9.8,11.0] (speed=6.92 m/s, elev=51.9 deg)
- [16:11:21] flight_45 N=20: FLAGGED -- |a|=14.98 outside nominal band [9.8,11.0] (speed=7.43 m/s, elev=52.0 deg)
- [16:11:21] flight_45 N=30: FLAGGED -- |a|=11.67 outside nominal band [9.8,11.0] (speed=7.43 m/s, elev=48.7 deg)
- [16:11:21] flight_46 N=20: FLAGGED -- |a|=11.27 outside nominal band [9.8,11.0] (speed=6.61 m/s, elev=63.7 deg)
- [16:11:21] flight_46 N=30: FLAGGED -- |a|=11.03 outside nominal band [9.8,11.0] (speed=6.73 m/s, elev=61.5 deg)
- [16:11:21] flight_47 N=20: FLAGGED -- |a|=13.20 outside nominal band [9.8,11.0] (speed=7.56 m/s, elev=56.7 deg)
- [16:11:21] flight_48 N=20: FLAGGED -- |a|=13.72 outside nominal band [9.8,11.0] (speed=8.46 m/s, elev=44.8 deg)
- [16:11:21] flight_48 N=30: FLAGGED -- |a|=12.50 outside nominal band [9.8,11.0] (speed=8.11 m/s, elev=45.9 deg)
- [16:11:21] flight_49 N=20: FLAGGED -- |a|=9.53 outside nominal band [9.8,11.0] (speed=6.97 m/s, elev=48.9 deg)
- [16:11:21] flight_49 N=30: FLAGGED -- |a|=11.18 outside nominal band [9.8,11.0] (speed=7.15 m/s, elev=51.2 deg)
- [16:11:21] flight_50 N=20: FLAGGED -- |a|=11.95 outside nominal band [9.8,11.0] (speed=7.58 m/s, elev=47.2 deg)
- [16:11:21] flight_51 N=20: FLAGGED -- |a|=13.55 outside nominal band [9.8,11.0]; gravity crosscheck diff=59.7 deg > 45.0 (speed=7.68 m/s, elev=49.9 deg)
- [16:11:21] flight_52 N=20: FLAGGED -- |a|=15.07 outside nominal band [9.8,11.0] (speed=8.55 m/s, elev=57.1 deg)
- [16:11:21] flight_52 N=30: FLAGGED -- |a|=13.48 outside nominal band [9.8,11.0] (speed=8.40 m/s, elev=56.4 deg)
- [16:11:21] flight_53 N=20: FLAGGED -- |a|=11.28 outside nominal band [9.8,11.0] (speed=7.15 m/s, elev=53.2 deg)
- [16:11:21] flight_53 N=30: FLAGGED -- |a|=11.19 outside nominal band [9.8,11.0] (speed=7.19 m/s, elev=56.5 deg)
- [16:11:21] flight_54 N=20: FLAGGED -- |a|=12.13 outside nominal band [9.8,11.0] (speed=7.47 m/s, elev=37.8 deg)
- [16:11:21] flight_54 N=30: FLAGGED -- |a|=11.26 outside nominal band [9.8,11.0] (speed=7.34 m/s, elev=37.3 deg)
- [16:11:21] flight_55 N=20: FLAGGED -- |a|=11.77 outside nominal band [9.8,11.0] (speed=7.57 m/s, elev=48.3 deg)
- [16:11:21] flight_55 N=30: FLAGGED -- |a|=11.11 outside nominal band [9.8,11.0] (speed=7.48 m/s, elev=47.9 deg)
- [16:11:21] flight_57 N=20: FLAGGED -- |a|=9.67 outside nominal band [9.8,11.0] (speed=6.39 m/s, elev=53.2 deg)
- [16:11:21] flight_58 N=20: FLAGGED -- |a|=15.04 outside nominal band [9.8,11.0] (speed=7.42 m/s, elev=62.1 deg)
- [16:11:21] flight_59 N=30: FLAGGED -- |a|=8.59 outside nominal band [9.8,11.0] (speed=7.08 m/s, elev=59.9 deg)
- [16:11:21] progress: 60/149 flights processed
- [16:11:21] flight_61 N=20: FLAGGED -- gravity crosscheck diff=48.4 deg > 45.0 (speed=7.61 m/s, elev=2.8 deg)
- [16:11:21] flight_61 N=30: FLAGGED -- |a|=8.77 outside nominal band [9.8,11.0] (speed=7.31 m/s, elev=3.7 deg)
- [16:11:21] flight_62 N=20: FLAGGED -- |a|=9.73 outside nominal band [9.8,11.0] (speed=9.26 m/s, elev=8.2 deg)
- [16:11:21] flight_63 N=20: FLAGGED -- |a|=15.31 outside nominal band [9.8,11.0]; gravity crosscheck diff=56.3 deg > 45.0 (speed=9.85 m/s, elev=3.9 deg)
- [16:11:21] flight_63 N=30: FLAGGED -- |a|=9.71 outside nominal band [9.8,11.0] (speed=9.02 m/s, elev=4.4 deg)
- [16:11:21] flight_64 N=20: FLAGGED -- |a|=8.55 outside nominal band [9.8,11.0] (speed=7.39 m/s, elev=12.1 deg)
- [16:11:21] flight_64 N=30: FLAGGED -- |a|=9.29 outside nominal band [9.8,11.0] (speed=7.51 m/s, elev=12.7 deg)
- [16:11:21] flight_65 N=20: FLAGGED -- |a|=8.39 outside nominal band [9.8,11.0] (speed=6.72 m/s, elev=8.7 deg)
- [16:11:21] flight_65 N=30: FLAGGED -- |a|=9.39 outside nominal band [9.8,11.0] (speed=6.74 m/s, elev=9.2 deg)
- [16:11:21] flight_66 N=20: FLAGGED -- |a|=8.58 outside nominal band [9.8,11.0] (speed=7.54 m/s, elev=-1.0 deg)
- [16:11:21] flight_66 N=30: FLAGGED -- |a|=7.87 outside nominal band [9.8,11.0] (speed=7.43 m/s, elev=-1.4 deg)
- [16:11:21] flight_67 N=30: FLAGGED -- adjusted from 30 -> 27, flight has fewer usable frames (speed=8.62 m/s, elev=-8.8 deg)
- [16:11:21] flight_68 N=30: FLAGGED -- |a|=9.45 outside nominal band [9.8,11.0] (speed=8.33 m/s, elev=11.6 deg)
- [16:11:21] flight_70 N=20: FLAGGED -- |a|=12.64 outside nominal band [9.8,11.0] (speed=8.93 m/s, elev=3.8 deg)
- [16:11:21] flight_70 N=30: FLAGGED -- |a|=9.56 outside nominal band [9.8,11.0] (speed=9.17 m/s, elev=2.0 deg)
- [16:11:21] flight_71 N=20: FLAGGED -- |a|=9.76 outside nominal band [9.8,11.0] (speed=7.33 m/s, elev=-10.6 deg)
- [16:11:21] flight_71 N=30: FLAGGED -- |a|=9.45 outside nominal band [9.8,11.0]; adjusted from 30 -> 27, flight has fewer usable frames (speed=7.28 m/s, elev=-9.8 deg)
- [16:11:21] flight_72 N=20: FLAGGED -- |a|=15.01 outside nominal band [9.8,11.0]; gravity crosscheck diff=60.6 deg > 45.0 (speed=9.17 m/s, elev=2.9 deg)
- [16:11:21] flight_72 N=30: FLAGGED -- |a|=9.50 outside nominal band [9.8,11.0] (speed=8.51 m/s, elev=4.4 deg)
- [16:11:21] flight_74 N=20: FLAGGED -- |a|=13.67 outside nominal band [9.8,11.0] (speed=8.76 m/s, elev=13.5 deg)
- [16:11:21] flight_75 N=20: FLAGGED -- |a|=8.06 outside nominal band [9.8,11.0] (speed=7.61 m/s, elev=5.9 deg)
- [16:11:21] flight_75 N=30: FLAGGED -- |a|=8.52 outside nominal band [9.8,11.0] (speed=7.34 m/s, elev=8.1 deg)
- [16:11:21] flight_76 N=20: FLAGGED -- |a|=15.82 outside nominal band [9.8,11.0]; gravity crosscheck diff=47.4 deg > 45.0 (speed=7.35 m/s, elev=14.6 deg)
- [16:11:21] flight_77 N=30: FLAGGED -- |a|=9.26 outside nominal band [9.8,11.0] (speed=7.99 m/s, elev=7.6 deg)
- [16:11:21] flight_79 N=20: FLAGGED -- |a|=8.71 outside nominal band [9.8,11.0] (speed=9.79 m/s, elev=-3.3 deg)
- [16:11:21] flight_79 N=30: FLAGGED -- |a|=8.49 outside nominal band [9.8,11.0] (speed=9.65 m/s, elev=-3.2 deg)
- [16:11:21] flight_80 N=20: FLAGGED -- |a|=7.36 outside nominal band [9.8,11.0] (speed=8.63 m/s, elev=-6.8 deg)
- [16:11:21] flight_80 N=30: FLAGGED -- |a|=8.37 outside nominal band [9.8,11.0]; adjusted from 30 -> 28, flight has fewer usable frames (speed=8.82 m/s, elev=-6.7 deg)
- [16:11:21] progress: 80/149 flights processed
- [16:11:21] flight_81 N=20: FLAGGED -- |a|=8.10 outside nominal band [9.8,11.0] (speed=9.94 m/s, elev=-6.7 deg)
- [16:11:21] flight_81 N=30: FLAGGED -- |a|=9.44 outside nominal band [9.8,11.0] (speed=9.83 m/s, elev=-5.1 deg)
- [16:11:21] flight_82 N=20: FLAGGED -- |a|=9.20 outside nominal band [9.8,11.0] (speed=9.44 m/s, elev=-0.5 deg)
- [16:11:21] flight_82 N=30: FLAGGED -- |a|=9.33 outside nominal band [9.8,11.0] (speed=9.69 m/s, elev=-0.6 deg)
- [16:11:21] flight_83 N=20: FLAGGED -- |a|=11.24 outside nominal band [9.8,11.0] (speed=9.37 m/s, elev=4.8 deg)
- [16:11:21] flight_84 N=20: FLAGGED -- |a|=9.61 outside nominal band [9.8,11.0] (speed=10.45 m/s, elev=-9.9 deg)
- [16:11:21] flight_84 N=30: FLAGGED -- adjusted from 30 -> 26, flight has fewer usable frames (speed=10.46 m/s, elev=-9.3 deg)
- [16:11:21] flight_85 N=20: FLAGGED -- |a|=11.52 outside nominal band [9.8,11.0] (speed=9.61 m/s, elev=7.8 deg)
- [16:11:21] flight_86 N=30: FLAGGED -- |a|=9.24 outside nominal band [9.8,11.0] (speed=9.87 m/s, elev=-2.8 deg)
- [16:11:21] flight_87 N=30: FLAGGED -- |a|=9.74 outside nominal band [9.8,11.0] (speed=9.51 m/s, elev=4.3 deg)
- [16:11:21] flight_88 N=20: FLAGGED -- |a|=11.31 outside nominal band [9.8,11.0] (speed=9.50 m/s, elev=10.1 deg)
- [16:11:21] flight_89 N=30: FLAGGED -- |a|=11.18 outside nominal band [9.8,11.0]; adjusted from 30 -> 23, flight has fewer usable frames (speed=10.04 m/s, elev=-10.3 deg)
- [16:11:21] flight_90 N=20: FLAGGED -- |a|=8.70 outside nominal band [9.8,11.0] (speed=8.22 m/s, elev=7.0 deg)
- [16:11:21] flight_90 N=30: FLAGGED -- |a|=9.51 outside nominal band [9.8,11.0] (speed=8.23 m/s, elev=8.2 deg)
- [16:11:21] flight_92 N=20: FLAGGED -- |a|=11.07 outside nominal band [9.8,11.0] (speed=6.89 m/s, elev=50.4 deg)
- [16:11:21] flight_92 N=30: FLAGGED -- |a|=9.77 outside nominal band [9.8,11.0] (speed=6.91 m/s, elev=47.8 deg)
- [16:11:21] flight_93 N=20: FLAGGED -- |a|=17.82 outside nominal band [9.8,11.0] (speed=7.56 m/s, elev=53.1 deg)
- [16:11:21] flight_95 N=20: FLAGGED -- |a|=11.45 outside nominal band [9.8,11.0] (speed=7.78 m/s, elev=54.1 deg)
- [16:11:21] flight_96 N=20: FLAGGED -- |a|=8.37 outside nominal band [9.8,11.0] (speed=6.45 m/s, elev=46.9 deg)
- [16:11:21] flight_96 N=30: FLAGGED -- |a|=9.22 outside nominal band [9.8,11.0] (speed=6.58 m/s, elev=49.0 deg)
- [16:11:21] flight_98 N=20: FLAGGED -- |a|=11.44 outside nominal band [9.8,11.0] (speed=7.25 m/s, elev=53.1 deg)
- [16:11:21] flight_99 N=20: FLAGGED -- |a|=11.21 outside nominal band [9.8,11.0]; gravity crosscheck diff=50.8 deg > 45.0 (speed=6.47 m/s, elev=50.2 deg)
- [16:11:21] flight_100 N=20: FLAGGED -- |a|=8.21 outside nominal band [9.8,11.0] (speed=7.15 m/s, elev=50.1 deg)
- [16:11:21] flight_100 N=30: FLAGGED -- |a|=9.08 outside nominal band [9.8,11.0] (speed=7.22 m/s, elev=50.2 deg)
- [16:11:21] progress: 100/149 flights processed
- [16:11:21] flight_101 N=20: FLAGGED -- |a|=14.25 outside nominal band [9.8,11.0] (speed=6.01 m/s, elev=53.5 deg)
- [16:11:21] flight_101 N=30: FLAGGED -- |a|=11.29 outside nominal band [9.8,11.0] (speed=6.03 m/s, elev=52.1 deg)
- [16:11:21] flight_102 N=20: FLAGGED -- |a|=11.19 outside nominal band [9.8,11.0] (speed=6.79 m/s, elev=51.6 deg)
- [16:11:21] flight_104 N=30: FLAGGED -- |a|=9.14 outside nominal band [9.8,11.0] (speed=6.83 m/s, elev=55.2 deg)
- [16:11:21] flight_105 N=20: FLAGGED -- |a|=13.02 outside nominal band [9.8,11.0] (speed=7.66 m/s, elev=57.4 deg)
- [16:11:21] flight_106 N=20: FLAGGED -- |a|=15.24 outside nominal band [9.8,11.0] (speed=7.52 m/s, elev=59.9 deg)
- [16:11:21] flight_106 N=30: FLAGGED -- |a|=9.48 outside nominal band [9.8,11.0] (speed=7.16 m/s, elev=56.9 deg)
- [16:11:21] flight_107 N=20: FLAGGED -- |a|=14.41 outside nominal band [9.8,11.0] (speed=7.28 m/s, elev=54.4 deg)
- [16:11:21] flight_108 N=20: FLAGGED -- |a|=11.90 outside nominal band [9.8,11.0] (speed=6.69 m/s, elev=55.9 deg)
- [16:11:21] flight_109 N=20: FLAGGED -- |a|=8.87 outside nominal band [9.8,11.0] (speed=7.05 m/s, elev=51.2 deg)
- [16:11:21] flight_110 N=20: FLAGGED -- |a|=11.57 outside nominal band [9.8,11.0] (speed=7.42 m/s, elev=46.5 deg)
- [16:11:21] flight_110 N=30: FLAGGED -- |a|=11.35 outside nominal band [9.8,11.0] (speed=7.40 m/s, elev=46.3 deg)
- [16:11:21] flight_111 N=20: FLAGGED -- |a|=17.27 outside nominal band [9.8,11.0] (speed=7.00 m/s, elev=55.6 deg)
- [16:11:21] flight_111 N=30: FLAGGED -- |a|=11.76 outside nominal band [9.8,11.0] (speed=6.95 m/s, elev=53.3 deg)
- [16:11:21] flight_112 N=20: FLAGGED -- |a|=17.24 outside nominal band [9.8,11.0]; gravity crosscheck diff=46.4 deg > 45.0 (speed=6.77 m/s, elev=54.9 deg)
- [16:11:21] flight_112 N=30: FLAGGED -- |a|=11.47 outside nominal band [9.8,11.0] (speed=6.74 m/s, elev=52.6 deg)
- [16:11:21] flight_113 N=20: FLAGGED -- |a|=12.30 outside nominal band [9.8,11.0] (speed=7.31 m/s, elev=45.8 deg)
- [16:11:21] flight_113 N=30: FLAGGED -- |a|=11.12 outside nominal band [9.8,11.0] (speed=7.30 m/s, elev=41.8 deg)
- [16:11:21] flight_114 N=20: FLAGGED -- |a|=12.28 outside nominal band [9.8,11.0] (speed=6.76 m/s, elev=51.8 deg)
- [16:11:21] flight_114 N=30: FLAGGED -- |a|=11.35 outside nominal band [9.8,11.0] (speed=6.69 m/s, elev=50.4 deg)
- [16:11:21] flight_116 N=20: FLAGGED -- |a|=13.21 outside nominal band [9.8,11.0] (speed=6.62 m/s, elev=60.5 deg)
- [16:11:21] flight_117 N=20: FLAGGED -- |a|=11.77 outside nominal band [9.8,11.0] (speed=6.56 m/s, elev=52.7 deg)
- [16:11:21] flight_118 N=20: FLAGGED -- |a|=11.47 outside nominal band [9.8,11.0] (speed=6.53 m/s, elev=41.9 deg)
- [16:11:21] progress: 120/149 flights processed
- [16:11:21] flight_121 N=20: FLAGGED -- |a|=14.38 outside nominal band [9.8,11.0] (speed=8.06 m/s, elev=56.0 deg)
- [16:11:21] flight_121 N=30: FLAGGED -- |a|=11.60 outside nominal band [9.8,11.0] (speed=8.04 m/s, elev=52.0 deg)
- [16:11:21] flight_122 N=20: FLAGGED -- |a|=11.61 outside nominal band [9.8,11.0] (speed=7.50 m/s, elev=59.3 deg)
- [16:11:21] flight_122 N=30: FLAGGED -- |a|=11.23 outside nominal band [9.8,11.0] (speed=7.59 m/s, elev=58.8 deg)
- [16:11:21] flight_123 N=20: FLAGGED -- |a|=11.56 outside nominal band [9.8,11.0] (speed=7.18 m/s, elev=53.3 deg)
- [16:11:21] flight_124 N=20: FLAGGED -- |a|=15.54 outside nominal band [9.8,11.0] (speed=7.65 m/s, elev=53.5 deg)
- [16:11:21] flight_124 N=30: FLAGGED -- |a|=13.01 outside nominal band [9.8,11.0] (speed=7.59 m/s, elev=51.4 deg)
- [16:11:21] flight_125 N=20: FLAGGED -- |a|=14.76 outside nominal band [9.8,11.0] (speed=7.72 m/s, elev=51.2 deg)
- [16:11:21] flight_125 N=30: FLAGGED -- |a|=12.08 outside nominal band [9.8,11.0] (speed=7.61 m/s, elev=48.5 deg)
- [16:11:21] flight_126 N=20: FLAGGED -- |a|=12.19 outside nominal band [9.8,11.0] (speed=7.13 m/s, elev=54.5 deg)
- [16:11:21] flight_127: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_128: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_129: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_130: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_131: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_132: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_133: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_134: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_135: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_136: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_137: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_138: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_139: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_140: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] progress: 140/149 flights processed
- [16:11:21] flight_141: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_142: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_143: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_144: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_145: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_146: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_147: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_148: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] flight_149: SKIPPED (both N) -- missing tuned-detector detections csv
- [16:11:21] batch loop complete: 149 flights processed, 298 rows written
- [16:11:21] wrote CSV -> C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\2026_07_21_gym\flight_binning\flight_velocity_angle.csv (298 rows)
- [16:11:21] summary: 251 ok rows, 47 skipped rows, 168 flagged (of the ok rows), out of 298 total attempted rows
- [16:11:21] plotted distribution_N20.png (125 points, 94 flagged)
- [16:11:21] plotted distribution_N30.png (126 points, 74 flagged)
- [16:11:21] plotted distribution_overlay_histograms.png
- [16:11:23] plotted distribution_N_sensitivity.png
- [16:11:23] === flight_velocity_angle_binner.py: batch run complete ===
- [20:41:51] === flight_velocity_angle_binner.py: batch run starting (multi-session) ===
- [20:41:51] --- session 2026_07_21_gym ---
- [20:41:51] 2026_07_21_gym: loaded world transform(s): registration1 from img_0031, registration2 from img_0034
- [20:41:51] 2026_07_21_gym: 126 flights with tuned-detector detection CSVs
- [20:41:51] 2026_07_21_gym/flight_1 N=20: FLAGGED -- |a|=14.61 outside nominal band [9.8,11.0] (speed=8.24 m/s, elev=59.6 deg)
- [20:41:51] 2026_07_21_gym/flight_2 N=20: FLAGGED -- |a|=9.20 outside nominal band [9.8,11.0] (speed=8.77 m/s, elev=-7.2 deg)
- [20:41:51] 2026_07_21_gym/flight_2 N=30: FLAGGED -- |a|=9.13 outside nominal band [9.8,11.0] (speed=8.85 m/s, elev=-6.0 deg)
- [20:41:51] 2026_07_21_gym/flight_3 N=30: FLAGGED -- |a|=9.29 outside nominal band [9.8,11.0] (speed=9.95 m/s, elev=5.3 deg)
- [20:41:51] 2026_07_21_gym/flight_4 N=20: FLAGGED -- |a|=11.37 outside nominal band [9.8,11.0]; gravity crosscheck diff=49.7 deg > 45.0 (speed=8.25 m/s, elev=-5.1 deg)
- [20:41:51] 2026_07_21_gym/flight_4 N=30: FLAGGED -- |a|=8.86 outside nominal band [9.8,11.0] (speed=7.94 m/s, elev=-4.9 deg)
- [20:41:51] 2026_07_21_gym/flight_5 N=30: FLAGGED -- |a|=9.43 outside nominal band [9.8,11.0] (speed=8.05 m/s, elev=-1.1 deg)
- [20:41:51] 2026_07_21_gym/flight_6 N=20: FLAGGED -- |a|=15.52 outside nominal band [9.8,11.0] (speed=8.28 m/s, elev=8.3 deg)
- [20:41:51] 2026_07_21_gym/flight_7 N=20: FLAGGED -- |a|=11.80 outside nominal band [9.8,11.0] (speed=7.95 m/s, elev=-10.0 deg)
- [20:41:51] 2026_07_21_gym/flight_7 N=30: FLAGGED -- |a|=9.60 outside nominal band [9.8,11.0]; adjusted from 30 -> 28, flight has fewer usable frames (speed=7.93 m/s, elev=-9.9 deg)
- [20:41:51] 2026_07_21_gym/flight_8 N=30: FLAGGED -- |a|=9.24 outside nominal band [9.8,11.0] (speed=8.10 m/s, elev=-2.8 deg)
- [20:41:51] 2026_07_21_gym/flight_9 N=30: FLAGGED -- |a|=9.30 outside nominal band [9.8,11.0] (speed=8.73 m/s, elev=3.7 deg)
- [20:41:51] 2026_07_21_gym/flight_10 N=20: FLAGGED -- |a|=9.52 outside nominal band [9.8,11.0] (speed=8.65 m/s, elev=-3.3 deg)
- [20:41:51] 2026_07_21_gym/flight_10 N=30: FLAGGED -- |a|=8.91 outside nominal band [9.8,11.0] (speed=8.54 m/s, elev=-3.7 deg)
- [20:41:51] 2026_07_21_gym/flight_11 N=20: FLAGGED -- |a|=9.76 outside nominal band [9.8,11.0] (speed=6.47 m/s, elev=22.7 deg)
- [20:41:51] 2026_07_21_gym/flight_12 N=20: FLAGGED -- |a|=9.32 outside nominal band [9.8,11.0] (speed=8.32 m/s, elev=4.6 deg)
- [20:41:51] 2026_07_21_gym/flight_12 N=30: FLAGGED -- |a|=9.04 outside nominal band [9.8,11.0] (speed=8.31 m/s, elev=4.2 deg)
- [20:41:51] 2026_07_21_gym/flight_13 N=20: FLAGGED -- |a|=11.83 outside nominal band [9.8,11.0] (speed=8.15 m/s, elev=9.4 deg)
- [20:41:51] 2026_07_21_gym/flight_13 N=30: FLAGGED -- |a|=9.67 outside nominal band [9.8,11.0] (speed=8.36 m/s, elev=9.2 deg)
- [20:41:51] 2026_07_21_gym/flight_14 N=20: FLAGGED -- |a|=9.56 outside nominal band [9.8,11.0] (speed=8.02 m/s, elev=2.3 deg)
- [20:41:51] 2026_07_21_gym/flight_14 N=30: FLAGGED -- |a|=9.44 outside nominal band [9.8,11.0] (speed=8.18 m/s, elev=1.8 deg)
- [20:41:51] 2026_07_21_gym/flight_15 N=20: FLAGGED -- |a|=11.06 outside nominal band [9.8,11.0] (speed=8.54 m/s, elev=17.3 deg)
- [20:41:51] 2026_07_21_gym/flight_16 N=20: FLAGGED -- |a|=9.64 outside nominal band [9.8,11.0] (speed=9.02 m/s, elev=-1.1 deg)
- [20:41:51] 2026_07_21_gym/flight_16 N=30: FLAGGED -- |a|=9.35 outside nominal band [9.8,11.0] (speed=9.02 m/s, elev=-1.4 deg)
- [20:41:51] 2026_07_21_gym/flight_17 N=20: FLAGGED -- |a|=11.76 outside nominal band [9.8,11.0]; adjusted from 20 -> 19, flight has fewer usable frames (speed=10.12 m/s, elev=-17.5 deg)
- [20:41:51] 2026_07_21_gym/flight_17 N=30: FLAGGED -- |a|=11.76 outside nominal band [9.8,11.0]; adjusted from 30 -> 19, flight has fewer usable frames (speed=10.12 m/s, elev=-17.5 deg)
- [20:41:51] 2026_07_21_gym/flight_18 N=20: FLAGGED -- |a|=11.47 outside nominal band [9.8,11.0] (speed=6.17 m/s, elev=33.3 deg)
- [20:41:51] 2026_07_21_gym/flight_18 N=30: FLAGGED -- |a|=9.53 outside nominal band [9.8,11.0] (speed=6.37 m/s, elev=29.2 deg)
- [20:41:51] 2026_07_21_gym/flight_19 N=20: FLAGGED -- |a|=11.45 outside nominal band [9.8,11.0]; gravity crosscheck diff=53.8 deg > 45.0 (speed=6.90 m/s, elev=20.0 deg)
- [20:41:51] 2026_07_21_gym/flight_20 N=20: FLAGGED -- |a|=9.77 outside nominal band [9.8,11.0] (speed=7.55 m/s, elev=11.4 deg)
- [20:41:51] 2026_07_21_gym/flight_20 N=30: FLAGGED -- |a|=9.12 outside nominal band [9.8,11.0] (speed=7.64 m/s, elev=11.3 deg)
- [20:41:51] 2026_07_21_gym: progress 20/126 flights processed
- [20:41:51] 2026_07_21_gym/flight_21 N=20: FLAGGED -- |a|=8.71 outside nominal band [9.8,11.0] (speed=7.14 m/s, elev=51.4 deg)
- [20:41:51] 2026_07_21_gym/flight_21 N=30: FLAGGED -- |a|=9.55 outside nominal band [9.8,11.0] (speed=7.26 m/s, elev=51.4 deg)
- [20:41:51] 2026_07_21_gym/flight_22 N=20: FLAGGED -- |a|=14.66 outside nominal band [9.8,11.0] (speed=7.66 m/s, elev=51.4 deg)
- [20:41:51] 2026_07_21_gym/flight_22 N=30: FLAGGED -- |a|=11.47 outside nominal band [9.8,11.0] (speed=7.48 m/s, elev=49.6 deg)
- [20:41:51] 2026_07_21_gym/flight_24 N=20: FLAGGED -- |a|=11.10 outside nominal band [9.8,11.0] (speed=6.85 m/s, elev=50.8 deg)
- [20:41:51] 2026_07_21_gym/flight_24 N=30: FLAGGED -- |a|=9.35 outside nominal band [9.8,11.0] (speed=6.71 m/s, elev=49.3 deg)
- [20:41:51] 2026_07_21_gym/flight_25 N=20: FLAGGED -- |a|=13.54 outside nominal band [9.8,11.0] (speed=9.34 m/s, elev=45.9 deg)
- [20:41:51] 2026_07_21_gym/flight_25 N=30: FLAGGED -- |a|=12.32 outside nominal band [9.8,11.0] (speed=9.10 m/s, elev=46.6 deg)
- [20:41:51] 2026_07_21_gym/flight_26 N=20: FLAGGED -- |a|=11.63 outside nominal band [9.8,11.0] (speed=7.01 m/s, elev=58.1 deg)
- [20:41:51] 2026_07_21_gym/flight_26 N=30: FLAGGED -- |a|=9.28 outside nominal band [9.8,11.0] (speed=6.76 m/s, elev=56.9 deg)
- [20:41:51] 2026_07_21_gym/flight_27 N=20: FLAGGED -- |a|=9.65 outside nominal band [9.8,11.0] (speed=6.80 m/s, elev=46.5 deg)
- [20:41:51] 2026_07_21_gym/flight_28 N=30: FLAGGED -- |a|=8.93 outside nominal band [9.8,11.0] (speed=6.30 m/s, elev=48.4 deg)
- [20:41:51] 2026_07_21_gym/flight_29 N=20: FLAGGED -- |a|=11.59 outside nominal band [9.8,11.0] (speed=7.42 m/s, elev=57.5 deg)
- [20:41:51] 2026_07_21_gym/flight_30 N=20: FLAGGED -- |a|=11.47 outside nominal band [9.8,11.0] (speed=6.51 m/s, elev=61.4 deg)
- [20:41:51] 2026_07_21_gym/flight_31 N=20: FLAGGED -- |a|=11.24 outside nominal band [9.8,11.0] (speed=6.77 m/s, elev=54.0 deg)
- [20:41:51] 2026_07_21_gym/flight_33 N=20: SKIPPED -- implausible |a|=26.37 m/s^2 (hard gate [5.0,20.0])
- [20:41:51] 2026_07_21_gym/flight_33 N=30: FLAGGED -- |a|=13.73 outside nominal band [9.8,11.0] (speed=8.71 m/s, elev=45.5 deg)
- [20:41:51] 2026_07_21_gym/flight_34 N=30: FLAGGED -- |a|=9.65 outside nominal band [9.8,11.0] (speed=6.68 m/s, elev=55.3 deg)
- [20:41:51] 2026_07_21_gym/flight_35 N=20: FLAGGED -- |a|=16.93 outside nominal band [9.8,11.0] (speed=8.73 m/s, elev=59.7 deg)
- [20:41:51] 2026_07_21_gym/flight_35 N=30: FLAGGED -- |a|=11.12 outside nominal band [9.8,11.0] (speed=8.63 m/s, elev=55.0 deg)
- [20:41:51] 2026_07_21_gym/flight_36 N=20: FLAGGED -- |a|=11.90 outside nominal band [9.8,11.0] (speed=8.17 m/s, elev=49.8 deg)
- [20:41:51] 2026_07_21_gym/flight_36 N=30: FLAGGED -- |a|=11.24 outside nominal band [9.8,11.0] (speed=8.02 m/s, elev=50.5 deg)
- [20:41:51] 2026_07_21_gym/flight_37 N=30: FLAGGED -- |a|=11.42 outside nominal band [9.8,11.0] (speed=7.61 m/s, elev=57.2 deg)
- [20:41:51] 2026_07_21_gym/flight_38 N=20: FLAGGED -- |a|=11.83 outside nominal band [9.8,11.0] (speed=7.96 m/s, elev=65.0 deg)
- [20:41:51] 2026_07_21_gym/flight_38 N=30: FLAGGED -- |a|=12.09 outside nominal band [9.8,11.0] (speed=7.94 m/s, elev=68.2 deg)
- [20:41:51] 2026_07_21_gym/flight_39 N=20: FLAGGED -- |a|=9.64 outside nominal band [9.8,11.0] (speed=7.00 m/s, elev=55.1 deg)
- [20:41:51] 2026_07_21_gym: progress 40/126 flights processed
- [20:41:51] 2026_07_21_gym/flight_41 N=20: FLAGGED -- |a|=11.70 outside nominal band [9.8,11.0] (speed=7.72 m/s, elev=55.7 deg)
- [20:41:51] 2026_07_21_gym/flight_42 N=20: FLAGGED -- gravity crosscheck diff=48.0 deg > 45.0 (speed=6.68 m/s, elev=51.1 deg)
- [20:41:51] 2026_07_21_gym/flight_43 N=30: FLAGGED -- |a|=11.90 outside nominal band [9.8,11.0] (speed=7.70 m/s, elev=54.4 deg)
- [20:41:51] 2026_07_21_gym/flight_44 N=20: FLAGGED -- |a|=14.59 outside nominal band [9.8,11.0] (speed=7.15 m/s, elev=54.1 deg)
- [20:41:51] 2026_07_21_gym/flight_44 N=30: FLAGGED -- |a|=11.05 outside nominal band [9.8,11.0] (speed=6.92 m/s, elev=51.9 deg)
- [20:41:51] 2026_07_21_gym/flight_45 N=20: FLAGGED -- |a|=14.98 outside nominal band [9.8,11.0] (speed=7.43 m/s, elev=52.0 deg)
- [20:41:51] 2026_07_21_gym/flight_45 N=30: FLAGGED -- |a|=11.67 outside nominal band [9.8,11.0] (speed=7.43 m/s, elev=48.7 deg)
- [20:41:51] 2026_07_21_gym/flight_46 N=20: FLAGGED -- |a|=11.27 outside nominal band [9.8,11.0] (speed=6.61 m/s, elev=63.7 deg)
- [20:41:51] 2026_07_21_gym/flight_46 N=30: FLAGGED -- |a|=11.03 outside nominal band [9.8,11.0] (speed=6.73 m/s, elev=61.5 deg)
- [20:41:51] 2026_07_21_gym/flight_47 N=20: FLAGGED -- |a|=13.20 outside nominal band [9.8,11.0] (speed=7.56 m/s, elev=56.7 deg)
- [20:41:51] 2026_07_21_gym/flight_48 N=20: FLAGGED -- |a|=13.72 outside nominal band [9.8,11.0] (speed=8.46 m/s, elev=44.8 deg)
- [20:41:51] 2026_07_21_gym/flight_48 N=30: FLAGGED -- |a|=12.50 outside nominal band [9.8,11.0] (speed=8.11 m/s, elev=45.9 deg)
- [20:41:52] 2026_07_21_gym/flight_49 N=20: FLAGGED -- |a|=9.53 outside nominal band [9.8,11.0] (speed=6.97 m/s, elev=48.9 deg)
- [20:41:52] 2026_07_21_gym/flight_49 N=30: FLAGGED -- |a|=11.18 outside nominal band [9.8,11.0] (speed=7.15 m/s, elev=51.2 deg)
- [20:41:52] 2026_07_21_gym/flight_50 N=20: FLAGGED -- |a|=11.95 outside nominal band [9.8,11.0] (speed=7.58 m/s, elev=47.2 deg)
- [20:41:52] 2026_07_21_gym/flight_51 N=20: FLAGGED -- |a|=13.55 outside nominal band [9.8,11.0]; gravity crosscheck diff=59.7 deg > 45.0 (speed=7.68 m/s, elev=49.9 deg)
- [20:41:52] 2026_07_21_gym/flight_52 N=20: FLAGGED -- |a|=15.07 outside nominal band [9.8,11.0] (speed=8.55 m/s, elev=57.1 deg)
- [20:41:52] 2026_07_21_gym/flight_52 N=30: FLAGGED -- |a|=13.48 outside nominal band [9.8,11.0] (speed=8.40 m/s, elev=56.4 deg)
- [20:41:52] 2026_07_21_gym/flight_53 N=20: FLAGGED -- |a|=11.28 outside nominal band [9.8,11.0] (speed=7.15 m/s, elev=53.2 deg)
- [20:41:52] 2026_07_21_gym/flight_53 N=30: FLAGGED -- |a|=11.19 outside nominal band [9.8,11.0] (speed=7.19 m/s, elev=56.5 deg)
- [20:41:52] 2026_07_21_gym/flight_54 N=20: FLAGGED -- |a|=12.13 outside nominal band [9.8,11.0] (speed=7.47 m/s, elev=37.8 deg)
- [20:41:52] 2026_07_21_gym/flight_54 N=30: FLAGGED -- |a|=11.26 outside nominal band [9.8,11.0] (speed=7.34 m/s, elev=37.3 deg)
- [20:41:52] 2026_07_21_gym/flight_55 N=20: FLAGGED -- |a|=11.77 outside nominal band [9.8,11.0] (speed=7.57 m/s, elev=48.3 deg)
- [20:41:52] 2026_07_21_gym/flight_55 N=30: FLAGGED -- |a|=11.11 outside nominal band [9.8,11.0] (speed=7.48 m/s, elev=47.9 deg)
- [20:41:52] 2026_07_21_gym/flight_57 N=20: FLAGGED -- |a|=9.67 outside nominal band [9.8,11.0] (speed=6.39 m/s, elev=53.2 deg)
- [20:41:52] 2026_07_21_gym/flight_58 N=20: FLAGGED -- |a|=15.04 outside nominal band [9.8,11.0] (speed=7.42 m/s, elev=62.1 deg)
- [20:41:52] 2026_07_21_gym/flight_59 N=30: FLAGGED -- |a|=8.59 outside nominal band [9.8,11.0] (speed=7.08 m/s, elev=59.9 deg)
- [20:41:52] 2026_07_21_gym: progress 60/126 flights processed
- [20:41:52] 2026_07_21_gym/flight_61 N=20: FLAGGED -- gravity crosscheck diff=48.4 deg > 45.0 (speed=7.61 m/s, elev=2.8 deg)
- [20:41:52] 2026_07_21_gym/flight_61 N=30: FLAGGED -- |a|=8.77 outside nominal band [9.8,11.0] (speed=7.31 m/s, elev=3.7 deg)
- [20:41:52] 2026_07_21_gym/flight_62 N=20: FLAGGED -- |a|=9.73 outside nominal band [9.8,11.0] (speed=9.26 m/s, elev=8.2 deg)
- [20:41:52] 2026_07_21_gym/flight_63 N=20: FLAGGED -- |a|=15.31 outside nominal band [9.8,11.0]; gravity crosscheck diff=56.3 deg > 45.0 (speed=9.85 m/s, elev=3.9 deg)
- [20:41:52] 2026_07_21_gym/flight_63 N=30: FLAGGED -- |a|=9.71 outside nominal band [9.8,11.0] (speed=9.02 m/s, elev=4.4 deg)
- [20:41:52] 2026_07_21_gym/flight_64 N=20: FLAGGED -- |a|=8.55 outside nominal band [9.8,11.0] (speed=7.39 m/s, elev=12.1 deg)
- [20:41:52] 2026_07_21_gym/flight_64 N=30: FLAGGED -- |a|=9.29 outside nominal band [9.8,11.0] (speed=7.51 m/s, elev=12.7 deg)
- [20:41:52] 2026_07_21_gym/flight_65 N=20: FLAGGED -- |a|=8.39 outside nominal band [9.8,11.0] (speed=6.72 m/s, elev=8.7 deg)
- [20:41:52] 2026_07_21_gym/flight_65 N=30: FLAGGED -- |a|=9.39 outside nominal band [9.8,11.0] (speed=6.74 m/s, elev=9.2 deg)
- [20:41:52] 2026_07_21_gym/flight_66 N=20: FLAGGED -- |a|=8.58 outside nominal band [9.8,11.0] (speed=7.54 m/s, elev=-1.0 deg)
- [20:41:52] 2026_07_21_gym/flight_66 N=30: FLAGGED -- |a|=7.87 outside nominal band [9.8,11.0] (speed=7.43 m/s, elev=-1.4 deg)
- [20:41:52] 2026_07_21_gym/flight_67 N=30: FLAGGED -- adjusted from 30 -> 27, flight has fewer usable frames (speed=8.62 m/s, elev=-8.8 deg)
- [20:41:52] 2026_07_21_gym/flight_68 N=30: FLAGGED -- |a|=9.45 outside nominal band [9.8,11.0] (speed=8.33 m/s, elev=11.6 deg)
- [20:41:52] 2026_07_21_gym/flight_70 N=20: FLAGGED -- |a|=12.64 outside nominal band [9.8,11.0] (speed=8.93 m/s, elev=3.8 deg)
- [20:41:52] 2026_07_21_gym/flight_70 N=30: FLAGGED -- |a|=9.56 outside nominal band [9.8,11.0] (speed=9.17 m/s, elev=2.0 deg)
- [20:41:52] 2026_07_21_gym/flight_71 N=20: FLAGGED -- |a|=9.76 outside nominal band [9.8,11.0] (speed=7.33 m/s, elev=-10.6 deg)
- [20:41:52] 2026_07_21_gym/flight_71 N=30: FLAGGED -- |a|=9.45 outside nominal band [9.8,11.0]; adjusted from 30 -> 27, flight has fewer usable frames (speed=7.28 m/s, elev=-9.8 deg)
- [20:41:52] 2026_07_21_gym/flight_72 N=20: FLAGGED -- |a|=15.01 outside nominal band [9.8,11.0]; gravity crosscheck diff=60.6 deg > 45.0 (speed=9.17 m/s, elev=2.9 deg)
- [20:41:52] 2026_07_21_gym/flight_72 N=30: FLAGGED -- |a|=9.50 outside nominal band [9.8,11.0] (speed=8.51 m/s, elev=4.4 deg)
- [20:41:52] 2026_07_21_gym/flight_74 N=20: FLAGGED -- |a|=13.67 outside nominal band [9.8,11.0] (speed=8.76 m/s, elev=13.5 deg)
- [20:41:52] 2026_07_21_gym/flight_75 N=20: FLAGGED -- |a|=8.06 outside nominal band [9.8,11.0] (speed=7.61 m/s, elev=5.9 deg)
- [20:41:52] 2026_07_21_gym/flight_75 N=30: FLAGGED -- |a|=8.52 outside nominal band [9.8,11.0] (speed=7.34 m/s, elev=8.1 deg)
- [20:41:52] 2026_07_21_gym/flight_76 N=20: FLAGGED -- |a|=15.82 outside nominal band [9.8,11.0]; gravity crosscheck diff=47.4 deg > 45.0 (speed=7.35 m/s, elev=14.6 deg)
- [20:41:52] 2026_07_21_gym/flight_77 N=30: FLAGGED -- |a|=9.26 outside nominal band [9.8,11.0] (speed=7.99 m/s, elev=7.6 deg)
- [20:41:52] 2026_07_21_gym/flight_79 N=20: FLAGGED -- |a|=8.71 outside nominal band [9.8,11.0] (speed=9.79 m/s, elev=-3.3 deg)
- [20:41:52] 2026_07_21_gym/flight_79 N=30: FLAGGED -- |a|=8.49 outside nominal band [9.8,11.0] (speed=9.65 m/s, elev=-3.2 deg)
- [20:41:52] 2026_07_21_gym/flight_80 N=20: FLAGGED -- |a|=7.36 outside nominal band [9.8,11.0] (speed=8.63 m/s, elev=-6.8 deg)
- [20:41:52] 2026_07_21_gym/flight_80 N=30: FLAGGED -- |a|=8.37 outside nominal band [9.8,11.0]; adjusted from 30 -> 28, flight has fewer usable frames (speed=8.82 m/s, elev=-6.7 deg)
- [20:41:52] 2026_07_21_gym: progress 80/126 flights processed
- [20:41:52] 2026_07_21_gym/flight_81 N=20: FLAGGED -- |a|=8.10 outside nominal band [9.8,11.0] (speed=9.94 m/s, elev=-6.7 deg)
- [20:41:52] 2026_07_21_gym/flight_81 N=30: FLAGGED -- |a|=9.44 outside nominal band [9.8,11.0] (speed=9.83 m/s, elev=-5.1 deg)
- [20:41:52] 2026_07_21_gym/flight_82 N=20: FLAGGED -- |a|=9.20 outside nominal band [9.8,11.0] (speed=9.44 m/s, elev=-0.5 deg)
- [20:41:52] 2026_07_21_gym/flight_82 N=30: FLAGGED -- |a|=9.33 outside nominal band [9.8,11.0] (speed=9.69 m/s, elev=-0.6 deg)
- [20:41:52] 2026_07_21_gym/flight_83 N=20: FLAGGED -- |a|=11.24 outside nominal band [9.8,11.0] (speed=9.37 m/s, elev=4.8 deg)
- [20:41:52] 2026_07_21_gym/flight_84 N=20: FLAGGED -- |a|=9.61 outside nominal band [9.8,11.0] (speed=10.45 m/s, elev=-9.9 deg)
- [20:41:52] 2026_07_21_gym/flight_84 N=30: FLAGGED -- adjusted from 30 -> 26, flight has fewer usable frames (speed=10.46 m/s, elev=-9.3 deg)
- [20:41:52] 2026_07_21_gym/flight_85 N=20: FLAGGED -- |a|=11.52 outside nominal band [9.8,11.0] (speed=9.61 m/s, elev=7.8 deg)
- [20:41:52] 2026_07_21_gym/flight_86 N=30: FLAGGED -- |a|=9.24 outside nominal band [9.8,11.0] (speed=9.87 m/s, elev=-2.8 deg)
- [20:41:52] 2026_07_21_gym/flight_87 N=30: FLAGGED -- |a|=9.74 outside nominal band [9.8,11.0] (speed=9.51 m/s, elev=4.3 deg)
- [20:41:52] 2026_07_21_gym/flight_88 N=20: FLAGGED -- |a|=11.31 outside nominal band [9.8,11.0] (speed=9.50 m/s, elev=10.1 deg)
- [20:41:52] 2026_07_21_gym/flight_89 N=30: FLAGGED -- |a|=11.18 outside nominal band [9.8,11.0]; adjusted from 30 -> 23, flight has fewer usable frames (speed=10.04 m/s, elev=-10.3 deg)
- [20:41:52] 2026_07_21_gym/flight_90 N=20: FLAGGED -- |a|=8.70 outside nominal band [9.8,11.0] (speed=8.22 m/s, elev=7.0 deg)
- [20:41:52] 2026_07_21_gym/flight_90 N=30: FLAGGED -- |a|=9.51 outside nominal band [9.8,11.0] (speed=8.23 m/s, elev=8.2 deg)
- [20:41:52] 2026_07_21_gym/flight_92 N=20: FLAGGED -- |a|=11.07 outside nominal band [9.8,11.0] (speed=6.89 m/s, elev=50.4 deg)
- [20:41:52] 2026_07_21_gym/flight_92 N=30: FLAGGED -- |a|=9.77 outside nominal band [9.8,11.0] (speed=6.91 m/s, elev=47.8 deg)
- [20:41:52] 2026_07_21_gym/flight_93 N=20: FLAGGED -- |a|=17.82 outside nominal band [9.8,11.0] (speed=7.56 m/s, elev=53.1 deg)
- [20:41:52] 2026_07_21_gym/flight_95 N=20: FLAGGED -- |a|=11.45 outside nominal band [9.8,11.0] (speed=7.78 m/s, elev=54.1 deg)
- [20:41:52] 2026_07_21_gym/flight_96 N=20: FLAGGED -- |a|=8.37 outside nominal band [9.8,11.0] (speed=6.45 m/s, elev=46.9 deg)
- [20:41:52] 2026_07_21_gym/flight_96 N=30: FLAGGED -- |a|=9.22 outside nominal band [9.8,11.0] (speed=6.58 m/s, elev=49.0 deg)
- [20:41:52] 2026_07_21_gym/flight_98 N=20: FLAGGED -- |a|=11.44 outside nominal band [9.8,11.0] (speed=7.25 m/s, elev=53.1 deg)
- [20:41:52] 2026_07_21_gym/flight_99 N=20: FLAGGED -- |a|=11.21 outside nominal band [9.8,11.0]; gravity crosscheck diff=50.8 deg > 45.0 (speed=6.47 m/s, elev=50.2 deg)
- [20:41:52] 2026_07_21_gym/flight_100 N=20: FLAGGED -- |a|=8.21 outside nominal band [9.8,11.0] (speed=7.15 m/s, elev=50.1 deg)
- [20:41:52] 2026_07_21_gym/flight_100 N=30: FLAGGED -- |a|=9.08 outside nominal band [9.8,11.0] (speed=7.22 m/s, elev=50.2 deg)
- [20:41:52] 2026_07_21_gym: progress 100/126 flights processed
- [20:41:52] 2026_07_21_gym/flight_101 N=20: FLAGGED -- |a|=14.25 outside nominal band [9.8,11.0] (speed=6.01 m/s, elev=53.5 deg)
- [20:41:52] 2026_07_21_gym/flight_101 N=30: FLAGGED -- |a|=11.29 outside nominal band [9.8,11.0] (speed=6.03 m/s, elev=52.1 deg)
- [20:41:52] 2026_07_21_gym/flight_102 N=20: FLAGGED -- |a|=11.19 outside nominal band [9.8,11.0] (speed=6.79 m/s, elev=51.6 deg)
- [20:41:52] 2026_07_21_gym/flight_104 N=30: FLAGGED -- |a|=9.14 outside nominal band [9.8,11.0] (speed=6.83 m/s, elev=55.2 deg)
- [20:41:52] 2026_07_21_gym/flight_105 N=20: FLAGGED -- |a|=13.02 outside nominal band [9.8,11.0] (speed=7.66 m/s, elev=57.4 deg)
- [20:41:52] 2026_07_21_gym/flight_106 N=20: FLAGGED -- |a|=15.24 outside nominal band [9.8,11.0] (speed=7.52 m/s, elev=59.9 deg)
- [20:41:52] 2026_07_21_gym/flight_106 N=30: FLAGGED -- |a|=9.48 outside nominal band [9.8,11.0] (speed=7.16 m/s, elev=56.9 deg)
- [20:41:52] 2026_07_21_gym/flight_107 N=20: FLAGGED -- |a|=14.41 outside nominal band [9.8,11.0] (speed=7.28 m/s, elev=54.4 deg)
- [20:41:52] 2026_07_21_gym/flight_108 N=20: FLAGGED -- |a|=11.90 outside nominal band [9.8,11.0] (speed=6.69 m/s, elev=55.9 deg)
- [20:41:52] 2026_07_21_gym/flight_109 N=20: FLAGGED -- |a|=8.87 outside nominal band [9.8,11.0] (speed=7.05 m/s, elev=51.2 deg)
- [20:41:52] 2026_07_21_gym/flight_110 N=20: FLAGGED -- |a|=11.57 outside nominal band [9.8,11.0] (speed=7.42 m/s, elev=46.5 deg)
- [20:41:52] 2026_07_21_gym/flight_110 N=30: FLAGGED -- |a|=11.35 outside nominal band [9.8,11.0] (speed=7.40 m/s, elev=46.3 deg)
- [20:41:52] 2026_07_21_gym/flight_111 N=20: FLAGGED -- |a|=17.27 outside nominal band [9.8,11.0] (speed=7.00 m/s, elev=55.6 deg)
- [20:41:52] 2026_07_21_gym/flight_111 N=30: FLAGGED -- |a|=11.76 outside nominal band [9.8,11.0] (speed=6.95 m/s, elev=53.3 deg)
- [20:41:52] 2026_07_21_gym/flight_112 N=20: FLAGGED -- |a|=17.24 outside nominal band [9.8,11.0]; gravity crosscheck diff=46.4 deg > 45.0 (speed=6.77 m/s, elev=54.9 deg)
- [20:41:52] 2026_07_21_gym/flight_112 N=30: FLAGGED -- |a|=11.47 outside nominal band [9.8,11.0] (speed=6.74 m/s, elev=52.6 deg)
- [20:41:52] 2026_07_21_gym/flight_113 N=20: FLAGGED -- |a|=12.30 outside nominal band [9.8,11.0] (speed=7.31 m/s, elev=45.8 deg)
- [20:41:52] 2026_07_21_gym/flight_113 N=30: FLAGGED -- |a|=11.12 outside nominal band [9.8,11.0] (speed=7.30 m/s, elev=41.8 deg)
- [20:41:52] 2026_07_21_gym/flight_114 N=20: FLAGGED -- |a|=12.28 outside nominal band [9.8,11.0] (speed=6.76 m/s, elev=51.8 deg)
- [20:41:52] 2026_07_21_gym/flight_114 N=30: FLAGGED -- |a|=11.35 outside nominal band [9.8,11.0] (speed=6.69 m/s, elev=50.4 deg)
- [20:41:52] 2026_07_21_gym/flight_116 N=20: FLAGGED -- |a|=13.21 outside nominal band [9.8,11.0] (speed=6.62 m/s, elev=60.5 deg)
- [20:41:52] 2026_07_21_gym/flight_117 N=20: FLAGGED -- |a|=11.77 outside nominal band [9.8,11.0] (speed=6.56 m/s, elev=52.7 deg)
- [20:41:52] 2026_07_21_gym/flight_118 N=20: FLAGGED -- |a|=11.47 outside nominal band [9.8,11.0] (speed=6.53 m/s, elev=41.9 deg)
- [20:41:52] 2026_07_21_gym: progress 120/126 flights processed
- [20:41:52] 2026_07_21_gym/flight_121 N=20: FLAGGED -- |a|=14.38 outside nominal band [9.8,11.0] (speed=8.06 m/s, elev=56.0 deg)
- [20:41:52] 2026_07_21_gym/flight_121 N=30: FLAGGED -- |a|=11.60 outside nominal band [9.8,11.0] (speed=8.04 m/s, elev=52.0 deg)
- [20:41:52] 2026_07_21_gym/flight_122 N=20: FLAGGED -- |a|=11.61 outside nominal band [9.8,11.0] (speed=7.50 m/s, elev=59.3 deg)
- [20:41:52] 2026_07_21_gym/flight_122 N=30: FLAGGED -- |a|=11.23 outside nominal band [9.8,11.0] (speed=7.59 m/s, elev=58.8 deg)
- [20:41:52] 2026_07_21_gym/flight_123 N=20: FLAGGED -- |a|=11.56 outside nominal band [9.8,11.0] (speed=7.18 m/s, elev=53.3 deg)
- [20:41:52] 2026_07_21_gym/flight_124 N=20: FLAGGED -- |a|=15.54 outside nominal band [9.8,11.0] (speed=7.65 m/s, elev=53.5 deg)
- [20:41:52] 2026_07_21_gym/flight_124 N=30: FLAGGED -- |a|=13.01 outside nominal band [9.8,11.0] (speed=7.59 m/s, elev=51.4 deg)
- [20:41:52] 2026_07_21_gym/flight_125 N=20: FLAGGED -- |a|=14.76 outside nominal band [9.8,11.0] (speed=7.72 m/s, elev=51.2 deg)
- [20:41:52] 2026_07_21_gym/flight_125 N=30: FLAGGED -- |a|=12.08 outside nominal band [9.8,11.0] (speed=7.61 m/s, elev=48.5 deg)
- [20:41:52] 2026_07_21_gym/flight_126 N=20: FLAGGED -- |a|=12.19 outside nominal band [9.8,11.0] (speed=7.13 m/s, elev=54.5 deg)
- [20:41:52] 2026_07_21_gym: done, 126 flights processed
- [20:41:52] --- session 2026_07_15_gym ---
- [20:41:52] 2026_07_15_gym: loaded world transform(s): registration from img_0030
- [20:41:52] 2026_07_15_gym: 37 flights with tuned-detector detection CSVs
- [20:41:52] 2026_07_15_gym/flight_01 N=30: FLAGGED -- adjusted from 30 -> 25, flight has fewer usable frames (speed=10.86 m/s, elev=-12.5 deg)
- [20:41:52] 2026_07_15_gym/flight_11 N=20: FLAGGED -- |a|=12.71 outside nominal band [9.8,11.0] (speed=8.50 m/s, elev=55.0 deg)
- [20:41:52] 2026_07_15_gym/flight_11 N=30: FLAGGED -- |a|=11.47 outside nominal band [9.8,11.0] (speed=8.36 m/s, elev=53.3 deg)
- [20:41:52] 2026_07_15_gym/flight_12 N=20: FLAGGED -- |a|=11.36 outside nominal band [9.8,11.0] (speed=7.53 m/s, elev=57.6 deg)
- [20:41:52] 2026_07_15_gym/flight_14 N=20: FLAGGED -- |a|=11.97 outside nominal band [9.8,11.0]; gravity crosscheck diff=46.8 deg > 45.0 (speed=7.60 m/s, elev=47.8 deg)
- [20:41:52] 2026_07_15_gym/flight_15 N=20: FLAGGED -- |a|=12.16 outside nominal band [9.8,11.0] (speed=7.94 m/s, elev=59.2 deg)
- [20:41:52] 2026_07_15_gym/flight_15 N=30: FLAGGED -- |a|=11.08 outside nominal band [9.8,11.0] (speed=7.82 m/s, elev=58.9 deg)
- [20:41:52] 2026_07_15_gym/flight_17 N=20: FLAGGED -- |a|=13.18 outside nominal band [9.8,11.0] (speed=7.77 m/s, elev=53.5 deg)
- [20:41:52] 2026_07_15_gym/flight_17 N=30: FLAGGED -- |a|=11.52 outside nominal band [9.8,11.0]; gravity crosscheck diff=53.7 deg > 45.0 (speed=7.73 m/s, elev=31.0 deg)
- [20:41:52] 2026_07_15_gym/flight_19 N=20: FLAGGED -- |a|=11.65 outside nominal band [9.8,11.0] (speed=7.78 m/s, elev=48.6 deg)
- [20:41:52] 2026_07_15_gym/flight_19 N=30: FLAGGED -- |a|=11.33 outside nominal band [9.8,11.0] (speed=7.73 m/s, elev=49.2 deg)
- [20:41:52] 2026_07_15_gym/flight_20 N=20: FLAGGED -- |a|=14.28 outside nominal band [9.8,11.0] (speed=8.17 m/s, elev=53.8 deg)
- [20:41:52] 2026_07_15_gym/flight_20 N=30: FLAGGED -- |a|=11.27 outside nominal band [9.8,11.0] (speed=7.85 m/s, elev=51.8 deg)
- [20:41:53] 2026_07_15_gym/flight_21 N=20: FLAGGED -- |a|=11.92 outside nominal band [9.8,11.0] (speed=7.67 m/s, elev=52.1 deg)
- [20:41:53] 2026_07_15_gym/flight_21 N=30: FLAGGED -- |a|=11.66 outside nominal band [9.8,11.0] (speed=7.60 m/s, elev=52.8 deg)
- [20:41:53] 2026_07_15_gym/flight_22 N=20: FLAGGED -- |a|=13.00 outside nominal band [9.8,11.0] (speed=7.54 m/s, elev=55.5 deg)
- [20:41:53] 2026_07_15_gym/flight_23 N=20: FLAGGED -- |a|=15.24 outside nominal band [9.8,11.0] (speed=7.19 m/s, elev=53.6 deg)
- [20:41:53] 2026_07_15_gym/flight_23 N=30: FLAGGED -- |a|=11.08 outside nominal band [9.8,11.0] (speed=6.96 m/s, elev=50.3 deg)
- [20:41:53] 2026_07_15_gym/flight_24 N=20: FLAGGED -- |a|=11.72 outside nominal band [9.8,11.0] (speed=7.04 m/s, elev=54.0 deg)
- [20:41:53] 2026_07_15_gym/flight_24 N=30: FLAGGED -- |a|=11.46 outside nominal band [9.8,11.0] (speed=7.11 m/s, elev=52.7 deg)
- [20:41:53] 2026_07_15_gym/flight_25 N=20: FLAGGED -- |a|=11.27 outside nominal band [9.8,11.0] (speed=7.61 m/s, elev=54.0 deg)
- [20:41:53] 2026_07_15_gym/flight_25 N=30: FLAGGED -- |a|=11.70 outside nominal band [9.8,11.0] (speed=7.65 m/s, elev=54.5 deg)
- [20:41:53] 2026_07_15_gym/flight_26 N=30: FLAGGED -- |a|=11.21 outside nominal band [9.8,11.0] (speed=7.28 m/s, elev=54.1 deg)
- [20:41:53] 2026_07_15_gym/flight_27 N=20: FLAGGED -- |a|=11.22 outside nominal band [9.8,11.0] (speed=8.02 m/s, elev=37.7 deg)
- [20:41:53] 2026_07_15_gym/flight_28 N=20: FLAGGED -- |a|=12.30 outside nominal band [9.8,11.0] (speed=7.65 m/s, elev=60.0 deg)
- [20:41:53] 2026_07_15_gym/flight_28 N=30: FLAGGED -- |a|=12.18 outside nominal band [9.8,11.0] (speed=7.63 m/s, elev=59.3 deg)
- [20:41:53] 2026_07_15_gym/flight_29 N=20: FLAGGED -- |a|=12.25 outside nominal band [9.8,11.0] (speed=7.33 m/s, elev=59.3 deg)
- [20:41:53] 2026_07_15_gym/flight_29 N=30: FLAGGED -- |a|=11.73 outside nominal band [9.8,11.0] (speed=7.33 m/s, elev=59.3 deg)
- [20:41:53] 2026_07_15_gym/flight_31 N=20: FLAGGED -- |a|=12.13 outside nominal band [9.8,11.0] (speed=7.29 m/s, elev=53.9 deg)
- [20:41:53] 2026_07_15_gym: progress 20/37 flights processed
- [20:41:53] 2026_07_15_gym/flight_36 N=20: FLAGGED -- |a|=11.18 outside nominal band [9.8,11.0] (speed=6.31 m/s, elev=57.5 deg)
- [20:41:53] 2026_07_15_gym/flight_36 N=30: SKIPPED -- implausible |a|=49.28 m/s^2 (hard gate [5.0,20.0])
- [20:41:54] 2026_07_15_gym/flight_45 N=20: FLAGGED -- |a|=9.77 outside nominal band [9.8,11.0] (speed=6.73 m/s, elev=58.9 deg)
- [20:41:54] 2026_07_15_gym/flight_48 N=30: FLAGGED -- |a|=11.39 outside nominal band [9.8,11.0] (speed=7.63 m/s, elev=59.3 deg)
- [20:41:54] 2026_07_15_gym/flight_49 N=20: FLAGGED -- |a|=9.09 outside nominal band [9.8,11.0] (speed=6.43 m/s, elev=64.2 deg)
- [20:41:54] 2026_07_15_gym/flight_50 N=30: FLAGGED -- |a|=9.41 outside nominal band [9.8,11.0] (speed=6.06 m/s, elev=64.3 deg)
- [20:41:54] 2026_07_15_gym/flight_52 N=20: FLAGGED -- |a|=11.08 outside nominal band [9.8,11.0] (speed=7.55 m/s, elev=20.2 deg)
- [20:41:54] 2026_07_15_gym/flight_52 N=30: FLAGGED -- |a|=11.17 outside nominal band [9.8,11.0] (speed=7.51 m/s, elev=20.4 deg)
- [20:41:54] 2026_07_15_gym/flight_53 N=20: FLAGGED -- |a|=11.57 outside nominal band [9.8,11.0] (speed=9.04 m/s, elev=4.0 deg)
- [20:41:54] 2026_07_15_gym/flight_54 N=20: FLAGGED -- |a|=9.41 outside nominal band [9.8,11.0] (speed=7.93 m/s, elev=-3.9 deg)
- [20:41:54] 2026_07_15_gym/flight_54 N=30: FLAGGED -- |a|=8.88 outside nominal band [9.8,11.0] (speed=7.74 m/s, elev=-2.9 deg)
- [20:41:54] 2026_07_15_gym/flight_55 N=20: FLAGGED -- |a|=8.36 outside nominal band [9.8,11.0] (speed=8.19 m/s, elev=-11.2 deg)
- [20:41:54] 2026_07_15_gym/flight_55 N=30: FLAGGED -- |a|=8.25 outside nominal band [9.8,11.0]; adjusted from 30 -> 28, flight has fewer usable frames (speed=8.23 m/s, elev=-11.4 deg)
- [20:41:54] 2026_07_15_gym/flight_56 N=20: FLAGGED -- |a|=9.42 outside nominal band [9.8,11.0] (speed=8.29 m/s, elev=0.8 deg)
- [20:41:54] 2026_07_15_gym/flight_56 N=30: FLAGGED -- |a|=9.35 outside nominal band [9.8,11.0] (speed=8.27 m/s, elev=0.9 deg)
- [20:41:54] 2026_07_15_gym/flight_57 N=20: FLAGGED -- |a|=8.02 outside nominal band [9.8,11.0] (speed=8.63 m/s, elev=-13.5 deg)
- [20:41:54] 2026_07_15_gym/flight_57 N=30: FLAGGED -- |a|=7.84 outside nominal band [9.8,11.0]; adjusted from 30 -> 25, flight has fewer usable frames (speed=8.58 m/s, elev=-13.6 deg)
- [20:41:54] 2026_07_15_gym/flight_58 N=20: FLAGGED -- |a|=8.29 outside nominal band [9.8,11.0]; adjusted from 20 -> 18, flight has fewer usable frames (speed=9.16 m/s, elev=-24.4 deg)
- [20:41:54] 2026_07_15_gym/flight_58 N=30: FLAGGED -- |a|=8.29 outside nominal band [9.8,11.0]; adjusted from 30 -> 18, flight has fewer usable frames (speed=9.16 m/s, elev=-24.4 deg)
- [20:41:54] 2026_07_15_gym/flight_59 N=20: FLAGGED -- |a|=8.88 outside nominal band [9.8,11.0]; adjusted from 20 -> 15, flight has fewer usable frames (speed=9.41 m/s, elev=-29.0 deg)
- [20:41:54] 2026_07_15_gym/flight_59 N=30: FLAGGED -- |a|=8.88 outside nominal band [9.8,11.0]; adjusted from 30 -> 15, flight has fewer usable frames (speed=9.41 m/s, elev=-29.0 deg)
- [20:41:55] 2026_07_15_gym/flight_60 N=30: FLAGGED -- |a|=9.04 outside nominal band [9.8,11.0] (speed=7.67 m/s, elev=2.1 deg)
- [20:41:55] 2026_07_15_gym: done, 37 flights processed
- [20:41:55] batch loop complete across all sessions: 326 rows written
- [20:41:55] wrote CSV -> C:\Users\44772\Desktop\OneDrive - Imperial College London\Uni\00_Masters Project\01_Testing\vision_system_ball_detection_work\data\flight_binning\flight_velocity_angle.csv (326 rows)
- [20:41:55] summary [2026_07_21_gym]: 251 ok rows
- [20:41:55] summary [2026_07_15_gym]: 73 ok rows
- [20:41:55] summary [overall]: 324 ok rows, 2 skipped rows, 218 flagged (of the ok rows), out of 326 total attempted rows
- [20:41:55] plotted distribution_N20.png (162 points, 121 flagged)
- [20:41:56] plotted distribution_N30.png (162 points, 97 flagged)
- [20:41:56] plotted distribution_overlay_histograms.png
- [20:42:00] plotted distribution_N_sensitivity.png
- [20:42:00] plotted distribution_by_session.png
- [20:42:00] === flight_velocity_angle_binner.py: batch run complete ===

## [discussion] User asked how to bin flights for predictor coverage (advisory only, no code)

User asked for a recommendation on binning strategy, not an implementation --
answered as an exploratory/advisory question, did NOT compute or apply
edges (still respecting the task's "no bin edges" scope).

**Given:** angle is genuinely bimodal in both sessions' combined distribution
(flat cluster -20 to +20 deg, high-arc cluster 45-65 deg, real gap between
them -- see `distribution_by_session.png`), speed is fairly continuous
6-10.5 m/s.

**Recommendation given:** avoid naive equal-width angle bins (would straddle
the empty 20-45 deg gap or leave a bin empty) -- bin around the two visible
clusters directly (2-3 sub-bins each, split by speed) so bins map onto real
throw types (flat drives vs high sets), not an arbitrary statistical grid.

**Flagged an unresolved tension in context.md, not something to silently
pick a side of**: SS4.9 says hand-label ~10-12 flights TOTAL for Link B;
SS8 separately floats ~8-12 PER BIN for "validation coverage" -- these only
agree at ~1 bin. Recommended the 4-6 bin range context.md itself suggests as
more realistic for a solo thrower (fits the 10-12-total framing, ~2
flights/bin), but flagged this needs supervisor confirmation per SS8's own
open item, not a call to make unilaterally.

Offered to propose actual bin edges against the real distribution once bin
count + the total-vs-per-bin question are settled -- not done yet, waiting.
