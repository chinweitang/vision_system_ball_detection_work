# Threading provenance audit

Read-only. No figures. Generated 2026-08-24 20:50 by `src/regen_2class/audit_threading_provenance_03.py`.

**Gate result: PASS** (20 of 20 checks pass).

Supersedes earlier run(s) of this same audit left in place by the
never-overwrite rule: `audit_threading_provenance.md`, `audit_threading_provenance_03.md`. Where they disagree with this
report, this one is current.

## Scope

The claim under audit is not about cv2/TBB internal threading. It is that
running the two cameras' detectors as two concurrent Python
`threading.Thread`s beats running them serially on the Pi 5, and that the
threaded per-pair detect cost sits below the 16.667 ms (60 fps) capture
cadence. That second half is load-bearing: the prediction-pipeline sweep's
latency model assumes a capture-bound regime, which holds only if threaded
detect fits inside cadence.

Gates applied by this script (its own, not inherited): **G1** every audited
number is locatable in the checkpoint JSON and that file is internally
consistent; **G2** every literal restating a checkpoint number agrees with
it; **G3** the build-time-derived block of `summary.txt` recomputes from the
raw sweep CSV.

## 1. Origin — the Step-1 checkpoint

Single source of every threading number in the repo:

    results/pi_benchmarking/parallel_detect_checkpoint_20260804.json

| Arm | n | median (ms) | p95 (ms) | mean (ms) | min | max |
|---|---:|---:|---:|---:|---:|---:|
| serial | 488 | 17.309 | 17.935 | 17.373 | 16.848 | 24.126 |
| threaded (2 Python threads) | 488 | 13.578 | 14.973 | 13.677 | 12.812 | 15.618 |
| multiprocess | 488 | 27.957 | 28.287 | 28.056 | 27.182 | 52.542 |

Recorded verdict: `winner = threaded`, `speedup_threaded = 1.2748`, `below_cadence = True`.

All three are recomputable from the file's own medians, and all three
agree: speedup = 17.309389 / 13.577648 = **1.2748**; argmin(median) = **threaded**; 13.578 ms < 16.667 ms = **True**.

Headroom, stated because the claim is a median but a dropped frame hinges
on the tail: median clears cadence by **3.089 ms**, p95 by **1.694 ms**.

Multiprocessing was measured and **lost** — 27.957 ms median, 1.62x *slower*
than serial. The threaded win is 1.27x, below the 1.7x bar the producing
script sets for clean parallelism, which is why the surrounding prose
attributes the shortfall to TBB thread-pool contention rather than to a
clean 2x.

## 2. Producer

`src/pi_benchmarking/parallel_detect_checkpoint_pi.py` — 2 `threading.Thread` construction(s), multiprocessing arm present
(`True`), serialises via `json.dump` (`True`). The script measures wall-clock
of the *pair* rather than summing per-thread self-reported times, which is
the right construction for this question.

## 3. Restatement — derived vs transcribed

Nothing outside the producer opens the checkpoint JSON. Every downstream
appearance of these numbers is a **literal**, unlinked to its source:

| Site | Quotes | Restates | JSON value | Rounds to | Agrees |
|---|---|---|---:|---:|:--:|
| `src/pi_benchmarking/prediction_pipeline_sweep_pi.py` L17 | `13.578` | `threaded.median` | 13.577648 | 13.578 | yes |
| `src/pi_benchmarking/prediction_pipeline_sweep_pi.py` L159 | `1.27` | `speedup_threaded` | 1.274844 | 1.27 | yes |
| `src/pi_benchmarking/prediction_pipeline_sweep_pi_vaxis.py` L132 | `1.27` | `speedup_threaded` | 1.274844 | 1.27 | yes |
| `src/stereo/pipeline_sweep_aggregate.py` L211 | `13.578` | `threaded.median` | 13.577648 | 13.578 | yes |
| `src/stereo/pipeline_sweep_aggregate.py` L211 | `14.973` | `threaded.p95` | 14.972666 | 14.973 | yes |
| `src/stereo/pipeline_sweep_aggregate.py` L212 | `1.27` | `speedup_threaded` | 1.274844 | 1.27 | yes |
| `results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/summary.txt` L11 | `13.578` | `threaded.median` | 13.577648 | 13.578 | yes |
| `results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/summary.txt` L11 | `14.973` | `threaded.p95` | 14.972666 | 14.973 | yes |
| `results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/summary.txt` L12 | `1.27` | `speedup_threaded` | 1.274844 | 1.27 | yes |

9 of 9 sites are TRANSCRIBED, 0 DERIVED.

Files under `src/` that name the checkpoint JSON: `src/regen_2class/audit_threading_provenance.py`, `src/regen_2class/build_iteration_rows.py`.

The sharpest case is `src/stereo/pipeline_sweep_aggregate.py`. Its `summary.txt` writer emits the whole
"Step 1 checkpoint (for reference)" block as hard-coded `f.write(...)`
string literals. The published `summary.txt` therefore *looks* like it
reports the checkpoint, but re-running the aggregation against a changed
checkpoint would reproduce the old numbers silently. Right now the
transcription is **accurate** — every literal matches the JSON to the
decimals it was written at — so this is a latent coupling failure, not a
present error.

## 4. What *is* derived at build time

The "Full-sweep detect diagnostics" block of `summary.txt` is genuinely
computed from `results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv`.
Recomputed here from the same file:

| Statistic | Recomputed | Present verbatim in summary.txt |
|---|---:|:--:|
| median | 13.707 ms | yes |
| p95 | 15.108 ms | yes |
| p99 | 15.404 ms | yes |
| max | 19.224 ms | yes |
| min | 12.781 ms | yes |
| sample count | 2481 | yes |

