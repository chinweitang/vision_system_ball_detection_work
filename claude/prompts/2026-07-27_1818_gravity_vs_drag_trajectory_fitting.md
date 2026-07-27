# 2026-07-27 18:18 — Three-way trajectory model comparison (flight_01/flight_22 pilot)

**Instructions:** Copy the block below and paste it into a fresh Claude Code session
in this repo.

---

```
READ FIRST: claude/claude_rules.md, then claude/context.md §5 (prediction model) and
§4.6 (error budget). Then read src/stereo/predict_sweep.py and
src/stereo/label_vs_detection.py IN FULL — this task consolidates and extends their
existing fitting logic, not replaces it.

═══════════════════════════════════════════════════════════════════════════════
TASK
═══════════════════════════════════════════════════════════════════════════════

Compare THREE trajectory models to determine which predicts best — the decisive test
being held-out prediction error at a range of lead times, not full-arc fit residual
(different questions, already discussed and settled — do not conflate them):

- **Model A — free gravity, no drag**: today's existing approach (`fit_constant_accel`
  in `predict_sweep.py`), a fully free 9-parameter fit (`p0, v0, a` all free).
- **Model B — fixed gravity, no drag**: `a` fixed at `g_fixed` (see below), only
  `p0, v0` fit. This is now a LINEAR fit (`p(t) - 0.5*g_fixed*t^2 = p0 + v0*t`,
  ordinary least squares — no nonlinear solver needed).
- **Model C — fixed gravity + drag**: `dv/dt = g_fixed - k*|v|*v`, `g_fixed` fixed
  (same value as Model B), `p0, v0, k` fit (nonlinear — no closed form once drag is
  in the equation of motion).

Comparing all three (not just picking one baseline) isolates each change separately:
A vs. B answers "does fixing gravity alone help" (the user's own long-standing "try
fixed gravity" todo item, answered as a side effect); B vs. C isolates drag's
contribution on a level playing field; A vs. C shows the full picture against current
practice.

**`g_fixed`, and a units gotcha — get this right, it's easy to get wrong silently:**
`data/2026_07_15_gym/flight_binning/world_frame_validation/registration_world_transform.npz`
already exists (built by the flight-velocity-angle-binner task, validated via
`world_frame_precision_single.py`'s guardrails — RMS 1.32mm, baseline-perpendicular-
to-up angle 89.75°, well within tolerance). Load its `up_vec` (camera-frame, unit
vector) — do NOT recompute it. `g_fixed = 9810 * (-up_vec)`, in **mm/s², not m/s²**
— triangulated positions come out in mm (extrinsics' `T` is in mm) and the existing
fits' internal `a` values are in mm/s² (`predict_sweep.py` only converts to m/s² for
display: `norm_a_label = ... / 1000.0`). Using `9.81` instead of `9810` here would
silently produce a nonsense fit, not an obvious error — verify the resulting `g_fixed`
magnitude is ~9810 mm/s² before trusting anything built on top of it.

Three phases, each with its own checkpoint:
- **Phase 0**: consolidate duplicated fitting code into one shared module (this
  session already has 3 independent implementations of the same gravity-only fit —
  `predict_sweep.py`, `label_vs_detection.py`, `triangulate_flight.py` — which
  already caused real confusion once; adding two more models without consolidating
  first would make it worse).
- **Phase 1**: on `flight_01` and `flight_22`'s full, densely-labelled arcs, compute
  Models A/B, sweep drag coefficient K for Model C, refine via nonlinear fit, and
  settle on one K value to carry forward.
- **Phase 2**: the decisive comparison — fit all 3 models on early windows only,
  predict forward, score against the held-out final labelled frame, across a sweep
  of window sizes, for both flights, on both labelled and detected points.

**Design decisions already made — do not re-litigate:**
1. K estimation (Phase 1): fit separately on flight_01 and flight_22 first
   (cross-check — do they roughly agree?), THEN pool both flights' points into one
   joint fit for the final K used in Phase 2. If the two flights disagree
   substantially, report this as a real finding before deciding how to proceed,
   don't silently average.
2. `g_fixed` (Models B and C) comes from the existing, validated checkerboard
   world-frame registration for `2026_07_15_gym` (see above) — this session's
   flight_01/flight_22 both live in that session, which has ONE registration for the
   whole session (no mid-session split, unlike `2026_07_21_gym`). Do not use
   world-registration for any OTHER session, and do not fall back to a gravity-fit-
   derived direction — the whole point of Models B/C is to test a fixed, externally-
   validated gravity, not a trajectory-fit-derived one (which would be circular:
   biased by the very drag effect being tested).
3. Model C's `g_fixed` is NOT borrowed from Model A's fitted `a` — Model A's fit is
   expected to be biased by unmodeled drag (that bias is the original reason drag
   was worth investigating), so feeding it into Model C as a fixed input would be
   circular. Model B and Model C both use the SAME externally-fixed `g_fixed` from
   decision #2, independent of Model A entirely.
4. In Phase 2, K is HELD FIXED at Phase 1's result for Model C — do not refit K per
   window. Physically it's a property of the ball/air, not something that should
   vary flight-to-flight or window-to-window; refitting it per short window would
   reopen the same low-N nonlinear-instability problem already diagnosed this
   session for other fits.
5. Phase 2 computes all 3 models on BOTH labelled and detected points (6 curves per
   flight total) — matching `predict_sweep.py`'s existing labelled/detected curve
   pair, extended to 3 models instead of 1. The detected-points curves MUST use the
   TUNED detector output
   (`data/detector_tuning/detections/03_stride1_thresh16_openk3_area30_circ0.3/
   2026_07_15_gym/flight_01_cam{0,1}_detections.csv` and `flight_22_cam{0,1}_
   detections.csv`), NOT `analysis_3` — this exact mistake (using stale pre-tuning
   detections) has already happened twice this session in other tasks, do not repeat
   it a third time.

═══════════════════════════════════════════════════════════════════════════════
LOGGING (NEW LOG FILE, REAL-TIME UPDATES)
═══════════════════════════════════════════════════════════════════════════════

Create `claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md`
(new topic — do not append to any other worklog).

**Update it continuously and immediately — not just after each named step above.**
The user is watching this file in real time (`tail -f`) specifically to catch
problems as they happen and to check you're not drifting off-task, not to read a
retrospective summary once something is already finished. Concretely:
- Log BEFORE starting a non-trivial sub-step ("about to sweep K from X to Y...", not
  only "swept K, got...") as well as after it completes.
- Log every attempt in real time as it happens, including ones that don't work —
  a nonlinear fit failing to converge, a wrong initial guess, a unit mistake you
  catch and fix, a number that looks physically implausible before you've figured
  out why. Write it down when you notice it, not after you've already resolved it
  and are describing it in hindsight — the point is for the user to see the same
  thing you're seeing, when you're seeing it.
- If you're debugging something (e.g. `g_fixed` not coming out near ~9810, a fit
  not converging, Phase 0's before/after numbers not matching), narrate the
  debugging as you go — what you tried, what you found, what you're trying next —
  not just the eventual root cause once found.
- If you notice yourself about to do something outside this task's scope, log that
  the moment you notice it (the existing "considered doing [X], asking first"
  pattern below applies here too — log it AS you stop, not after you've already
  decided what to do about it).
- Append after every single one of these moments — don't batch several into one
  write. When in doubt, write the log update, don't wait to see if it's "worth" one.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT TO DO
═══════════════════════════════════════════════════════════════════════════════

### Phase 0 — consolidate fitting code

1. Read `predict_sweep.py`, `label_vs_detection.py`, and (from the pixel-velocity
   sync-correction task) `src/stereo/triangulate_flight.py` in full.

2. Create `src/stereo/trajectory_fit.py`. Move into it (not duplicate):
   `fit_parabola_axis` (currently in `label_vs_detection.py`) and
   `fit_constant_accel`/`predict_at` (currently in `predict_sweep.py`) — this becomes
   Model A. Update `label_vs_detection.py`, `predict_sweep.py`, `triangulate_flight.py`,
   and `src/stereo/flight_velocity_angle_binner.py` (which imports `fit_constant_accel`
   from `predict_sweep.py`) to import from the new module instead. `triangulate_
   flight.py`'s own `fit_quadratic_residual_rms` (currently a separate `np.polyfit`
   call) should also be reconciled with the shared fit — confirm/note whether it now
   produces numerically equivalent residuals (it should, same polynomial family,
   different parametrization), and note in the log which convention it ends up using.

3. **Verify this refactor is behavior-neutral before adding anything new** — do NOT
   stop to wait for confirmation on this if it passes; this is mechanical refactor
   verification, not a judgment call (claude_rules.md §4: exploratory/diagnostic
   work goes straight in, no pre-approval gate needed). Only STOP if something
   doesn't match (see ERROR HANDLING). Four concrete checks, each anchored to a
   number already established earlier this session — run each BEFORE moving the
   code (capture the "golden" output) and AFTER (rerun, diff):
   - `predict_sweep.py`: full N-sweep on `flight_01`, compare every row's
     `err_label_mm`/`err_det_mm`/`norm_a_label`/`norm_a_det` before vs. after.
   - `label_vs_detection.py`: comparison run on `flight_01`, compare the summary
     stats (median/mean/RMS `mag`, the reprojection/gravity-gate values) before vs.
     after.
   - `triangulate_flight.py`: rerun on `flight_5` (already the specific flight used
     to validate it in the sync-correction task, with recorded RMS numbers —
     naive=29.71mm etc. in that worklog) and confirm matching numbers.
   - `flight_velocity_angle_binner.py`: rerun its existing 3-flight smoke test
     (`flight_1`, `flight_5`, `flight_65`) and confirm identical skip-reasons and
     speed/elevation values to what's already recorded in that worklog.
   Log all four before/after comparisons explicitly, then proceed straight into
   Phase 1 if all four match — do not pause for a go-ahead.

### Phase 1 — Model discovery on flight_01 and flight_22 (full arc, labelled points)

5. In `trajectory_fit.py`, add:
   - `load_g_fixed()` — loads `up_vec` from the existing
     `registration_world_transform.npz` (decision #2), returns `g_fixed = 9810 *
     (-up_vec)` mm/s². Assert/print its magnitude is ~9810 as a sanity check.
   - `fit_constant_accel_fixed_g(t, xyz, g)` — Model B: linear least-squares fit of
     `(p0, v0)` only, `a` fixed at `g`.
   - `simulate_drag(p0, v0, k, g, t_array)` — Model C: numerically integrate
     `dv/dt = g - k*|v|*v` (RK4 or `scipy.integrate.solve_ivp`) from `(p0, v0)` at
     t=0, returning positions at the requested times.
   - `fit_drag_given_k(t, xyz, k, g, p0_guess, v0_guess)` — nonlinear least-squares
     fit of `(p0, v0)` only (g and k both fixed) via `scipy.optimize.least_squares`,
     minimizing position residual against `simulate_drag`.
   - `fit_drag_free_k(t, xyz, g, p0_guess, v0_guess, k_guess)` — same but with `k`
     also free, seeded from whatever `k_guess` is passed in.

6. New script `src/stereo/drag_k_discovery.py`. Load `g_fixed` once (decision #2).
   For EACH of flight_01 and flight_22 separately (full labelled tracks, triangulated
   via the now-shared `label_vs_detection.triangulate`):
   - Model A residual (existing free-gravity fit) — reference point only.
   - Model B residual (`fit_constant_accel_fixed_g` with `g_fixed`).
   - Model C: sweep K over a range centered on a physically-derived estimate for a
     regulation volleyball (~0.03, from `k ≈ 0.5·ρ_air·Cd·A/m` with `ρ_air≈1.2,
     Cd≈0.4, A≈0.0346 m², m≈0.27 kg` — a starting point, not a hard constraint,
     widen the sweep if the optimum lands at an edge). For each candidate K, call
     `fit_drag_given_k` with `g=g_fixed` and record the residual.
   - Take the sweep's best K, refine via `fit_drag_free_k` (free `p0,v0,k`, `g` still
     fixed, seeded from the sweep's best point) — record the refined K and residual.
   - Report all four numbers per flight: A residual, B residual, C-sweep-best
     residual, C-refined residual.

7. Compare flight_01's and flight_22's independently-fitted K values. If they're in
   reasonable agreement, pool both flights' points into one joint `fit_drag_free_k`
   call (concatenating both tracks with a shared time origin convention you define
   and log clearly, `g` still fixed) to get a single final K. If they disagree
   substantially, report this as a finding and ask before picking a final K to carry
   forward, rather than silently averaging or picking one flight arbitrarily.

8. **STOP at Checkpoint 1**, report Phase 0's before/after verification results
   (folded in here since Phase 0 itself doesn't pause — see above) alongside all of
   Phase 1 (A/B/C residuals per flight, K agreement, the final pooled K), wait for
   confirmation on the K value before Phase 2.

### Phase 2 — prediction-sweep comparison (the decisive test)

9. New script `src/stereo/trajectory_model_prediction_sweep.py`, extending
   `predict_sweep.py`'s existing windowing methodology (target = last labelled
   frame, sweep N over the usable fit-frame range) rather than rebuilding it from
   scratch. For each of flight_01 and flight_22, for each N in the sweep, on BOTH
   the labelled-points track and the detected-points track (tuned detections per
   decision #5 — you'll need a small adapter to combine each flight's separate
   cam0/cam1 tuned-detections CSVs into the single `frame_index,cam,u,v` schema
   `label_vs_detection.load_points_csv` expects, since the tuned-detections files
   are two separate per-cam `frame_number,u,v` files, not one combined file):
   - Fit Model A on the window, predict to the target, record error (should
     reproduce `predict_sweep.py`'s current numbers unchanged).
   - Fit Model B on the SAME window (`g_fixed`), predict to the target, record error.
   - Fit Model C on the SAME window (`g_fixed`, K fixed from Phase 1), predict to the
     target via `simulate_drag`, record error.
   - Report all 6 resulting curves (A/B/C x labelled/detected) per flight, plotted
     together (error vs. N, with the lead-time secondary axis `predict_sweep.py`
     already uses) — organize the plot so A-vs-B and B-vs-C are each easy to read
     off directly (e.g. consistent color per model, linestyle per data source).

10. **STOP at Checkpoint 2**: report the full 6-curve comparison for both flights.
    State plainly: does fixing gravity alone help (A vs B)? Does drag help on top of
    fixed gravity (B vs C)? Where does the full pipeline land overall (A vs C)? At
    which lead times, and by how much — this is the actual answer the whole exercise
    exists to produce. Do not editorialize beyond what the numbers show.

═══════════════════════════════════════════════════════════════════════════════
SCOPE - WHAT NOT TO DO
═══════════════════════════════════════════════════════════════════════════════

Do NOT do (unless explicitly asked later):
- ❌ Refit K per-window in Phase 2 — held fixed at Phase 1's result (decision #4)
- ❌ Use a world-registration from any session other than `2026_07_15_gym`, or a
  gravity-fit-derived direction, for `g_fixed` (decisions #2-3)
- ❌ Use `9.81` instead of `9810` for `g_fixed`'s magnitude — units must be mm/s²
- ❌ Use `analysis_3` for flight_01/flight_22's detected-points curves — use the
  tuned-detections folder (decision #5)
- ❌ Revisit the pixel-velocity sync-correction task's still-open "does sub-frame
  correction help" question — that's a natural follow-up once these models exist,
  but it's a separate task, not part of this one
- ❌ Touch `detector_core.py`, any labelling tool, or the final-point-labelling
  target-pairing fix — unrelated to this task
- ❌ Commit anything to git
- ❌ Create more than the one new log file named in LOGGING above

IF you think something else should be done that isn't covered above:
1. STOP
2. Log: "Considered doing [X] but it's not in scope — asking first"
3. Report and wait for a response

═══════════════════════════════════════════════════════════════════════════════
TIMING EXPECTATIONS
═══════════════════════════════════════════════════════════════════════════════

Phase 0 (refactor + verify): normal dev iteration, no long process expected. Phase 1
(K-sweep, ~30 candidate K values x nonlinear fit each, x2 flights + 1 pooled fit,
each on a small point count): expect well under a minute total. Phase 2 (N-sweep x
6 curves x 2 flights, again small per-flight data): expect low single-digit minutes
at most. STOP and investigate if any step runs past ~5 minutes.

═══════════════════════════════════════════════════════════════════════════════
CHECKPOINTS
═══════════════════════════════════════════════════════════════════════════════

Only 2 checkpoints — Phase 0 does NOT pause (it's mechanical refactor verification;
proceed automatically if all 4 before/after checks match, per Phase 0 step 3):

Checkpoint 1 (after Phase 0 + Phase 1): Phase 0's before/after verification results,
A/B/C residual comparisons per flight, K agreement, final pooled K — wait for
confirmation before fixing K into Phase 2.
Checkpoint 2 (after Phase 2): the full 6-curve comparison and the decisive
A-vs-B-vs-C finding.

Do not proceed past either checkpoint without explicit go-ahead. Phase 0 is the one
exception to "stop and wait" in this task — only stop mid-Phase-0 if a verification
check actually fails (see ERROR HANDLING), not to ask permission to continue when
everything matches.

═══════════════════════════════════════════════════════════════════════════════
ERROR HANDLING
═══════════════════════════════════════════════════════════════════════════════

Expected (log, flag, continue):
- A nonlinear fit (Model C) failing to converge for a particular K value in the
  sweep or a particular small N in Phase 2 — log it, skip that point, don't abort
  the sweep.

Unexpected (STOP immediately):
- Any of Phase 0's 4 before/after checks NOT matching — the refactor broke
  something. This is the one case where Phase 0 itself should stop and report,
  rather than proceeding straight into Phase 1 — fix it before building anything
  new on top of a broken consolidation.
- `g_fixed`'s magnitude coming out far from ~9810 mm/s² — a units or sign error,
  fix before anything downstream trusts it.
- Model A's curve in Phase 2 not matching `predict_sweep.py`'s existing recorded
  numbers for flight_01/flight_22 — investigate before trusting Models B/C's
  numbers either.

═══════════════════════════════════════════════════════════════════════════════
GIT WORKFLOW
═══════════════════════════════════════════════════════════════════════════════

No git. Do not commit anything.

═══════════════════════════════════════════════════════════════════════════════
SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════════════════════

✅ `trajectory_fit.py` is the single source of Model A's fit; the 3 previous
   independent implementations now import from it, verified behavior-neutral
✅ `g_fixed` loaded from the existing validated world-frame transform (not
   recomputed, not gravity-fit-derived), confirmed ~9810 mm/s² in magnitude
✅ Models B and C both use the same `g_fixed`, independent of Model A's own biased
   fit (decision #3)
✅ Per-flight K estimates compared before pooling; disagreement (if any) reported,
   not silently resolved
✅ Phase 2 produces all 6 curves (A/B/C x labelled/detected) per flight, using tuned
   detections not analysis_3
✅ A plain, numbers-based answer to "does fixing gravity help, does drag help on top
   of that, and where does the full pipeline land" — the actual point of the exercise
✅ Existing predict_sweep.py Model-A numbers reproduced unchanged after the refactor
✅ New log file created and updated in real time throughout
✅ No commits made

═══════════════════════════════════════════════════════════════════════════════
START WORK
═══════════════════════════════════════════════════════════════════════════════

Begin now:
1. Create the new log file; read claude_rules.md, context.md §5/§4.6, predict_sweep.py,
   label_vs_detection.py, triangulate_flight.py in full
2. Phase 0: consolidate into trajectory_fit.py, run the 4 before/after verification
   checks — proceed straight into Phase 1 if all match, stop and report only if one
   doesn't
3. Phase 1: load g_fixed, build Model B/C fitting functions, run A/B/C comparison +
   K-sweep/refinement on flight_01 and flight_22 separately then pooled, report at
   Checkpoint 1 (including Phase 0's verification results) and wait
4. Phase 2: build and run the 6-curve prediction sweep, report at Checkpoint 2
```
