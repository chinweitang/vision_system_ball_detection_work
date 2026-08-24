# two_axis_sweep_figures.py
#
# Three report figures from the Pi two-axis (fit-window W) full-pipeline sweep.
# Read-only against two_axis_sweep_summary_by_W.csv / two_axis_sweep_raw.csv --
# no CSV regenerated or modified.
#
# Palette: dataviz skill's validated default (references/palette.md), light
# mode, static PNG for thesis inclusion -- same convention as
# ransac_sweep_figures.py / ransac_threshold_sweep_figures.py. Blue/red pair
# already validated via scripts/validate_palette.js earlier this session
# (CVD dE 21.6 protan, normal-vision dE 32.3, both clear of floors).

import csv
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
SWEEP_DIR = REPO_ROOT / "results" / "pi_benchmarking" / "two_axis_sweep"
FIG_DIR = SWEEP_DIR / "figures"

SUMMARY_CSV = SWEEP_DIR / "two_axis_sweep_summary_by_W.csv"

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"
RED = "#e34948"

DPI = 300
FIGSIZE = (8.0, 5.0)
BUDGET_MS = 430.0


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
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    ax.xaxis.label.set_color(INK_SECONDARY)
    ax.yaxis.label.set_color(INK_SECONDARY)


def load_csv_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def figure1_time(rows):
    x = np.array([float(r["W_ms"]) for r in rows])
    w_plus_c_med = np.array([float(r["w_plus_compute_ms_median"]) for r in rows])
    w_plus_c_p95 = np.array([float(r["w_plus_compute_ms_p95"]) for r in rows])

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    style_axes(ax)

    ax.plot(x, x, color=INK_MUTED, linewidth=1.5, linestyle=(0, (2, 2)),
            label="W alone (observation only)", zorder=2)
    ax.plot(x, w_plus_c_med, color=BLUE, linewidth=2, marker="o", markersize=8,
            markerfacecolor=BLUE, markeredgecolor=SURFACE, markeredgewidth=1.5,
            solid_capstyle="round", label="W + compute (median)", zorder=3)
    ax.plot(x, w_plus_c_p95, color=RED, linewidth=2, linestyle=(0, (5, 3)),
            marker="o", markersize=8, markerfacecolor=RED, markeredgecolor=SURFACE,
            markeredgewidth=1.5, label="W + compute (p95)", zorder=4)

    ax.axhline(BUDGET_MS, color=INK_MUTED, linewidth=1.25, linestyle=(0, (1, 2)), zorder=1)
    ax.annotate("430ms actuation budget", xy=(x.max(), BUDGET_MS), xytext=(x.max(), BUDGET_MS + 25),
                fontsize=8, color=INK_MUTED, ha="right", va="bottom")

    ax.set_xlabel("fit window duration W (ms)")
    ax.set_ylabel("total elapsed time: W + detection + triangulation + RANSAC (ms)")
    ax.set_xticks(x)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_title("Total pipeline time vs fit window W\n(Pi, rect kernel, serial cam0+cam1, RANSAC n_iterations=3)",
                 fontsize=12, color=INK_PRIMARY, loc="left", pad=12)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3, frameon=False,
              fontsize=8.5, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    out = FIG_DIR / "figure1_W_vs_time_consumed.png"
    fig.savefig(out, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out


def figure2_position_error(rows):
    x = np.array([float(r["W_ms"]) for r in rows])
    med = np.array([float(r["position_error_mm_median"]) for r in rows])
    iqr = np.array([float(r["position_error_mm_iqr"]) for r in rows])

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    style_axes(ax)
    ax.fill_between(x, med - iqr / 2, med + iqr / 2, color=BLUE, alpha=0.12, zorder=1)
    ax.plot(x, med, color=BLUE, linewidth=2, marker="o", markersize=8,
            markerfacecolor=BLUE, markeredgecolor=SURFACE, markeredgewidth=1.5,
            solid_capstyle="round", label="median (shaded = IQR)", zorder=3)

    ax.set_xlabel("fit window duration W (ms)")
    ax.set_ylabel("final-point position error (mm)")
    ax.set_xticks(x)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_title("Position prediction error vs fit window W\n(Pi, rect kernel, RANSAC n_iterations=3, n=150 flights)",
                 fontsize=12, color=INK_PRIMARY, loc="left", pad=12)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), frameon=False,
              fontsize=8.5, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    out = FIG_DIR / "figure2_W_vs_position_error.png"
    fig.savefig(out, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out


def figure3_velocity_error(rows):
    x = np.array([float(r["W_ms"]) for r in rows])
    med_a = np.array([float(r["velocity_error_a_mm_s_median"]) for r in rows])
    med_b = np.array([float(r["velocity_error_b_mm_s_median"]) for r in rows])

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    style_axes(ax)
    ax.set_yscale("log")
    ax.plot(x, med_a, color=BLUE, linewidth=2, marker="o", markersize=8,
            markerfacecolor=BLUE, markeredgecolor=SURFACE, markeredgewidth=1.5,
            solid_capstyle="round",
            label="method (a): full-traj self-consistency", zorder=3)
    ax.plot(x, med_b, color=RED, linewidth=2, linestyle=(0, (5, 3)), marker="o", markersize=8,
            markerfacecolor=RED, markeredgecolor=SURFACE, markeredgewidth=1.5,
            label="method (b): independent finite-difference", zorder=4)

    ax.set_xlabel("fit window duration W (ms)")
    ax.set_ylabel("velocity prediction error, median (mm/s, log scale)")
    ax.set_xticks(x)
    ax.set_title("Velocity prediction error vs fit window W -- two independent methods\n"
                 "(a) is a self-consistency check, not ground truth; (b) is independent but noisier",
                 fontsize=11.5, color=INK_PRIMARY, loc="left", pad=12)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), frameon=False,
              fontsize=8.5, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    out = FIG_DIR / "figure3_W_vs_velocity_error.png"
    fig.savefig(out, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out


def main():
    rows = load_csv_rows(SUMMARY_CSV)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    p1 = figure1_time(rows)
    print(f"Figure 1 -> {p1}")
    p2 = figure2_position_error(rows)
    print(f"Figure 2 -> {p2}")
    p3 = figure3_velocity_error(rows)
    print(f"Figure 3 -> {p3}")

    for p in (p1, p2, p3):
        img = plt.imread(p)
        h, w = img.shape[0], img.shape[1]
        print(f"  {p.name}: {w}x{h}px @ {DPI} DPI ({w/DPI:.2f}x{h/DPI:.2f} in)")


if __name__ == "__main__":
    main()
