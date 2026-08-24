# Work Log: Detection improvement figure v2, single panel

**Session:** 2026-08-24_1103
**Status:** Complete

Related: [2026-08-24_0052_detection_improvement_figure.md](2026-08-24_0052_detection_improvement_figure.md)
built v1 (four panels, split by denominator). v2 is a single panel by request,
with the denominators moved into the caption.

---

## Original Request

> Read data/detector_tuning/history/results_history.csv. Do not modify it. Write
> src/regen_2class/detection_improvement_v2.py producing a SINGLE-panel figure:
> x-axis the chronological stage labels, two series in different colours, markers
> only, no lines. Series 1 "average combined detection rate", series 2 "true
> detection rate". Do not use the word recall anywhere in the figure, axis labels or
> caption. EXCLUDE the rect close-kernel row entirely. Annotate in the caption, not
> on the axis, that combined rate before the full-dataset stage is a 10-flight sample
> and after it is 163 flights, and that true detection rate is 54 points on one
> flight before round 3 and 240 points on two flights after. STOP if excluding the
> rect row leaves fewer than 5 rows carrying a combined rate. STOP if any stage label
> is not unique. Output to data/regenerate_figures/detection_improvement_v2/. Log
> incrementally to claude/claude_logs/. Do not overwrite the v1 outputs.

---

## [11:03] Path correction

Both paths in the request predate this morning's `results/` migration:

| requested | actual |
|---|---|
| `data/detector_tuning/history/results_history.csv` | `results/detector_tuning/history/results_history.csv` |
| `data/regenerate_figures/detection_improvement_v2/` | `results/regenerate_figures/detection_improvement_v2/` |

Using the new locations. `data/detector_tuning/` now holds only `contact_sheets`.

## [11:03] Terminology constraint

The source column is named with the forbidden word. It is never printed: the
script reads it by column name in code only, and every user-facing string - series
label, axis label, title, caption, and the companion CSV's column headers - uses
**"true detection rate"**. Checked programmatically before writing (see the
terminology gate below) rather than by eye.

---

## [11:40] Gates - all three PASS

| gate | result |
|---|---|
| rect exclusion leaves >= 5 combined-rate rows | **PASS** - 6 rows (baseline, candidate, +mask v2, +mask v3, +mask v4 sample, full dataset) |
| all stage labels unique | **PASS** - 11 labels, no duplicates; raw `stage` strings also checked for uniqueness |
| forbidden word absent from user-facing strings | **PASS** - 0 of 26 strings contain it |

Excluded exactly 1 row: `2026-08-03 rect close kernel validation (...)`. 11 rows remain.

### The terminology gate

The source column for series 2 is named with the forbidden word. Rather than
relying on care, the script collects **every** user-facing string - series labels,
axis label, title, all 10 caption lines, and all 11 x-axis labels - and asserts the
word appears in none of them **before** anything is written. The column is touched
by name in code only. The companion CSV header uses `true_detection_rate`.

Verified independently after the run: `grep -ci recall` on the output CSV returns 0.

### Denominator transitions - derived, not hardcoded

The caption's four numbers are read from the file rather than typed:

- combined rate: **10**-flight sample through `+ mask v4 + area30 (sample)`,
  **163** flights from `full dataset 163 flights` onward
- true detection rate: **54** points on **one flight** before the round 3 sweep,
  **240** points on **two flights** after

`flight_word()` counts `flight_` occurrences in the row's own population text, so
"one flight" / "two flights" cannot drift from the source.

---

## [11:50] Two render defects, both caught by looking at the PNG

**1. Value labels collided with the other series' markers.** I had placed series 1
labels above and series 2 below, a fixed per-series rule. But series 2 is HIGHER
than series 1 at 4 of the 6 stages carrying both, so the lower series' label landed
on top of the higher series' marker - `0.8740` sat directly on the `0.9259` diamond.

Fixed by placing labels **by rank at each x** rather than by series: at any stage,
the higher value is labelled above and the lower below, whichever series each is.

**2. Caption lines overlapped.** Gap was 0.0145 of figure height; at 6.0 pt on a
4.9 in canvas a line is ~0.017. Raised the figure to 5.6 in and the gap to 0.0163.

---

## [11:55] Complete

| output | |
|---|---|
| `src/regen_2class/detection_improvement_v2.py` | the script |
| `results/regenerate_figures/detection_improvement_v2/detection_improvement_v2.png` | single panel, 6.6 in at 300 dpi |
| `results/regenerate_figures/detection_improvement_v2/detection_improvement_v2.csv` | 11 rows, rect excluded |

Source CSV mtime still 2026-08-03 15:45 - not modified. v1 outputs are
byte-identical to their staged versions (their 11:31 mtime comes from the earlier
full-package smoke test, not this task) and live in a separate folder.

### Judgement worth recording

A single shared y-axis is dimensionally fine - both series are rates in [0, 1] -
but it does place values from different populations side by side, which v1
deliberately avoided by splitting into four panels. The brief asked for one panel
with the caveat in the caption, so that is what was built; the caption leads with
**DENOMINATORS CHANGE PART-WAY ALONG BOTH SERIES** and states explicitly that the
0.9784 -> 0.9667 step is a change of population, not of performance, since that is
the specific misreading a single panel invites.
