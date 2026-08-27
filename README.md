# Stereo Vision Ball Detection and Trajectory Prediction

MSc project. A two-camera Raspberry Pi rig that detects a volleyball in flight,
triangulates its 3D position, fits a drag-aware ballistic model in real time, and
predicts where the ball will cross a target plane — early enough to be useful.

The research question is not "can the position be computed" but **how early can a
usable prediction be made**, and what limits that: detection quality, frame rate,
observation window length, or the robust fit itself.

---

## ⚠️ Read this before cloning

**This repository does not run end-to-end from a clean clone.** The raw capture
data is not here and cannot be.

`data/` is gitignored — roughly 62 GB of session images, calibration captures and
detector contact sheets. It is not regenerable from anything in this repo, and it
does not belong on GitHub.

So:

| | |
|---|---|
| ✅ **Every result is committed** | Figures, CSVs and reports in `results/` are the actual outputs, not placeholders |
| ✅ **Every script is committed** | The code that produced each result is in `src/`, and `results/regenerate_figures/INDEX.md` maps output files back to the script that wrote them |
| ✅ **Aggregation/plotting scripts do run** | Anything reading a committed CSV under `results/` works from a clone |
| ❌ **Detection and calibration do not run** | They read images under `data/` |

If you clone this and a script fails on a missing path under `data/`, that is
expected and is not a bug. The intended way to read this repo is: **start from the
results, follow `INDEX.md` back to the producing script.**

---

## Setup

```bash
pip install -r requirements.txt
```

Python 3.9.12 was used throughout. `picamera2` is required only by the three
capture scripts that run on the Pi; every analysis script runs without it.

---

## Repository map

