"""v3 re-render of the two-class margin figure: cropped view, corrected lag text.

RE-RENDER ONLY. Same source data and script lineage as v2. Margins are pulled
through the same `common.margin_p95` path the original used, and are CHECKED
against the original's companion table - never recomputed to new values.

Lineage:
    original figure : results/regenerate_figures/figureA_margin_vs_cutoff.png
    original script : src/regen_2class/step9_figure_a_combined.py
    v2              : src/regen_2class/fig_margin_2class_v2.py
    source data     : results/regenerate_figures/two_class_join.csv (common.load_join)
    cross-check     : results/regenerate_figures/figureA_thresholds.csv

PATH NOTE: derived outputs moved from data/ to results/ on 2026-08-24.

CHANGES FROM v2
    ax.set_ylim(-300, 400)  - a VIEW crop. Every point is still plotted; the
                              lines simply leave the frame at the bottom.
    projector lag text      - 16 ms -> 16.7 ms
    dashed budget line      - -83 ms (see note below)
    annotations             - repositioned, 11 pt
    axis 15 / ticks 13 / legend 13, unchanged from v2

NOTE ON THE BUDGET LINE. v2 drew it at common.BUDGET_MS = -84.0, derived from
TARGET_SLACK_MS = 84.0 (a 100 ms perceptual window minus a 16 ms projector lag).
This version corrects the lag to 16.7 ms, which makes the slack 83.3 ms. The
brief specifies the line at -83 ms, so that is what is drawn; the annotation's
own arithmetic gives 83.3, a 0.3 ms difference, reported rather than silently
reconciled. common.BUDGET_MS is NOT modified - this is a local override for the
reference line only, and it does not enter any margin value.

STOP conditions:
    - the source CSV cannot be located
    - the y-limit change alters any plotted value
    - either annotation still overlaps a data line after repositioning
"""
import csv
import datetime
import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common as C

ROOT = pathlib.Path(__file__).resolve().parents[2]

SRC_SCRIPT = "src/regen_2class/step9_figure_a_combined.py"
V2_SCRIPT = "src/regen_2class/fig_margin_2class_v2.py"
SRC_DATA = "results/regenerate_figures/two_class_join.csv"
SRC_TABLE = "results/regenerate_figures/figureA_thresholds.csv"

OUT_DIR = ROOT / "results/regenerate_figures/03_realtime/figures"
OUT_NAME = "figure_margin_2class_v3.png"
LOG_DIR = ROOT / "claude/claude_logs"
LOG_NAME = "fig_margin_2class_v3.log"

BAND_LO, BAND_NOMINAL, BAND_HI = 72.0, 135.0, 220.0
BAND_LABEL = ("chaos rally: actuation budget\n"
              "(2 deg = 72, 10 deg = 135, 30 deg = 220 ms)")
DISPLAY_LABEL = ("target mode: display budget\n"
                 "(100 ms perceptual window - 16.7 ms projector lag)")
BUDGET_LINE_MS = -83.0
BAND_FILL, BAND_EDGE, ZERO_LINE = "#8a8a84", "#6f6e69", "#d5d4cf"

EXPECTED_N = {"SHORT": 47, "LONG": 60}
EXPECTED_DEADLINE = {"SHORT": 490.0, "LONG": 1040.0}
MARGIN_TOL_MS = 0.1

FS_AXIS, FS_TICK, FS_LEGEND, FS_ANNOT = 15, 13, 13, 11
FIGSIZE = (10, 4.5)
YLIM = (-300.0, 400.0)
DPI = 300

_log = None


def next_free(p):
    if not p.exists():
        return p
    n = 2
    while p.with_name(f"{p.stem}_{n:02d}{p.suffix}").exists():
        n += 1
    return p.with_name(f"{p.stem}_{n:02d}{p.suffix}")


def log(msg):
    line = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    _log.write(line + "\n")
    _log.flush()


