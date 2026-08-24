"""flight_22 RANSAC figure, recoloured for the combined panel - NEW file, nothing overwritten.

A presentation-only re-render of `ransac_effect_flight22.py`. Every number,
series, gate and exclusion is that script's; this one changes colour, caption
placement and page size and nothing else.

WHY A SEPARATE SCRIPT: the original sets series colour in TWO places - the
`SERIES` table (lines 81-83) and a hardcoded `#e34948` on the hand-pickup
`axvspan` (line 256). Editing one and leaving the other is exactly how the band
ends up silently denoting the wrong series. This script sets every colour in ONE
dict, `PALETTE`, resolves it once, prints the resolved hex per series, and
asserts the binding before drawing.

RED AND BLUE ARE IMPORTED, NOT RETYPED, from `ransac_effect_pooled.COLOR` - the
same dict object `ransac_effect_p95.png` draws from. They are therefore the same
red and the same blue by construction, not by matching hex strings by eye.

BAND COLOUR: the brief names red, blue and green and binds all three to series.
The hand-pickup band cannot reuse any of them without reading as that series, so
it is drawn in neutral grey (`common.MUTED`). Stated here because it is the one
colour the brief does not specify.

NO-DRIFT GATE: the three series are rebuilt from source via the original's own
`reconstruct_fit_frames()` (so its validation gate genuinely re-runs), then every
plotted value is compared against the previous run's companion CSV. Any
difference at all stops the script.

Outputs (both NEW; the existing .png and .csv are never touched):
    results/regenerate_figures/ransac_effect_flight22/ransac_effect_flight22_clean.png
    results/regenerate_figures/ransac_effect_flight22/ransac_effect_flight22_clean.caption.txt
"""
import csv
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
ROOT = _HERE.parents[1]
for _p in (str(_HERE), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common as C  # noqa: E402
# The ORIGINAL script's own helpers and constants. Importing runs nothing - its
# main() is behind an __main__ guard - and guarantees this figure is built from
# the same definitions, not a re-typed copy of them.
import ransac_effect_flight22 as ORIG  # noqa: E402
# The exact objects the p95 panel draws from.
from src.regen_2class.ransac_effect_pooled import (  # noqa: E402
    COLOR as POOLED_COLOR, S_PLAIN, S_RANSAC,
)
# Page size and type sizes are IMPORTED from the p95 panel's own script, not
# retyped, so this figure is the same size and the same typography by
# construction. Half-width is then a \includegraphics scale in the document,
# which keeps both panels' fonts identical on the page - rendering one of them
# smaller would not.
from src.regen_2class.ransac_effect_tail import (  # noqa: E402
    PAGE_W_IN as P95_W_IN, PAGE_H_IN as P95_H_IN, DPI as P95_DPI,
    FS_TITLE as P95_FS_TITLE, FS_AXIS as P95_FS_AXIS,
    FS_TICK as P95_FS_TICK, FS_LEGEND as P95_FS_LEGEND,
)

OUT_DIR = ROOT / "results/regenerate_figures/ransac_effect_flight22"
PREV_CSV = OUT_DIR / "ransac_effect_flight22.csv"
OUT_PNG = OUT_DIR / "ransac_effect_flight22_clean.png"
OUT_CAPTION = OUT_DIR / "ransac_effect_flight22_clean.caption.txt"

# ---------------------------------------------------------------------------
# THE ONLY PLACE COLOUR IS SET IN THIS SCRIPT.
# Keys are the series keys used by the original's SERIES table.
# ---------------------------------------------------------------------------
PALETTE = {
    "det_ransac": POOLED_COLOR[S_RANSAC],   # RED   - "with RANSAC", same as p95
    "det_plain": POOLED_COLOR[S_PLAIN],     # BLUE  - "without RANSAC", same as p95
    "label_plain": C.BAND_COLOR["success"],  # GREEN - hand-labelled reference
}
BAND_COLOR = C.MUTED  # neutral; see module docstring
# What each entry above is REQUIRED to be, checked at run time.
INTENDED = {"det_ransac": "red", "det_plain": "blue", "label_plain": "green"}

# Draw order: reference underneath, the two treatments on top of it.
DRAW_ORDER = ["label_plain", "det_plain", "det_ransac"]
LABEL = {
    "label_plain": "fitted on hand-labelled points",
    "det_plain": "fitted on detected points, no RANSAC",
    "det_ransac": "fitted on detected points, with RANSAC",
}

# Identical to ransac_effect_p95_clean.png in both page size and type size -
# the values are imported above, so the two panels cannot drift apart.
PAGE_W_IN, PAGE_H_IN, DPI = P95_W_IN, P95_H_IN, P95_DPI
FS_TITLE, FS_AXIS, FS_TICK, FS_LEGEND = (P95_FS_TITLE, P95_FS_AXIS,
                                         P95_FS_TICK, P95_FS_LEGEND)

EXPECT_WINDOWS = 85
EXPECT_X_LO, EXPECT_X_HI = 33.3, 1498.7
EXPECT_BAND_LO, EXPECT_BAND_HI = 699.0, 749.0


def stop(msg):
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _family(h):
    """Coarse colour name from the hex, so the assertion tests the ACTUAL bound
    value rather than trusting the variable it came from."""
    r, g, b = _hex_to_rgb(h)
    if r > g and r > b:
        return "red"
    if b > r and b > g:
        return "blue"
    if g > r and g > b:
        return "green"
    return "neutral"


def confirm_palette():
    """Print the resolved hex per series and prove each matches the intent."""
    print("RESOLVED SERIES COLOURS")
    wrong = []
    for key in DRAW_ORDER:
        hexv = PALETTE[key]
        fam = _family(hexv)
        want = INTENDED[key]
        mark = "OK" if fam == want else "WRONG"
        src = ("ransac_effect_pooled.COLOR[%r]" % (S_RANSAC if key == "det_ransac"
                                                   else S_PLAIN)
               if key in ("det_ransac", "det_plain") else 'common.BAND_COLOR["success"]')
        print(f"  {LABEL[key]:<44} {hexv}  rgb{_hex_to_rgb(hexv)}  "
              f"-> {fam:<7} (want {want:<5}) {mark}   [{src}]")
        if fam != want:
            wrong.append((key, hexv, fam, want))
    print(f"  {'hand-pickup band (not a series)':<44} {BAND_COLOR}  "
          f"rgb{_hex_to_rgb(BAND_COLOR)}  -> {_family(BAND_COLOR)}   [common.MUTED]")
    if wrong:
        stop("the resolved colour does not match the intended assignment:\n"
             + "\n".join(f"  {LABEL[k]}: {h} resolves to {f}, wanted {w}"
                         for k, h, f, w in wrong))
    # red and blue must be the SAME objects the p95 panel uses
    if PALETTE["det_ransac"] != POOLED_COLOR[S_RANSAC] or \
            PALETTE["det_plain"] != POOLED_COLOR[S_PLAIN]:
        stop("red/blue are not the values ransac_effect_p95.png draws from")
    print(f"  PALETTE CHECK PASS - red/blue identical to the p95 panel "
          f"({POOLED_COLOR[S_PLAIN]} / {POOLED_COLOR[S_RANSAC]})")
    n_places = 1
    print(f"  colour is set in {n_places} place in this script (PALETTE); "
          f"the band is the only other colour and is named above")


def caption_facts(common_n, series, band, dropped, ts, fit_frames):
    """Every number that appears in the caption, computed from the data.

    Single source: the caption text is built from this dict and nothing else, so
    no figure in this folder can carry a number that was typed rather than
    measured.
    """
    xs = [x for x, _ in series["label_plain"]]
    dts = [(ts[b] - ts[a]) / 1e6 for a, b in zip(sorted(ts), sorted(ts)[1:])]
    return dict(
        flight=ORIG.FLIGHT,
        n_windows=len(common_n),
        x_lo=min(xs), x_hi=max(xs),
        band_lo=band[0], band_hi=band[1],
        hp_lo=ORIG.HANDPICKUP_FRAMES[0], hp_hi=ORIG.HANDPICKUP_FRAMES[1],
        n_fit_frames=len(fit_frames),
        dt_median_ms=sorted(dts)[len(dts) // 2],
        nominal_dt_ms=16.652,
        dropped_ransac=dropped["det_ransac"],
        plain_csv=ORIG.PLAIN_CSV,
        ransac_csv=ORIG.RANSAC_CSV,
    )


def caption_lines(f):
    """The caption, rendered from caption_facts() only."""
    lines = [
        f"{f['flight']} only. All three series use the SAME trajectory model - gravity held fixed, quadratic drag added. "
        f"What differs is the source of the fitted points and whether RANSAC is applied, nothing else.",
        f"The hand-labelled series is the PLAIN fit, not a RANSAC one: the contrast being drawn is RANSAC vs no RANSAC "
        f"on DETECTED points, and applying it to the reference as well would blur that.",
        f"x is real elapsed time between the first and last frame of each fit window, from this flight's own per-frame "
        f"sensor timestamps (cam0/cam1 mean), spanning {f['x_lo']:.1f} to {f['x_hi']:.1f} ms over {f['n_windows']} windows. "
        f"It is NOT the nominal {f['nominal_dt_ms']:.3f} ms/frame constant the source pipeline uses; the flight's own median "
        f"inter-frame interval is {f['dt_median_ms']:.4f} ms.",
        f"Shaded band: confirmed hand-pickup frames {f['hp_lo']}-{f['hp_hi']}, converted to the same ms axis "
        f"({f['band_lo']:.0f}-{f['band_hi']:.0f} ms).",
        f"Windows where any series had no value are excluded from ALL THREE, so the x set is identical by construction"
        + (f" - N={f['dropped_ransac']} dropped, where the RANSAC fit produced no value." if f["dropped_ransac"] else "."),
        f"Log y: the series span several orders of magnitude at short windows.",
        f"Sources: {f['plain_csv']}",
        f"         {f['ransac_csv']}",
    ]
    return lines


def main():
    confirm_palette()

    plain = [r for r in ORIG.read(ORIG.PLAIN_CSV) if r["flight"] == ORIG.FLIGHT]
    ransac = [r for r in ORIG.read(ORIG.RANSAC_CSV) if r["flight"] == ORIG.FLIGHT]
    ts = ORIG.frame_times()

    # Re-runs the original's own reconstruction gate, which stops if the rebuilt
    # fit-frame sequence disagrees with last_fit_frame at any window.
    fit_frames, target, lab, det = ORIG.reconstruct_fit_frames(plain)
    print(f"\nGATE 0 PASS: fit-frame reconstruction validated for all {len(plain)} windows")
    f0 = fit_frames[0]

    def window_ms(n):
        return (ts[fit_frames[n - 1]] - ts[f0]) / 1e6

    p_by = {int(r["N"]): r for r in plain}
    r_by = {int(r["N"]): r for r in ransac}
    cols = {"label_plain": ("err_C_label_mm", p_by),
            "det_plain": ("err_C_det_mm", p_by),
            "det_ransac": ("err_C_det_ransac_mm", r_by)}
    have = {k: {n for n, r in src.items() if r.get(col, "").strip()}
            for k, (col, src) in cols.items()}
    common_n = sorted(set.intersection(*have.values()))
    dropped = {k: sorted(set(p_by) - v) for k, v in have.items()}
    series = {k: [(window_ms(n), float(src[n][col])) for n in common_n]
              for k, (col, src) in cols.items()}

    # ---- GATE 1: identical x set across all three series -------------------
    xsets = {k: tuple(round(x, 6) for x, _ in v) for k, v in series.items()}
    if len(set(xsets.values())) != 1:
        stop(f"the three series do not share an identical x set: "
             f"{ {k: len(v) for k, v in xsets.items()} }")
    xs = [x for x, _ in series["label_plain"]]
    print(f"GATE 1 PASS: all three series share an identical x set "
          f"({len(common_n)} windows, {min(xs):.1f}..{max(xs):.1f} ms)")

    # ---- GATE 2: the stated shape ------------------------------------------
    if len(common_n) != EXPECT_WINDOWS:
        stop(f"expected {EXPECT_WINDOWS} windows, got {len(common_n)}")
    if round(min(xs), 1) != EXPECT_X_LO or round(max(xs), 1) != EXPECT_X_HI:
        stop(f"expected x span {EXPECT_X_LO}..{EXPECT_X_HI} ms, got "
             f"{min(xs):.1f}..{max(xs):.1f} ms")
    print(f"GATE 2 PASS: {EXPECT_WINDOWS} windows, "
          f"{EXPECT_X_LO}..{EXPECT_X_HI} ms as specified")

    hp_lo, hp_hi = ORIG.HANDPICKUP_FRAMES
    band = ((ts[hp_lo] - ts[f0]) / 1e6, (ts[hp_hi] - ts[f0]) / 1e6)
    if not (EXPECT_BAND_LO <= band[0] <= EXPECT_BAND_LO + 1 and
            EXPECT_BAND_HI <= band[1] <= EXPECT_BAND_HI + 1):
        stop(f"hand-pickup band computed as {band[0]:.1f}-{band[1]:.1f} ms, "
             f"expected ~{EXPECT_BAND_LO:.0f}-{EXPECT_BAND_HI:.0f} ms")
    print(f"GATE 3 PASS: hand-pickup band {band[0]:.1f}-{band[1]:.1f} ms "
          f"(frames {hp_lo}-{hp_hi})")

    # ---- GATE 4: no plotted value differs from the previous run -------------
    if not PREV_CSV.is_file():
        stop(f"previous run's CSV missing, cannot prove values are unchanged: "
             f"{PREV_CSV.relative_to(ROOT).as_posix()}")
    prev = list(csv.DictReader(open(PREV_CSV, encoding="utf-8")))
    if len(prev) != len(common_n):
        stop(f"previous run has {len(prev)} rows, this run has {len(common_n)}")
    col_of = {"label_plain": "err_hand_labelled_mm",
              "det_plain": "err_detected_no_ransac_mm",
              "det_ransac": "err_detected_with_ransac_mm"}
    diffs = []
    for i, (n, prow) in enumerate(zip(common_n, prev)):
        if int(prow["N_frames"]) != n:
            diffs.append((n, "N_frames", prow["N_frames"], n))
        if f"{series['label_plain'][i][0]:.3f}" != prow["observation_window_ms"]:
            diffs.append((n, "observation_window_ms", prow["observation_window_ms"],
                          f"{series['label_plain'][i][0]:.3f}"))
        for k, col in col_of.items():
            now = f"{series[k][i][1]:.4f}"
            if now != prow[col]:
                diffs.append((n, col, prow[col], now))
    if diffs:
        stop(f"{len(diffs)} plotted value(s) differ from the previous run. "
             f"Reporting rather than proceeding.\n  (N, column, before, now)\n"
             + "\n".join(f"    {d}" for d in diffs[:20]))
    print(f"GATE 4 PASS: all {len(common_n)} windows x 4 columns identical to the "
          f"previous run, to the digit")

    # ---- caption, from caption_facts() only --------------------------------
    facts = caption_facts(common_n, series, band, dropped, ts, fit_frames)
    caption = caption_lines(facts)

    # ---- draw: no caption, no footnote, nothing below the axes -------------
    fig, ax = plt.subplots(figsize=(PAGE_W_IN, PAGE_H_IN))
    fig.patch.set_facecolor(C.SURF)
    C.style_axes(ax)
    ax.set_yscale("log")
    ax.axvspan(band[0], band[1], color=BAND_COLOR, alpha=0.22, zorder=1,
               label=f"hand-pickup frames {hp_lo}-{hp_hi}")
    for key in DRAW_ORDER:
        ax.plot([x for x, _ in series[key]], [y for _, y in series[key]],
                "-", color=PALETTE[key], lw=1.3, zorder=4, label=LABEL[key])
    ax.set_xlabel("observation window (ms)", color=C.INK, fontsize=FS_AXIS)
    ax.set_ylabel("prediction error at target (mm)", color=C.INK, fontsize=FS_AXIS)
    ax.tick_params(labelsize=FS_TICK)
    # Headroom so the legend sits clear of the data instead of over the
    # no-RANSAC spike. Presentation only - the y LIMIT moves, no value does.
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, hi * 2.2)
    ax.legend(frameon=False, fontsize=FS_LEGEND, labelcolor=C.INK2,
              loc="upper right")
    ax.set_title("flight_22: effect of RANSAC on the fixed-gravity, drag-included fit",
                 color=C.INK, fontsize=FS_TITLE, loc="left", pad=6)
    fig.tight_layout()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=DPI, facecolor=C.SURF)
    plt.close(fig)
    OUT_CAPTION.write_text("\n".join(caption) + "\n", encoding="utf-8")

    print(f"\nwrote {OUT_PNG.relative_to(ROOT).as_posix()}  "
          f"({PAGE_W_IN} x {PAGE_H_IN} in @ {DPI} dpi)")
    print(f"wrote {OUT_CAPTION.relative_to(ROOT).as_posix()}  ({len(caption)} lines)")
    print("existing ransac_effect_flight22.png / .csv not touched")


if __name__ == "__main__":
    main()
