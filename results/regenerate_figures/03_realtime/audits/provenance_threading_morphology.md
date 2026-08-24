# Provenance audit - real-time threading and morphology numbers

Generated 2026-08-24 20:42. Read-only; no benchmark was re-run.

## STOP conditions

**FIRED - value not locatable in a CSV.** 8 of 8 audited values have no CSV cell equal to them: `serial_median`, `serial_p95`, `threaded_median`, `threaded_p95`, `multiprocess_median`, `multiprocess_p95`, `morph_close_ellipse_median`, `morph_close_rect_median`.

Every threading statistic lives in **JSON only** (`parallel_detect_checkpoint_20260804.json`), restated as prose in `02_pi_pipeline_sweep_parallel_detection/summary.txt`. Neither is a CSV. The apparent grep hits in `pipeline_sweep_raw.csv` are *different* per-pair measurements from the later full sweep that happen to share leading digits - they are not these statistics.

Call-site structuring elements: all resolved statically from the AST.

Q1 same-script test: **PASS** - serial and threaded come from one script and one run.

## Per-number provenance

| number | value (full precision) | source file | producing script | struct. element @ call site | kernel size | timing scope | n | machine |
|---|---|---|---|---|---|---|---|---|
| serial median 17.309 | `17.309388999827206` | `results/pi_benchmarking/parallel_detect_checkpoint_20260804.json` | `src/pi_benchmarking/parallel_detect_checkpoint_pi.py` | open `MORPH_ELLIPSE`, close **`MORPH_RECT`** (checkpoint_pi.py:39, :42) | open 3x3, close 30x30 | per **stereo pair** (cam0+cam1 wall-clocked together) | 488 | Raspberry Pi 5 (asserted in script docstring + timing_history notes; **not a recorded field**) |
| threaded median 13.578 | `13.577647999860346` | `results/pi_benchmarking/parallel_detect_checkpoint_20260804.json` | `src/pi_benchmarking/parallel_detect_checkpoint_pi.py` | open `MORPH_ELLIPSE`, close **`MORPH_RECT`** (checkpoint_pi.py:39, :42) | open 3x3, close 30x30 | per **stereo pair** (cam0+cam1 wall-clocked together) | 488 | Raspberry Pi 5 (asserted in script docstring + timing_history notes; **not a recorded field**) |
| threaded p95 14.973 | `14.972665999550372` | `results/pi_benchmarking/parallel_detect_checkpoint_20260804.json` | `src/pi_benchmarking/parallel_detect_checkpoint_pi.py` | open `MORPH_ELLIPSE`, close **`MORPH_RECT`** (checkpoint_pi.py:39, :42) | open 3x3, close 30x30 | per **stereo pair** (cam0+cam1 wall-clocked together) | 488 | Raspberry Pi 5 (asserted in script docstring + timing_history notes; **not a recorded field**) |
| multiprocess median ~28 | `27.956629999913275` | `results/pi_benchmarking/parallel_detect_checkpoint_20260804.json` | `src/pi_benchmarking/parallel_detect_checkpoint_pi.py` | open `MORPH_ELLIPSE`, close **`MORPH_RECT`** (checkpoint_pi.py:39, :42) | open 3x3, close 30x30 | per **stereo pair** (cam0+cam1 wall-clocked together) | 488 | Raspberry Pi 5 (asserted in script docstring + timing_history notes; **not a recorded field**) |
| n = 488 pairs | `488` | `results/pi_benchmarking/parallel_detect_checkpoint_20260804.json` | `src/pi_benchmarking/parallel_detect_checkpoint_pi.py` | as above | as above | per **stereo pair** (cam0+cam1 wall-clocked together) | 488 | Raspberry Pi 5 (asserted in script docstring + timing_history notes; **not a recorded field**) |
| morph-close ELLIPSE 84.05 | `84.05102000012994` | `results/pi_benchmarking/mask_breakdown_results_20260803.json` | `src/pi_benchmarking/benchmark_mask_breakdown_pi.py` | `MORPH_ELLIPSE` (close), resolved at the mask-breakdown call site | 30x30 | per **camera per frame** (cam0 only) | 448 | Raspberry Pi 5 (asserted in script docstring + timing_history notes; **not a recorded field**) |
| morph-close RECT 4.77 | `4.767838999629021` | `results/pi_benchmarking/mask_breakdown_results_20260803.json` | `src/pi_benchmarking/benchmark_mask_breakdown_pi.py` | `MORPH_RECT` (close), resolved at the mask-breakdown call site | 30x30 | per **camera per frame** (cam0 only) | 448 | Raspberry Pi 5 (asserted in script docstring + timing_history notes; **not a recorded field**) |

### Also present in a CSV, as prose

`results/pi_benchmarking/history/timing_history.csv` restates 84.051 / 4.768 / 86.66 inside its free-text `headline_numbers` column. That is a narrative restatement, not a numeric column, so it is not a machine-readable source; the JSON above is authoritative.

### 24 Aug migration note

`timing_history.csv`'s `artifacts` column still points at pre-migration `data/pi_benchmarking/...` paths. Those files now live under `results/pi_benchmarking/...`. Resolved against `results/` for this audit; the CSV itself was not modified.

### Sample-count reconciliation (488 vs 448)

Both runs use the **same 8 flights** (verified: True). The checkpoint reports n=488 pairs; the mask breakdown reports n=448. The difference is exactly 40 = 8 flights x 5 warmup pairs, which the mask breakdown discards (`n_warmup_pairs = 5`) and the checkpoint does not. They are the same pair population, not a typo of one another.

### Machine

No result JSON records a machine, host or platform field. 'Raspberry Pi 5' comes from `parallel_detect_checkpoint_pi.py`'s docstring ("RUNS ON THE PI") and `timing_history.csv`'s Stage 1 note ("real Pi 5 hardware"). **The machine is asserted in prose, not captured as data.**
