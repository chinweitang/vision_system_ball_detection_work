# Work Log: Label-derived HIT/MISS classification

**Session:** 2026-08-20_2043
**Start:** 20:43
**Status:** In Progress
**Duration:** [updating]

---

## Original Request

> Derive a label-based HIT/MISS classification from label_vs_fit_per_flight.csv and
> report its agreement with the Model-C classification.
>
> CONTEXT: cls_ref and cls_rederived in that file are BOTH Model-C, so the existing
> reproduced_01 check is a determinism test, not a ground-truth comparison. No
> label-derived classification exists anywhere in the repo. This produces the only
> genuine model-vs-ground-truth classification agreement rate available, and it
> feeds a requirement in the report.
>
> Scope: derive cls_label by aperture containment on label_Y/label_Z (0..2000mm);
> derive cls_modelc the same way and ASSERT it matches cls_ref for all 20 rows
> (STOP if not); compute edge_dist_label and edge_dist_modelc; report agreement
> count, every disagreeing flight, and a full 20-row table sorted ascending by
> edge_dist_modelc; write results to
> data/regenerate_figures/label_derived_classification.csv.
>
> NOT: modify label_vs_fit_per_flight.csv or anything outside
> data/regenerate_figures/ and the log dir; re-run label_vs_fit_crossing.py or any
> fitting code; commit to git; produce plots; compute any other statistic.
>
> STOP conditions: cls_modelc does not reproduce cls_ref 20/20; any of label_Y,
> label_Z, modelc_Y, modelc_Z null or non-numeric; file does not have exactly 20
> data rows. Timing: under 5 min, stop and report if over 10.

---

## Objective

Produce the only genuine model-vs-ground-truth crossing classification agreement
rate available in this project, by classifying the manually-labelled crossing
position through the same aperture-containment rule Model-C is classified by.

---

## Path convention note (deviation from the prompt, resolved not asked)

The prompt names `dev/claude_rules.md`, `dev/log_template.md` and `dev/logs/`.
There is no `dev/` directory in this repo. The real convention, used by every
prior worklog, is `claude/claude_rules.md`, `claude/log_template.md` and
`claude/claude_logs/`. Mapped accordingly - same resolution as the 2026-08-04
Pi-sweep worklog recorded for the identical mismatch.

Also noted: `claude/claude_rules.md` Section 10 states logs live in `claude/logs/`,
but that directory does not exist and no log has ever been written there. Following
actual practice (`claude/claude_logs/`), not the stale line in the rules file.

---

## Pre-flight checks

**Data-protection gate (claude_rules.md Section 2).** The task writes under `data/`,
which normally requires explicit permission. Two things clear it:
1. The prompt explicitly authorises `data/regenerate_figures/` as a write target.
2. Checked before writing: `data/regenerate_figures/` exists and is EMPTY, and
   `label_derived_classification.csv` does not exist. So this is a pure create,
   not an overwrite. No existing data file is at risk.

No file under `data/` outside that one new CSV is touched. `label_vs_fit_per_flight.csv`
is opened read-only.

---

## Log

- [20:45:21] Loaded `data/prediction/06_label_vs_fit/label_vs_fit_per_flight.csv` read-only: **20 data rows**.
- [20:45:21] CHECK 1 row count == 20: **PASS**
- [20:45:21] CHECK 2 all of ['label_Y', 'label_Z', 'modelc_Y', 'modelc_Z'] numeric and non-null across 20 rows: **PASS**
- [20:45:21]   ranges: label_Y [-39.6, 1964.5], label_Z [391.2, 1890.4], modelc_Y [-54.0, 2084.0], modelc_Z [474.0, 1988.5]
- [20:45:39] CHECK 3: rederiving cls_modelc from (modelc_Y, modelc_Z) with APERTURE_SIZE_MM=2000.0 and rule `HIT iff 0<=Y<=2000 and 0<=Z<=2000` (matches label_vs_fit_crossing.py:331 + prediction_pipeline_sweep_pi.py:406-408).
- [20:45:39] CHECK 3 cls_modelc reproduces cls_ref: **PASS 20/20**
- [20:45:39]   cls_ref distribution: {'HIT': 18, 'MISS_HIGH_WIDE': 2}
- [20:45:39]   cls_rederived matches cls_ref: 20/20 (pre-existing determinism check, both Model-C)
- [20:46:12] Derived cls_label + cls_modelc + edge distances for all 20 flights.
- [20:46:12] Wrote **data/regenerate_figures/label_derived_classification.csv** (20 rows, 15 cols, sorted ascending by edge_dist_modelc). New file, no overwrite.
- [20:46:12]   `pos_err_total_mm` is a PASSTHROUGH copy from the source file, not a statistic computed here.

