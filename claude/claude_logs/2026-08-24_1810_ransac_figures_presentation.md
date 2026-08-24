# Work Log: RANSAC figures - presentation pass

**Session:** 2026-08-24_1810
**Status:** BLOCKED on flight_22; p95 proceeding

Related: [2026-08-24_1747_ransac_effect_tail.md](2026-08-24_1747_ransac_effect_tail.md).
`ransac_effect_flight22.py` was NOT written in that session - it already existed
in the repo.

---

## Original Request

> Regenerate the two RANSAC figures with a consistent palette and no caption text
> drawn on the canvas. [...] "without RANSAC" is blue, "with RANSAC" is red, in
> both ransac_effect_p95.png and ransac_effect_flight22.png. In the flight_22
> figure the "fitted on hand-labelled points" series becomes a neutral grey or
> black dashed line [...] Do not use green in either figure. [...] Write the
> caption text that was previously baked in to a sibling .caption.txt file for
> each, with every number still computed by the existing caption_facts() path
> [...] STOP and report rather than guessing if either figure's colours are set
> in more than one place in its script.

---

## [18:10] Step 1 - two premise checks before touching anything

### (a) STOP FIRES: flight_22 sets colours in TWO places

`src/regen_2class/ransac_effect_flight22.py`:

```
 81:    ("label_plain", "fitted on hand-labelled points", "#2a78d6", "-"),
 82:    ("det_plain", "fitted on detected points, no RANSAC", "#e34948", "-"),
 83:    ("det_ransac", "fitted on detected points, with RANSAC", "#1baf7a", "-"),
...
256:    ax.axvspan(band[0], band[1], color="#e34948", alpha=0.10, zorder=1,
```

The `SERIES` table (81-83) is one source. Line 256 is a SECOND, independent
hardcoded literal for the hand-pickup band, which the table does not govern.

This is not pedantry, it changes the meaning of the figure. The band's `#e34948`
currently matches `det_plain` - the NO-RANSAC series. Under the requested palette
red moves to `det_ransac` (WITH RANSAC). Recolouring `SERIES` alone would leave
the band red while red now denotes the opposite series, making the band read as
belonging to the RANSAC line. There is no way to infer the intended band colour
from the brief, so per the instruction: stopping and reporting, not guessing.

### (b) `caption_facts()` does not exist in either script

```
$ grep -rn "caption_facts" src/
src/regen_2class/stage_timing_breakdown.py:283:def caption_facts(summary):
src/regen_2class/stage_timing_breakdown.py:381:    facts = caption_facts(summary)
```

It exists only in `stage_timing_breakdown.py`, an unrelated script. Both RANSAC
scripts build their captions as inline f-string lists at draw time
(`ransac_effect_tail.py` `cap = [...]` inside `draw()`;
`ransac_effect_flight22.py` `caption = [...]` at line 224).

Reading the intent as "the numbers must stay computed, not hardcoded" rather than
"call a function that exists", the fix is to EXTRACT that inline construction
into a real `caption_facts()` in each script and have both the on-canvas caption
(unchanged output) and the new `.caption.txt` render from it. Flagging rather
than silently inventing a function and calling it "existing".

### (c) p95 colours: single source, and ALREADY the requested palette

`ransac_effect_tail.py` sets series colour in exactly one place, line 202,
`color=COLOR[name]`, imported from `ransac_effect_pooled.py:79`:

```
76: S_PLAIN, S_RANSAC = "without RANSAC", "with RANSAC"
79: COLOR = {S_PLAIN: "#2a78d6", S_RANSAC: "#e34948"}
```

Blue = "without RANSAC", red = "with RANSAC" - exactly what was asked for. **No
colour change is needed for the p95 figure**, and none will be made. Every other
`color=` in that script is theme ink (`C.INK`, `C.INK2`, `C.SURF`), not series
colour. No green anywhere in it.

Note for the record: `COLOR` is shared with `ransac_effect_pooled.py`, so had a
change been needed it would also have moved `ransac_effect_pooled.png`, which was
not in scope. Moot, since no change is required.

### Decision

flight_22 is blocked on (a). The p95 work is independent of that answer - its
palette is already correct and the caption-off-canvas change does not touch the
band question - so it proceeds now. Statistic-identity is proved by snapshotting
the existing CSV before the re-run and diffing after.

## [18:09] Step 2 - correction: the infrastructure already exists

Revised (b) from Step 1. `src/regen_2class/clean_figures.py` exists, and BOTH
scripts already import it and already have the `--clean` branch wired:

