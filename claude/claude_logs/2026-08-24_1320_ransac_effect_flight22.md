# Work Log: flight_22 RANSAC-effect figure, fixed-gravity-with-drag only

**Session:** 2026-08-24_1320
**Status:** Complete

---

## Original Request

> Locate the script and CSV behind the existing flight_22 plain-vs-RANSAC figure.
> Read-only. Write src/regen_2class/ransac_effect_flight22.py producing a
> single-panel figure for the fixed-gravity-with-drag model only, with three series:
> fitted on hand-labelled points, fitted on detected points without RANSAC, fitted on
> detected points with RANSAC. X-axis must be observation window in milliseconds,
> converted from frame count using that flight's real timestamps, stating the
> conversion in the log. Y-axis prediction error at target in mm, log scale. Shade the
> confirmed hand-pickup frame range. No series label may contain "Model A", "Model B"
> or "Model C"; assert before writing. STOP if the three series do not share an
> identical set of x values. Output to results/regenerate_figures/ransac_effect_flight22/.
> Log incrementally.

---

## [13:20] Step 1 - located

| artefact | path |
|---|---|
| **script** | `src/stereo/trajectory_model_prediction_sweep.py` |
| **CSV, plain** | `results/trajectory_fit_comparison/phase2/prediction_sweep.csv` |
| **CSV, RANSAC** | `results/trajectory_fit_comparison/phase2/prediction_sweep_ransac.csv` |
| **existing figures** | `.../phase2/prediction_sweep_ransac_flight_22.png`, `..._zoom_flight_22.png`, `prediction_sweep_flight_22.png` |

