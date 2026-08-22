# Work Log: Chaos-rally sweep, COMBINED landing-error criterion

**Session:** 2026-08-22_1606
**Start:** 16:06
**Status:** In Progress
**Duration:** [updating]

---

## Original Request

> Regenerate the chaos-rally outcome sweep with a COMBINED landing-error criterion.
> Re-read of existing data at new thresholds. No new experiments, no new data, no
> model changes, no re-fitting. The build is frozen.
>
> Script to src/regen_2class/step13_chaos_sweep_landing_error.py, no heredocs.
> Output to the NEXT numbered subfolder under data/regenerate_figures/.
>
> landing_error_mm = |dp| + e*|dv|*t, e = 0.68, t = 1.0 s. Run BOTH thresholds as
> full figures: 500 mm (arm's reach, stationary player) and 1000 mm (step plus reach
> over a 1 s return). Neither is to be labelled "the requirement".
>
> Verdict precedence: no_response, late, wrong_class, wrong_placement, success.
> A in {72,135,220} ms, minus sign in the timing test. Operating point = max success
> rate, latest tie; landing error must not influence the maximisation. Five STOP
> gates including a three-criterion regression and a mathematical bug detector.
> Print and CSV: per-window bands, plateaus, operating points, landing-error split
> into its two terms, independent flag counts, a three-scheme comparison, and a
> separate-vs-combined cross-tabulation.

---

## Objective

Score the frozen chaos-rally sweep against a single combined landing-error budget
rather than two separately-allocated tolerances, at both candidate thresholds, and
quantify how much stricter the combined test is than separate gates.

---

## OUTPUT FOLDER

Enumerated `data/regenerate_figures/` before writing. One numbered subfolder existed,
`01_chaos_4criterion`. Created the next in sequence:
**`data/regenerate_figures/02_chaos_landing_error/`**, verified empty before writing.
Everything from this task goes there; nothing outside it is touched.

Note the script filename is `step13_chaos_sweep_landing_error.py` as briefed, which
sits alongside the existing `step13_chaos_sweep_4criterion.py`. Two different
"step13" files now exist. Flagged rather than silently renumbered.

---

## WHY THIS CHANGED

The three-criterion version removed position, arguing a rigid panel in pure
translation returns the ball independently of contact location. That is correct for
the outgoing VELOCITY:

    v_out = e * v_in + (1 + e) * u

carries no rotation term. It is NOT correct for the outgoing POSITION: the ball
departs from wherever it was struck, so a crossing-position error translates the
whole return trajectory by the same amount.

**The requirement is about the SUM, not each term alone.** Position error and
velocity error displace the SAME landing point in the SAME frame. Testing them
separately forces an arbitrary allocation between the two terms that no physics
justifies, and produces false failures where one term is large and the other small.
Both derive from the same Model-C fit on the same detected points, so they are
correlated in source and add LINEARLY; quadrature would assume an independence that
does not hold.

## UNITS CHECK

    landing_error_mm = |dp| + e * |dv| * t
                       [mm]  +  [-] * [mm/s] * [s]
                     = [mm]  +  [mm]
                     = [mm]                              OK

e is dimensionless. |dv| in mm/s multiplied by t in seconds yields mm, which is
commensurable with |dp| in mm and can be added directly.

## WHAT |dp| AND |dv| ACTUALLY ARE IN THIS DATA

**|dp| = `position_error_mm`, already the full 3D magnitude, no reconstruction
needed.** Checked in source: `prediction_pipeline_sweep_pi.py:411` computes it as
`hypot(cy_own - crossing_Y, cz_own - crossing_Z)` - only two components. That is
NOT an approximation of a 3D distance: both the predicted and the reference crossing
point lie ON the crossing plane by construction (each is found by root-solving
depth(t) = plane_depth), so the depth component of the displacement between them is
identically zero. The in-plane 2-component distance IS the 3D magnitude.

**|dv| computed from the per-axis components** as
`sqrt(err_vx^2 + err_vy^2 + err_vz^2)` per the brief, and cross-checked against the
stored scalar `velocity_error_mm_s` on every row.

---

## Log

- [16:07] Created `data/regenerate_figures/02_chaos_landing_error/`, verified empty.
  One numbered subfolder existed (`01_chaos_4criterion`), so 02 is next in sequence.
