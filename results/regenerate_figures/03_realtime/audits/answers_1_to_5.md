# Explicit answers (1)-(5)

Generated 2026-08-24 20:42. Read-only.

## (1) Do 17.309 and 13.578 come from the same script, kernel and input flights?

**YES.** Evidence:

- Same file: both are fields of `results/pi_benchmarking/parallel_detect_checkpoint_20260804.json` (`/serial/median`, `/threaded/median`).
- Same script: that JSON is written by `src/pi_benchmarking/parallel_detect_checkpoint_pi.py`.
- Same loop, same frames: `measure_flight()` times SERIAL then THREADED inside one `for i in idx_range` body, on the same `back0/fwd0/back1/fwd1` arrays (checkpoint_pi.py:92-106). The docstring states this explicitly: "on the SAME frames (fair same-run comparison, not reusing an older serial number from a different run/date)".
- Same kernel: both call `detect_one` -> `compute_mask_rect_close`, whose close element is `MORPH_RECT` at line 42 and open element `MORPH_ELLIPSE` at line 39, sized 3x3 and 30x30 from the run's own recorded config.
- Same flights: one `/flights` list of 8 flights serves both, and both report n=488.

**Caveat worth carrying:** this pair is measured with the **RECT** close kernel, i.e. the post-fix detector. Neither number is comparable to the ellipse-era 84.05 ms figures without saying so.

## (2) Which stages are inside the 13.578 ms timer, in order?

Timer opens at `checkpoint_pi.py:101` and closes at `:106`. In order:

1. `threading.Thread(...)` constructed x2 (one per camera)
2. `th0.start()`, `th1.start()`
3. per thread, `detect_one()`:
   1. `cv2.min(back, fwd)`
   2. `cv2.threshold(..., 16, 255, THRESH_BINARY)`
   3. `getStructuringElement(MORPH_ELLIPSE, (3,3))` + `morphologyEx(MORPH_OPEN)`
   4. `getStructuringElement(MORPH_RECT, (30,30))` + `morphologyEx(MORPH_CLOSE)`
   5. `apply_exclusion(mask, cam_name)`
   6. `extract_candidates()` - `findContours`, area filter, `arcLength`, circularity filter, `moments`
4. `th0.join()`, `th1.join()`

**Explicitly NOT inside the timer:** PNG decode (`cv2.imread`, marked "untimed decode" at :75), the four `cv2.absdiff` calls that build back/fwd (:86-89, before `t0`), and everything downstream - trajectory filtering, pairing/sub-frame correction, triangulation, model fit.

So 13.578 ms is **mask + contour extraction for both cameras**, wall-clocked as a pair, and nothing else.

## (3) Is 4.77 ms the close call alone or the whole mask pipeline?

**The close call alone.** It is `/summary/morph_close_rect/median` = `4.767838999629021` ms, one of five separately timed substeps in the mask breakdown.

| substep | median (ms) |
|---|--:|
| threshold | 0.4985 |
| morph-open | 1.2050 |
| **morph-close (RECT)** | 4.7678 |
| exclusion | 0.9053 |
| **whole mask, RECT** | **7.3767** |

Whole mask with RECT is 7.38 ms, not 4.77. And the full per-frame detection with RECT (mask + contour extraction) is `9.7944` ms, from `rect_total_results_20260803.json` `/stats/median`.

## (4) Exact multiprocess median and p95

- median: **27.956629999913275 ms**
- p95: **28.287037000525743 ms**

To 3 dp: median 27.957 ms, p95 28.287 ms (n=488, mean 28.056, min 27.182, max 52.542). The '~28 ms' shorthand rounds the median up by 0.04 ms.

## (5) Ellipse-era per-frame-per-camera total, and 84.05 as a fraction

`timing_history.csv` carries **two** different per-frame-per-camera totals for the ellipse era. Both are given, because 'total' is ambiguous between them.

**(a) Mask-only total** - the mask-breakdown row, cam0, sum of the four substep medians:

- threshold 0.4985 + morph-open 1.2050 + morph-close(ELLIPSE) 84.0510 + exclusion 0.9053 = **86.6599 ms** (the CSV states 86.66 ms)
- 84.051 / 86.6599 = **96.99%**

**(b) Whole-detection total** - the Stage 1 row, "Detection: 88.66-89.80ms/frame/cam (mean 89.39ms)":

- 84.051 / 89.39 = **94.03%**

The CSV's own narrative uses reading (a) - it says morph-close is "~97% of the mask bottleneck (84.05ms of 86.66ms)". Reading (b) is the fraction of *all* detection work, which is the more conservative claim.

**Caution:** (a) is cam0-only and excludes contour extraction; (b) is a mean over a range across both cameras. They are not the same denominator and should not be mixed in one sentence.
