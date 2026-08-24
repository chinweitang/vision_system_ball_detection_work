# launch_to_crossing_budget.py
#
# claude/prompts/2026-08-04_1735_launch_to_crossing_budget.md
#
# Recomputes the worst-case timing budget as launch-to-CROSSING-PLANE
# duration (crosser flights only: HIT + MISS_HIGH_WIDE), replacing the
# stale 430ms full-flight-duration figure.
#
# Clock check (see worklog claude/claude_logs/2026-08-04_1738_
# launch_to_crossing_budget_worklog.md for the full trace): all_flights_
# common.build_corrected_track() zero-bases t at the first usable fit
# frame (t_sec = (t_avg - t_avg[0]) / 1e9). crossing_plane_classification.
# classify_flight() fits Model C to that same zero-based t array and finds
# t_cross via brentq bisection over the SAME array, with no re-zeroing --
# so t_start=0 and t_cross are already on an identical clock;
# launch_to_crossing_ms = t_cross * 1000 directly.
#
# t_cross is computed inside classify_flight() but was never persisted to
# crossing_classification.csv's columns. Retrieved by re-calling the
# frozen, UNMODIFIED build_geometry()/classify_flight() (fixed RANSAC_SEED,
# fully deterministic, identical inputs) for the 107 crossers only --
# each flight's cls and duration_ms are verified to reproduce the existing
# CSV row exactly before its t_cross is trusted. This is a reproduction of
# the same frozen computation to recover a discarded field, not a re-fit
# with different methodology.
#
# Frozen, read-only: crossing_plane_classification.build_geometry() /
# classify_flight(), all_flights_common.load_session_calib(). Not modified.

import csv
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.stereo.all_flights_common import load_session_calib, registration_for  # noqa: E402
from src.stereo.crossing_plane_classification import (  # noqa: E402
    build_geometry, classify_flight, load_pooled_k, TAPE_REGISTRATIONS, REG_KEY_FOR,
)

IN_CSV = REPO_ROOT / "results" / "prediction" / "01_crossing_plane_setup" / "crossing_classification.csv"
OUT_DIR = REPO_ROOT / "results" / "prediction" / "04_launch_to_crossing_budget"
LOG_PATH = REPO_ROOT / "claude" / "claude_logs" / "2026-08-04_1738_launch_to_crossing_budget_worklog.md"
OLD_BUDGET_MS = 430.0

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"
RED = "#e34948"
DPI = 300


def log_append(msg: str) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(f"- [{datetime.now().strftime('%H:%M:%S')}] {msg}\n")


