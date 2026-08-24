"""Step 9 - Figure A, rebuilt IN PLACE to carry both game modes on one axis.

Overwrites results/regenerate_figures/figureA_margin_vs_cutoff.png. No second figure
is produced.

Base is unchanged from step 4: same classes recomputed from the bin column, same
min-anchored deadlines recomputed from launch_to_crossing_ms (nothing hardcoded),
same margin_p95(w) = deadline(class) - w - p95(latency_ms over that class at w),
same axis naming. Each class line is truncated at its own maximum
launch_to_crossing_ms.

What the two readings mean, and why they share one axis:
  margin > 0  chaos rally. Time left after the prediction is ready and before the
              ball arrives, i.e. the budget available for actuation. Read against
              the actuation band.
  margin < 0  target mode. The answer lands after impact, which is tolerable
              provided the display fires inside the perceptual window. Read
              against the -84 ms display budget.

Reads existing outputs only. Nothing re-runs the Pi sweep, detection or fitting.
"""
import csv
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common as C
import clean_figures as CF

FIG = C.OUT_DIR + "figureA_margin_vs_cutoff.png"
TABLE_CSV = C.OUT_DIR + "figureA_thresholds.csv"

# Actuation band, chaos rally. Panel tilt moves for a 2 m x 2 m, 20 kg panel
# rotating about its centre line at 350 Nm output torque, triangular velocity
# profile, plus 20 ms lumped command and settling.
BAND_LO, BAND_NOMINAL, BAND_HI = 72.0, 135.0, 220.0
BAND_LABEL = ("chaos rally: actuation budget\n"
              "(2 deg = 72, 10 deg = 135, 30 deg = 220 ms)")
DISPLAY_LABEL = ("target mode: display budget\n"
                 "(100 ms perceptual window - 16 ms projector lag)")

# Only these two are drawn as verticals; all four appear in the printed table.
DRAWN_THRESHOLDS = [BAND_NOMINAL, C.BUDGET_MS]
TABLE_THRESHOLDS = [BAND_HI, BAND_NOMINAL, BAND_LO, C.BUDGET_MS]

BAND_FILL, BAND_EDGE, ZERO_LINE = "#8a8a84", "#6f6e69", "#d5d4cf"


def largest_window_at_or_above(windows, margins, threshold):
    """Largest observation window whose margin_p95 is still >= threshold.

    Last grid point at or above the threshold - the grid is 50 ms coarse, so the
    true boundary lies between this point and the next one up."""
    ok = [w for w, m in zip(windows, margins) if m >= threshold]
    return max(ok) if ok else None


