# Work Log: Chaos-rally sweep, FOUR-criterion verdict

**Session:** 2026-08-22_1530
**Start:** 15:30
**Status:** In Progress
**Duration:** [updating]

---

## Original Request

> Regenerate the chaos-rally outcome sweep with a FOUR-criterion verdict. Re-read of
> existing data at new thresholds. No new experiments, no new data, no model changes,
> no re-fitting. The build is frozen.
>
> Script to src/regen_2class/step13_chaos_sweep_4criterion.py, no heredocs. Output to
> the NEXT numbered subfolder under data/regenerate_figures/, never overwriting.
>
> Verdict precedence: no_response, late, wrong_class, wrong_position (>500 mm),
> wrong_velocity (any axis >735 mm/s), success. A in {72,135,220} ms, minus sign in
> the timing test. Primary figure plus a 250 mm / 368 mm/s sensitivity figure.
> Operating point = max success rate, latest tie, position must not influence the
> maximisation. Four STOP gates including a three-criterion regression check.
> Print and CSV: per-window bands, plateaus, operating points, capability,
> independent flag counts, and a 3-crit vs 4-crit comparison.

---

## Objective

Re-score the frozen chaos-rally sweep with position reinstated as a pass criterion,
under a linearly-split 1000 mm landing-error budget, and quantify what that costs
relative to the three-criterion result.

---

## OUTPUT FOLDER

Enumerated `data/regenerate_figures/` before writing: it contains 24 files and
**zero subdirectories**, so there was no existing numbered sequence to continue.
Created the first: **`data/regenerate_figures/01_chaos_4criterion/`**, using the
`NN_descriptive_name` convention already used by `data/prediction/01_crossing_plane_setup`
and `data/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection`. Verified empty
before writing. Every output of this task goes there; nothing outside it is touched.

---

## WHY POSITION RETURNS AS A PASS CRITERION

The three-criterion version (Figure H) removed position, arguing that a rigid panel
in pure translation returns the ball independently of contact location. That
argument is correct for the outgoing VELOCITY and incorrect for the outgoing
POSITION.

    v_out = e * v_in + (1 + e) * u

carries no rotation term, so the outgoing velocity really is independent of where on
the surface contact occurs. But the ball departs from **wherever it was struck**. A
crossing-position error therefore translates the entire return trajectory by the
same amount. Position governs the return's origin even though it does not govern the
return's direction or speed. Removing it discarded a real error term.

**The two terms add LINEARLY, not in quadrature.** Position error and velocity error
displace the same landing point in the same frame, and both derive from the same
Model-C fit on the same detected points. They are correlated in source. Quadrature
would assume an independence that does not hold and would understate the total.

## THRESHOLD DERIVATION

Total landing-error budget at the player: **1000 mm**, split **equally** between the
two terms. Equal allocation is a stated budget CHOICE, not a derived result: no
physical basis favours either term, and over a 1 s return a static offset and an
accumulated velocity error are directly commensurable.

- Position term: **500 mm** crossing-position error.
- Velocity term: 500 mm / (e x t), with e = 0.68 (published volleyball-on-rigid-
  surface coefficient of restitution, not assumed) and t = 1.0 s return flight
  -> **735 mm/s**, applied isotropically to all three world axes.

Supersedes the previous 1471 mm/s, which allocated the full 1000 mm to velocity and
counted no position term at all.

---

## Log

- [15:31] Created `data/regenerate_figures/01_chaos_4criterion/`, verified empty.
  No numbered subfolders existed previously - the directory held 24 files and zero
  subdirectories, so 01 is the first in sequence.
- [15:32] Wrote `src/regen_2class/step13_chaos_sweep_4criterion.py`, self-contained
  flags (strict `>` on both thresholds, matching the brief; step10 used `>=` on
  position, so the flag function is written locally rather than imported to avoid a
  silent mismatch). Only `load_per_axis` and `AXIS_TITLE` are imported.
- [15:33] Thresholds DERIVED in code from the budget, not hardcoded:
  `budget_to_thresholds(1000)` -> position 500 mm, velocity 735.29 mm/s.
  Sensitivity `budget_to_thresholds(500)` -> 250 mm, 367.65 mm/s.