- [16:09] Wrote `src/regen_2class/step13_chaos_sweep_landing_error.py`. Self-contained
  flags; only `load_per_axis` imported from step10.
- [16:11] Ran. All gates pass, both thresholds rendered.

## STOP GATES - all five PASS

| gate | result |
|---|---|
| join shape | 2568 rows, 107 flights, 24 windows -> **PASS** |
| class counts | SHORT 47, LONG 60 -> **PASS** |
| band sums == class n | all 48 cells per A, both thresholds -> **PASS** |
| three-criterion regression | 6/6 exact -> **PASS** |
| bug detector (pass combined<=500 while failing BOTH separate tests) | 0 rows -> **PASS** |

Regression gate reproduced by disabling placement AND restoring velocity to
1470.6 mm/s, since running it at any other velocity tolerance would change two
things at once and void the check. SHORT 93.6 / 93.6 / 74.5, LONG 98.3 / 98.3 / 98.3,
all exact.

**|dv| cross-check: 0 mismatches over 2481 fitted rows** between
`sqrt(err_vx^2+err_vy^2+err_vz^2)` and the stored `velocity_error_mm_s`.

Deadlines recomputed min-anchored for the record (SHORT 490, LONG 1040 ms); the
chaos verdict uses `launch_to_crossing_ms - A` and never consumes them.

## RESULTS - combined <= 500 mm (arm's reach, stationary player)

| class | A | plateau | selected | success | placement | class | late | no_resp |
|---|--:|---|--:|--:|--:|--:|--:|--:|
| SHORT | 72 | {250} | 250 ms | **83.0%** (39/47) | 4 | 2 | 0 | 2 |
| LONG | 72 | {650,700,750} | 750 ms | **95.0%** (57/60) | 0 | 0 | 3 | 0 |
| SHORT | 135 | {250} | 250 ms | **72.3%** (34/47) | 4 | 2 | 5 | 2 |
| LONG | 135 | {650} | 650 ms | **95.0%** (57/60) | 2 | 1 | 0 | 0 |
| SHORT | 220 | {200} | 200 ms | **51.1%** (24/47) | 11 | 1 | 9 | 2 |
| LONG | 220 | {550} | 550 ms | **86.7%** (52/60) | 4 | 3 | 0 | 1 |

## RESULTS - combined <= 1000 mm (step plus reach over a 1 s return)

| class | A | plateau | selected | success | placement | class | late | no_resp |
|---|--:|---|--:|--:|--:|--:|--:|--:|
| SHORT | 72 | {200,250} | 250 ms | **91.5%** (43/47) | 0 | 2 | 0 | 2 |
| LONG | 72 | {650,700} | 700 ms | **98.3%** (59/60) | 0 | 1 | 0 | 0 |
| SHORT | 135 | {200} | 200 ms | **91.5%** (43/47) | 1 | 1 | 0 | 2 |
| LONG | 135 | {650} | 650 ms | **98.3%** (59/60) | 0 | 1 | 0 | 0 |
| SHORT | 220 | {200} | 200 ms | **72.3%** (34/47) | 1 | 1 | 9 | 2 |
| LONG | 220 | {600} | 600 ms | **96.7%** (58/60) | 1 | 1 | 0 | 0 |

## COMPARISON across the three schemes

| class | A | 3-crit | combined-1000 | delta | combined-500 | delta |
|---|--:|--:|--:|--:|--:|--:|
| SHORT | 72 | 93.6% | 91.5% | -2.1 | **83.0%** | **-10.6** |
| LONG | 72 | 98.3% | 98.3% | +0.0 | **95.0%** | **-3.3** |
| SHORT | 135 | 93.6% | 91.5% | -2.1 | **72.3%** | **-21.3** |
| LONG | 135 | 98.3% | 98.3% | +0.0 | **95.0%** | **-3.3** |
| SHORT | 220 | 74.5% | 72.3% | -2.1 | **51.1%** | **-23.4** |
| LONG | 220 | 98.3% | 96.7% | -1.7 | **86.7%** | **-11.7** |

SHORT drops under both thresholds, as anticipated. Reported, not reconciled.

**The two thresholds are not a small variation on each other - they are different
regimes.** At 1000 mm the cost is a uniform -2.1 pp for SHORT and ~0 for LONG. At
500 mm SHORT loses 10.6 to 23.4 pp and LONG 3.3 to 11.7 pp. The mechanism is visible
in the landing-error distributions: SHORT's median landing error is 290-309 mm with
p90 524-709 mm, so a 500 mm threshold cuts through the steep part of the
distribution, between median and p90, where small threshold changes move many
flights. A 1000 mm threshold sits beyond SHORT's p90 and clips only the tail.