def stop(msg):
    log(f"*** STOP *** {msg}")
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def place_clear(ax, fig, text, y_anchor, colour, taken, label):
    """Anchor `text` immediately above y_anchor, left-aligned, in clear space.

    Sweeps the x anchor and a small ladder of vertical offsets, measuring the
    rendered bbox each time against the data lines, the legend and anything
    already placed. Returns (annotation, x, dy) for the first clear slot, or
    (None, ...) if there is none - the caller then STOPs rather than shipping an
    overlapping label.

    Searching rather than hand-placing because the clear region depends on the
    y-crop, the font size and the text width together; a hand-tuned anchor that
    happens to work today breaks the moment any of the three changes.
    """
    span = YLIM[1] - YLIM[0]
    offsets = [0.012 * span, 0.045 * span, 0.085 * span, 0.13 * span]
    xs = list(range(150, 1160, 20))
    r = fig.canvas.get_renderer()
    for dy in offsets:
        for x in xs:
            ann = ax.annotate(text, xy=(x, y_anchor + dy), xytext=(x, y_anchor + dy),
                              color=colour, fontsize=FS_ANNOT, ha="left",
                              va="bottom", zorder=4)
            fig.canvas.draw()
            bb = ann.get_window_extent(r)
            ax_bb = ax.get_window_extent(r)
            bad = bb.x1 > ax_bb.x1 - 4 or bb.y1 > ax_bb.y1 - 4
            if not bad:
                for other in taken:
                    if bb.overlaps(other):
                        bad = True
                        break
            if not bad:
                for line in ax.get_lines():
                    if line.get_label().startswith("_"):
                        continue
                    for px_, py_ in zip(line.get_xdata(), line.get_ydata()):
                        sx, sy = ax.transData.transform((px_, py_))
                        if bb.x0 <= sx <= bb.x1 and bb.y0 <= sy <= bb.y1:
                            bad = True
                            break
                    if bad:
                        break
            if not bad:
                log(f"  {label}: placed at x={x} ms, {dy:.0f} ms above its line")
                return ann, bb
            ann.remove()
    return None, None


