READ FIRST: claude/claude_rules.md

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Produce corrected feasibility + accuracy figures from the existing pipeline-sweep results, expressing the TRUE real-time constraint: total launch-to-prediction-ready time (t + latency) against each regime's crossing deadline. The current figures plot latency(t) alone, which drops the observation term t and makes feasibility look trivial. This fixes that.

CORE RELATIONSHIP (state in worklog, implement exactly):
- For a prediction made at cutoff t, the pipeline is ready at T_ready(t) = t + latency(t), measured on the launch-relative clock (t=0 = first-usable-fit-frame, SAME clock as the crossing deadline).
- Feasibility (actuation_lead = 0 per supervisor): T_ready(t) < deadline, i.e. margin(t) = deadline - t - latency(t) > 0.
- WORST-CASE pairing (this is the honest guarantee, not average-case): use p95 latency and the regime's worst-case-fast deadline. margin(t) = deadline - t - latency_p95(t).
- Deadlines per regime (launch-to-crossing, from 05_budget_by_elevation_bin):
    FLAT = 490ms  (min-anchored design target; P5=502 is thin-sample n=35, min=491 - use 490, note this)
    MID  = 710ms  (P5, n=12)
    LOB  = 1080ms (P5, n=60)

DATA SOURCE (read only, do NOT re-run the sweep):
- data/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv (2568 rows)
- and pipeline_sweep_summary_by_bin_T.csv (72 rows)
- latency per (flight,T) and its p95 per (bin,T), position error, velocity error per component, HIT/MISS, are all already in these. If per-component velocity is NOT in the raw CSV, STOP and report (do not re-run the Pi) - we'll decide how to get it.

OUTPUT: all new figures to data/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/figures2/

═══════════════════════════════════════════════════════════════════════════════
LOGGING
═══════════════════════════════════════════════════════════════════════════════

UPDATE existing worklog: claude/claude_logs/2026-08-04_1906_pi_prediction_pipeline_sweep_worklog.md (append a new dated section, do not overwrite).
- State the core relationship + worst-case pairing rationale.
- Paste the FULL numeric summary INLINE in the worklog (the equivalent of summary.txt content): per-regime, per-T table of T_ready median+p95, margin, max-usable-t, and position + per-component velocity error at the operating point. Do not just reference a file - the numbers go in the worklog text.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

1. Compute per (bin, T): latency median and p95, then T_ready_med = T + latency_med, T_ready_p95 = T + latency_p95, and margin_p95 = deadline - T - latency_p95.

2. Per regime, find MAX-USABLE-T = the largest T with margin_p95(T) > 0 (worst-case feasible cutoff). Report it. Also report accuracy (position + per-component velocity) AT that max-usable-t - this is the real operating point, not T=490 universally.

3. FIGURE 1 - MARGIN (headline feasibility), 1 panel, 3 regime curves:
   - x = cutoff t (ms); y = margin_p95(t) = deadline - t - latency_p95(t) (ms)
   - one line per regime (FLAT/MID/LOB), each using its OWN deadline
   - horizontal line at margin=0 (the feasibility boundary); shade margin<0 region
   - mark each regime's max-usable-t (zero crossing)
   - also plot margin_median as a lighter/dashed companion line per regime, so the p95 tail cost is visible
   - this answers "how much time to spare" directly on the y-axis

4. FIGURE 2 - FEASIBILITY as two-curve form (the attached-graph style, per regime, 3 panels):
   - x = cutoff t; y = time (ms)
   - per panel (one per regime): T_ready_med and T_ready_p95 rising curves, plus a horizontal dotted line at that regime's deadline
   - shade infeasible region (above deadline); mark max-usable-t
   - this is the "observation + full pipeline vs budget" view the user asked for, done with concurrent-detection latency

5. FIGURE 3 - POSITION ERROR at the operating point, 1 panel, 3 regime curves:
   - x = cutoff t; y = median position error (mm) with IQR band per regime
   - 100mm provisional threshold line
   - VERTICAL line at each regime's max-usable-t (from step 2) so the reader reads error at the feasible cutoff, not at an arbitrary T

6. FIGURE 4 - VELOCITY ERROR, 3 PANELS BY AXIS (X_world depth / Y_world width / Z_world up):
   - each panel: x = cutoff t; y = median velocity error for THAT component (mm/s); 3 regime curves (FLAT/MID/LOB)
   - VERTICAL line at each regime's max-usable-t
   - LABEL-PRECISION FLOOR per axis, drawn as a shaded band or horizontal line: X ~155mm/s, Z ~135mm/s (validated to label precision), Y ~282mm/s (UNRESOLVED - annotate that width velocity cannot be validated below this by the current label method). This visually caps how far down velocity accuracy can be claimed per axis.

7. All figures: dataviz skill conventions, light mode, static PNG, consistent regime colours across all four.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

- ❌ Do NOT re-run the Pi sweep - read existing CSVs only.
- ❌ Do NOT use median latency for the feasibility/margin boundary - the guarantee uses p95 (median may appear as a companion reference line only).
- ❌ Do NOT use 502ms for FLAT - use 490ms (state why: thin-sample P5, min-anchored).
- ❌ Do NOT plot latency(t) alone as the feasibility figure - feasibility is t + latency vs deadline.
- ❌ Do NOT present accuracy as ground truth - it's CONVERGENCE vs full-arc fit (placeholder); label every accuracy figure/section as such, and note the ~106mm label-vs-fit reference floor + the velocity label floors.
- ❌ Do NOT overwrite the worklog or existing figures/ - append to worklog, write to figures2/.
- ❌ No git.

IF per-component velocity error is not present in the existing CSVs: STOP and report - do not re-run the Pi to regenerate it, we'll decide.

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ margin_p95(t) computed per (regime,T); max-usable-t per regime reported
✅ Accuracy (position + 3 velocity components) reported AT each regime's max-usable-t, not just T=490
✅ Fig 1 (margin, headline), Fig 2 (feasibility 3-panel), Fig 3 (position error w/ operating-point lines), Fig 4 (velocity 3-panels-by-axis w/ label floors) in figures2/
✅ Worklog appended with core relationship + FULL numeric summary inline (not just a file reference)
✅ Accuracy labelled convergence-not-ground-truth throughout
✅ FLAT deadline = 490 (noted min-anchored), MID 710, LOB 1080

START WORK