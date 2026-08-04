# 2026-08-03 16:00 — Rect vs ellipse close-kernel: Model C prediction-error comparison at fixed 430ms window

**Instructions:** Copy the block below and paste it into a fresh Claude Code session
in this repo if continuing this task in a new session. This session's own worklog
(`claude/claude_logs/2026-08-03_pi_realtime_benchmark_worklog.md`) and
`claude/decision_log.md` (entries 55-64) have the full decision trail if picking
this up later.

---

```
READ FIRST: claude/claude_rules.md, then claude/decision_log.md entries 55-64
(Pi real-time benchmark section, especially 63-64), then claude/claude_logs/
2026-08-03_pi_realtime_benchmark_worklog.md IN FULL. This is a direct
continuation — the Pi real-time investigation found that swapping
detector_core.compute_mask's close-kernel from cv2.MORPH_ELLIPSE to
cv2.MORPH_RECT (same 30x30 size) cuts that step's Pi timing 17.6x (84.05ms ->
4.77ms, would bring detection inside the 16.6ms/60fps budget), but a full
163-flight accuracy revalidation (decision 64) found this REGRESSES detection
accuracy: avg_combined_rate 0.9667->0.9452 (-2.15pp), labeled_recall
0.9250->0.8875 (-3.75pp), and 51% of individual flights regressed >2pp
(worst: flight_17 -10.23pp, flight_22 -9.89pp, flight_50 -9.30pp, flight_63
-9.09pp) — NOT concentrated in one obvious trajectory-geometry bucket.

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

The open question this task answers: does that detection-accuracy regression
actually matter for what's downstream and load-bearing — Model C
(gravity+drag) prediction error against the held-out final-point labels — or
does the trajectory-consistency filter + RANSAC absorb it? A ~2pp pooled
detection-rate drop could mean either "cosmetic, RANSAC handles it" or "a real
prediction-accuracy problem," and only measuring the actual downstream metric
answers which.

Compare Model C final-point prediction error between ellipse-kernel and
rect-kernel mask detections, at a FIXED fit window of 430ms (not the usual
N-sweep), across all 163 flights, twice per flight (once per detection
source), same held-out target methodology already established and validated
(src/stereo/trajectory_model_prediction_sweep_all_flights.py — reuse its
target-triangulation, frame-exclusion-for-leakage, and RANSAC-fallback logic
exactly, don't re-derive).

Two corrections to the original request already made and logged (see
worklog): (1) the rect-branch detections from the earlier validation run
were never persisted to CSV (only combined_rate + contact sheets were saved)
— regenerate them first, cheap and deterministic, same monkey-patch approach
as before (compute_mask_rect_close, now factored into a shared unnumbered
module — see below — since this is its 3rd use site, per claude_rules.md §3's
"extract shared logic rather than duplicate" convention). (2) Output goes
under data/trajectory_fit_comparison/rect_vs_ellipse_kernel/, NOT
data/pi_benchmarking/ (that's for Pi-timing results specifically; this is a
laptop-side accuracy/prediction question).

--- Implementation plan already designed, follow it rather than re-deriving ---

1. Extract compute_mask_rect_close() (the MORPH_ELLIPSE->MORPH_RECT-on-close-
   kernel-only mirror of detector_core.compute_mask, everything else
   identical) into a new unnumbered module:
   src/image_processing/02_adjacent_frame_differencing/compute_mask_rect_close_variant.py
   Update 12_run_full_dataset_rect_close_kernel.py to import it instead of
   defining it inline (this is MY OWN new file from this session, not
   pre-existing production code — safe to refactor). Do NOT touch
   detector_core.py.

2. New script (mirrors 11_generate_detections_csv.py's exact pattern/CSV
   format: frame_number,u,v, RAW un-filtered dc.run_detection() output,
   4-decimal formatting) to regenerate rect-kernel detection CSVs for all 163
   flights x 2 cams, monkey-patching dc.compute_mask via the extracted
   module. Output: data/detector_tuning/detections/12_rect_close_kernel/<session>/.
   No contact sheets needed this time (just CSVs, should be much faster than
   the earlier validation run).

3. New script under src/stereo/ adapting trajectory_model_prediction_sweep_all_flights.py:
   - A parameterized build_corrected_track_from_dir(session, flight_id,
     detections_dir, K0,D0,K1,D1,P0,P1, min_pairs=8) mirroring
     all_flights_common.build_corrected_track exactly, but taking
     detections_dir as an explicit argument instead of pulling it from the
     hardcoded SESSIONS[session]["detections_dir"] (needed since this must
     run against TWO different detections directories per flight, not the
     one all_flights_common.py hardcodes for the ellipse baseline).
   - Per flight, per variant (ellipse dir = existing
     data/detector_tuning/detections/03_.../, rect dir = the new one from
     step 2): build the track, triangulate the held-out final-point target
     (load_final_point_targets(), reused unmodified), exclude any fit point
     coinciding with the target's own frame (leakage guard, reused from the
     existing script's exact logic), then select N = the largest window
     where the LAST point's time t[N-1] <= 0.430s (fixed 430ms window, not
     an N-sweep — this is the one real methodological change from the
     existing script). Fit Model C via RANSAC (build_model_fit_predict("C",
     g_fixed, k_fixed=pooled_k), ransac_fit, with the SAME fallback-to-plain-
     fit behavior the existing script uses when the window is smaller than
     RANSAC_MIN_SAMPLES["C"]=8 — reuse fit_and_predict_ransac's exact
     pattern). Record error_mm = ||pred - target_xyz|| AND rejected_frac
     (fraction of the fit window RANSAC rejected) for each variant — the
     rejected_frac comparison is what answers "did RANSAC absorb it."
   - Skip/log flights where either variant can't produce a valid window (too
     few points, target before window starts, etc.) — same skip categories
     as the existing script, don't invent new ones.

4. Output, under data/trajectory_fit_comparison/rect_vs_ellipse_kernel/:
   - Pooled median/IQR error_mm for both variants (ellipse, rect).
   - Per-flight comparison CSV: session, flight, ellipse_error_mm,
     rect_error_mm, delta_mm (rect minus ellipse), ellipse_rejected_frac,
     rect_rejected_frac, flagged (delta_mm > threshold).
   - Regression threshold: use the ~250mm noise-floor figure Chin Wei gave
     as the anchor (cross-check it against the existing
     data/trajectory_fit_comparison/all_flights/phase2/
     prediction_error_summary_table.csv's Model C row nearest a plausible
     lead time before trusting it blindly — verify, don't just assume the
     hint is exactly right).
   - Explicit check: do flight_17, flight_22, flight_50, flight_63 (the
     worst DETECTION-rate regressions, session-qualified per the worklog:
     2026_07_15_gym/flight_17, 2026_07_15_gym/flight_22,
     2026_07_21_gym/flight_50, 2026_07_21_gym/flight_63) also show the
     largest PREDICTION-error regressions, or do their rejected_frac values
     show RANSAC compensating? Report this explicitly, don't bury it in the
     aggregate table.

Keep logging in real time to claude/claude_logs/
2026-08-03_pi_realtime_benchmark_worklog.md and claude/decision_log.md
(continue numbering from 64) as this proceeds — both ongoing requirements
for this task per Chin Wei, not one-time asks.
```
