# ransac_sweep_figures.py
#
# Two report figures from the RANSAC n_iterations sweep
# (results/trajectory_fit_comparison/ransac_iterations_sweep/), for direct
# thesis inclusion. Read-only against the existing sweep outputs -- does not
# regenerate or modify ransac_sweep_raw.csv or either summary table.
#
# Palette/marks per the dataviz skill's validated default palette
# (references/palette.md): categorical slot 1 (blue #2a78d6) for the primary
# series in both figures, slot 8 (red #e34948) for the flagged-unstable
# subset in Figure 2 -- validated via scripts/validate_palette.js before use
# (worst-pair CVD dE 21.6 protan / normal-vision dE 32.3, both clear of the
# 8/15 floors). Static PNG for print/thesis inclusion, not an interactive
# HTML chart -- interaction-layer parts of the skill (tooltips, hover) don't
# apply; mark specs (2px lines, >=8px markers, recessive hairline gridlines,
# text in ink tokens not series colors, legend for 2+ series) do.
#
# The 480ms reference line in Figure 1 is deliberately labelled as an upper
# bound, not "the RANSAC budget" -- see the figure's own annotation and
# claude/claude_logs/2026-08-03_pi_realtime_benchmark_worklog.md for why a
# fully-corrected residual budget can't be stated yet (depends on unmeasured
# actuation latency).
#
# Usage:
#   python src/stereo/ransac_sweep_figures.py

import csv
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
SWEEP_DIR = REPO_ROOT / "results" / "trajectory_fit_comparison" / "ransac_iterations_sweep"
FIG_DIR = SWEEP_DIR / "figures"

RAW_CSV = SWEEP_DIR / "ransac_sweep_raw.csv"
TABLE1_CSV = SWEEP_DIR / "table1_wallclock_by_niterations.csv"
TABLE2_CSV = SWEEP_DIR / "table2_error_by_niterations.csv"

# -- palette (references/palette.md, light mode -- static print/thesis figure) --
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"      # categorical slot 1
RED = "#e34948"       # categorical slot 8 -- validated as a pair with BLUE

PI_HITS_REGIME_CEILING_MS = 480.0  # upper bound, NOT the true RANSAC allowance -- see module docstring

N_ITERATIONS_VALUES = [3, 5, 7, 10, 15, 25]
PERSISTENTLY_UNSTABLE_FLIGHTS = [
    ("2026_07_21_gym", "flight_121"), ("2026_07_21_gym", "flight_122"),
    ("2026_07_21_gym", "flight_38"), ("2026_07_21_gym", "flight_45"),
    ("2026_07_21_gym", "flight_46"), ("2026_07_21_gym", "flight_22"),
    ("2026_07_21_gym", "flight_125"),
]

FIGSIZE = (8.0, 5.0)   # inches
DPI = 300               # print/thesis resolution


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


def load_table1():
    rows = []
    with open(TABLE1_CSV, newline="") as f:
        for row in csv.DictReader(f):
            rows.append((int(row["n_iterations"]), float(row["median_wall_ms"]), float(row["p95_wall_ms"])))
    return sorted(rows)


def load_table2():
    rows = []
    with open(TABLE2_CSV, newline="") as f:
        for row in csv.DictReader(f):
            rows.append((int(row["n_iterations"]), float(row["median_error_mm"]), float(row["iqr_error_mm"])))
    return sorted(rows)


def load_raw():
    rows = []
    with open(RAW_CSV, newline="") as f:
        for row in csv.DictReader(f):
            if row["status"] != "ok":
                continue
            rows.append(row)
    return rows