| Path | What it is |
|---|---|
| `src/` | All code, 152 files. See breakdown below. |
| `results/` | All derived outputs — figures, tables, reports. 64 MB, committed deliberately. |
| `calibration_outputs/` | Camera intrinsics and stereo extrinsics (`.npz`) used by the pipeline. |
| `claude/` | Development record — task briefs and work logs. See [Process record](#process-record). |
| `data/` | **Not in the repo.** Raw captures, gitignored. |

### `src/`

| Path | Purpose |
|---|---|
| `pi_code/` | **Runs on the Raspberry Pi, not the laptop.** Stereo capture (`capture_flights_stereo.py`), exposure sweep, and the camera sync startup test. These import `picamera2` and write to the Pi's own home directory, not into this repo. |
| `calibration/intrinsic/` | Per-camera fisheye calibration, coverage check, and the convergence study (how many board images are actually needed). |
| `calibration/extrinsic/` | Stereo extrinsic solve (`solve_extrinsic.py`). |
| `image_processing/01_background_median_subtraction/` | First detector generation — background subtraction. Superseded. |
| `image_processing/02_adjacent_frame_differencing/` | **The detector that is actually used.** `detector_core.py` is the shared implementation; the numbered scripts are the sweeps and dataset runs built on it. |
| `stereo/` | Triangulation, trajectory fitting (`trajectory_fit.py`), pairing and sync correction. |
| `registration/` | World-frame registration and the triangulation-precision validation. |
| `pi_benchmarking/` | On-Pi timing and the real-time prediction sweeps. Where the latency numbers come from. |
| `regen_2class/` | Analysis and figure generation for the report. Largest folder — one script per figure or audit. |

### `results/`

| Path | Files | What |
|---|--:|---|
| `regenerate_figures/` | 183 | Report figures and their source tables. **Start at `INDEX.md`.** |
| `detector_tuning/` | 690 | Detector parameter sweeps and detection-rate history. |
| `trajectory_fit_comparison/` | 60 | Model A/B/C comparison across flights. |
| `pi_benchmarking/` | 31 | Real Pi timing: per-stage latency, prediction sweeps. |
| `prediction/` | 24 | Crossing-position and outcome predictions. |
| `flight_binning/`, `sync_correction_validation*/` | 23 | Flight classification; sync-correction validation. |
| `tmp_pipeline_sweep_detections/` | 214 | Frozen per-camera detections. **Name is misleading** — see [Known warts](#known-warts). |

---

## Where to start reading

**`results/regenerate_figures/INDEX.md`** is the entry point. It maps every output
file to the script that produced it and to whatever reads it downstream, resolved
by grepping `src/` rather than by assumption.

**`results/regenerate_figures/CAPTIONS.md`** holds the caption text for each
figure, with every number computed from the data rather than typed, so caption and
figure cannot drift apart.

Note: `INDEX.md` was generated 2026-08-24 and does not yet cover the two newest
subfolders (`04_zone_classification`, `05_framerate_decimation`).

---

## The pipeline

1. **Capture** — two Pi cameras, 1456×1088, 60 fps, hardware-synced, side by side
   (`cam0` right, `cam1` left).
2. **Calibration** — fisheye intrinsics per camera; stereo extrinsics from a
   checkerboard. Convergence study in `src/calibration/intrinsic/convergence_test.py`
   establishes how many board images are actually needed.
3. **Detection** — three-frame differencing → threshold → morphological open/close
   → exclusion mask → contour filter on area and circularity → **largest surviving
   candidate by area**. One detection per frame per camera; the runner-up is
   discarded. Parameters in `results/detector_tuning/candidate_config.json`.
4. **Trajectory filter** — de-spikes detections that are kinematically impossible
   (>80 px/frame), removing static false positives such as light fixtures before
   they reach the fit.
5. **Pairing and triangulation** — cross-camera pairing with pixel-velocity sync
   correction, then triangulation to 3D.
6. **Fitting** — RANSAC over a fixed-gravity + quadratic-drag model, integrated
   with `solve_ivp`. Production settings: 3 iterations, minimum 8 inliers, fixed
   seed 42.
7. **Prediction** — forward-integrate to the target plane and report the crossing
   position.

### Flight classes

Flights are split at a 45° launch-elevation cut into **SHORT** (47 flights) and
**LONG** (60 flights). Most analyses are reported per class, because the two
behave differently.

Each class has its own real-time deadline. These are **not hardcoded** — they are
recomputed from the data on every call as
`floor(min(launch_to_crossing_ms) / 10) * 10`, anchored on the minimum so no flight
in a class can cross before its own deadline elapses. On the current dataset that
yields **490 ms** for SHORT and **1040 ms** for LONG.

### One convention that matters

Throughout the analysis, prediction error is measured against the **full-arc fit**
of the same flight, not against ground truth. It therefore measures **convergence**
— how quickly a short observation window reaches the answer the whole arc gives —
and not absolute accuracy. This distinction is maintained in the figure axis labels
and captions.

---

## Process record

`claude/` contains the development record: 31 task briefs (`prompts/`) and 39 work
logs (`claude_logs/`).

This work was done with AI assistance, and the folder is committed deliberately
rather than left out. The logs record what was tried, what failed, which diagnoses
turned out to be wrong and why, and the verification gates each analysis had to
pass before its numbers were used — for example the regression check requiring a
re-run to reproduce 2,481 existing values within 1 mm before any new result derived
from it was accepted.

It is a full audit trail of how each number in `results/` came to exist.

---

## Known warts

Left in place deliberately — this repo was submitted for assessment, and renaming
things would break path references across scripts for no analytical gain.

- **`results/tmp_pipeline_sweep_detections/`** is not temporary. It holds the frozen
  per-camera detections that the frame-rate decimation study reads. Three scripts
  reference the path.
- **`results/regenerate_figures/detection_improvement{,_v2,_v3}/`** are three
  generations of the same figure. `v3` is current; the earlier two are kept so the
  progression is visible.
- **Some analyses have `_02` suffixed outputs.** Scripts never overwrite: a rerun
  takes the next free numeric suffix. Where both exist, the higher suffix is the
  later run, and the work log for that date says which was used.
- **`figureA_margin_vs_cutoff.png`** is written by two different scripts to the same
  path — flagged in `INDEX.md`, not resolved.
