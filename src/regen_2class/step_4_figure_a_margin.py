"""Step 4 - Figure A: feasibility margin vs observation window.

    margin_p95(w) = deadline(class) - w - p95(latency_ms of that class at w)

Deadlines are recomputed from the joined data by the min rule; no deadline value
is hardcoded. The budget reference line is at -84 ms, which is the 100 ms
perceptual window minus the 16 ms projector input lag. That projector figure is an
END-TO-END measurement and already includes the frame period, so panel /
quantisation / render terms are NOT added on top - doing so double-counts. Pi
render and compositor latency is neglected and the caption says so.

Writes figureA_margin_vs_cutoff.png at 150 dpi.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import regen_2class.common as C

FIG = C.OUT_DIR + "figureA_margin_vs_cutoff.png"


def main():
    rows = C.load_join()
    windows = C.windows_of(rows)
    dl = C.deadlines(rows)
    margins, n_ok = C.margin_p95(rows, windows)
    max_window = C.max_usable_window(rows, windows)
    n_of = {c: len(v) for c, v in C.class_durations(rows).items()}

    fig, ax = plt.subplots(figsize=(10, 5.8))
    fig.patch.set_facecolor(C.SURF)
    C.style_axes(ax)

    for c in C.CLASSES:
        ax.plot(windows, margins[c], color=C.CLASS_COLOR[c], lw=2.0, marker="o", ms=5,
                mec=C.SURF, mew=1.2, zorder=3,
                label=f"{c} (n={n_of[c]}, deadline={dl[c]:.0f} ms)")

    # Label lives in the legend, not in-plot: both series sweep monotonically
    # through y=BUDGET_MS, so any horizontal text band near that value is crossed
    # by a data line somewhere along x.
    ax.axhline(C.BUDGET_MS, color=C.MUTED, ls=(0, (5, 3)), lw=1.6, zorder=2,
               label=C.BUDGET_LABEL)
    lo, hi = ax.get_ylim()

    for c in C.CLASSES:
        if max_window[c] is None:
            continue
        ax.axvline(max_window[c], color=C.CLASS_COLOR[c], ls=":", lw=1.5, zorder=2)
        ax.annotate(f"max usable window = {max_window[c]} ms",
                    xy=(max_window[c], hi),
                    xytext=(max_window[c] - 14, hi - 0.03 * (hi - lo)),
                    color=C.CLASS_COLOR[c], fontsize=9, rotation=90, ha="right", va="top")

    ax.set_ylim(lo, hi)
    ax.set_xlabel(C.X_LABEL, color=C.INK, fontsize=10.5)
    # Kept short deliberately: the full formula written out here overflows the
    # canvas height once "observation window" replaces "T", and the label clips.
    # The definition lives in the caption instead.
    ax.set_ylabel("margin_p95 (ms)", color=C.INK, fontsize=10.5)
    ax.set_title("Feasibility margin vs observation window, two-class scheme "
                 "(worst-case p95 latency)", color=C.INK, fontsize=12.5, loc="left", pad=12)
    ax.legend(frameon=False, fontsize=9.0, labelcolor=C.INK2, loc="upper center",
              bbox_to_anchor=(0.5, -0.13), ncol=1, handlelength=2.6)

    caption = [
        "margin_p95 = deadline - observation window - p95 latency, per class. Deadline is the class minimum launch-to-crossing time rounded down to 10 ms.",
        "Budget = 100 ms perceptual window minus 16 ms projector input lag. The projector figure is measured end to end and already includes the frame period,",
        "so panel, quantisation and render terms are not added separately. Pi render and compositor latency is neglected.",
    ]
    for i, line in enumerate(caption):
        fig.text(0.012, 0.030 - i * 0.016, line, color=C.INK2, fontsize=7.5)

    fig.tight_layout()
    fig.savefig(FIG, dpi=150, facecolor=C.SURF, bbox_inches="tight")
    plt.close(fig)

    print(f"deadlines: {dl}")
    print(f"max usable window: {max_window}")
    for c in C.CLASSES:
        i = windows.index(max_window[c])
        nxt = windows[i + 1] if i + 1 < len(windows) else None
        print(f"  {c}: margin at {max_window[c]} ms = {margins[c][i]:.1f} ms"
              + (f", next step {nxt} ms = {margins[c][i+1]:.1f} ms" if nxt else ""))
    print(f"wrote {FIG}")


if __name__ == "__main__":
    main()