- `ransac_effect_tail.py:52,215-216`
- `ransac_effect_flight22.py:59,269-270`

So no code change was needed for the caption half at all - it is a flag.

More importantly, this module already provides the no-drift guarantee the brief
asked `caption_facts()` to provide, and provides it more strongly. From its
docstring: the script keeps its single caption list, and in clean mode *that same
list object* is handed to `write_clean()` instead of being drawn. There is only
ever one list, so the text file cannot drift from the figure "not by discipline,
but because there is nothing to keep in sync". Every number in it
(`len(keys)`, `len(dropped)`, `BIN_MS`, `MIN_CELLS`, flight count) is computed
from the data at draw time, as required.

Building a separate `caption_facts()` would have ADDED a second place for the
text to live, weakening the guarantee. Not doing it.

## [18:09] Step 3 - p95 regenerated, all gates re-run

`python src/regen_2class/ransac_effect_tail.py --clean`

### Gates - all still pass, unchanged

```
KEY GATE PASS: both series carry the identical 9592 keys after exclusion
CROSS-CHECK PASS: per-bin surviving counts match the pooled run's n_paired
PLOTTED RANGE: 0-1500 ms (15 bins), all >= 100 cells
  EXCLUDED   1500-1600 ms  n=21 (below 100; reported, not hidden)
```

### STATISTIC-IDENTITY GATE: PASS, byte-for-byte

Snapshotted `ransac_effect_tail.csv` before the run and diffed after:

```
d570ad8c6e82faf73ef939e821962176  (before)
d570ad8c6e82faf73ef939e821962176  (after)
CSV: IDENTICAL
SUMMARY: IDENTICAL
```

Not "no meaningful difference" - the same MD5. No statistic moved by any amount.

### Palette: no change was needed

`ransac_effect_tail.py` was ALREADY blue = "without RANSAC", red = "with RANSAC"
(`COLOR` at `ransac_effect_pooled.py:79`). It already matched the requested
palette, so nothing was recoloured and no green exists in it. Confirmed visually
on the rendered clean PNG.

### Captioned versions preserved

`ransac_effect_p95.png` and `ransac_effect_tail.png` still carry their 17:50
mtimes - clean mode takes the other branch and never rewrites them.

### Outputs

```
ransac_effect_p95_clean.png    1980x1320 px @ 300 dpi = 6.60 x 4.40 in
ransac_effect_p95.caption.txt  2 lines
ransac_effect_tail_clean.png   1980x1320 px @ 300 dpi = 6.60 x 4.40 in
ransac_effect_tail.caption.txt 2 lines
```

**Width caveat to raise with the user**: `clean_figures.CLEAN_WIDTH_IN` defaults
to 6.6 in, documented there as "0.8 x A4 paper width (210 mm)" following
`step17_print_size_figures.py`. That is 0.8 of the PAPER width, not of LaTeX
`\textwidth`. A typical A4 `\textwidth` is ~6.27 in, so a true 0.8 textwidth is
~5.0 in. The module anticipates this and takes a `CLEAN_WIDTH_IN` env override.
Used the repo default rather than silently switching conventions.

## [18:12] flight_22 - NOT DONE, blocked on the colour STOP

See Step 1(a). Awaiting a decision on the hand-pickup band colour before any
recolour. No file under `results/regenerate_figures/ransac_effect_flight22/`
was touched, and `ransac_effect_flight22.py` was not modified.

## [18:16] Step 4 - NEW flight_22 figure (green now explicitly requested)

The user reversed the previous instruction: green was ruled out last turn (the
red/green pair is not CVD-validated on this machine, and the reference series was
to be neutral grey). This turn green is named explicitly, "no substitutions".
Treating that as the decision and proceeding. Recording the reversal here because
`common.py`'s palette notes claim CVD validation for the pairs it defines, and
red+green is NOT among the validated pairs - so this figure carries a colour
combination the rest of the figure set deliberately avoids.

New file, nothing overwritten: `src/regen_2class/ransac_effect_flight22_clean.py`.
Written as a SEPARATE script rather than an edit precisely because the original
sets colour in two places; a new file with one `PALETTE` dict removes the trap
instead of working around it.

### Resolved colours, printed before drawing (as requested)

