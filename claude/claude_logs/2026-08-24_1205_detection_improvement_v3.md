# Work Log: detection_improvement_v3

**Session:** 2026-08-24_1205
**Status:** In progress - blocked on the row-number mapping

Related: [2026-08-24_0052_detection_improvement_figure.md](2026-08-24_0052_detection_improvement_figure.md) (v1).
v2 has no log of its own; read the script directly.

---

## Original Request

> Rebuild detection_improvement_v2.py as detection_improvement_v3.py. Same two
> series and colours. Changes: EXCLUDE every stage row carrying no rate in either
> series, so only stages with data appear. Replace each x-label with an integer
> row number supplied as a hard-coded mapping I will give you, and set the x-axis
> label to "iteration stage, numbered as in Table 3". Draw a vertical dashed
> divider immediately before the final stage and annotate it "population changes
> to 163 flights". Reduce the caption to at most three lines. Keep the assertion
> that the word recall appears in no user-facing string. STOP if excluding
> no-rate rows leaves fewer than 5 stages, or if any supplied row number is
> unused. Output to results/regenerate_figures/detection_improvement_v3/. Do not
> overwrite v1 or v2. Log incrementally.

---

## [12:05] Step 1 - source, exclusions, and the >=5 gate

Source: `results/detector_tuning/history/results_history.csv`, 12 rows, read-only.

### Two exclusions apply, not one

The brief names one new exclusion (rows carrying no rate in either series). v2's
own exclusion of the **rect close-kernel** row is not listed as a change, so it
carries forward. The divider requirement confirms this independently: "immediately
before the final stage ... population changes to 163 flights" only makes sense if
the final stage is the 163-flight row (file row 11). If the rect row (also 163
flights) were included it would be last, and a divider before it would sit between
two 163-flight stages and be wrong. Keeping the rect exclusion.

### Rows dropped

| file row | reason | stage |
|---|---|---|
| 2 | no rate either series | round 1 sweep (48 stride/thresh/open_k combos) |
| 4 | no rate either series | full-dataset artifact audit (pre-mask-v3) |
| 7 | no rate either series | round 3 sweep (24 min_area/min_circ combos) |
| 8 | no rate either series | audit at min_area=30/min_circ=0.30 (pre-mask-v4) |
| 9 | no rate either series | post-mask-v4 re-audit |
| 12 | rect close kernel (v2 rule) | rect close kernel validation |

### Rows surviving - 6 stages

| # | file row | stage | combined | series 2 | n_flights |
|---|---|---|---|---|---|
| 1 | 1 | baseline (defaults) | 0.2772 | 0.9074 | 10 |
| 2 | 3 | candidate config (no fixes) | 0.8740 | 0.9259 | 10 |
| 3 | 5 | candidate + mask v2 + trajectory filter | 0.7549 | 0.9259 | 10 |
| 4 | 6 | candidate + mask v3 (4 zones) + trajectory filter | 0.8552 | 0.9259 | 10 |
| 5 | 10 | + mask v4 + min_area=30/min_circ=0.30 - 10-FLIGHT SAMPLE | 0.9784 | 0.9250 | 10 |
| 6 | 11 | + mask v4 + min_area=30/min_circ=0.30 - FULL 163-FLIGHT DATASET | 0.9667 | 0.9250 | 163 |

**GATE PASS: 6 stages >= the minimum of 5.** STOP does not fire.

Note every surviving row carries BOTH series - the "no rate in either series"
exclusion happens to remove exactly the rows that carried neither, leaving none
that carry only one. So the "stages with no marker" grey-dash device from v2 is
now dead code and comes out.

The population change sits between surviving stage 5 (10 flights) and stage 6
(163 flights) - i.e. immediately before the final stage, exactly where the brief
places the divider. Consistent, and derived from the data rather than assumed.

## [12:07] Step 2 - BLOCKED on the supplied mapping

The brief says the row numbers are "a hard-coded mapping I will give you", and
adds a STOP for any supplied row number that goes unused. Both need the actual
numbers, so the mapping cannot be invented.

Building the full script now with the mapping as an empty constant plus a gate
that refuses to run while it is empty, and validating everything else end-to-end
against a scratchpad output directory so that filling in the numbers is the only
remaining step.

## [12:20] Step 3 - script written and validated except for the numbers

`src/regen_2class/detection_improvement_v3.py`.

Design point: `ROW_NUMBERS` is a list of `(stage_substring, integer)` pairs, keyed
by substring rather than by position - same reasoning as v2's `LABEL_KEYS`. A new
history row cannot silently shift every number by one, and the "unused number"
STOP becomes checkable (a positional list has no notion of an unused entry).

Validated end-to-end against a scratchpad output dir (env var
`DETECTION_IMPROVEMENT_V3_OUT`) so nothing lands in `results/` before the real
numbers arrive.

### Gates confirmed firing