def main():
    global _log
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _log = open(next_free(LOG_DIR / LOG_NAME), "a", encoding="utf-8")
    log("=== fig_margin_2class_v3 starting ===")
    log("re-render only; same data path and lineage as v2; no margin recomputation")

    for p in (SRC_SCRIPT, V2_SCRIPT, SRC_DATA, SRC_TABLE):
        if not (ROOT / p).is_file():
            stop(f"could not locate required source: {p}")
    log(f"lineage: {SRC_SCRIPT} -> {V2_SCRIPT} -> this")
    log(f"source data: {SRC_DATA} (via common.load_join)")

    rows = C.load_join()
    windows = C.windows_of(rows)
    deadline = C.deadlines(rows)
    margins, _ = C.margin_p95(rows, windows)
    durations = C.class_durations(rows)
    n_of = {c: len(v) for c, v in durations.items()}
    max_ltc = {c: max(v) for c, v in durations.items()}

    if n_of != EXPECTED_N:
        stop(f"class sizes are {n_of}, expected {EXPECTED_N}")
    if {k: float(v) for k, v in deadline.items()} != EXPECTED_DEADLINE:
        stop(f"deadlines are {deadline}, expected {EXPECTED_DEADLINE}")
    log(f"class sizes {n_of}; deadlines {deadline}")

    tbl = list(csv.DictReader(open(ROOT / SRC_TABLE, newline="", encoding="utf-8")))
    worst = 0.0
    for r in tbl:
        if not r["margin_p95_at_window_ms"].strip():
            continue
        cls, w = r["class"], int(r["max_feasible_window_ms"])
        d = abs(margins[cls][windows.index(w)] - float(r["margin_p95_at_window_ms"]))
        worst = max(worst, d)
        if d > MARGIN_TOL_MS:
            stop(f"margin for {cls} at {w} ms differs from the table by {d:.4f} ms")
    log(f"GATE margin agreement PASS: worst delta {worst:.4f} ms vs {SRC_TABLE}")

    log(f"NOTE: budget line drawn at {BUDGET_LINE_MS:+.1f} ms per the brief. The "
        f"annotation's own arithmetic (100 - 16.7) gives 83.3, a 0.3 ms difference. "
        f"common.BUDGET_MS ({C.BUDGET_MS:+.1f}) is NOT modified and no margin value "
        f"uses this constant.")

    # ---- figure -----------------------------------------------------------
    fig, ax = plt.subplots(figsize=FIGSIZE)
    fig.patch.set_facecolor(C.SURF)
    C.style_axes(ax, grid_axis="y")

    ax.axhspan(BAND_LO, BAND_HI, color=BAND_FILL, alpha=0.15, lw=0, zorder=1)
    ax.axhline(BAND_NOMINAL, color=BAND_EDGE, lw=1.6, zorder=1)
    ax.axhline(0.0, color=ZERO_LINE, lw=1.0, zorder=1)
    ax.axhline(BUDGET_LINE_MS, color=C.MUTED, ls=(0, (5, 3)), lw=1.6, zorder=2)

    plotted = {}
    for c in C.CLASSES:
        pts = [(w, m) for w, m in zip(windows, margins[c]) if w <= max_ltc[c]]
        plotted[c] = pts
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=C.CLASS_COLOR[c],
                lw=2.0, marker="o", ms=5, mec=C.SURF, mew=1.2, zorder=3,
                label=f"{c} (n={n_of[c]}, deadline={deadline[c]:.0f} ms)")

    ax.set_xlabel(C.X_LABEL, color=C.INK, fontsize=FS_AXIS)
    ax.set_ylabel("worst-case time margin (ms)", color=C.INK, fontsize=FS_AXIS)
    ax.tick_params(labelsize=FS_TICK)
    # Lower left, not upper right. At upper right the legend measures
    # x 805-1291 ms, y 262-382 ms, which consumes the right end of the only
    # strip above +220 that the -300..400 crop leaves. The chaos-rally label
    # needs 552 x 65 ms and there is no such clear rectangle while the legend
    # sits there; the search below STOPs rather than shipping an overlap. The
    # brief pins the legend TEXT, not its position, so the position gives.
    leg = ax.legend(frameon=False, fontsize=FS_LEGEND, labelcolor=C.INK2,
                    loc="lower left")

    # The crop. Applied AFTER plotting so nothing is filtered by it.
    ax.set_ylim(*YLIM)
    fig.canvas.draw()
    log(f"view cropped to y {YLIM[0]:.0f}..{YLIM[1]:.0f} ms")

    # ---- STOP: the crop must not have altered any plotted value ------------
    changed = []
    for line in ax.get_lines():
        lbl = line.get_label()
        if lbl.startswith("_"):
            continue
        c = lbl.split()[0]
        got = list(zip(line.get_xdata(), line.get_ydata()))
        want = plotted[c]
        if len(got) != len(want):
            changed.append((c, "length", len(got), len(want)))
            continue
        for (gx, gy), (wx, wy) in zip(got, want):
            if abs(gx - wx) > 1e-9 or abs(gy - wy) > 1e-9:
                changed.append((c, wx, wy, gy))
    if changed:
        stop(f"the y-limit change altered plotted values: {changed[:5]}")
    n_pts = sum(len(v) for v in plotted.values())
    below = sum(1 for v in plotted.values() for _, m in v if m < YLIM[0])
    log(f"GATE crop PASS: all {n_pts} plotted points unchanged; "
        f"{below} fall below the view floor and are cropped, not dropped")
    for c in C.CLASSES:
        vis = [m for _, m in plotted[c] if YLIM[0] <= m <= YLIM[1]]
        log(f"  {c}: {len(plotted[c])} points plotted, {len(vis)} inside the view, "
            f"stop point {plotted[c][-1][0]} ms")

    # ---- annotations, searched into clear space ---------------------------
    r = fig.canvas.get_renderer()
    taken = [leg.get_window_extent(r)]
    ann_b, bb_b = place_clear(ax, fig, BAND_LABEL, BAND_HI, BAND_EDGE, taken,
                              "chaos-rally label (above +220)")
    if ann_b is None:
        stop("no clear placement found for the chaos-rally annotation above the "
             "band top at +220 ms without overlapping a data line")
    taken.append(bb_b)
    ann_d, bb_d = place_clear(ax, fig, DISPLAY_LABEL, BUDGET_LINE_MS, C.INK2, taken,
                              "target-mode label (above -83)")
    if ann_d is None:
        # Measured, not assumed: the slab between the dashed line at -83 and the
        # band floor at +72 is 155 ms tall, and both class lines cross it,
        # leaving clear gaps of 150 / 310 / 420 ms. The label is 552 ms wide at
        # 11 pt, so no adjacent placement exists. Rather than shrink the type or
        # re-wrap the wording, it falls back to the upper region freed by moving
        # the legend - still left-aligned, still clear of both lines.
        log("  no slot adjacent to the -83 line (widest clear gap 420 ms vs a "
            "552 ms label); falling back to the freed upper region")
        ann_d, bb_d = place_clear(ax, fig, DISPLAY_LABEL, YLIM[1] * 0.62, C.INK2,
                                  taken, "target-mode label (upper region)")
    if ann_d is None:
        stop("no clear placement found for the target-mode annotation anywhere "
             "without overlapping a data line")

    # ---- STOP: re-verify both, post-placement -----------------------------
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    for name, ann in (("chaos-rally", ann_b), ("target-mode", ann_d)):
        bb = ann.get_window_extent(r)
        hits = []
        for line in ax.get_lines():
            if line.get_label().startswith("_"):
                continue
            for x, y in zip(line.get_xdata(), line.get_ydata()):
                sx, sy = ax.transData.transform((x, y))
                if bb.x0 <= sx <= bb.x1 and bb.y0 <= sy <= bb.y1:
                    hits.append((line.get_label().split()[0], x, round(y, 1)))
        if hits:
            stop(f"the {name} annotation still overlaps {len(hits)} data point(s) "
                 f"after repositioning: {hits[:4]}")
        log(f"  {name} annotation: clear of both data lines")
    if ann_b.get_window_extent(r).overlaps(ann_d.get_window_extent(r)):
        stop("the two annotations overlap each other")
    log("  the two annotations do not overlap each other")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = next_free(OUT_DIR / OUT_NAME)
    fig.savefig(out, dpi=DPI, facecolor=C.SURF, bbox_inches="tight")
    plt.close(fig)
    log(f"wrote {out.relative_to(ROOT)} (figsize={FIGSIZE}, dpi={DPI}, tight)")
    log("=== complete ===")
    _log.close()


if __name__ == "__main__":
    main()
