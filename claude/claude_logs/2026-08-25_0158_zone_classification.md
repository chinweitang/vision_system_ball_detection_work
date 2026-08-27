# Work Log: Zone-classification convergence vs cell size

**Session:** 2026-08-25_0158
**Start:** 01:58:00
**Status:** 🔄 In Progress — PHASE 1 (discovery only)
**Duration:** [updating]

---

## Original Request

Measure zone-classification convergence against square cell size on the
5000 x 4000 mm crossing plane, for SHORT and LONG at their operating windows
(SHORT 400 ms, LONG 850 ms), to find the smallest cell correctly classified for
at least 94.2% of flights.

Phase 1 is **discovery only** — locate inputs, report, STOP. No analysis code.

---

## Objective

Establish, from existing sweep outputs only, the smallest square zone on the
target wall that can be resolved given end-to-end crossing-position spread.

**Terminology, held throughout:** the reference is the full-arc
fixed-gravity-with-drag fit, so every number here measures **convergence toward
that reference**, not accuracy against ground truth. The word "accuracy" is not
used for this quantity in the log, the outputs or the figure caption. (The
`clears_94_2` column and the summary CSV's required `accuracy` column name are
fixed by the brief's success criteria and are kept verbatim as column names
only.)

---

## Path notes, recorded before starting

**1. `dev/` does not exist.** The brief cites `dev/claude_rules.md` and
`dev/log_template.md`. Neither path exists. Both files are in `claude/`:

```
claude/claude_rules.md   18977 bytes  Jul 23 18:06
claude/log_template.md   23883 bytes  Nov 24  2025
```

Read from there. Flagging rather than silently substituting.

**2. `data/` -> `results/` migration, 24 Aug.** Derived outputs moved from
`data/` to `results/` on 2026-08-24. Session capture folders stayed in `data/`.
All discovery below reports post-migration paths.

---

## PHASE 1 — Discovery

Status: starting.

### [02:01] Item 1 — per-flight per-window sweep — 🔴 BLOCKING

**Summary: the sweep exists, the reference position exists, but the PREDICTED
crossing position does not exist in any stored output. It is computed and then
discarded.**

<details><summary>Diagnostic: columns of the candidate sweep CSV</summary>

Command:
```
head -1 results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv
```
Output:
```
 1 session          7 n_detected        13 latency_feasible
 2 flight           8 n_ideal_cadence   14 last_pair_detect_ms
 3 bin              9 position_error_mm 15 triangulate_ms
 4 T_ms            10 velocity_error_mm_s 16 ransac_ms
 5 status          11 hit_miss_match    17 predict_ms
 6 airborne        12 latency_ms
```
2568 rows = 107 flights x 24 windows. Windows and row count are right.

**Learned:** it carries `position_error_mm` — a scalar magnitude — and no
position columns at all.
</details>

<details><summary>Diagnostic: the two full JSONs, and the per-axis velocity CSV</summary>

`pipeline_sweep_full_20260804.json`, `t_rows[0]` keys:
```
T_ms, airborne, n_detected, n_ideal_cadence, status, t_cross_own_ms,
last_pair_detect_ms, triangulate_ms, ransac_ms, predict_ms, latency_ms,
latency_feasible, position_error_mm, velocity_error_mm_s, cls_own, hit_miss_match
```

`pipeline_sweep_full_vaxis_20260805.json` adds only VELOCITY components:
```
... vx_own, vy_own, vz_own, vx_ref, vy_ref, vz_ref, err_vx, err_vy, err_vz
```

`figures2/velocity_by_axis_raw.csv` header: `vx_own, vy_own, vz_own, vx_ref,
vy_ref, vz_ref, err_vx, err_vy, err_vz, velocity_error_mm_s`.

**Learned:** the vaxis re-run decomposed VELOCITY per axis but not POSITION.
There is a per-axis velocity breakdown and no per-axis position breakdown.
</details>

<details><summary>Diagnostic: exhaustive scan of every CSV under results/</summary>

Scanned every CSV under `results/` smaller than 8 MB whose header contains
`T_ms` or `window`, looking for any of `pos_y`, `pos_z`, `y_own`, `z_own`,
`crossing_y`, `pred_y`, `py_own`:

```
(no matches)
```

**Learned:** no stored per-window predicted position anywhere in results/.
</details>

<details><summary>Root cause, quoted from source — prediction_pipeline_sweep_pi.py:402-426</summary>