def main():
    rows = C.load_join()
    windows = C.windows_of(rows)
    deadline = C.deadlines(rows)
    margins, _ = C.margin_p95(rows, windows)
    durations = C.class_durations(rows)
    n_of = {c: len(v) for c, v in durations.items()}
    max_ltc = {c: max(v) for c, v in durations.items()}
    print(f"deadlines recomputed from data: {deadline}")
    print(f"line truncation at each class max launch_to_crossing_ms: "
          f"{ {c: round(v, 1) for c, v in max_ltc.items()} }")

    # median position error at a given class/window, ok rows only
    def median_pos_err(cls, window):
        vals = [float(r["position_error_mm"]) for r in rows
                if r["cls2"] == cls and int(r["T_ms"]) == window and r["status"] == "ok"]
        return st.median(vals) if vals else None

    table = []
    for c in C.CLASSES:
        for thr in TABLE_THRESHOLDS:
            w = largest_window_at_or_above(windows, margins[c], thr)
            table.append(dict(cls=c, threshold_ms=thr, max_window_ms=w,
                              median_position_error_mm=median_pos_err(c, w) if w else None,
                              margin_at_window_ms=(margins[c][windows.index(w)] if w else None)))

    with open(TABLE_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["class", "threshold_ms", "max_feasible_window_ms",
                    "margin_p95_at_window_ms", "median_position_error_mm"])
        for t in table:
            if t["max_window_ms"] is None:
                w.writerow([t["cls"], f"{t['threshold_ms']:+.0f}", "INFEASIBLE", "", ""])
            else:
                w.writerow([t["cls"], f"{t['threshold_ms']:+.0f}", t["max_window_ms"],
                            f"{t['margin_at_window_ms']:.1f}",
                            f"{t['median_position_error_mm']:.1f}"])
    print(f"wrote {TABLE_CSV}")

    print()
    hdr = (f"{'class':6s} {'threshold':>10} {'max window':>11} {'margin@win':>11} "
           f"{'med pos err':>12}")
    print(hdr)
    print("-" * len(hdr))
    for t in table:
        if t["max_window_ms"] is None:
            print(f"{t['cls']:6s} {t['threshold_ms']:>+10.0f} {'INFEASIBLE':>11} "
                  f"{'-':>11} {'-':>12}")
        else:
            print(f"{t['cls']:6s} {t['threshold_ms']:>+10.0f} "
                  f"{t['max_window_ms']:>9d} ms {t['margin_at_window_ms']:>9.1f} ms "
                  f"{t['median_position_error_mm']:>9.1f} mm")

    # ---- figure ----
    fig, ax = plt.subplots(figsize=(11.0, 7.4))
    fig.patch.set_facecolor(C.SURF)
    C.style_axes(ax)

    # Reference layer, all behind the data (data is zorder 3).
    ax.axhspan(BAND_LO, BAND_HI, color=BAND_FILL, alpha=0.15, lw=0, zorder=1)
    ax.axhline(BAND_NOMINAL, color=BAND_EDGE, lw=1.6, zorder=1)
    ax.axhline(0.0, color=ZERO_LINE, lw=1.0, zorder=1)
    ax.axhline(C.BUDGET_MS, color=C.MUTED, ls=(0, (5, 3)), lw=1.6, zorder=2)

    for c in C.CLASSES:
        pts = [(w, m) for w, m in zip(windows, margins[c]) if w <= max_ltc[c]]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=C.CLASS_COLOR[c],
                lw=2.0, marker="o", ms=5, mec=C.SURF, mew=1.2, zorder=3,
                label=f"{c} (n={n_of[c]}, deadline={deadline[c]:.0f} ms)")

    lo, hi = ax.get_ylim()
    for c in C.CLASSES:
        for thr in DRAWN_THRESHOLDS:
            w = largest_window_at_or_above(windows, margins[c], thr)
            if w is None:
                print(f"INFEASIBLE: {c} never reaches margin_p95 >= {thr:+.0f} ms, "
                      f"vertical omitted")
                continue
            ax.axvline(w, color=C.CLASS_COLOR[c], ls=":", lw=1.4, zorder=2)
            # Anchored at the BOTTOM, not the top: LONG sits high on the left, so
            # top-anchored rotated labels get crossed by it. Both classes stay well
            # above the floor at every marked window.
            ax.annotate(f"{c} {thr:+.0f}: {w} ms", xy=(w, lo),
                        xytext=(w - 12, lo + 0.02 * (hi - lo)), color=C.CLASS_COLOR[c],
                        fontsize=8.2, rotation=90, ha="right", va="bottom")

    # Band label: sits in the lower half of the band, where SHORT has already
    # dropped below it and LONG has not yet descended into it. LONG reaches the
    # text band only past ~660 ms, well right of where the text ends.
    # Hung from just under the nominal line so the solid +135 rule does not strike
    # through the first text line, and still clear of the band floor at +72.
    ax.annotate(BAND_LABEL, xy=(windows[0], BAND_NOMINAL),
                xytext=(290, BAND_NOMINAL - 6.0),
                color=BAND_EDGE, fontsize=7.4, ha="left", va="top", zorder=4)
    # Display label: right-aligned above its own line, far enough right that LONG
    # has descended well below it.
    ax.annotate(DISPLAY_LABEL, xy=(windows[-1], C.BUDGET_MS),
                xytext=(windows[-1], C.BUDGET_MS + 0.012 * (hi - lo)),
                color=C.INK2, fontsize=8.2, ha="right", va="bottom", zorder=4)

    ax.set_ylim(lo, hi)
    ax.set_xlabel(C.X_LABEL, color=C.INK, fontsize=10.5)
    ax.set_ylabel("margin_p95 (ms)", color=C.INK, fontsize=10.5)
    ax.set_title("Feasibility margin vs observation window, both game modes "
                 "(worst-case p95 latency)", color=C.INK, fontsize=12.5,
                 loc="left", pad=12)
    ax.legend(frameon=False, fontsize=9.5, labelcolor=C.INK2, loc="upper right")

    caption = [
        "Margin above zero is the time remaining after the prediction is ready and before the ball arrives: the budget available for actuation, read by chaos rally. Margin below zero means the",
        "answer lands after impact, which target mode tolerates provided the display fires inside the perceptual window. Actuation band edges correspond to panel tilt moves of 2, 10 and 30 degrees",
        "for a 2 m x 2 m, 20 kg panel rotating about its centre line at 350 Nm output torque, triangular velocity profile, plus 20 ms lumped command and settling.",
        "margin_p95 = deadline - observation window - p95 latency; deadline is the class minimum launch-to-crossing time rounded down to 10 ms. Verticals mark the LAST grid point at or above each",
        "threshold, so with a 50 ms grid the true boundary lies between that point and the next. Each class line stops at its own maximum launch-to-crossing time. Pi render and compositor latency is neglected.",
    ]
    if CF.clean():
        CF.write_clean(fig, caption, FIG)
    else:
        for i, line in enumerate(caption):
            fig.text(0.008, 0.072 - i * 0.0145, line, color=C.INK2, fontsize=6.9)

        fig.tight_layout(rect=[0, 0.135, 1, 1])
        fig.savefig(FIG, dpi=150, facecolor=C.SURF)
    plt.close(fig)
    print(f"\nwrote {FIG} (overwritten in place, no second figure)")


if __name__ == "__main__":
    main()
