# Work Log: Persist crossing positions (laptop re-run, positions only)

**Session:** 2026-08-25_0212
**Start:** 02:12:00
**Status:** ✅ Complete
**Duration:** [updating]

---

## Original Request

Create a laptop copy of `prediction_pipeline_sweep_pi.py` that additionally
persists `cy_own`, `cz_own`, `cy_ref`, `cz_ref`; re-run the 107-flight x
24-window sweep on the laptop; verify against the original Pi sweep's
`position_error_mm`; report and STOP.

Follow-on from Phase 1 of the zone-classification task
([2026-08-25_0158_zone_classification.md](2026-08-25_0158_zone_classification.md)),
which found the predicted crossing position is computed at
`prediction_pipeline_sweep_pi.py:402-426` and discarded at `row.update(...)`.

---

## 🔴 ALL TIMING OUTPUT FROM THIS RUN IS VOID

This run exists to recover **positions only**. It executes on the laptop, not the
Pi. Every timing column it produces — `last_pair_detect_ms`, `triangulate_ms`,
`ransac_ms`, `predict_ms`, `latency_ms`, `latency_feasible` — is a **laptop**
measurement and is **void**. None of it may be quoted, carried forward, or
compared against anything.

Every latency figure in the report came from the original Pi run
(`results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/`) and stays
that way. This log will restate this at the end.

---

## Path note, recorded before starting

The brief cites `dev/claude_rules.md` and `dev/log_template.md`. **`dev/` does
not exist.** Both files are in `claude/`:

```
claude/claude_rules.md   18977 bytes
claude/log_template.md   23883 bytes
```

Read from there. Flagged rather than silently substituted. Same note as the
previous task's log.

---

## Method note — why this is done solo, not fanned out to agents

Ultracode is on, which biases toward orchestrating with subagents. Not used here,
deliberately: the brief forbids writing anything outside two specific paths, and
earlier today a subagent created a file it had been explicitly told not to create
(`src/regen_2class/ransac_effect_flight22_clean.py`, logged in
[2026-08-24_1400_caption_extraction.md](2026-08-24_1400_caption_extraction.md)).
The work here is one file copy, one localised edit, one run and one deterministic
numeric gate — none of it benefits from parallel exploration, and all of it is
exactly reproducible. The containment risk outweighs the (nil) speed gain.

---

## STEP 1 — RANSAC seed check

Status: starting.

### [02:14] Step 1 result — seed is FIXED. No STOP.

**The RANSAC seed is a hardcoded literal `42`, set at the single call site.**
Not per-flight, not unseeded.

Quoted verbatim, `src/pi_benchmarking/prediction_pipeline_sweep_pi.py:378-382`:

```python
        t0 = perf_ms()
        try:
            res = ransac_fit(t_win, xyz_win, fit_fn, predict_fn, min_samples=MIN_SAMPLES_C,
                              inlier_threshold_mm=RANSAC_INLIER_THRESHOLD_MM,
                              n_iterations=N_ITERATIONS, random_seed=42, frame_numbers=frames0_win)
```

A grep for `seed|random|rng|np.random|RANSAC_SEED` across the whole file returns
**exactly one line** — line 382 above. There is no other RNG touch point.

And `src/stereo/trajectory_fit.py:193`, inside `ransac_fit`:

```python
    rng = np.random.default_rng(random_seed)
```

The generator is constructed **fresh on every call** from that constant, so every
(flight, window) pair draws an identical sample sequence. The sweep is fully
deterministic and reproducible on any machine.

---

### [02:16] Steps 2-3 — copy made, edit applied

**Copy:** `src/regen_2class/prediction_pipeline_sweep_positions.py`

```
src md5 : b32e9204c37bb5f17b194402a6f4f926
dst md5 : b32e9204c37bb5f17b194402a6f4f926   (identical at copy time)
```

Original untouched — mtime still `2026-08-24 09:42`, unchanged from the
migration.

**The diff is three hunks, all additive. No line was removed or altered.**

<details><summary>Hunk 1 — row.update(), the only computational change</summary>

Added four keys to the existing `row.update(...)` at what is now line ~426:

```python
cy_own=cy_own, cz_own=cz_own,
cy_ref=float(ref_row["crossing_Y"]), cz_ref=float(ref_row["crossing_Z"]),
```

`cy_own`/`cz_own` were already computed at lines 406-407 and thrown away; they
are now kept. Nothing about how they are computed changed.
</details>

<details><summary>Hunk 2 — a --csv option</summary>

```python
ap.add_argument("--csv", default=None,
                help="also emit a positions CSV (timing columns omitted)")
```
</details>

<details><summary>Hunk 3 — CSV emit at the end</summary>

The Pi script writes **JSON only**; `pipeline_sweep_raw.csv` is produced
separately by `src/stereo/pipeline_sweep_aggregate.py`. The brief requires a CSV
at a specific path, so the copy emits one itself. It refuses to overwrite:

```python
if csv_path.exists():
    raise SystemExit(f"refusing to overwrite existing file: {csv_path}")
```

Columns: session, flight, T_ms, status, airborne, n_detected, **cy_own, cz_own,
cy_ref, cz_ref**, position_error_mm, velocity_error_mm_s, cls_own,
hit_miss_match, t_cross_own_ms.
</details>

#### 🟡 Decision: timing columns deliberately OMITTED from the CSV

Options considered:

1. **Mirror the Pi CSV's schema exactly**, timing columns included. Rejected —
   this is a laptop run, so those columns would be void numbers sitting in a file
   that looks like the Pi sweep. Anyone joining on (flight, window) later would
   have no signal that they must not be used.
2. **Omit timing columns entirely.** Chosen. The void values cannot leak because
   they are not written. `--out` still writes the full JSON, so nothing is lost,
   and that JSON is clearly a new artefact rather than a lookalike.

The brief's "change nothing else" governs the sweep computation; the CSV schema
does not exist in the original at all, so this is a choice about a new artefact,
not a change to an existing one. Flagging it rather than deciding silently.

#### 🟡 Reported, not resolved silently: how cy_ref/cz_ref are obtained

The brief asks for the reference "projected through the same p_far/u/up used for
the prediction, NOT joined from another file". **A literal re-projection is not
possible**, and the reason is structural:

<details><summary>Diagnostic: crossing_classification.csv holds no 3D reference point</summary>

```
head -1 results/prediction/01_crossing_plane_setup/crossing_classification.csv
 1 registration   5 crossing_Y      9 duration_ms    13 n_inliers
 2 session        6 crossing_Z     10 elevation_deg  14 n_points
 3 flight_id      7 crossing_speed 11 speed_m_s      15 edge_dist
 4 cls            8 crossing_vel_xyz 12 flag_reason
```

`crossing_vel_xyz` is a **velocity**. There is no 3D crossing POSITION column,
so there is nothing to re-project.
</details>

What is stored instead: `crossing_Y`/`crossing_Z` are **already plane
coordinates**, produced by `crossing_plane_classification.build_geometry` — the
same frozen function this sweep imports (line 87) and calls (line 452) to build
`geo["p_far"], geo["u"], geo["up"]`. So they are already in the identical basis;
the projection has simply been done once, upstream, by the same code.

They are also the exact two values the original's `position_error_mm` is measured
against (line 411), so persisting them cannot introduce a mismatch between the
error and the coordinates it came from.

**Consequence for the verification gate, stated plainly:** because
`position_error_mm = hypot(cy_own - crossing_Y, cz_own - crossing_Z)` by
construction, the gate does not independently test the reference side. What it
DOES test is the prediction side end to end — that the laptop reproduces the Pi's
`cy_own`/`cz_own` closely enough that the recomputed magnitude matches the Pi's
stored one. That is the real question here, and the gate answers it.

---

### [02:18] Step 4 — running the sweep on the laptop

**Run complete.** 107/107 flights, exit code 0.

```
  107/107 flights done (956.2s elapsed, 8.94s/flight)
Wrote results/regenerate_figures/04_zone_classification/pipeline_sweep_positions.json
Wrote results\regenerate_figures\04_zone_classification\pipeline_sweep_positions.csv  (2568 rows)
```

The `956.2s` and `8.94s/flight` above are **wall-clock progress reporting for the
laptop run, not a measurement of anything**, and like every other timing from
this run they are void. Quoted only to evidence the run finished.

---

### [02:36] Step 5 — VERIFICATION GATE — ✅ PASS

**Summary: 2481 rows compared, 100.00% match within 1.0 mm, 0 failures. No row
list to report because no row fails.**

| check | result |
|---|--:|
| rows in new CSV | **2568** |
| unique (session, flight, T_ms) keys, new / old | 2568 / 2568 |
| keys in Pi but not laptop | **0** |
| keys in laptop but not Pi | **0** |
| flights in Pi but not laptop | **0** |
| rows compared (values on both sides) | **2481** |
| matching within **1e-6 mm** | 275 (11.08%) |
| matching within **1.0 mm** | **2481 (100.00%)** |
| **FAILING the 1.0 mm gate** | **0** |
| blank on both sides (fit_failed) | 87 |
| blank on one side only | 0 |
| total accounted for | 2568 |

**Every row failing the 1.0 mm gate: none.** The list required by the brief is
empty.

<details><summary>Full gate output</summary>