def pct(sorted_vals, p):
    n = len(sorted_vals)
    idx_f = p * (n - 1)
    lo, hi = int(np.floor(idx_f)), int(np.ceil(idx_f))
    if lo == hi:
        return sorted_vals[lo]
    frac = idx_f - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(IN_CSV, newline="") as f:
        all_rows = list(csv.DictReader(f))
    crossers = [r for r in all_rows if r["cls"] in ("HIT", "MISS_HIGH_WIDE")]
    excluded = [r for r in all_rows if r["cls"] == "MISS_SHORT"]
    log_append(f"Loaded {len(all_rows)} flights from crossing_classification.csv. "
               f"Crossers (HIT+MISS_HIGH_WIDE)={len(crossers)}, "
               f"excluded MISS_SHORT={len(excluded)}.")
    assert len(crossers) + len(excluded) == len(all_rows)

    pooled_k = load_pooled_k()
    geometries = {}
    for reg_key, cfg in TAPE_REGISTRATIONS.items():
        geometries[reg_key] = build_geometry(reg_key, cfg)
    log_append(f"Rebuilt geometry for all 3 registrations (identical frozen build_geometry(), "
               f"pooled_k={pooled_k:.6e}).")

    calib_cache = {}
    out_rows = []
    mismatches = []
    for r in crossers:
        session, flight_id = r["session"], r["flight_id"]
        if session not in calib_cache:
            calib_cache[session] = load_session_calib(session)
        K0, D0, K1, D1, P0, P1 = calib_cache[session]
        reg = registration_for(session, flight_id)
        reg_key = REG_KEY_FOR[(session, reg)]
        geo = geometries[reg_key]

        result = classify_flight(session, flight_id, geo, K0, D0, K1, D1, P0, P1, pooled_k)

        if result["status"] != "ok" or result.get("cls") != r["cls"]:
            mismatches.append((session, flight_id, "status/cls mismatch", result))
            continue
        dur_delta = abs(result["duration_ms"] - float(r["duration_ms"]))
        if dur_delta > 1e-3:
            mismatches.append((session, flight_id, f"duration_ms mismatch delta={dur_delta:.6f}ms", result))
            continue
        if "t_cross" not in result:
            mismatches.append((session, flight_id, "no t_cross in result (MISS_SHORT path?)", result))
            continue

        t_start_ms = 0.0  # build_corrected_track zero-bases t at the first usable fit frame
        t_cross_ms = float(result["t_cross"]) * 1000.0
        out_rows.append({
            "registration": reg_key, "session": session, "flight_id": flight_id, "cls": r["cls"],
            "elevation_deg": r["elevation_deg"], "speed_m_s": r["speed_m_s"],
            "t_start_ms": t_start_ms, "t_cross_ms": t_cross_ms,
            "launch_to_crossing_ms": t_cross_ms - t_start_ms,
        })

    log_append(f"Re-ran frozen classify_flight() for {len(crossers)} crossers to retrieve t_cross "
               f"(discarded by 01_'s CSV writer). Verified against existing cls+duration_ms: "
               f"{len(out_rows)} matched exactly, {len(mismatches)} mismatched.")
    if mismatches:
        log_append("*** MISMATCHES FOUND -- excluded from output, listing all: ***")
        for session, flight_id, reason, result in mismatches:
            log_append(f"  {session}/{flight_id}: {reason} (result={result})")
    if len(mismatches) > 0.1 * len(crossers):
        log_append("*** STOP: >10% mismatch rate -- frozen re-run is NOT reproducing 01_'s results "
                   "deterministically, cannot trust t_cross values. Reporting, not proceeding further. ***")
        raise SystemExit("Reproduction mismatch rate too high -- see log.")

    n = len(out_rows)
    vals = sorted(row["launch_to_crossing_ms"] for row in out_rows)
    stats = {
        "n": n,
        "mean": float(np.mean(vals)),
        "median": pct(vals, 0.5),
        "min": vals[0],
        "max": vals[-1],
        "P5": pct(vals, 0.05),
        "P10": pct(vals, 0.10),
        "P15": pct(vals, 0.15),
    }
    log_append(f"Distribution (n={n}, linear/numpy-style interpolation): "
               f"mean={stats['mean']:.1f}ms median={stats['median']:.1f}ms min={stats['min']:.1f}ms "
               f"max={stats['max']:.1f}ms P5={stats['P5']:.1f}ms P10={stats['P10']:.1f}ms "
               f"P15={stats['P15']:.1f}ms")

    shortest = sorted(out_rows, key=lambda r: r["launch_to_crossing_ms"])[:8]
    log_append("8 shortest flights:")
    for row in shortest:
        log_append(f"  {row['session']}/{row['flight_id']} ({row['registration']}): "
                   f"launch_to_crossing_ms={row['launch_to_crossing_ms']:.1f} "
                   f"elevation_deg={row['elevation_deg']} speed_m_s={row['speed_m_s']} cls={row['cls']}")

    delta = stats["P5"] - OLD_BUDGET_MS
    log_append(f"OLD budget (430ms, full-flight P5) vs NEW budget (P5 launch-to-crossing "
               f"={stats['P5']:.1f}ms): delta={delta:+.1f}ms "
               f"({'shorter' if delta < 0 else 'longer'}, i.e. new budget is "
               f"{'TIGHTER' if delta < 0 else 'more permissive'} than previously assumed).")

    csv_path = OUT_DIR / "launch_to_crossing.csv"
    fieldnames = ["registration", "session", "flight_id", "cls", "elevation_deg", "speed_m_s",
                  "t_start_ms", "t_cross_ms", "launch_to_crossing_ms"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)
    log_append(f"Wrote {csv_path} ({n} rows)")

    summary_path = OUT_DIR / "summary.txt"
    with open(summary_path, "w") as f:
        f.write("Launch-to-crossing-plane duration budget (crossers only, n={})\n".format(n))
        f.write("=" * 70 + "\n\n")
        f.write(f"mean   = {stats['mean']:.1f} ms\n")
        f.write(f"median = {stats['median']:.1f} ms\n")
        f.write(f"min    = {stats['min']:.1f} ms\n")
        f.write(f"max    = {stats['max']:.1f} ms\n")
        f.write(f"P5     = {stats['P5']:.1f} ms\n")
        f.write(f"P10    = {stats['P10']:.1f} ms\n")
        f.write(f"P15    = {stats['P15']:.1f} ms\n")
        f.write("(percentiles: linear interpolation between order statistics, numpy default)\n\n")
        f.write(f"OLD budget (430ms, full-flight P5) vs NEW budget (P5 launch-to-crossing = "
                f"{stats['P5']:.1f}ms): delta = {delta:+.1f}ms\n\n")
        f.write("8 shortest flights:\n")
        f.write(f"{'flight':40s} {'reg':10s} {'elev_deg':>9s} {'speed_m_s':>10s} {'launch_to_cross_ms':>20s}\n")
        for row in shortest:
            flight_label = f"{row['session']}/{row['flight_id']}"
            f.write(f"{flight_label:40s} {row['registration']:10s} {row['elevation_deg']:>9s} "
                    f"{row['speed_m_s']:>10s} {row['launch_to_crossing_ms']:>20.1f}\n")
    log_append(f"Wrote {summary_path}")

    # Histogram
    fig, ax = plt.subplots(figsize=(8.0, 5.0), dpi=DPI)
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

    ax.hist(vals, bins=24, color=BLUE, alpha=0.85, edgecolor=SURFACE, linewidth=1.2, zorder=3)
    for label, val, ls in [("P5", stats["P5"], (0, (1, 2))), ("P10", stats["P10"], (0, (3, 2))),
                            ("P15", stats["P15"], (0, (5, 2)))]:
        ax.axvline(val, color=RED, linewidth=1.5, linestyle=ls, zorder=4)

    legend_text = (f"P5  = {stats['P5']:.0f} ms\n"
                   f"P10 = {stats['P10']:.0f} ms\n"
                   f"P15 = {stats['P15']:.0f} ms")
    ax.text(0.98, 0.96, legend_text, transform=ax.transAxes, fontsize=9,
            color=INK_SECONDARY, ha="right", va="top", linespacing=1.6,
            family="monospace", bbox=dict(facecolor=SURFACE, edgecolor=BASELINE,
                                           boxstyle="round,pad=0.4", linewidth=1))

    ax.set_xlabel("launch-to-crossing-plane duration (ms)")
    ax.set_ylabel("flight count")
    ax.set_title(f"Launch-to-crossing-plane duration distribution (n={n} crossers)",
                 fontsize=12, color=INK_PRIMARY, loc="left", pad=12)
    fig.tight_layout()
    fig_path = OUT_DIR / "launch_to_crossing_histogram.png"
    fig.savefig(fig_path, dpi=DPI, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    log_append(f"Wrote {fig_path}")

    log_append("DONE.")
    return stats


if __name__ == "__main__":
    main()
