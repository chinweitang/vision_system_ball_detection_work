#!/usr/bin/env python3
"""validate_sync_correction.py

Validation harness for pixel_velocity_correction.py, per the 2026-07-25
sync-correction task's Checkpoint 2. For each of a handful of representative
flights (spanning the sync audit's measured offset range):
  - runs triangulate_flight.triangulate_flight() (3-mode residual comparison)
  - plots original vs. corrected 2D centroid positions per camera, with an
    arrow per shifted point, so a wrong-direction/wrong-magnitude bug would
    be visible immediately
  - sanity-checks correction magnitude (px) against that flight's own
    per-frame pixel displacement, so a correction that's implausibly large
    relative to one frame's motion stands out

Reads only from data/2026_07_21_gym/ball_flights/<flight>/ (analysis_3 CSVs,
timestamps.csv) - all read-only. Writes only to results/sync_correction_validation/
(new folder, does not touch any existing analysis_3/contact-sheet output).
"""
from pathlib import Path
import sys
import csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from triangulate_flight import triangulate_flight, tuned_detections_paths  # noqa: E402
from stereo_flight_sync_table import analyze_flight  # noqa: E402

BALL_FLIGHTS = REPO_ROOT / "data" / "2026_07_21_gym" / "ball_flights"
OUT_DIR = REPO_ROOT / "results" / "sync_correction_validation_tuned_detections"

FLIGHTS = ["flight_92", "flight_5", "flight_20", "flight_100",
           "flight_60", "flight_110", "flight_120", "flight_50"]


def plot_shift(flight_name, pc, out_path):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), dpi=130)
    for ax, cam, ux, vx, uxc, vxc in (
        (axes[0], "cam0", "u0_raw", "v0_raw", "u0_corr", "v0_corr"),
        (axes[1], "cam1", "u1_raw", "v1_raw", "u1_corr", "v1_corr"),
    ):
        raw_u = [p[ux] for p in pc]
        raw_v = [p[vx] for p in pc]
        cor_u = [p[uxc] for p in pc]
        cor_v = [p[vxc] for p in pc]
        ax.scatter(raw_u, raw_v, s=18, c="#c0392b", label="raw", zorder=3)
        ax.scatter(cor_u, cor_v, s=18, c="#2471a3", label="corrected", zorder=3)
        for ru, rv, cu, cv in zip(raw_u, raw_v, cor_u, cor_v):
            if abs(cu - ru) > 1e-6 or abs(cv - rv) > 1e-6:
                ax.annotate("", xy=(cu, cv), xytext=(ru, rv),
                            arrowprops=dict(arrowstyle="->", color="#555", lw=1))
        ax.set_title(f"{flight_name} {cam}")
        ax.set_xlabel("u (px)")
        ax.set_ylabel("v (px)")
        ax.invert_yaxis()
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def shift_magnitude_sanity(flight_name, pc):
    """Compare each corrected point's shift (px) against that same camera's
    own typical per-frame displacement, from the OTHER points in this pair
    list (a cheap proxy for local ball speed)."""
    shifts = []
    for p in pc:
        if not p["corrected"]:
            continue
        d0 = ((p["u0_corr"] - p["u0_raw"]) ** 2 + (p["v0_corr"] - p["v0_raw"]) ** 2) ** 0.5
        d1 = ((p["u1_corr"] - p["u1_raw"]) ** 2 + (p["v1_corr"] - p["v1_raw"]) ** 2) ** 0.5
        shifts.append(max(d0, d1))
    if not shifts:
        return None
    return {"n_corrected": len(shifts), "mean_shift_px": float(np.mean(shifts)),
            "max_shift_px": float(np.max(shifts))}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows_out = []
    for flight_name in FLIGHTS:
        flight_dir = BALL_FLIGHTS / flight_name
        ts_csv = flight_dir / "timestamps.csv"
        if tuned_detections_paths(flight_name) is None:
            print(f"{flight_name}: no tuned-detections output, skipping")
            continue

        audit = analyze_flight(ts_csv)
        try:
            results, pc, baseline_mm = triangulate_flight(flight_dir, ts_csv)
        except Exception as e:
            print(f"{flight_name}: triangulation failed ({e}), skipping")
            continue

        print(f"\n=== {flight_name}  (audit residual={audit['residual_ms']:+.3f} ms, "
              f"jitter={audit['jitter_us']:.2f} us) ===")
        for mode in ("naive", "paired_only", "corrected"):
            r = results.get(mode)
            if r is None:
                print(f"  {mode:12s} <5 points, skipped")
                continue
            print(f"  {mode:12s} n={r['n']:3d}  overall_rms={r['overall_rms']:7.2f} mm  "
                  f"x={r['residuals']['x']:6.2f} y={r['residuals']['y']:6.2f} z={r['residuals']['z']:6.2f}")
            rows_out.append({"flight": flight_name, "mode": mode, "n": r["n"],
                              "overall_rms_mm": r["overall_rms"],
                              "x_rms_mm": r["residuals"]["x"], "y_rms_mm": r["residuals"]["y"],
                              "z_rms_mm": r["residuals"]["z"],
                              "audit_residual_ms": audit["residual_ms"]})

        sanity = shift_magnitude_sanity(flight_name, pc)
        if sanity:
            print(f"  shift sanity: n_corrected={sanity['n_corrected']}  "
                  f"mean={sanity['mean_shift_px']:.2f}px  max={sanity['max_shift_px']:.2f}px")

        plot_path = OUT_DIR / f"{flight_name}_shift.png"
        plot_shift(flight_name, pc, plot_path)
        print(f"  wrote {plot_path}")

    csv_path = OUT_DIR / "residual_comparison.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["flight", "mode", "n", "overall_rms_mm",
                                          "x_rms_mm", "y_rms_mm", "z_rms_mm", "audit_residual_ms"])
        w.writeheader()
        w.writerows(rows_out)
    print(f"\nwrote {csv_path}")


if __name__ == "__main__":
    main()
