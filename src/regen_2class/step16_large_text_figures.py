"""Step 16 - large-text re-renders of two figures, for print in the report.

Creates NEW files. Nothing existing is overwritten:
    02_chaos_landing_error/figure_chaos_landing_error_500mm_large.png
    figureD_outcome_sweep_large.png

Numbers are identical to the originals - the verdict machinery is imported from
the scripts that produced them (step13_chaos_sweep_landing_error, step_7_figure_d_outcome)
rather than reimplemented, so only font sizes, figure size and caption line breaks
differ.

Caption lines are RE-WRAPPED, not just re-sized. At the enlarged size the original
line lengths overflow the right edge of the canvas and get silently clipped; every
caption line here is held to a width that fits.
"""
import pathlib
import sys

# This folder carries two import conventions: step_1..step_7 use
# "regen_2class.common" (needs src/ on the path), step8..step15 use "common"
# (needs src/regen_2class/ on the path). Both are added so this script can import
# from either set without editing them.
_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common as C
from step10_chaos_outcome_sweep import load_per_axis
import step13_chaos_sweep_landing_error as LE
import step_7_figure_d_outcome as FD

OUT_LE = LE.OUT_DIR + "figure_chaos_landing_error_500mm_large.png"
OUT_FD = C.OUT_DIR + "figureD_outcome_sweep_large.png"

# enlarged type scale, shared by both figures
FS_SUPTITLE, FS_PANEL, FS_AXIS, FS_TICK = 22, 15, 16, 12
FS_XTICK, FS_LEGEND, FS_ANNOT, FS_CAP = 11, 15, 12, 10.5


def draw_panels(fig, axes, windows, panels, counts_of, best_of, n_of, band_order,
                band_color, keep_of, xtick_step=1):
    """Shared stacked-bar panel drawing at the enlarged type scale."""
    for ax, key in zip(axes, panels):
        C.style_axes(ax, grid_axis="y")
        label, counts, best = key["label"], counts_of(key), best_of(key)
        keep = keep_of(key)
        xs = list(range(len(keep)))
        bottom = [0] * len(keep)
        for b in band_order:
            vals = [counts[b][i] for i in keep]
            ax.bar(xs, vals, bottom=bottom, color=band_color[b], width=0.8,
                   edgecolor=C.SURF, linewidth=0.8, zorder=3,
                   label=b if key.get("first") else None)
            bottom = [p + q for p, q in zip(bottom, vals)]
        n = n_of(key)
        # step13's best dict carries "idx"; step_7's does not, so derive it from
        # the selected window rather than requiring both to expose the same key.
        best_idx = best.get("idx", windows.index(best["window"])) if best else None
        if best_idx is not None and best_idx in keep:
            bi = keep.index(best_idx)
            ax.axvline(bi, color=C.INK2, ls=":", lw=1.6, zorder=4)
            ax.annotate(f"best {best['window']} ms   {best['rate']:.1f}%",
                        xy=(bi, n), xytext=(bi + 0.5, n * 1.04),
                        color=C.INK, fontsize=FS_ANNOT, ha="left", va="bottom", zorder=5)
        ax.set_ylim(0, n * 1.18)
        ax.set_title(label, color=C.INK, fontsize=FS_PANEL, loc="left", pad=6)
        ax.set_ylabel("flights", color=C.INK, fontsize=FS_AXIS)
        ax.tick_params(labelsize=FS_TICK)
        ax.set_xticks(xs)
        ax.set_xticklabels([str(windows[i]) if (j % xtick_step == 0) else ""
                            for j, i in enumerate(keep)], rotation=90, fontsize=FS_XTICK)


def caption_block(fig, lines, gap=0.0125, floor_y=0.010, fontsize=FS_CAP):
    """Anchor the LAST line at a fixed height and grow upward, so a longer
    caption cannot run off the bottom. Returns the rect bottom to use."""
    start_y = floor_y + (len(lines) - 1) * gap
    for i, line in enumerate(lines):
        fig.text(0.006, start_y - i * gap, line, color=C.INK2, fontsize=fontsize)
    return start_y + 0.022


