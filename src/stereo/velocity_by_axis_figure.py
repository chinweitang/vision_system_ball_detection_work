# velocity_by_axis_figure.py
#
# claude/prompts/2026-08-05_1254_pi_sweep_rerun_velocity_error_components.md
#
# Figure 4: velocity error by world axis (X_world=depth, Y_world=width,
# Z_world=up), 3 panels, BIAS (signed mean, line) + SCATTER (RMS, band) per
# regime. Read-only against velocity_by_axis_summary.csv -- no CSV
# regenerated, no Pi re-run. Written only to figures2/ (new path).
#
# Per-axis reference validity is NON-UNIFORM: X/Z are validated to label
# precision (decision 77, ~155/~135mm/s), Y is UNRESOLVED (label SD
# ~282mm/s) -- the label-precision floor bands make this visually explicit;
# convergence below the Y floor is not interpretable as accuracy.
#
# Accuracy is CONVERGENCE vs full-arc fit (placeholder), NOT ground truth.

import csv
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
FIG_DIR = REPO_ROOT / "data" / "pi_benchmarking" / "02_pi_pipeline_sweep_parallel_detection" / "figures2"
SUMMARY_CSV = FIG_DIR / "velocity_by_axis_summary.csv"

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
COLORS = {"FLAT": "#2a78d6", "MID": "#e39a1f", "LOB": "#e34948"}
FLOOR_COLOR = "#898781"
BIN_ORDER = ["FLAT", "MID", "LOB"]
MAX_USABLE_T = {"FLAT": 300.0, "MID": 450.0, "LOB": 800.0}

AXES = [
    ("X_depth", "X_world (depth)", 155.0, "validated to label precision"),
    ("Y_width", "Y_world (width)", 282.0, "UNRESOLVED -- reference not validated by label method"),
    ("Z_up", "Z_world (up)", 135.0, "validated to label precision"),
]

DPI = 300


def style_axes(ax):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(BASELINE)
        ax.spines[spine].set_linewidth(1)
    ax.grid(axis="y", color=GRIDLINE, linewidth=1, linestyle="-", zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK_MUTED, labelsize=8.5)
    ax.xaxis.label.set_color(INK_SECONDARY)
    ax.yaxis.label.set_color(INK_SECONDARY)


def load_rows():
    with open(SUMMARY_CSV, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in r:
            if k != "bin":
                r[k] = float(r[k])
    return rows


def by_bin(rows):
    return {b: sorted([r for r in rows if r["bin"] == b], key=lambda r: r["T_ms"]) for b in BIN_ORDER}


def main():
    rows = load_rows()
    binned = by_bin(rows)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.8), dpi=DPI)

    for ax, (axis_key, axis_label, floor_mm_s, floor_note) in zip(axes, AXES):
        style_axes(ax)

        # label-precision floor band
        ax.axhspan(-floor_mm_s, floor_mm_s, color=FLOOR_COLOR, alpha=0.12, zorder=0)
        ax.axhline(0, color=INK_MUTED, linewidth=1.0, linestyle=(0, (1, 2)), zorder=1)

        for b in BIN_ORDER:
            rs = binned[b]
            x = np.array([r["T_ms"] for r in rs])
            bias = np.array([r[f"{axis_key}_bias_mm_s"] for r in rs])
            rms = np.array([r[f"{axis_key}_scatter_rms_mm_s"] for r in rs])

            ax.fill_between(x, bias - rms, bias + rms, color=COLORS[b], alpha=0.12, zorder=2)
            ax.plot(x, bias, color=COLORS[b], linewidth=2, marker="o", markersize=4,
                    markerfacecolor=COLORS[b], markeredgecolor=SURFACE, markeredgewidth=0.8,
                    solid_capstyle="round", label=f"{b}", zorder=3)

            mt = MAX_USABLE_T[b]
            ax.axvline(mt, color=COLORS[b], linewidth=1.25, linestyle=(0, (1, 1)), alpha=0.7, zorder=2)

        ax.set_xlabel("cutoff t (ms)")
        if axis_key == "X_depth":
            ax.set_ylabel("velocity error: bias (line) +/- scatter RMS (band), mm/s")
        ax.set_xlim(100, 1300)
        ax.set_title(f"{axis_label}\nfloor={floor_mm_s:.0f}mm/s ({floor_note})",
                     fontsize=10, color=INK_PRIMARY, loc="left")
        if axis_key == "X_depth":
            ax.legend(loc="upper right", frameon=False, fontsize=8.5, labelcolor=INK_SECONDARY)

    fig.suptitle("Velocity error by world axis at the feasible operating point (vertical lines = max-usable-t)\n"
                 "CONVERGENCE vs full-arc fit -- placeholder, NOT ground truth. Per-axis reference validity "
                 "differs: X/Z validated (decision 77), Y unresolved.",
                 fontsize=11, color=INK_PRIMARY, x=0.02, ha="left", y=1.06)
    fig.tight_layout()
    out = FIG_DIR / "figure4_velocity_error_by_axis.png"
    fig.savefig(out, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)

    img = plt.imread(out)
    h, w = img.shape[0], img.shape[1]
    print(f"Figure 4 -> {out}")
    print(f"  {out.name}: {w}x{h}px @ {DPI} DPI ({w/DPI:.2f}x{h/DPI:.2f} in)")


if __name__ == "__main__":
    main()
