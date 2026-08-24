"""Re-render of the two-class feasibility-margin figure. NO new analysis.

    margin_p95(t) = deadline(class) - t - latency_p95(t)

Reads exactly one existing CSV - results/regenerate_figures/two_class_join.csv,
the same JOIN_CSV that src/regen_2class/step9_figure_a_combined.py used to build
results/regenerate_figures/figureA_margin_vs_cutoff.png. Nothing here re-runs the
Pi sweep, detection, fitting or any outcome sweep; the join is opened read-only.

Differences from step 9, all of them presentational:
  - every vertical is gone: the four dotted threshold rules, their rotated
    labels, and the vertical gridlines. Grid is horizontal only.
  - the target-mode budget line is at -83 ms (100 ms perceptual window minus
    16.7 ms projector lag), not -84 ms / 16 ms. C.BUDGET_MS is deliberately NOT
    used, since it still carries the old -84.
  - the five-line caption block below the axes is gone, and so is the title. The
    caption is written to a sibling .txt and typeset in the document instead.

Unchanged from step 9: the data path, the class scheme, the min-anchored
deadlines recomputed from launch_to_crossing_ms, the p95 rule, the truncation of
each class line at its own maximum launch-to-crossing time, and the chaos-rally
actuation band (72-220 ms, nominal 135 ms) with its label text.

Run from the repository root:  python src/regen_2class/fig_margin_2class.py
"""
import csv
import math
import pathlib
import sys

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common as C

OUT_DIR = "results/regenerate_figures/03_realtime/figures"
OUT_STEM = "figure_margin_2class"
DPI = 300

# ---- horizontal references ----------------------------------------------
# Actuation band, chaos rally. Carried over verbatim from step 9: panel tilt
# moves for a 2 m x 2 m, 20 kg panel rotating about its centre line at 350 Nm
# output torque, triangular velocity profile, plus 20 ms lumped command and
# settling.
BAND_LO, BAND_NOMINAL, BAND_HI = 72.0, 135.0, 220.0
BAND_LABEL = ("chaos rally: actuation budget\n"
              "(2 deg = 72, 10 deg = 135, 30 deg = 220 ms)")

# Target-mode display budget. 100 ms perceptual window minus 16.7 ms projector
# lag. The projector figure is measured END TO END and already includes the frame
# period, so panel / quantisation / render terms are not added on top. Pi render
# and compositor latency is neglected.
BUDGET_MS = -83.0
DISPLAY_LABEL = ("target mode: display budget\n"
                 "(100 ms perceptual window minus 16.7 ms projector lag)")

BAND_FILL, BAND_EDGE, ZERO_LINE = "#8a8a84", "#6f6e69", "#d5d4cf"

# ---- gates ---------------------------------------------------------------
EXPECT_N = {"SHORT": 47, "LONG": 60}
EXPECT_DEADLINE = {"SHORT": 490.0, "LONG": 1040.0}
MARGIN_TOL_MS = 0.1
# A vertical rule would ink a contiguous column run spanning most of the axes.
# The tallest legitimate run is the actuation band fill, ~8 percent of the axes
# height, so 0.30 sits far above the noise and far below any real vertical.
VERTICAL_RUN_LIMIT = 0.30


class GateFailure(RuntimeError):
    """Raised when a stated stop condition trips. Nothing is written."""


def next_free(directory, stem, suffixes):
    """Smallest index whose every sibling path is still free, and those paths.

    Never overwrites: index 0 means the bare stem, thereafter _1, _2, ... The
    same index is used for every suffix so the PNG and its caption keep a
    matching stem.
    """
    d = pathlib.Path(directory)
    i = 0
    while True:
        name = stem if i == 0 else f"{stem}_{i}"
        paths = [d / (name + s) for s in suffixes]
        if not any(p.exists() for p in paths):
            return i, paths
        i += 1


