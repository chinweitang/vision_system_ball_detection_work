"""Step 17 - four figures re-rendered AT PRINT SIZE for the report.

Creates NEW files; nothing existing is overwritten:
    02_chaos_landing_error/figure_chaos_landing_error_500mm_print.png
    figureD_outcome_sweep_print.png
    figureB_position_error_convergence_print.png
    figureG_velocity_by_axis_twoclass_print.png

SIZING APPROACH - why this is not "the same figure with bigger fonts"
---------------------------------------------------------------------
The target is legibility at 0.8 of an A4 page width = 0.8 * 210 mm = 168 mm
= 6.6 in. Enlarging fonts on a 16-20 in canvas is counterproductive: that canvas
is shrunk ~3x to reach 6.6 in on the page, so a 15 pt tick label prints at ~5 pt.

Instead each figure is built AT its final printed width (PAGE_W_IN), so the scale
factor is 1:1 and the font sizes below are the actual point sizes on the page.
Rendered at 300 dpi for print. Body text in a report is ~10-11 pt, so figure text
at 7-11 pt reads correctly alongside it.

Captions are omitted from the figures; the report document carries them. The full
caption text for each is preserved in the docstrings of step16/step13 and in the
comments below.

Numbers are identical to the originals - all verdict/statistic machinery is
imported from the scripts that produced them, or reproduces their computation
line-for-line where it was inline. Nothing is re-fitted and no Pi job is re-run.
"""
import math
import pathlib
import statistics as st
import sys

# step_1..step_7 import "regen_2class.common"; step8..step16 import "common".
_HERE = pathlib.Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common as C
import clean_figures as CF
from step10_chaos_outcome_sweep import (
    AXIS_TITLE, LABEL_FLOOR, load_per_axis, render_velocity_figure,  # noqa: F401
)
import step10_chaos_outcome_sweep as S10
import step13_chaos_sweep_landing_error as LE
import step_7_figure_d_outcome as FD

PAGE_W_IN = 6.6          # 0.8 x A4 width (210 mm)
DPI = 300

# Actual point sizes on the printed page, since the figure is built 1:1.
FS_SUPTITLE, FS_PANEL, FS_AXIS = 11, 9, 9.5
FS_TICK, FS_XTICK, FS_LEGEND, FS_ANNOT = 8, 6.5, 8, 7.5

OUT_LE = LE.OUT_DIR + "figure_chaos_landing_error_500mm_print.png"
OUT_FD = C.OUT_DIR + "figureD_outcome_sweep_print.png"
OUT_B = C.OUT_DIR + "figureB_position_error_convergence_print.png"
OUT_G = C.OUT_DIR + "figureG_velocity_by_axis_twoclass_print.png"


def style(ax, grid_axis="both"):
    C.style_axes(ax, grid_axis=grid_axis)
    ax.tick_params(labelsize=FS_TICK)


def stacked_panels(axes, windows, keys, counts_of, best_of, n_of, band_order,
                   band_color, keep_of, xtick_every=1):
    for ax, key in zip(axes, keys):
        style(ax, grid_axis="y")
        counts, best, n = counts_of(key), best_of(key), n_of(key)
        keep = keep_of(key)
        xs = list(range(len(keep)))
        bottom = [0] * len(keep)
        for b in band_order:
            vals = [counts[b][i] for i in keep]
            ax.bar(xs, vals, bottom=bottom, color=band_color[b], width=0.82,
                   edgecolor=C.SURF, linewidth=0.4, zorder=3,
                   label=b if key.get("first") else None)
            bottom = [p + q for p, q in zip(bottom, vals)]
        best_idx = best.get("idx", windows.index(best["window"])) if best else None
        if best_idx is not None and best_idx in keep:
            bi = keep.index(best_idx)
            ax.axvline(bi, color=C.INK2, ls=":", lw=1.0, zorder=4)
            ax.annotate(f"best {best['window']} ms  {best['rate']:.1f}%",
                        xy=(bi, n), xytext=(bi + 0.4, n * 1.05),
                        color=C.INK, fontsize=FS_ANNOT, ha="left", va="bottom", zorder=5)
        ax.set_ylim(0, n * 1.22)
        ax.set_title(key["label"], color=C.INK, fontsize=FS_PANEL, loc="left", pad=3)
        ax.set_ylabel("flights", color=C.INK, fontsize=FS_AXIS)
        ax.set_xticks(xs)
        ax.set_xticklabels([str(windows[i]) if (j % xtick_every == 0) else ""
                            for j, i in enumerate(keep)], rotation=90, fontsize=FS_XTICK)