## STOP GATES - all four PASS

| gate | result |
|---|---|
| join shape | 2568 rows, 107 flights, 24 windows -> **PASS** |
| class counts | SHORT 47, LONG 60 -> **PASS** |
| band sums == class n | all 48 cells per A, both variants -> **PASS** |
| three-criterion regression | 6/6 exact -> **PASS** |

**Regression gate detail.** Reproducing the published three-criterion result
requires disabling position AND restoring velocity to 1470.6 mm/s. Running it at the
new 735 mm/s would change two things at once and the check would be void - at
735 mm/s the velocity criterion does fire (28 rows breach), so it could not
reproduce Figure H by construction. With position disabled and velocity restored:

    SHORT A=72   93.6% (want 93.6)    LONG A=72   98.3% (want 98.3)
    SHORT A=135  93.6% (want 93.6)    LONG A=135  98.3% (want 98.3)
    SHORT A=220  74.5% (want 74.5)    LONG A=220  98.3% (want 98.3)

Machinery confirmed unchanged; only the criterion set differs.

Deadlines recomputed min-anchored for the record (SHORT 490, LONG 1040 ms) but the
chaos verdict uses `launch_to_crossing_ms - A` directly and never consumes them.

## PRIMARY RESULT - position > 500 mm, velocity > 735 mm/s

| class | A | plateau | selected | success | success | w_vel | w_pos | w_class | late | no_resp |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|
| SHORT | 72 | {250} | 250 ms | **91.5%** | 43 | 0 | 0 | 2 | 0 | 2 |
| LONG | 72 | {650} | 650 ms | **98.3%** | 59 | 0 | 0 | 1 | 0 | 0 |
| SHORT | 135 | {200} | 200 ms | **89.4%** | 42 | 1 | 1 | 1 | 0 | 2 |
| LONG | 135 | {650} | 650 ms | **98.3%** | 59 | 0 | 0 | 1 | 0 | 0 |
| SHORT | 220 | {200} | 200 ms | **70.2%** | 33 | 1 | 1 | 1 | 9 | 2 |
| LONG | 220 | {600} | 600 ms | **95.0%** | 57 | 0 | 2 | 1 | 0 | 0 |

Position capability at those points: SHORT median 121-127 mm, p90 248-350 mm, max
851-919 mm. LONG median 110-115 mm, p90 180-317 mm, max 402-650 mm. Per-axis
velocity bias and scatter RMS are in `operating_points_primary.csv`.

All six plateaus are single-window except none - every plateau has exactly one
window, so the latest-tie rule never had to break a tie in the primary variant.

## INDEPENDENT FLAG COUNTS at the selected operating points (primary)

Precedence masks everything below the first failure, so these are the per-requirement
failure rates the requirements table needs.

| class | A | no_response | late | wrong_class | wrong_position | wrong_velocity |
|---|--:|--:|--:|--:|--:|--:|
| SHORT | 72 | 2/47 | 0/45 | 2/45 | 1/45 | 1/45 |
| LONG | 72 | 0/60 | 0/60 | 1/60 | 0/60 | 0/60 |
| SHORT | 135 | 2/47 | 0/45 | 1/45 | 2/45 | 1/45 |
| LONG | 135 | 0/60 | 0/60 | 1/60 | 0/60 | 0/60 |
| SHORT | 220 | 2/47 | 9/45 | 1/45 | 2/45 | 1/45 |
| LONG | 220 | 0/60 | 0/60 | 1/60 | 2/60 | 0/60 |

Band counts and independent counts agree closely here, which means the failure modes
are almost entirely disjoint at these operating points - unlike the earlier
four-criterion run at 100 mm, where precedence was masking a large position band.

## COMPARISON: three-criterion vs four-criterion

