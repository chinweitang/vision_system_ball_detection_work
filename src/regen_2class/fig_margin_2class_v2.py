"""Re-render of the two-class margin figure for full-width LaTeX placement.

RE-RENDER ONLY. No new analysis, no sweep re-run. Margins are recomputed from
the same join CSV through the same `common.margin_p95` the original figure used,
purely so they can be CHECKED against the original's companion table - not to
produce new values.

Source figure : results/regenerate_figures/figureA_margin_vs_cutoff.png
Producing script: src/regen_2class/step9_figure_a_combined.py
Source data   : results/regenerate_figures/two_class_join.csv  (via common.load_join)
Cross-check   : results/regenerate_figures/figureA_thresholds.csv

PATH NOTE: derived outputs moved from data/ to results/ on 2026-08-24. All paths
here are post-migration; older logs citing data/regenerate_figures/... mean the
same files.

Kept unchanged from the original: both class lines and their stop points, the
legend text, the chaos-rally actuation band 72-220 ms with its solid line at
135 ms, the target-mode dashed budget line, the zero line, and both inline
budget labels.

Removed: the dotted threshold verticals and their rotated labels, the title, and
the caption block.

Changed: figsize (10, 4.5); y-label "worst-case time margin (ms)"; explicit font
sizes 15 / 13 / 13 / 12.

VERTICAL LINES: the original leaves matplotlib's grid on both axes, which draws
vertical gridlines. Since the brief forbids vertical lines and makes a
vertical-line artefact a STOP condition, the grid here is restricted to the y
axis. The rendered PNG is then scanned column by column and the run count is
asserted, so the check is on the OUTPUT rather than on intent.

STOP conditions:
    - source CSV or producing script cannot be located
    - class sizes are not SHORT n=47, LONG n=60
    - deadlines are not 490 and 1040 ms
    - recomputed margin disagrees with the original's table by > 0.1 ms
    - a vertical-line artefact appears in the output
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
SRC_FIGURE = "results/regenerate_figures/figureA_margin_vs_cutoff.png"
SRC_DATA = "results/regenerate_figures/two_class_join.csv"
SRC_TABLE = "results/regenerate_figures/figureA_thresholds.csv"

OUT_DIR = ROOT / "results/regenerate_figures/03_realtime/figures"
OUT_NAME = "figure_margin_2class_v2.png"
LOG_DIR = ROOT / "claude/claude_logs"
LOG_NAME = "fig_margin_2class_v2.log"

# Verbatim from step9_figure_a_combined.py - not re-derived.
BAND_LO, BAND_NOMINAL, BAND_HI = 72.0, 135.0, 220.0
BAND_LABEL = ("chaos rally: actuation budget\n"
              "(2 deg = 72, 10 deg = 135, 30 deg = 220 ms)")
DISPLAY_LABEL = ("target mode: display budget\n"
                 "(100 ms perceptual window - 16 ms projector lag)")
BAND_FILL, BAND_EDGE, ZERO_LINE = "#8a8a84", "#6f6e69", "#d5d4cf"

EXPECTED_N = {"SHORT": 47, "LONG": 60}
EXPECTED_DEADLINE = {"SHORT": 490.0, "LONG": 1040.0}
MARGIN_TOL_MS = 0.1

FS_AXIS, FS_TICK, FS_LEGEND, FS_ANNOT = 15, 13, 13, 12
FIGSIZE = (10, 4.5)
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


def scan_vertical_runs(png_path, bg_hex):
    """Column-wise ink scan of the rendered PNG.

    Returns contiguous groups of columns that are almost entirely ink. With the
    grid restricted to y and no axvline calls, the only such group should be the
    left spine.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    im = Image.open(png_path).convert("RGB")
    w, h = im.size
    bg = tuple(int(bg_hex[i:i + 2], 16) for i in (1, 3, 5))
    px = im.load()
    heavy = []
    for x in range(w):
        ink = 0
        for y in range(h):
            r, g, b = px[x, y]
            if abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) > 30:
                ink += 1
        if ink / h > 0.80:
            heavy.append(x)
    groups, cur = [], []
    for x in heavy:
        if cur and x == cur[-1] + 1:
            cur.append(x)
        else:
            if cur:
                groups.append((cur[0], cur[-1]))
            cur = [x]
    if cur:
        groups.append((cur[0], cur[-1]))
    return groups, (w, h)