# ---------------------------------------------------------------- landing error
def landing_error_print(rows, per_axis, windows, max_ltc, n_class):
    threshold = 500.0
    results = {}
    for A in LE.A_VALUES:
        _, counts, _, best = LE.evaluate(rows, per_axis, windows, A, threshold,
                                         LE.FAILURES_COMBINED, LE.BAND_ORDER, n_class)
        results[A] = dict(counts=counts, best=best)
        print("  [A=%3.0f] " % A + "  ".join(
            f"{c} {best[c]['window']}ms {best[c]['rate']:.1f}%" for c in C.CLASSES))

    fig, grid = plt.subplots(3, 2, figsize=(PAGE_W_IN, 7.6), sharex=True)
    fig.patch.set_facecolor(C.SURF)
    keys, axes = [], []
    for row_i, A in enumerate(LE.A_VALUES):
        for col_i, cls in enumerate(C.CLASSES):
            keys.append(dict(A=A, cls=cls,
                             label=f"{cls} (n={n_class[cls]})  A = {A:.0f} ms",
                             first=(row_i == 0 and col_i == 0)))
            axes.append(grid[row_i][col_i])
    # two narrow columns of 21-24 bars: label every other window so the rotated
    # ticks do not collide at this width
    stacked_panels(axes, windows, keys,
                   counts_of=lambda k: results[k["A"]]["counts"][k["cls"]],
                   best_of=lambda k: results[k["A"]]["best"][k["cls"]],
                   n_of=lambda k: n_class[k["cls"]],
                   band_order=LE.BAND_ORDER, band_color=LE.BAND_COLOR,
                   keep_of=lambda k: [i for i, w in enumerate(windows)
                                      if w <= max_ltc[k["cls"]]],
                   xtick_every=2)
    for col_i in range(2):
        grid[-1][col_i].set_xlabel(C.X_LABEL, color=C.INK, fontsize=FS_AXIS)
    handles, _ = axes[0].get_legend_handles_labels()
    fig.legend(handles, LE.BAND_ORDER, frameon=False, fontsize=FS_LEGEND,
               labelcolor=C.INK2, loc="upper center", bbox_to_anchor=(0.5, 0.955),
               ncol=3, columnspacing=1.2, handlelength=1.4)
    fig.suptitle(f"Chaos-rally outcome, combined landing error <= {threshold:.0f} mm\n"
                 f"(arm's reach, stationary player)",
                 color=C.INK, fontsize=FS_SUPTITLE, x=0.01, ha="left", y=0.998)
    # This script never drew a caption on the canvas (see the module
    # docstring); clean mode therefore only re-sizes and records that fact.
    if CF.clean():
        CF.write_clean(fig, [], OUT_LE)
    else:
        fig.tight_layout(rect=[0, 0.005, 1, 0.885])
        fig.savefig(OUT_LE, dpi=DPI, facecolor=C.SURF)
    plt.close(fig)
    print(f"wrote {OUT_LE}")