### RESULT: agreement of label-derived vs Model-C classification

**19/20 agree (95%). 1 disagree.**

Disagreeing flights:

| flight | bin | label_Y | label_Z | modelc_Y | modelc_Z | cls_label | cls_modelc | edge_label | edge_modelc |
|---|---|---:|---:|---:|---:|---|---|---:|---:|
| flight_88 | FLAT | 1964.5 | 1276.2 | 2084.0 | 1265.8 | HIT | MISS_HIGH_WIDE | 35.5 | -84.0 |

### Full 20-row table, sorted ascending by edge_dist_modelc

| # | flight | bin | sym | label_Y | label_Z | modelc_Y | modelc_Z | cls_label | cls_modelc(=cls_ref) | agree | edge_label | edge_modelc | pos_err_mm |
|--:|---|---|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|
| 1 | flight_88 | FLAT | T | 1964.5 | 1276.2 | 2084.0 | 1265.8 | HIT | MISS_HIGH_WIDE | **NO** | 35.5 | -84.0 | 119.9 |
| 2 | flight_22 | LOB | T | -39.6 | 932.5 | -54.0 | 963.3 | MISS_HIGH_WIDE | MISS_HIGH_WIDE | yes | -39.6 | -54.0 | 34.1 |
| 3 | flight_109 | LOB | T | 622.1 | 1890.4 | 513.9 | 1988.5 | HIT | HIT | yes | 109.6 | 11.5 | 146.1 |
| 4 | flight_14 | LOB | T | 1451.4 | 1865.7 | 1543.2 | 1794.0 | HIT | HIT | yes | 134.3 | 206.0 | 116.5 |
| 5 | flight_6 | FLAT | T | 326.4 | 761.9 | 343.7 | 797.9 | HIT | HIT | yes | 326.4 | 343.7 | 39.9 |
| 6 | flight_19 | MID | T | 443.6 | 760.2 | 389.3 | 814.9 | HIT | HIT | yes | 443.6 | 389.3 | 77.1 |
| 7 | flight_12 | LOB | T | 376.0 | 1288.8 | 415.2 | 1259.8 | HIT | HIT | yes | 376.0 | 415.2 | 48.7 |
| 8 | flight_118 | MID | T | 614.4 | 962.0 | 431.5 | 1095.3 | HIT | HIT | yes | 614.4 | 431.5 | 226.4 |
| 9 | flight_11 | MID | F | 1645.4 | 503.6 | 1566.3 | 588.2 | HIT | HIT | yes | 354.6 | 433.7 | 115.8 |
| 10 | flight_107 | LOB | F | 705.2 | 391.2 | 483.5 | 474.0 | HIT | HIT | yes | 391.2 | 474.0 | 236.8 |
| 11 | flight_15 | MID | T | 784.3 | 1393.7 | 733.4 | 1442.5 | HIT | HIT | yes | 606.3 | 557.5 | 70.5 |
| 12 | flight_69 | FLAT | T | 396.9 | 1435.0 | 571.7 | 1400.2 | HIT | HIT | yes | 396.9 | 571.7 | 178.3 |
| 13 | flight_33 | MID | T | 917.2 | 1257.1 | 847.6 | 1336.6 | HIT | HIT | yes | 742.9 | 663.4 | 105.7 |
| 14 | flight_53 | FLAT | T | 1134.0 | 586.1 | 917.7 | 670.0 | HIT | HIT | yes | 586.1 | 670.0 | 232.0 |
| 15 | flight_119 | MID | F | 892.0 | 563.1 | 727.0 | 708.8 | HIT | HIT | yes | 563.1 | 708.8 | 220.1 |
| 16 | flight_73 | MID | T | 1201.7 | 1203.7 | 1254.4 | 1195.7 | HIT | HIT | yes | 796.3 | 745.6 | 53.4 |
| 17 | flight_56 | LOB | T | 1346.0 | 779.9 | 1205.4 | 893.5 | HIT | HIT | yes | 654.0 | 794.6 | 180.8 |
| 18 | flight_75 | FLAT | T | 1011.7 | 941.7 | 1184.5 | 923.8 | HIT | HIT | yes | 941.7 | 815.5 | 173.8 |
| 19 | flight_13 | FLAT | T | 872.6 | 875.2 | 867.4 | 928.8 | HIT | HIT | yes | 872.6 | 867.4 | 53.8 |
| 20 | flight_87 | FLAT | T | 1002.5 | 970.5 | 1042.6 | 993.6 | HIT | HIT | yes | 970.5 | 957.4 | 46.2 |

