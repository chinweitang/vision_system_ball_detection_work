# 2026-07-28 16:21 — Stratified reanalysis: observation-duration as primary axis, split at 1000ms

**Instructions:** Copy the block below and paste it into the same Claude Code session
that's been running the gravity-vs-drag trajectory fitting task.

---

```
READ FIRST: claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md
IN FULL (particularly the all-flights generalization, Checkpoint 2, and the
flight-duration-distribution follow-up) — this is a further cheap follow-up, no new
fitting/computation, just re-slicing and re-plotting data already in
`prediction_sweep_all_flights.csv` and `flight_durations.csv`.

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

The flight-duration distribution came back clearly bimodal (a shorter cluster
peaking ~600-650ms, a longer one ~1350-1450ms, with a low-density gap roughly
800-1150ms) — plausibly corresponding to this project's own already-documented two
actuation regimes (hits ~480ms vs. sets/receives ~1057ms, per `context.md` §6), not
an arbitrary artifact. Split at **1000ms** into two strata: "short" (<1000ms total
observable duration) and "long" (>=1000ms).

Separately: pooling all flights by lead-time alone was flagged as conflating
different difficulty regimes (a short flight forced to reach a given lead time has
much less data behind its fit than a long flight reaching the same lead time).
Observation-duration (how much was actually fit on) is the more scientifically
direct axis for "which model handles more/less data best," since it's the thing
that's actually varied, whereas lead-time is a leftover determined by each flight's
own arbitrary total length. Make observation-duration the PRIMARY comparison axis
going forward; keep lead-time as a secondary/operational view, but stratified now
too, so both views are actually fair within each duration regime.

═══════════════════════════════════════════════════════════════════════════════
LOGGING
═══════════════════════════════════════════════════════════════════════════════

Continue appending to
claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md — same
task, do not create a new log file.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

1. Join each flight's total duration (from
   `data/trajectory_fit_comparison/all_flights/duration_distribution/flight_durations.csv`)
   onto `prediction_sweep_all_flights.csv`'s rows, and assign each flight to the
   "short" (<1000ms) or "long" (>=1000ms) stratum. Report the resulting flight
   counts per stratum (expect long > short, per the histogram's visibly denser
   second cluster) — confirm this matches what you'd expect from the already-seen
   distribution before proceeding.

2. Confirm/reuse `fit_window_duration_ms` however it was established in the
   flight-duration-distribution task (check that task's own worklog entry for
   exactly how it was derived) — don't recompute it a different way.

3. **Primary output — observation-duration axis, stratified**: for each of the 2
   strata separately, produce the same pooled-scatter + binned-median/IQR-trend
   treatment as the original lead-time plot, but with `fit_window_duration_ms` on
   the x-axis instead of lead time. Pick representative observation-duration points
   for a summary table from each stratum's own actual achievable range (don't guess
   fixed numbers — a stratum's range differs from the other's) — same spirit as the
   existing lead-time summary table, adapted per stratum.

4. **Secondary output — lead-time axis, stratified**: the same pooled-scatter +
   trend treatment as the ORIGINAL `prediction_error_vs_leadtime.png`, but computed
   separately within each stratum instead of pooling all 158 flights together —
   directly shows whether stratifying resolves the original fairness concern, and
   answers the operational "how much lead time can I get, for this actuation
   regime" question properly per regime instead of conflated.

5. Carry over the RANSAC-health-flag visual distinction (different marker/color)
   into all 4 new plots, same convention as the original.

6. Report: within EACH stratum separately, does Model C still win at every
   representative point (both axes)? Does the ranking/gap size look similar to the
   unstratified all-flights result, or does it look meaningfully different once
   properly separated by duration regime? This is the actual point of doing this —
   say plainly whether stratifying changes the headline conclusion or just
   confirms it more rigorously.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

- ❌ Don't rerun any fitting/RANSAC/K-discovery — this only re-slices and re-plots
  already-computed data
- ❌ Don't overwrite the original `prediction_error_vs_leadtime.png` or
  `prediction_error_summary_table.csv` — new files, additive, per this whole
  project's established convention
- ❌ Don't touch Phase 1 or the pooled K — this is Phase 2 output analysis only
- ❌ Don't commit anything to git

═══════════════════════════════════════════════════════════════════════════════
OUTPUT LOCATION
═══════════════════════════════════════════════════════════════════════════════

New folder: `data/trajectory_fit_comparison/all_flights/stratified_by_duration/`
- `prediction_error_vs_obsduration_short.png` / `_long.png` (primary axis)
- `prediction_error_vs_leadtime_short.png` / `_long.png` (secondary axis)
- `stratified_summary_table.csv` (both strata, both axes, representative points)

═══════════════════════════════════════════════════════════════════════════════
START WORK
═══════════════════════════════════════════════════════════════════════════════

Begin now: join durations, assign strata, confirm counts, produce all 4 plots +
summary table, report whether the headline finding holds up within each stratum.
```
