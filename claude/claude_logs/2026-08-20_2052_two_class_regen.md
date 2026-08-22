# Work Log: Two-class (SHORT/LONG) figure regeneration

**Session:** 2026-08-20_2052
**Start:** 20:49
**Status:** In Progress - Steps 1-2, holding at CHECKPOINT 1
**Duration:** [updating]

---

## Original Request

> Regenerate the timing, convergence and duration figures under a two-class scheme
> (SHORT / LONG at a 45 degree elevation cut), and produce a new per-flight outcome
> sweep that counts success, late, wrong and no-response across the T grid.
>
> CONTEXT: the existing three-class scheme (FLAT/MID/LOB) is being replaced because
> the elevation distribution is bimodal and MID (n=12) sits in the sparse valley.
> The existing deadlines were not derived by a consistent rule: FLAT 490 is
> min-anchored, MID 710 and LOB 1080 are not. This run recomputes both class
> deadlines by a single stated rule.
>
> STEP 1 CLASSES: SHORT = FLAT union MID, LONG = LOB. Cross-check vs elevation_deg;
> assert SHORT < 45 and LONG >= 45. STOP on mismatch. Expected 47 / 60 / 107.
> STEP 2 DEADLINES: per class print n/min/P5/P25/median/max of launch_to_crossing_ms.
> deadline = min rounded DOWN to nearest 10 ms. No hardcoded 490/710/1080.
> CHECKPOINT 1: STOP, report, wait for approval before Step 3.
> STEP 3 JOIN, STEP 4 FIG A margin, STEP 5 FIG B convergence, STEP 6 FIG C duration,
> CHECKPOINT 2, STEP 7 FIG D outcome sweep. All outputs to data/regenerate_figures/,
> 150 dpi.
>
> NOT: write outside data/regenerate_figures/ and the log dir; modify any existing
> CSV/JSON/script; re-run any Pi/capture/detection/fitting job; git; regenerate
> unlisted figures; call position_error_mm accuracy; use last_pair_detect_ms as a
> timestamp; hardcode deadlines; drop fit_failed from Figure D.

---

## Objective

Replace the three-class FLAT/MID/LOB scheme with a two-class SHORT/LONG split at a
45 degree elevation cut, with both class deadlines derived by one consistent
min-anchored rule, and add a per-flight outcome sweep.

---

## Path convention

Prompt says `dev/`; no such directory exists. Using the repo's real convention
`claude/claude_rules.md`, `claude/log_template.md`, `claude/claude_logs/` - same
mapping as every prior worklog. Rules file already read this session.

---

## Log

### STEP 1 - CLASSES

- [20:50:26] Read `data/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv` (2568 rows) and `data/prediction/04_launch_to_crossing_budget/launch_to_crossing.csv` (107 rows), both read-only.
- [20:50:26] bin is consistent across all 24 T rows for every flight: **PASS** (107 flights)
- [20:50:26] Mapping applied: SHORT = FLAT union MID, LONG = LOB.
- [20:50:26]   source bin counts: {'LOB': 60, 'MID': 12, 'FLAT': 35}
- [20:50:26]   **class counts: SHORT=47, LONG=60, total=107**
- [20:50:26]   expected 47 / 60 / 107: **PASS**
- [20:50:26] All 107 sweep flights present in launch_to_crossing.csv on (session, flight_id): **PASS**
- [20:50:26] Elevation cross-check at the 45 deg cut (107 flights):
- [20:50:26]   **PASS - 0 mismatches.** Every SHORT flight has elevation < 45, every LONG >= 45.
- [20:50:26]   SHORT elevation range [-6.04, 44.22] deg  (n=47)
- [20:50:26]   LONG  elevation range [45.10, 60.38] deg  (n=60)
- [20:50:26]   gap across the cut: SHORT max 44.22 -> LONG min 45.10 = 0.88 deg of empty elevation

### STEP 2 - DEADLINES

- [20:50:54] Source column: `launch_to_crossing_ms` from launch_to_crossing.csv.
- [20:50:54] Percentiles by linear interpolation between order statistics (numpy default).

| class | n | min | P5 | P25 | median | max |
|---|--:|--:|--:|--:|--:|--:|
| SHORT | 47 | 491.5 | 507.5 | 567.5 | 620.1 | 1120.6 |
| LONG | 60 | 1047.8 | 1080.0 | 1162.4 | 1240.7 | 1559.3 |

- [20:50:54] **RULE (single, applied identically to both classes):**
      deadline(class) = floor( min(launch_to_crossing_ms over that class) / 10 ) * 10
      i.e. the population minimum, rounded DOWN to the nearest 10 ms.
      Min-anchored, not percentile-anchored: no flight in the class is allowed to
      have already crossed before the deadline.

- [20:50:54] **deadline(SHORT) = 490 ms**   (min 491.4509 -> floor to 10 ms)
- [20:50:54] **deadline(LONG) = 1040 ms**   (min 1047.7817 -> floor to 10 ms)

- [20:50:54] **Change vs the previous three-class scheme:**
    - SHORT deadline 490 ms. The old FLAT deadline was also min-anchored and
      came out at the same 490 ms, so SHORT is unchanged in value despite now
      covering FLAT+MID (n=47, not 35). MID's old 710 ms (a P5) is discarded.
    - LONG deadline 1040 ms, **down from the previously used 1080 ms**. The old
      1080 was LOB's P5, not its minimum, so it permitted the earliest-crossing 5%
      of lobs to cross before the deadline had even elapsed. Under the min rule the
      LONG budget tightens by 40 ms.
    - No deadline value is hardcoded anywhere; both are computed from the CSV above.

- [20:50:54] Sanity: SHORT max 1120.6 ms vs LONG min 1047.8 ms
      -> the two class duration ranges OVERLAP by 72.8 ms.
      Quantified as the confusion region in Step 6 (Figure C).

- [20:50:54] **CHECKPOINT 1 REACHED - holding. No figures written, no files created in
      data/regenerate_figures/. Awaiting approval before Step 3.**

---

### CHECKPOINT 1 APPROVED by Chin Wei - continuing to Step 3.

### Palette (dataviz skill, loaded before writing any plotting code)

- [20:55:41] Categorical slots 1 and 8 of the reference palette: SHORT `#2a78d6` (blue), LONG `#e34948` (red).
- [20:55:41] Validated with `scripts/validate_palette.js "#2a78d6,#e34948" --mode light`: **ALL CHECKS PASS**
      lightness band PASS, chroma floor PASS, CVD separation PASS (protan dE 21.6, tritan 34.5),
      normal-vision floor PASS (dE 32.3), contrast vs surface PASS (both >= 3:1).
      Not eyeballed. Same pair the RANSAC thesis figures already use, so the new
      figures stay visually consistent with the existing report set.

### STEP 3 - JOIN

