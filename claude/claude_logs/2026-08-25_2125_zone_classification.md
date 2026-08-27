# Work Log: Zone-classification convergence vs cell size

**Session:** 2026-08-25_2125
**Start:** 21:25:31
**Status:** ✅ Complete
**Duration:** [updating]

---

## Original Request

Measure zone-classification convergence against square cell size on the
5000 x 4000 mm crossing plane, SHORT at 400 ms and LONG at 850 ms, to find the
smallest cell classifiable for at least 94.2% of flights.

Write ONE script to `src/regen_2class/`, outputs to
`results/regenerate_figures/04_zone_classification/`. **Do not run it — the user
runs it.**

---

## Related sessions

| log | what it established |
|---|---|
| [2026-08-25_0158_zone_classification.md](2026-08-25_0158_zone_classification.md) | Phase 1 discovery. Found the original Pi sweep stores only `position_error_mm`, so per-cell assignment was unrecoverable. Blocked. |
| [2026-08-25_0212_persist_crossing_positions.md](2026-08-25_0212_persist_crossing_positions.md) | Laptop re-run persisting `cy_own/cz_own/cy_ref/cz_ref`. Verification gate: 2481 rows compared, **100% within 1.0 mm**, 0 failures. This produced the input for the present task. |

---

## 🔴 Terminology, held throughout

The reference is the **full-arc fixed-gravity-with-drag fit**, not ground truth.
Every number here measures **convergence toward that reference**. The word
"accuracy" is not used for the quantity in prose, in the figure, or in its axis
labels.

**One deliberate exception, flagged rather than hidden:** the success criteria
name a summary column `accuracy` literally. That column name is kept verbatim
because it is an explicit deliverable spec. Everywhere the script and log
*describe* the quantity, it is called the match fraction or convergence. The
figure's y-axis says "fraction in same cell as reference", not "accuracy".

---

## Path note

The brief cites `dev/claude_rules.md` and `dev/log_template.md`. **`dev/` does
not exist**; both files are in `claude/`. Read from there. Same flag as the two
preceding logs — recording it again rather than assuming it carries over.

---

## Input confirmed present

```
results/regenerate_figures/04_zone_classification/
  pipeline_sweep_positions.csv    455400 bytes   2026-08-25 21:22
  pipeline_sweep_positions.json  2104552 bytes   2026-08-25 21:22
```

Kernel is **RECT**, matching production — established in the Phase 1 log by
reading the call site of `prediction_pipeline_sweep_pi.py` (local
`compute_mask_rect_close`, `cv2.MORPH_RECT` close kernel, `cv2.MORPH_ELLIPSE`
open kernel).

---

## STEP 1 — design decisions, recorded before writing code

### Reference position is per-flight, not per-window

`cy_ref`/`cz_ref` originate in `crossing_classification.csv` and are constant
across all 24 windows of a flight. The Y-offset search therefore dedupes to one
row per flight before counting inclusion — otherwise each flight would be counted
24 times and the search would be unchanged in shape but meaningless in units.

Asserted in the script: every flight's `(cy_ref, cz_ref)` must be identical
across its rows.

### 🟡 Decision: predictions falling outside the envelope

Inclusion is decided on the reference only, as instructed. But a prediction can
land outside the 5000 x 4000 envelope even when its reference is inside.

Options considered:

1. **Clamp the predicted cell index into range.** Rejected. Clamping maps every
   outside prediction onto an edge cell, so a reference that happens to sit in
   that same edge cell would score as a MATCH. That manufactures agreement out of
   a prediction that missed the wall entirely — it would inflate the result at
   exactly the large-D end where edge cells are biggest.
2. **Record the raw out-of-range index and never match it.** Chosen. The
   predicted cell is computed with the same floor division and written to the raw
   CSV as-is, including negative or oversized indices, so the miss is visible.
   A prediction outside the envelope cannot equal an inside reference cell.

The reference index is clamped only for the exact upper-edge case
(`cy_ref == y0 + 5000` or `cz_ref == 4000`), where floor division would yield one
index past the last cell. That is a boundary artefact, not an out-of-envelope
point.

