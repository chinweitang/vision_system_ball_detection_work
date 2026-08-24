"""Figure C - launch-to-crossing duration distribution, crossers only.

Reads results/regenerate_figures/two_class_join.csv and writes
figureC_duration_distribution.png at 150 dpi.

Overlaid (not stacked) histogram, one colour per class, with vertical markers at
min / P5 / median / max per class. Marker VALUES are listed in two compact
per-class text blocks rather than rotated onto each line: SHORT's min (491) and P5
(508) are only 17 ms apart, so on-line rotated labels collide illegibly.

Also reports the confusion region of the 45-degree elevation proxy: SHORT flights
whose launch-to-crossing time exceeds LONG's minimum.
"""
import csv
import statistics as st

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

JOIN = "results/regenerate_figures/two_class_join.csv"
OUT = "results/regenerate_figures/figureC_duration_distribution.png"

SURF, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
COL = {"SHORT": "#2a78d6", "LONG": "#e34948"}
CLASSES = ["SHORT", "LONG"]


def percentile(values, p):
    v = sorted(values)
    k = (len(v) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def style_axes(ax):
    ax.set_facecolor(SURF)
    ax.grid(True, color="#e5e4df", lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#d5d4cf")
    ax.tick_params(colors=INK2, labelsize=9)


def main():
    rows = list(csv.DictReader(open(JOIN, encoding="utf-8")))
    # collapse the 24-rows-per-flight grid down to one row per flight
    per_flight = {(r["session"], r["flight"]): (r["cls2"], float(r["launch_to_crossing_ms"]))
                  for r in rows}
    vals = {c: sorted(d for cls, d in per_flight.values() if cls == c) for c in CLASSES}
    stats = {c: {"min": min(vals[c]), "P5": percentile(vals[c], 0.05),
                 "median": st.median(vals[c]), "max": max(vals[c])} for c in CLASSES}

    fig, ax = plt.subplots(figsize=(10, 6.0))
    fig.patch.set_facecolor(SURF)
    style_axes(ax)

    bins = np.linspace(min(vals["SHORT"] + vals["LONG"]),
                       max(vals["SHORT"] + vals["LONG"]), 29)
    for c in CLASSES:
        ax.hist(vals[c], bins=bins, color=COL[c], alpha=0.55, edgecolor=COL[c],
                lw=1.3, zorder=3, label=f"{c} (n={len(vals[c])})")

    for c in CLASSES:
        for value in stats[c].values():
            ax.axvline(value, color=COL[c], ls=":", lw=1.2, zorder=4)

    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, hi * 1.12)

    # Two compact blocks in the empty band between the SHORT and LONG clusters.
    for i, c in enumerate(CLASSES):
        s = stats[c]
        text = (f"{c}\n"
                f"min     {s['min']:.0f}\n"
                f"P5      {s['P5']:.0f}\n"
                f"median  {s['median']:.0f}\n"
                f"max     {s['max']:.0f}")
        ax.annotate(text, xy=(0.40, 0.95 - i * 0.30), xycoords="axes fraction",
                    color=COL[c], fontsize=8.4, ha="left", va="top",
                    family="monospace",
                    bbox=dict(boxstyle="round,pad=0.35", fc=SURF, ec=COL[c], lw=0.9, alpha=0.92))

    short_max = stats["SHORT"]["max"]
    long_min = stats["LONG"]["min"]
    confusion = [v for v in vals["SHORT"] if v > long_min]

    ax.set_xlabel("launch-to-crossing time (ms)", color=INK, fontsize=10.5)
    ax.set_ylabel("flight count", color=INK, fontsize=10.5)
    ax.set_title("Launch-to-crossing duration distribution, n=107 crossing flights",
                 color=INK, fontsize=12.5, loc="left", pad=12)
    ax.legend(frameon=False, fontsize=9.5, labelcolor=INK2, loc="upper right")

    caption = [
        "Launch-to-crossing time, NOT observable track length. Overlaid, not stacked. Dotted verticals mark each class's min / P5 / median / max.",
        "The earlier n=158 duration figure plotted a different quantity (total observable duration, first usable fit frame to held-out target) on a",
        f"different population (all fitted flights, not crossers only). The two are not comparable. Confusion region of the 45-deg elevation proxy:",
        f"{len(confusion)} SHORT flights cross later than LONG's minimum ({long_min:.1f} ms); SHORT max is {short_max:.1f} ms.",
    ]
    for i, line in enumerate(caption):
        fig.text(0.012, 0.056 - i * 0.0165, line, color=INK2, fontsize=7.6)

    fig.tight_layout(rect=[0, 0.085, 1, 1])
    fig.savefig(OUT, dpi=150, facecolor=SURF)
    plt.close(fig)

    print(f"SHORT max = {short_max:.1f} ms")
    print(f"LONG  min = {long_min:.1f} ms")
    print(f"confusion region = {len(confusion)} SHORT flights: "
          f"{', '.join(f'{v:.1f}' for v in sorted(confusion))}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
