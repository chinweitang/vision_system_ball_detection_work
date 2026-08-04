READ FIRST: dev/claude_rules.md

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

On the Pi, measure the real-time prediction pipeline (parallel detection -> triangulation -> Model-C fit -> crossing-state prediction) as a function of prediction-cutoff time t, to answer: at the v1 universal 490ms deadline, how accurate is the crossing-state prediction (position + velocity + HIT/MISS) per elevation regime, and is the pipeline latency-feasible. Sweep t past 490ms to characterise what a regime-adaptive window (v2) would recover.

CONTEXT - read carefully, prior runs baked in wrong assumptions here:
- TWO-CLOCK MODEL. Frames arrive every 16.666ms (60fps) regardless of detection speed. Detection runs IN PARALLEL across cam0+cam1 (two threads), CONCURRENT WITH CAPTURE - NOT batched after a window closes. Per-pair detect ~9.5ms if parallelism holds: if <16.666ms, detection keeps pace with capture, no backlog, latency is capture-bound; if >16.666ms (e.g. serial ~19ms), backlog grows at (detect-16.666)ms/pair and latency becomes compute-bound. The test MUST measure per-pair detect latency relative to 16.666ms - that line is the pass/fail hinge.
- 3-FRAME DETECTION LAG: detection uses 3-frame differencing, so the system is always 1 frame (~16.6ms) behind the latest captured frame. Include this one-frame lag in the latency model.
- CLOCK: t=0 per flight = first-usable-fit-frame (SAME origin as the launch-to-crossing budget). 'Predict at cutoff t' = use each flight's points from t=0 through t=0+t only. The 490ms deadline is measured on THIS clock, per flight, not a global wall clock.
- GROUND TRUTH IS PLACEHOLDER: manual crossing-bracket labels are NOT ready yet. Use the FULL-ARC Model-C fit crossing state (from 01_/frozen classify) as the reference. This makes accuracy a CONVERGENCE result (early-cutoff prediction vs full-fit prediction), NOT ground-truth accuracy. Label every accuracy output as such. This test must be RE-RUN against manual labels later.
- Flights: crossers only (107, HIT + MISS_HIGH_WIDE) - only these have a crossing event. Full elevation regime (FLAT/MID/LOB per 02_ bins: <15 / 15-45 / >=45 deg).
- Data: the 8.7GB of flight frames is ALREADY on the Pi from the previous run - do NOT re-transfer. Verify presence first (du -sh) and STOP if missing.
- Model C, detector, RANSAC, calibration, triangulation: FROZEN, READ only.

═══════════════════════════════════════════════════════════════════════════════
LOGGING (DETAILED LEVEL)
═══════════════════════════════════════════════════════════════════════════════

Work log: dev/claude_logs/2026-08-04_[HHMM]_pi_prediction_pipeline_sweep.md
Follow dev/log_template.md. Real-time append. Log: measured per-pair parallel detect time (and whether it beat 16.666ms), thread-vs-process decision + measured speedup, per-t eligible-n, and per-regime accuracy at t=490ms.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

Work on the Pi. New subfolder for outputs: data/pi_benchmarking/02_pi_pipeline_sweep_parllel_detection/.

1. PARALLELISM FIRST (this decides everything downstream):
   - Implement detection of cam0+cam1 concurrently (two threads). Measure real per-pair detect time over a sample of flights.
   - Report the speedup vs serial. If speedup < 1.7x (GIL-bound / memory-contention), LOG it and try multiprocessing with shared-memory frames as a fallback; report which won.
   - State clearly whether per-pair detect is BELOW or ABOVE 16.666ms - this is the headline hinge.
   - CHECKPOINT: stop and report the per-pair number + speedup before running the full sweep. Wait for my go.

2. PIPELINE LATENCY MODEL (per flight, per cutoff t):
   latency(t) = time to produce the crossing prediction given points up to t, modelled as concurrent-with-capture:
     - if per-pair detect <= 16.666ms: latency ~= detect(last pair) + triangulate + fit + predict + one_frame_lag(16.6ms)  [capture-bound, compute hidden under cadence]
     - if per-pair detect > 16.666ms: add accumulated backlog = (N(t)-1)*(detect-16.666)  [compute-bound]
   where N(t) = number of frame-pairs from t=0 to t (~ t / 16.666).
   Measure the real compute components on the Pi (detect, triangulate, fit, predict); do NOT assume them.