def figure1_wallclock(table1):
    n_iters = np.array([r[0] for r in table1], dtype=float)
    medians = np.array([r[1] for r in table1])
    p95s = np.array([r[2] for r in table1])

    slope, intercept = np.polyfit(n_iters, medians, 1)

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    style_axes(ax)

    ax.plot(n_iters, medians, color=BLUE, linewidth=2, marker="o", markersize=8,
            markerfacecolor=BLUE, markeredgecolor=SURFACE, markeredgewidth=1.5,
            solid_capstyle="round", solid_joinstyle="round", label="median wall-clock time", zorder=3)
    ax.plot(n_iters, p95s, color=BLUE, linewidth=2, linestyle=(0, (5, 3)), marker="o", markersize=8,
            markerfacecolor=SURFACE, markeredgecolor=BLUE, markeredgewidth=1.5,
            solid_capstyle="round", label="p95 wall-clock time", zorder=3)

    # linear fit trend (thin, behind the data)
    x_fit = np.array([n_iters.min(), n_iters.max()])
    ax.plot(x_fit, slope * x_fit + intercept, color=BLUE, linewidth=1, linestyle=":", alpha=0.5, zorder=1)
    ax.annotate(f"linear fit: {slope:.1f} ms/iteration\n(confirms theoretical linear-cost model)",
                xy=(n_iters[2], slope * n_iters[2] + intercept), xytext=(n_iters[1], medians[-1] * 0.55),
                fontsize=8.5, color=INK_SECONDARY,
                arrowprops=dict(arrowstyle="-", color=INK_MUTED, linewidth=1))

    ax.axhline(PI_HITS_REGIME_CEILING_MS, color=INK_MUTED, linewidth=1.5, linestyle=(0, (1, 2)), zorder=2)
    ax.annotate("480ms hits-regime ceiling*", xy=(25, PI_HITS_REGIME_CEILING_MS),
                xytext=(25, PI_HITS_REGIME_CEILING_MS * 1.12), ha="right", va="bottom",
                fontsize=8, color=INK_MUTED)
    fig.text(0.01, -0.04,
              "* Upper bound, not the true RANSAC allowance -- residual after the 430ms observation window,\n"
              "triangulation, non-RANSAC fit overhead, comms, and actuation latency is smaller, but not yet\n"
              "derivable (actuation latency is unmeasured).",
              fontsize=7.5, color=INK_MUTED, ha="left", va="top")

    ax.set_xlabel("n_iterations")
    ax.set_ylabel("wall-clock time (ms)")
    ax.set_xticks(N_ITERATIONS_VALUES)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_title("RANSAC wall-clock time vs iteration count (laptop timing)",
                 fontsize=12, color=INK_PRIMARY, loc="left", pad=12)

    legend = ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK_SECONDARY)
    fig.tight_layout()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIG_DIR / "figure1_ransac_wallclock_vs_niterations.png"
    fig.savefig(out_path, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out_path, slope


def figure2_error(table2, raw_rows):
    n_iters = np.array([r[0] for r in table2], dtype=float)
    pop_medians = np.array([r[1] for r in table2])

    # Q25/Q75 computed directly from raw data (median +- IQR/2 is not generally
    # equal to Q25/Q75 for a skewed distribution -- don't approximate it)
    pop_q25, pop_q75 = [], []
    for n in N_ITERATIONS_VALUES:
        vals = np.array([float(r["error_mm"]) for r in raw_rows if int(r["n_iterations"]) == n])
        pop_q25.append(np.percentile(vals, 25))
        pop_q75.append(np.percentile(vals, 75))
    pop_q25, pop_q75 = np.array(pop_q25), np.array(pop_q75)

    unstable_medians = []
    for n in N_ITERATIONS_VALUES:
        vals = np.array([float(r["error_mm"]) for r in raw_rows
                          if int(r["n_iterations"]) == n
                          and (r["session"], r["flight"]) in PERSISTENTLY_UNSTABLE_FLIGHTS])
        unstable_medians.append(np.median(vals) if len(vals) else np.nan)
    unstable_medians = np.array(unstable_medians)

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    style_axes(ax)

    ax.fill_between(n_iters, pop_q25, pop_q75, color=BLUE, alpha=0.10, zorder=1, linewidth=0)
    ax.plot(n_iters, pop_medians, color=BLUE, linewidth=2, marker="o", markersize=8,
            markerfacecolor=BLUE, markeredgecolor=SURFACE, markeredgewidth=1.5,
            solid_capstyle="round", label="full population (n=150 flights) -- median, IQR band", zorder=3)

    ax.plot(n_iters, unstable_medians, color=RED, linewidth=2, linestyle=(0, (5, 3)), marker="o", markersize=8,
            markerfacecolor=RED, markeredgecolor=SURFACE, markeredgewidth=1.5,
            label="structurally unstable subset (n=7 flights,\nunstable even at n_iterations=25) -- median", zorder=4)

    ax.set_xlabel("n_iterations")
    ax.set_ylabel("final-point prediction error (mm)")
    ax.set_xticks(N_ITERATIONS_VALUES)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_title("RANSAC prediction error vs iteration count:\npopulation vs structurally unstable flights",
                 fontsize=12, color=INK_PRIMARY, loc="left", pad=12)

    # legend below the plot (outside the data area) -- both series occupy the
    # full vertical span (blue ~125-195mm band, red ~260-301mm), no clear
    # gap inside the axes wide enough for a 2-line legend without collision
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=1, frameon=False,
              fontsize=8.5, labelcolor=INK_SECONDARY)
    fig.tight_layout()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIG_DIR / "figure2_ransac_error_vs_niterations.png"
    fig.savefig(out_path, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out_path


def main():
    table1 = load_table1()
    table2 = load_table2()
    raw_rows = load_raw()

    p1, slope = figure1_wallclock(table1)
    print(f"Figure 1 -> {p1}")
    print(f"  linear fit slope: {slope:.2f} ms/iteration")

    p2 = figure2_error(table2, raw_rows)
    print(f"Figure 2 -> {p2}")

    for p in (p1, p2):
        img = plt.imread(p)
        h, w = img.shape[0], img.shape[1]
        print(f"  {p.name}: {w}x{h}px @ {DPI} DPI ({w/DPI:.2f}x{h/DPI:.2f} in)")


if __name__ == "__main__":
    main()