# --------------------------------------------------------------------------
def landing_error_500mm_large(rows, per_axis, windows, max_ltc, n_class):
    threshold, anchor = 500.0, "arm's reach, stationary player"
    results = {}
    for A in LE.A_VALUES:
        pr, counts, rate, best = LE.evaluate(rows, per_axis, windows, A, threshold,
                                             LE.FAILURES_COMBINED, LE.BAND_ORDER, n_class)
        results[A] = dict(counts=counts, best=best)
        print(f"  [A={A:.0f}] " + "  ".join(
            f"{c} best {best[c]['window']}ms {best[c]['rate']:.1f}%" for c in C.CLASSES))

    fig, axgrid = plt.subplots(3, 2, figsize=(19.0, 15.0), sharex=True)
    fig.patch.set_facecolor(C.SURF)
    keys, axes = [], []
    for row_i, A in enumerate(LE.A_VALUES):
        for col_i, cls in enumerate(C.CLASSES):
            keys.append(dict(A=A, cls=cls, label=f"{cls}  (n={n_class[cls]})   A = {A:.0f} ms",
                             first=(row_i == 0 and col_i == 0)))
            axes.append(axgrid[row_i][col_i])
    draw_panels(fig, axes, windows, keys,
                counts_of=lambda k: results[k["A"]]["counts"][k["cls"]],
                best_of=lambda k: results[k["A"]]["best"][k["cls"]],
                n_of=lambda k: n_class[k["cls"]],
                band_order=LE.BAND_ORDER, band_color=LE.BAND_COLOR,
                keep_of=lambda k: [i for i, w in enumerate(windows) if w <= max_ltc[k["cls"]]])
    for col_i in range(2):
        axgrid[-1][col_i].set_xlabel(C.X_LABEL, color=C.INK, fontsize=FS_AXIS)

    handles, _ = axes[0].get_legend_handles_labels()
    fig.legend(handles, LE.BAND_ORDER, frameon=False, fontsize=FS_LEGEND,
               labelcolor=C.INK2, loc="upper center", bbox_to_anchor=(0.5, 0.972), ncol=5)
    fig.suptitle(f"Chaos-rally outcome sweep, combined landing-error criterion "
                 f"<= {threshold:.0f} mm  ({anchor})",
                 color=C.INK, fontsize=FS_SUPTITLE, x=0.006, ha="left", y=0.995)

    vel_equiv = threshold / (LE.E_COR * LE.T_RETURN_S)
    caption = [
        f"landing_error = |dp| + e*|dv|*t, e = {LE.E_COR}, t = {LE.T_RETURN_S:.1f} s. A total landing-error allowance at the player of {threshold:.0f} mm.",
        f"Because the budget is not split between the two terms, a flight with small position error may spend the whole allowance on velocity,",
        f"corresponding to {vel_equiv:.0f} mm/s - {vel_equiv/LE.Y_WIDTH_LABEL_SD:.1f}x the ~{LE.Y_WIDTH_LABEL_SD:.0f} mm/s Y_width label SD, so the test remains above the reference noise floor on the weak axis.",
        "Position and velocity errors are CONVERGENCE against the full-arc Model-C fit, NOT accuracy against ground truth.",
        "|dp| is the crossing-position error magnitude; it is a two-component in-plane distance and that IS its 3D magnitude, because both the",
        "predicted and reference crossing points lie on the plane by construction.",
        "Chaos rally needs the answer A ms BEFORE arrival: late is t_obs + latency > launch_to_crossing - A, opposite in sign to target mode's",
        "+84 ms after. t_obs = min(observation window, duration). Verdict precedence first-match-wins: no_response, late, wrong_class,",
        "wrong_placement, success. Where several windows tie at the maximum success rate the LATEST is selected.",
        "fit_failed rows are retained as no_response; the denominator is always the class n. Each class is truncated at its own maximum",
        "launch-to-crossing time. A = 72 / 135 / 220 ms are panel tilt moves of 2, 10 and 30 degrees.",
    ]
    rect_bottom = caption_block(fig, caption)
    fig.tight_layout(rect=[0, rect_bottom, 1, 0.955])
    fig.savefig(OUT_LE, dpi=150, facecolor=C.SURF)
    plt.close(fig)
    print(f"wrote {OUT_LE}")


