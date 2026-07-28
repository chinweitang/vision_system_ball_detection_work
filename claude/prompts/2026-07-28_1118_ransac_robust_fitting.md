# 2026-07-28 11:18 — RANSAC-robustify Models A/B/C, validate on flight_01/flight_22 only

**Instructions:** Copy the block below and paste it into the same Claude Code session
that's been running the gravity-vs-drag trajectory fitting task.

---

```
READ FIRST: claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md
IN FULL — this is a direct continuation of that task, not a new one. You already
built trajectory_fit.py (Models A/B/C), drag_k_discovery.py (Phase 1), and
trajectory_model_prediction_sweep.py (Phase 2), and produced
data/trajectory_fit_comparison/{phase1,phase2}/*. Do not rebuild any of that —
reuse it.

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Add RANSAC-robustified fitting to trajectory_fit.py and use it to test one specific,
confirmed bug: flight_22's Phase 2 detected-points curves show a sharp error spike
around N≈44-46, traced (via the contact sheet) to the detector picking up a person's
hand for several consecutive frames — a real contamination point, not noise.

**Scope is deliberately limited to flight_01 and flight_22 — do NOT generalize to
all flights in this task.** That's a separate, later step, for two reasons: (1) it
keeps this a clean one-variable test (does RANSAC fix the KNOWN case) rather than
conflating "does RANSAC work" with "what does it do across 163 flights," and (2) at
that scale the right visualization is an aggregate/distribution question, not more
per-flight line charts — a different task's problem, not this one's.

**Design decisions already made — do not re-litigate:**
1. RANSAC applies to all 3 models (A/B/C), not just C — otherwise you can't tell
   whether Model C looks better because of drag or because only it got robustified.
   Expect it to NOT fix Model A's low-N blowup (that's underdetermination — too few
   points for 9 free parameters — a different failure mode than outlier
   contamination; robust fitting doesn't address it, and shouldn't be expected to).
2. Inlier threshold: 75mm (comfortably above the ~15-50mm RMS seen on clean flights,
   well below the hundreds-to-thousands-of-mm scale of the known contamination).
   Adjust and note if evidence suggests otherwise, don't treat this as untouchable.
3. Log exactly which frames get rejected per flight per model — the point is to
   verify RANSAC caught the SPECIFIC known contamination (confirm it rejects
   flight_22's hand-pickup frames specifically), not just that some aggregate number
   improved for an unrelated reason.
4. Do NOT overwrite the existing plain-fit outputs
   (`models_full_arc_residual.png/.csv`, `residual_vs_K.png`,
   `prediction_sweep.csv`, `prediction_sweep_flight_01/22.png`) — write new,
   clearly-named files alongside them so both are directly comparable.
5. Keep graphs readable via small multiples, not more overlaid lines on one axis:
   - `residual_vs_K_ransac.png`: one panel per flight_01/flight_22/pooled, each
     panel just 2 lines (plain vs. RANSAC) — not 6 lines on one axis.
   - `models_full_arc_residual_ransac.png`: same grouped-bar shape as the original,
     with each model's bar paired with its RANSAC variant next to it.
   - `prediction_sweep_ransac_flight_01/22.png`: one row of 3 subplots (one per
     model), each showing that model's plain-vs-RANSAC pair (label and det).
   - `prediction_sweep_ransac_zoom_flight_22.png`: a focused before/after pair
     zoomed on the N≈40-50 region specifically, since that's the one confirmed
     case — this one matters more than the comprehensive view.

═══════════════════════════════════════════════════════════════════════════════
LOGGING
═══════════════════════════════════════════════════════════════════════════════

Continue appending to
claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md — same
task, do not create a new log file. Update continuously as you work (per that
task's own logging instructions — before starting a sub-step as well as after,
narrate debugging/dead-ends as they happen, don't batch).

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

1. In `trajectory_fit.py`, add a generic `ransac_fit(t, xyz, fit_fn, predict_fn,
   min_samples, inlier_threshold_mm, n_iterations, random_seed)` wrapper: repeatedly
   sample `min_samples` random points, call `fit_fn` on that subset, use
   `predict_fn` to check every point's residual against the candidate fit, track
   the largest inlier set found, then do one final `fit_fn` call on that winning
   inlier set. Return the fitted params, the residual on the inlier set, and the
   accepted/rejected frame-number lists. This must work uniformly for Model A/B
   (linear fits) and Model C (nonlinear) — the wrapper only needs `fit_fn`/`predict_fn`
   to share a consistent calling convention, it doesn't need to know which kind of
   fit is underneath.
   - Pick `min_samples` sensibly per model (more than the bare theoretical minimum,
     consistent with this session's own established lesson that too-few-point
     nonlinear fits are unstable) — but small enough to leave room for outliers
     within each flight's actual point count (27 for flight_01, 93 for flight_22).
   - Compute `n_iterations` from the standard RANSAC formula
     (N = log(1-p)/log(1-(1-e)^s) for a target success probability p and an assumed
     worst-case outlier fraction e) rather than picking an arbitrary round number —
     show your reasoning/inputs in the log.
   - Fix and log a random seed for reproducibility.

2. **Phase 1**: for each flight, run RANSAC once per model to get that flight's
   accepted/rejected split (for Model C, use the already-known refined K from the
   existing run as the reference model for identifying inliers — re-running full
   RANSAC at every K-sweep grid point would be needlessly expensive and isn't
   necessary for what this test is checking). Reuse that same accepted-points set
   to recompute: the K-sweep curve (plain fit, RANSAC-selected points only) and
   Models A/B's full-arc residual, so `residual_vs_K_ransac.png` and
   `models_full_arc_residual_ransac.png` (+ matching CSVs) show plain vs. RANSAC
   side by side per decision #5.

3. **Phase 2**: for each flight, each N, each model, each data source (label/det),
   fit via `ransac_fit` instead of the plain fit. Record errors the same way the
   existing `prediction_sweep.csv` does, in a new `prediction_sweep_ransac.csv`.
   Produce `prediction_sweep_ransac_flight_01/22.png` and the zoomed flight_22
   comparison per decision #5.

4. **Verify the specific claim**: confirm in the log whether RANSAC actually
   rejected flight_22's known hand-pickup frames (the ones identified via the
   contact sheet, around N≈44-46's fit window) — this is the direct answer to "did
   it work," not just whether the aggregate curve looks better.

5. Report: did the flight_22 spike shrink or disappear? Did RANSAC reject the
   specific known-bad frames? Any change (better or worse) to Model A's low-N
   behavior (expected: none, per decision #1 — flag clearly if it's NOT none, that
   would be a surprise worth understanding)? Any flights/models where RANSAC
   rejected suspiciously many points (would suggest the threshold or min_samples
   needs adjusting, not that the data is that bad)?

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

Do NOT do (unless explicitly asked later):
- ❌ Generalize to any flight beyond flight_01/flight_22
- ❌ Overwrite any existing file under data/trajectory_fit_comparison/ — only add
  new, clearly-named ones (decision #4)
- ❌ Run full RANSAC independently at every K-sweep grid point (decision #2's
  cheaper approach — one reference RANSAC pass per flight per model, reused
  across the sweep)
- ❌ Change the underlying model definitions (Models A/B/C themselves) — only wrap
  their existing fit calls in RANSAC, don't alter what they compute
- ❌ Commit anything to git

IF you think something else should be done that isn't covered above:
1. STOP
2. Log: "Considered doing [X] but it's not in scope — asking first"
3. Report and wait for a response

═══════════════════════════════════════════════════════════════════════════════
TIMING EXPECTATIONS
═══════════════════════════════════════════════════════════════════════════════

RANSAC multiplies each fit by however many iterations you compute (likely a few
hundred), across 2 flights, 3 models, up to ~90 N-values in Phase 2 — more work
than the original pass but still small point counts per fit. Expect low
single-digit minutes, not more. STOP and investigate if it runs past ~10 minutes.

═══════════════════════════════════════════════════════════════════════════════
CHECKPOINT
═══════════════════════════════════════════════════════════════════════════════

STOP after Phase 1 + Phase 2 RANSAC results are produced and report: whether the
flight_22 spike shrank, whether RANSAC rejected the specific known-bad frames,
Model A's behavior (should be unchanged), and any surprising rejection counts. Wait
for direction before considering whether/how to generalize beyond these 2 flights.

═══════════════════════════════════════════════════════════════════════════════
GIT WORKFLOW
═══════════════════════════════════════════════════════════════════════════════

No git. Do not commit anything.

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ `ransac_fit` works uniformly across Models A/B/C
✅ Rejected frame numbers logged per flight per model — direct confirmation (or
   disconfirmation) of catching the known flight_22 hand-pickup frames specifically
✅ All new outputs are additive (existing plain-fit files untouched), using small
   multiples/faceted layouts, not overloaded single-axis charts
✅ A plain answer: did RANSAC fix the confirmed case, and did it leave Model A's
   already-understood instability alone as expected
✅ Existing worklog continued, updated in real time
✅ No commits made
```