```
new (laptop) : results\regenerate_figures\04_zone_classification\pipeline_sweep_positions.csv  rows=2568
old (Pi)     : results\pi_benchmarking\02_pi_pipeline_sweep_parallel_detection\pipeline_sweep_raw.csv  rows=2568
unique keys  : new=2568  old=2568

keys in Pi but not in laptop : 0
keys in laptop but not in Pi : 0

flights in Pi but not in laptop: 0

==========================================================================
VERIFICATION GATE
==========================================================================
  rows compared (both sides have values) : 2481
  matching within 1e-06 mm              : 275   (11.08%)
  matching within 1 mm                : 2481   (100.00%)
  FAILING the 1 mm gate              : 0

  rows blank on BOTH sides (fit_failed)  : 87
  blank on Pi, present on laptop         : 0
  present on Pi, blank on laptop         : 0
  total rows accounted for               : 2568

  no row fails the 1 mm gate

  delta distribution (mm): min 9.004e-11  median 7.915e-06  p95 2.033e-04
                           p99 6.679e-04  max 1.357e-02
```

Match key is `(session, flight, T_ms)`, not `(flight, T_ms)` — 32 flight ids
exist in both sessions and a bare id would mis-pair them.
</details>

#### 🟡 The 1e-6 tier behaved differently from the brief's expectation — reported, not glossed

The brief anticipated "up to 10 rows failing the 1e-6 gate but passing the 1.0 mm
gate (floating point)". The actual split is the other way round: **2206 rows fail
1e-6 and pass 1.0 mm**, with only 275 (11.08%) meeting 1e-6.

This is not a STOP condition — the STOP is on >10 rows failing the **1.0 mm**
gate, and zero do — but the expectation was wrong and the reason is worth
recording.

The deltas are minute: median **7.9e-06 mm** (8 picometres), p99 **6.7e-04 mm**,
max **1.36e-02 mm** (14 nanometres). Not CSV rounding — the Pi CSV stores
`position_error_mm` at full float repr (e.g. `281.06567501784946`). The cause is
genuine platform-level numerical divergence: `simulate_drag` integrates with
`solve_ivp` RK45 at `rtol=1e-8, atol=1e-6`, and the least-squares fits go through
platform BLAS/libm. Different builds land on trivially different last bits, which
the ODE amplifies slightly. A 1e-6 mm tolerance is simply tighter than
cross-platform float reproducibility of an adaptive ODE solve; 1.0 mm is the
meaningful bar and everything clears it by ~2 orders of magnitude.

#### Per-flight delta, and the "structurally fragile" expectation

The brief asked that the 7 known structurally-fragile flights be logged by name
if they showed larger deltas. **9 of 107 flights have any delta above 1e-3 mm**:

| flight | max delta (mm) | median delta (mm) |
|---|--:|--:|
| `2026_07_21_gym/flight_82` | 1.357e-02 | 2.540e-05 |
| `2026_07_15_gym/flight_33` | 2.787e-03 | 7.220e-06 |
| `2026_07_21_gym/flight_122` | 2.251e-03 | 1.600e-04 |
| `2026_07_21_gym/flight_43` | 1.897e-03 | 2.253e-05 |
| `2026_07_21_gym/flight_76` | 1.630e-03 | 1.022e-05 |
| `2026_07_15_gym/flight_29` | 1.232e-03 | 1.570e-04 |
| `2026_07_21_gym/flight_16` | 1.212e-03 | 7.915e-06 |
| `2026_07_21_gym/flight_36` | 1.081e-03 | 1.068e-03 (n=24) |
| `2026_07_21_gym/flight_58` | 1.068e-03 | 1.324e-04 |

Listed by name as instructed. **All nine are still ~3 orders of magnitude inside
the 1.0 mm gate**, so none is treated as a success without reporting, and none
constitutes a failure. I have not attempted to match these against a specific
"7 fragile flights" list — no such list was supplied and I am not inferring one.

#### Column sanity — all four present and non-null

| column | blanks on `status=='ok'` rows | min (mm) | max (mm) |
|---|--:|--:|--:|
| `cy_own` | 0 | -1160.4 | 2329.7 |
| `cz_own` | 0 | -928.4 | 2958.3 |
| `cy_ref` | 0 | -361.4 | 2084.0 |
| `cz_ref` | 0 | 273.8 | 2917.6 |

NaN count: **0**. Values outside +/-10 m on any axis: **0**.

---

## 🔴 RESTATED: ALL TIMING FROM THIS RUN IS VOID

No timing column was written to the CSV, none was read by the gate, and none is
quoted anywhere in this log as a measurement. Every latency figure in the report
remains the original Pi run's.

## Files created (both inside the two permitted paths)

| path | |
|---|---|
| `src/regen_2class/prediction_pipeline_sweep_positions.py` | the copy, 3 additive hunks |
| `src/regen_2class/verify_crossing_positions.py` | the gate |
| `results/regenerate_figures/04_zone_classification/pipeline_sweep_positions.csv` | 2568 rows |
| `results/regenerate_figures/04_zone_classification/pipeline_sweep_positions.json` | full run record |

`src/pi_benchmarking/prediction_pipeline_sweep_pi.py` untouched — mtime still
`2026-08-24 09:42`.

**Status: ✅ Complete. Stopping at the verification gate as instructed.**
