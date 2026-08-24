"""Detection improvement across the chronological tuning stages.

A READ of results/detector_tuning/history/results_history.csv. The file is opened
read-only and never written back. Nothing is re-run.

One marker per history row, x-axis the stage label, chronological order taken
from the file's own row order.

WHY FOUR PANELS AND NOT TWO
The history's numbers do not share a denominator:

  avg_combined_rate  measured on a 10-flight sample for the early stages and on
                     the full 163-flight dataset for the last two
  labeled_recall     measured over 54 labelled points (flight_01 only) early and
                     240 points (flight_01 + flight_22) later

Putting either pair on one axis would invite a comparison the data cannot
support, so each denominator gets its own panel with its own y-axis. The panels
share the x-axis because chronology IS the story; the y-axes are deliberately
separate because the y-values are not commensurable.

The two splits are NOT the same partition: row 10 carries a 10-flight combined
rate but a 240-point recall, so the recall denominator changes one stage earlier
than the flight population does. One shared divider would be wrong for one of
the two metrics.

NO INTERPOLATION. Markers only - no connecting lines, no fitted trend. The
stages are discrete configuration changes, not samples of a continuous process,
and the x positions are ordinal, not a time axis.

STOP conditions, both checked before anything is drawn:
  - a row carries a recall whose point count is unannotated (blank
    labeled_recall_flights) while other rows' counts differ
  - a row carries a value whose flight population is unannotated (blank
    n_flights) while other rows' populations differ

Outputs (both NEW):
    results/regenerate_figures/detection_improvement/detection_improvement.png
    results/regenerate_figures/detection_improvement/detection_improvement_rows.csv
"""
import csv
import pathlib
import re
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
HIST = "results/detector_tuning/history/results_history.csv"
OUT_DIR = ROOT / "results/regenerate_figures/detection_improvement"
OUT_PNG = OUT_DIR / "detection_improvement.png"
OUT_CSV = OUT_DIR / "detection_improvement_rows.csv"

# Short x-axis labels, keyed by a substring that must match exactly one stage
# string. Keyed rather than positional so a new history row cannot silently
# shift every label by one.
LABEL_KEYS = [
    ("baseline (defaults)", "baseline\n(defaults)"),
    ("round 1 sweep", "round 1 sweep\nstride/thresh/open_k"),
    ("candidate config (no fixes)", "candidate\n(no fixes)"),
    ("artifact audit (pre-mask-v3", "audit\npre-mask-v3"),
    ("mask v2 + trajectory filter", "+ mask v2\n+ traj filter"),
    ("mask v3 (4 zones)", "+ mask v3\n(4 zones)"),
    ("round 3 sweep", "round 3 sweep\nmin_area/min_circ"),
    ("audit at min_area=30/min_circ=0.30 (pre-mask-v4", "audit\npre-mask-v4"),
    ("post-mask-v4 re-audit", "audit\npost-mask-v4"),
    ("10-FLIGHT SAMPLE", "+ mask v4\n+ area30 (sample)"),
    # "(current)" is load-bearing: the rect row's stage text ALSO ends in
    # "- FULL 163-FLIGHT DATASET", so the bare phrase matches both rows and
    # would label the rect stage as the ellipse one.
    ("FULL 163-FLIGHT DATASET (current)", "same config\nfull dataset"),
    ("rect close kernel", "rect close kernel\n(ELLIPSE->RECT)"),
]

# The two rows the brief asks to mark distinctly. Both are 163-flight, 240-point,
# and differ only in the close-kernel shape, so they are the one genuinely
# like-for-like pair in the whole file. Same substring trap as above.
ELLIPSE_KEY = "FULL 163-FLIGHT DATASET (current)"
RECT_KEY = "rect close kernel"

MARKER_COLOR = "#2a78d6"
ELLIPSE_COLOR = "#1baf7a"
RECT_COLOR = "#e34948"
NOVAL_COLOR = "#c9c8c3"

PAGE_W_IN, DPI = 6.6, 300
FS_SUPTITLE, FS_PANEL, FS_AXIS = 11, 8.5, 8.5
FS_TICK, FS_XTICK, FS_ANNOT, FS_CAP, FS_LEGEND = 7.5, 6.0, 6.2, 5.6, 7.0


