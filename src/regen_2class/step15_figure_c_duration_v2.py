"""Step 15 - Figure C v2: duration distribution with only the min markers.

A REPLOT of frozen results from results/regenerate_figures/two_class_join.csv. No
fitting, detection or Pi job is re-run. Writes a NEW file; the original
figureC_duration_distribution.png is left in place.

Changes from the original:
  1. The two per-class stat boxes (min / P5 / median / max) are removed.
  2. All vertical dotted markers removed EXCEPT each class's minimum.
  3. Each remaining minimum is labelled at its own line.
  4. All text and numbers enlarged.

The min is the marker worth keeping: it is what the min-anchored deadline rule
uses, so it is the only one of the four that feeds a downstream number.
"""
import csv

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common as C

OUT_PNG = C.OUT_DIR + "figureC_duration_distribution_v2.png"
FS_LABEL, FS_TICK, FS_TITLE, FS_ANNOT, FS_CAP = 16, 14, 18, 14, 9.5


def main():
    rows = C.load_join()
    # collapse the 24-rows-per-flight grid to one row per flight
    per_flight = {(r["session"], r["flight"]): (r["cls2"], float(r["launch_to_crossing_ms"]))
                  for r in rows}
    vals = {c: sorted(d for cls, d in per_flight.values() if cls == c) for c in C.CLASSES}
    mins = {c: min(v) for c, v in vals.items()}
    print(f"flights: SHORT {len(vals['SHORT'])}, LONG {len(vals['LONG'])}, "
          f"total {len(per_flight)}")
    print(f"minima retained as the only markers: "
          f"SHORT {mins['SHORT']:.1f} ms, LONG {mins['LONG']:.1f} ms")

    fig, ax = plt.subplots(figsize=(11.5, 6.8))
    fig.patch.set_facecolor(C.SURF)
    C.style_axes(ax)

    bins = np.linspace(min(vals["SHORT"] + vals["LONG"]),
                       max(vals["SHORT"] + vals["LONG"]), 29)
    for c in C.CLASSES:
        ax.hist(vals[c], bins=bins, color=C.CLASS_COLOR[c], alpha=0.55,
                edgecolor=C.CLASS_COLOR[c], lw=1.3, zorder=3,
                label=f"{c} (n={len(vals[c])})")

    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, hi * 1.18)
    lo, hi = ax.get_ylim()
    for c in C.CLASSES:
        ax.axvline(mins[c], color=C.CLASS_COLOR[c], ls=":", lw=1.8, zorder=4)
        # label sits beside its own line; the two minima are ~556 ms apart so they
        # cannot collide
        ax.annotate(f"{c} min\n{mins[c]:.0f} ms", xy=(mins[c], hi),
                    xytext=(mins[c] + 12, hi * 0.985),
                    color=C.CLASS_COLOR[c], fontsize=FS_ANNOT, ha="left", va="top",
                    zorder=5)

    ax.set_xlabel("launch-to-crossing time (ms)", color=C.INK, fontsize=FS_LABEL)
    ax.set_ylabel("flight count", color=C.INK, fontsize=FS_LABEL)
    ax.tick_params(labelsize=FS_TICK)
    ax.set_title("Launch-to-crossing duration distribution, n=107 crossing flights",
                 color=C.INK, fontsize=FS_TITLE, loc="left", pad=12)
    ax.legend(frameon=False, fontsize=FS_LABEL, labelcolor=C.INK2, loc="upper right")

    short_max, long_min = max(vals["SHORT"]), mins["LONG"]
    confusion = [v for v in vals["SHORT"] if v > long_min]
    # Lines kept to ~135 characters: at the enlarged caption size, longer lines
    # overflow the right edge of the canvas and get clipped.
    caption = [
        "Launch-to-crossing time, NOT observable track length. Overlaid, not stacked.",
        "Dotted verticals mark each class's MINIMUM only - the statistic the min-anchored deadline rule uses.",
        "The earlier n=158 duration figure plotted a different quantity (total observable duration, first usable fit frame to held-out",
        "target) on a different population (all fitted flights, not crossers only). The two are not comparable.",
        f"Confusion region of the 45-deg elevation proxy: {len(confusion)} SHORT flights cross later than LONG's minimum ({long_min:.1f} ms); SHORT max is {short_max:.1f} ms.",
    ]
    gap, floor_y = 0.0165, 0.010
    start_y = floor_y + (len(caption) - 1) * gap
    for i, line in enumerate(caption):
        fig.text(0.008, start_y - i * gap, line, color=C.INK2, fontsize=FS_CAP)

    fig.tight_layout(rect=[0, start_y + 0.030, 1, 1])
    fig.savefig(OUT_PNG, dpi=150, facecolor=C.SURF)
    plt.close(fig)
    print(f"wrote {OUT_PNG}")
    print("original figureC_duration_distribution.png left untouched")


if __name__ == "__main__":
    main()