### Grid convention

- anchored at the bottom-left of the envelope: `y0 = chosen offset`, `z0 = 0`
- `col = floor((cy - y0) / D)`, `row = floor((cz - z0) / D)`
- `n_cols = ceil(5000 / D)`, `n_rows = ceil(4000 / D)`
- cells clipped at the top and right where D does not divide evenly — expected,
  logged, not worked around

### Y-offset search range

Derived from the data rather than hardcoded: offsets stepped by 10 mm across
`[min(cy_ref) - 5000, max(cy_ref) + 10]`, which is every offset for which the
5000 mm window could contain at least one reference. Ties broken by taking the
**smallest** offset, so the result is deterministic and reproducible.

---

## STEP 2 — writing the script

Status: in progress.

### [21:32] Input verified before writing

<details><summary>Diagnostic: schema and window availability</summary>

```
=== positions CSV header ===
 1 session   4 status      7 cy_own   10 cz_ref             13 cls_own
 2 flight    5 airborne    8 cz_own   11 position_error_mm  14 hit_miss_match
 3 T_ms      6 n_detected  9 cy_ref   12 velocity_error_mm_s 15 t_cross_own_ms

=== windows present ===
 [150,200,250,300,350,400,450,490,500,550,600,650,700,750,800,850,900,950,
  1000,1050,1100,1150,1200,1250]
 400: True   850: True
 flights: 107
 rows: 2568   ok: 2481
 ok rows at T=400: 107     at T=850: 107
```

**Learned:** all 107 flights have `status == ok` at BOTH operating windows, so no
flight is lost to a fit failure at 400 or 850 ms. The 87 non-ok rows sit at other
windows and never enter this analysis.
</details>

---

### [21:40] Script written — `src/regen_2class/zone_classification.py`

376 lines, one file. **Not executed** — the brief reserves the run for the user.
Static checks only:

```
  syntax OK  ( 376 lines )
```

<details><summary>Static runtime estimate (computed from the input, script not run)</summary>

```
  cy_ref range      : -361.4 .. 2084.0 mm
  offset grid       : -5370 .. 2100, 748 offsets x 107 flights = 80,036 checks
  cell sweep        : 2 classes x 11 sizes x ~107 flights = ~2,354 rows
  -> well under 1 minute
```

Comfortably inside the "under 1 minute" expectation and nowhere near the 2-minute
stop threshold.
</details>

**Output directory currently holds only the two inputs**, so no output collides:

```
pipeline_sweep_positions.csv
pipeline_sweep_positions.json
```

Every output nonetheless goes through `next_free()`, which takes the next numeric
suffix rather than overwriting, per the no-overwrite rule.

#### Gates the script enforces, in order

| gate | STOP condition |
|---|---|
| windows | 400 ms or 850 ms absent |
| join | any flight not joining to a class; flight count != 107; counts != SHORT 47 / LONG 60 |
| coordinates | any of the four position columns NaN, blank, or outside +/-10 m |
| reference constancy | a flight whose `(cy_ref, cz_ref)` varies across its windows |
| prediction present | an included flight with no prediction at its operating window |

The reference-constancy gate is not in the brief's list. Added because the whole
Y-offset search rests on the reference being one point per flight; if it ever
varied across windows the search would be silently meaningless rather than
visibly wrong. Logged here rather than added quietly.

#### What the script writes

| file | content |
|---|---|
| `zone_classification_raw.csv` | one row per (class, D, flight): flight id, class, window, D, ref (row,col), pred (row,col), match, and the four raw coordinates |
| `zone_classification_summary.csv` | one row per (class, D): grid shape, n included, n correct, `accuracy`, `clears_94_2` |
| `y_offset_search.csv` | `y_offset_mm`, `n_inside` across the full 10 mm grid |
| `crossing_error_percentiles.csv` | per class: n, median, p90, p95, max of the in-plane error magnitude |
| `figure_zone_classification.png` | white background, log x, markers per cell size, dashed line at 94.2%, axis labels in mm, **no caption burned in** |

