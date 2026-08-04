# 2026-08-03 13:16 — Pi real-time: compute_mask breakdown + RANSAC iteration sweep

**Instructions:** Copy the block below and paste it into a fresh Claude Code session
in this repo if continuing this task in a new session. This session's own worklog
(`claude/claude_logs/2026-08-03_pi_realtime_benchmark_worklog.md`) and
`claude/decision_log.md` (entries 55-62) have the full decision trail if picking
this up later.

---

```
READ FIRST: claude/claude_rules.md, then claude/decision_log.md entries 55-62 (Pi
real-time benchmark section), then claude/claude_logs/
2026-08-03_pi_realtime_benchmark_worklog.md IN FULL. This is a direct continuation
of that task, not a new one — Stage 1 (end-to-end pipeline timing benchmark) and
Stage 2 (Pi-vs-laptop correctness diff) are DONE with clean results already in
data/pi_benchmarking/. Do not rebuild either — reuse their code and data.

═══════════════════════════════════════════════════════════════════════════════
CONTEXT (established, do not re-derive)
═══════════════════════════════════════════════════════════════════════════════

Stage 1 found two decisive real-time budget overruns on the Pi 5 hardware:
1. Detection: ~89ms/frame/camera vs the 16.6ms (60fps) budget — ~5.3x over.
   ~86-87ms of that is bundled inside detector_core.compute_mask() (threshold +
   morph-open 3x3 + morph-close 30x30 + exclusion), essentially flat across all 8
   sample flights. NOT yet subdivided further — compute_mask is one function, can't
   see which of its 4 internal steps dominates without new instrumentation.
2. Prediction: bare Model C fit is cheap (~22-101ms, fine against the ~480ms
   actuation budget), but the RANSAC-wrapped version (15 iterations, matching the
   real production RANSAC_N_ITERATIONS["C"] constant in trajectory_fit.py) costs
   ~335ms (short flights) up to ~1070-1176ms (long flights, N=72-89) — over 2x the
   entire actuation budget on its own for longer flights.

Stage 2: zero divergence between Pi (OpenCV 4.10.0) and laptop (OpenCV 4.13.0)
output — not a concern, don't re-check.

Freeze: 9 Aug 2026 (per Chin Wei directly, not context.md's stale "~6 Aug"). This
IS the current focus (O1/O2 done; this real-time characterization is the
remaining work) — not competing with mesh (O3). If it's still slow by freeze, that
becomes a documented limitation, not a blocker — so the goal is targeted,
time-bounded optimization investigation, not "solve it or bust."

Already discussed and decided (see decision log for full reasoning, don't
re-litigate): do the compute_mask breakdown AND the RANSAC sweep before
attempting a windowed/ROI detector (Chin Wei's idea, validated as sound in
discussion, but bigger effort + real accuracy risk — deferred, not dropped,
mentioned here so a later session doesn't lose track of it as a live option).

═══════════════════════════════════════════════════════════════════════════════
TASK 1 — compute_mask internal-phase breakdown
═══════════════════════════════════════════════════════════════════════════════

Confirm (or refute) that morph-close (30x30 elliptical kernel) is the dominant
cost inside compute_mask, not threshold/morph-open/exclusion. Time
threshold/morph-open/morph-close/exclusion SEPARATELY, on the Pi, on the same 8
flights already used in Stage 1 (src/pi_benchmarking/flights_manifest.json).

Do NOT modify detector_core.py (production code, needs permission per
claude_rules.md §2, and it's already-tuned/validated logic). Instead write a
timing-only instrumented mirror of compute_mask's exact cv2 call sequence
(threshold -> morphologyEx OPEN -> morphologyEx CLOSE -> apply_exclusion) as new
code in src/pi_benchmarking/, clearly commented as mirroring compute_mask
verbatim for diagnostic purposes only — same pattern already used for
label_vs_detection's small helpers before that got reversed in favor of full
reuse (decision 57) — this case is different because production code cannot be
touched but the mirror is trivial/low-drift-risk (4 cv2 calls in a fixed order,
not real tuned logic).

Follow the same validate-locally-first-then-run-on-Pi workflow already
established (see run_pi_benchmark.ps1's pattern). Add results to
data/pi_benchmarking/ and to the new timing_history.csv (see Task 3).

═══════════════════════════════════════════════════════════════════════════════
TASK 2 — RANSAC n_iterations sweep
═══════════════════════════════════════════════════════════════════════════════

Sweep n_iterations (reusing ransac_fit as-is, no code changes — just pass
different n_iterations values) across a reasonable range (e.g. 1,2,3,5,8,10,15),
measure real Pi compute time per value across the same 8 flights, and back-compute
what success probability each n_iterations value implies via the EXISTING
ransac_n_iterations() formula already in trajectory_fit.py (inverse direction: given
n_iterations and RANSAC_MIN_SAMPLES["C"]=8 and the project's own established
RANSAC_OUTLIER_FRACTION=0.15 assumption, what success_prob does that number of
iterations actually buy you?). This mirrors the reasoning already used once in
this codebase (decision 50) to choose RANSAC_OUTLIER_FRACTION/RANSAC_SUCCESS_PROB
for the offline Phase 2 sweep — same tradeoff, now for the Pi instead of the
laptop.

Scope check with Chin Wei before building (see open question in the conversation
this prompt was generated from): does this need an EMPIRICAL robustness check
against the known flight_22 hand-contamination case (see
claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md and
decision 49-50), or is the formula-based success-probability framing sufficient
for a first pass given the time budget? flight_22 is NOT in the current 8-flight
Stage-1 sample and would need adding if an empirical check is wanted.

═══════════════════════════════════════════════════════════════════════════════
TASK 3 — timing_history.csv
═══════════════════════════════════════════════════════════════════════════════

New file: data/pi_benchmarking/history/timing_history.csv, mirroring the real
existing convention (data/detector_tuning/history/results_history.csv — read it
first for the exact column style: date, stage, n_flights, headline metrics,
pointer-to-raw-artifact, free-text notes). One row per benchmark run. Backfill
today's two runs (Stage 1 baseline, Stage 2 correctness) before adding the new
compute_mask/RANSAC rows.

═══════════════════════════════════════════════════════════════════════════════
TASK 4 — clean tables/graphs for the thesis report
═══════════════════════════════════════════════════════════════════════════════

Once Tasks 1-2 have real numbers: tables for the low-variance detection-phase
breakdown (mean/median/p95/p99 per phase, vs the 16.6ms budget line) — a table
communicates this better than a chart, no real trend to show. One or two targeted
GRAPHS specifically for genuine trend stories: RANSAC cost vs N (with a 480ms
budget reference line, showing where it crosses) and the compute_mask
internal-phase breakdown (which step dominates). Load the `dataviz` skill before
writing any plotting code — do not hand-roll default-styled matplotlib charts for
a thesis report.

Keep logging in real time to claude/claude_logs/
2026-08-03_pi_realtime_benchmark_worklog.md and keep claude/decision_log.md
updated (continue numbering from 62) as new decisions get made — both explicitly
requested by Chin Wei as ongoing requirements for this task, not one-time asks.
```