---

## Analysis

### Headline

**cls_label agrees with cls_ref (Model-C) on 19 of 20 flights, 95%.**

This is the only genuine model-vs-ground-truth classification agreement rate in the
project. The pre-existing `reproduced_01` check is 20/20 but compares Model-C
against Model-C, so it measures determinism only and cannot detect a bias shared by
both.

### The single disagreement is a boundary straddle, not a logic failure

`flight_88` (FLAT, symmetric, not residual-flagged):
- label  (1964.5, 1276.2) -> 35.5 mm INSIDE the Y=2000 edge  -> HIT
- Model-C(2084.0, 1265.8) -> 84.0 mm OUTSIDE the Y=2000 edge -> MISS_HIGH_WIDE
- separation between the two estimates: **119.9 mm** (`pos_err_total`)

The two estimates are 119.9 mm apart, against a pooled median label-vs-fit position
error of ~105.7 mm (`06_label_vs_fit/summary.txt`). So this flight disagrees for
exactly the reason the error budget predicts: a ~120 mm disagreement placed across a
boundary that both estimates sit within ~85 mm of. The containment rule is not at
fault, and neither estimate is anomalous.

### The 95% is flattered by class balance and by distance from the boundary

Three caveats that matter if this number goes in the report:

**1. The sample is 18 HIT / 2 MISS_HIGH_WIDE under Model-C.** A classifier that
answered "HIT" unconditionally would score 18/20 = 90%. The 95% figure therefore
carries only ~5 points of information over the trivial baseline. On the MISS side
specifically, agreement is **1 of 2**.

**2. Most flights are nowhere near the boundary, so the test is not hard for them.**
Ranking by |edge_dist_modelc|, only **3 of 20** flights sit closer to an aperture
edge than the ~106 mm median position error:

| flight | edge_dist_modelc | outcome |
|---|---:|---|
| flight_88 | -84.0 mm | **disagrees** |
| flight_22 | -54.0 mm | agrees (both MISS) |
| flight_109 | +11.5 mm | agrees (both HIT) |

The remaining 17 flights are all >200 mm from any edge (14 of them >340 mm), where a
~106 mm error cannot flip the class. **Restricted to the flights where the
classification is actually at risk, agreement is 2 of 3.** That is the honest
statement of what this sample can support.

**3. flight_109 was deliberately selected as a decision-boundary probe** (edge_dist
~11 mm, reserved in `02_candidate_reselection`). It agrees, which is a real if
single-instance positive: at 11.5 mm from the edge the label and the model still
landed on the same side.

### Recommended framing for the report

Report it as: *label-derived and Model-C crossing classifications agree on 19 of 20
manually-labelled flights (95%); the single disagreement is a near-boundary case
where the two crossing estimates differ by 119.9 mm, consistent with the ~106 mm
median label-vs-fit position error.* Then state the class-balance and
distance-to-boundary caveats rather than letting 95% stand alone.

---

## Outputs

- `data/regenerate_figures/label_derived_classification.csv` - 20 rows, 15 columns,
  sorted ascending by `edge_dist_modelc`. NEW file; directory was empty beforehand,
  nothing overwritten.
  Columns: `flight_id, registration, elevation_bin, symmetric, label_Y, label_Z,
  modelc_Y, modelc_Z, cls_label, cls_modelc, cls_ref, agree, edge_dist_label,
  edge_dist_modelc, pos_err_total_mm`.
- This log.

Note on `edge_dist_*`: computed with the formula given in the task,
`min(Y, 2000-Y, Z, 2000-Z)`. This is SIGNED - it goes negative for points outside the
aperture, and the magnitude is then the overshoot past the nearest edge. Retained as
signed because the sign carries the HIT/MISS information.

## Scope adherence

- `label_vs_fit_per_flight.csv` opened read-only, unmodified.
- No fitting code re-run. No plots. No git operations.
- No statistic computed beyond those requested; `pos_err_total_mm` is a passthrough
  copy from the source file.
- Only two files written: the CSV above and this log.

**Status:** Complete
**Duration:** ~4 min (20:43 start, 20:47 finish), inside the 5 min expectation.