# --------------------------------------------------------------------- figure D
def figure_d_print(rows, windows):
    _, n_of, counts, _, best = FD.evaluate(rows, windows, FD.ACCURATE_MM_MAIN)
    for p in FD.PANELS:
        print(f"  {p}: {best[p]['window']} ms  {best[p]['rate']:.1f}%")

    fig, axarr = plt.subplots(3, 1, figsize=(PAGE_W_IN, 7.2), sharex=True)
    fig.patch.set_facecolor(C.SURF)
    keys = [dict(panel=p, label=f"{p} (n={n_of[p]})", first=(i == 0))
            for i, p in enumerate(FD.PANELS)]
    all_idx = list(range(len(windows)))
    stacked_panels(list(axarr), windows, keys,
                   counts_of=lambda k: counts[k["panel"]],
                   best_of=lambda k: best[k["panel"]],
                   n_of=lambda k: n_of[k["panel"]],
                   band_order=C.BAND_ORDER, band_color=C.BAND_COLOR,
                   keep_of=lambda k: all_idx)
    axarr[-1].set_xlabel(C.X_LABEL, color=C.INK, fontsize=FS_AXIS)
    handles, _ = axarr[0].get_legend_handles_labels()
    fig.legend(handles, C.BAND_ORDER, frameon=False, fontsize=FS_LEGEND,
               labelcolor=C.INK2, loc="upper center", bbox_to_anchor=(0.5, 0.962),
               ncol=4, columnspacing=1.2, handlelength=1.4)
    fig.suptitle(f"Per-flight outcome vs observation window "
                 f"(accuracy threshold {FD.ACCURATE_MM_MAIN:.0f} mm)",
                 color=C.INK, fontsize=FS_SUPTITLE, x=0.01, ha="left", y=0.998)
    # This script never drew a caption on the canvas (see the module
    # docstring); clean mode therefore only re-sizes and records that fact.
    if CF.clean():
        CF.write_clean(fig, [], OUT_FD)
    else:
        fig.tight_layout(rect=[0, 0.005, 1, 0.925])
        fig.savefig(OUT_FD, dpi=DPI, facecolor=C.SURF)
    plt.close(fig)
    print(f"wrote {OUT_FD}")


# --------------------------------------------------------------------- figure B
def figure_b_print(rows, windows, max_window, n_of):
    """Same computation as step_5_figure_b_convergence: median + IQR of
    position_error_mm per class per window, fit_failed rows excluded."""
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
    print(f"  excluded fit_failed: SHORT {sum(excluded['SHORT'])}, "
          f"LONG {sum(excluded['LONG'])}, total "
          f"{sum(excluded['SHORT']) + sum(excluded['LONG'])}")
    for c in C.CLASSES:
        print(f"  {c} median at max usable window {max_window[c]} ms = "
              f"{med[c][windows.index(max_window[c])]:.1f} mm")

    fig, ax = plt.subplots(figsize=(PAGE_W_IN, 4.0))
    fig.patch.set_facecolor(C.SURF)
    style(ax)
    for c in C.CLASSES:
        ax.fill_between(windows, q1[c], q3[c], color=C.CLASS_COLOR[c],
                        alpha=0.15, lw=0, zorder=2)
        ax.plot(windows, med[c], color=C.CLASS_COLOR[c], lw=1.4, marker="o", ms=3,
                mec=C.SURF, mew=0.6, zorder=3,
                label=f"{c} median, n={n_of[c]} (shaded = IQR)")
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, hi * 1.06)
    lo, hi = ax.get_ylim()
    for c in C.CLASSES:
        ax.axvline(max_window[c], color=C.CLASS_COLOR[c], ls=":", lw=1.0, zorder=2)
        ax.annotate(f"max usable {max_window[c]} ms",
                    xy=(max_window[c], hi), xytext=(max_window[c] - 12, hi * 0.99),
                    color=C.CLASS_COLOR[c], fontsize=FS_ANNOT, rotation=90,
                    ha="right", va="top")
    ax.set_xlabel(C.X_LABEL, color=C.INK, fontsize=FS_AXIS)
    ax.set_ylabel("position error, median (mm)", color=C.INK, fontsize=FS_AXIS)
    ax.set_title("Position-error CONVERGENCE vs observation window",
                 color=C.INK, fontsize=FS_SUPTITLE, loc="left", pad=6)
    ax.legend(frameon=False, fontsize=FS_LEGEND, labelcolor=C.INK2, loc="upper right")
    # This script never drew a caption on the canvas (see the module
    # docstring); clean mode therefore only re-sizes and records that fact.
    if CF.clean():
        CF.write_clean(fig, [], OUT_B)
    else:
        fig.tight_layout()
        fig.savefig(OUT_B, dpi=DPI, facecolor=C.SURF)
    plt.close(fig)
    print(f"wrote {OUT_B}")