3. SWEEP prediction-cutoff t. Range: from ~150ms up to the max crossing time (~1250ms), sensible step (e.g. 50ms).
   For each t, for each flight whose crossing time > t (still airborne):
     - fit Model C to that flight's points in [0, t] (reuse frozen fit code)
     - predict crossing state: position (Y,Z at plane) + velocity
     - compare to the full-arc-fit reference: position error (mm), velocity error, and predicted HIT/MISS vs reference HIT/MISS
   Record per (flight, t).

4. AGGREGATE + REPORT, split by elevation bin (FLAT/MID/LOB), NEVER pooled raw across regimes:
   - error(t) and HIT/MISS accuracy(t) per bin (median + IQR)
   - eligible_n(t) per bin (how many flights still airborne at t) - report explicitly, it's a result
   - latency(t) per bin vs the per-flight deadline
   - THE V1 HEADLINE: at t=490ms, per bin: HIT/MISS accuracy, position error median/IQR, velocity error, eligible_n (should be 107 total at 490ms), and latency-feasible? (yes/no per bin)
   - Acceptable-position-error threshold = 100mm (starting tolerance; label as provisional). Report, per bin, the smallest t at which median position error < 100mm AND HIT/MISS accuracy is high - i.e. t_min per regime.

5. FIGURES (dataviz conventions, light mode, static PNG):
   - accuracy(t) per bin, with t=490ms marked and eligible_n annotated
   - position error(t) per bin with 100mm threshold line
   - latency(t) vs 16.666ms cadence line + per-pair detect bar (the capture-bound vs compute-bound story)

6. STATE which constraint binds at 490ms: error or latency. Do not assume - read it off: is median error already <100mm with latency slack (error-bound / latency trivially met), or does latency exceed the deadline (latency-bound)? Report per regime.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

- ❌ Do NOT batch detection after the window - it must be modelled concurrent with capture (parallel, two cameras).
- ❌ Do NOT pool raw error/accuracy across elevation regimes - always split FLAT/MID/LOB.
- ❌ Do NOT treat accuracy as ground-truth - it's convergence vs full-fit reference until manual labels land. Label it.
- ❌ Do NOT re-transfer the 8.7GB (already on Pi) - verify and STOP if absent.
- ❌ Do NOT re-fit/re-tune Model C, RANSAC, detector, calibration - frozen.
- ❌ Do NOT include MISS_SHORT flights (no crossing event).
- ❌ Do NOT cap the sweep at 490ms - sweep the full t range; 490ms is one readout, the rest characterises v2.
- ❌ No git, no frozen-code edits (work around edge cases as before, log them).

IF per-pair parallel detect can't get below 16.666ms even with multiprocessing: do NOT hide it - that IS the finding (system is compute-bound), report it prominently at the checkpoint.

═══════════════════════════════════════════════════════════════════════════════
TIMING / CHECKPOINT / GIT
═══════════════════════════════════════════════════════════════════════════════

Expected ~20-30 min (Pi compute). CHECKPOINT after step 1 (parallelism measurement) - stop, report per-pair detect + speedup, wait for go before the full sweep.
STOP if: data missing, per-pair detect wildly off (>30ms suggests parallelism failed), or >10% flights fail to fit.
GIT: Option B - no git.

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ Real parallel per-pair detect time measured, speedup reported, stated above/below 16.666ms
✅ Latency modelled concurrent-with-capture with the 1-frame lag, components measured on Pi not assumed
✅ t swept full range; error(t), accuracy(t), eligible_n(t), latency(t) all per elevation bin
✅ V1 HEADLINE at t=490ms: per-regime HIT/MISS accuracy + position error + latency-feasibility, all 107 present
✅ Accuracy labelled as convergence-vs-full-fit (placeholder), flagged for re-run against manual labels
✅ Binding constraint (error vs latency) stated per regime, read off not assumed
✅ 3 figures + per-flight CSV + summary in 06_pi_pipeline_sweep/
✅ Work log complete, checkpoint respected

START WORK