# 2026-08-03 11:54 — Pi real-time benchmark (detect → triangulate → predict)

**Instructions:** Copy the block below and paste it into a fresh Claude Code session
in this repo if continuing this task in a new session. This session's own worklog
(`claude/claude_logs/2026-08-03_pi_realtime_benchmark_worklog.md`) has the live
progress if picking this up later.

---

```
READ FIRST: claude/claude_rules.md, then claude/context.md (full — this task touches
detection §4.5, triangulation §4.8, and prediction §5). Then read
src/image_processing/02_adjacent_frame_differencing/detector_core.py,
src/stereo/triangulate.py, and src/stereo/trajectory_fit.py IN FULL — this task
benchmarks their real, existing production logic on the Pi, and must import/reuse
it, not duplicate or reimplement it.

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

All detection and prediction analysis currently runs offline on the laptop, well
after a flight is over. There's no data on how fast the real chain — detect(cam0) →
detect(cam1) → triangulate → accumulate 3D points → fit a trajectory — actually runs
on the Raspberry Pi 5 hardware. This matters because O2 (prediction) and O4
(actuation, stretch) eventually need this whole chain to run live, and that only
works if it fits inside the real-time budget: detection against the 16.6ms/60fps
frame cadence, and the full observe→predict latency against the ~480ms actuation
timing budget (context.md §6).

Build an end-to-end pipeline replay benchmark that runs ON THE PI (SSH access
confirmed: `ssh -i ~/.ssh/id_volley chinnywei@192.168.50.1`, hostname volley-pi),
feeding it real pre-captured `ball_in_frame` frames as if they were arriving live —
NOT two disconnected benchmarks (detection alone, prediction alone fed some
independently-sourced point set) added up on paper afterward. That approach was
tried and rejected during planning: it can't capture interaction effects (thread/TBB
contention, memory pressure, scheduling) that only show up when things run together,
and it's easy to silently drop a real pipeline stage that way (triangulation was
missed in an earlier pass of this plan for exactly this reason).

Also verify the Pi's detection/triangulation OUTPUT matches the laptop's — the
laptop runs OpenCV 4.13.0, the Pi runs 4.10.0, a confirmed version mismatch. All of
the project's validated accuracy numbers (recall 0.9208, the 326-point Model-C
validation) were computed on the laptop build; a divergence on the Pi would be a
real finding, not just a benchmarking footnote.

Open architecture question this benchmark should help answer, not assume: does the
live predictor fit once (after accumulating enough points) or refit continuously as
new points arrive (rolling/incremental)? Nothing in the project has decided this —
Pattern A's offline validation only ever did single fits per N. Measure both a
single-shot fit and a rolling-refit replay, and let the measured cost of rolling
refit help decide whether it's viable.

--- Design decisions already made (do not re-litigate without new evidence) ---

- One end-to-end pipeline replay per flight: load real cam0+cam1 `ball_in_frame`
  frames + `timestamps.csv` into RAM (untimed), pair by nearest SensorTimestamp,
  warm up (untimed), then TIME (in real order): detect-cam0, detect-cam1 (both via
  detector_core.py, phase-by-phase: diff/threshold/morph-open/morph-close/
  exclusion/contours), triangulate the paired detection via triangulate.py's
  triangulate_points (using that session's real calibration_outputs/*.npz),
  append to a running 3D point stream. At checkpoints, call trajectory_fit.py's
  predictor: (a) single fit_drag_given_k at a realistic N (K fixed at the pooled
  5.27e-5 value per context.md §5), (b) the same wrapped in ransac_fit, (c) a
  rolling-refit replay (refit on every new pair using the real accumulated stream).
- Report mean/median/p95/p99/max per phase, not just mean — tail latency matters
  more than average for a real-time budget (claude_rules.md §5: measure each phase
  separately, one bottleneck at a time).
- Sequential single-cam-pair first, no concurrency yet — dual-cam/concurrent
  detection is a later, conditional stage only if warranted by these numbers.
- Flight sample: 6-8 flights spanning the ball_in_frame frame-count range (short
  ~30-frame through long ~90-frame), pulled from both 2026_07_21_gym and
  2026_07_15_gym sessions. No pre-existing named "spread sample" exists in-repo to
  reuse — pick fresh by sorting available flights by frame count and spreading
  across percentiles.
- File locations (confirmed with the project owner):
  - `src/pi_benchmarking/benchmark_pipeline_pi.py` — the Pi-side benchmark script
    (imports detector_core.py, exclusion_mask.py, triangulate.py, trajectory_fit.py;
    does not duplicate their logic).
  - `src/pi_benchmarking/run_pi_benchmark.ps1` — laptop-side orchestrator (follows
    the existing `capture_intrinsic.ps1` pattern: `$SSH_KEY = "$HOME\.ssh\id_volley"`,
    `chinnywei@192.168.50.1`). Selects flights, scp's cam0/cam1 ball_in_frame PNGs +
    timestamps.csv + the four reused modules + candidate_config.json + the relevant
    session's calibration_outputs/*.npz into a NEW `~/benchmark/` folder on the Pi
    (kept separate from `~/captures/` — do not touch/modify/delete anything already
    on the Pi), ssh-runs the benchmark, scp's the results JSON back.
  - `src/pi_benchmarking/compare_pi_vs_laptop_output.py` — Stage 2, runs the same
    detect→triangulate chain locally on the identical flights/config, diffs against
    the Pi's recorded output (detected/not-detected, 2D centroid delta per cam, 3D
    triangulated-point delta).
  - `data/pi_benchmarking/` — new results folder (parallel to `data/detector_tuning/`,
    per claude_rules.md §7 — diagnostic artifacts get their own folder, separate from
    real per-flight data). NEW files only; nothing existing under data/ is touched.
  - Real-time worklog: `claude/claude_logs/2026-08-03_pi_realtime_benchmark_worklog.md`
    (append after each significant step, per claude_rules.md §10 — note this repo's
    actual convention is `claude/claude_logs/`, not the `claude/logs/` path literally
    written in claude_rules.md §10, which is stale versus real practice).

--- Staged execution — build/validate incrementally, do not batch ---

1. Build benchmark_pipeline_pi.py + run_pi_benchmark.ps1, select the flight sample,
   locate the relevant calibration_outputs, transfer to the Pi, run it. CHECKPOINT:
   confirm it runs cleanly and every phase's timing looks sane before treating
   numbers as meaningful.
2. Build compare_pi_vs_laptop_output.py, run it, review the diff. CHECKPOINT:
   near-zero/exact match is expected; any systematic disagreement (given the
   confirmed 4.13.0-vs-4.10.0 gap) is a real finding to surface, not noise.
3. Interpret both results together against the 16.6ms detection budget and the
   ~480ms actuation budget, and decide what (if anything) is worth building next
   (concurrent cam0/cam1 detection, live-feed simulation, cheaper fit strategies).
   This decision is conditional on the real numbers from steps 1-2 — do not
   pre-build follow-up work before they're in hand.

Full rationale and grounding facts (Pi is Debian 13/trixie, 4 cores, OpenCV 4.10.0
NEON+TBB, boots to graphical.target; production config is
data/detector_tuning/candidate_config.json) are in the approved plan and this
session's worklog — read the worklog for anything not covered above.
```
