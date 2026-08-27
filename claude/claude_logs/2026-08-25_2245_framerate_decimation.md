# Work Log: Frame-rate decimation vs prediction convergence

**Session:** 2026-08-25_2245
**Start:** 22:45:00
**Status:** ⏸ PHASE 1 complete — awaiting approval
**Duration:** [updating]

---

## Original Request

Measure how much of the prediction error is due to point count, by re-running the
observation-window sweep on decimated detections (30 fps, 20 fps) and comparing
convergence against the existing 60 fps result.

Phase 1 is **discovery only**: identify the script and detection set, the exact
line where detections for a window are selected, the RANSAC seed quoted verbatim,
and the minimum-inlier and n_iterations values. Then STOP.

---

## Objective

Separate two competing terms in the crossing-position error:

- **random** centroid noise, scaling ~1/sqrt(N), which WOULD improve with frame rate
- **conditioning**, set by how much arc the window covers, which would NOT

If 30 fps sits close to 60 fps, point count is not the limiter.

**Terminology:** the reference is the full-arc fixed-gravity-with-drag fit, so
every number is convergence toward that reference, not accuracy against ground
truth.

---

## 🔴 All timings from this run are void

Any run of this sweep on the laptop produces laptop timings. They are void, will
not be reported, and every latency figure in the report stays from the original
Pi run. Restated at the end.

---

## Path note

The brief cites `dev/claude_rules.md` and `dev/log_template.md`. **`dev/` does not
exist**; both are in `claude/`. Read from there. Same flag as the preceding logs.

---

## PHASE 1 — Discovery

Status: starting.

### [22:48] Item 3 — RANSAC seed — FIXED. No STOP.

**Hardcoded literal `42`, at the single call site.** Quoted verbatim,
`src/pi_benchmarking/prediction_pipeline_sweep_pi.py:378-382`:

```python
        t0 = perf_ms()
        try:
            res = ransac_fit(t_win, xyz_win, fit_fn, predict_fn, min_samples=MIN_SAMPLES_C,
                              inlier_threshold_mm=RANSAC_INLIER_THRESHOLD_MM,
                              n_iterations=N_ITERATIONS, random_seed=42, frame_numbers=frames0_win)
```

A grep for `random_seed` across the file returns exactly that one line.
`trajectory_fit.py:193` builds `rng = np.random.default_rng(random_seed)` fresh on
every call, so each (flight, window, rate, phase) draws an identical sequence.
Deterministic. **No STOP.**

### [22:49] Item 4 — minimum inliers and n_iterations — both as expected

```
 95: N_ITERATIONS = 3            # decisions 68/70 (adopted) -- realistic production-relevant cost
 96: MIN_SAMPLES_C = RANSAC_MIN_SAMPLES["C"]  # 8
```

resolved in `src/stereo/trajectory_fit.py:245`:

```python
RANSAC_MIN_SAMPLES = {"A": 6, "B": 6, "C": 8}  # more than bare theoretical
```

| | value |
|---|--:|
| minimum inliers (model C) | **8** |
| n_iterations | **3** |
| inlier threshold | `RANSAC_INLIER_THRESHOLD_MM` (unchanged) |

Both match the brief's expectation.

### [22:50] Item 2 — where detections for a window are selected

`src/pi_benchmarking/prediction_pipeline_sweep_pi.py:354-372`:

```python
    for T in T_VALUES_MS:
        row = {"T_ms": T}
        ...
        w_s = T / 1000.0
        n_w = int(np.searchsorted(t_full, w_s, side="right"))     # <-- 360
        row["n_detected"] = n_w
        row["n_ideal_cadence"] = T / CADENCE_MS

        if n_w < MIN_SAMPLES_C:                                    # <-- 364
            row["status"] = "not_fit_eligible"
            row["reason"] = f"only {n_w} points (< min_samples={MIN_SAMPLES_C})"
            result["t_rows"].append(row)
            continue

        t_win = t_full[:n_w]                                       # <-- 370
        xyz_win = xyz_full[:n_w]
        frames0_win = frames0_full[:n_w]
```

**Line 360** cuts the window by TIME against `t_full`; **lines 370-372** take the
prefix that enters the fit. Decimation must be applied to `t_full` / `xyz_full` /
`frames0_full` **before line 360**, so a window of a given duration contains
proportionally fewer points — which is the requested behaviour, and is NOT the
same as shortening the window.

**Line 364 is the fit-failure gate** (`n_w < 8`). Under decimation this will fire
at short windows. Those failures are results, not bugs, and are left alone.

### [22:52] 🔴 Item 1 — the sweep does NOT read a frozen detection set

**It detects inline, from images.** `prediction_pipeline_sweep_pi.py:316-330`:

```python
    # -- detect once, both cams CONCURRENT (threaded), real Pi wall-clock per pair --
    det0, det1, t_pair_ms = detect_flight_threaded(cam0_dir, cam1_dir, cfg)
    ...
    c0_csv = REPO_ROOT / "results" / "tmp_pipeline_sweep_detections" / f"{session}_{flight_id}_cam0.csv"
    c1_csv = REPO_ROOT / "results" / "tmp_pipeline_sweep_detections" / f"{session}_{flight_id}_cam1.csv"
    write_detections3_csv(c0_csv, det0)
    write_detections3_csv(c1_csv, det1)

    pairs = build_corrected_pairs(c0_csv, c1_csv, ts_csv, ...)
```

So the answer to "which frozen detection set produced `pipeline_sweep_raw.csv`" is
**none**. It runs RECT detection over the raw images each time and writes the
result to a scratch directory.

<details><summary>Diagnostic: what frozen detection sources DO exist</summary>

```
=== tmp_pipeline_sweep_detections: what is there now? ===
214 files
-rw-r--r-- 2026-08-25 21:06  2026_07_15_gym_flight_11_cam0.csv
-rw-r--r-- 2026-08-25 21:06  2026_07_15_gym_flight_11_cam1.csv
...

=== does the tmp set cover all 107 sweep flights? ===
  sweep flights: 107   tmp dir covers: 107   missing: 0

=== other frozen sets ===
results/detector_tuning/detections/03_stride1_thresh16_openk3_area30_circ0.3/  (ELLIPSE)
results/detector_tuning/detections/12_rect_close_kernel/                       (326 csv)
```
</details>

**`results/tmp_pipeline_sweep_detections/` now holds all 214 CSVs (107 flights x
2 cams)** — written by the positions re-run at 21:06-21:22, i.e. the exact RECT
detections this sweep produces, frozen to disk.

#### 🟡 Consequence for Phase 2 — reported, not resolved

The brief requires "No new detection. Frozen detections only." The script as
written cannot satisfy that, because detection is inline. Two paths:

1. **Keep `detect_flight_threaded` and decimate after it.** Detections are
   recomputed identically, but detection code *does* execute — arguably re-running
   detection. It also dominates cost: the positions re-run took ~956 s wall clock
   for one arm, almost all of it detection. Six arms that way is **~96 minutes**,
   which **exceeds the brief's own 60-minute stop threshold**.
2. **Read the frozen CSVs from `results/tmp_pipeline_sweep_detections/` and skip
   `detect_flight_threaded` entirely.** Satisfies "frozen detections only"
   literally, and removes the dominant cost so six arms fit comfortably inside the
   threshold.

Path 2 is the only one that satisfies both the no-new-detection rule and the
runtime limit, but it **does modify the copy upstream of the fit** — replacing the
detect call with a CSV read. Nothing downstream of `build_corrected_pairs` would
change: same pairing, triangulation, model, K, RANSAC parameters, seed, plane and
reference.