def main():
    global _log
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = next_free(LOG_DIR / LOG_NAME)
    _log = open(log_path, "a", encoding="utf-8")

    log("=== fig_margin_2class_v2 starting ===")
    log(f"log: {log_path.relative_to(ROOT)}")
    log("re-render only; no sweep re-run, no new analysis")

    # ---- locate the source -------------------------------------------------
    log("--- locating the source figure's script and data ---")
    for p in (SRC_SCRIPT, SRC_DATA, SRC_TABLE):
        if not (ROOT / p).is_file():
            stop(f"could not locate required source: {p}")
    log(f"producing script : {SRC_SCRIPT}")
    log(f"existing figure  : {SRC_FIGURE}"
        f"{'' if (ROOT/SRC_FIGURE).is_file() else '  (NOT on disk)'}")
    log(f"source data path : {SRC_DATA}  (reached via common.load_join)")
    log(f"cross-check table: {SRC_TABLE}")
    log(f"NOTE: step_4_figure_a_margin.py also writes {SRC_FIGURE}; "
        f"step9 is the authoritative producer and is the one reused here")

    # ---- data, via the same path the original used -------------------------
    rows = C.load_join()
    windows = C.windows_of(rows)
    deadline = C.deadlines(rows)
    margins, n_ok = C.margin_p95(rows, windows)
    durations = C.class_durations(rows)
    n_of = {c: len(v) for c, v in durations.items()}
    max_ltc = {c: max(v) for c, v in durations.items()}
    log(f"loaded {len(rows)} join rows, {len(windows)} windows "
        f"{windows[0]}..{windows[-1]}")

    # ---- STOP: class sizes -------------------------------------------------
    if n_of != EXPECTED_N:
        stop(f"class sizes are {n_of}, expected {EXPECTED_N}")
    log(f"GATE class sizes PASS: {n_of}")

    # ---- STOP: deadlines ---------------------------------------------------
    if {k: float(v) for k, v in deadline.items()} != EXPECTED_DEADLINE:
        stop(f"deadlines are {deadline}, expected {EXPECTED_DEADLINE}")
    log(f"GATE deadlines PASS: {deadline}")

    # ---- STOP: margins agree with the original's own table -----------------
    tbl = list(csv.DictReader(open(ROOT / SRC_TABLE, newline="", encoding="utf-8")))
    checked, worst = 0, 0.0
    for r in tbl:
        if not r["margin_p95_at_window_ms"].strip():
            continue
        cls, w = r["class"], int(r["max_feasible_window_ms"])
        stored = float(r["margin_p95_at_window_ms"])
        mine = margins[cls][windows.index(w)]
        d = abs(mine - stored)
        worst = max(worst, d)
        checked += 1
        log(f"  check {cls:5s} thr {r['threshold_ms']:>4s} @ {w:4d} ms: "
            f"table {stored:8.1f}  recomputed {mine:8.1f}  delta {d:.4f}")
        if d > MARGIN_TOL_MS:
            stop(f"recomputed margin for {cls} at {w} ms is {mine:.4f}, table says "
                 f"{stored:.4f} (delta {d:.4f} > {MARGIN_TOL_MS} ms)")
    log(f"GATE margin agreement PASS: {checked} points checked, "
        f"worst delta {worst:.4f} ms")

    # ---- discrepancy note --------------------------------------------------
    log(f"NOTE: the target-mode dashed budget line is at {C.BUDGET_MS:+.1f} ms "
        f"(common.BUDGET_MS = -TARGET_SLACK_MS, TARGET_SLACK_MS={C.TARGET_SLACK_MS}). "
        f"The brief describes it as -83 ms. Kept at the source value because the "
        f"line is a 'keep unchanged' item; reporting the mismatch rather than "
        f"moving it.")

    # ---- figure ------------------------------------------------------------
    log("--- rendering ---")
    fig, ax = plt.subplots(figsize=FIGSIZE)
    fig.patch.set_facecolor(C.SURF)
    # grid_axis="y": the original's default draws vertical gridlines, which the
    # brief forbids and makes a STOP condition.
    C.style_axes(ax, grid_axis="y")

    ax.axhspan(BAND_LO, BAND_HI, color=BAND_FILL, alpha=0.15, lw=0, zorder=1)
    ax.axhline(BAND_NOMINAL, color=BAND_EDGE, lw=1.6, zorder=1)
    ax.axhline(0.0, color=ZERO_LINE, lw=1.0, zorder=1)
    ax.axhline(C.BUDGET_MS, color=C.MUTED, ls=(0, (5, 3)), lw=1.6, zorder=2)

    for c in C.CLASSES:
        pts = [(w, m) for w, m in zip(windows, margins[c]) if w <= max_ltc[c]]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=C.CLASS_COLOR[c],
                lw=2.0, marker="o", ms=5, mec=C.SURF, mew=1.2, zorder=3,
                label=f"{c} (n={n_of[c]}, deadline={deadline[c]:.0f} ms)")
        log(f"  {c}: {len(pts)} points, stop point {pts[-1][0]} ms "
            f"(max launch-to-crossing {max_ltc[c]:.1f} ms)")

    lo, hi = ax.get_ylim()
    # The original's label anchors were tuned for an 11 x 7.4 canvas at 7.4/8.2 pt.
    # At 10 x 4.5 and 12 pt each label is roughly 470 ms of x-range wide, so the
    # original anchors put the two straight through each other. Repositioned to
    # the two clear regions - the brief forbids shrinking the type to fit, so
    # they move instead. Both still sit on the side of the plot their own budget
    # governs: the actuation label just above the band, the display label below
    # the zero crossing.
    ann_band = ax.annotate(BAND_LABEL, xy=(windows[-1], BAND_NOMINAL),
                           xytext=(windows[-1], BAND_HI + 15.0),
                           color=BAND_EDGE, fontsize=FS_ANNOT, ha="right",
                           va="bottom", zorder=4)
    ann_disp = ax.annotate(DISPLAY_LABEL, xy=(windows[0], C.BUDGET_MS),
                           xytext=(windows[0] + 10, lo + 0.21 * (hi - lo)),
                           color=C.INK2, fontsize=FS_ANNOT, ha="left",
                           va="top", zorder=4)
    ax.set_ylim(lo, hi)

    ax.set_xlabel(C.X_LABEL, color=C.INK, fontsize=FS_AXIS)
    ax.set_ylabel("worst-case time margin (ms)", color=C.INK, fontsize=FS_AXIS)
    ax.tick_params(labelsize=FS_TICK)

    leg = ax.legend(frameon=False, fontsize=FS_LEGEND, labelcolor=C.INK2,
                    loc="upper right")

    # ---- legend overlap: move, never shrink --------------------------------
    fig.canvas.draw()
    lb = leg.get_window_extent()
    overlap = False
    for line in ax.get_lines():
        xd, yd = line.get_xdata(), line.get_ydata()
        if len(xd) == 0 or line.get_label().startswith("_"):
            continue
        for x, y in zip(xd, yd):
            px, py = ax.transData.transform((x, y))
            if lb.x0 <= px <= lb.x1 and lb.y0 <= py <= lb.y1:
                overlap = True
                break
        if overlap:
            break
    if overlap:
        log("  legend overlaps a data line at upper right -> moving to lower left "
            "(font size unchanged)")
        leg.remove()
        leg = ax.legend(frameon=False, fontsize=FS_LEGEND, labelcolor=C.INK2,
                        loc="lower left")
        fig.canvas.draw()
    else:
        log("  legend at upper right does not overlap either data line")

    # ---- annotation collision check: labels vs each other, and vs the data --
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    bb = {"actuation label": ann_band.get_window_extent(r),
          "display label": ann_disp.get_window_extent(r)}
    if bb["actuation label"].overlaps(bb["display label"]):
        stop("the two inline budget labels overlap each other at this aspect "
             "ratio; the brief forbids shrinking the type, so they must be "
             "repositioned rather than resized")
    log("  the two inline budget labels do not overlap each other")
    for name, box in bb.items():
        hits = []
        for line in ax.get_lines():
            if line.get_label().startswith("_"):
                continue
            for x, y in zip(line.get_xdata(), line.get_ydata()):
                px, py = ax.transData.transform((x, y))
                if box.x0 <= px <= box.x1 and box.y0 <= py <= box.y1:
                    hits.append((line.get_label().split()[0], x, round(y, 1)))
        if hits:
            log(f"  WARNING: {name} overlaps {len(hits)} data point(s): {hits[:4]}")
        else:
            log(f"  {name}: clear of both data lines")

    log(f"  axvline calls made: 0 (none in this script); grid axis = y only")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = next_free(OUT_DIR / OUT_NAME)
    fig.savefig(out, dpi=DPI, facecolor=C.SURF, bbox_inches="tight")
    plt.close(fig)
    log(f"wrote {out.relative_to(ROOT)}  (figsize={FIGSIZE}, dpi={DPI}, "
        f"bbox_inches='tight')")

    # ---- STOP: vertical-line artefact in the OUTPUT ------------------------
    scan = scan_vertical_runs(out, C.SURF)
    if scan is None:
        log("  WARNING: PIL unavailable, vertical-artefact scan skipped")
    else:
        groups, (w, h) = scan
        log(f"  output {w}x{h}px; near-full-height ink column groups: {groups}")
        if len(groups) > 1:
            stop(f"{len(groups)} near-full-height vertical runs found in the output "
                 f"at columns {groups} - expected at most 1 (the left spine). "
                 f"A vertical-line artefact is present.")
        log(f"GATE vertical-line PASS: {len(groups)} run(s) "
            f"({'left spine only' if groups else 'none'})")

    log("=== complete ===")
    _log.close()


if __name__ == "__main__":
    main()