def independent_margins(join_csv):
    """Recompute the whole margin grid straight from the source columns.

    Deliberately avoids common.py's helpers and its hand-rolled percentile,
    using csv.DictReader and numpy.percentile instead, so agreement with the
    plotted values is a real cross-check and not a restatement of one function.
    """
    with open(join_csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    per_flight = {(r["session"], r["flight"]):
                  (r["cls2"], float(r["launch_to_crossing_ms"])) for r in rows}
    durations = {c: [d for cls, d in per_flight.values() if cls == c]
                 for c in C.CLASSES}
    deadline = {c: math.floor(min(v) / 10.0) * 10.0 for c, v in durations.items()}
    windows = sorted({int(r["T_ms"]) for r in rows})

    margins = {}
    for c in C.CLASSES:
        margins[c] = []
        for w in windows:
            lat = [float(r["latency_ms"]) for r in rows
                   if r["cls2"] == c and int(r["T_ms"]) == w and r["status"] == "ok"]
            margins[c].append(deadline[c] - w - float(np.percentile(np.array(lat), 95.0)))
    return dict(n_of={c: len(v) for c, v in durations.items()},
                deadline=deadline,
                max_ltc={c: max(v) for c, v in durations.items()},
                windows=windows, margins=margins, n_rows=len(rows))


def assert_no_vertical_artists(ax):
    """No artist in the axes may be a vertical rule, and no x gridline may show."""
    bad = []
    for gl in ax.get_xgridlines():
        if gl.get_visible():
            bad.append("visible x gridline")
    for ln in ax.lines:
        xs = ln.get_xdata()
        if len(xs) > 1 and np.ptp(np.asarray(xs, dtype=float)) == 0.0:
            bad.append(f"vertical Line2D at x={xs[0]}")
    for txt in ax.texts:
        if float(txt.get_rotation()) % 180.0 != 0.0:
            bad.append(f"rotated text {txt.get_text()!r}")
    if bad:
        raise GateFailure("vertical artefacts present in the axes: " + "; ".join(bad))


def assert_no_vertical_pixels(png_path, ax_position):
    """Scan the rendered axes interior for a column-shaped ink run.

    Catches anything the artist walk cannot see - a stray rule baked in by a
    style, a spine drawn twice, a leftover annotation. Works on the saved file,
    which is the artefact the gate is actually about.
    """
    img = plt.imread(str(png_path))[:, :, :3]
    h, w = img.shape[:2]
    x0, y0, x1, y1 = ax_position  # figure fraction, origin bottom left
    # figure fraction -> row/col, with the image origin at the top
    c_lo, c_hi = int(round(x0 * w)), int(round(x1 * w))
    r_lo, r_hi = int(round((1.0 - y1) * h)), int(round((1.0 - y0) * h))
    pad = max(3, int(round(0.004 * w)))  # step over the spines
    interior = img[r_lo + pad:r_hi - pad, c_lo + pad:c_hi - pad]

    surf = np.array(matplotlib.colors.to_rgb(C.SURF))
    ink = np.abs(interior - surf).max(axis=2) > 0.02

    rows_n = ink.shape[0]
    worst_run, worst_col = 0, None
    for j in range(ink.shape[1]):
        run = best = 0
        for v in ink[:, j]:
            run = run + 1 if v else 0
            if run > best:
                best = run
        if best > worst_run:
            worst_run, worst_col = best, j
    frac = worst_run / float(rows_n)
    print(f"  vertical-pixel scan: axes interior {ink.shape[1]}x{rows_n} px, "
          f"longest contiguous ink column run = {worst_run} px "
          f"({frac:.3f} of axes height) at interior column {worst_col}")
    if frac > VERTICAL_RUN_LIMIT:
        raise GateFailure(
            f"vertical-line artefact in {png_path}: contiguous ink run of "
            f"{worst_run} px ({frac:.3f} of axes height) exceeds "
            f"{VERTICAL_RUN_LIMIT:.2f}")
    return frac


def main():
    print(f"data path (unchanged from step 9): {C.JOIN_CSV}")
    rows = C.load_join()
    windows = C.windows_of(rows)
    deadline = C.deadlines(rows)
    margins, _ = C.margin_p95(rows, windows)
    durations = C.class_durations(rows)
    n_of = {c: len(v) for c, v in durations.items()}
    max_ltc = {c: max(v) for c, v in durations.items()}

    # ---- gates on the inputs --------------------------------------------
    if n_of != EXPECT_N:
        raise GateFailure(f"class sizes are {n_of}, expected {EXPECT_N}")
    if deadline != EXPECT_DEADLINE:
        raise GateFailure(f"deadlines are {deadline}, expected {EXPECT_DEADLINE}")
    print(f"  class sizes {n_of}  [gate ok]")
    print(f"  deadlines   {deadline}  [gate ok]")
    print(f"  max launch-to-crossing { {c: round(v, 3) for c, v in max_ltc.items()} }")

    # ---- figure ----------------------------------------------------------
    fig, ax = plt.subplots(figsize=(11.0, 7.4))
    fig.patch.set_facecolor(C.SURF)
    C.style_axes(ax, grid_axis="y")  # horizontal grid only: no verticals

    ax.axhspan(BAND_LO, BAND_HI, color=BAND_FILL, alpha=0.15, lw=0, zorder=1)
    ax.axhline(BAND_NOMINAL, color=BAND_EDGE, lw=1.6, zorder=1)
    ax.axhline(0.0, color=ZERO_LINE, lw=1.0, zorder=1)
    ax.axhline(BUDGET_MS, color=C.MUTED, ls=(0, (5, 3)), lw=1.6, zorder=2)

    plotted = {}
    for c in C.CLASSES:
        pts = [(w, m) for w, m in zip(windows, margins[c]) if w <= max_ltc[c]]
        dropped = [w for w in windows if w > max_ltc[c]]
        print(f"  {c}: line stops at {pts[-1][0]} ms "
              f"(max launch-to-crossing {max_ltc[c]:.3f} ms); "
              f"windows past it, dropped: {dropped if dropped else 'none'}")
        plotted[c] = pts
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=C.CLASS_COLOR[c],
                lw=2.0, marker="o", ms=5, mec=C.SURF, mew=1.2, zorder=3,
                label=f"{c} (n={n_of[c]}, deadline={deadline[c]:.0f} ms)")

    lo, hi = ax.get_ylim()

    # Inline labels for the two annotated references. Positions carried over from
    # step 9, where they were placed to miss both data lines; the data, the axis
    # limits and the band are unchanged, so the clearances still hold.
    ax.annotate(BAND_LABEL, xy=(windows[0], BAND_NOMINAL),
                xytext=(290, BAND_NOMINAL - 6.0),
                color=BAND_EDGE, fontsize=7.4, ha="left", va="top", zorder=4)
    ax.annotate(DISPLAY_LABEL, xy=(windows[-1], BUDGET_MS),
                xytext=(windows[-1], BUDGET_MS + 0.012 * (hi - lo)),
                color=C.INK2, fontsize=8.2, ha="right", va="bottom", zorder=4)

    ax.set_ylim(lo, hi)
    ax.set_xlabel(C.X_LABEL, color=C.INK, fontsize=10.5)
    ax.set_ylabel("margin_p95 (ms)", color=C.INK, fontsize=10.5)
    # No title: the caption is written in the document, and a baked title would
    # duplicate it. The legend stays - it is the only thing naming the two lines.
    ax.legend(frameon=False, fontsize=9.5, labelcolor=C.INK2, loc="upper right")

    assert_no_vertical_artists(ax)
    fig.tight_layout()

    # ---- gate: plotted values vs an independent recomputation ------------
    ind = independent_margins(C.JOIN_CSV)
    if ind["n_of"] != EXPECT_N or ind["deadline"] != EXPECT_DEADLINE:
        raise GateFailure(f"independent pass disagrees on class sizes / deadlines: "
                          f"{ind['n_of']} {ind['deadline']}")
    worst = 0.0
    for ln in ax.lines:
        lbl = ln.get_label()
        if not any(lbl.startswith(c) for c in C.CLASSES):
            continue
        c = lbl.split(" ")[0]
        xy = ln.get_xydata()
        ref = dict(zip(ind["windows"], ind["margins"][c]))
        for x, y in xy:
            d = abs(y - ref[int(round(x))])
            worst = max(worst, d)
    print(f"  plotted vs independent recomputation: worst |diff| = {worst:.6f} ms "
          f"over {sum(len(v) for v in plotted.values())} grid points "
          f"(tolerance {MARGIN_TOL_MS} ms)")
    if worst > MARGIN_TOL_MS:
        raise GateFailure(f"plotted margins disagree with the source columns by "
                          f"{worst:.4f} ms, over the {MARGIN_TOL_MS} ms tolerance")

    # ---- write, never overwriting ----------------------------------------
    pathlib.Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
    idx, (png, txt) = next_free(OUT_DIR, OUT_STEM, [".png", ".txt"])
    if idx:
        print(f"  NOTE: {OUT_STEM}.png already existed, using suffix _{idx}")
    ax_position = tuple(ax.get_position().extents)
    fig.savefig(png, dpi=DPI, facecolor=C.SURF)
    plt.close(fig)
    print(f"wrote {png} at {DPI} dpi")

    assert_no_vertical_pixels(png, ax_position)

    txt.write_text("margin_p95(t) = deadline - t - latency_p95(t)\n", encoding="utf-8")
    print(f"wrote {txt}")


if __name__ == "__main__":
    try:
        main()
    except GateFailure as e:
        print(f"\nSTOP - gate failed, nothing written: {e}")
        sys.exit(2)
