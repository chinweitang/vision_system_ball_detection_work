# 2026-07-28 17:09 — Decompose prediction error into world-frame axes (strong vs. weak)

**Instructions:** Copy the block below and paste it into the same Claude Code session
that's been running the gravity-vs-drag trajectory fitting task.

---

```
READ FIRST: claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md
IN FULL, particularly the all-flights generalization, stratified-by-duration
reanalysis, and the RANSAC investigation. This is a further follow-up on that task.
Also re-read claude/context.md §4.7-4.8 for the strong/weak axis framework this task
is built on (X = person-to-rebounder, STRONG; Y = width, WEAK — the axis the ±100mm
spec actually applies to; Z = vertical, STRONG).

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Every prediction-error number produced so far (the pooled lead-time plot, the
stratified observation-duration plots) is a flat 3D Euclidean distance
(`|predicted - target|`). That number can't tell you WHERE the error actually lives
— it could be mostly in the strong axes (already known to be precise to ~1-5mm from
the calibration work) or mostly in the weak/width axis (where the actual ±100mm spec
applies). Decompose it, using the world-frame registrations already built and
validated in this pipeline (reused, not recomputed) — this directly answers whether
the ~200mm error already found is actually close to spec on the axis that matters,
or genuinely far from it, before any further effort goes into reducing the raw
number.

**Design decisions:**
1. Reuse the EXACT same per-session/per-flight-range world-frame transform selection
   logic already built for `load_g_fixed()` (registration1 for `2026_07_21_gym`
   flights <=60, registration2 for >60, single registration for `2026_07_15_gym`) —
   don't rebuild this selection logic, and don't recompute the registrations
   themselves.
2. Check FIRST whether any intermediate per-row predicted-3D-point data from the
   original Phase 2 run was saved anywhere reusable, before assuming a full re-run
   is needed. If nothing was cached (likely, given
   `prediction_sweep_all_flights.csv`'s schema only has the final scalar
   `error_mm`), a re-run is unavoidable to recover the actual predicted point per
   row — but reuse the EXACT same RANSAC seed/config/pooled-K as the original run,
   so the new run's `error_mm` should reproduce IDENTICALLY to the existing CSV.
   Verify this reproduction explicitly — it's a strong, free sanity check that
   nothing else changed before trusting the new per-axis breakdown.
3. For each row, additionally record the SIGNED per-axis world-frame error
   (`error_x_mm`, `error_y_width_mm`, `error_z_mm` = the rotated
   `predicted - target` vector), not just the magnitude. Verify
   `sqrt(x^2+y^2+z^2) ~= error_mm` (already in the CSV) as a reconciliation check.
4. Reuse the SAME stratified structure already established (short/long at 1000ms,
   observation-duration as the primary axis) — this is an extension of that
   analysis, not a new one.

═══════════════════════════════════════════════════════════════════════════════
LOGGING
═══════════════════════════════════════════════════════════════════════════════

Continue appending to
claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md — same
task, do not create a new log file.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

1. Check for any reusable cached per-row prediction data (decision #2); if none,
   confirm you'll need to re-run the fitting.

2. Extend the Phase 2 script (or a copy of it) to additionally output the rotated,
   signed per-axis error per row, using the correct per-flight world-frame
   transform (decision #1). Re-run for the same 158 flights that succeeded
   originally, same RANSAC config/seed/pooled K.

3. **Verify reproduction**: confirm the new run's `error_mm` values match the
   existing `prediction_sweep_all_flights.csv` (within float precision) — report
   this explicitly before trusting anything downstream. If they don't match,
   STOP and investigate the discrepancy rather than proceeding.

4. Verify the axis-reconciliation identity (decision #3) holds.

5. Produce per-axis stratified plots: for each stratum (short/long), a multi-panel
   figure (3 subplots — X/person-rebounder, Y/width, Z/vertical) on the
   observation-duration axis, same pooled-scatter + binned-trend treatment as the
   existing stratified plots, per model (A/B/C). Mark the ±100mm line explicitly on
   the Y/width panel specifically — that's the actual spec line.

6. At the same representative observation-duration points already established per
   stratum (from `stratified_summary_table.csv`), report the Y/width-axis error
   specifically for Model C, and state plainly: is it inside or outside ±100mm at
   each of those points, for each stratum? This is the actual answer the whole
   analysis is for.

7. Report whether the X/Z (strong-axis) errors are, as expected, small/dominated by
   the width axis, or whether that assumption turns out to be wrong (report either
   way, don't force the expected answer).

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

- ❌ Don't recompute or modify the world-frame registration transforms themselves —
  reuse what's already validated
- ❌ Don't change the pooled K, RANSAC config, or any fitting logic — this task only
  adds an axis-decomposed OUTPUT to the same fits, it doesn't change how they're
  computed
- ❌ Don't skip the reproduction-verification step — if the re-run doesn't match the
  original `error_mm` values, nothing downstream can be trusted until that's
  understood
- ❌ Don't touch the RANSAC-threshold question (adaptive/MAD-based threshold) or the
  rejected-points 3D visualization — those are separate, already-identified
  follow-ups, not part of this task
- ❌ Don't commit anything to git

IF you think something else should be done that isn't covered above:
1. STOP
2. Log: "Considered doing [X] but it's not in scope — asking first"
3. Report and wait for a response

═══════════════════════════════════════════════════════════════════════════════
TIMING EXPECTATIONS
═══════════════════════════════════════════════════════════════════════════════

This re-runs the same fitting workload as the original Phase 2 batch (~948s / ~16min
parallelized, per the worklog) — expect similar, reuse `ProcessPoolExecutor` the same
way, no new timing pilot needed since the workload is already characterized.

═══════════════════════════════════════════════════════════════════════════════
GIT WORKFLOW
═══════════════════════════════════════════════════════════════════════════════

No git. Do not commit anything.

═══════════════════════════════════════════════════════════════════════════════
OUTPUT LOCATION
═══════════════════════════════════════════════════════════════════════════════

New folder: `data/trajectory_fit_comparison/all_flights/axis_decomposition/`
- `prediction_sweep_axis_decomposed.csv` (all rows, with the 3 new signed-axis columns)
- `axis_error_short.png` / `axis_error_long.png` (3-panel figures per stratum)
- `axis_summary_table.csv` (per-stratum, per-representative-point, per-model,
  per-axis)

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ Reproduction of the existing `error_mm` values confirmed before trusting the new
   per-axis data
✅ Axis-reconciliation identity verified
✅ Per-axis stratified plots produced, ±100mm marked on the width panel
✅ A plain answer: is Model C's width-axis error inside or outside ±100mm, at the
   established representative points, in each stratum
✅ Existing worklog continued, updated in real time
✅ No commits made

═══════════════════════════════════════════════════════════════════════════════
START WORK
═══════════════════════════════════════════════════════════════════════════════

Begin now: check for cached prediction data, re-run with axis output if needed,
verify reproduction, verify reconciliation, produce plots, report the width-axis
answer plainly.
```