```
fitted on hand-labelled points          #1baf7a  rgb(27,175,122)  -> green  (want green) OK   [common.BAND_COLOR["success"]]
fitted on detected points, no RANSAC    #2a78d6  rgb(42,120,214)  -> blue   (want blue ) OK   [ransac_effect_pooled.COLOR['without RANSAC']]
fitted on detected points, with RANSAC  #e34948  rgb(227,73,72)   -> red    (want red  ) OK   [ransac_effect_pooled.COLOR['with RANSAC']]
hand-pickup band (not a series)         #8a8a84  rgb(138,138,132) -> neutral              [common.MUTED]
PALETTE CHECK PASS - red/blue identical to the p95 panel (#2a78d6 / #e34948)
colour is set in 1 place in this script (PALETTE)
```

The check classifies each hex by its dominant RGB channel and asserts against the
intended name, so it tests the value actually bound to the artist, not the
variable it was read from. Red and blue are imported from
`ransac_effect_pooled.COLOR` - the same dict object the p95 panel draws from - so
they are the same colours by construction, not by matching strings by eye.

**Band colour, the one thing the brief did not specify**: red, blue and green are
all now bound to series, so reusing any for the band would make it read as that
series - the exact failure the original had (its band was red, matching the
no-RANSAC line). Drawn in `common.MUTED` grey and called out on the figure legend
as "hand-pickup frames 44-47".

### Gates - all pass

```
GATE 0 PASS: fit-frame reconstruction validated for all 87 windows
GATE 1 PASS: all three series share an identical x set (85 windows, 33.3..1498.7 ms)
GATE 2 PASS: 85 windows, 33.3..1498.7 ms as specified
GATE 3 PASS: hand-pickup band 699.4-749.3 ms (frames 44-47)
GATE 4 PASS: all 85 windows x 4 columns identical to the previous run, to the digit
```

GATE 0 is the ORIGINAL script's own `reconstruct_fit_frames()`, imported and
genuinely re-run rather than reimplemented. GATE 4 compares every plotted value
against the previous run's companion CSV field by field - 85 windows x
(N, window_ms, 3 error columns). Zero differences.

### caption_facts()

Created as a real function in the new script, since none existed anywhere in the
RANSAC scripts (flagged twice; only `stage_timing_breakdown.py` has one). It
returns a dict of computed values - window count, x span, band edges, hand-pickup
frames, median inter-frame interval, dropped N list, source paths - and
`caption_lines()` renders the text from that dict alone. No number in the caption
is typed.

Nice confirmation it is live: the caption now reports the flight's own median
inter-frame interval as 16.6520 ms, computed from the timestamps, against the
pipeline's nominal 16.652 constant - the original's caption asserted the two
"agree to about 6 microseconds over the longest window" as prose.

### Canvas

No caption, no footnote, nothing below the axes except the x-axis label (kept, as
instructed alongside the title, legend, log y and band). Caption written to
`ransac_effect_flight22_clean.caption.txt`, 8 lines.

### Size

3.30 x 4.40 in @ 300 dpi (990 x 1320 px). Width is half of
`clean_figures.CLEAN_WIDTH_IN` (6.6 in); height matches
`ransac_effect_p95_clean.png` exactly (both 1320 px tall) so the two panels align
when set side by side.

**Flag**: the p95 panel is still 6.6 in wide. Side by side the pair is 9.9 in, not
a matched two-column layout. If they are to sit as equal halves, p95 needs
re-rendering at 3.3 in too - `CLEAN_WIDTH_IN=3.3 python
src/regen_2class/ransac_effect_tail.py --clean` does it. Not done, as it was not
asked for and would rewrite the p95 clean PNG.

### Untouched

`ransac_effect_flight22.png` and `.csv` both still at their 17:53 mtimes.
`ransac_effect_flight22.py` not modified.

**Status: Complete.**

## [18:24] Step 5 - aspect ratio was wrong, fixed

User flagged the figure looked squashed. They were right and the cause was my
sizing decision in Step 4, not a rendering fault.

**The error**: I set width to half (3.3 in) but kept height at 4.4 in "to match
the p95 panel's height". Matching absolute height to a panel that is TWICE as
wide produces a portrait 0.75:1 box. p95 is 6.6 x 4.4 = landscape 1.5:1. The
flight_22 panel came out 3.3 x 4.4 = 0.75:1, squashing a chart that spans 1.5 s
on x into a tall narrow column and letting the legend dominate.

**The fix**: same 1.5:1 ASPECT as p95, not the same absolute height.
3.3 x 2.2 in @ 300 dpi (990 x 660 px). Font sizes scaled down to suit
(title 6.5, axis 6.0, tick 5.2, legend 4.8).

