# Work Log: Detection improvement figure across iteration stages

**Session:** 2026-08-24_0052
**Status:** Complete

Related: [2026-08-24_0037_iteration_rows.md](2026-08-24_0037_iteration_rows.md)
covered the same history CSV as fragment rows. This one plots it.

Logging incrementally per Section 10 of `claude/claude_rules.md` (the previous two
tasks in this session were written up as end-of-task dumps, which broke that rule).

---

## Original Request

> Read data/detector_tuning/history/results_history.csv. Do not modify it. Write
> src/regen_2class/detection_improvement_figure.py plotting avg_combined_rate and
> labelled_recall across the chronological iteration stages, one marker per history
> row, x-axis the stage label. Output to data/regenerate_figures/detection_improvement/.
> Log to claude/claude_logs/. STOP if any row's recall point count differs from
> another row's without being annotated, and report which rows are not comparable
> rather than plotting them on the same axis: the 54-point and 240-point recall
> populations are different denominators. STOP if any row's flight population differs
> from another's without annotation (10-flight sample vs 163-flight). Annotate the
> ellipse and rect rows distinctly. Do not interpolate between stages.

---

## [00:52] Step 1 - read the source, enumerate the populations

12 rows in `data/detector_tuning/history/results_history.csv`. Opened read-only.

### Annotation completeness - checked before anything else

Both STOP conditions test for a population difference **that is not annotated**.
Checked programmatically:

- rows carrying a value but with blank `n_flights`: **none**
- rows carrying a recall but with blank `labeled_recall_flights`: **none**

So neither STOP fires. Every row that carries a number also carries its
denominator, in `n_flights` and in `labeled_recall_flights`. The populations DO
differ, which is why the second half of the instruction applies: report the
non-comparable groups and keep them off a shared axis.

### The populations

| group | rows | denominator |
|---|---|---|
| combined rate, 10-flight sample | 1, 3, 5, 6, 10 | 10 flights |
| combined rate, full dataset | 11, 12 | 163 flights |
| recall, flight_01 only | 1, 3, 5, 6 | 54 points |
| recall, flight_01 + flight_22 | 10, 11, 12 | 240 points |

Rows 2, 4, 7, 8, 9 record no rate at all - they are sweep and audit stages. They
keep their x position (chronology is the point) but carry no marker.

### Finding: the two metrics change denominator at DIFFERENT stages

Row 10 is a **10-flight** combined rate but a **240-point** recall. So the
combined-rate split and the recall split are not the same partition - the recall
denominator changes one stage earlier (at round 3, row 7) than the flight
population does (at row 11). A single "before/after" vertical divider would
therefore be wrong for one of the two metrics. Four separate panels it is.

---

## [01:02] Step 2 - wrote the script, and a guard caught a real bug

`src/regen_2class/detection_improvement_figure.py`. First run **STOPPED**:

```
*** STOP ***
stage string matched 2 label keys, expected exactly 1:
  rect close kernel validation (MORPH_ELLIPSE->MORPH_RECT, close_k=30 only, ...
LABEL_KEYS is out of date with the history file.
```

**Root cause, and it was mine.** The rect row's `stage` text ends with
`- FULL 163-FLIGHT DATASET`, exactly the substring I had chosen as the key for the
ELLIPSE row. So `ELLIPSE_KEY` matched BOTH rows 11 and 12.

Had the guard not been there, the rect row would have been drawn with the ellipse
marker and the ellipse label - i.e. the one thing the brief specifically asked to
annotate distinctly would have been annotated wrongly, and the figure would have
looked entirely plausible.

**Fix:** key the ellipse row on `FULL 163-FLIGHT DATASET (current)`. The
`(current)` suffix is on row 11 only.

**Second fix, from the same lesson.** `short_label()` only checked one direction:
how many keys match a given row. It could not catch one key matching two rows -
which is precisely what happened. Added `gate_labels()`, which asserts every key
matches exactly one row AND every short label is unique, and STOPs naming the
colliding rows.

---

## [01:03] Step 3 - both gates PASS, figure written

```
GATE 1 recall annotation PASS: point counts [54, 240], every row carrying a recall names its own
GATE 2 flight annotation PASS: populations ['10', '163'], every row carrying a value names its own
```