# --------------------------------------------------------------------------
def figure_d_large(rows, windows):
    per_rows, n_of, counts, rate, best = FD.evaluate(rows, windows, FD.ACCURATE_MM_MAIN)
    for p in FD.PANELS:
        print(f"  {p}: best {best[p]['window']} ms  {best[p]['rate']:.1f}%")

    fig, axarr = plt.subplots(3, 1, figsize=(16.0, 15.0), sharex=True)
    fig.patch.set_facecolor(C.SURF)
    keys = [dict(panel=p, label=f"{p}  (n={n_of[p]})", first=(i == 0))
            for i, p in enumerate(FD.PANELS)]
    all_idx = list(range(len(windows)))
    draw_panels(fig, list(axarr), windows, keys,
                counts_of=lambda k: counts[k["panel"]],
                best_of=lambda k: best[k["panel"]],
                n_of=lambda k: n_of[k["panel"]],
                band_order=C.BAND_ORDER, band_color=C.BAND_COLOR,
                keep_of=lambda k: all_idx)
    axarr[-1].set_xlabel(C.X_LABEL, color=C.INK, fontsize=FS_AXIS)

    handles, _ = axarr[0].get_legend_handles_labels()
    fig.legend(handles, C.BAND_ORDER, frameon=False, fontsize=FS_LEGEND,
               labelcolor=C.INK2, loc="upper center", bbox_to_anchor=(0.5, 0.972), ncol=4)
    # Shortened from the original wording: at FS_SUPTITLE the full sentence is
    # wider than the canvas and the trailing "200 mm)" is clipped.
    fig.suptitle(f"Per-flight outcome vs observation window, two-class scheme "
                 f"(accuracy threshold {FD.ACCURATE_MM_MAIN:.0f} mm)",
                 color=C.INK, fontsize=FS_SUPTITLE, x=0.006, ha="left", y=0.995)

    caption = [
        "POOLED is the performance of a system with no regime classifier. SHORT and LONG are the achievable performance if the class",
        "were known at prediction time.",
        "Verdict precedence, first match wins: not answered -> no_response; not in_time -> late; not accurate -> wrong; otherwise success.",
        f"in_time = t_obs + latency <= launch_to_crossing + {C.TARGET_SLACK_MS:.0f} ms, t_obs = min(observation window, duration).",
        f"accurate = position error < {FD.ACCURATE_MM_MAIN:.0f} mm, which is CONVERGENCE against the full-arc Model-C fit, NOT ground truth.",
        "fit_failed rows are retained as no_response; the denominator is always the panel n.",
    ]
    rect_bottom = caption_block(fig, caption)
    fig.tight_layout(rect=[0, rect_bottom, 1, 0.955])
    fig.savefig(OUT_FD, dpi=150, facecolor=C.SURF)
    plt.close(fig)
    print(f"wrote {OUT_FD}")


def main():
    rows = C.load_join()
    windows = C.windows_of(rows)
    per_axis = load_per_axis()
    durations = C.class_durations(rows)
    n_class = {c: len(v) for c, v in durations.items()}
    max_ltc = {c: max(v) for c, v in durations.items()}

    print("landing-error 500 mm, large text:")
    landing_error_500mm_large(rows, per_axis, windows, max_ltc, n_class)
    print("\nfigure D, large text:")
    figure_d_large(rows, windows)
    print("\nboth originals left untouched")


if __name__ == "__main__":
    main()