# --------------------------------------------------------------------- figure G
def figure_g_print(rows, per_axis, windows, max_ltc, op_window):
    """Same computation as step10.render_velocity_figure: per-axis signed bias
    (mean) and scatter RMS per class per window, with the decision-77 floor band."""
    fig, axes = plt.subplots(3, 1, figsize=(PAGE_W_IN, 7.4))
    fig.patch.set_facecolor(C.SURF)
    for j, ax_key in enumerate(("x", "y", "z")):
        ax = axes[j]
        style(ax)
        floor = LABEL_FLOOR[ax_key]
        ax.axhspan(-floor, floor, color="#8a8a84", alpha=0.13, lw=0, zorder=1)
        ax.axhline(0.0, color="#d5d4cf", lw=0.8, zorder=1)
        for cls in C.CLASSES:
            xs, bias, rms = [], [], []
            for w in windows:
                if w > max_ltc[cls]:
                    continue
                vals = [per_axis[(r["session"], r["flight"], w)][j] for r in rows
                        if r["cls2"] == cls and int(r["T_ms"]) == w and r["status"] == "ok"]
                if not vals:
                    continue
                xs.append(w)
                bias.append(st.mean(vals))
                rms.append(math.sqrt(sum(v * v for v in vals) / len(vals)))
            ax.fill_between(xs, [b - r for b, r in zip(bias, rms)],
                            [b + r for b, r in zip(bias, rms)],
                            color=C.CLASS_COLOR[cls], alpha=0.13, lw=0, zorder=2)
            ax.plot(xs, bias, color=C.CLASS_COLOR[cls], lw=1.4, marker="o", ms=2.5,
                    mec=C.SURF, mew=0.5, zorder=3, label=cls if j == 0 else None)
        lo, hi = ax.get_ylim()
        for cls in C.CLASSES:
            if op_window[cls] is not None:
                ax.axvline(op_window[cls], color=C.CLASS_COLOR[cls], ls=":",
                           lw=1.0, zorder=2)
        ax.set_ylim(lo, hi)
        unresolved = " UNRESOLVED" if ax_key == "y" else " validated"
        ax.set_title(f"{AXIS_TITLE[ax_key]} - floor {floor:.0f} mm/s,{unresolved}",
                     color=C.INK, fontsize=FS_PANEL, loc="left", pad=3)
        ax.set_ylabel("bias +/- RMS (mm/s)", color=C.INK, fontsize=FS_AXIS)
        if j == 0:
            ax.legend(frameon=False, fontsize=FS_LEGEND, labelcolor=C.INK2,
                      loc="lower right")
    axes[-1].set_xlabel(C.X_LABEL, color=C.INK, fontsize=FS_AXIS)
    fig.suptitle("Per-axis velocity error vs observation window",
                 color=C.INK, fontsize=FS_SUPTITLE, x=0.01, ha="left", y=0.998)
    # This script never drew a caption on the canvas (see the module
    # docstring); clean mode therefore only re-sizes and records that fact.
    if CF.clean():
        CF.write_clean(fig, [], OUT_G)
    else:
        fig.tight_layout(rect=[0, 0.005, 1, 0.965])
        fig.savefig(OUT_G, dpi=DPI, facecolor=C.SURF)
    plt.close(fig)
    print(f"wrote {OUT_G}")


def main():
    rows = C.load_join()
    windows = C.windows_of(rows)
    per_axis = load_per_axis()
    durations = C.class_durations(rows)
    n_class = {c: len(v) for c, v in durations.items()}
    max_ltc = {c: max(v) for c, v in durations.items()}
    max_window = C.max_usable_window(rows, windows)
    print(f"page width {PAGE_W_IN} in at {DPI} dpi; font sizes are printed points\n")

    print("landing-error 500 mm:")
    landing_error_print(rows, per_axis, windows, max_ltc, n_class)
    print("\nfigure D:")
    figure_d_print(rows, windows)
    print("\nfigure B:")
    figure_b_print(rows, windows, max_window, n_class)
    print("\nfigure G:")
    # Verticals must match the ORIGINAL figureG, which took them from step10's own
    # A=135 ms best windows (six-band verdict, position 100 mm, velocity 1470.6
    # mm/s) - NOT from the later landing-error criterion, which selects LONG 650
    # rather than 700 and would silently change the figure's content.
    _, _, _, _, best135 = S10.evaluate(rows, per_axis, windows, 135.0,
                                       S10.POSITION_THRESHOLD_MM)
    op = {c: (best135[c]["window"] if best135[c]["feasible"] else None)
          for c in C.CLASSES}
    print(f"  operating-window verticals: {op}")
    figure_g_print(rows, per_axis, windows, max_ltc, op)
    print("\nall originals and _large versions left untouched")


if __name__ == "__main__":
    main()