Neither STOP condition fires, because both test for an UNANNOTATED difference and
the CSV annotates every one. The differences themselves are real and are handled
by splitting the panels.

Groups reported rather than co-plotted:

| panel | rows | denominator |
|---|---|---|
| combined rate, 10-flight sample | 1, 3, 5, 6, 10 | 10 flights |
| combined rate, full dataset | 11, 12 | 163 flights |
| labelled recall, flight_01 only | 1, 3, 5, 6 | 54 points |
| labelled recall, flight_01 + flight_22 | 10, 11, 12 | 240 points |
| no rate recorded (sweep/audit) | 2, 4, 7, 8, 9 | - |

Four panels, four independent y-axes, shared x. No connecting lines anywhere.

---

## [01:20] Step 4 - second bug, caught by looking at the render

The "no value in this panel" dashes were visible in **panel 1 only**. They were
being placed at `min(values) - pad` BEFORE `set_ylim` ran, and the y-limits are
computed from a span with a 0.02 floor. Any panel whose values span less than that
floor put the dashes below its own axis, where they were clipped away silently.

Panels 2, 3 and 4 all span under 0.02 (0.0215, 0.0185, 0.0375 - two of the three),
so three of four panels lost the marker that distinguishes "not measured here" from
"measured as zero" - the exact ambiguity the marker exists to remove.

**Fix:** set the y-limits first, then place the dashes at 5% of the final axis
range. Verified on the re-render: dashes now present in all four panels.

Both bugs this task were caught by a check rather than by luck - the first by a
guard I had written, the second by reading the PNG. Worth keeping both habits.

---

## [01:28] Step 5 - complete

| output | |
|---|---|
| `src/regen_2class/detection_improvement_figure.py` | the script |
| `data/regenerate_figures/detection_improvement/detection_improvement.png` | 4 panels, 6.6 in wide at 300 dpi |
| `data/regenerate_figures/detection_improvement/detection_improvement_rows.csv` | 12 rows, one per history row, with parsed denominators and kernel marker |

Source `results_history.csv` mtime still 2026-08-03 15:45 - not modified. Nothing
re-run, no fitting, no detection.

### What the figure shows

Within panel 1 (10-flight sample), the arc is 0.2772 baseline -> 0.9784. Two
things a reader should not misread, both captioned:

- The dip at `+ mask v2 + traj filter` (0.8740 -> 0.7549) is not a regression - the
  trajectory filter removes false positives that were inflating the rate, and
  recall is unchanged at 0.9259 across those three stages.
- The final 163-flight number (0.9667) is LOWER than the 10-flight sample (0.9784),
  which is a population change, not a regression. They are in different panels
  precisely so that step is not read as a drop.

Panel 4 carries the only like-for-like pair: ELLIPSE 0.9250 -> RECT 0.8875 recall,
alongside 0.9667 -> 0.9452 combined in panel 2.

### Not done, flagged

The palette was not machine-validated - `validate_palette.js` is not present on this
machine (confirmed by a filesystem search this session). The three marker colours
are from the documented categorical order used elsewhere in this figure set, but the
green/red ellipse-vs-rect pair in particular should be re-checked for CVD separation
before print, since that distinction is the one the brief asked to make legible.

---

## [01:31] Session-wide data-protection verification

Full-tree scan of `data/` for files modified today (the earlier check was scoped to
three folders, and ran before this task's outputs existed):

```
00:10  data/regenerate_figures/detection_rates_reconciled.txt
00:25  data/regenerate_figures/stage_timing/figure_stage_timing_breakdown.png
00:25  data/regenerate_figures/stage_timing/stage_timing_by_class_window.csv
00:37  data/regenerate_figures/iteration_rows.md
01:28  data/regenerate_figures/detection_improvement/detection_improvement.png
01:28  data/regenerate_figures/detection_improvement/detection_improvement_rows.csv
```

Six files, all requested outputs, all under `data/regenerate_figures/`. No
pre-existing file anywhere under `data/` was overwritten or deleted across any of
the four tasks this session - `detector_tuning/`, `pi_benchmarking/`, session
captures and `calibration_outputs/` all untouched. Section 2 of `claude_rules.md`
satisfied session-wide.