- [20:55:41] Read with `csv.DictReader` (proper quoted-field parsing, NOT a comma split).
      crossing_classification.csv carries `crossing_vel_xyz` as a quoted JSON-style list
      in one field; DictReader handles it. Verified: 15 columns parsed, crossing_vel_xyz reads as [3099.2768060316394, 5063.11...
- [20:55:41] Lookups keyed on **(session, flight_id)**, never on flight id alone. launch=107 unique, crossing_classification=163 unique, 0 duplicates.
- [20:55:41] Bare-id hazard confirmed present in the data: `flight_13` appears in 2 sessions ['2026_07_15_gym', '2026_07_21_gym']. A bare-id join would collide these.
- [20:55:41] duration_ms present and non-blank for all 107 flights: **PASS**
- [20:55:41] ASSERT rows after join == 2568: got **2568** -> **PASS**
- [20:55:41] ASSERT distinct flights == 107: got **107** -> **PASS**
- [20:55:41] ASSERT distinct T values == 24: got **24** -> **PASS**
- [20:55:41] ASSERT no duplicate (session, flight, T): 0 duplicates -> **PASS**
- [20:55:41] Join is 1:1, no row multiplication, no dropped rows.
- [20:55:41]   class row split: {'LONG': 1440, 'SHORT': 1128} (SHORT 47x24=1128, LONG 60x24=1440)
- [20:55:41]   status split: {'ok': 2481, 'fit_failed': 87} (87 fit_failed expected, treated as data)
- [20:55:41] Wrote **data/regenerate_figures/two_class_join.csv** (2568 rows, 19 cols). New file, no overwrite.

### STEP 4 - FIGURE A: margin vs cutoff

- [20:58:40] deadlines recomputed in-script from joined data, not hardcoded: SHORT=490 LONG=1040
- [20:58:40] margin_p95(T) = deadline(class) - T - p95(latency_ms of that class at T).
- [20:58:40] latency_ms is populated only on status==ok rows; p95 taken over those, n logged per T.
- [20:58:40] **max-usable-T defined as the largest T with margin_p95(T) >= -84 ms**, i.e. still inside the
      target-mode budget. Same inequality as Step 7 in_time (t_obs + latency <= crossing + 84),
      rearranged. Stated explicitly because the task supplies the -84 reference line but does
      not restate the max-usable-T rule.
- [20:58:40] **max-usable-T: SHORT = 350 ms, LONG = 800 ms**

| T_ms | SHORT margin_p95 | n_ok | LONG margin_p95 | n_ok |
|--:|--:|--:|--:|--:|
| 150 | 201.0 | 37 | 739.5 | 25 |
| 200 | 151.0 | 45 | 671.9 | 45 |
| 250 | 83.7 | 45 | 615.0 | 51 |
| 300 | 18.9 | 47 | 553.5 | 59 |
| 350 | -38.5 | 47 | 490.3 | 60 |
| 400 | -95.3 | 47 | 437.3 | 60 |
| 450 | -167.6 | 47 | 376.8 | 59 |
| 490 | -204.8 | 47 | 332.3 | 59 |
| 500 | -232.3 | 47 | 315.2 | 59 |
| 550 | -290.4 | 47 | 257.1 | 59 |
| 600 | -336.9 | 47 | 189.0 | 60 |
| 650 | -399.4 | 47 | 140.8 | 60 |
| 700 | -457.0 | 47 | 65.1 | 60 |
| 750 | -526.8 | 47 | 21.0 | 60 |
| 800 | -572.6 | 47 | -38.8 | 59 |
| 850 | -623.6 | 47 | -98.1 | 60 |
| 900 | -693.6 | 47 | -170.5 | 59 |
| 950 | -757.1 | 47 | -218.0 | 60 |
| 1000 | -811.2 | 47 | -293.4 | 60 |
| 1050 | -862.7 | 47 | -344.8 | 60 |
| 1100 | -916.7 | 47 | -411.1 | 56 |
| 1150 | -987.7 | 47 | -446.7 | 60 |
| 1200 | -1008.3 | 46 | -516.8 | 59 |
| 1250 | -1069.0 | 47 | -569.5 | 59 |

- [20:58:40] Wrote **figureA_margin_vs_cutoff.png** (150 dpi).

### STEP 5 - FIGURE B: position-error convergence

| T_ms | SHORT excl | SHORT med (mm) | SHORT IQR | LONG excl | LONG med (mm) | LONG IQR |
|--:|--:|--:|--|--:|--:|--|
| 150 | 10 | 180.3 | [126.6, 298.6] | 35 | 549.5 | [356.8, 784.4] |
| 200 | 2 | 127.4 | [92.6, 215.9] | 15 | 391.5 | [263.1, 673.5] |
| 250 | 2 | 121.3 | [78.6, 186.4] | 9 | 373.9 | [233.1, 603.7] |
| 300 | 0 | 86.3 | [63.0, 153.1] | 1 | 340.8 | [181.1, 491.3] |
| 350 | 0 | 67.8 | [53.2, 113.6] | 0 | 248.5 | [154.2, 426.8] |
| 400 | 0 | 59.9 | [35.4, 95.8] | 0 | 224.4 | [142.4, 296.8] |
| 450 | 0 | 50.1 | [30.9, 85.0] | 1 | 178.5 | [123.5, 277.5] |
| 490 | 0 | 45.6 | [27.0, 76.7] | 1 | 156.3 | [105.5, 241.6] |
| 500 | 0 | 46.3 | [28.1, 64.1] | 1 | 171.8 | [111.5, 237.7] |
| 550 | 0 | 33.3 | [19.8, 54.2] | 1 | 145.7 | [103.0, 210.4] |
| 600 | 0 | 24.8 | [17.5, 52.2] | 0 | 115.0 | [74.4, 175.9] |
| 650 | 0 | 25.7 | [17.3, 42.8] | 0 | 110.1 | [76.8, 142.9] |
| 700 | 0 | 24.1 | [12.7, 43.0] | 0 | 90.7 | [64.1, 133.2] |
| 750 | 0 | 21.7 | [12.8, 49.8] | 0 | 91.1 | [53.8, 125.2] |
| 800 | 0 | 21.7 | [13.9, 38.5] | 1 | 76.7 | [56.9, 113.2] |
| 850 | 0 | 21.6 | [11.9, 37.3] | 0 | 64.7 | [42.6, 93.8] |
| 900 | 0 | 20.4 | [11.9, 36.8] | 1 | 63.6 | [38.7, 87.7] |
| 950 | 0 | 20.4 | [12.1, 41.6] | 0 | 54.6 | [34.3, 82.1] |
| 1000 | 0 | 20.4 | [12.3, 39.3] | 0 | 51.2 | [35.4, 72.4] |
| 1050 | 0 | 21.6 | [12.3, 41.0] | 0 | 44.5 | [28.6, 64.5] |
| 1100 | 0 | 20.4 | [12.3, 36.5] | 4 | 39.3 | [23.8, 62.8] |
| 1150 | 0 | 20.4 | [12.3, 36.5] | 0 | 34.9 | [20.2, 57.7] |
| 1200 | 1 | 21.0 | [11.8, 36.9] | 1 | 34.4 | [23.3, 47.4] |
| 1250 | 0 | 20.4 | [10.3, 36.5] | 1 | 34.2 | [21.5, 51.7] |

- [20:59:27] total excluded: SHORT 15, LONG 72, combined 87 (equals the 87 fit_failed rows)
- [20:59:27] median at each max-usable-T: SHORT(T=350) = 67.8 mm, LONG(T=800) = 76.7 mm
- [20:59:27] Wrote **figureB_position_error_convergence.png** (150 dpi) and figureB_excluded_counts.csv

### STEP 6 - FIGURE C: duration distribution, crossers only

- [21:00:00] one row per FLIGHT (deduplicated from the 24-row-per-flight grid): 47 SHORT + 60 LONG = 107 flights.
| class | n | min | P5 | median | max |
|---|--:|--:|--:|--:|--:|
| SHORT | 47 | 491.5 | 507.5 | 620.1 | 1120.6 |
| LONG | 60 | 1047.8 | 1080.0 | 1240.7 | 1559.3 |

- [21:00:01] **SHORT max = 1120.6 ms**
- [21:00:01] **LONG min  = 1047.8 ms**
- [21:00:01] **CONFUSION REGION = 5 SHORT flights with duration > LONG minimum (1047.8 ms)**
      values (ms): 1059.9, 1078.6, 1081.0, 1118.6, 1120.6
      that is 5/47 = 10.6% of SHORT, 4.7% of all crossers.
- [21:00:01] Wrote **figureC_duration_distribution.png** (150 dpi).

---

### [convention change, 21:01] Mid-task instruction from Chin Wei

> Do not use python - <<'PYEOF' heredocs. Write each step's code to
> scripts/regen_2class/step_N_name.py and run it with
> python scripts/regen_2class/step_N_name.py. Set the working directory once at the
> start rather than prefixing every command with cd.

Applied from Step 7 onward. Figures A, B and C were already rendered by the time this
arrived, so they are not re-run; their code is not preserved as files unless asked.
Created `scripts/regen_2class/`.

Note this overrides the task's own "do NOT write outside data/regenerate_figures/ and
the log dir" line - the later explicit instruction wins, and `scripts/` is an allowed
create location under claude_rules.md Section 2 anyway.


### [21:06] Visual QA pass on Figures A, B, C (dataviz skill step 7 - render and look)

Opened all three PNGs and inspected rather than assuming they were clean.

- **Figure B: clean on first render.** No collisions, captions fit, IQR bands read
  correctly. Not re-rendered.
- **Figure A: two real defects, both fixed.**
  1. The budget annotation crossed the SHORT line near T=300-400 and visually read
     as labelling y=0 rather than y=-84. Moving it right-aligned above the line's
     right end fixed the first collision but it then crossed the LONG line near
     T=800. Root cause: both series sweep monotonically through y=-84, so ANY
     horizontal text band near that value is crossed by a data line somewhere
     along x - there is no clean in-plot placement for a label this long. Final
     fix: the budget line carries its label as a legend entry, legend moved below
     the axes. Same pattern used by the existing RANSAC thesis figure 2 for the
     same reason.
  2. ~15% dead whitespace below the axes once the legend moved out; cropped with
     bbox_inches="tight".
- **Figure C: one real defect, fixed.** SHORT's min (491) and P5 (508) are 17 ms
  apart, so their rotated on-line labels overlapped illegibly. Replaced the eight
  rotated on-line labels with two compact per-class monospace stat blocks placed in
  the empty band between the two clusters; the eight dotted vertical markers remain.

Figures A and C were re-rendered from the new scripts. Numbers unchanged and
re-verified identical after the fix (SHORT max-usable-T 350, LONG 800; confusion
region 5). Only my own figures from this task were overwritten - no pre-existing
data file was touched.

New files: `scripts/regen_2class/step_4_figure_a_margin.py`,
`scripts/regen_2class/step_6_figure_c_duration.py`.

---

## CHECKPOINT 2 - holding for approval

Figures A, B, C complete. Step 7 (outcome sweep) NOT started.

### CHECKPOINT 2 APPROVED - continuing to Step 7.

### STEP 7 - FIGURE D: outcome sweep

- [21:12] Palette selection for the four outcome bands, validated not eyeballed:
    - FIRST TRIED the reserved status palette (good/warning/serious/critical =
      #0ca30c/#fab219/#ec835a/#d03b3b). **FAILED**: warning vs serious measure
      normal-vision dE 13.6, under the hard 15 floor, and they are ADJACENT in the
      mandated band order (wrong then late). The skill is explicit that a
      normal-vision floor under 15 is a hard fail that secondary encoding does not
      excuse, and the band order is fixed by the task so reordering is not available.
      Also FAILED the lightness band on #fab219.
    - Root cause: a green->yellow->orange->red severity ramp has three inherently
      close adjacent warm pairs. Also arguable on the merits: late, wrong and
      no_response are three DIFFERENT KINDS of failure (timing, accuracy, no fit),
      not three degrees of one thing, so a severity ramp encodes a relationship
      that is not really there.
    - ADOPTED distinct hues: success #1baf7a, wrong #eda100, late #4a3aa7,
      no_response #e34948. Validator: lightness PASS, chroma PASS, CVD separation
      PASS (worst adjacent 9.1 protan, 27.0 tritan), normal-vision PASS (22.9).
      Contrast vs surface WARN on two slots - the relief rule is satisfied by the
      legend, the direct best-T labels, and outcome_sweep_by_class_T.csv serving as
      the table view.
- [21:12] 2px surface gap between stacked segments via edgecolor=SURF, lw=1.0.
- [21:13] **ASSERT four counts sum to panel n at every T: PASS, 3 panels x 24 T = 72
  cells checked, 0 failures.**
- [21:13] fit_failed rows retained as no_response; denominator always the class n.
  in_time and accurate are stored blank for those rows, since latency and position
  error do not exist when the fit failed.

**Best T per panel, and late/wrong co-occurrence at that T:**

| panel | n | best T | success rate | n_success | n_late | n_wrong | n_no_response | late AND wrong |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| SHORT | 47 | 400 ms | 95.7% | 45 | 0 | 2 | 0 | 0 |
| LONG | 60 | 850 ms | 96.7% | 58 | 0 | 2 | 0 | 0 |
| POOLED | 107 | 450 ms | 68.2% | 73 | 7 | 26 | 1 | 0 |

- [21:13] **late and wrong co-occur 0 times at every panel's best T.** At each best T
  the residual failures are purely accuracy failures (2 wrong, 0 late for both
  classes), so the two failure modes are disjoint there rather than compounding.

### Two findings that need stating in the report

**1. Figure A and Figure D disagree about the usable cutoff, and both are correct.**
Figure A gives max-usable-T of 350 (SHORT) and 800 (LONG). Figure D's best T is 400
and 850, one grid step LATER in each case. Not a contradiction - they answer
different questions:
  - Figure A is a WORST-CASE CLASS GUARANTEE: the class MINIMUM deadline against the
    class p95 latency. One number for the whole class, set by its earliest-crossing
    member.
  - Figure D is PER-FLIGHT ACTUAL: each flight judged against its OWN crossing time.
    A flight that crosses late has more slack than the class minimum allows for.
So Figure A is the number to quote for a guarantee, Figure D for expected
performance. If both appear without reconciliation they will read as contradictory -
the same trap the old figure3_latency_vs_t vs figures2/figure1_margin pair fell into.

**2. A single universal cutoff is much worse than a per-class one.**
POOLED peaks at 68.2%, while SHORT and LONG individually reach 95.7% and 96.7%. No
single T serves both classes: the T that suits SHORT is far too early for LONG
(driving `wrong`), and the T that suits LONG is far too late for SHORT (driving
`late`). The ~28 point gap between POOLED and the per-class figures is the direct,
quantified case for a class-adaptive cutoff, and it is the strongest argument this
sweep produces.

### Visual QA on Figure D

Rendered and inspected. First render put the best-T annotations at 0.97 of panel n,
which placed them ON the full-height bars in all three panels. Moved into the 14%
headroom at 1.045 of n. Re-rendered and re-checked: bands distinct, legend clear,
tick labels legible at 24 categories, caption fits. No remaining collisions.

---

## Outputs (all under data/regenerate_figures/)

| file | contents |
|---|---|
| `two_class_join.csv` | 2568 rows, the joined sweep + duration + class |
| `figureA_margin_vs_cutoff.png` | 150 dpi |
| `figureB_position_error_convergence.png` | 150 dpi |
| `figureB_excluded_counts.csv` | per class per T: n_ok, n_fit_failed, median, IQR |
| `figureC_duration_distribution.png` | 150 dpi |
| `figureD_outcome_sweep.png` | 150 dpi, 3 panels |
| `outcome_sweep_per_flight.csv` | 2568 rows: three booleans + verdict per flight per T |
| `outcome_sweep_by_class_T.csv` | class, T, four counts, success_rate |

Scripts: `scripts/regen_2class/step_{4,6,7}_*.py`. Steps 1-3 and 5 ran before the
script-file instruction arrived and exist only in this log.

## Scope adherence

- No existing CSV, JSON or script modified. All source files opened read-only.
- No Pi benchmark, capture, detection or fitting job re-run.
- No git operations.
- No figure regenerated other than A, B, C, D.
- position_error_mm labelled CONVERGENCE, never accuracy, in every caption.
- last_pair_detect_ms never used as a timestamp.
- No deadline hardcoded; both recomputed from data by the min rule in every script.
- fit_failed rows retained in Figure D as no_response.

**Status:** Complete
**Duration:** 20:49 start, 21:14 finish, ~25 min against the 30-40 min estimate.

---

# REVISION - 2026-08-20 21:20  (Figures A and D, plus script backfill)

## Scope resolution recorded before starting

The header says "Figures A and D only", but item 2 is headed "AXIS LABEL, ALL
FIGURES". Those conflict. Resolution:

- **Figure B updated too.** It is the only other figure carrying the old
  "prediction cutoff T (ms)" label, and leaving it would defeat item 2's stated
  purpose (consistency with the pipeline timing diagram). It is a label-only change
  replotted from existing computed data - no recomputation, which respects the "do
  NOT recompute" constraint.
- **Figure C NOT updated.** Its x-axis is "launch-to-crossing time (ms)", a
  different physical quantity, not an observation window. Renaming it would be wrong.

Flagging rather than silently choosing; say the word if Figure B should revert.

## Item 1 - Figure A budget line label

Old: -84 ms  -  target mode budget (1080p@240Hz: 4ms panel, 4.2ms quantisation, ~8ms render)
New: -84 ms  -  target mode budget (4K@60Hz, 16ms input lag, BenQ X500i)

The -84 value is UNCHANGED: 100 ms perceptual window minus 16 ms projector input
lag. The old decomposition was removed because projector input-lag specs are
measured end to end and already include the frame period, so listing panel,
quantisation and render terms alongside double-counted them. Added to the caption:
"Pi render and compositor latency is neglected."

The arithmetic is unchanged, so no margin was recomputed - max usable window is
still SHORT 350 / LONG 800, identical to the pre-revision run.

## Item 2 - axis rename

"prediction cutoff T (ms)" -> "observation window (ms)" in Figures A, B and D:
axis labels, the max-usable annotations (max-usable-T -> max usable window),
Figure D's per-panel annotations (best T -> best window), titles and captions.

CSV column names were NOT renamed. T_ms and T stay as they are, because they are
referenced by the values already recorded earlier in this log and renaming them
would silently break that correspondence. Flagged as a deliberate inconsistency
between figure text and column headers.

## Item 3 - Figure D panel order

Panels are now POOLED, SHORT, LONG top to bottom. Caption gained:
"POOLED is the performance of a system with no regime classifier. SHORT and LONG
are the achievable performance if the class were known at prediction time."

## Item 4 - accuracy-threshold sensitivity, 200 mm vs 170 mm

Rationale recorded: position_error_mm is CONVERGENCE against the full-arc Model-C
fit, not error against ground truth. Total error against truth is approximately the
quadrature of convergence error and the ~106 mm label-vs-fit accuracy floor
(06_label_vs_fit/summary.txt, median 105.7 mm). So a 200 mm requirement against
truth corresponds to roughly sqrt(200^2 - 106^2) = 169.6 mm of allowable
convergence error, rounded to 170 mm. The script prints that arithmetic on every run.

**COMPARISON TABLE**

| panel | n | best window @200mm | success @200mm | best window @170mm | success @170mm | delta |
|---|--:|--:|--:|--:|--:|--:|
| POOLED | 107 | 450 ms | 68.2% | 450 ms | 60.7% | **-7.5 pp** |
| SHORT | 47 | 400 ms | 95.7% | 400 ms | 91.5% | **-4.3 pp** |
| LONG | 60 | 850 ms | 96.7% | 850 ms | 95.0% | **-1.7 pp** |

Band detail at each best window:

| panel | threshold | success | late | wrong | no_response | late AND wrong |
|---|--:|--:|--:|--:|--:|--:|
| POOLED | 200 mm | 73 | 7 | 26 | 1 | 0 |
| POOLED | 170 mm | 65 | 7 | 34 | 1 | 0 |
| SHORT | 200 mm | 45 | 0 | 2 | 0 | 0 |
| SHORT | 170 mm | 43 | 0 | 4 | 0 | 0 |
| LONG | 200 mm | 58 | 0 | 2 | 0 | 0 |
| LONG | 170 mm | 57 | 0 | 3 | 0 | 0 |

**The best window is IDENTICAL under both thresholds in all three panels.** Only the
success rate moves, and it moves through the accuracy test alone - the late and
no_response counts are unchanged by construction, since the threshold only enters
the accurate test. This is a genuine robustness result: the choice of operating
window does not depend on where the accuracy line is drawn between 170 and 200 mm.
LONG is the least sensitive (-1.7 pp), POOLED the most (-7.5 pp).

Assertion re-checked on the sensitivity run: counts sum to panel n at all 72 cells.

## Item 5 - script backfill and reproduction check

New: common.py (shared palette, axis naming, percentile, class/deadline rules,
margin and max-usable-window helpers - per claude_rules.md Section 3, shared logic
goes in an unnumbered importable module rather than being duplicated).

Backfilled: step_1_classes.py, step_2_deadlines.py, step_3_join.py,
step_5_figure_b_convergence.py. Rewritten onto common.py: step_4_figure_a_margin.py,
step_7_figure_d_outcome.py. step_6_figure_c_duration.py left as written (no change
required by this revision).

**Reproduction check - every backfilled script re-run and compared to the values
already recorded above:**

| script | reproduced |
|---|---|
| step_1 | SHORT 47 / LONG 60 / 107; elevation cross-check PASS 0 mismatches; ranges [-6.04, 44.22] and [45.10, 60.38]; gap 0.88 deg - ALL MATCH |
| step_2 | SHORT min 491.5 P5 507.5 P25 567.5 med 620.1 max 1120.6; LONG min 1047.8 P5 1080.0 P25 1162.4 med 1240.7 max 1559.3; deadlines 490 / 1040 - ALL MATCH |
| step_3 | 2568 rows, 107 flights, 24 windows, 0 dupes, splits {LONG 1440, SHORT 1128} and {ok 2481, fit_failed 87} - ALL MATCH. two_class_join.csv md5 identical before and after (55fa50b7d4749fd3eda6132db218dcc8) - byte-for-byte reproduction, nothing silently changed. |
| step_4 | deadlines 490/1040, max usable window 350/800, margins -38.5 / -38.8 - ALL MATCH |
| step_5 | max usable window 350/800, excluded 15/72/87, medians 67.8 / 76.7 mm - ALL MATCH |
| step_7 | 200 mm run: POOLED 450/68.2%, SHORT 400/95.7%, LONG 850/96.7%, late&wrong 0 - ALL MATCH |

Every figure in the report set is now reproducible from a file rather than from
this log.

### New finding surfaced by the backfill

step_3 now reports the bare-id hazard quantitatively: **32 flight ids appear in more
than one session**, not just flight_13. The earlier entry named flight_13 because
that was the one the task called out; the real exposure is an order of magnitude
larger. Any analysis in this project that joins on a bare flight id is wrong for 32
ids, not 1. Worth auditing other scripts for that pattern.

## Visual QA on the revision

- **Figure A: y-axis label clipped after the rename.** "observation window" is
  longer than "T", so the full formula ylabel overflowed the canvas height and cut
  off at "(ms". Caught by rendering and looking, not assumed. Fixed by shortening
  the ylabel to "margin_p95 (ms)" and moving the formula into the caption. This is
  the same defect already catalogued for
  two_axis_sweep/figures/figure1_W_vs_time_consumed.png.
- **Figure D (both thresholds): clean on first render.** POOLED reads top, band
  order correct, best-window annotations sit in the headroom, 24 tick labels
  legible, four caption lines fit.
- **Figure B: clean.** Label change only.

## Outputs after the revision

| file | status |
|---|---|
| figureA_margin_vs_cutoff.png | updated (label, axis, caption, ylabel fix) |
| figureB_position_error_convergence.png | updated (axis label only) |
| figureB_excluded_counts.csv | unchanged values, rewritten |
| figureC_duration_distribution.png | untouched |
| figureD_outcome_sweep.png | updated (POOLED top, axis, caption) |
| figureD_outcome_sweep_170mm.png | NEW - sensitivity run |
| outcome_sweep_by_class_T.csv | updated (panel order) |
| outcome_sweep_by_class_T_170mm.csv | NEW |
| outcome_sweep_per_flight.csv | updated |
| outcome_sweep_per_flight_170mm.csv | NEW |
| two_class_join.csv | byte-identical |

Scripts: scripts/regen_2class/ - common.py, step_1_classes.py, step_2_deadlines.py,
step_3_join.py, step_4_figure_a_margin.py, step_5_figure_b_convergence.py,
step_6_figure_c_duration.py, step_7_figure_d_outcome.py

**Status:** Revision complete. No Pi sweep re-run, no margins or verdicts recomputed
except the item-4 sensitivity run. No git operations.

---

# REVISION 2 - 2026-08-21 13:45  (Figure A rebuilt in place, both game modes)

Code: `src/regen_2class/step9_figure_a_combined.py`. Figure A overwritten in place;
no second figure produced. Script set is now consolidated under `src/regen_2class/`
(`scripts/regen_2class/` no longer exists), so step 9 imports the existing
`common.py` rather than duplicating the class/deadline/margin logic. That resolves
the two-directory split flagged in the previous revision.

## Base - verified unchanged

Deadlines recomputed from `launch_to_crossing_ms` by the min rule on every run:
SHORT 490 ms, LONG 1040 ms. Nothing hardcoded. Classes recomputed from the `bin`
column: SHORT 47, LONG 60. Margin definition, axis naming and p95 latency treatment
all unchanged.

**One correction to the brief.** Line truncation at each class's maximum
launch_to_crossing_ms was listed under "BASE - UNCHANGED", but Figure A did NOT
previously truncate - that was introduced in Figure E (step 8). It is applied here
as instructed, so this IS a change to Figure A, not a carry-over. Effect: the SHORT
line now stops at the 1100 ms grid point (its class max is 1120.6 ms) instead of
running to 1250 ms. LONG is unaffected (class max 1559.3 ms, beyond the grid).

## Added

1. **Actuation band**, +72 to +220 ms, neutral grey alpha 0.15, solid nominal rule
   at +135, all at zorder 1 so they sit behind the data lines (zorder 3).
2. **-84 ms dashed line kept**, relabelled "target mode: display budget (100 ms
   perceptual window - 16 ms projector lag)".
3. **Zero reference**, thin light rule at y=0, unlabelled in the plot area.
4. **Two verticals per class** rather than four: the largest window at or above
   +135 (chaos nominal) and at or above -84 (target).
5. Caption extended with both readings and the panel-dynamics derivation.

## THRESHOLD TABLE (all four thresholds; only +135 and -84 are drawn)

| class | threshold | max feasible window | margin at that window | median position error |
|---|--:|--:|--:|--:|
| SHORT | +220 | **INFEASIBLE** | - | - |
| SHORT | +135 | 200 ms | 151.0 ms | 127.4 mm |
| SHORT | +72 | 250 ms | 83.7 ms | 121.3 mm |
| SHORT | -84 | 350 ms | -38.5 ms | 67.8 mm |
| LONG | +220 | 550 ms | 257.1 ms | 145.7 mm |
| LONG | +135 | 650 ms | 140.8 ms | 110.1 mm |
| LONG | +72 | 650 ms | 140.8 ms | 110.1 mm |
| LONG | -84 | 800 ms | -38.8 ms | 76.7 mm |

Also written to `data/regenerate_figures/figureA_thresholds.csv`.

### Three things the table says that the figure alone does not

**1. SHORT cannot afford a 30 degree panel move at all.** SHORT's margin peaks at
+201.0 ms at the shortest window in the grid (150 ms) and never reaches +220. So a
30 degree tilt is INFEASIBLE for the short class at every observation window
tested, not merely expensive. The vertical is correctly omitted from the figure and
INFEASIBLE is printed. If 30 degree moves are a requirement for short flights, the
answer is not a shorter window - there is none - it is a faster panel or a lower
pipeline latency.

**2. LONG's +135 and +72 thresholds land on the SAME window, 650 ms.** That is grid
coarseness, not a coincidence: margin drops from +140.8 at 650 ms to +65.1 at
700 ms, straddling both thresholds in one 50 ms step. The true +72 boundary sits
somewhere in 650-700 ms and the grid cannot resolve it. Stated in the caption as the
last-grid-point-at-or-above convention.

**3. Chaos rally costs roughly double the position error.** Moving from the target
window to the chaos nominal window nearly doubles median position error in both
classes:
- SHORT: 67.8 mm at 350 ms (target) -> 127.4 mm at 200 ms (chaos +135)
- LONG: 76.7 mm at 800 ms (target) -> 110.1 mm at 650 ms (chaos +135)

That is the real cost of reserving actuation time, and it is not visible on the
margin axis. Worth stating explicitly in the report: the two game modes are not
just different deadlines, they sit at materially different accuracy operating
points. Note both convergence figures still sit on the ~106 mm label-vs-fit floor,
so the chaos-rally numbers in particular are at or below the floor and should not be
read as achieved accuracy.

## Visual QA - three real collisions found and fixed

Rendered and inspected rather than assumed. First render had three defects:

1. **Caption clipped.** Seven caption lines at 0.0135 spacing from y=0.052 put the
   last three at negative figure coordinates, entirely off-canvas. Condensed to five
   lines, font 6.9, figure height raised 6.6 -> 7.4 in, `rect` bottom 0.115 -> 0.135.
2. **Band label struck by the LONG line.** Placed left-aligned inside the band at
   x=305 as the brief specified, it extended to roughly x=790, and LONG descends
   through the band from about x=610 - so the line crossed the text. Fixed by
   reducing to fontsize 7.4 and hanging the label from just under the nominal rule,
   which shortens it to end near x=720 and drops it into the part of the band LONG
   reaches later. The brief anticipated this ("if the band label collides with the
   LONG line, move it down or right") - moved down.
3. **Vertical labels struck by the LONG line.** Top-anchored rotated labels crossed
   LONG, which sits high on the left (+739 at 150 ms). Moved all four to the BOTTOM
   of the plot, where both classes are far above the floor at every marked window.

Second render fixed 1 and 3 but the solid +135 rule still struck through the band
label's first text line. Third render hangs the label 6 ms below the rule with
`va="top"`. Verified clear: no rule or data line crosses either annotation, and the
two annotations do not touch each other.

## Outputs

| file | status |
|---|---|
| `data/regenerate_figures/figureA_margin_vs_cutoff.png` | OVERWRITTEN in place, 150 dpi, single figure |
| `data/regenerate_figures/figureA_thresholds.csv` | NEW - 8 rows, all four thresholds per class |
| `src/regen_2class/step9_figure_a_combined.py` | NEW |

## Scope adherence

- One figure, overwritten in place. No second version created.
- No Pi benchmark, capture, detection or fitting job re-run; all inputs read-only.
- No deadline hardcoded; both recomputed from `launch_to_crossing_ms` on every run.
- No git operations.
- Nothing written outside `data/regenerate_figures/`, `src/regen_2class/` and this log.

**Status:** Complete
**Duration:** 13:45 start, 13:57 finish, ~12 min against the 15 min expectation.

---

# REVISION 3 - 2026-08-21 15:00  (Step 10: chaos-rally outcome sweep)

Code: `src/regen_2class/step10_chaos_outcome_sweep.py`, run from the file. Figures A,
D and E untouched.

## REPORTED BEFORE COMPUTING - per-axis velocity IS available

**Per-axis velocity error exists per flight per observation window.** Source:
`data/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/figures2/velocity_by_axis_raw.csv`
- 2481 rows, exactly the `status=="ok"` rows, carrying SIGNED `err_vx`, `err_vy`,
`err_vz` alongside the scalar `velocity_error_mm_s`. Produced by
`prediction_pipeline_sweep_pi_vaxis.py`, a copy of the sweep script whose only
change was persisting the components; its regression check matched the original on
all 2481 rows.

**The conservative scalar fallback was NOT used.** Cross-checked here as well:
`hypot(err_vx, err_vy, err_vz)` reproduces the stored scalar with **0 mismatches
over 2481 rows**.

Note the raw sweep CSV and `pipeline_sweep_full_20260804.json` carry only the
scalar - the per-axis components live solely in the vaxis outputs.

## Palette note

The dataviz validator could not be run: the skill bundle had been cleared from the
session temp directory and re-invoking the skill did not restore it. Rather than
eyeball CVD separation for six bands, the colours are a CONTIGUOUS RUN of the
documented 8-slot categorical order (slots 8,7,6,5,4,3 taken in reverse).
`palette.md` states that order clears every hard gate on the adjacent pairlist -
worst adjacent CVD dE 9.1, normal-vision dE 19.6, light mode - and adjacency is
symmetric, so a reversed contiguous run inherits the guarantee. success, late and
no_response keep their Figure D hexes so the two outcome figures read consistently.
Flagged so it can be re-validated when the bundle is available.

**Band order.** The brief said "six bands in the precedence order above", so they
stack bottom to top as no_response, late, wrong_class, wrong_position,
wrong_velocity, success - i.e. success on TOP. Figure D stacked success at the
bottom. Easy to flip if the inconsistency is unwanted.

## Assertions

Bands sum to class n at every window, for all three A values: PASS, 48 cells each.
Classes recomputed from `bin`: SHORT 47, LONG 60. Truncation at class max
launch_to_crossing_ms: SHORT 1120.6, LONG 1559.3 ms.

## RESULTS at each (class, A) best window, position threshold 100 mm

| class | A | best window | success | no_resp | late | wrong_class | wrong_pos | wrong_vel | median pos | p90 pos | hit/miss agree | n_fit_failed |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| SHORT | 72 | 300 ms | **53.2%** (25/47) | 0 | 4 | 2 | 16 | 0 | 86.3 mm | 297.1 mm | 95.7% | 0 |
| LONG | 72 | 700 ms | **56.7%** (34/60) | 0 | 0 | 1 | 25 | 0 | 90.7 mm | 179.5 mm | 98.3% | 0 |
| SHORT | 135 | 250 ms | **36.2%** (17/47) | 2 | 5 | 2 | 21 | 0 | 121.3 mm | 248.4 mm | 95.6% | 2 |
| LONG | 135 | 700 ms | **53.3%** (32/60) | 0 | 3 | 1 | 24 | 0 | 90.7 mm | 179.5 mm | 98.3% | 0 |
| SHORT | 220 | 200 ms | **27.7%** (13/47) | 2 | 9 | 1 | 22 | 0 | 127.4 mm | 350.2 mm | 97.8% | 2 |
| LONG | 220 | 600 ms | **38.3%** (23/60) | 0 | 0 | 1 | 36 | 0 | 115.0 mm | 316.6 mm | 98.3% | 0 |

Nothing is INFEASIBLE - every (class, A) achieves some success. Per-axis velocity
bias and scatter RMS at each operating point are in `chaos_outcome_by_class_A.csv`.

## HEADLINE 1 - the velocity criterion never binds. Not once.

`wrong_velocity` fires **0 times out of 2568 rows at every A**, both as a verdict
and as an independent flag with precedence ignored. The tolerances are one to two
orders of magnitude above the observed errors:

| axis | tolerance | worst single-row error | share of tolerance |
|---|--:|--:|--:|
| X_world depth | 6618 mm/s | 745 mm/s | 11.3% |
| Y_world width | 3676 mm/s | 1038 mm/s | 28.2% |
| Z_world up | 2206 mm/s | 1734 mm/s | **78.6%** |

So the four-criterion verdict is really a three-criterion verdict on this data. The
`court dimension / (e x T_return)` derivation with e=0.68 and T_return=1.0 s
produces tolerances the predictor is nowhere near violating. Z_up is the only axis
that comes close, at 79% of tolerance in the worst single row - if any tolerance is
ever tightened, that is the one that will start to bite. This does not mean velocity
prediction is good in an absolute sense; it means the requirement as derived is not
a constraint. Worth restating in the report rather than presenting a criterion that
silently never fires.

## HEADLINE 2 - wrong_position dominates, and its threshold sits below the reference floor

`wrong_position` is the single largest failure band at every operating point
(16-36 flights, versus 0-9 for late and 1-2 for wrong_class). The sensitivity run
shows how sharply it binds:

| class | A | best win @100mm | success @100 | best win @150mm | success @150 | delta |
|---|--:|--:|--:|--:|--:|--:|
| SHORT | 72 | 300 | 53.2% | 300 | 66.0% | **+12.8 pp** |
| LONG | 72 | 700 | 56.7% | 750 | 85.0% | **+28.3 pp** |
| SHORT | 135 | 250 | 36.2% | 200 | 53.2% | **+17.0 pp** |
| LONG | 135 | 700 | 53.3% | 650 | 78.3% | **+25.0 pp** |
| SHORT | 220 | 200 | 27.7% | 200 | 40.4% | **+12.8 pp** |
| LONG | 220 | 600 | 38.3% | 650 | 68.3% | **+30.0 pp** |

LONG gains 25-30 points from a 50 mm relaxation. That is not a robust operating
point - it means a large share of LONG flights sit just outside 100 mm.

**The deeper problem: 100 mm is below the reference's own accuracy floor.**
`position_error_mm` is CONVERGENCE against the full-arc Model-C fit, and that fit
agrees with the manual labels only to a median of ~105.7 mm
(`06_label_vs_fit/summary.txt`). Requiring convergence under 100 mm therefore
demands agreement tighter than the reference is itself known to. A meaningful share
of the `wrong_position` band is measuring reference noise, not predictor failure.
The 150 mm variant is the more defensible requirement on this evidence, and the
success rates should be quoted from it, or from a ground-truth comparison once more
labels exist.

## Failure-mode co-occurrence at each best window

Sparse throughout - failure modes are close to disjoint:

| class | A | co-occurring pairs |
|---|--:|---|
| SHORT | 72 | late+wrong_position 1, wrong_class+wrong_position 2 |
| LONG | 72 | wrong_class+wrong_position 1 |
| SHORT | 135 | late+wrong_position 3, wrong_class+wrong_position 2 |
| LONG | 135 | late+wrong_position 1, wrong_class+wrong_position 1 |
| SHORT | 220 | late+wrong_position 7, wrong_class+wrong_position 1 |
| LONG | 220 | wrong_class+wrong_position 1 |

Every pair involving `wrong_velocity` is zero by construction. The only pair that
grows materially is SHORT's late+wrong_position at A=220 (7 flights): at the
tightest actuation demand, short flights that are late are also usually inaccurate,
because both come from the same cause - the window has been cut too short. Full
matrix in `chaos_outcome_cooccurrence.csv`.

## Figure G - per-axis velocity, two-class

Regenerated under SHORT/LONG as a NEW file in `data/regenerate_figures/`; the
original three-class `figures2/figure4_velocity_error_by_axis.png` is untouched, per
the data-protection rule. Per-axis label-precision floor bands retained, with the
caption stating X and Z are validated to label precision (decision 77) while
Y_world's floor is UNRESOLVED - inside that band means "not distinguishable from the
reference's own unknown noise", not "accurate to that figure". X-axis relabelled
"observation window (ms)". Dotted verticals at the A=135 ms chaos operating windows,
SHORT 250 ms and LONG 700 ms.

## Visual QA

Both figures rendered and inspected. Figure F: six panels correct, bands legible,
best-window annotations in the headroom, SHORT panels correctly show no bars past
1100 ms under the shared x-axis (verified both classes start at index 0 so the
shared ticks align). Figure G: caption sat tight against the canvas edge on first
render; raised the caption block and `rect` bottom, re-rendered and re-checked.

## Outputs (all new, nothing overwritten)

| file | contents |
|---|---|
| `figureF_chaos_outcome_sweep.png` | 6 panels, 150 dpi |
| `figureG_velocity_by_axis_twoclass.png` | 3 panels, 150 dpi |
| `chaos_outcome_by_class_A.csv` | per (class, A) best window, six bands, position, hit/miss, per-axis bias/RMS/n_out |
| `chaos_outcome_cooccurrence.csv` | all 10 failure-mode pairs per (class, A) |
| `chaos_outcome_sensitivity_100_vs_150.csv` | best window and success at both thresholds |
| `src/regen_2class/step10_chaos_outcome_sweep.py` | the script |

## Scope adherence

- No Pi benchmark, capture, detection or fitting job re-run; all inputs read-only.
- Figures A, D and E untouched. No deadline hardcoded.
- Every step is in the script file; no heredocs used anywhere. The figures are
  regenerable from the file alone.
- No git operations.

**Status:** Complete
**Duration:** 14:39 start, 15:02 finish, ~23 min against the 25 min expectation.

---

# REVISION 4 - 2026-08-21 15:08  (Figure F only: band order, colours, T_return check)

Edited and rerun `src/regen_2class/step10_chaos_outcome_sweep.py`. Figures A, D and E
untouched, timestamps verified unchanged.

**CORRECTION to this entry as first written.** It originally claimed Figure G was
also untouched. That was wrong: `main()` calls `render_velocity_figure` at the end,
so rerunning the script REWROTE figureG_velocity_by_axis_twoclass.png and its
timestamp changed, against the instruction not to touch G. Verified afterwards that
the CONTENT is unchanged - md5 taken before and after a further rerun is identical
(0d64eaf15fd91b8c36d33ec2d0546c45), and no code path feeding G was edited in this
revision (BAND_ORDER, BAND_COLOR and the Figure F caption are not read by
render_velocity_figure; the T_return block is print-only). So G is byte-identical to
the version approved in revision 3, but the file was rewritten rather than left
alone. To regenerate F alone in future, main() needs a guard or a CLI flag.

## 1. Band order flipped to match Figure D

Stack is now bottom to top: success, wrong_velocity, wrong_position, wrong_class,
late, no_response. Success on the floor, as in Figure D.

`FAILURES` (the precedence list consumed by `verdict_of`) and `BAND_ORDER` (the
stacking/legend list) are now two separate constants with a comment saying so. The
verdict logic is byte-for-byte unchanged - confirmed by the success rates being
identical to the previous run at all six operating points (53.2 / 36.2 / 27.7 SHORT,
56.7 / 53.3 / 38.3 LONG). Legend kept top-centre, in stack order read bottom to top.

## 2. Colours fixed to Figure D's palette

| band | hex | source |
|---|---|---|
| success | `#1baf7a` | Figure D |
| wrong_velocity | `#fac775` | lighter amber |
| wrong_position | `#eda100` | Figure D's "wrong" - dominant band here |
| wrong_class | `#c98500` | darker amber |
| late | `#4a3aa7` | Figure D |
| no_response | `#e34948` | Figure D |

The palette validator was NOT run against these, per instruction: the hexes are
fixed to match an existing report figure, so validation could only produce a
recommendation that must be ignored. Recorded here so the omission is deliberate and
visible rather than an oversight. The three amber shades are close by design - they
are meant to read as one failure family - and `wrong_velocity` is empty on this
data, so in practice only two ambers ever appear side by side.

Caption line describing the stack updated; caption is now 6 lines, so its block and
the `rect` bottom were raised to keep the last line on canvas (checked by rendering).

## 3. PRINT ONLY - velocity tolerance at T_return = 2.0 s

Tolerance scales as 1 / T_return, so doubling the return time halves every
tolerance. Verdict and figure keep the 1.0 s values; this is diagnostic only.
Evaluated over the 2481 status==ok rows.

| axis | tol @1.0s | breaches | tol @2.0s | breaches | worst \|err\| | % of 2.0s tol |
|---|--:|--:|--:|--:|--:|--:|
| X_world depth | 6618 | 0 | 3309 | 0 | 745 | 22.5% |
| Y_world width | 3676 | 0 | 1838 | 0 | 1038 | 56.5% |
| Z_world up | 2206 | 0 | 1103 | **7** | 1734 | **157.2%** |
| ANY axis | - | **0** (0.00%) | - | **7** (0.28%) | | |

**The "velocity never binds" result is not robust to T_return, but it very nearly
is.** At 2.0 s the criterion starts firing, and only on Z_up: 7 rows of 2481, 0.28%.
X and Z... X and Y still clear their halved tolerances with 22.5% and 56.5% margin.
So the exposure is entirely on the vertical axis, which was already the closest to
binding at 1.0 s (78.6% of tolerance).

Practical reading: even at double the assumed return time the criterion changes 7
rows out of 2481, which would not move any operating point - the best windows are
selected on success rate and `wrong_velocity` sits below `wrong_position` in
precedence, where 16-36 flights already fail. So the conclusion "velocity is not the
binding constraint" survives the T_return assumption. What does NOT survive is the
stronger claim that the criterion never fires at all: that is specific to
T_return = 1.0 s.

If T_return is ever revised upward, Z_up is the axis to re-check and the only one
worth instrumenting.

## Verification

- Success rates identical to the pre-revision run at all six operating points,
  confirming the change was presentational only.
- Band sums still equal class n at all 48 cells per A value.
- Figures A, D, E file timestamps unchanged. Figure G REWRITTEN by the rerun but
  byte-identical (md5 0d64eaf15fd91b8c36d33ec2d0546c45); see the correction above.

**Status:** Complete
**Duration:** ~6 min against the 10 min expectation.

---

# REVISION 5 - 2026-08-21 15:16  (Figure F: colours + placement-based velocity tolerance)

Edited and rerun `src/regen_2class/step10_chaos_outcome_sweep.py`. Figures A, D, E
and G untouched - G verified by md5, unchanged at
`0d64eaf15fd91b8c36d33ec2d0546c45`, timestamp still 15:00.

**Figure G guard added.** `main()` now renders G only when `--figure-g` is passed.
That was the cause of the revision-4 slip where a Figure-F-only rerun rewrote G as a
side effect. Default runs print "Figure G NOT regenerated" and leave the file alone.
The figure is still regenerable from the file alone, as required, just deliberately.

## 1. Colours

| band | hex | note |
|---|---|---|
| success | `#1baf7a` | Figure D |
| wrong_velocity | `#e87ba4` | magenta |
| wrong_position | `#eda100` | amber |
| wrong_class | `#2a78d6` | blue |
| late | `#4a3aa7` | Figure D |
| no_response | `#e34948` | Figure D |

Band order and legend order unchanged, success still on the floor. Validator not run,
per instruction. Stale comment about the old amber family removed rather than left
contradicting the new assignment.

### The recolour exposed a band that was previously invisible

The old `wrong_class` (#c98500 dark amber) sat directly against `wrong_position`
(#eda100) and was unreadable at bar width. With `wrong_class` now blue, it is
obvious that it is a SUBSTANTIAL band in LONG at short-to-mid windows - roughly
10 flights at 300-550 ms - not the 1-2 flights visible at the best windows. Nothing
in the data changed; the band was always there and the amber family concealed it.
That is exactly the misread reported, and it means any earlier reading of Figure F
that treated wrong_class as negligible was reading the palette, not the data.

## 2. Velocity tolerance: containment -> placement, isotropic

    delta_v_max = placement_tolerance / (e x T_return) = 1.0 m / (0.68 x 1.0 s)
                = 1470.6 mm/s on every axis

(The figure and console round this to 1471; the brief quoted 1470. Same number,
1000/0.68 = 1470.588.)

Replaces the per-axis court-dimension tolerances (X 6618, Y 3676, Z 2206). Caption
carries the rationale: the court-width tolerance tested only whether the ball stays
in play, whereas the game requires the return to land near an intended spot, and a
player covers roughly 1 m during a 1 s return flight.

Worst single-row error against the new tolerance:
X 745 mm/s (50.7%), Y 1038 mm/s (70.6%), **Z 1734 mm/s (117.9%)**. Z now breaches.

`wrong_velocity` as an independent flag: **2 of 2568 rows**, up from 0 under the old
tolerances. As a VERDICT: still 0, because both rows also fail an earlier criterion.

## 3. PLACEMENT SENSITIVITY GRID (print only)

Breach counts over the 2481 status==ok rows:

| placement | T_return | tol mm/s | X | Y | Z | ANY | % rows |
|--:|--:|--:|--:|--:|--:|--:|--:|
| 0.5 m | 1.0 s | 735 | 1 | 8 | 21 | 28 | 1.13% |
| 0.5 m | 2.0 s | 368 | 18 | 83 | 110 | **168** | **6.77%** |
| 1.0 m | 1.0 s | 1471 | 0 | 0 | 2 | 2 | 0.08% | <- primary |
| 1.0 m | 2.0 s | 735 | 1 | 8 | 21 | 28 | 1.13% |
| 1.5 m | 1.0 s | 2206 | 0 | 0 | 0 | 0 | 0.00% |
| 1.5 m | 2.0 s | 1103 | 0 | 0 | 7 | 7 | 0.28% |

Z_up dominates every breaching cell - it is the binding axis at every tolerance
tested. Note 1.5 m / 1.0 s reproduces 2206 mm/s exactly, which is the old Z
court-height tolerance; the old per-axis Z figure WAS a 1.5 m placement tolerance in
disguise.

### Best window and success rate across the same grid: NOTHING MOVES

| placement | T_ret | tol | SHORT A=72 | LONG A=72 | SHORT A=135 | LONG A=135 | SHORT A=220 | LONG A=220 |
|--:|--:|--:|---|---|---|---|---|---|
| 0.5 m | 1.0 s | 735 | 300ms 53.2% | 700ms 56.7% | 250ms 36.2% | 700ms 53.3% | 200ms 27.7% | 600ms 38.3% |
| 0.5 m | 2.0 s | 368 | 300ms 53.2% | 700ms 56.7% | 250ms 36.2% | 700ms 53.3% | 200ms 27.7% | 600ms 38.3% |
| 1.0 m | 1.0 s | 1471 | 300ms 53.2% | 700ms 56.7% | 250ms 36.2% | 700ms 53.3% | 200ms 27.7% | 600ms 38.3% |
| 1.0 m | 2.0 s | 735 | 300ms 53.2% | 700ms 56.7% | 250ms 36.2% | 700ms 53.3% | 200ms 27.7% | 600ms 38.3% |
| 1.5 m | 1.0 s | 2206 | 300ms 53.2% | 700ms 56.7% | 250ms 36.2% | 700ms 53.3% | 200ms 27.7% | 600ms 38.3% |
| 1.5 m | 2.0 s | 1103 | 300ms 53.2% | 700ms 56.7% | 250ms 36.2% | 700ms 53.3% | 200ms 27.7% | 600ms 38.3% |

**Every cell is identical across the whole grid.** A 4x change in tolerance
(2206 -> 368 mm/s) moves breach counts from 0 to 168 rows and changes neither the
best window nor the success rate anywhere.

The mechanism is precedence, not insensitivity. `wrong_velocity` sits BELOW
`wrong_position` in the first-match-wins order, and `wrong_position` already claims
16-36 flights at every operating point. Rows that breach velocity are almost always
rows that already failed position, so tightening velocity re-labels failures without
creating new ones.

Two consequences worth carrying into the report:
- The velocity criterion cannot affect the choice of operating window under this
  verdict structure, whatever the placement tolerance. Reporting it as a live
  constraint would overstate it.
- If velocity is genuinely a design requirement rather than a tie-breaker, it needs
  to be assessed OUTSIDE the precedence chain - as its own pass/fail rate on the
  fitted rows - not as the fifth band of a first-match-wins verdict. The
  independent-flag count (2 rows at 1471 mm/s, 168 at 368 mm/s) is the honest
  number; the band count of 0 is an artefact of ordering.

## Verification

- Bands sum to class n at all 48 cells per A.
- Success rates unchanged from revision 4 at all six operating points, confirming
  the velocity change did not alter any verdict outcome.
- Caption grew to 7 lines; block and `rect` bottom raised, checked by rendering.
- Figures A, D, E timestamps unchanged; G md5 unchanged.

**Status:** Complete
**Duration:** ~9 min against the 10 min expectation.

---

# STEP 11 - 2026-08-21 15:30  (R4 pass rate vs panel size)

Code: `src/regen_2class/step11_panel_size_sensitivity.py`. Console + CSV only, no
figure. Verdict machinery imported from step10 rather than re-implemented, so the
six bands are identical by construction. Nothing re-run; APERTURE_SIZE_MM untouched.

Threshold = aperture / 20 (delta-wide perimeter dead band retaining 81% usable
area). Operating windows SHORT 300 ms, LONG 700 ms, A = 72 ms. Both windows carry
0 fit_failed, so n_ok = n_total and the denominators are unambiguous.

**Hit/miss classification deliberately NOT recomputed.** `wrong_class` keeps the
frozen 2000 mm result from `hit_miss_match`, per instruction - where balls happened
to cross in this dataset is a property of these throws, not of a venue.

## R4 alone: fraction with position_error_mm below aperture/20

| aperture | R4 thr | SHORT (300 ms) | LONG (700 ms) | POOLED |
|--:|--:|---|---|---|
| 2000 | 100.0 | 28/47 59.6% | 34/60 56.7% | 62/107 **57.9%** |
| 2250 | 112.5 | 30/47 63.8% | 39/60 65.0% | 69/107 **64.5%** |
| 2500 | 125.0 | 31/47 66.0% | 43/60 71.7% | 74/107 **69.2%** |
| 2750 | 137.5 | 33/47 70.2% | 46/60 76.7% | 79/107 **73.8%** |
| 3000 | 150.0 | 35/47 74.5% | 47/60 78.3% | 82/107 **76.6%** |

## Full six-band verdict, POOLED (only the position threshold changes)

| aperture | success | w_vel | w_pos | w_cls | late | no_resp | success rate |
|--:|--:|--:|--:|--:|--:|--:|--:|
| 2000 | 59 | 0 | 41 | 3 | 4 | 0 | 55.1% |
| 2250 | 66 | 0 | 34 | 3 | 4 | 0 | 61.7% |
| 2500 | 71 | 0 | 29 | 3 | 4 | 0 | 66.4% |
| 2750 | 76 | 0 | 24 | 3 | 4 | 0 | 71.0% |
| 3000 | 78 | 0 | 22 | 3 | 4 | 0 | 72.9% |

Per-class rows in `panel_size_sensitivity.csv`.

## Observations

**Exactly one band moves.** `wrong_velocity` stays 0, `wrong_class` stays 3, `late`
stays 4, `no_response` stays 0 at every aperture. Success and `wrong_position` trade
one-for-one. That is structural, not coincidence: `late` and `no_response` do not
depend on position, velocity is unaffected, and `wrong_class` is frozen by
instruction. So overall success tracks R4 almost exactly, +17.8 pp against R4's
+18.7 pp across the full range.

**R4-alone and the band count differ, and both are right.** At 2000 mm, 19 SHORT
flights have position error >= 100 mm but `wrong_position` shows 16. The other 3
failed earlier in precedence (late or wrong_class) and are counted there. R4-alone
counts every flight breaching R4; the band counts only those where R4 is the FIRST
failure. Quote whichever matches the question, but not interchangeably.

**Diminishing returns, sharply, at the last step.** Pooled success gains per 250 mm:
+6.6, +4.7, +4.6, then **+1.9** pp. LONG is the cause - it saturates at 46/60 -> 47/60
over the final step while SHORT keeps gaining. On this evidence 2750 mm captures
most of the benefit and 3000 mm buys little.

**A hard ceiling around 73%.** Even at 3000 mm, 22 flights still fail position, plus
3 wrong_class and 4 late. Enlarging the panel cannot fix those: 4 are timing
failures and 3 are classification disagreements, neither of which the aperture
touches.

**The larger apertures make R4 measurable rather than reference-limited.** At 2000 mm
the threshold is 100 mm, BELOW the ~105.7 mm median label-vs-fit floor
(`06_label_vs_fit/summary.txt`), so a share of that 41-flight `wrong_position` band
is reference noise rather than predictor failure. At 2750 and 3000 mm the thresholds
(137.5 and 150 mm) sit ABOVE the floor, so the pass/fail decision starts to reflect
the predictor. This is a second, independent argument for the larger panel that has
nothing to do with the raw pass rate, and it is worth stating separately in the
report.

## Output

`data/regenerate_figures/panel_size_sensitivity.csv` - 15 rows (5 apertures x
SHORT/LONG/POOLED), columns: aperture_mm, r4_threshold_mm, scope, window_ms,
n_total, n_ok, r4_pass, r4_pass_rate, success_rate, and the six band counts.

**Status:** Complete. ~7 min.

---

# STEP 12 - 2026-08-21 15:45  (Figure H: three-criterion chaos sweep)

Code: `src/regen_2class/step12_chaos_sweep_3criterion.py`. NEW files only -
`figure_h_chaos_3criterion.png` and `.csv`. Figures A, D, E, F, G untouched,
timestamps verified. APERTURE_SIZE_MM not read or changed anywhere in this module.

## RATIONALE for removing wrong_position as a pass criterion

Figure F's four-criterion verdict included `wrong_position` at 100 mm, derived as a
dead-band containment margin around the aperture perimeter. It is removed here
because it **double-counts the hit/miss test**.

The impulse axis translates the panel along its surface normal at uniform velocity.
Return DIRECTION is therefore set by the commanded panel angle, and return SPEED by
the translation velocity. Neither depends on where on the surface the ball makes
contact. Crossing position governs only WHETHER contact occurs - and that is exactly
what `hit_miss_match` tests. Figure F counted the same physical requirement twice,
once as classification and once as a millimetre threshold.

Position accuracy is still reported, as a CAPABILITY (median / p90 / max
position_error_mm at the operating point), not as pass/fail.

Verdict machinery reuses step10's `flags()`, which is precedence-independent by
construction, so Figures F and H differ only in the iteration order over the same
flag dict - not in how any flag is computed.

## Assertions

Bands sum to class n at every window for all three A values: PASS, 48 cells each.
Classes recomputed from `bin`: SHORT 47, LONG 60.

## RESULTS at each (class, A) best window

| class | A | best window | success | w_vel | w_class | late | no_resp | pos median | pos p90 | pos max | hit/miss | n_fit_failed |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| SHORT | 72 | 200 ms | **93.6%** (44/47) | 0 | 1 | 0 | 2 | 127.4 | 350.2 | 851.4 mm | 97.8% | 2 |
| LONG | 72 | 600 ms | **98.3%** (59/60) | 0 | 1 | 0 | 0 | 115.0 | 316.6 | 649.8 mm | 98.3% | 0 |
| SHORT | 135 | 200 ms | **93.6%** (44/47) | 0 | 1 | 0 | 2 | 127.4 | 350.2 | 851.4 mm | 97.8% | 2 |
| LONG | 135 | 600 ms | **98.3%** (59/60) | 0 | 1 | 0 | 0 | 115.0 | 316.6 | 649.8 mm | 98.3% | 0 |
| SHORT | 220 | 150 ms | **74.5%** (35/47) | 0 | 1 | 0 | 2 | - | - | - | - | - |
| LONG | 220 | 600 ms | **98.3%** (59/60) | 0 | 1 | 0 | 0 | 115.0 | 316.6 | 649.8 mm | 98.3% | 0 |

Per-axis velocity bias/RMS at each operating point is in the CSV. Nothing is
INFEASIBLE.

## INDEPENDENT flag counts at the best windows

The bands answer "what failed FIRST". These answer "how often does each requirement
fail at all" - the number the requirements table needs.

| class | A | window | no_response | late | wrong_class | wrong_velocity | wrong_position* |
|---|--:|--:|--:|--:|--:|--:|--:|
| SHORT | 72 | 200 ms | 2/47 | 0/45 | 1/45 | 0/45 | **30/45** |
| LONG | 72 | 600 ms | 0/60 | 0/60 | 1/60 | 0/60 | **37/60** |
| SHORT | 135 | 200 ms | 2/47 | 0/45 | 1/45 | 0/45 | **30/45** |
| LONG | 135 | 600 ms | 0/60 | 0/60 | 1/60 | 0/60 | **37/60** |
| LONG | 220 | 600 ms | 0/60 | 0/60 | 1/60 | 0/60 | **37/60** |

*not a criterion in Figure H; shown for reference. Denominator is evaluable rows -
`no_response` is over class n, the rest over fitted rows only, since a failed fit has
no latency, class or velocity to test.

At every operating point the three live criteria are nearly perfectly satisfied:
**late 0, wrong_velocity 0, wrong_class 1**. All residual failure is `no_response`
(2 SHORT flights whose RANSAC fit failed at 200 ms).

## COMPARISON: Figure F four-criterion vs Figure H three-criterion

| class | A | F window | F success | H window | H success | delta |
|---|--:|--:|--:|--:|--:|--:|
| SHORT | 72 | 300 ms | 53.2% | 200 ms | 93.6% | **+40.4 pp** |
| LONG | 72 | 700 ms | 56.7% | 600 ms | 98.3% | **+41.7 pp** |
| SHORT | 135 | 250 ms | 36.2% | 200 ms | 93.6% | **+57.4 pp** |
| LONG | 135 | 700 ms | 53.3% | 600 ms | 98.3% | **+45.0 pp** |
| SHORT | 220 | 200 ms | 27.7% | 150 ms | 74.5% | **+46.8 pp** |
| LONG | 220 | 600 ms | 38.3% | 600 ms | 98.3% | **+60.0 pp** |

Both numbers belong in the report. The gap is 40 to 60 points - the position
criterion was carrying essentially the whole failure rate in Figure F.

**The best window also moves EARLIER in five of six cases** (SHORT 300->200,
250->200, 200->150; LONG 700->600 twice). That is a second-order consequence worth
naming: once position stops being scored, there is no longer any reason to observe
for longer, because the three remaining criteria are satisfied almost immediately
and a longer window only increases the risk of being late. Removing the criterion
does not just raise the score, it changes the recommended operating point.

## SENSITIVITY: containment reinstated at the END of the precedence chain

Order becomes no_response, late, wrong_class, wrong_velocity, wrong_position. This
isolates the true containment cost - flights that fail position AND NOTHING ELSE.

| class | A | window | H success | fail position ONLY | success if position kept |
|---|--:|--:|--:|--:|--:|
| SHORT | 72 | 200 ms | 93.6% | **29** | 31.9% |
| LONG | 72 | 600 ms | 98.3% | **36** | 38.3% |
| SHORT | 135 | 200 ms | 93.6% | **29** | 31.9% |
| LONG | 135 | 600 ms | 98.3% | **36** | 38.3% |
| SHORT | 220 | 150 ms | 74.5% | **29** | 12.8% |
| LONG | 220 | 600 ms | 98.3% | **36** | 38.3% |

**The containment cost is almost the entire failure rate, and it is not an ordering
artefact.** 29 of 47 SHORT and 36 of 60 LONG flights fail position after passing
every other requirement. In Figure F the position band was partially masked by
earlier failures; moved to the tail it is even larger, because the flights that used
to be absorbed by `late` at the longer F windows now pass timing at the shorter H
windows and fail on position instead.

So the whole chaos-rally result hinges on whether the 100 mm containment threshold
is a real requirement. If it is, success is 12-38%. If the double-counting argument
holds, success is 74-98%. There is no middle reading, and the report should present
the physical argument for removal rather than the number alone.

Two caveats to carry with that:
- `position_error_mm` is CONVERGENCE against the full-arc Model-C fit, not accuracy
  against truth, and the 100 mm threshold sits BELOW the ~105.7 mm median
  label-vs-fit floor. Part of the 29/36 is reference noise regardless.
- The position CAPABILITY numbers are large at the H operating points (median
  115-127 mm, p90 316-350 mm, max 650-851 mm) precisely because the windows moved
  earlier. If position matters at all, the H operating points are the wrong ones.

## Visual QA

Rendered and inspected. Six panels, five bands, success on the floor, colours as
specified, legend top-centre in stack order, seven caption lines all on canvas,
SHORT truncated at 1100 ms under the shared x-axis. `wrong_velocity` is present in
the legend but never visible - it is zero everywhere, consistent with step 10.
No collisions.

## Outputs

| file | contents |
|---|---|
| `data/regenerate_figures/figure_h_chaos_3criterion.png` | 6 panels, 150 dpi, NEW |
| `data/regenerate_figures/figure_h_chaos_3criterion.csv` | per (class, A): bands, F-vs-H comparison, position capability, hit/miss, per-axis velocity, independent flags, containment sensitivity |
| `src/regen_2class/step12_chaos_sweep_3criterion.py` | the script |

**Status:** Complete. ~14 min against the 20 min expectation.

---

# STEP 12, REVISION 1 - 2026-08-21 16:05  (latest-plateau window selection)

Edited and rerun `src/regen_2class/step12_chaos_sweep_3criterion.py`. Figure H and
its CSV overwritten in place. Figures A, D, E, F, G untouched, timestamps verified.

## Change: operating window is now the LATEST at the maximum, not the earliest

`evaluate_h` previously used `max(range(...), key=...)`, which returns the FIRST
index at the maximum. Now, explicitly:

1. `mx = max(rate[c])` - the maximum success rate over all windows. Reliability is
   the pass criterion and decides on its own.
2. `plateau = [j for j, v in enumerate(rate[c]) if v == mx]`, then `i = plateau[-1]`.

Exact float equality is safe here: rates are `100.0 * k / n` with the same `n`, so
equal success counts give bit-identical floats.

**Position error does not enter step 1.** It is reported as a capability and only
ever breaks ties, exactly as briefed.

**Rationale.** Once all three pass criteria are satisfied, extending the window
cannot raise the success count, but crossing position error keeps falling. Taking
the earliest tied window left that accuracy unclaimed, and it placed the operating
point where position capability was WORST - which biased the capability figures,
because the window had been chosen by an argument that assumed position did not
matter. This was the concern raised against the first Figure H run; it is now fixed
rather than merely noted.

Added `position_stats()` (median / p90 / max / n_ok per class per window) and a
`max_ltc` guard that warns if a selected window falls outside the plotted range. No
warning fired - every selected window is inside truncation.

## PLATEAUS - every window at the maximum success rate

All six plateaus are CONTIGUOUS.

| class | A | plateau | selected | success | n_ok | pos med | pos p90 | pos max |
|---|--:|---|--:|--:|--:|--:|--:|--:|
| SHORT | 72 | {200} | **200** | 93.6% | 45 | 127.4 | 350.2 | 851.4 |
| LONG | 72 | {600, 650, 700} | **700** | 98.3% | 60 | **90.7** | **179.5** | 576.7 |
| SHORT | 135 | {200} | **200** | 93.6% | 45 | 127.4 | 350.2 | 851.4 |
| LONG | 135 | {600, 650} | **650** | 98.3% | 60 | 110.1 | **179.9** | 401.6 |
| SHORT | 220 | {150, 200} | **200** | 74.5% | 45 | 127.4 | 350.2 | 851.4 |
| LONG | 220 | {600} | **600** | 98.3% | 60 | 115.0 | 316.6 | 649.8 |

Per-window detail for the multi-window plateaus:

**LONG A=72** - three windows, all 98.3% (59/60):

| window | n_ok | pos med | pos p90 | pos max |
|--:|--:|--:|--:|--:|
| 600 | 60 | 115.0 | 316.6 | 649.8 |
| 650 | 60 | 110.1 | 179.9 | 401.6 |
| **700** | 60 | **90.7** | **179.5** | 576.7 |

median -24.3, p90 -137.2, max -73.2 mm from 600 to 700.

**LONG A=135** - two windows, both 98.3%: 600 -> 650 gives median -4.9, p90 -136.7,
max -248.2 mm.

**SHORT A=220** - two windows, both 74.5% (35/47): 150 -> 200 gives median -52.9,
p90 -134.2, but **max +79.4 mm (772.0 -> 851.4)**. n_ok rises 37 -> 45.

## Two things the per-window detail exposes

**1. pos_max does not follow median and p90.** At SHORT A=220 the selected window
has a WORSE maximum (851.4 vs 772.0 mm) despite better median and p90. Same pattern
at LONG A=72, where max rises from 401.6 at 650 ms to 576.7 at the selected 700 ms
even though median and p90 both improve. Selecting late improves the typical case
and the upper-decile case; it does not improve the extreme tail. If the requirement
is worst-case rather than typical, the latest window is not automatically right, and
for LONG A=72 the middle window (650 ms) is actually the best worst-case choice at
identical success.

**2. Identical success rate, completely different failure composition.** SHORT
A=220 at the two plateau windows:

| window | success | wrong_velocity | wrong_class | late | no_response |
|--:|--:|--:|--:|--:|--:|
| 150 | 35 | 0 | 1 | 1 | **10** |
| 200 | 35 | 0 | 1 | **9** | 2 |

Both 74.5%, but 150 ms fails by not answering at all (10 RANSAC fit failures in the
small-N zone, n_ok 37) while 200 ms fails by being late (9 flights). The selection
rule is agnostic between these; a system designer should not be. Eight fewer
fit-failures is a genuine robustness gain - a no_response is unrecoverable, whereas
a late answer may still be partially usable - which supports the choice, but it is a
judgement the success rate alone does not capture and it should be stated in the
report rather than hidden behind an identical percentage.

## Effect on the F-vs-H comparison

Deltas are unchanged in magnitude, but two windows now coincide with Figure F's,
which makes those rows a cleaner like-for-like comparison:

| class | A | F window | F success | H window | H success | delta |
|---|--:|--:|--:|--:|--:|--:|
| SHORT | 72 | 300 | 53.2% | 200 | 93.6% | +40.4 |
| LONG | 72 | 700 | 56.7% | **700** | 98.3% | +41.7 |
| SHORT | 135 | 250 | 36.2% | 200 | 93.6% | +57.4 |
| LONG | 135 | 700 | 53.3% | 650 | 98.3% | +45.0 |
| SHORT | 220 | 200 | 27.7% | **200** | 74.5% | +46.8 |
| LONG | 220 | 600 | 38.3% | **600** | 98.3% | +60.0 |

LONG A=72, SHORT A=220 and LONG A=220 now compare at the SAME window, so those three
deltas isolate the effect of removing the position criterion with no confound from a
window change. That was not true before.

## Position capability now sits at the label floor

LONG A=72 at 700 ms reaches a **90.7 mm median**, below the ~105.7 mm median
label-vs-fit floor. At that operating point the position capability is no longer
distinguishable from the reference's own noise, so it cannot be quoted as an
achieved accuracy - only as "at or below the floor".

## Outputs

| file | change |
|---|---|
| `figure_h_chaos_3criterion.png` | overwritten; vertical lines and annotations moved to the latest-plateau windows; one caption line added |
| `figure_h_chaos_3criterion.csv` | overwritten, now LONG format - one row per (class, A, plateau window) with `is_selected`, per-window success/n_ok/pos median/p90/max, and the (class, A) summary repeated so each row stands alone. 10 rows. |

Caption line added verbatim as briefed: "Where several observation windows achieve
the maximum success rate, the latest is selected: reliability is at ceiling across
the plateau, so a longer window reduces crossing position error at no cost to
success."

## Visual QA

Rendered and inspected. Vertical lines sit at 200 / 700 / 200 / 650 / 200 / 600 ms,
annotations updated, eight caption lines all on canvas, bands and colours unchanged,
SHORT still truncated at 1100 ms. No collisions.

**Status:** Complete. ~8 min against the 10 min expectation.
