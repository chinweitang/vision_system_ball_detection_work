# 2026-07-28 12:20 — Generalize gravity/drag model comparison to all ~163 flights

**Instructions:** Copy the block below and paste it into the same Claude Code session
that's been running the gravity-vs-drag trajectory fitting task.

---

```
READ FIRST: claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md
IN FULL — this is a direct continuation of that task (Phase 0 consolidation, Phase 1
K-discovery, Phase 2 prediction sweep, then RANSAC validated on flight_01/flight_22
only). This task generalizes Phases 1-2 to every eligible flight across both
sessions, now that RANSAC is validated. Do not rebuild anything already working —
reuse trajectory_fit.py, drag_k_discovery.py, trajectory_model_prediction_sweep.py,
and ransac_fit.

Also read claude/claude_logs/2026-07-25_flight_velocity_angle_binner_worklog.md's
flight-enumeration section (for the multi-session eligible-flight list — 126 flights
in 2026_07_21_gym + 37 in 2026_07_15_gym = 163 total) and
src/stereo/pixel_velocity_correction.py in full (for `build_corrected_pairs()` —
needed now, see decision #3).

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Generalize K-discovery and the prediction sweep from the flight_01/flight_22 pilot
to every eligible flight in both sessions, producing one aggregate answer to "does
drag help, and by how much, across the real dataset" instead of a 2-flight anecdote.

**Design decisions already made — do not re-litigate:**

1. **K-discovery now runs on TUNED DETECTOR points, not manual labels** — labels
   only exist for flight_01/flight_22; every other flight has no choice but detector
   output. This is exactly why RANSAC had to be validated before this step: a
   contaminated flight's detector points could otherwise corrupt the one shared K
   used by every flight's Model C fit. Apply RANSAC (validated settings from the
   prior task) to every flight's full-track fit before it contributes to K.

2. **Per-flight refined K, only where inlier count supports it.** After RANSAC
   gives a flight's inlier set, only attempt a per-flight nonlinear free-K refit if
   that flight has enough inliers to trust it (at least ~20-25 — same "don't trust
   a nonlinear fit on too few points" lesson as everywhere else this session; adjust
   and note if evidence suggests a different cutoff). Flights below that get
   "insufficient data for individual K" rather than a misleading number — they still
   contribute to the pooled fit (decision #4), just not to the per-flight diagnostic.
   Record each such flight's fitted `|v0|` (initial speed) alongside its K, to check
   whether K correlates with launch speed (a real pattern Zhang et al. report in the
   literature — K ranging ~0.12-0.18 as a function of velocity, not just noise).

3. **Apply timestamp pairing + pixel-velocity correction to the early-window
   triangulation now, not just to the final-point labels.** The held-out targets
   (`data/final_point_labels/final_point_labels.csv`) were already labelled with
   correct nearest-timestamp cam0/cam1 pairing. The early-window fitting data (both
   K-discovery's full-track points and Phase 2's fit windows) currently still uses
   naive same-`frame_index` pairing via `label_vs_detection.triangulate()`'s input
   construction. Fix this now: build the paired point arrays via
   `pixel_velocity_correction.build_corrected_pairs()` (filter → nearest-timestamp
   pairing → sub-frame correction) before calling `triangulate()`, so the input the
   model is fit on is prepared the same way the target it's predicting toward was.

4. **Final K = one joint nonlinear fit across ALL flights simultaneously** (shared
   K, separate `p0,v0` per flight — same principle as the 2-flight pooling, just
   scaled up), using each flight's RANSAC inlier points. This is required regardless
   of the per-flight diagnostic in decision #2 — it's how Phase 2 gets its one fixed
   K.

5. **Results aggregation**: pool every `(flight, N)` result into one scatter per
   model — x-axis `lead_time_ms` (NOT raw N — different flights have different
   frame densities/lengths, so N isn't comparable across flights, exactly the
   lesson from the binner's own N=5/10-vs-N=20/30 problem), y-axis `error_mm` —
   with a binned median/IQR trend line per model overlaid. Plus a summary table:
   median and p90 error per model at a handful of representative lead times (e.g.
   100/300/500/1000ms). Exact filenames for this and every other output are in the
   OUTPUT FILES section below — that section is the authoritative list, don't
   improvise different names/locations.

6. **RANSAC health-check flag**: for each `(flight, model, N)`, compute the
   rejected-point fraction, bucket by lead-time (not raw N), and flag a flight as
   anomalous only if its rejection fraction is a real outlier relative to OTHER
   flights in the same lead-time bucket (not a fixed ceiling — a fixed ceiling would
   false-flag the already-understood large-N/full-arc-spread effect found on
   flight_22, which is benign, not a new problem). Also separately count and report
   RANSAC convergence failures per flight (already logged, currently just falls
   through to NaN) as their own QA signal.

7. **Timing discipline — this is a much bigger job than the 2-flight pilot.** Time
   a small sample (~10 flights) through the FULL pipeline (RANSAC K-discovery +
   RANSAC prediction sweep) BEFORE committing to all 163, and extrapolate. If the
   projection is large, parallelize per-flight via `ProcessPoolExecutor` — matching
   the established convention already used elsewhere in this project for exactly
   this kind of multi-flight batch job (`07_artifact_audit.py`, `10_run_full_dataset.py`).
   Do not just kick off a 163-flight serial loop and hope — this exact mistake (a
   30+ minute projection caught only by timing a sample first) already happened once
   in the 2-flight RANSAC task; don't repeat it at 80x the scale.

8. **Checkpoint 1 is conditional, not automatic** — same principle as Phase 0 in
   the earlier task (claude_rules.md §4: mechanical/verifiable work goes straight
   through, only stop if something's actually wrong). Now that RANSAC and the
   pooling methodology are both already validated on flight_01/flight_22, there's a
   trusted reference point to check the generalized result against — this isn't a
   first-time judgment call anymore. Proceed straight into Phase 2 WITHOUT stopping
   if all of the following hold; STOP and report only if one doesn't:
   - The final pooled K is within 2x of the 2-flight pilot's K (6.053818e-05 1/mm)
     in either direction
   - Fewer than ~30% of flights ended up "insufficient data" for an individual K
   - The RANSAC health-check (decision #6) doesn't flag an unusually large fraction
     of flights during Phase 1's own fitting
   If continuing automatically, still log the full Phase 1 summary (per-flight K
   distribution, velocity-correlation result, pooled K) before moving on — the
   point is skipping the wait-for-a-human pause, not skipping the reporting.

═══════════════════════════════════════════════════════════════════════════════
OUTPUT FILES — the complete list, exact paths (all new, none overwrite the pilot)
═══════════════════════════════════════════════════════════════════════════════

Everything below lives under `data/trajectory_fit_comparison/all_flights/` (new
folder — `phase1/`/`phase2/` from the pilot stay untouched as the reference point).

**`all_flights/phase1/`:**
- `k_sweep_pooled.csv` + `residual_vs_K_pooled.png` — a coarse (~15-20 point) sweep
  of the JOINT weighted-across-all-flights residual vs. candidate K, with the final
  joint-fit K marked — the aggregate equivalent of the pilot's `residual_vs_K_ransac.png`,
  showing whether the population-level K optimum is well-defined or flat.
- `per_flight_k.csv` — one row per eligible flight: flight id, session, RANSAC
  inlier count, per-flight refined K (or "insufficient_data"), fitted `|v0|`.
- `per_flight_k_distribution.png` — histogram of per-flight K (flights with enough
  data only).
- `k_vs_velocity.png` — scatter of `|v0|` vs. per-flight K, correlation coefficient
  annotated (the literature-motivated check from this task's design).
- `models_full_arc_residual_all_flights.csv` — per-flight, per-model (A/B/C)
  full-arc RANSAC residual (raw data).
- `models_full_arc_residual_distribution.png` — box/violin plot of full-arc
  residual by model across all flights (a 163-flight bar chart isn't readable —
  this is the distribution equivalent of the pilot's grouped-bar chart).
- `ransac_rejection_summary.csv` — per-flight, per-model rejection fraction and
  convergence-failure flag from Phase 1's own fitting (feeds decision #8's
  Checkpoint-1 condition).

**`all_flights/phase2/`:**
- `prediction_sweep_all_flights.csv` — every `(flight, N, model, source)` row, the
  full raw data everything else derives from.
- `prediction_error_vs_leadtime.png` — the main result: pooled scatter
  (`lead_time_ms` vs. `error_mm`) with a binned median/IQR trend line per model
  (A/B/C). Only 2 of the 163 flights (flight_01, flight_22) have manual labels —
  their label-track curves are already shown in the pilot's own
  `phase2/prediction_sweep_flight_01/22.png`, not re-needed here — so this
  aggregate plot is the DETECTOR-track population result specifically, not a
  label-vs-detector comparison (there isn't enough label data at this scale for
  that to mean anything population-wide). Mark this in the plot title so it isn't
  mistaken for a repeat of the pilot's label/det comparison. RANSAC-health-flagged
  points (decision #6) should be visually distinguished (different marker/color),
  matching the flagged-point convention already used in the binner's own
  distribution plots.
- `prediction_error_summary_table.csv` — median and p90 error per model at
  representative lead times (100/300/500/1000ms).
- `ransac_health_flags.csv` — every flagged `(flight, model, N)` with its rejection
  fraction and the same-lead-time-bucket baseline it was compared against, so any
  of them can be looked at individually afterward.

═══════════════════════════════════════════════════════════════════════════════
LOGGING
═══════════════════════════════════════════════════════════════════════════════

Continue appending to
claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md — same
task, do not create a new log file. Update continuously (before starting a sub-step
as well as after, narrate debugging/dead-ends as they happen, don't batch — this
task's own established logging convention).

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

1. Read the materials listed at the top. Confirm the eligible-flight list (163)
   matches the binner's own recorded count before proceeding — if it doesn't,
   investigate the discrepancy rather than silently using a different number.

2. Time a ~10-flight sample through the full pipeline (RANSAC K-discovery +
   corrected-pairing triangulation + RANSAC prediction sweep) and extrapolate to
   163. Parallelize via `ProcessPoolExecutor` per flight if the projection is large.
   Report the estimate before committing to the full run.

3. **Phase 1, generalized**: for every eligible flight, build corrected-paired
   detector points (decision #3), run RANSAC per model (A/B/C) on the full track,
   reuse Model C's inlier set for that flight's K-sweep, and — where inlier count
   supports it (decision #2) — a per-flight refined K. Record each flight's `|v0|`
   alongside its K for the velocity-correlation check.

4. Fit the final pooled K via one joint nonlinear fit across all flights'
   RANSAC-inlier points (decision #4).

5. Produce all `phase1/` outputs per the OUTPUT FILES section above, and report
   the velocity-vs-K correlation finding, the per-flight K distribution (including
   how many flights had "insufficient data"), and the final pooled K.

6. **Checkpoint 1 — conditional (decision #8)**: log the full Phase 1 summary
   regardless. STOP and wait for direction only if one of decision #8's three
   conditions fails; otherwise proceed straight into Phase 2 with the pooled K.

7. **Phase 2, generalized**: for every eligible flight, use its final-point label
   — from `data/final_point_labels/final_point_labels.csv` (columns: `session,
   flight, cam, frame_number, ..., centroid_x, centroid_y, diameter_px`) — as the
   held-out target: triangulate that flight's labelled cam0/cam1 pair (already
   correctly timestamp-paired at labelling time) to get the target position. Sweep
   N (per-flight, same mechanism as before), fit Models A/B/C with RANSAC (K fixed
   from step 4/Checkpoint 1) on the DETECTOR track for every flight — only
   flight_01/flight_22 have a label track at all, so there is no population-scale
   "label vs. detector" comparison to make here (that comparison stays a 2-flight
   thing, already captured in the pilot's own outputs). Apply the RANSAC
   health-check flag (decision #6).

8. Produce all `phase2/` outputs per the OUTPUT FILES section above: the pooled
   scatter + binned trend, the summary table, and the RANSAC health-check flags
   with enough detail to look at any flagged flight individually.

9. All outputs go under `data/trajectory_fit_comparison/all_flights/` per the
   OUTPUT FILES section — do not touch or overwrite the existing `phase1/`/`phase2/`
   folders (those are the validated 2-flight pilot, keep them as a reference point).

10. **STOP at Checkpoint 2**: report the full aggregate finding — does drag help,
    by how much, at which lead times, across the real dataset — plus the
    velocity-correlation result and any flagged flights. This is the actual headline
    answer the whole exercise has been building toward.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

Do NOT do (unless explicitly asked later):
- ❌ Overwrite anything under `data/trajectory_fit_comparison/phase1/` or `phase2/`
  — new output goes in `all_flights/` (decision from step 9)
- ❌ Skip the timing pilot and just run all 163 flights serially — time a sample
  first, parallelize if needed (decision #7)
- ❌ Use a fixed rejection-rate ceiling for the RANSAC health check — compare
  against other flights at similar lead time (decision #6)
- ❌ Refit K per-window in Phase 2 — still held fixed at the Checkpoint-1 result,
  same as the pilot
- ❌ Modify `pixel_velocity_correction.py`, `trajectory_fit.py`'s existing
  functions, or the flight-enumeration logic — reuse them
- ❌ Commit anything to git

IF you think something else should be done that isn't covered above:
1. STOP
2. Log: "Considered doing [X] but it's not in scope — asking first"
3. Report and wait for a response

═══════════════════════════════════════════════════════════════════════════════
TIMING EXPECTATIONS
═══════════════════════════════════════════════════════════════════════════════

Unknown until the step-2 pilot measurement — that's the point of doing it first
rather than assuming. As a rough anchor: the 2-flight pilot (one short, one
~90-frame-window flight) took ~2.5 minutes for Phase 2 alone; 163 flights of mixed
length, run serially, would clearly blow past any reasonable budget — parallelize
per decision #7 rather than accepting a long serial run.

═══════════════════════════════════════════════════════════════════════════════
CHECKPOINTS
═══════════════════════════════════════════════════════════════════════════════

Checkpoint 1 (after generalized Phase 1) is CONDITIONAL, not automatic — per
decision #8, log the full summary (per-flight K distribution, velocity-K
correlation, final pooled K) regardless, but only STOP and wait if one of the 3
named conditions fails. Otherwise proceed straight into Phase 2.

Checkpoint 2 (after generalized Phase 2) always stops: full aggregate result,
RANSAC health-check flags. Wait before considering this done — this is the
headline finding, always worth a human look before calling it final.

═══════════════════════════════════════════════════════════════════════════════
ERROR HANDLING
═══════════════════════════════════════════════════════════════════════════════

Expected (log, skip that flight, continue):
- A flight with too few RANSAC inliers for a per-flight K (decision #2) — contributes
  to the pooled fit only, logged as "insufficient data," not treated as an error.
- A flight missing a final-point label or tuned-detections file — skip, log, don't
  abort the batch.

Unexpected (STOP immediately):
- The eligible-flight count not matching the binner's recorded 163 (step 1)
- The step-2 timing pilot projecting an unreasonable total (e.g. many hours) even
  after parallelizing — investigate the bottleneck rather than just letting it run
- Any systematic difference between this task's Model A reproduction and the
  pilot's numbers for flight_01/flight_22 specifically (would indicate the
  corrected-pairing change broke something for the flights it's already validated on)

═══════════════════════════════════════════════════════════════════════════════
GIT WORKFLOW
═══════════════════════════════════════════════════════════════════════════════

No git. Do not commit anything.

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ Timing measured on a sample before committing to the full run; parallelized if
   the projection warranted it
✅ Phase 1 generalized to all eligible flights, using RANSAC-cleaned detector
   points and corrected cam0/cam1 pairing throughout
✅ Per-flight K computed only where inlier count supports it; velocity-correlation
   check reported with real numbers, not just "should be checked"
✅ Final K from one joint fit across all flights' inliers
✅ Phase 2 generalized, aggregated by lead time (not raw N) across all flights,
   with the pooled-scatter-plus-trend visualization and summary table
✅ RANSAC health-check flags only anomalies relative to same-lead-time peers, not
   the already-understood large-N effect
✅ All 12 files named in the OUTPUT FILES section exist at their exact specified
   paths under `data/trajectory_fit_comparison/all_flights/{phase1,phase2}/`;
   existing pilot outputs untouched
✅ Existing worklog continued, updated in real time throughout
✅ No commits made

═══════════════════════════════════════════════════════════════════════════════
START WORK
═══════════════════════════════════════════════════════════════════════════════

Begin now:
1. Read the worklog, the binner's flight-enumeration section, and
   pixel_velocity_correction.py in full
2. Confirm the 163-flight eligible list matches the binner's count
3. Time a ~10-flight sample through the full pipeline, extrapolate, parallelize if
   needed
4. Run generalized Phase 1 — log the summary; stop only if a Checkpoint-1 red-flag
   condition (decision #8) is tripped, otherwise continue straight on
5. Run generalized Phase 2, report at Checkpoint 2, wait
```
