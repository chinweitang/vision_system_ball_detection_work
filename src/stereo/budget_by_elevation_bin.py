# budget_by_elevation_bin.py
#
# claude/prompts/2026-08-04_1735_launch_to_crossing_budget.md (follow-on
# task, appended after the pooled 04_ run).
#
# Recomputes the launch-to-crossing-plane timing budget PER ELEVATION BIN
# (FLAT<15deg / MID 15-45deg / LOB>=45deg, same cuts as 02_'s candidate
# reselection) instead of pooled across all 107 crossers. Pooled P5 is
# contaminated by throw mix (60/107 crossers are LOB) -- it reflects how
# many lobs vs flats were thrown that day, not the physics. FLAT drives
# reach the plane fastest, so FLAT's P5 is the throw-mix-independent design
# target; MID/LOB are reported for contrast (they have slack).
#
# Purely reuses results/prediction/04_launch_to_crossing_budget/
# launch_to_crossing.csv (already-computed, already-validated
# launch_to_crossing_ms per crosser) -- no t_cross recomputation, no
# re-fit, no re-classification. Read-only.

import csv
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]

IN_CSV = REPO_ROOT / "results" / "prediction" / "04_launch_to_crossing_budget" / "launch_to_crossing.csv"
OUT_DIR = REPO_ROOT / "results" / "prediction" / "05_budget_by_elevation_bin"
LOG_PATH = REPO_ROOT / "claude" / "claude_logs" / "2026-08-04_1738_launch_to_crossing_budget_worklog.md"

# Same cuts as 02_candidate_reselection (FLAT<15, MID 15-45, LOB>=45)
BIN_ORDER = ["FLAT", "MID", "LOB"]
COLORS = {"FLAT": "#2a78d6", "MID": "#e39a1f", "LOB": "#e34948"}  # blue/amber/red, categorical order

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
DPI = 300


def log_append(msg: str) -> None:
    from datetime import datetime
    with open(LOG_PATH, "a") as f:
        f.write(f"- [{datetime.now().strftime('%H:%M:%S')}] {msg}\n")


def elevation_bin(elevation_deg: float) -> str:
    if elevation_deg < 15.0:
        return "FLAT"
    elif elevation_deg < 45.0:
        return "MID"
    return "LOB"