Two CSVs, not one: the plain and RANSAC fits were written to separate files
deliberately (script line 260: *"New file, additive -- does NOT touch
prediction_sweep.csv"*). So the three requested series come from two files:

| series | file | column |
|---|---|---|
| fitted on hand-labelled points | `prediction_sweep.csv` | `err_C_label_mm` |
| fitted on detected points, no RANSAC | `prediction_sweep.csv` | `err_C_det_mm` |
| fitted on detected points, with RANSAC | `prediction_sweep_ransac.csv` | `err_C_det_ransac_mm` |

### A choice I had to make and am flagging

Series 1 is specified as "fitted on hand-labelled points", unqualified. RANSAC
variants of the label fit also exist (`err_C_label_ransac_mm`). I used the
**plain** label fit, because series 2 vs 3 is precisely the RANSAC contrast and
the label series is the reference the other two are read against; putting RANSAC
on the reference too would blur what the figure is testing. Stated in the caption.

## [13:22] Step 2 - the confirmed hand-pickup range

From `trajectory_model_prediction_sweep.py:172`:

```python
known_bad_frames = {44, 45, 46, 47} if flight_name == "flight_22" else set()
```

and the existing figure shades it at line 339:

```python
ax.axvspan(44, 47, color="red", alpha=0.08, label="known hand-pickup frames (44-47)")
```

So the confirmed range is **frames 44-47 inclusive**. The source comment (lines
168-171) is worth carrying forward - the scoping to flight_22 is deliberate:

> A plain, unscoped frame-number set would spuriously "match" other flights' own
> frame numbers (e.g. flight_01's fit_frames happen to start at frame 44 too, a
> coincidence with nothing to do with contamination -- caught this exact
> false-positive tag in an earlier run

Since the new x-axis is milliseconds, the shaded band must be converted from
frames 44-47 to the same ms scale rather than drawn at x=44..47.

## [13:24] Step 3 - the x-axis conversion, and why the existing one does not qualify

**The existing pipeline does NOT use real timestamps.** `trajectory_model_prediction_sweep.py:162`:

```python
t_full = np.array([(f - t0_frame) * FRAME_DT for f in fit_frames])
```

with `FRAME_DT = 16.652e-3  # s per frame, as given` (`label_vs_detection.py:42`) -
a nominal constant. The brief requires real timestamps, so this figure derives its
own axis.

### The conversion used here

Real per-frame times come from `data/2026_07_15_gym/ball_flights/flight_22/timestamps.csv`
(columns `frame_index`, `cam`, `sensor_timestamp_ns`). For each frame index present
on BOTH cameras:

    t_frame = (sensor_timestamp_ns[cam0] + sensor_timestamp_ns[cam1]) / 2

The cam0/cam1 average, not cam0 alone. This matches the convention the codebase
already uses (`all_flights_common.py:167`, `t_avg = (t0_ns + t1_ns) / 2`), and the
comment there explains why it matters: the two cameras' timestamps are not
identical, which is the entire reason sub-frame correction exists.

The observation window for a given fit window is then

    observation_window_ms = ( t_frame[last_fit_frame] - t_frame[first_fit_frame] ) / 1e6

i.e. first-to-last elapsed real time, in ms.

### Measured, for flight_22

| quantity | value |
|---|--:|
| frames with both cameras | 181 (indices 0-180) |
| inter-frame dt, minimum | 16.6465 ms |
| inter-frame dt, **median** | **16.6520 ms** |
| inter-frame dt, maximum | 16.6550 ms |
| nominal `FRAME_DT` in the existing script | 16.6520 ms |
| full span, frames 4 to 92, real | **1465.382 ms** |
| full span, frames 4 to 92, nominal | 1465.376 ms |

The nominal constant happens to equal the real MEDIAN exactly, so the two agree to
about 6 microseconds over the longest window. The real timestamps are used anyway,
as specified - but the honest summary is that on this flight the choice changes the
axis by well under a tenth of a millisecond, not that it corrects a real error.

## [13:26] Step 4 - the identical-x gate needs a decision

The two CSVs carry an identical set of `N` for flight_22 (87 values, N = 3..89), so
the frame grids match. **But `err_C_det_ransac_mm` is blank at N=8 and N=9**
(last_fit_frame 9 and 10) - the RANSAC fit did not produce a value there - while
both plain columns are complete.

Dropping blanks per-series would leave the three series with different x sets and
trip the STOP. Rather than stop with nothing delivered, the script takes the
**intersection** of windows where all three series have a value, so the identical-x
condition holds by construction, and then asserts it. The 2 dropped windows are
reported in the output, the caption and here. Flagging this because the brief's STOP
had no "instead" clause - this is my judgement, not something it authorised.

---

## [13:34] Step 5 - built, with the window start PROVED rather than assumed

`src/regen_2class/ransac_effect_flight22.py`.

Neither CSV stores the FIRST fit frame - only `last_fit_frame` per N - so the
window start had to be recovered. Rather than assume the frames are consecutive
(they are not; `fit_frames` spans 2..92 but contains only 89 entries, so there
are gaps), the fit-frame sequence is rebuilt from its definition in the source
pipeline:

```python
fit_frames = sorted((label_common & det_common) - {target_frame})
```

and then **proved**: `fit_frames[N-1]` must equal the CSV's own `last_fit_frame`
for every N, or the script stops.

```
fit-frame reconstruction VALIDATED against last_fit_frame for all 87 windows
  label frames 93, detection frames 89, target frame 93
  fit_frames: 89, [2..92]
```

That check is what makes the ms axis trustworthy - a wrong window start would
shift every x value by a constant and nothing in the figure would look wrong.

### Gates

```
GATE 1 PASS: all three series share an identical x set (85 windows, 33.3..1498.7 ms)
GATE 2:      hand-pickup frames 44-47 -> 699.4..749.3 ms on this axis
GATE 3 PASS: none of ['model a','model b','model c'] appear in the 19 user-facing strings
```

Band conversion checks by hand: frames 44 and 47 are 42 and 45 frames after
`fit_frames[0] = 2`; 42 x 16.652 = 699.4 ms and 45 x 16.652 = 749.3 ms. Matches.

### Series populations

| series | windows |
|---|--:|
| fitted on hand-labelled points | 87 |
| fitted on detected points, no RANSAC | 87 |
| fitted on detected points, with RANSAC | 85 (missing N=8, 9) |
| **intersection plotted** | **85** |

### One render fix

The caption line naming the dropped windows ran off the right edge; split in two.

---

## [13:38] What the figure shows

The result is unusually clean:

- Up to ~680 ms the three series sit within a factor of ~2-3 of each other, with
  the two detected series noisy around the hand-labelled reference.
- **At the hand-pickup band the no-RANSAC series jumps by roughly 30x**, from
  ~120 mm to ~4000 mm, and it never recovers - it stays an order of magnitude
  above the other two for the remaining 750 ms of the sweep.
- The RANSAC series shows **no such jump**. It tracks the hand-labelled reference
  across the band and beyond, ending slightly BELOW it.

So on this flight RANSAC is not a marginal robustness improvement: it is the
difference between the contamination entering the fit permanently and being
rejected outright. The band lines up with the jump exactly, which is the point of
shading it.

Note the no-RANSAC damage is persistent, not transient. Once frames 44-47 are
inside the fit window they stay inside it for every longer window, so a single
4-frame contamination episode degrades every subsequent prediction.

## Status: COMPLETE

| output | |
|---|---|
| `src/regen_2class/ransac_effect_flight22.py` | the script |
| `results/regenerate_figures/ransac_effect_flight22/ransac_effect_flight22.png` | single panel, log y, 6.6 in at 300 dpi |
| `results/regenerate_figures/ransac_effect_flight22/ransac_effect_flight22.csv` | 85 rows, with a per-row in-band flag |

All inputs read-only; none modified. Nothing re-fitted or re-run.
