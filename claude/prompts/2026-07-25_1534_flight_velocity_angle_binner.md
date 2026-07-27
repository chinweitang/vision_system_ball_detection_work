# 2026-07-25 15:34 — Automated flight binner: initial velocity + angle distribution

**Instructions:** Copy the block below and paste it into a fresh Claude Code session
in this repo.

---

```
READ FIRST: claude/claude_rules.md, then claude/context.md in full (project context —
especially §4.5 detection pipeline, §4.8 calibration/world-frame, §4.9 arc capture /
Link B stratified labelling, §8 data strategy). This task's OWN new log file (see
LOGGING below) is where you write everything — no need to read other worklogs first.

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Build a batch script that computes each flight's initial launch speed and elevation
angle for every flight in `data/2026_07_21_gym/ball_flights`, and plot the
distribution across all flights — so the user can choose sensible bin edges for
stratified hand-labelling (Link B / detection-error validation, `context.md` §4.9)
by looking at the real data, not guessing bins upfront.

**This task's deliverable is the distribution, NOT chosen bins.** Do not pick or
apply bin edges — stop once the distribution is computed and plotted, and report it.

Context: two existing scripts already do almost everything needed here, just for one
flight at a time — reuse them, do not re-derive this logic:
- `src/stereo/label_vs_detection.py` has `triangulate(uv0, uv1, K0, D0, K1, D1, P0, P1)`
  — validated fisheye triangulation (undistort + `cv2.triangulatePoints`), plus
  `load_calib()` for loading intrinsics/extrinsics.
- `src/stereo/predict_sweep.py` has `fit_constant_accel(t, xyz)` — fits
  `p(t) = p0 + v0*t + 0.5*a*t^2` per axis to the first N triangulated points of a
  flight, returning `(p0, v0, a)`. It also already solves "which way is up without
  world registration" by deriving gravity direction from the fitted `a` vector — but
  per this session's decision below, world-frame registration is the PRIMARY
  reference for angle here, not the fit-derived direction (see step 2). Still use
  `predict_sweep.py`'s existing fit-vs-world-registration angle comparison as a
  cheap cross-check/QA flag (it already computes exactly this).
- `src/image_processing/02_adjacent_frame_differencing/detector_core.py`'s
  `filter_trajectory_outliers()` must be run on each camera's raw detections BEFORE
  fitting — the earliest frames of a flight (ball leaving the hand) are exactly where
  a hand/arm detection is most likely to be picked over the ball (a real bug already
  found in this dataset: largest-area-candidate-selection sometimes prefers an arm),
  so an unfiltered early-window fit is the most likely place for that bug to corrupt
  a result.
- Extrinsics: use `calibration_outputs/2026_07_21/test2/stereo_extrinsic.npz`
  specifically (NOT the top-level `calibration_outputs/2026_07_21/stereo_extrinsic.npz`
  — confirmed earlier this session: test2 has tighter RMS and a baseline closer to
  the nominal 850mm). Intrinsics: `calibration_outputs/cam0_intrinsics_fisheye.npz` /
  `cam1_intrinsics_fisheye.npz`.

**Design decisions already confirmed with the user (do not re-litigate):**
1. Use real 3D triangulated velocity/angle, not a 2D pixel-velocity proxy — a 2D
   proxy from one camera is a bad stand-in here because this is a side-on stereo rig
   (the camera's weak/depth axis is the width axis), so a throw with real lateral
   velocity would show artificially low pixel velocity in a single camera regardless
   of its true 3D speed.
2. Angle reference: **world-frame checkerboard registration**, not the fit-derived
   gravity direction — a per-flight fit derived from only a handful of early frames
   can be unphysical (`predict_sweep.py` already shows accel fits at low N can be
   wildly off, e.g. |a|~440 m/s² at N=3), so it's not a reliable "up" reference on
   its own. BUT this session's world registration has never been validated — see
   step 2, which must happen before any angle is computed.
3. `data/2026_07_21_gym/world_registration/` has TWO registrations because the rig's
   world frame changed mid-session: **registration1 covers flights 1-60 (inclusive),
   registration2 covers flights 61 onwards.** Each registration folder has 2
   candidate checkerboard image pairs (cam0+cam1) — e.g. `registration1/{cam0,cam1}/
   img_0031.png` and `.../img_0032.png` — validate both via
   `src/registration/world_frame_precision_single.py`'s guardrails and use whichever
   passes / has the better residual, for EACH of registration1 and registration2
   independently.
4. Compute speed/angle at 2 different fit-window sizes (e.g. N=5 and N=10, adjust if
   a flight has fewer usable frames — reuse `predict_sweep.py`'s own N>=3 minimum
   gate) and report both, so the user can see how sensitive the result is to window
   choice before this becomes a permanent methodology decision.

═══════════════════════════════════════════════════════════════════════════════
LOGGING (NEW LOG FILE, REAL-TIME UPDATES — CRITICAL)
═══════════════════════════════════════════════════════════════════════════════

Create a NEW log file: `claude/claude_logs/2026-07-25_flight_velocity_angle_binner_worklog.md`
(this is a separate piece of work from both the detector-tuning worklog and the
pixel-velocity sync-correction worklog — do not append to either of those).

Follow the same conventions as the existing worklogs (`claude/claude_rules.md` §10 —
chronological sections, what was tried, what was found including dead ends and wrong
assumptions, why a decision was made, what's still open).

**Update it CONTINUOUSLY while working, not once at the end.** Specifically, append
immediately after each of: reading the reused scripts, each world-registration
validation result (both candidate images, both registrations), any flight that fails
or gets flagged/skipped and why, the full batch run completing, each plot being
produced, and both checkpoints. The user monitors this file in real time — if there's
a long gap between an update and the next one while something is still running, that
defeats the purpose. When in doubt, log more often, not less.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

1. Create the new log file first. Read `claude/claude_rules.md`, `claude/context.md`,
   then read in full: `src/stereo/label_vs_detection.py`, `src/stereo/predict_sweep.py`,
   `src/registration/world_frame_precision_single.py`,
   `src/registration/world_registration.py` (if separate from the above),
   `src/image_processing/02_adjacent_frame_differencing/detector_core.py`
   (`run_detection()`, `filter_trajectory_outliers()`). Log a short summary of each
   script's reusable pieces before writing any new code.

2. **World-frame registration validation (do this BEFORE any per-flight angle
   computation)**: for registration1 (`img_0031`, `img_0032`) and registration2
   (`img_0033`, `img_0034`) independently, run `world_frame_precision_single.py`'s
   guardrail checks against each candidate cam0+cam1 image pair. Pick whichever
   image in each registration passes / has the better residual. If BOTH candidates
   in a registration fail the guardrails, STOP and report — do not silently proceed
   with a failing registration.

3. **STOP at Checkpoint 1** and report: which image won for registration1, which won
   for registration2, their residuals/guardrail results, and the resulting world "up"
   direction for each. Wait for confirmation before computing any per-flight angles
   from these.

4. **Build the batch script** (e.g. `src/stereo/flight_velocity_angle_binner.py`),
   run across every flight under `data/2026_07_21_gym/ball_flights`:
   - Load detections from
     `data/detector_tuning/detections/03_stride1_thresh16_openk3_area30_circ0.3/
     2026_07_21_gym/flight_N_cam0_detections.csv` /
     `..._cam1_detections.csv` (columns: `frame_number, u, v`, same format as the
     older per-flight `analysis_3/*_detections3.csv`, but this is the CURRENT, final
     tuned-detector output — MIN_AREA=30, exclusion-mask v4, trajectory filter, full
     163-flight production run — NOT the stale pre-tuning baseline in each flight's
     own `analysis_3/` folder. Confirmed by row count: `flight_5` has 37 rows here
     vs. 19 in the old `analysis_3` file — do not use `analysis_3` for this task.
     Note: only 126 of the session's 149 flights have a file here — some flights
     won't have tuned detections at all; skip and log those (see ERROR HANDLING).
   - Run `filter_trajectory_outliers()` on each camera's raw detections independently.
   - Pair by matching `frame_number` between the two filtered sets (naive index
     pairing is fine here, same as `label_vs_detection.py`'s own approach — this is
     a bulk statistics task, not a precision-tracking one, so sync correction is not
     needed).
   - For the flight's earliest paired frames, triangulate via the reused
     `triangulate()`, then fit via the reused `fit_constant_accel()` at each of the 2
     window sizes (N values) from decision 4 above, extracting `v0` (initial
     velocity vector) each time.
   - Determine which registration (1 or 2) applies from the flight number (<=60 -> 1,
     >60 -> 2) and rotate `v0` into that world frame using the validated transform
     from Checkpoint 1. Compute elevation angle (angle of `v0` above horizontal in
     the world frame) and speed (`|v0|`, convert to m/s).
   - Also compute `predict_sweep.py`'s existing fit-derived-gravity-vs-world-up cross
     check angle, and flag any flight where it disagrees by a large margin (reuse
     whatever threshold `predict_sweep.py` already uses, e.g. its existing >45°
     warning) — this doubles as a cheap dataset-wide check for the arm/hand
     candidate-selection bug corrupting early frames, since a corrupted fit is a
     likely cause of a large disagreement here.
   - If a flight has too few usable frames (< the N>=3 minimum), a failed fit gate,
     or an implausible result (e.g. `|a|` wildly outside a gravity-plus-drag-plausible
     range, reusing `predict_sweep.py`'s/`label_vs_detection.py`'s existing gate
     constants as a reference), SKIP it and log why — do not let one bad flight abort
     the batch, and do not silently include a garbage point in the distribution.
   - Write one row per flight per N value to a CSV (flight_id, N, speed_m_s,
     elevation_deg, gravity_crosscheck_diff_deg, registration_used, skipped/flag
     reason if any).

5. **Plot the distribution**: scatter of speed vs. elevation angle (one plot per N
   value, or overlaid/faceted — your call), plus marginal histograms for speed and
   for angle separately. Visually distinguish or annotate any flagged/cross-check-
   disagreement flights so the user can see if they cluster in a particular region
   rather than scattering randomly.

6. Save the CSV and plots to a new, clearly-named location — e.g.
   `data/2026_07_21_gym/flight_binning/` — do not write into any existing
   `analysis_3` folder or into `data/detector_tuning/detections/` (read the tuned
   detections from there, but this task's own outputs go elsewhere).

7. **STOP at Checkpoint 2** and report: the full distribution (plots + CSV summary),
   how many flights were skipped/flagged and why, the sensitivity between the 2 N
   values tested, and the world-registration validation result from Checkpoint 1 for
   reference. Do NOT propose or apply bin edges — that's an explicit follow-up
   decision for the user once they've seen this.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

Do NOT do (unless explicitly asked later):
- ❌ Choose or apply bin edges — this task stops at the distribution
- ❌ Use `calibration_outputs/2026_07_21/stereo_extrinsic.npz` (top-level) — use
  `test2/stereo_extrinsic.npz` only
- ❌ Use the fit-derived gravity direction as the PRIMARY angle reference — world
  registration is primary; the fit-derived direction is a cross-check flag only
- ❌ Use `analysis_3/*_detections3.csv` (the stale pre-tuning baseline) — use
  `data/detector_tuning/detections/03_stride1_thresh16_openk3_area30_circ0.3/
  2026_07_21_gym/` instead (see step 4)
- ❌ Overwrite or delete anything under `data/2026_07_21_gym/ball_flights/<flight>/`,
  anything under `data/detector_tuning/detections/`, or any existing
  `data/2026_07_21_gym/world_registration/` image — all read-only inputs
- ❌ Modify `label_vs_detection.py`, `predict_sweep.py`, `detector_core.py`,
  `world_frame_precision_single.py`, or `world_registration.py` — reuse/import from
  them, don't change their existing logic
- ❌ Attempt sync correction (nearest-timestamp pairing, sub-frame velocity shift) —
  out of scope for this task, naive same-index pairing is sufficient here (see step 4)
- ❌ Commit anything to git
- ❌ Create more than the one new log file named in LOGGING above

IF you think something else should be done that isn't covered above:
1. STOP
2. Log: "Considered doing [X] but it's not in scope — asking first"
3. Report and wait for a response

═══════════════════════════════════════════════════════════════════════════════
TIMING EXPECTATIONS
═══════════════════════════════════════════════════════════════════════════════

I/O-bound analysis on already-captured/already-detected data, not a heavy compute
sweep:
- World-frame validation (step 2): 4 candidate image pairs total — expect well under
  a minute.
- Batch script across all flights in `data/2026_07_21_gym/ball_flights` (~149
  flights per the earlier sync-correction session's finding): each flight is a small
  triangulation + fit on a handful of early frames — expect low single-digit minutes
  total, not more.

STOP and investigate if any single step runs past ~5 minutes with no output change.

═══════════════════════════════════════════════════════════════════════════════
CHECKPOINTS
═══════════════════════════════════════════════════════════════════════════════

Checkpoint 1 — after world-frame registration validation (steps 2-3): STOP, report
which candidate image won for registration1 and registration2 and why, wait for
confirmation before computing any per-flight angle from them.

Checkpoint 2 — after the full batch + distribution plots (steps 4-7): STOP, report
the distribution, skipped/flagged flights, and N-sensitivity. Do not choose bins.
Wait for the user's next instruction.

Do not proceed past either checkpoint without explicit go-ahead.

═══════════════════════════════════════════════════════════════════════════════
ERROR HANDLING
═══════════════════════════════════════════════════════════════════════════════

Expected (log, skip that flight, continue):
- A flight missing a tuned-detections file under `data/detector_tuning/detections/
  03_stride1_thresh16_openk3_area30_circ0.3/2026_07_21_gym/` (23 of 149 flights are
  already known to be missing one), or with too few filtered frames to fit
  (< N minimum).
- A fit that fails `predict_sweep.py`/`label_vs_detection.py`'s existing plausibility
  gates (e.g. `|a|` far outside a gravity-plausible range).

Unexpected (STOP immediately, don't guess a workaround):
- BOTH candidate images in a registration failing the world-frame guardrails (step 2)
- `test2/stereo_extrinsic.npz` failing to load, or a triangulated baseline wildly off
  from ~850mm
- A large fraction (not just a handful) of flights failing/flagged — would suggest a
  bug in the batch script itself, not noisy individual flights

═══════════════════════════════════════════════════════════════════════════════
GIT WORKFLOW
═══════════════════════════════════════════════════════════════════════════════

No git. Do not commit anything.

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ World-frame registration validated for both registration1 and registration2
   before any angle was computed, with the choice reported and justified at
   Checkpoint 1
✅ Speed + elevation angle computed per flight at 2 window sizes, reusing
   `triangulate()` / `fit_constant_accel()` / `filter_trajectory_outliers()` rather
   than duplicating their logic
✅ Flights that couldn't be fit reliably were skipped and logged, not silently
   included with garbage values
✅ The fit-vs-world-registration cross-check flag was computed and used to surface
   any flights where the arm/hand-selection bug may have corrupted the result
✅ Distribution (scatter + histograms, both N values) plotted and saved to a new
   location, not mixed into `analysis_3` or `data/detector_tuning/`
✅ No bin edges were chosen or applied — task stopped at the distribution, reported
   at Checkpoint 2
✅ No existing file under `data/2026_07_21_gym/` was modified
✅ New log file created and updated continuously throughout — not written once at
   the end
✅ No commits made

═══════════════════════════════════════════════════════════════════════════════
START WORK
═══════════════════════════════════════════════════════════════════════════════

Begin now:
1. Create claude/claude_logs/2026-07-25_flight_velocity_angle_binner_worklog.md
2. Read claude/claude_rules.md, claude/context.md, and the 4-5 scripts named in
   step 1 of SCOPE above — log a summary of what's being reused before coding
3. Validate world-frame registration (registration1 + registration2)
4. Report at Checkpoint 1 and wait
5. Build the batch script and run it across data/2026_07_21_gym/ball_flights
6. Plot the distribution
7. Report at Checkpoint 2 and wait
```