Caveat worth stating plainly: those CSVs were written by the laptop positions run,
not the original Pi run. The item-10 regression check (60 fps arm must reproduce
`pipeline_sweep_raw.csv`'s `position_error_mm` for all 2568 cells) is exactly the
test of whether that substitution is sound — so the check is load-bearing here,
not a formality.

**Not deciding this unilaterally.** Awaiting approval.

---

## PHASE 1 COMPLETE — awaiting approval

---

## PHASE 2 — Path 2 approved (frozen CSVs, detection skipped)

### [23:05] Condition 1 — VERIFIED, no STOP

The frozen CSVs **are** per-camera detections written **before**
`build_corrected_pairs`.

`write_detections3_csv` (line 211) emits exactly three columns from the raw
per-camera detection dict:

```python
        w.writerow(["frame_number", "u", "v"])
        for fn in sorted(detections):
            u, v = detections[fn]
            w.writerow([fn, u, v])
```

A frozen file's actual header matches:

```
frame_number,u,v
43,238.95243166489172,573.1178558750444
```

and `build_corrected_pairs` (pixel_velocity_correction.py:96-110) consumes them
with `load_detections3`, then does its own Step-A trajectory filter and pairing:

```python
    raw0 = load_detections3(cam0_detections3_csv)
    raw1 = load_detections3(cam1_detections3_csv)
    kept0 = dc.filter_trajectory_outliers(raw0, max_speed_px_per_frame, min_run_length)
```

So the read enters at exactly the point `detect_flight_threaded` exited: the same
two CSVs plus the same timestamps file, into the same call. Trajectory filtering,
pairing, triangulation and fit all still run. **Not post-pairing. No STOP.**

### [23:08] Script written

`src/regen_2class/framerate_decimation_sweep.py`, copied from the verified
`prediction_pipeline_sweep_positions.py` (it already exposes
`cy_own/cz_own/cy_ref/cz_ref`, which item 9 asks for "if the source script
already exposes them"). Original Pi script untouched.

Changes, all upstream of or around the window cut:

| what | detail |
|---|---|
| detection | `detect_flight_threaded(...)` call replaced by a read of the two frozen per-camera CSVs; missing file -> flight skipped with a reason |
| `t_pair_ms` | set to `{}`. It fed only `last_pair_detect_ms` -> `latency_ms`, both TIMING and void here. Empty makes them NaN rather than inventing a laptop number |
| decimation | on **cam0 frame number**, `frame % step == offset`, applied to `pairs` **before** the window cut at line 360 |
| re-anchor | `t_full` re-anchored on the first RETAINED pair — a camera at that rate and phase starts its clock at its own first sample. At step=1/offset=0 this reduces exactly to the original |
| arms | `--rates` flag; 60 alone by default so the regression arm runs first |
| schema | rows gain `fps`, `phase`, `n_points_used` |

Unchanged: pairing, triangulation, model, K, RANSAC parameters, **seed 42**,
`MIN_SAMPLES_C = 8`, the line-364 fit-failure gate, plane, reference, window grid,
flight population.

#### 🟡 Decimation is on FRAME NUMBER, not list index

A camera at 30 fps captures every 2nd frame whether or not the detector found the
ball in it. Selecting on `cam0_frame % step == offset` reproduces that. Selecting
on position in the pair list would let a single detection gap shift the phase of
every later sample, which no real camera does.

### [23:20] Condition 2 — 60 fps arm run FIRST and ALONE

`--rates 60`. 2568 rows, 107/107 flights, 581 s wall clock.

### [23:22] ITEM-10 REGRESSION GATE — PASS

**0 failures at 1.0 mm, limit 10.**

<details><summary>Full gate output</summary>

```
new (60 fps, frozen detections): results\regenerate_figures\05_framerate_decimation\decimation_60fps.csv  rows=2568
old (existing sweep)           : results\pi_benchmarking\02_pi_pipeline_sweep_parallel_detection\pipeline_sweep_raw.csv  rows=2568
unique keys: new=2568  old=2568

keys in old but not new : 0
keys in new but not old : 0
flights old=107  new=107  lost=0

==============================================================================
ITEM-10 REGRESSION GATE  (60 fps, frozen detections vs existing sweep)
==============================================================================
  rows compared                    : 2481
  matching within 1e-06 mm          : 275  (11.08%)
  matching within 1 mm             : 2481  (100.00%)
  FAILING the 1 mm gate           : 0

  blank on both (fit ineligible)   : 87
  present old, blank new           : 0
  present new, blank old           : 0
  total accounted for              : 2568

  no row fails the 1 mm gate

  delta distribution (mm): min 9.004e-11  median 7.915e-06  p95 2.033e-04  p99 6.679e-04  max 1.357e-02

  GATE PASS: 0 failures, limit 10. The frozen per-camera CSVs reproduce the inline detector.
```
</details>

**Every failing row: none.** The list required by item 10 is empty.

The 1e-6 tier again sits at 11.08%, identical to the positions run's figure, with
the same delta distribution (median 7.9e-06 mm, max 1.36e-02 mm). That is
cross-platform float behaviour in the adaptive ODE solve, not a detection
difference — and it is the *same* distribution as the run that still did inline
detection, which is itself evidence the substitution changed nothing.

**Conclusion: reading the frozen per-camera CSVs is equivalent to running the
inline detector.** The decimated arms may proceed.

### Runtime estimate for the remaining arms

60 fps took 581 s. The five decimated arms do the same pairing and triangulation
and fewer fits each (decimation reduces points, and more short windows fail the
n<8 gate before fitting). Estimate **~45-50 minutes for all six arms**, or
**~40 minutes for the remaining five**. Under the 60-minute threshold, but not by
much.

(That 581 s is wall clock for planning purposes, not a latency measurement.)

## 🔴 All timings from this run are void

`last_pair_detect_ms` and `latency_ms` are NaN by construction in this arm. No
timing value from this run is reported or carried forward. Every latency figure in
the report remains the original Pi run's.

**Status: 60 fps arm complete and validated. Awaiting approval to run 30 and 20 fps.**

---

## PHASE 3 — Two-panel figure from the completed arms

**Started:** 2026-08-26 00:4x. Aggregation and plotting only. No arm re-run.

Rules file read first, as instructed. Noting again that the brief cites
`dev/claude_rules.md`; **`dev/` does not exist** — the file is `claude/claude_rules.md`.
Same flag as every preceding log in this task.

### The claim this figure has to carry

Frame rate does **not** materially change prediction convergence, but it **does**
set the minimum usable observation window, through the 8-inlier requirement of the
robust fit. Panel A carries the first half, Panel B the second. The contrast
between the panels is the argument, so both must be on the same x axis.

### [00:4x] Arm CSVs found — 4 of the 6 planned

Two arms (20 fps phase 1 and phase 2) were cut mid-run and wrote nothing. What
exists:

| file | arm | rows | flights | windows | ok | not_fit_eligible | fit_failed | blank err |
|---|---|--:|--:|--:|--:|--:|--:|--:|
| `decimation_60fps.csv` | 60 fps ph0 | 2568 | 107 | 24 | 2481 | 0 | 87 | 87 |
| `decimation_30fps_phase0.csv` | 30 fps ph0 | 2568 | 107 | 24 | 2070 | 224 | 274 | 498 |
| `decimation_30fps_phase1.csv` | 30 fps ph1 | 2568 | 107 | 24 | 2082 | 233 | 253 | 486 |
| `decimation_20fps_phase0.csv` | 20 fps ph0 | 2568 | 107 | 24 | 1796 | 447 | 325 | 772 |

**Every arm is exactly 2568 rows (107 x 24). No STOP triggered.**

Checked and true in all four files: `blank position_error_mm` count equals
`not_fit_eligible + fit_failed` exactly. So `status != ok` and `blank error` are
the same set, and the failure definition in the brief (either condition) is not
double-counting or missing anything.

**Phase coverage is asymmetric and this is a real limitation of the figure:**
60 fps has its only possible phase (step 1 — nothing to offset), 30 fps has both
of 2, but 20 fps has **1 of 3**. The 20 fps line therefore rests on a single grid
alignment, and 20 fps is the rate most exposed to phase because it discards two
frames in three. Recorded here so the figure is not read as if all three rates
were equally averaged.

### 🔴 Why Panel A must be paired — recorded before writing the code

The brief is explicit and the reason is worth keeping in the log, because the
unpaired version of this plot tells the opposite story:

At 400 ms the **unpaired** 30 fps median error (90 mm) is *better* than 60 fps
(137 mm). That is an artefact. 21.5% of 30 fps cells have no fit at that window,
and the ones that fail are the hard flights — short, fast, few points. Dropping
them leaves 30 fps being scored on an easier subset than 60 fps. The comparison
measures which flights survived, not which rate is more accurate.

Pairing on `(session, flight, T_ms)` and requiring **both** arms to have produced
a fit removes exactly that selection effect. Consequence to keep in view: the
paired 60 fps curve is *not* the same curve as the all-flights 60 fps curve — it
is 60 fps restricted to the cells its comparison rate also managed, and it is a
different restriction for the 30 fps comparison than for the 20 fps one. The
script therefore emits a separate paired-60 column per comparison rate rather
than one shared 60 fps series.

Where `n_pair < 60` the line is drawn dashed and lighter: below that the surviving
set is small and self-selected, so the median is not comparable to the solid
region even though it is still a paired number.

**No unpaired error comparison is produced or reported anywhere.**

### [00:5x] Script written — `src/regen_2class/framerate_two_panel.py`

504 lines, one file. **Not executed** — the brief reserves the run for the user.

Static checks only:

```
syntax OK  (504 lines)
undefined names: ['__file__']        <- module global, not a real finding
module imported OK; main() NOT invoked
median([]) -> None | median([1,2,3,4]) -> 2.5
```

#### 🟡 Design decision: there are TWO 60 fps baselines in Panel A, not one

The brief says to plot "the paired median error for 60 fps (restricted to the
paired set for that comparison), 30 fps and 20 fps". Read literally, "that
comparison" is per-comparison — and it has to be, because the paired set against
30 fps is a different set of cells from the paired set against 20 fps. 20 fps
fails on more cells, so pairing against it discards more, and the 60 fps median
over what survives is a different number.

Options considered:

1. **One 60 fps line, using the 30 fps pairing.** Rejected: it would sit in the
   same panel as the 20 fps curve while not being its baseline, which invites
   exactly the wrong comparison.
2. **One 60 fps line over the three-way intersection** (cells all rates fitted).
   Rejected: it changes the 30 fps comparison to satisfy the 20 fps one, and
   throws away paired 30 fps cells that are perfectly valid.
3. **Two 60 fps baselines, one per comparison.** Chosen. Each comparison is then
   internally honest, and the CSV carries both columns anyway.

Kept distinguishable by shade and marker (`s` vs `^`, dark vs light blue) rather
than by linestyle, because **linestyle is already carrying the `n_pair < 60`
meaning** and must not encode two things at once.

This is an interpretation of an ambiguous line in the brief rather than a
deviation from it, so it is logged and reported rather than treated as a STOP.

#### Gates the script enforces, in order

| gate | STOP condition |
|---|---|
| arm row count | any arm CSV whose row count is not 2568 |
| arm purity | an arm CSV mixing more than one `(fps, phase)` |
| arm duplication | the same `(fps, phase)` in two CSVs (would double-count) |
| arm shape | any arm not 107 flights x 24 windows |
| duplicate key | a repeated `(session, flight, T_ms)` within one arm |
| pairing soundness | a key present in a comparison arm but absent from 60 fps |
| base arm present | no 60 fps arm — Panel A cannot be built without it |
| empty comparison | a rate with zero paired cells at **every** window |

Expected-and-continue, per the brief: a rate having zero paired cells at the
**shortest** windows. Those windows are written to the CSV with `n_pair = 0` and
a blank median, and are kept on the x axis rather than dropped, so the gap is
visible as a gap.

#### Design choices worth recording

- **Phases are pooled, not averaged as medians.** For a rate with two phases,
  both phases' paired cells go into one median rather than taking a median of
  two medians. A median of medians would weight a phase with few surviving cells
  equally against one with many.
- **Panel B sums phases rather than averaging fractions.** With equal cell counts
  per phase the two are arithmetically identical, but summing keeps `n_total`
  honest about how much evidence sits behind each point.
- **`cell_ok` tests status AND non-blank error**, though they were verified
  equivalent across all four arms, because the brief defines failure as either.
- **`first_stable_below` scans from the long-window end backwards**, so a single
  spike at a long window correctly disqualifies every shorter window. Scanning
  forwards and stopping at the first sub-threshold value would report a window
  that does not actually "stay below".
- **No smoothing, no interpolation, no fitted curve.** Markers at measured
  windows, straight segments between them.

#### Outputs (all via `next_free()`, nothing overwritten)

| file | content |
|---|---|
| `framerate_panelA_paired.csv` | per (rate, T_ms): `n_pair`, paired 60 fps median, comparison-rate median, ratio, median `n_points_used` for both |
| `framerate_panelB_failures.csv` | per (rate, T_ms): `n_total`, `n_failed`, `fail_fraction` |
| `figure_framerate_two_panel.png` | stacked panels, shared x, single legend, white background |

The script prints both tables in full and the minimum-window threshold before
writing the figure, so the numbers reach the log even if the figure is later
redrawn.

**No timing column is read, plotted or written. No unpaired error comparison is
produced anywhere in this script.**

Awaiting the user's run.

### [01:0x] RUN COMPLETE

Runtime: seconds, as expected. Outputs written (none pre-existing, so no
`next_free()` suffix was needed):

```
framerate_panelA_paired.csv     48 rows
framerate_panelB_failures.csv   72 rows
figure_framerate_two_panel.png
```

Arms consumed: 20 fps ph0, 30 fps ph0, 30 fps ph1, 60 fps ph0. The script printed
its own note that 20 fps has 1 of 3 phases and is therefore not fully
phase-averaged.

No gate fired.

#### PANEL A — paired convergence error, 30 fps vs 60 fps

`60fps med` is 60 fps restricted to the cells 30 fps also fitted.

```
    T_ms  n_pair   60fps med   rate med   ratio   60 pts  rate pts   note
     150       0                                                     no paired cells
     200       0                                                     no paired cells
     250      45    130.5547   137.0121  1.0495     16.0       8.0   self-selected
     300     108     96.5654   104.2970  1.0801     19.0      10.0
     350     132     93.1136    99.8168  1.0720     22.0      11.0
     400     168     97.9307    90.0901  0.9199     25.0      13.0
     450     189    103.8536   106.4501  1.0250     28.0      14.0
     490     193     94.3846   102.4730  1.0857     30.0      15.0
     500     195     85.6323    91.8195  1.0723     31.0      16.0
     550     196     79.7529    83.2653  1.0440     33.0      17.0
     600     205     67.2869    66.0806  0.9821     36.0      19.0
     650     207     58.4736    63.8783  1.0924     39.0      19.0
     700     206     54.8563    63.3924  1.1556     41.0      21.0
     750     207     52.9511    55.6070  1.0502     44.0      22.0
     800     208     51.4196    50.3695  0.9796     46.0      24.0
     850     213     44.5838    51.3470  1.1517     49.0      24.0
     900     211     39.9605    41.8223  1.0466     51.0      26.0
     950     211     39.4626    43.3105  1.0975     53.0      27.0
    1000     210     39.0171    35.7527  0.9163     56.0      28.0
    1050     210     34.9113    36.0192  1.0317     58.0      29.0
    1100     203     26.8029    31.5611  1.1775     61.0      31.0
    1150     208     25.3500    29.3224  1.1567     64.0      32.0
    1200     208     26.2750    25.3592  0.9651     66.0      33.5
    1250     208     25.4931    24.7162  0.9695     69.0      34.0
```

#### PANEL A — paired convergence error, 20 fps vs 60 fps

```
    T_ms  n_pair   60fps med   rate med   ratio   60 pts  rate pts   note
     150       0                                                     no paired cells
     200       0                                                     no paired cells
     250       0                                                     no paired cells
     300       0                                                     no paired cells
     350      28     73.6766   107.4540  1.4585     22.0       8.0   self-selected
     400      44    118.7347    87.2646  0.7350     25.0       9.0   self-selected
     450      66     80.0064    92.4566  1.1556     28.0      10.0
     490      66     76.9570    92.4566  1.2014     30.0      10.0
     500      82     78.1179    73.9276  0.9464     31.0      11.0
     550      90     70.1363    84.7890  1.2089     33.0      12.0
     600      95     54.9469    67.0762  1.2207     36.0      13.0
     650      98     56.5734    65.3254  1.1547     39.0      14.0
     700     101     61.9062    60.5703  0.9784     41.0      15.0
     750      99     52.8724    56.5875  1.0703     44.0      15.0
     800     102     52.6021    62.5141  1.1884     46.0      16.0
     850     105     44.5838    56.6013  1.2695     49.0      17.0
     900     102     41.8710    54.0884  1.2918     51.0      18.0
     950     104     40.8151    45.1140  1.1053     53.0      18.0
    1000     103     37.3300    41.5071  1.1119     56.0      19.0
    1050     103     34.9646    39.7134  1.1358     59.0      20.0
    1100     100     27.0114    35.6384  1.3194     61.0      21.0
    1150     100     25.6311    35.1044  1.3696     64.0      22.0
    1200     100     26.2750    31.5696  1.2015     66.0      22.0
    1250     102     25.4931    28.3194  1.1109     69.0      23.0
```

#### PANEL B — fit-failure fraction, all flights, unpaired

30 fps totals are 214 because both its phases are pooled; 60 and 20 fps are 107.

```
    T_ms                  60 fps                  30 fps                  20 fps
            failed/total     pct    failed/total     pct    failed/total     pct
     150          45/107   42.1%         214/214  100.0%         107/107  100.0%
     200          17/107   15.9%         214/214  100.0%         107/107  100.0%
     250          11/107   10.3%         169/214   79.0%         107/107  100.0%
     300           1/107    0.9%         106/214   49.5%         107/107  100.0%
     350           0/107    0.0%          82/214   38.3%          79/107   73.8%
     400           0/107    0.0%          46/214   21.5%          63/107   58.9%
     450           1/107    0.9%          25/214   11.7%          41/107   38.3%
     490           1/107    0.9%          21/214    9.8%          41/107   38.3%
     500           1/107    0.9%          19/214    8.9%          25/107   23.4%
     550           1/107    0.9%          18/214    8.4%          17/107   15.9%
     600           0/107    0.0%           9/214    4.2%          12/107   11.2%
     650           0/107    0.0%           7/214    3.3%           9/107    8.4%
     700           0/107    0.0%           8/214    3.7%           6/107    5.6%
     750           0/107    0.0%           7/214    3.3%           8/107    7.5%
     800           1/107    0.9%           4/214    1.9%           4/107    3.7%
     850           0/107    0.0%           1/214    0.5%           2/107    1.9%
     900           1/107    0.9%           2/214    0.9%           4/107    3.7%
     950           0/107    0.0%           3/214    1.4%           3/107    2.8%
    1000           0/107    0.0%           4/214    1.9%           4/107    3.7%
    1050           0/107    0.0%           4/214    1.9%           4/107    3.7%
    1100           4/107    3.7%           6/214    2.8%           3/107    2.8%
    1150           0/107    0.0%           6/214    2.8%           7/107    6.5%
    1200           2/107    1.9%           4/214    1.9%           7/107    6.5%
    1250           1/107    0.9%           5/214    2.3%           5/107    4.7%
```

#### MINIMUM USABLE WINDOW — failure fraction first below 5% and staying below

| rate | minimum window |
|---|---|
| 60 fps | **300 ms** |
| 30 fps | **600 ms** |
| 20 fps | **1250 ms** |

Note on the 20 fps figure: it is 1250 ms because the criterion requires the
fraction to stay below 5% at every longer window, and 20 fps is at 6.5% at both
1150 and 1200 ms. It first *touches* below 5% much earlier (3.7% at 800 ms) but
does not stay there. This is the backwards-scan behaviour working as designed,
not an artefact.

### [01:0x] 🟡 Defect in the rendered figure — reported, NOT fixed

The shared legend carries a **fifth entry, a plain "60 fps"**, which comes from
Panel B's handles being merged in. Panel A's own entries are the two paired
baselines ("60 fps (paired vs 30)", "60 fps (paired vs 20)") plus "30 fps" and
"20 fps"; the merge loop adds any Panel B label not already present, and Panel B's
60 fps line is labelled plainly, so it survives deduplication while "30 fps" and
"20 fps" do not.

Effect: the legend mixes Panel A identities with one Panel B identity, and a
reader could take the plain "60 fps" swatch for a fifth curve in Panel A.

**Not fixed, because the brief says not to modify the script after running.**
Recorded here for a decision. The fix is confined to the legend-merge block in
`draw()` and touches no computed value.

### [01:0x] Addition 1 — n_pair per (rate, window)

`n_pair < 60` is the dashed/faded region.

| T_ms | 30 fps n_pair | 30 fps line | 20 fps n_pair | 20 fps line |
|--:|--:|:--|--:|:--|
| 150 | 0 | **no paired cells** | 0 | **no paired cells** |
| 200 | 0 | **no paired cells** | 0 | **no paired cells** |
| 250 | 45 | dashed | 0 | **no paired cells** |
| 300 | 108 | solid | 0 | **no paired cells** |
| 350 | 132 | solid | 28 | dashed |
| 400 | 168 | solid | 44 | dashed |
| 450 | 189 | solid | 66 | solid |
| 490 | 193 | solid | 66 | solid |
| 500 | 195 | solid | 82 | solid |
| 550 | 196 | solid | 90 | solid |
| 600 | 205 | solid | 95 | solid |
| 650 | 207 | solid | 98 | solid |
| 700 | 206 | solid | 101 | solid |
| 750 | 207 | solid | 99 | solid |
| 800 | 208 | solid | 102 | solid |
| 850 | 213 | solid | 105 | solid |
| 900 | 211 | solid | 102 | solid |
| 950 | 211 | solid | 104 | solid |
| 1000 | 210 | solid | 103 | solid |
| 1050 | 210 | solid | 103 | solid |
| 1100 | 203 | solid | 100 | solid |
| 1150 | 208 | solid | 100 | solid |
| 1200 | 208 | solid | 100 | solid |
| 1250 | 208 | solid | 102 | solid |

Segment boundaries:

- **30 fps** — no paired cells at 150, 200 ms; dashed at 250 ms only; **solid from 300 ms**
- **20 fps** — no paired cells at 150–300 ms; dashed at 350 and 400 ms; **solid from 450 ms**

30 fps `n_pair` maxima reach 213 of a possible 214 (107 flights x 2 phases);
20 fps reaches 105 of a possible 107 (1 phase).

### [01:0x] Addition 2 — the two operating points

SHORT 400 ms and LONG 850 ms. The `60 fps` column differs between the two rate
blocks because each is 60 fps restricted to the cells that rate also fitted; at
850 ms the two restrictions happen to give the same median (44.5838), at 400 ms
they do not.

| window | rate | n_pair | 60 fps median err (mm) | rate median err (mm) | ratio | 60 fps median pts | rate median pts |
|--:|--:|--:|--:|--:|--:|--:|--:|
| 400 | 30 | 168 | 97.9307 | 90.0901 | 0.9199 | 25.0 | 13.0 |
| 400 | 20 | 44 | 118.7347 | 87.2646 | 0.7350 | 25.0 | 9.0 |
| 850 | 30 | 213 | 44.5838 | 51.3470 | 1.1517 | 49.0 | 24.0 |
| 850 | 20 | 105 | 44.5838 | 56.6013 | 1.2695 | 49.0 | 17.0 |

**The 400 ms / 20 fps row sits at `n_pair = 44`, inside the dashed region**, so
it is one of the self-selected points and is drawn dashed in Panel A. Flagged
because the brief names 400 ms as the SHORT operating point and this is the one
operating-point cell that does not meet the solid-line threshold.

---

## PHASE 3 COMPLETE

Script written, run once, not modified after the run. Log appended throughout.
No timing value was read, plotted or written anywhere in this phase. No unpaired
error comparison was produced.

---

## PHASE 4 — Rebuilt on a common flight set (3 lines)

**Trigger:** two objections from the user. (1) "cells" is confusing terminology.
(2) Why can there not simply be three lines, 60 / 30 / 20.

### Terminology dropped

"Cell" is gone from every user-facing string. At any given window each unit is
just **one flight**, so Panel B's y-axis is now `flights with no fit (%)` and the
printed tables count flights. `cell_ok()` survives as an internal identifier
only — it is not user-facing.

### 🔴 The three-line question — resolved by changing the pairing, not the plot

The previous figure had two 60 fps baselines because each comparison had its own
paired set. That was correct but unreadable. The user chose the alternative:
restrict **all three rates to the flights every arm fitted**, so one 60 fps line
is legitimately the baseline for both comparisons.

Rule now implemented: a flight enters a window only if 60 fps **and both 30 fps
phases and** 20 fps all produced a fit for it at that window. Within a rate,
phases are pooled — a flight contributes one observation per phase.

**The cost, stated plainly:** 20 fps fits the fewest flights, so it sets the
common set for everyone. The 30 fps comparison loses most of its evidence at
short windows — at 400 ms it drops from 168 paired flights to **42 common
flights**. This was a deliberate trade of statistical power for one readable
baseline, made by the user with the cost stated in advance.

Consequence recorded so the figure is not over-read: **the 60 fps line in
Panel A is NOT the all-flights 60 fps curve.** It is 60 fps on the subset every
rate managed, which at short windows is a small and relatively easy subset.
Panel B is unaffected — it stays all-flights and unpaired.

### Common flight count per window

| T_ms | common flights | line |
|--:|--:|:--|
| 150–300 | 0 | **no common flights** |
| 350 | 19 | dashed |
| 400 | 42 | dashed |
| 450 | 63 | solid |
| 490 | 65 | solid |
| 500 | 78 | solid |
| 550 | 84 | solid |
| 600 | 91 | solid |
| 650 | 95 | solid |
| 700 | 96 | solid |
| 750 | 96 | solid |
| 800 | 99 | solid |
| 850 | 104 | solid |
| 900 | 101 | solid |
| 950 | 102 | solid |
| 1000 | 101 | solid |
| 1050 | 101 | solid |
| 1100 | 98 | solid |
| 1150 | 99 | solid |
| 1200 | 100 | solid |
| 1250 | 99 | solid |

All three lines break to dashed at the same window now, because the threshold is
driven by one shared count rather than three different ones. Solid from **450 ms**.

### PANEL A — common-set convergence error

```
    T_ms  flights    60 fps err    pts    x60    30 fps err    pts    x60    20 fps err    pts    x60   note
     150        0                                                                                       no common flights
     200        0                                                                                       no common flights
     250        0                                                                                       no common flights
     300        0                                                                                       no common flights
     350       19       67.8386   22.0 1.0000       82.1222   11.0 1.2106       79.5931    8.0 1.1733   self-selected
     400       42      103.9631   25.0 1.0000       76.1220   13.0 0.7322       83.2825    9.0 0.8011   self-selected
     450       63       70.8518   28.0 1.0000       83.3803   14.0 1.1768       89.0112   10.0 1.2563
     490       65       77.3910   30.0 1.0000       80.6413   15.0 1.0420       95.9020   10.0 1.2392
     500       78       75.1006   31.0 1.0000       73.5984   16.0 0.9800       69.3768   11.0 0.9238
     550       84       64.9463   34.0 1.0000       74.2098   17.0 1.1426       79.5223   12.0 1.2244
     600       91       49.6865   36.0 1.0000       58.5884   19.0 1.1792       66.0611   13.0 1.3296
     650       95       55.9312   39.0 1.0000       57.6469   20.0 1.0307       62.0472   14.0 1.1093
     700       96       52.4177   41.0 1.0000       60.9717   21.0 1.1632       60.0242   15.0 1.1451
     750       96       52.2203   44.0 1.0000       51.1808   22.0 0.9801       54.6444   15.0 1.0464
     800       99       51.3202   46.0 1.0000       48.2007   24.0 0.9392       61.7058   16.0 1.2024
     850      104       43.7670   49.0 1.0000       51.1121   24.0 1.1678       55.5320   17.0 1.2688
     900      101       41.4460   51.0 1.0000       41.1060   26.0 0.9918       53.9574   18.0 1.3019
     950      102       39.6682   53.0 1.0000       41.8364   27.0 1.0547       44.4264   18.0 1.1199
    1000      101       37.3300   56.0 1.0000       35.0655   28.0 0.9393       41.5071   19.0 1.1119
    1050      101       34.8580   59.0 1.0000       35.8241   29.0 1.0277       39.3045   20.0 1.1276
    1100       98       26.7062   61.0 1.0000       31.0795   31.0 1.1638       35.6384   21.0 1.3345
    1150       99       25.3500   64.0 1.0000       28.7949   32.0 1.1359       35.0190   22.0 1.3814
    1200      100       26.2750   66.0 1.0000       24.9319   34.0 0.9489       31.5696   22.0 1.2015
    1250       99       25.3126   69.0 1.0000       24.1623   34.0 0.9546       27.4493   23.0 1.0844
```

### The two operating points, common-set

| window | flights | 60 fps err / pts | 30 fps err / pts | 20 fps err / pts |
|--:|--:|--:|--:|--:|
| 400 ms (SHORT) | 42 | 103.9631 mm / 25.0 | 76.1220 mm / 13.0 | 83.2825 mm / 9.0 |
| 850 ms (LONG) | 104 | 43.7670 mm / 49.0 | 51.1121 mm / 24.0 | 55.5320 mm / 17.0 |

400 ms sits at 42 common flights, **below the 60 threshold**, so the SHORT
operating point is in the dashed region.

### Panel B unchanged

Identical to Phase 3 — it never used pairing. Minimum usable window is unchanged:
**60 fps 300 ms, 30 fps 600 ms, 20 fps 1250 ms.**

### Legend defect from Phase 3 — now fixed as a side effect

Phase 3's stray fifth legend entry (a plain "60 fps" leaking in from Panel B)
is gone. Both panels now label their series identically as `60 fps` / `30 fps` /
`20 fps`, so the merge deduplicates to exactly three entries. The fix came from
the restructure, not from a separate edit.

### Outputs (next_free suffixes, nothing overwritten)

```
framerate_panelA_paired_02.csv        72 rows  (long format: one row per rate x window)
framerate_panelB_failures_02.csv      72 rows  (unchanged content)
figure_framerate_two_panel_02.png
```

Phase 3's `_01` outputs are left untouched on disk.

**No timing value read, plotted or written. Panel B remains the only unpaired
quantity, and it is a failure count, not an error comparison.**

---

## PHASE 4 COMPLETE