The raw CSV carries the four coordinates alongside the cell indices deliberately:
any disputed match can be recomputed by hand from the row itself without going
back to the sweep.

---

## FIGURE CAPTION (text lives here, not in the image)

> Fraction of flights whose predicted crossing position falls in the same square
> cell as the reference position, against cell side length, on a 5000 x 4000 mm
> crossing plane. SHORT is evaluated at a 400 ms observation window and LONG at
> 850 ms. The grid is anchored at the bottom-left corner of the envelope and
> cells are clipped where the side length does not divide the envelope evenly.
> Inclusion in the denominator is decided on the reference position alone; the
> Y offset of the envelope was chosen to maximise the number of the 107 flights
> whose reference falls inside it, and flights whose reference falls outside are
> excluded. The dashed line marks 94.2%.
>
> **The reference is the full-arc fixed-gravity-with-drag fit, not ground truth.
> This figure therefore measures convergence toward that reference, not accuracy
> against ground truth.** Zone size here is limited by end-to-end crossing-position
> spread, not by calibration precision: triangulation precision is ~3.25 mm RMS
> overall, roughly three orders of magnitude tighter than the crossing spread, so
> it is not the binding term.

---

### Awaiting the run

The three log statements the brief requires — the Y offset chosen and flights
gained over zero, the per-class excluded counts, and the smallest D clearing
94.2% per class — are all printed by the script and will be appended here once
the user runs it. They cannot be stated in advance without executing the script,
which is out of scope.

**Status: script complete, not run.**

---

## [21:58] Edit — column rename + two reporting additions

Script grew 376 -> 478 lines. Static syntax check: **OK**. Not run.

### 1. Column rename `accuracy` -> `match_fraction`

| line | before -> after |
|---|---|
| 9-11 | docstring: was "carries a column literally named `accuracy` because the deliverable spec names it so" -> now states the column IS `match_fraction` and why it is deliberately not accuracy |
| 298-300 | summary row key `accuracy=` -> `match_fraction=`; adjacent comment reworded |
| 443 | figure reads `r["accuracy"]` -> `r["match_fraction"]` |
| 447 | comment "Deliberately not \"accuracy\"" -> "Not \"accuracy\"" |

The rename was unambiguous — only two code references existed (the write at 300
and the read at 443), so no STOP.