```python
pos_own, vel_own = eval_pos_vel(params, predict_fn, t_cross_own)
predict_ms = perf_ms() - t0

p_far, u, up = geo["p_far"], geo["u"], geo["up"]
cy_own = float(np.dot(pos_own - p_far, u))
cz_own = float(np.dot(pos_own - p_far, up))
inside = (0.0 <= cy_own <= APERTURE_SIZE_MM) and (0.0 <= cz_own <= APERTURE_SIZE_MM)
cls_own = "HIT" if inside else "MISS_HIGH_WIDE"

position_error_mm = float(np.hypot(cy_own - ref_row["crossing_Y"], cz_own - ref_row["crossing_Z"]))
velocity_error_mm_s = float(np.linalg.norm(vel_own - ref_row["crossing_vel_xyz"]))
hit_miss_match = (cls_own == ref_row["cls"])
...
row.update(
    status="ok", t_cross_own_ms=t_cross_own * 1000.0,
    last_pair_detect_ms=last_pair_detect_ms,
    triangulate_ms=triangulate_ms, ransac_ms=ransac_ms, predict_ms=predict_ms,
    latency_ms=latency_ms, latency_feasible=bool(latency_ms <= 490.0),
    position_error_mm=position_error_mm, velocity_error_mm_s=velocity_error_mm_s,
    cls_own=cls_own, hit_miss_match=hit_miss_match,
)
```

`cy_own` and `cz_own` ARE the predicted crossing position in plane coordinates.
They are computed on lines 406-407, consumed on 411 and 413, and **never appear
in `row.update(...)`**. They are discarded when the loop iterates.
</details>

**Why this blocks zone classification.** Assigning a predicted point to a grid
cell requires its (Y, Z). What survives is `position_error_mm = hypot(dY, dZ)` —
one scalar for two unknowns. The direction of the error is unrecoverable, so the
predicted cell cannot be reconstructed at any cell size. This is not a precision
problem; the information is absent.

`cls_own` is also NOT a substitute: it is binary HIT / MISS_HIGH_WIDE against a
single aperture (`APERTURE_SIZE_MM`), not a cell index.

**Reference position, by contrast, EXISTS:**
`results/prediction/01_crossing_plane_setup/crossing_classification.csv`,
163 rows, columns `crossing_Y`, `crossing_Z`, `crossing_vel_xyz`, `cls`,
`elevation_deg`, `registration` — the full-arc fixed-gravity-with-drag fit.

### [02:03] Item 2 — SHORT/LONG assignment — ✅

| path | column | SHORT | LONG | flights |
|---|---|--:|--:|--:|
| `results/regenerate_figures/two_class_join.csv` | `cls2` | **47** | **60** | 107 |

Cross-checked: applying a 45 deg split to the same file's `elevation_deg` column
reproduces {SHORT 47, LONG 60} exactly. Counts match the required 47/60.

### [02:03] Item 3 — world-frame registration — ✅

Defined in `src/stereo/all_flights_common.py:35,42`; loaded at
`crossing_plane_classification.py:104` as
`world_frame_dir / f"{registration}_world_transform.npz"`.

| registration | flights | npz path |
|---|--:|---|
| `REG_21_1` | 60 | `data/2026_07_21_gym/flight_binning/world_frame_validation/registration1_world_transform.npz` |
| `REG_21_2` | 66 | `data/2026_07_21_gym/flight_binning/world_frame_validation/registration2_world_transform.npz` |
| `REG_15` | 37 | `data/2026_07_15_gym/flight_binning/world_frame_validation/registration_world_transform.npz` |

(Counts are over all 163 rows of `crossing_classification.csv`.) These are under
`data/` and were NOT migrated — the 24 Aug move covered derived results only.

Note `crossing_plane_classification.py:77`:
`SEPARATION_EXPECT_MM = 700.0  # Chin Wei confirmed ~700mm clicked, not the tape's true ~1m`
— the two clicked ground points are ~700 mm apart, and `p_near`/`p_far`/`u`/`up`
derive from them at lines 142-149.

### [02:04] Item 4 — kernel configuration — ✅ RECT

`src/pi_benchmarking/prediction_pipeline_sweep_pi.py`:
```
113: def compute_mask_rect_close(back, fwd, cam_name, diff_threshold, open_kernel, close_kernel):
118:     open_k  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_kernel, open_kernel))
121:     close_k = cv2.getStructuringElement(cv2.MORPH_RECT,    (close_kernel, close_kernel))
127:     mask = compute_mask_rect_close(back, fwd, cam_name, cfg["diff_threshold"], ...)
```
**Determined by:** reading the call site. The producer defines and calls a LOCAL
`compute_mask_rect_close`, not the shared `detector_core.compute_mask`. Close
kernel is **MORPH_RECT**; the open kernel stays MORPH_ELLIPSE.

Only one candidate sweep output exists, so no ambiguity to report under the
error-handling rule.

### [02:04] Windows check — ✅

24 windows: 150-1250 in 50 ms steps plus 490. **400 present: yes. 850 present:
yes.**

