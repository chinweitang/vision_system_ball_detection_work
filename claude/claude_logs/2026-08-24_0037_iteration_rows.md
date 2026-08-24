# Work Log: Fragment-style iteration rows, six changes

**Session:** 2026-08-24_0037
**Status:** Complete
**Duration:** ~30 min

---

## Original Request

> For each row I will name, extract the exact before and after values from the CSVs
> on disk and emit a fragment-style row Trigger | Change | Measured effect | Cost
> accepted. Rows: (1) morph close kernel ellipse to rect, (2) RANSAC n_iterations 15
> to 3, (3) serial to threaded detection, (4) min_area 200 to 30, (5)
> trajectory-coherence filter added, (6) exclusion masks added. Write
> src/regen_2class/build_iteration_rows.py, output to
> data/regenerate_figures/iteration_rows.md. Log to claude/claude_logs/. STOP and
> report rather than guessing if any value cannot be found in a CSV; leave that cell
> as NOT_FOUND. Every number must trace to a file path, which must be printed
> alongside it.

---

## Result

**68 values extracted, all traced. 2 emitted as NOT_FOUND rather than guessed.**

Provenance is enforced structurally, not by discipline: every value is a `Val`
object carrying its own file path and locator, and the renderer cannot emit one
without a source. A value that no CSV holds returns `NOT_FOUND` and is appended to
an UNRESOLVED list that prints both to stdout and into the document.

Values per row: 1 -> 21, 2 -> 8, 3 -> 7, 4 -> 9, 5 -> 10, 6 -> 13.

Nine source CSVs. Numbers living inside free-text `headline_numbers` cells of the
two history CSVs are pulled by regex against the actual cell text, so they are read
from the file rather than transcribed; the locator names the row and the column.

---

## Path correction

`data/detector_tuning/results_history.csv` does not exist - it is at
`data/detector_tuning/history/results_history.csv`. Same correction as the
2026-08-24_0010 reconciliation task.

---

## The two NOT_FOUND cells

**Row 2, RANSAC 15 -> 3: the after-value does not exist in any CSV.**
`timing_history.csv` records only the 15-iteration baseline (335.3-1175.3 ms across
8 flights), and its own notes say "RANSAC n_iterations sweep still pending (Task
2)". No file records a RANSAC-wrapped Model-C fit timed at 3 iterations.

The tempting substitute is `pipeline_sweep_raw.csv`'s `ransac_ms` (median 162.6 ms,
max 338.2 ms, n=2481) - which does run at `N_ITERATIONS = 3`. It is **not** the same
quantity: it wraps all four LSQ fits rather than the Model-C RANSAC fit alone, and
covers 107 flights against stage 1's 8. It is reported in the cell as an adjacent
measurement, explicitly labelled as not the after-value. The accuracy cost of
dropping to 3 iterations is not quantified in any CSV either.

**Row 3, serial -> threaded: the before-value cannot be isolated.** The only serial
detection figure in a CSV (`timing_history.csv` stage 1, 88.66-89.80 ms/frame/cam)
was measured with the **ellipse** kernel. Reading serial-vs-threaded off it would
also absorb row 1's 17.6x kernel speedup, so the two effects cannot be separated
from CSVs. The threaded after-value is computed from `pipeline_sweep_raw.csv`
(median 13.71 ms, p95 15.11 ms, n=2481).

The isolated number does exist - `parallel_detect_checkpoint_20260804.json`, and a
derived "1.27x vs serial" line in the sweep's `summary.txt` - but neither is a CSV,
so both are named under UNRESOLVED rather than used. **Worth noting for the report:
threading alone bought 1.27x, not 2x; nearly all of the 89 -> 13.7 ms improvement is
the kernel change, not the threading.**

---

## Confounds found and handled

**Row 6 would have double-counted row 4.** The history's own v3 -> v4 comparison is
0.8552 -> 0.9784, but those two rows differ in `min_area` (200 vs 30) as well as
mask version, so that delta is mostly row 4's effect. Re-read at a **fixed
min_area=30** using the round-3 sweep winner, the true v3 -> v4 step is
**0.9751 -> 0.9784** - an order of magnitude smaller than the history's framing
implies. Stated in the row and in the caveats.

**Row 5 is confounded and cannot be fixed.** The history bundles mask v2 with the
trajectory filter in one entry, and its per-flight source is recorded verbatim as
`NOT RECOVERABLE (original CSV overwritten before this history file existed)`. The
row carries that string rather than papering over it.

**Row 5's direction is not a regression.** Combined rate falls 0.8740 -> 0.7549
(-11.91 pp) while recall holds at 0.9259. The filter removes counted-but-wrong
detections, so the drop is false positives leaving - the row says so, because a
reader scanning the table would otherwise read it as a loss.

---

## Discrepancy against the worklog prose

**"13 improved" vs 12.** The history row for the rect kernel says 83 of 163 flights
regressed >2pp and "only 13 improved >2pp". Recomputed from
`rect_vs_ellipse_comparison.csv`: strict `>2` gives **12**, `>=2` gives **13**. The
entire difference is one flight sitting exactly on the boundary at +2.00 pp,
`2026_07_21_gym/flight_69`; the history counts `>=2`. Both counts and the boundary
flight are emitted rather than silently picking one convention.

(The regression count is unaffected - 83 either way, and it matches the CSV's own
`flagged_regression` column exactly.)

**Hotspot point totals differ from the prose.** History says "total rejected points
181 -> 86". Summing `total_points` over the bins the two audit CSVs list gives
**126 -> 42**. The bin counts do match (13 -> 9), so the prose figure is a wider
population of rejected points than the hotspot CSVs enumerate. The CSV numbers are
used; the prose figure is flagged as not reproducible from these files rather than
quoted.

---

## Notable content

- Row 1 is the same ellipse/rect conflict surfaced on 2026-08-24_0010: accepted for
  the real-time path because detection was the binding constraint, while the
  detector-tuning history records the identical change as NOT RECOMMENDED for
  production. Both facts are in the row.
- Row 4 (min_area 200 -> 30) is the only change in the set where **both** metrics
  improve with a single variable moved - min_circ held at 0.30. The cleanest win.
- Row 4's cost is indirect: the looser area floor is what raised the hotspot count
  and forced the mask v4 round in row 6. 2 of 24 grid combos failed the recall gate,
  so the floor could not simply be dropped without checking recall.

---

## Caveats written into the document

Four, so the fragments cannot be lifted into a report and misread:

1. **Recall populations differ.** Rows 5 and 6's v2/v3 figures are `flight_01 only
   (54 points)`; rows 4 and 6's v4 figures are `flight_01 + flight_22 (240 points)`.
   Recall is not comparable across that boundary.
2. **Flight populations differ.** Rows 4, 5, 6 are 10-flight numbers; row 1's
   accuracy is the full 163. Compare only within a row.
3. Row 5's confound and its unrecoverable source.
4. The hotspot-total discrepancy above.

---

## Outputs

| file | contents |
|---|---|
| `src/regen_2class/build_iteration_rows.py` | the extractor |
| `data/regenerate_figures/iteration_rows.md` | 6 fragment rows, source list, 68-row value-level provenance table, UNRESOLVED section, caveats |
| this log | |

All nine input CSVs opened read-only; none modified. Nothing re-run.
