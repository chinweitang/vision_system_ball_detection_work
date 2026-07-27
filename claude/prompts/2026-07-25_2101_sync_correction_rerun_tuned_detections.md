# 2026-07-25 21:01 — Rerun sync-correction validation with the correct (tuned) detections

**Instructions:** Copy the block below and paste it into a fresh Claude Code session
in this repo.

---

```
READ FIRST: claude/claude_logs/2026-07-25_pixel_velocity_sync_correction_worklog.md
IN FULL — this is a continuation/correction of that exact task, not a new one. Then
claude/claude_rules.md and claude/context.md §4.6 (error budget term C) for context.

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Fix a data-source bug in the pixel-velocity sync-correction work and rerun the
validation. The scripts and design from that task are correct and should NOT be
rebuilt — only the detections input source needs to change, then Steps 5-6 (build
triangulate_flight.py's comparison, validate_sync_correction.py) need to be rerun.

**The bug**: `src/stereo/pixel_velocity_correction.py` / `src/stereo/triangulate_flight.py`
load ball-centroid detections from each flight's own `analysis_3/*_detections3.csv`.
That folder holds the STALE pre-tuning detector output — confirmed by direct
comparison: `flight_5_cam0` has 19 rows in `analysis_3` vs. **37 rows** in the
correct source. The correct, current detections (final tuned detector — MIN_AREA=30,
exclusion-mask v4, trajectory filter, full 163-flight production run, per
`claude/claude_logs/2026-07-23_ball_detection_rate_tuning_worklog.md`) live at:

  data/detector_tuning/detections/03_stride1_thresh16_openk3_area30_circ0.3/
  2026_07_21_gym/flight_N_cam{0,1}_detections.csv

Same column format as before (`frame_number,u,v`) — this is a path fix, not a
reformatting job. Note: only 126 of the session's 149 flights have a file here
(23 flights have no tuned-detections output at all) — handle that gracefully.

**Why this matters**: Checkpoint 2 of the original task found the sub-frame velocity
correction *hurt* results at low point counts (5-12 kept points per flight) on 3 of 7
validation flights. That low point density is very likely an artifact of using the
sparser `analysis_3` baseline, not a real property of the correction method — with
roughly double the point density from the correct source, that finding may not
reproduce. Don't assume either way — rerun and report what actually happens.

═══════════════════════════════════════════════════════════════════════════════
LOGGING (CONTINUE THE EXISTING WORKLOG)
═══════════════════════════════════════════════════════════════════════════════

This is the SAME piece of work as before, being corrected — continue appending to
`claude/claude_logs/2026-07-25_pixel_velocity_sync_correction_worklog.md`. Do NOT
create a new log file. Add a new top-level section (e.g. "Bug found: wrong detections
source — rerun with tuned detections") continuing from where Checkpoint 2 left off.

Update it continuously while working (after the code fix, after re-picking the
validation flight sample, after each flight's results come in, at the final
checkpoint) — not once at the end.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

1. Read `claude/claude_logs/2026-07-25_pixel_velocity_sync_correction_worklog.md` in
   full to recall the exact existing design (per-flight correction, forward-
   extrapolate-whichever-frame-is-earlier convention, finite-difference velocity,
   8.5ms max-pair-gap cutoff and why it's set there). Then read
   `src/stereo/pixel_velocity_correction.py`, `src/stereo/triangulate_flight.py`, and
   `src/stereo/validate_sync_correction.py` in full — these already exist and already
   work, don't rebuild them.

2. **Fix the detections source**: update whichever function loads per-flight
   detections (in `pixel_velocity_correction.py` and/or `triangulate_flight.py`) to
   read from
   `data/detector_tuning/detections/03_stride1_thresh16_openk3_area30_circ0.3/2026_07_21_gym/
   flight_N_cam{0,1}_detections.csv` instead of each flight's own
   `analysis_3/*_detections3.csv`. Keep everything else (the `{frame_number: (u,v)}`
   dict shape downstream, `filter_trajectory_outliers()` call, pairing/correction
   logic) unchanged — this is a single I/O path change, not a redesign. Handle
   flights with no file at this path by skipping/logging, not crashing.

3. **Re-pick the validation flight sample.** The original 7 flights (flight_92,
   flight_5, flight_100, flight_20, flight_110, flight_120, flight_60) were chosen to
   span the full range of measured sync offsets from `data/2026_07_21_gym/sync_audit.csv`
   (−8.29ms to +8.30ms), with flight_50/flight_130 swapped out for lacking adequate
   `analysis_3` detections. Re-derive the sample fresh: pick flights spanning that
   same offset range, checking availability against the TUNED-detections folder this
   time (126/149 flights). Note whether flight_50/flight_130 now have adequate data
   under the correct source — if so, it's worth mentioning in the log whether the
   original substitution was itself a symptom of the same bug, but you don't have to
   force them back into the sample. A sample size around 7-10 is fine — representative
   and fast to iterate, not exhaustive.

4. **Rerun** `triangulate_flight.py`'s 3-mode comparison (naive / paired_only /
   corrected) and the full `validate_sync_correction.py` validation across the
   reselected sample, using the corrected detections source.

5. **Do NOT overwrite the existing `data/sync_correction_validation/` output** — it's
   now a known-stale-input run, but still useful as a direct before/after comparison.
   Write this rerun's output to a new, clearly-named location, e.g.
   `data/sync_correction_validation_tuned_detections/`.

6. **Report a side-by-side comparison**: for any flight present in both the old and
   new validation sets, show old (stale, `analysis_3`) vs. new (tuned detections)
   point counts and per-mode RMS. Specifically address: does the "correction hurts at
   low point counts" finding from Checkpoint 2 still appear with the correct, denser
   data, or does it resolve? Re-run the same shift-magnitude sanity check
   (correction size should track the audit's measured per-flight offset) on the new
   results too.

7. **STOP at the checkpoint** (see below) and report the full comparison before
   concluding anything about whether/how to gate or smooth the sub-frame correction —
   that decision (from the 3 options discussed: minimum point-count gate, smoothed
   velocity estimate, or opportunistic per-point application) should only be made
   after seeing whether the original finding actually holds up with correct data.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

Do NOT do (unless explicitly asked later):
- ❌ Redesign the correction algorithm itself (velocity estimate method, correction
  direction convention, the 8.5ms gap cutoff) — this task is a data-source fix and
  rerun, not a redesign. If the low-point-count issue genuinely persists with correct
  data, report it and ask before changing the algorithm.
- ❌ Overwrite or modify `data/sync_correction_validation/` (the original run) — new
  output goes to a new location (step 5)
- ❌ Overwrite or delete `data/2026_07_21_gym/sync_audit.csv` or
  `sync_residual_vs_flight.png` — unaffected by this bug, no need to rerun
- ❌ Modify anything under `data/detector_tuning/detections/` or any flight's
  `analysis_3/` folder — both are read-only inputs
- ❌ Create a new log file — continue the existing one
- ❌ Commit anything to git

IF you think something else should be done that isn't covered above:
1. STOP
2. Log: "Considered doing [X] but it's not in scope — asking first"
3. Report and wait for a response

═══════════════════════════════════════════════════════════════════════════════
TIMING EXPECTATIONS
═══════════════════════════════════════════════════════════════════════════════

This is a path fix plus a rerun of an already-working pipeline on ~7-10 flights —
expect low single-digit minutes total, not more. STOP and investigate if any step
runs past ~5 minutes with no output change.

═══════════════════════════════════════════════════════════════════════════════
CHECKPOINT
═══════════════════════════════════════════════════════════════════════════════

After the rerun and comparison (steps 4-7): STOP, report the old-vs-new comparison
table, whether the low-point-count finding persists or resolves, and wait for
direction on how to proceed (including whether any of the 3 previously-discussed
mitigation options are even still needed) before doing anything further.

═══════════════════════════════════════════════════════════════════════════════
ERROR HANDLING
═══════════════════════════════════════════════════════════════════════════════

Expected (log, skip, continue):
- A flight in the reselected sample turning out to have no tuned-detections file
  after all — pick a different one spanning a similar offset, log the substitution.

Unexpected (STOP immediately):
- The tuned-detections file existing but producing wildly different point counts
  than the `flight_5: 19->37` pattern already confirmed (e.g. fewer points than
  `analysis_3` had) — would suggest the path or file being read is still wrong.
- Any of the core validation gates already built into `triangulate_flight.py` /
  `validate_sync_correction.py` failing (e.g. baseline far from ~850mm) — those gates
  already exist for a reason, don't bypass them.

═══════════════════════════════════════════════════════════════════════════════
GIT WORKFLOW
═══════════════════════════════════════════════════════════════════════════════

No git. Do not commit anything.

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ Detections now loaded from `data/detector_tuning/detections/
   03_stride1_thresh16_openk3_area30_circ0.3/2026_07_21_gym/`, not `analysis_3`
✅ Validation flight sample re-derived against the correct source's availability,
   still spanning the sync audit's offset range
✅ Rerun output written to a NEW location, not overwriting the original
   `data/sync_correction_validation/`
✅ Side-by-side old-vs-new comparison reported, explicitly answering whether the
   low-point-count finding still holds
✅ No decision made yet about gating/smoothing the correction — that waits for the
   checkpoint
✅ Existing worklog continued (not a new file), updated in real time throughout
✅ No commits made

═══════════════════════════════════════════════════════════════════════════════
START WORK
═══════════════════════════════════════════════════════════════════════════════

Begin now:
1. Read the existing sync-correction worklog in full, then the 3 existing scripts
2. Fix the detections-loading path
3. Re-pick the validation flight sample against the correct source's availability
4. Rerun the 3-mode comparison + validation, output to a new location
5. Report the old-vs-new comparison at the checkpoint and wait
```
