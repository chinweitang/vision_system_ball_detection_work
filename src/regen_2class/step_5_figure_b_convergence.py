"""Step 5 - Figure B: position-error convergence vs observation window.

Median position_error_mm per class per window with an IQR band. status=='fit_failed'
rows are excluded from the median; the excluded count per class per window is
printed beneath the plot, listed in the log, and written to
figureB_excluded_counts.csv.

position_error_mm is CONVERGENCE against the full-arc Model-C fit, NOT accuracy
against ground truth. Every caption says so.

Writes figureB_position_error_convergence.png (150 dpi) and
figureB_excluded_counts.csv.
"""
import csv
import pathlib
import statistics as st
import sys

# This script imports "regen_2class.common" (needs src/ on the path); the shared
# clean_figures helper sits beside it and is imported bare, like the step8+ scripts.
_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import regen_2class.common as C
import clean_figures as CF

FIG = C.OUT_DIR + "figureB_position_error_convergence.png"
COUNTS_CSV = C.OUT_DIR + "figureB_excluded_counts.csv"


def main():
    rows = C.load_join()
    windows = C.windows_of(rows)
    max_window = C.max_usable_window(rows, windows)
    n_of = {c: len({(r["session"], r["flight"]) for r in rows if r["cls2"] == c})
            for c in C.CLASSES}

    med, q1, q3, excluded = {}, {}, {}, {}
    for c in C.CLASSES:
        med[c], q1[c], q3[c], excluded[c] = [], [], [], []
        for w in windows:
            sub = [r for r in rows if r["cls2"] == c and int(r["T_ms"]) == w]
            ok = [float(r["position_error_mm"]) for r in sub if r["status"] == "ok"]
            excluded[c].append(sum(1 for r in sub if r["status"] == "fit_failed"))
            med[c].append(st.median(ok))
            q1[c].append(C.percentile(ok, 0.25))
            q3[c].append(C.percentile(ok, 0.75))

    fig, ax = plt.subplots(figsize=(10, 6.2))
    fig.patch.set_facecolor(C.SURF)
    C.style_axes(ax)
    for c in C.CLASSES:
        ax.fill_between(windows, q1[c], q3[c], color=C.CLASS_COLOR[c],
                        alpha=0.15, lw=0, zorder=2)
        ax.plot(windows, med[c], color=C.CLASS_COLOR[c], lw=2.0, marker="o", ms=5,
                mec=C.SURF, mew=1.2, zorder=3,
                label=f"{c} median, n={n_of[c]} (shaded = IQR)")
    lo, hi = ax.get_ylim()
    for c in C.CLASSES:
        ax.axvline(max_window[c], color=C.CLASS_COLOR[c], ls=":", lw=1.5, zorder=2)
        ax.annotate(f"max usable window {max_window[c]} ms",
                    xy=(max_window[c], hi), xytext=(max_window[c] - 14, hi - 0.03 * (hi - lo)),
                    color=C.CLASS_COLOR[c], fontsize=8.5, rotation=90, ha="right", va="top")
    ax.set_ylim(lo, hi)
    ax.set_xlabel(f"{C.X_LABEL}   -   dotted verticals = max usable window from Figure A",
                  color=C.INK, fontsize=10.5)
    ax.set_ylabel("crossing-point position error, median (mm)", color=C.INK, fontsize=10.5)
    ax.set_title("Position-error CONVERGENCE vs observation window, two-class scheme",
                 color=C.INK, fontsize=12.5, loc="left", pad=12)
    ax.legend(frameon=False, fontsize=9.5, labelcolor=C.INK2, loc="upper right")

    caption = [
        "CONVERGENCE against the full-arc Model-C fit, NOT ground truth. This is agreement with the reference fit, not accuracy against labels.",
        "fit_failed rows excluded from the median. Excluded count per window (ascending) - SHORT: " + ",".join(str(x) for x in excluded["SHORT"]),
        "LONG: " + ",".join(str(x) for x in excluded["LONG"]) + f".  Denominators: SHORT n={n_of['SHORT']}, LONG n={n_of['LONG']}.",
    ]
    if CF.clean():
        CF.write_clean(fig, caption, FIG)
    else:
        for i, line in enumerate(caption):
            fig.text(0.012, 0.042 - i * 0.018, line, color=C.INK2, fontsize=7.8)

        fig.tight_layout(rect=[0, 0.075, 1, 1])
        fig.savefig(FIG, dpi=150, facecolor=C.SURF)
    plt.close(fig)

    with open(COUNTS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cls2", "T_ms", "n_total", "n_ok", "n_fit_failed",
                    "median_mm", "q1_mm", "q3_mm"])
        for c in C.CLASSES:
            for i, win in enumerate(windows):
                w.writerow([c, win, n_of[c], n_of[c] - excluded[c][i], excluded[c][i],
                            f"{med[c][i]:.4f}", f"{q1[c][i]:.4f}", f"{q3[c][i]:.4f}"])

    print(f"max usable window: {max_window}")
    print(f"total excluded: SHORT {sum(excluded['SHORT'])}, LONG {sum(excluded['LONG'])}, "
          f"combined {sum(excluded['SHORT']) + sum(excluded['LONG'])}")
    for c in C.CLASSES:
        i = windows.index(max_window[c])
        print(f"  {c} median at max usable window ({max_window[c]} ms) = {med[c][i]:.1f} mm")
    print(f"wrote {FIG}")
    print(f"wrote {COUNTS_CSV}")


if __name__ == "__main__":
    main()
