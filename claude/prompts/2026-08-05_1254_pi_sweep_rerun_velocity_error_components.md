READ FIRST: claude/claude_rules.md

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Re-run the Pi prediction-pipeline sweep to persist PER-AXIS velocity error (signed, all 3 world components) for every (flight,T), which the original run discarded (only the scalar norm ||vel_own - vel_ref|| was saved). Then produce the 3-panel-by-axis velocity error figure into figures2/. Everything else about the sweep is unchanged - this is a targeted re-run to recover the per-component breakdown, not a redesign.

*** DATA SAFETY (READ FIRST): This task must NOT overwrite or delete ANY existing
file. Edit a COPY of the script, write results to NEW filenames, append to (never
overwrite) the worklog, write figures only to figures2/. The original script, the
original raw Pi output JSON, the existing CSVs, the existing figures/, the worklog
body, and the 8.7GB input flight frames on the Pi must all be left byte-for-byte
untouched. If any step would write to an existing path, STOP and report instead. ***

WHY: a scalar velocity norm hides which axis fails. Per-axis matters because (a) axes have different UX consequences for the rebounder return (X depth=arrival timing, Z up=panel height, Y width=lateral placement), and (b) the reference's own per-axis validity is NON-UNIFORM - X/Z are label-validated, Y is unresolved (label SD ~282mm/s). The plot must reflect that.

═══════════════════════════════════════════════════════════════════════════════
LOGGING
═══════════════════════════════════════════════════════════════════════════════

APPEND to claude/claude_logs/2026-08-04_1906_pi_prediction_pipeline_sweep_worklog.md (new dated section, do NOT overwrite existing content). Put the full per-axis numeric summary INLINE (per bin, per axis: bias and scatter at each regime's max-usable-t, plus the convergence trend). State the reference-validity caveat per axis explicitly.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

1. COPY prediction_pipeline_sweep_pi.py to a NEW file prediction_pipeline_sweep_pi_vaxis.py and modify ONLY the copy. Do NOT edit the original script.
   In the copy, in addition to the existing scalar velocity_error_mm_s, also persist, per (flight,T), the SIGNED per-axis error for each world component:
     err_vx = vx_own - vx_ref   (X_world, depth)
     err_vy = vy_own - vy_ref   (Y_world, width)
     err_vz = vz_own - vz_ref   (Z_world, up)
   Keep the SIGN (needed for bias). Also persist the raw vx/vy/vz for both own and ref so nothing is lost again. Do NOT change the fit, detection, RANSAC, T-grid, flight set, or any other logic - only ADD output columns.

2. Set the copy's raw output to a NEW filename: pipeline_sweep_full_vaxis_20260805.json (or similar NEW name). Do NOT overwrite pipeline_sweep_full_20260804.json or any existing sweep output. If the default output path in the copied script points at an existing file, change it before running.

3. Re-run the full 107-crosser x 24-T sweep on the Pi using the COPY (~14min, input frames already present, read-only). Verify 107/107. REGRESSION CHECK: confirm the scalar velocity_error_mm_s reproduces the original run's values for a couple of flights (same code path) - if it does NOT match, STOP (the minimal edit changed something it shouldn't have).

4. Aggregate per (bin, axis, T): mean signed error (BIAS) and RMS of signed error (SCATTER), plus median |error| if useful. Report BOTH bias and scatter - do not collapse to one number (bias is correctable, scatter is a floor).

5. FIGURE 4 - velocity error, 3 PANELS BY AXIS (X_world depth / Y_world width / Z_world up):
   - each panel: x = cutoff t; y = per-axis velocity error (mm/s); 3 regime curves (FLAT/MID/LOB)
   - show BIAS (signed mean) as the line and SCATTER (rms or IQR) as a band, so both are visible
   - VERTICAL line at each regime's max-usable-t (FLAT=300, MID=450, LOB=800, from margin_analysis.csv)
   - LABEL-PRECISION FLOOR per axis as a shaded horizontal band: X ~155mm/s, Z ~135mm/s (validated to label precision), Y ~282mm/s (UNRESOLVED - annotate: "reference Y velocity not validated by label method; convergence below this floor is not interpretable as accuracy")
   - title: CONVERGENCE vs full-arc fit, NOT ground truth; per-axis reference validity differs (X/Z validated, Y unresolved)
   dataviz conventions, light mode, static PNG, same regime colours as figures 1-3.

6. Write outputs ONLY to NEW paths under data/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/figures2/ :
   - figure4_velocity_error_by_axis.png
   - new per-axis raw + summary CSVs under NEW filenames (e.g. velocity_by_axis_raw.csv, velocity_by_axis_summary.csv)
   Do NOT overwrite pipeline_sweep_raw.csv, margin_analysis.csv, figures/, or any existing file.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

- ❌ Do NOT edit the original prediction_pipeline_sweep_pi.py - edit a COPY only.
- ❌ Do NOT overwrite pipeline_sweep_full_20260804.json or any existing raw/summary output - new filenames only.
- ❌ Do NOT delete ANY file, anywhere (no rm, no cleanup, no "freeing space"). If disk space is an issue, STOP and report.
- ❌ Do NOT modify or delete the input flight frames on the Pi - read-only.
- ❌ Do NOT change the fit / detection / RANSAC / T-grid / flight population - only ADD output columns.
- ❌ Do NOT save only |per-axis error| - keep the SIGN.
- ❌ Do NOT plot Y as if validated - label floor band + annotation must make clear Y convergence is not accuracy.
- ❌ Do NOT overwrite the worklog body or existing figures/ - append to worklog, write to figures2/.
- ❌ Do NOT present any of this as ground truth - convergence vs full-arc fit throughout.
- ❌ No git.

IF any write would land on an existing path, or the regression check fails, or disk space forces a deletion: STOP and report. Never resolve a conflict by overwriting or deleting.

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ Original script untouched; edits made to prediction_pipeline_sweep_pi_vaxis.py copy only
✅ Re-run raw output written to a NEW json; original 20260804 json intact
✅ Per-axis SIGNED velocity error persisted for all (flight,T); scalar norm regression-checked against old run
✅ 107/107 flights re-run successfully
✅ Per (bin,axis,T) BIAS and SCATTER aggregated (not collapsed)
✅ Figure 4: 3 panels by axis, bias+scatter, max-usable-t lines, per-axis label floors with Y-unresolved annotation
✅ Worklog appended (not overwritten) with full inline per-axis summary + per-axis reference-validity caveat
✅ New CSVs written under new names; NOTHING overwritten or deleted anywhere

START WORK