The y-axis label already read "fraction in same cell as reference" and needed no
change. Four mentions of the word remain in the file; **none is a column name,
dict key, print label or axis label** — they are the docstring explaining the
choice, the runtime disclaimer at line 116 ("...not accuracy against ground
truth"), and two comments. Removing the disclaimer would weaken the terminology
statement, so it stays.

### 2a. Y-offset position within the searched range

Added after the existing offset printout. Prints range endpoints, span, winning
offset, position as a fraction of the range, and distance to each endpoint. If
either distance is <= 100 mm it prints the required warning that references span
more than 5000 mm in Y and no window captures all of them.

### 2b. Structurally-fragile flights at the smallest passing D

Added after the smallest-D block. Resolves the seven names against the joined
data's `(session, flight)` keys, handling both the bare and session-qualified
forms given, then prints per class at that class's smallest passing D: match
status plus distance to the nearest cell boundary in Y and Z, for both the
reference and the prediction.

**🟡 Three of the seven names do not resolve, and the script reports each rather
than contributing zero rows silently:**

| name as given | in the data |
|---|---|
| `flight_121`, `flight_122`, `flight_45` | resolve uniquely to `2026_07_21_gym` |
| `2026_07_21_gym/flight_125` | resolves as given |
| `2026_07_21_gym/flight_22` | **not present as given** — `flight_22` exists only in `2026_07_15_gym` among the 107 |
| `flight_38`, `flight_46` | **not present** in any session |

This is not the STOP condition: the id *format* reconciles fine, and the
qualified/bare forms both parse. It is that two named flights are absent from the
107 and one is in the other session. The script prints an `UNRESOLVED` line for
each with the reason, so the run output will show it.

Nothing else changed. Clamping, the constant-reference gate, the offset search
range and tie-breaking, `next_free()`, the cell list, windows and envelope are
all untouched — verified by grep after editing.

**Status: edit complete, script not run.**

---

## [22:05] RUN COMPLETE

All four gates passed. All five outputs written, no suffixes needed (nothing
collided).

### The three required statements

**1. Y offset chosen, and flights gained over zero**

| | |
|---|--:|
| Y offset chosen | **-2910 mm** |
| flights inside at that offset | **107 of 107** |
| flights inside at offset 0 | 99 of 107 |
| **gained over offset 0** | **+8 flights** |

**2. Per-class excluded counts (reference outside the envelope)**

| class | excluded | included |
|---|--:|--:|
| SHORT | **0** | 47 |
| LONG | **0** | 60 |

No flight is excluded — the winning offset brings all 107 references inside the
envelope.

**3. Smallest D clearing 94.2%**

| class | smallest D clearing 94.2% |
|---|--:|
| SHORT (400 ms) | **2500 mm** |
| LONG (850 ms) | **1000 mm** |

Both classes have a passing size on the tested list; neither returns "none".

### Y-offset position within the searched range — no warning triggered

```
  searched range         : -5370 .. 2100 mm  (span 7470 mm)
  winning offset         : -2910 mm
  position within range  : 0.3293 (32.93% of the way from -5370 to 2100)
  distance to low end    : 2460 mm
  distance to high end   : 5010 mm
```

Both endpoint distances far exceed 100 mm, so the endpoint warning did **not**
fire.

### Cell sweep

| D (mm) | grid | SHORT | | LONG | |
|--:|---|--:|--:|--:|--:|
| 200 | 20x25 | 24/47 | 0.511 | 27/60 | 0.450 |
| 250 | 16x20 | 32/47 | 0.681 | 42/60 | 0.700 |
| 300 | 14x17 | 31/47 | 0.660 | 39/60 | 0.650 |
| 400 | 10x13 | 39/47 | 0.830 | 43/60 | 0.717 |
| 500 | 8x10 | 40/47 | 0.851 | 55/60 | 0.917 |
| 600 | 7x9 | 39/47 | 0.830 | 49/60 | 0.817 |
| 800 | 5x7 | 42/47 | 0.894 | 52/60 | 0.867 |
| 1000 | 4x5 | 43/47 | 0.915 | 58/60 | **0.967** |
| 1250 | 4x4 | 42/47 | 0.894 | 53/60 | 0.883 |
| 1670 | 3x3 | 43/47 | 0.915 | 56/60 | 0.933 |
| 2500 | 2x2 | 46/47 | **0.979** | 60/60 | **1.000** |

### Fragile flights — 4 of 7 resolved

```
  4 of 7 names resolved against the joined data
    resolved  flight_121                 -> 2026_07_21_gym/flight_121  cls=LONG  included=yes
    resolved  flight_122                 -> 2026_07_21_gym/flight_122  cls=LONG  included=yes
    resolved  flight_45                  -> 2026_07_21_gym/flight_45  cls=LONG  included=yes
    resolved  2026_07_21_gym/flight_125  -> 2026_07_21_gym/flight_125  cls=LONG  included=yes
```

All four are LONG. **SHORT:** none of the named flights is included in SHORT at
D=2500 mm.

**LONG, at D=1000 mm (grid 4x5):**

```
    flight                          match    ref dY    ref dZ   pred dY   pred dZ
    2026_07_21_gym/flight_125         yes     313.6     185.1     246.9     247.4
    2026_07_21_gym/flight_121         yes     461.2     386.7     497.0     431.4
    2026_07_21_gym/flight_122         yes     159.8      54.7     256.7     255.9
    2026_07_21_gym/flight_45          yes     225.6     184.8     165.2     195.5
```

Distances are mm to the nearest cell boundary on each axis, for the reference and
the prediction respectively. All four matched.

### The three UNRESOLVED lines, verbatim

```
  3 name(s) did NOT resolve - reported, not skipped:
    UNRESOLVED  flight_38                  not present          (no flight with this id)
    UNRESOLVED  flight_46                  not present          (no flight with this id)
    UNRESOLVED  2026_07_21_gym/flight_22   not present as given (flight id 'flight_22' exists in 2026_07_15_gym)
```

Not investigated — the user has reserved that as a separate provenance question.

### In-plane crossing-position error magnitude (convergence)

| class | n | median | p90 | p95 | max |
|---|--:|--:|--:|--:|--:|
| SHORT (400 ms) | 47 | 59.8939 | 158.9802 | 193.2956 | 276.7858 |
| LONG (850 ms) | 60 | 64.6785 | 119.6889 | 160.5596 | 223.2692 |

All values in mm.

### Outputs written

| file | rows |
|---|--:|
| `zone_classification_raw.csv` | 1177 |
| `zone_classification_summary.csv` | 22 |
| `y_offset_search.csv` | 748 |
| `crossing_error_percentiles.csv` | 2 |
| `figure_zone_classification.png` | — |

**Status: ✅ Complete.**

---

## [22:30] Edit — grid-phase averaging

478 -> 629 lines. Static syntax check: **OK**. Not run.

### Lines changed

| line(s) | before -> after |
|---|---|
| 17-30 | docstring: added the GRID PHASE rationale and the new output list |
| 62-77 | **new** `N_PHASE = 10` and `PHASE0_EXPECTED` — the previous run's per-(class, D) `n_correct` at phase (0,0), embedded as a regression check |
| 286-303 | **new** `count_matches(...)` helper: matches at one grid phase, optionally collecting per-flight detail |
| 305-352 | sweep rewritten: 100 phases per (class, D), origin offset by `(i*D/10, j*D/10)`. `raw_rows` is populated **only** when `i==j==0`, so the raw CSV stays phase 0 and is not multiplied by 100 |
| 354-357 | hard stop if any (class, D) yields other than 100 phase evaluations |
| 358-382 | summary row now carries mean / min / max / sd / phase0; `clears_94_2` judged on the **mean**, new `clears_94_2_worst` on the **min** |
| 386-410 | **new** phase-0 regression check against `PHASE0_EXPECTED`, run before any downstream reporting, hard-stopping on any mismatch |
| 412-460 | **new** four reports: smallest D clearing on mean; smallest clearing on min; widest min-max spread and where; monotonicity of the mean curve with each decrease and its size |
| 555 | added `write("zone_classification_by_phase.csv", phase_rows)` |
| 566-578 | figure: mean as the line, `fill_between(min, max)` as a shaded band per class |

### How phase 0 is guaranteed to reproduce

The existing `cell_index()` is **unchanged and still called**; only the `origin`
arguments differ. At phase (0,0) they reduce to `y0` and `0.0`, which are exactly
the previous arguments, so phase 0 is bit-identical by construction rather than
by coincidence. The embedded `PHASE0_EXPECTED` check then confirms it against the
previous run's actual counts at runtime and stops if it ever drifts.

### New output schema

`zone_classification_summary.csv` — one row per (class, D):
`cls, window_ms, D_mm, grid_rows, grid_cols, n_included, match_fraction_mean,
match_fraction_min, match_fraction_max, match_fraction_sd,
match_fraction_phase0, clears_94_2, clears_94_2_worst`

`zone_classification_by_phase.csv` — **new**, 100 rows per (class, D), 2200 total:
`cls, window_ms, D_mm, phase_i, phase_j, origin_y_mm, origin_z_mm, n_included,
n_correct, match_fraction`

`zone_classification_raw.csv` — unchanged schema, still phase 0 only.

Work: ~116,600 cell lookups. Seconds.

Envelope, Y-offset search, clamping, constant-reference gate, cell list, windows,
`next_free()` and the `match_fraction` naming all verified unchanged by grep.

**Status: edit complete, script not run.**

---

## [22:38] PHASE-AVERAGED RUN COMPLETE

All four gates passed. Six outputs written; the previous run's files were left in
place, so all but the new by-phase CSV took `_02` suffixes.

### Phase-0 regression check — ALL 22 PAIRS PASS

`ALL 22 (class, D) pairs reproduce phase 0 exactly.`

<details><summary>Full check, all 22 pairs</summary>

```
  OK  SHORT D=  200 mm  previous  24/47   now  24/47   phase0 fraction 0.510638
  OK  SHORT D=  250 mm  previous  32/47   now  32/47   phase0 fraction 0.680851
  OK  SHORT D=  300 mm  previous  31/47   now  31/47   phase0 fraction 0.659574
  OK  SHORT D=  400 mm  previous  39/47   now  39/47   phase0 fraction 0.829787
  OK  SHORT D=  500 mm  previous  40/47   now  40/47   phase0 fraction 0.851064
  OK  SHORT D=  600 mm  previous  39/47   now  39/47   phase0 fraction 0.829787
  OK  SHORT D=  800 mm  previous  42/47   now  42/47   phase0 fraction 0.893617
  OK  SHORT D= 1000 mm  previous  43/47   now  43/47   phase0 fraction 0.914894
  OK  SHORT D= 1250 mm  previous  42/47   now  42/47   phase0 fraction 0.893617
  OK  SHORT D= 1670 mm  previous  43/47   now  43/47   phase0 fraction 0.914894
  OK  SHORT D= 2500 mm  previous  46/47   now  46/47   phase0 fraction 0.978723
  OK  LONG  D=  200 mm  previous  27/60   now  27/60   phase0 fraction 0.450000
  OK  LONG  D=  250 mm  previous  42/60   now  42/60   phase0 fraction 0.700000
  OK  LONG  D=  300 mm  previous  39/60   now  39/60   phase0 fraction 0.650000
  OK  LONG  D=  400 mm  previous  43/60   now  43/60   phase0 fraction 0.716667
  OK  LONG  D=  500 mm  previous  55/60   now  55/60   phase0 fraction 0.916667
  OK  LONG  D=  600 mm  previous  49/60   now  49/60   phase0 fraction 0.816667
  OK  LONG  D=  800 mm  previous  52/60   now  52/60   phase0 fraction 0.866667
  OK  LONG  D= 1000 mm  previous  58/60   now  58/60   phase0 fraction 0.966667
  OK  LONG  D= 1250 mm  previous  53/60   now  53/60   phase0 fraction 0.883333
  OK  LONG  D= 1670 mm  previous  56/60   now  56/60   phase0 fraction 0.933333
  OK  LONG  D= 2500 mm  previous  60/60   now  60/60   phase0 fraction 1.000000
```
</details>

### The three original required statements

**1. Y offset chosen, and flights gained over zero** — unchanged from the previous
run, as expected: phase does not affect inclusion.

| | |
|---|--:|
| Y offset chosen | **-2910 mm** |
| flights inside | **107 of 107** |
| flights inside at offset 0 | 99 of 107 |
| **gained over offset 0** | **+8** |

**2. Per-class excluded counts**

| class | excluded | included |
|---|--:|--:|
| SHORT | **0** | 47 |
| LONG | **0** | 60 |

**3. Smallest D clearing 94.2%, judged on the MEAN**

| class | smallest D |
|---|--:|
| SHORT (400 ms) | **1670 mm** |
| LONG (850 ms) | **1670 mm** |

### The four new reports

**Smallest D whose MEAN clears 94.2%**

```
    SHORT 1670 mm
    LONG  1670 mm
```

**Smallest D whose MIN (worst phase) clears 94.2%**

```
    SHORT NONE on the tested list
    LONG  NONE on the tested list
```

**Widest min-max spread across all D**

```
    SHORT 0.277 at D=200 mm (min 0.446809, max 0.723404)
    LONG  0.267 at D=300 mm (min 0.566667, max 0.833333)
```

**Is the MEAN curve monotonically non-decreasing in D?**

```
    SHORT YES - non-decreasing at every step
    LONG  YES - non-decreasing at every step
```

### Cell sweep, phase-averaged

| D (mm) | grid | SHORT mean | SHORT [min, max] | sd | phase0 | LONG mean | LONG [min, max] | sd | phase0 |
|--:|---|--:|---|--:|--:|--:|---|--:|--:|
| 200 | 20x25 | 0.591 | [0.447, 0.723] | 0.054 | 0.511 | 0.597 | [0.450, 0.667] | 0.039 | 0.450 |
| 250 | 16x20 | 0.658 | [0.574, 0.766] | 0.052 | 0.681 | 0.665 | [0.567, 0.767] | 0.040 | 0.700 |
| 300 | 14x17 | 0.711 | [0.596, 0.830] | 0.055 | 0.660 | 0.705 | [0.567, 0.833] | 0.063 | 0.650 |
| 400 | 10x13 | 0.780 | [0.617, 0.872] | 0.055 | 0.830 | 0.776 | [0.667, 0.883] | 0.047 | 0.717 |
| 500 | 8x10 | 0.808 | [0.681, 0.915] | 0.054 | 0.851 | 0.816 | [0.700, 0.917] | 0.052 | 0.917 |
| 600 | 7x9 | 0.856 | [0.723, 0.957] | 0.048 | 0.830 | 0.848 | [0.767, 0.950] | 0.041 | 0.817 |
| 800 | 5x7 | 0.893 | [0.787, 0.957] | 0.034 | 0.894 | 0.881 | [0.800, 0.967] | 0.034 | 0.867 |
| 1000 | 4x5 | 0.897 | [0.809, 1.000] | 0.044 | 0.915 | 0.902 | [0.800, 0.983] | 0.038 | 0.967 |
| 1250 | 4x4 | 0.935 | [0.851, 1.000] | 0.034 | 0.894 | 0.930 | [0.850, 0.983] | 0.028 | 0.883 |
| 1670 | 3x3 | **0.952** | [0.872, 1.000] | 0.030 | 0.915 | **0.957** | [0.883, 1.000] | 0.026 | 0.933 |
| 2500 | 2x2 | **0.962** | [0.872, 1.000] | 0.029 | 0.979 | **0.967** | [0.883, 1.000] | 0.025 | 1.000 |

### Y-offset position within range — no warning triggered

```
  searched range         : -5370 .. 2100 mm  (span 7470 mm)
  winning offset         : -2910 mm
  position within range  : 0.3293 (32.93% of the way from -5370 to 2100)
  distance to low end    : 2460 mm
  distance to high end   : 5010 mm
```

Both endpoint distances far exceed 100 mm; the endpoint warning did **not** fire.

### Fragile flights — 4 of 7 resolved, all LONG

**SHORT:** none of the named flights is included in SHORT at D=1670 mm.

**LONG, at D=1670 mm (grid 3x3):**

```
    flight                          match    ref dY    ref dZ   pred dY   pred dZ
    2026_07_21_gym/flight_125         yes     346.4     814.9     413.1     752.6
    2026_07_21_gym/flight_121         yes     121.2      56.7     157.0     101.4
    2026_07_21_gym/flight_122         yes     819.8     724.7     753.3     744.1
    2026_07_21_gym/flight_45          yes     434.4     815.2     494.8     804.5
```

All four matched. Distances are mm to the nearest cell boundary on each axis, at
phase 0, for the reference and the prediction respectively.

### The three UNRESOLVED lines, verbatim

```
  3 name(s) did NOT resolve - reported, not skipped:
    UNRESOLVED  flight_38                  not present          (no flight with this id)
    UNRESOLVED  flight_46                  not present          (no flight with this id)
    UNRESOLVED  2026_07_21_gym/flight_22   not present as given (flight id 'flight_22' exists in 2026_07_15_gym)
```

Not investigated — reserved as a separate provenance question.

### Outputs written

| file | rows |
|---|--:|
| `zone_classification_raw_02.csv` | 1177 |
| `zone_classification_summary_02.csv` | 22 |
| `y_offset_search_02.csv` | 748 |
| `zone_classification_by_phase.csv` | **2200** |
| `crossing_error_percentiles_02.csv` | 2 |
| `figure_zone_classification_02.png` | — |

The previous run's files were left untouched.

**Status: ✅ Complete.**
