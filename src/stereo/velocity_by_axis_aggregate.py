# velocity_by_axis_aggregate.py
#
# claude/prompts/2026-08-05_1254_pi_sweep_rerun_velocity_error_components.md
#
# Aggregates the per-axis velocity re-run
# (data/pi_benchmarking/pipeline_sweep_full_vaxis_20260805.json, regression-
# checked 0-mismatch against the original pipeline_sweep_full_20260804.json)
# into per-(bin, axis, T) BIAS (signed mean error) and SCATTER (RMS of
# signed error), reported SEPARATELY -- bias is correctable, scatter is a
# floor, collapsing them into one number would hide that distinction.
#
# Read-only against the new JSON -- does NOT touch pipeline_sweep_raw.csv,
# margin_analysis.csv, or any existing file. Writes only to NEW filenames
# under figures2/.

import csv
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
IN_JSON = REPO_ROOT / "data" / "pi_benchmarking" / "pipeline_sweep_full_vaxis_20260805.json"
LAUNCH_TO_CROSSING_CSV = REPO_ROOT / "data" / "prediction" / "04_launch_to_crossing_budget" / "launch_to_crossing.csv"
OUT_DIR = REPO_ROOT / "data" / "pi_benchmarking" / "02_pi_pipeline_sweep_parallel_detection" / "figures2"

BIN_ORDER = ["FLAT", "MID", "LOB"]
AXES = ["X_depth", "Y_width", "Z_up"]
AXIS_ERR_KEY = {"X_depth": "err_vx", "Y_width": "err_vy", "Z_up": "err_vz"}


def elevation_bin(elevation_deg: float) -> str:
    if elevation_deg < 15.0:
        return "FLAT"
    elif elevation_deg < 45.0:
        return "MID"
    return "LOB"


def load_bins():
    out = {}
    with open(LAUNCH_TO_CROSSING_CSV, newline="") as f:
        for row in csv.DictReader(f):
            out[(row["session"], row["flight_id"])] = elevation_bin(float(row["elevation_deg"]))
    return out


def pct(sorted_vals, p):
    n = len(sorted_vals)
    if n == 0:
        return float("nan")
    idx_f = p * (n - 1)
    lo, hi = int(np.floor(idx_f)), int(np.ceil(idx_f))
    if lo == hi:
        return sorted_vals[lo]
    frac = idx_f - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    d = json.loads(IN_JSON.read_text())
    flights = d["flights"]
    T_values = d["T_values_ms"]
    bins = load_bins()

    raw_rows = []
    for fl in flights:
        key = (fl["session"], fl["flight"])
        b = bins.get(key)
        for row in fl.get("t_rows", []):
            if row["status"] != "ok":
                continue
            raw_rows.append({
                "session": fl["session"], "flight": fl["flight"], "bin": b, "T_ms": row["T_ms"],
                "vx_own": row["vx_own"], "vy_own": row["vy_own"], "vz_own": row["vz_own"],
                "vx_ref": row["vx_ref"], "vy_ref": row["vy_ref"], "vz_ref": row["vz_ref"],
                "err_vx": row["err_vx"], "err_vy": row["err_vy"], "err_vz": row["err_vz"],
                "velocity_error_mm_s": row["velocity_error_mm_s"],
            })

    raw_csv = OUT_DIR / "velocity_by_axis_raw.csv"
    with open(raw_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(raw_rows[0].keys()))
        w.writeheader()
        w.writerows(raw_rows)
    print(f"Wrote {raw_csv}: {len(raw_rows)} rows")

    summary_rows = []
    for b in BIN_ORDER:
        for T in T_values:
            sub = [r for r in raw_rows if r["bin"] == b and r["T_ms"] == T]
            n = len(sub)
            row = {"bin": b, "T_ms": T, "n": n}
            for axis in AXES:
                key = AXIS_ERR_KEY[axis]
                vals = [r[key] for r in sub]
                if vals:
                    bias = float(np.mean(vals))
                    scatter_rms = float(np.sqrt(np.mean(np.square(vals))))
                    abs_vals = sorted(abs(v) for v in vals)
                    median_abs = pct(abs_vals, 0.5)
                else:
                    bias = scatter_rms = median_abs = float("nan")
                row[f"{axis}_bias_mm_s"] = bias
                row[f"{axis}_scatter_rms_mm_s"] = scatter_rms
                row[f"{axis}_median_abs_mm_s"] = median_abs
            summary_rows.append(row)

    summary_csv = OUT_DIR / "velocity_by_axis_summary.csv"
    with open(summary_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        w.writeheader()
        w.writerows(summary_rows)
    print(f"Wrote {summary_csv}: {len(summary_rows)} rows")

    # -- numeric summary at each regime's max-usable-t (from margin_analysis.csv) --
    max_usable_t = {"FLAT": 300.0, "MID": 450.0, "LOB": 800.0}
    print("\n=== Per-axis bias/scatter AT each regime's max-usable-t ===")
    for b in BIN_ORDER:
        mt = max_usable_t[b]
        r = next(x for x in summary_rows if x["bin"] == b and x["T_ms"] == mt)
        print(f"\n{b} (T={mt:.0f}ms, n={r['n']}):")
        for axis in AXES:
            print(f"  {axis}: bias={r[f'{axis}_bias_mm_s']:+.1f}mm/s  "
                  f"scatter(rms)={r[f'{axis}_scatter_rms_mm_s']:.1f}mm/s  "
                  f"median|err|={r[f'{axis}_median_abs_mm_s']:.1f}mm/s")

    print("\n=== Full per-(bin,T) table, per axis (bias / scatter) ===")
    for b in BIN_ORDER:
        print(f"\n{b}:")
        header = f"{'T_ms':>6s}"
        for axis in AXES:
            header += f" {axis+'_bias':>14s} {axis+'_rms':>12s}"
        print(header)
        for r in sorted([x for x in summary_rows if x["bin"] == b], key=lambda x: x["T_ms"]):
            line = f"{r['T_ms']:>6.0f}"
            for axis in AXES:
                line += f" {r[f'{axis}_bias_mm_s']:>14.1f} {r[f'{axis}_scatter_rms_mm_s']:>12.1f}"
            print(line)

    return raw_rows, summary_rows


if __name__ == "__main__":
    main()