## THE ERROR SPLIT - the two classes are limited by different terms

Median split of landing_error into its two components at each operating point:

| class | A | window | \|dp\| median | e*\|dv\|*t median | dominant term |
|---|--:|--:|--:|--:|---|
| SHORT | 72 | 250 | 121.3 mm | **169.8 mm** | velocity (58%) |
| SHORT | 135 | 250 | 121.3 mm | **169.8 mm** | velocity (58%) |
| SHORT | 220 | 200 | 127.4 mm | **181.6 mm** | velocity (59%) |
| LONG | 72 | 750 | **91.1 mm** | 61.4 mm | position (60%) |
| LONG | 135 | 650 | **110.1 mm** | 77.4 mm | position (59%) |
| LONG | 220 | 550 | **145.7 mm** | 108.2 mm | position (57%) |

**SHORT is velocity-limited; LONG is position-limited.** That is a structural
finding the separate-criterion runs could not show, because splitting the budget in
advance hid which term was actually consuming it. It also means the two classes
would benefit from different improvements: SHORT from better velocity estimation,
LONG from better crossing-position estimation. Worth carrying into the report as its
own result, independent of which threshold is adopted.

## SEPARATE GATES vs COMBINED - how much stricter the combined test is

Over all 2481 fitted flight-window rows, comparing separate gates
(|dp| <= 500 mm AND |dv| <= 735 mm/s) against combined <= 500 mm:

| | rows | % of fitted |
|---|--:|--:|
| pass separate | 2380 | 95.9% |
| pass combined-500 | 2217 | 89.4% |
| **pass separate but FAIL combined** | **163** | **6.6%** |
| pass combined but FAIL separate | **0** | 0.0% |

The 163 rows are the quantification of the strictness: flights where each term alone
is within its own allowance but the SUM is not. Those are exactly the cases the
separate-criterion formulation was missing.

**The zero in the last row is analytic, not empirical.** Failing separate means
|dp| > 500 (so the sum already exceeds 500) or |dv| > 735.29 mm/s (so
e*|dv|*t > 0.68 x 735.29 = 500, and the sum again exceeds 500). Either branch forces
a combined failure. So combined<=500 is UNIFORMLY stricter than the separate gates
at those values - it can never pass something the separate test rejects. The count
being 0 confirms the implementation matches that algebra; it is a bug detector, not
evidence.

## Second-order effects on the operating point

At combined-500, LONG A=72 selects **750 ms**, later than the three-criterion 700 ms,
and picks up **3 `late` failures** while carrying **0 placement** failures. The
optimiser is trading lateness for placement accuracy - a longer window reduces
landing error enough to be worth three late flights. That is the criterion changing
the operating point's character, not just its score, and it only appears under the
tighter threshold.

## Visual QA

Both figures rendered and inspected, including cropping and reading the caption
bands directly rather than assuming. Seven caption lines each, all on canvas; the
adaptive caption block carried over from the previous task handled both. Titles are
labelled by threshold and anchor only - neither figure calls itself "the
requirement". Bands, colours, stacking order and truncation as specified.

## Outputs - all in data/regenerate_figures/02_chaos_landing_error/

| file | contents |
|---|---|
| `figure_chaos_landing_error_500mm.png` | 6 panels, 150 dpi |
| `figure_chaos_landing_error_1000mm.png` | 6 panels, 150 dpi |
| `bands_by_class_A_window_500mm.csv` | 144 rows, all five bands per class/A/window |
| `bands_by_class_A_window_1000mm.csv` | 144 rows |
| `operating_points_500mm.csv` | 6 rows: plateau, selected window, bands, landing median/p90/max, the \|dp\| and e*\|dv\|*t medians, independent flag counts |
| `operating_points_1000mm.csv` | 6 rows |
| `comparison_three_schemes.csv` | 6 rows: three-criterion, combined-1000, combined-500, with deltas |
| `separate_vs_combined_500.csv` | the cross-tabulation above |

Nothing outside that folder was created, modified or deleted.

**Status:** Complete
**Duration:** 16:06 start, 16:14 finish, ~8 min against the 30 min expectation.