Second pass: the legend still sat on top of the no-RANSAC spike, so added 4x
headroom on the y limit and tightened legend spacing. **The y LIMIT moved; no
value did** - GATE 4 re-run after both changes and still passes on all 85 windows
x 4 columns.

All five gates re-run and passing after the resize.

### Correction to Step 4's "flag"

Step 4 said p95 should be re-rendered at 3.3 in wide to make a matched pair. With
the aspect fixed that advice is now wrong in the detail: the two panels share the
same 1.5:1 proportions, so p95 at 6.6 x 4.4 and flight_22 at 3.3 x 2.2 scale to
the same shape. If they are to be set as two equal half-width columns, p95 should
be re-rendered at 3.3 x 2.2 (`CLEAN_WIDTH_IN=3.3` plus a height override), which
would also bring its font sizes into line with this panel's. Still not done - not
asked for, and it would rewrite the p95 clean PNG.

### Untouched

`ransac_effect_flight22.png` / `.csv` still 17:53.

### Correction: "untouched" was verified the weak way

Noticed after the resize that the original `ransac_effect_flight22.png`/`.csv`
mtimes had moved 17:53 -> 18:19, which contradicts the "not touched" line the
script prints and the claim made in Step 4.

Checked properly, against the MD5 baseline captured before the first run:

```
baseline: 43daefce67de38882f7baf0020c55047  ransac_effect_flight22.png
current : 43daefce67de38882f7baf0020c55047  ransac_effect_flight22.png
baseline: 6e03d908b61cdbe5b702e030f4a9d2ac  ransac_effect_flight22.csv
current : 6e03d908b61cdbe5b702e030f4a9d2ac  ransac_effect_flight22.csv
```

**Content is byte-identical.** Nothing was modified. `ransac_effect_flight22_clean.py`
writes only `..._clean.png` and `..._clean.caption.txt`; it opens the original CSV
read-only as `PREV_CSV` for GATE 4 and never writes either original path.

The mtime change is external - this repo lives under OneDrive, which rewrites file
timestamps on sync. Lesson for this session's other "untouched" claims: mtime is
evidence of nothing on this machine, and the earlier mtime-based confirmations
(plain_drag_sweep, ransac_effect_pooled, the sweep CSVs) are weaker than they
looked. The MD5 checks used for `ransac_effect_tail.csv` and here are the real
ones. Where a file matters, hash it.

## [18:32] Step 6 - sized from the p95 panel's own constants

User: still looks wrong, just use the same ratio as `ransac_effect_p95_clean.png`.

The 3.3 x 2.2 render WAS the same 1.5:1 ratio, so ratio alone was not the
problem. What differed was everything that does not scale with the box: title,
tick labels, axis labels and a four-entry legend keep their point size, so at
half the linear dimensions they occupy twice the relative area and the plot
region ends up visibly squatter than p95's. Shrinking the fonts to compensate
(the 6.5/6.0/5.2/4.8 set) then made this panel's type smaller than the panel it
sits beside - wrong in the other direction.

**Fix**: render at the SAME SIZE and SAME TYPE SIZE as p95, and get half-width by
scaling in the document rather than by rendering smaller. The constants are now
IMPORTED from `ransac_effect_tail`, not retyped:

```python
from src.regen_2class.ransac_effect_tail import (
    PAGE_W_IN as P95_W_IN, PAGE_H_IN as P95_H_IN, DPI as P95_DPI,
    FS_TITLE as P95_FS_TITLE, FS_AXIS as P95_FS_AXIS,
    FS_TICK as P95_FS_TICK, FS_LEGEND as P95_FS_LEGEND,
)
PAGE_W_IN, PAGE_H_IN, DPI = P95_W_IN, P95_H_IN, P95_DPI
```

so the two panels cannot drift apart on size or typography.

Verified identical:

```
flight22_clean: (1980, 1320)  1.5000
p95_clean     : (1980, 1320)  1.5000
IDENTICAL SIZE: True
```

Also unwrapped the title back to one line (it was split for the narrow render and
fits easily at 6.6 in) and reduced the legend headroom from 4.0x to 2.2x, which
is enough at full height.

All gates re-run after every one of these changes; GATE 4 still passes on all 85
windows x 4 columns.

### Originals, checked by hash not mtime

```
43daefce67de38882f7baf0020c55047  ransac_effect_flight22.png
6e03d908b61cdbe5b702e030f4a9d2ac  ransac_effect_flight22.csv
```

Unchanged from the pre-run baseline.

**Status: Complete.**