def pct(sorted_vals, p):
    n = len(sorted_vals)
    idx_f = p * (n - 1)
    lo, hi = int(np.floor(idx_f)), int(np.ceil(idx_f))
    if lo == hi:
        return sorted_vals[lo]
    frac = idx_f - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def bin_stats(vals):
    s = sorted(vals)
    return {
        "n": len(s), "min": s[0], "median": pct(s, 0.5),
        "P5": pct(s, 0.05), "P10": pct(s, 0.10), "P15": pct(s, 0.15),
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(IN_CSV, newline="") as f:
        rows = list(csv.DictReader(f))
    log_append(f"Loaded {len(rows)} crossers from 04_'s launch_to_crossing.csv (reused as-is, "
               f"no recomputation).")

    for r in rows:
        r["elevation_deg"] = float(r["elevation_deg"])
        r["speed_m_s"] = float(r["speed_m_s"])
        r["launch_to_crossing_ms"] = float(r["launch_to_crossing_ms"])
        r["bin"] = elevation_bin(r["elevation_deg"])

    by_bin = {b: [r for r in rows if r["bin"] == b] for b in BIN_ORDER}
    for b in BIN_ORDER:
        log_append(f"{b} bin: n={len(by_bin[b])} "
                   f"(elevation range in bin: "
                   f"{min(r['elevation_deg'] for r in by_bin[b]):.1f} to "
                   f"{max(r['elevation_deg'] for r in by_bin[b]):.1f} deg)")
    assert sum(len(by_bin[b]) for b in BIN_ORDER) == len(rows), "bin assignment lost/duplicated rows"

    bin_rows_out = []
    for b in BIN_ORDER:
        vals = [r["launch_to_crossing_ms"] for r in by_bin[b]]
        stats = bin_stats(vals)
        bin_rows_out.append({"bin": b, **stats})
        log_append(f"{b}: n={stats['n']} min={stats['min']:.1f}ms median={stats['median']:.1f}ms "
                   f"P5={stats['P5']:.1f}ms P10={stats['P10']:.1f}ms P15={stats['P15']:.1f}ms")

    pooled_vals = [r["launch_to_crossing_ms"] for r in rows]
    pooled_stats = bin_stats(pooled_vals)
    bin_rows_out.append({"bin": "POOLED", **pooled_stats})
    log_append(f"POOLED (reference, throw-mix-dependent, NOT the design target): n={pooled_stats['n']} "
               f"min={pooled_stats['min']:.1f}ms median={pooled_stats['median']:.1f}ms "
               f"P5={pooled_stats['P5']:.1f}ms P10={pooled_stats['P10']:.1f}ms P15={pooled_stats['P15']:.1f}ms")

    flat_p5 = bin_stats([r["launch_to_crossing_ms"] for r in by_bin["FLAT"]])["P5"]
    lob_p5 = bin_stats([r["launch_to_crossing_ms"] for r in by_bin["LOB"]])["P5"]
    log_append(f"*** FLAT P5 = {flat_p5:.1f}ms is the DESIGN TARGET (throw-mix-independent -- flat "
               f"drives reach the plane fastest, sets the true worst case regardless of how many "
               f"lobs were thrown that day). Pooled P5 ({pooled_stats['P5']:.1f}ms) is throw-mix-"
               f"dependent, NOT the target -- it reflects the day's lob/flat mix (60/107 LOB), not "
               f"the physics. LOB P5 ({lob_p5:.1f}ms) is shown for contrast: {lob_p5 - flat_p5:+.1f}ms "
               f"of slack relative to FLAT. ***")

    shortest_per_bin = {}
    for b in BIN_ORDER:
        shortest = sorted(by_bin[b], key=lambda r: r["launch_to_crossing_ms"])[:3]
        shortest_per_bin[b] = shortest
        log_append(f"{b} bin, 3 shortest flights:")
        for row in shortest:
            log_append(f"  {row['session']}/{row['flight_id']} ({row['registration']}): "
                       f"launch_to_crossing_ms={row['launch_to_crossing_ms']:.1f} "
                       f"elevation_deg={row['elevation_deg']:.2f} speed_m_s={row['speed_m_s']:.2f} "
                       f"cls={row['cls']}")

    # Write budget_by_bin.csv
    csv_path = OUT_DIR / "budget_by_bin.csv"
    fieldnames = ["bin", "n", "min", "median", "P5", "P10", "P15"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in bin_rows_out:
            w.writerow(row)
    log_append(f"Wrote {csv_path}")

    # Write summary.txt
    summary_path = OUT_DIR / "summary.txt"
    with open(summary_path, "w") as f:
        f.write("Launch-to-crossing-plane timing budget, by elevation bin\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"{'bin':8s} {'n':>4s} {'min':>10s} {'median':>10s} {'P5':>10s} {'P10':>10s} {'P15':>10s}\n")
        for row in bin_rows_out:
            f.write(f"{row['bin']:8s} {row['n']:>4d} {row['min']:>10.1f} {row['median']:>10.1f} "
                    f"{row['P5']:>10.1f} {row['P10']:>10.1f} {row['P15']:>10.1f}\n")
        f.write("\n(percentiles: linear interpolation between order statistics, numpy default)\n\n")
        f.write(f"FLAT P5 = {flat_p5:.1f} ms  <-- DESIGN TARGET (throw-mix-independent)\n")
        f.write(f"POOLED P5 = {pooled_stats['P5']:.1f} ms  <-- throw-mix-dependent, NOT the target\n")
        f.write(f"LOB P5 = {lob_p5:.1f} ms  <-- shown for contrast, {lob_p5 - flat_p5:+.1f}ms slack vs FLAT\n\n")
        for b in BIN_ORDER:
            f.write(f"{b} bin, 3 shortest flights:\n")
            f.write(f"{'flight':40s} {'reg':10s} {'elev_deg':>9s} {'speed_m_s':>10s} {'launch_to_cross_ms':>20s}\n")
            for row in shortest_per_bin[b]:
                flight_label = f"{row['session']}/{row['flight_id']}"
                f.write(f"{flight_label:40s} {row['registration']:10s} {row['elevation_deg']:>9.2f} "
                        f"{row['speed_m_s']:>10.2f} {row['launch_to_crossing_ms']:>20.1f}\n")
            f.write("\n")
    log_append(f"Wrote {summary_path}")

    # Histogram: overlaid per-bin series, each bin's P5 marked
    fig, ax = plt.subplots(figsize=(9.0, 5.5), dpi=DPI)
    ax.set_facecolor(SURFACE)
    fig.set_facecolor(SURFACE)
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

    all_vals = [r["launch_to_crossing_ms"] for r in rows]
    bin_edges = np.linspace(min(all_vals), max(all_vals), 26)

    for b in BIN_ORDER:
        vals = [r["launch_to_crossing_ms"] for r in by_bin[b]]
        ax.hist(vals, bins=bin_edges, color=COLORS[b], alpha=0.55, edgecolor=SURFACE,
                 linewidth=1.0, label=f"{b} (n={len(vals)})", zorder=3)

    for b in BIN_ORDER:
        p5 = bin_stats([r["launch_to_crossing_ms"] for r in by_bin[b]])["P5"]
        ax.axvline(p5, color=COLORS[b], linewidth=2, linestyle=(0, (4, 2)), zorder=4)

    legend_text = "\n".join(
        f"{b} P5 = {bin_stats([r['launch_to_crossing_ms'] for r in by_bin[b]])['P5']:.0f} ms"
        for b in BIN_ORDER
    )
    ax.text(0.98, 0.96, legend_text, transform=ax.transAxes, fontsize=9,
            color=INK_SECONDARY, ha="right", va="top", linespacing=1.6,
            family="monospace", bbox=dict(facecolor=SURFACE, edgecolor=BASELINE,
                                           boxstyle="round,pad=0.4", linewidth=1))

    ax.set_xlabel("launch-to-crossing-plane duration (ms)")
    ax.set_ylabel("flight count")
    ax.set_title("Launch-to-crossing-plane duration by elevation regime\n"
                 "(dashed lines = each bin's own P5; FLAT sets the design budget)",
                 fontsize=12, color=INK_PRIMARY, loc="left", pad=12)
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    fig_path = OUT_DIR / "budget_by_bin_histogram.png"
    fig.savefig(fig_path, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    log_append(f"Wrote {fig_path}")

    log_append("DONE.")


if __name__ == "__main__":
    main()