| STOP | trigger tested | fires |
|---|---|---|
| fewer than 5 stages | n/a - 6 survive | GATE 1 PASS |
| ROW_NUMBERS empty | run as shipped | yes, lists the 6 stages |
| supplied number unused | added `('round 1 sweep', 7)` | yes, names the unused key |
| stage unmatched | removed the mask v2 key | yes, names the stage |
| numbers not unique | set two stages to 5 | yes, reports `[5]` |
| word "recall" surfaced | n/a | GATE 3 PASS, 15 strings checked |

Divider derived, not hardcoded: `x = 4.5`, between surviving stage 5 (10 flights)
and stage 6 (163 flights). Added a guard that STOPs if the final stage is not a
163-flight row, since the annotation states that number literally.

### Two layout defects found in the proof render and fixed

1. **Caption line 2 ran past the right page edge** and was clipped in the PNG.
   Rewrote the three lines shorter, and added a real guard: after
   `fig.canvas.draw()`, each caption line's rendered extent is measured and the
   script STOPs if any ends beyond the page width. A character-count budget would
   have been a guess; this measures.
2. **Legend at `lower right` sat on top of the divider**, which spans the full
   plot height at that end. Moved to `center left`, which is empty.

v2's grey "no value recorded" dash markers removed as dead code - after the
no-rate exclusion, every surviving stage carries both series.

## [12:22] BLOCKED - need the row-number mapping

Everything else is done and verified. `ROW_NUMBERS` is empty and the script
refuses to run. Asking for the 6 integers.

Confirmed untouched so far: `results/regenerate_figures/detection_improvement/`
and `.../detection_improvement_v2/` unchanged; `.../detection_improvement_v3/`
does not exist yet.

## [14:42] Step 4 - mapping supplied, caption cut to two lines, rendered

### Mapping received

Table 3 rows **4, 5, 6, 7, 8, 9** in plot order. Rows 1-3 of Table 3 are the
library dataset and have no counterpart in this figure, so nothing is unused -
the unused-number STOP does not fire.

| plot pos | Table 3 row | stage |
|---|---|---|
| 1 | 4 | baseline (defaults) |
| 2 | 5 | candidate config (no fixes) |
| 3 | 6 | candidate + mask v2 + trajectory filter |
| 4 | 7 | candidate + mask v3 (4 zones) + trajectory filter |
| 5 | 8 | + mask v4 + area30 - 10-flight sample |
| 6 | 9 | + mask v4 + area30 - full 163-flight dataset |

### Caption cut from three lines to two

Dropped from the in-figure text: the markers-only rationale and the source line.
Both stay recorded - source in this module's docstring and in this log - but the
LaTeX caption will carry the same information and it should not appear on the
page twice.

The two lines are rendered verbatim as supplied, with **the stage ranges derived
from the data rather than typed**:

```
combined rate is measured on the validation sample at stages 4-8 and on all 163 flights at stage 9.
true detection rate is 54 labelled points on one flight at stages 4-7 and 240 points on two flights at stages 8-9.
```

Cross-checked the four ranges against the source before accepting the wording:

| claim | source evidence |
|---|---|
| validation sample at stages 4-8 | `n_flights=10` at plot positions 1-5 |
| all 163 flights at stage 9 | `n_flights=163` at plot position 6 only |
| 54 points, one flight, stages 4-7 | `flight_01 only (54 points)` at positions 1-4 |
| 240 points, two flights, stages 8-9 | `flight_01 + flight_22 (240 points)` at positions 5-6 |

All four match. `stage_range()` computes each from `ROW_NUMBERS` + the row data
and STOPs if a set turns out non-contiguous, since "stages 4-8" would then
silently misdescribe it. `flight_word()` derives "one flight"/"two flights" by
counting `flight_` in the source annotation rather than hardcoding it.

Caption line-count gate tightened from 3 to 2. The rendered-extent guard from
Step 3 still applies; both lines measure inside the page width.

### Gates on the real run

```
GATE 1 PASS: 6 stages survive (minimum 5)
GATE 2 PASS: 6 supplied row number(s), all used, all unique: [4, 5, 6, 7, 8, 9]
divider at x=4.5: population 10 -> 163 flights
GATE 3 PASS: 'recall' appears in none of the 14 user-facing strings
```

### Untouched, verified by mtime after the run

- `detection_improvement/` (v1): 2026-08-24 11:31
- `detection_improvement_v2/`: 2026-08-24 11:55
- `results_history.csv` (source): 2026-08-03 15:45

`detection_improvement_v3/` did not exist before this run.

## Deliverables

- `results/regenerate_figures/detection_improvement_v3/detection_improvement_v3.png`
- `results/regenerate_figures/detection_improvement_v3/detection_improvement_v3.csv`
  (keyed on `table3_row`)
- `src/regen_2class/detection_improvement_v3.py`

**Status: Complete.**
