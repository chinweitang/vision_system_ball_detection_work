# 2026-08-03 20:50 — Rect-branch remeasurement + two-axis (fit-window W) Pi sweep

**Instructions:** Copy the block below and paste it into a fresh Claude Code session
in this repo if continuing this task in a new session. This session's own worklog
(`claude/claude_logs/2026-08-03_pi_realtime_benchmark_worklog.md`) and
`claude/decision_log.md` (entries 71-72) have the full decision trail if picking
this up later.

---

```
READ FIRST: claude/claude_rules.md, then claude/decision_log.md entries 63-70
(rect-close-kernel Pi speedup, its accuracy regression, RANSAC n_iterations
adopted at 3, inlier-threshold sweep, the 7-flight structurally-unstable
subset), then claude/claude_logs/2026-08-03_pi_realtime_benchmark_worklog.md
IN FULL, then data/consolidated_status_20260803.md for the synthesized
status. This is a direct continuation of tonight's Pi real-time
characterization work.

═══════════════════════════════════════════════════════════════════════════════
TASK — two things, in order
═══════════════════════════════════════════════════════════════════════════════

STEP 1 — remeasure, don't estimate, rect-branch full detection cost

The 9.78ms/frame/camera rect-branch total used for the throughput check was
assembled from separate measurement runs (diff/contours from the
ellipse-branch timing, mask from decision 63's rect branch) — not a direct
single measurement. Before this feeds a design decision, measure the real
rect-branch total (diff -> threshold -> rect-morph-open -> rect-morph-close
-> exclusion -> contours+moments) end-to-end, on the Pi, same 8-flight
benchmark set. Report median + p95, compare against the 9.78ms estimate,
flag the delta if any.

STEP 2 — two-axis Pi sweep, full pipeline, rect kernel, serial

Using the confirmed rect-branch cost from Step 1, RANSAC n_iterations=3
(decision 68), inlier threshold=75mm (decision 70):

Sweep fit_window_duration_ms (W) across a range from just above
RANSAC_MIN_SAMPLES["C"]=8 points' worth of frame-time up to 430ms — choose
reasonable steps (e.g. every ~50ms) covering that range.

At each W, on the Pi, full pipeline: detect (both cams, SERIAL — confirmed
sufficient per throughput check) -> triangulate -> RANSAC fit (Model C) ->
predict final point (position AND velocity, confirm the existing fit code
retains full ODE state at query time, not just position — check before
assuming).

For velocity ground truth, compute two independent estimates and report
both, don't collapse into one number:
(a) Model C fit on the FULL observed trajectory (not W-limited) for the
same flight, queried at the target time — note explicitly in output this is
a self-consistency check (same model, more data), not independent ground
truth.
(b) Finite-difference velocity from 2-3 consecutive DETECTED 3D points
straddling the target frame, no model involved — genuinely independent,
noisier.

Run across the same flight population used in the RANSAC sweeps
(duration>=430ms, ~150 flights) — for each W, only include flights where
the fit window is actually achievable (skip/flag flights where
total_duration_ms < W + some minimum buffer).

Output:
- Per W: detected point count (median), total pipeline time (detection sum
  + triangulation + RANSAC fit, median + p95), position error (median +
  IQR vs labeled target), velocity error via method (a) and method (b)
  separately (median + IQR each).
- State the largest W where (W + total pipeline compute time) stays under
  430ms, and report position/velocity error at that W as the headline
  design-target result.
- State whether methods (a) and (b) for velocity roughly agree or diverge
  meaningfully — if they diverge, flag it rather than picking one as
  authoritative.

Save raw per-run data. Generate three figures using the dataviz skill: (1)
W vs time consumed [observation + compute stacked/overlaid] against 430ms
line, (2) W vs position error, (3) W vs velocity error [both methods].
Don't touch detector_core.py or trajectory_fit.py — this exercises existing
production config, doesn't change it.

Keep logging in real time to claude/claude_logs/
2026-08-03_pi_realtime_benchmark_worklog.md and claude/decision_log.md
(continue numbering from 70) as this proceeds — both ongoing requirements
for this task per Chin Wei, not one-time asks.
```

---

## Actual result (for traceability — not part of the reusable prompt above)

Step 1: confirmed accurate, 9.794ms median vs 9.78ms estimate (+0.1%).

Step 2: swept W in [150,200,250,300,350,400,430]ms, 150 flights, full
pipeline on the Pi. **No W in the swept range clears the 430ms budget at
p95** — W=150ms narrowly clears it at the median only (418.2ms vs 436.1ms
p95). Detection (serial cam0+cam1, ~19ms/point even with the fast rect
kernel), not RANSAC, is the dominant cost at every W (71-79% of total
compute) — this reverses the session's earlier RANSAC-focused framing.
Velocity methods (a)/(b) diverge ~31x, reported as an open gap rather than
resolved. Full writeup: claude/decision_log.md entry 72; data:
data/pi_benchmarking/two_axis_sweep/.