`src/stereo/pipeline_sweep_figures.py` also derives its own detect median from the raw CSV rather than
quoting the checkpoint (`True`), so the figure legend and the summary's
diagnostics block share a computed lineage that the Step-1 block does not.

Note the two are **different measurements** and differ slightly: the
checkpoint's threaded median is 13.578 ms over n=488 dedicated samples on 8
flights; the sweep's in-run detect median is 13.707 ms over n=2481 sampled
pairs on 107 flights. Neither is wrong; they are not interchangeable.

## 5. Population the claim was measured on

The checkpoint ran on **8 flights**. The sweep whose latency model it
licenses covers **107 flights**. Only **5 of the 8** checkpoint flights are
inside that population:

- `2026_07_21_gym/flight_17` — **not in sweep**
- `2026_07_21_gym/flight_63` — in sweep
- `2026_07_21_gym/flight_40` — in sweep
- `2026_07_21_gym/flight_59` — in sweep
- `2026_07_15_gym/flight_59` — **not in sweep**
- `2026_07_15_gym/flight_52` — in sweep
- `2026_07_15_gym/flight_45` — **not in sweep**
- `2026_07_15_gym/flight_15` — in sweep

This is not a defect — the sweep is restricted to crossing flights and the
checkpoint deliberately spanned a range of flight lengths — but the
threading result is a 8-flight measurement generalised to a 107-flight run,
and the report that uses it should say so.

## 6. Ledger and the 24 Aug `data/` → `results/` migration

`results/pi_benchmarking/history/timing_history.csv` carries **3 rows** and **none of them record the threading
checkpoint**:

- Stage 1 - end-to-end pipeline baseline (detect->pair+correct->triangulate->predict) on real Pi 5 hardware
- Stage 2 - Pi vs laptop correctness diff (not a timing measurement - included for completeness per request to b
- compute_mask breakdown - elliptical vs rectangular close-kernel A/B test

The threading result — the pass/fail hinge for the entire capture-bound
latency model — exists only as a JSON on disk and as prose in script
docstrings. It never entered the history ledger, so the ledger cannot be
used to find it.

Separately, the migration left every artifact pointer in that ledger stale:

| Row | Recorded path | State | Recoverable at |
|---:|---|---|---|
| 2 | `data/pi_benchmarking/stage1_results_20260803_1218.json` | **dangling** | `results/pi_benchmarking/stage1_results_20260803_1218.json` |
| 3 | `data/pi_benchmarking/stage2_correctness_diff.json` | **dangling** | `results/pi_benchmarking/stage2_correctness_diff.json` |
| 4 | `data/pi_benchmarking/mask_breakdown_results_20260803.json` | **dangling** | `results/pi_benchmarking/mask_breakdown_results_20260803.json` |

3 of 3 recorded paths dangle; 3 resolve one-for-one under `results/`.
The ledger was not rewritten when the tree moved.

## 7. Gate detail

| Gate | Check | Result |
|---|---|:--:|
| G1 | speedup_threaded == serial.median/threaded.median (recomputed 1.2748444355 vs recorded 1.2748444355) | pass |
| G1 | winner == argmin(median) (recomputed threaded vs recorded threaded) | pass |
| G1 | below_cadence == (threaded.median < cadence_ms) (recomputed True vs recorded True) | pass |
| G1 | cadence_ms == 1000/60 (16.666667) | pass |
| G1 | producer implements all three arms and serialises a result | pass |
| G2 | prediction_pipeline_sweep_pi.py quotes '13.578' for threaded.median; JSON rounds to 13.578 | pass |
| G2 | prediction_pipeline_sweep_pi.py quotes '1.27' for speedup_threaded; JSON rounds to 1.27 | pass |
| G2 | prediction_pipeline_sweep_pi_vaxis.py quotes '1.27' for speedup_threaded; JSON rounds to 1.27 | pass |
| G2 | pipeline_sweep_aggregate.py quotes '13.578' for threaded.median; JSON rounds to 13.578 | pass |
| G2 | pipeline_sweep_aggregate.py quotes '14.973' for threaded.p95; JSON rounds to 14.973 | pass |
| G2 | pipeline_sweep_aggregate.py quotes '1.27' for speedup_threaded; JSON rounds to 1.27 | pass |
| G2 | summary.txt quotes '13.578' for threaded.median; JSON rounds to 13.578 | pass |
| G2 | summary.txt quotes '14.973' for threaded.p95; JSON rounds to 14.973 | pass |
| G2 | summary.txt quotes '1.27' for speedup_threaded; JSON rounds to 1.27 | pass |
| G3 | summary.txt carries recomputed median=13.707 | pass |
| G3 | summary.txt carries recomputed p95=15.108 | pass |
| G3 | summary.txt carries recomputed p99=15.404 | pass |
| G3 | summary.txt carries recomputed max=19.224 | pass |
| G3 | summary.txt carries recomputed min=12.781 | pass |
| G3 | summary.txt carries recomputed sample count (n=2481 pairs sampled) | pass |

## 8. Relationship to the earlier audits in this directory

Two threading-adjacent audits already exist here and are **not** repeated:

- `audit_threading_provenance.md` — Pi-vs-laptop median comparison and the
  `ransac_ms` timed region; settled two quoted Pi medians against the raw CSV.
- `provenance_threading_morphology.md` + `answers_1_to_5.md` — resolved the
  morphology structuring elements from the producing scripts' ASTs and
  searched every CSV under `results/` for the audited values.

This run covers what neither did: the derivation chain of the threading
numbers themselves — who computes them, who merely repeats them, and
whether the repetition is still true.