def stop(msg):
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def read_history():
    with open(ROOT / HIST, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def short_label(stage):
    hits = [lab for key, lab in LABEL_KEYS if key.lower() in stage.lower()]
    if len(hits) != 1:
        stop(f"stage string matched {len(hits)} label keys, expected exactly 1:\n"
             f"  {stage[:110]}\n"
             f"LABEL_KEYS is out of date with the history file.")
    return hits[0]


def point_count(recall_flights):
    """The labelled-point denominator, parsed out of labeled_recall_flights.
    Returns None when the row records no labelled measurement at all."""
    m = re.search(r"\((\d+) points\)", recall_flights)
    return int(m.group(1)) if m else None


def gate_annotations(rows):
    """Both STOP conditions. Each fires only on an UNANNOTATED difference - the
    populations differing is expected and is handled by splitting the panels."""
    # --- recall point counts ---
    with_recall = [r for r in rows if r["labeled_recall"].strip()]
    unannotated = [r for r in with_recall if point_count(r["labeled_recall_flights"]) is None]
    counts = {point_count(r["labeled_recall_flights"]) for r in with_recall}
    counts.discard(None)
    if unannotated and len(counts) > 1:
        stop(f"{len(unannotated)} row(s) carry a labeled_recall with no point count "
             f"in labeled_recall_flights, while annotated rows show differing counts "
             f"{sorted(counts)}. Cannot establish comparability:\n"
             + "\n".join(f"  - {r['date']} {r['stage'][:70]}" for r in unannotated))

    # --- flight populations ---
    with_value = [r for r in rows
                  if r["avg_combined_rate"].strip() or r["labeled_recall"].strip()]
    no_pop = [r for r in with_value if not r["n_flights"].strip()]
    pops = {r["n_flights"].strip() for r in with_value if r["n_flights"].strip()}
    if no_pop and len(pops) > 1:
        stop(f"{len(no_pop)} row(s) carry a value with no n_flights, while "
             f"annotated rows show differing populations {sorted(pops)}:\n"
             + "\n".join(f"  - {r['date']} {r['stage'][:70]}" for r in no_pop))
    return counts, pops


def gate_labels(rows):
    """Every key must match exactly one row, and every row exactly one key.

    short_label() only checks the second direction. Without this check a key that
    matched two rows would silently give them the same x label - which is how the
    ellipse/rect collision first showed up.
    """
    for key, lab in LABEL_KEYS:
        hits = [r for r in rows if key.lower() in r["stage"].lower()]
        if len(hits) != 1:
            stop(f"label key {key!r} matched {len(hits)} rows, expected exactly 1:\n"
                 + "\n".join(f"  - {r['date']} {r['stage'][:80]}" for r in hits))
    if len({lab for _, lab in LABEL_KEYS}) != len(LABEL_KEYS):
        stop("two LABEL_KEYS entries share a short label")


def build(rows):
    """Attach the parsed fields each row needs, in file order (chronological)."""
    out = []
    for i, r in enumerate(rows):
        stage = r["stage"]
        out.append(dict(
            idx=i,
            n=i + 1,
            date=r["date"],
            stage=stage,
            label=short_label(stage),
            n_flights=r["n_flights"].strip(),
            comb=float(r["avg_combined_rate"]) if r["avg_combined_rate"].strip() else None,
            rec=float(r["labeled_recall"]) if r["labeled_recall"].strip() else None,
            pts=point_count(r["labeled_recall_flights"]),
            rec_flights=r["labeled_recall_flights"],
            is_ellipse=ELLIPSE_KEY.lower() in stage.lower(),
            is_rect=RECT_KEY.lower() in stage.lower(),
        ))
    return out


def panel(ax, recs, xs, value_key, keep, title, ylabel):
    """One denominator's markers. Rows outside `keep` get no marker at all -
    their x position stays, so chronology is preserved, but nothing is drawn
    that would imply a value this panel's denominator cannot support."""
    C.style_axes(ax, grid_axis="y")
    vals = [(r["idx"], r[value_key]) for r in recs
            if r in keep and r[value_key] is not None]
    plain = [(i, v) for i, v in vals
             if not recs[i]["is_ellipse"] and not recs[i]["is_rect"]]
    if plain:
        ax.plot([i for i, _ in plain], [v for _, v in plain], linestyle="none",
                marker="o", ms=5.5, color=MARKER_COLOR, zorder=4)
    for i, v in vals:
        r = recs[i]
        if r["is_ellipse"]:
            ax.plot([i], [v], linestyle="none", marker="D", ms=6.5,
                    color=ELLIPSE_COLOR, zorder=5)
        elif r["is_rect"]:
            ax.plot([i], [v], linestyle="none", marker="s", ms=6.5,
                    color=RECT_COLOR, zorder=5)
        ax.annotate(f"{v:.4f}", xy=(i, v), xytext=(0, 7),
                    textcoords="offset points", ha="center", va="bottom",
                    color=C.INK, fontsize=FS_ANNOT, zorder=6)

    # y-limits FIRST. The no-value dashes are then placed relative to the final
    # limits - computing them from the data range instead put them below the
    # axis in every panel whose values span less than the 0.02 floor, which
    # silently clipped them out of three of the four panels.
    if vals:
        lo = min(v for _, v in vals)
        hi = max(v for _, v in vals)
        span = max(hi - lo, 0.02)
        ax.set_ylim(lo - span * 0.30, hi + span * 0.34)

    # x positions this panel has no value for, marked so an empty slot reads as
    # "not measured here" rather than "measured and zero".
    missing = [r["idx"] for r in recs if r not in keep or r[value_key] is None]
    if missing:
        y0, y1 = ax.get_ylim()
        y = y0 + (y1 - y0) * 0.05
        for i in missing:
            ax.plot([i], [y], linestyle="none", marker="_", ms=5,
                    color=NOVAL_COLOR, zorder=3)
    ax.set_title(title, color=C.INK, fontsize=FS_PANEL, loc="left", pad=4)
    ax.set_ylabel(ylabel, color=C.INK, fontsize=FS_AXIS)
    ax.tick_params(labelsize=FS_TICK)
    ax.set_xlim(-0.6, len(recs) - 0.4)
    ax.set_xticks(range(len(recs)))


def write_csv(recs):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cols = ["row", "date", "short_label", "n_flights", "avg_combined_rate",
            "labeled_recall", "recall_points", "labeled_recall_flights",
            "kernel_marker", "stage"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in recs:
            w.writerow({
                "row": r["n"], "date": r["date"],
                "short_label": r["label"].replace("\n", " "),
                "n_flights": r["n_flights"],
                "avg_combined_rate": "" if r["comb"] is None else f"{r['comb']:.4f}",
                "labeled_recall": "" if r["rec"] is None else f"{r['rec']:.4f}",
                "recall_points": "" if r["pts"] is None else r["pts"],
                "labeled_recall_flights": r["rec_flights"],
                "kernel_marker": ("ELLIPSE close kernel" if r["is_ellipse"]
                                  else "RECT close kernel" if r["is_rect"] else ""),
                "stage": r["stage"],
            })
    print(f"wrote {OUT_CSV.relative_to(ROOT)}")


def caption_block(fig, lines, gap=0.0118, floor_y=0.008):
    """Anchor the LAST line at a fixed height and grow upward so a longer caption
    cannot run off the bottom edge."""
    start_y = floor_y + (len(lines) - 1) * gap
    for i, line in enumerate(lines):
        fig.text(0.006, start_y - i * gap, line, color=C.INK2, fontsize=FS_CAP)
    return start_y + 0.014


def main():
    raw = read_history()
    counts, pops = gate_annotations(raw)
    gate_labels(raw)
    recs = build(raw)
    xs = list(range(len(recs)))

    print(f"read {HIST}: {len(recs)} rows")
    print(f"GATE 1 recall annotation PASS: point counts {sorted(counts)}, "
          f"every row carrying a recall names its own")
    print(f"GATE 2 flight annotation PASS: populations {sorted(pops)}, "
          f"every row carrying a value names its own")

    comb10 = [r for r in recs if r["comb"] is not None and r["n_flights"] == "10"]
    comb163 = [r for r in recs if r["comb"] is not None and r["n_flights"] == "163"]
    rec54 = [r for r in recs if r["rec"] is not None and r["pts"] == 54]
    rec240 = [r for r in recs if r["rec"] is not None and r["pts"] == 240]

    print("\nNOT COMPARABLE ACROSS THESE GROUPS - each gets its own axis:")
    for name, grp in (("combined rate, 10-flight sample", comb10),
                      ("combined rate, 163-flight full dataset", comb163),
                      ("labelled recall, 54 points (flight_01 only)", rec54),
                      ("labelled recall, 240 points (flight_01 + flight_22)", rec240)):
        print(f"  {name}: rows {[r['n'] for r in grp]}")
    noval = [r["n"] for r in recs if r["comb"] is None and r["rec"] is None]
    print(f"  rows with no rate recorded (sweep/audit stages): {noval}")

    fig, axes = plt.subplots(4, 1, figsize=(PAGE_W_IN, 8.4), sharex=True)
    fig.patch.set_facecolor(C.SURF)
    panel(axes[0], recs, xs, "comb", comb10,
          "avg_combined_rate  -  10-flight validation sample", "combined rate")
    panel(axes[1], recs, xs, "comb", comb163,
          "avg_combined_rate  -  163-flight full dataset", "combined rate")
    panel(axes[2], recs, xs, "rec", rec54,
          "labelled recall  -  54 points (flight_01 only)", "recall")
    panel(axes[3], recs, xs, "rec", rec240,
          "labelled recall  -  240 points (flight_01 + flight_22)", "recall")

    axes[-1].set_xticklabels([r["label"] for r in recs], rotation=90,
                             fontsize=FS_XTICK)
    axes[-1].set_xlabel("iteration stage, chronological (not to time scale)",
                        color=C.INK, fontsize=FS_AXIS)

    handles = [
        plt.Line2D([], [], ls="none", marker="o", ms=5.5, color=MARKER_COLOR,
                   label="tuning stage"),
        plt.Line2D([], [], ls="none", marker="D", ms=6.5, color=ELLIPSE_COLOR,
                   label="ELLIPSE close kernel"),
        plt.Line2D([], [], ls="none", marker="s", ms=6.5, color=RECT_COLOR,
                   label="RECT close kernel"),
        plt.Line2D([], [], ls="none", marker="_", ms=6, color=NOVAL_COLOR,
                   label="no value in this panel"),
    ]
    fig.legend(handles=handles, frameon=False, fontsize=FS_LEGEND,
               labelcolor=C.INK2, loc="upper center",
               bbox_to_anchor=(0.5, 0.972), ncol=4)
    fig.suptitle("Detection performance across the tuning iteration stages",
                 color=C.INK, fontsize=FS_SUPTITLE, x=0.006, ha="left", y=0.995)

    caption = [
        "Markers only - NO interpolation. The stages are discrete configuration changes, so the x positions are ordinal, not a time axis,",
        "and a line between two of them would assert a path through configurations that were never run.",
        "FOUR PANELS BECAUSE THE DENOMINATORS DIFFER. Values may only be compared WITHIN a panel, never across panels:",
        f"  combined rate is a {comb10[0]['n_flights']}-flight sample mean in panel 1 and a {comb163[0]['n_flights']}-flight mean in panel 2;",
        "  recall is over 54 labelled points (flight_01 only) in panel 3 and 240 points (flight_01 + flight_22) in panel 4.",
        "The two splits are NOT the same partition: the '+ mask v4 + area30 (sample)' stage carries a 10-flight combined rate but an",
        "already-240-point recall, so the recall denominator changes one stage earlier than the flight population does.",
        "ELLIPSE (diamond) and RECT (square) mark the only genuinely like-for-like pair in the file - same 163 flights, same 240 points,",
        "differing only in the morphological close-kernel shape. Every other adjacent pair also changes config, population or both.",
        "Dashes on the lower edge mark stages this panel has no value for - sweep and audit rows record no rate, and a row measured on one",
        "denominator is absent from the other's panel. An empty slot means not measured here, not measured as zero.",
        "Source: results/detector_tuning/history/results_history.csv, read-only, plotted in the file's own row order. Values in the companion CSV.",
    ]
    rect_bottom = caption_block(fig, caption)
    fig.tight_layout(rect=[0, rect_bottom, 1, 0.952])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=DPI, facecolor=C.SURF)
    plt.close(fig)
    print(f"\nwrote {OUT_PNG.relative_to(ROOT)}")
    write_csv(recs)
    print("\nsource CSV not modified")


if __name__ == "__main__":
    main()