| class | A | 3-crit | 4-crit | delta | 3-crit window | 4-crit window |
|---|--:|--:|--:|--:|--:|--:|
| SHORT | 72 | 93.6% | **91.5%** | **-2.1** | 200 ms | 250 ms |
| LONG | 72 | 98.3% | **98.3%** | +0.0 | 700 ms | 650 ms |
| SHORT | 135 | 93.6% | **89.4%** | **-4.3** | 200 ms | 200 ms |
| LONG | 135 | 98.3% | **98.3%** | +0.0 | 650 ms | 650 ms |
| SHORT | 220 | 74.5% | **70.2%** | **-4.3** | 200 ms | 200 ms |
| LONG | 220 | 98.3% | **95.0%** | **-3.3** | 600 ms | 600 ms |

SHORT drops at every A, as anticipated: -2.1, -4.3, -4.3 pp. Reported, not
reconciled.

LONG is unaffected at A=72 and A=135 and drops 3.3 pp at A=220. So the cost of
reinstating position is not confined to SHORT, but it is much smaller for LONG.

**The drops are small because 500 mm is a loose threshold against this data.**
Position error medians at the operating points are 110-127 mm and p90s are 180-350
mm, so only a handful of flights exceed 500 mm at all. That is the honest reading:
reinstating position as a criterion is defensible physically, and at a 1000 mm
budget split equally it costs 0 to 4.3 points. It does not overturn the
three-criterion picture.

**One second-order effect worth noting.** At SHORT A=72 the selected window moved
LATER, 200 -> 250 ms, and at that window `wrong_position` is 0 rather than 1. Adding
a criterion moved the optimum to a longer window where position happens to be
cleaner. At LONG A=72 it moved EARLIER, 700 -> 650 ms. So the criterion change
perturbs the operating point in both directions; the window is not simply pushed one
way.

## SENSITIVITY - 500 mm budget: position > 250 mm, velocity > 368 mm/s

| class | A | selected | success | vs primary |
|---|--:|--:|--:|--:|
| SHORT | 72 | 300 ms | 76.6% | -14.9 |
| LONG | 72 | 700 ms | 95.0% | -3.3 |
| SHORT | 135 | 200 ms | 70.2% | -19.2 |
| LONG | 135 | 650 ms | 93.3% | -5.0 |
| SHORT | 220 | 200 ms | 53.2% | -17.0 |
| LONG | 220 | 650 ms | 83.3% | -11.7 |

Independent flags at the sensitivity thresholds show velocity becoming the dominant
SHORT failure: 11 of 45 at A=135 and A=220, versus 7 of 45 for position.

**This is a reported sensitivity and NOT the requirement.** At 368 mm/s the
tolerance sits at roughly 1.3x the Y_width label SD of ~282 mm/s (decision 77), so
on the weak axis the test is comparing the predictor against a tolerance only
marginally above the reference's own noise. The 11-of-45 SHORT velocity failures at
that setting cannot be attributed to the predictor with any confidence. The caption
states this on the figure.

## Visual QA

Both figures rendered and inspected. The primary was clean on first render. **The
sensitivity figure clipped its final caption line** - which was the "THIS IS A
REPORTED SENSITIVITY, NOT THE REQUIREMENT" continuation, the single line that most
needed to be legible. Cause: a fixed caption start height with a variable line count
(10 lines primary, 12 sensitivity). Fixed by anchoring the LAST line at a fixed
height and growing the block upward, with `rect` derived from the line count.
Re-rendered and verified by cropping and reading the caption band directly.

## Outputs - all in data/regenerate_figures/01_chaos_4criterion/

| file | contents |
|---|---|
| `figure_chaos_4criterion_primary.png` | 6 panels, 150 dpi |
| `figure_chaos_4criterion_sensitivity.png` | 6 panels, 150 dpi |
| `bands_by_class_A_window_primary.csv` | 144 rows: all six band counts per class, A, window |
| `bands_by_class_A_window_sensitivity.csv` | 144 rows |
| `operating_points_primary.csv` | 6 rows: plateau, selected window, bands, position median/p90/max, per-axis velocity bias and RMS, independent flag counts |
| `operating_points_sensitivity.csv` | 6 rows |
| `comparison_3crit_vs_4crit.csv` | 6 rows, both variants against the three-criterion baseline |

Nothing outside that folder was created, modified or deleted.

**Status:** Complete
**Duration:** 15:30 start, 15:38 finish, ~8 min against the 25 min expectation.
