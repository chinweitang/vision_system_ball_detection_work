# pipeline_sweep_margin_analysis.py
#
# claude/prompts/2026-08-05_1233_pi_pipeline_sweep_new_graphs.md
#
# Corrects the earlier figures (decision 76's figure3_latency_vs_t.png),
# which plotted latency(t) alone -- dropping the observation term t itself
# and making feasibility look trivially easy. The TRUE constraint: a
# prediction made using points up to cutoff t isn't ready until
# T_ready(t) = t + latency(t) has elapsed on the launch-relative clock (t=0
# = first-usable-fit-frame, same clock as the crossing deadline). Feasible
# iff T_ready(t) < deadline, i.e. margin(t) = deadline - t - latency(t) > 0.
#
# WORST-CASE pairing: margin_p95(t) = deadline - t - latency_p95(t) is the
# real guarantee (an average-case number is not a guarantee). Median
# latency is a companion reference only, never the feasibility boundary.
#
# Read-only against pipeline_sweep_raw.csv / pipeline_sweep_summary_by_bin_T.csv
# (data/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/) -- latency
# p95 per (bin,T) is NOT in the summary CSV (only median+IQR), so it's
# recomputed here directly from the raw per-(flight,T) rows -- still pure
# re-aggregation of already-persisted data, not a new Pi run.
#
# Per-component velocity error is NOT available in either file (checked
# both directly -- only the scalar norm was ever persisted); Figure 4
# (velocity by axis) is BLOCKED, not attempted here. See worklog.

import csv
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
SWEEP_DIR = REPO_ROOT / "data" / "pi_benchmarking" / "02_pi_pipeline_sweep_parallel_detection"
RAW_CSV = SWEEP_DIR / "pipeline_sweep_raw.csv"
OUT_CSV = SWEEP_DIR / "figures2" / "margin_analysis.csv"

BIN_ORDER = ["FLAT", "MID", "LOB"]
DEADLINE_MS = {"FLAT": 490.0, "MID": 710.0, "LOB": 1080.0}
POSITION_ERROR_THRESHOLD_MM = 100.0


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


def iqr(vals):
    if not vals:
        return float("nan")
    s = sorted(vals)
    return pct(s, 0.75) - pct(s, 0.25)


def load_raw():
    with open(RAW_CSV, newline="") as f:
        return list(csv.DictReader(f))


def main():
    (SWEEP_DIR / "figures2").mkdir(parents=True, exist_ok=True)
    raw = load_raw()
    T_values = sorted(set(float(r["T_ms"]) for r in raw))

    rows_out = []
    for b in BIN_ORDER:
        deadline = DEADLINE_MS[b]
        for T in T_values:
            sub_ok = [r for r in raw if r["bin"] == b and float(r["T_ms"]) == T and r["status"] == "ok"]
            lat = sorted(float(r["latency_ms"]) for r in sub_ok)
            pos = sorted(float(r["position_error_mm"]) for r in sub_ok)
            n_ok = len(sub_ok)

            lat_med = pct(lat, 0.5) if lat else float("nan")
            lat_p95 = pct(lat, 0.95) if lat else float("nan")
            T_ready_med = T + lat_med
            T_ready_p95 = T + lat_p95
            margin_med = deadline - T - lat_med
            margin_p95 = deadline - T - lat_p95

            rows_out.append({
                "bin": b, "T_ms": T, "deadline_ms": deadline, "n_fit_ok": n_ok,
                "latency_median_ms": lat_med, "latency_p95_ms": lat_p95,
                "T_ready_median_ms": T_ready_med, "T_ready_p95_ms": T_ready_p95,
                "margin_median_ms": margin_med, "margin_p95_ms": margin_p95,
                "feasible_p95": bool(margin_p95 > 0),
                "position_error_median_mm": pct(pos, 0.5) if pos else float("nan"),
                "position_error_iqr_mm": iqr([float(r["position_error_mm"]) for r in sub_ok]),
            })

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)
    print(f"Wrote {OUT_CSV}: {len(rows_out)} rows")

    # -- max-usable-t per bin: largest T with margin_p95(T) > 0 --
    max_usable_t = {}
    for b in BIN_ORDER:
        rows_b = sorted([r for r in rows_out if r["bin"] == b], key=lambda r: r["T_ms"])
        feasible_Ts = [r["T_ms"] for r in rows_b if r["feasible_p95"]]
        max_usable_t[b] = max(feasible_Ts) if feasible_Ts else None

    print("\n=== max-usable-t per bin (largest T with margin_p95>0) ===")
    for b in BIN_ORDER:
        print(f"{b}: max_usable_t={max_usable_t[b]}")

    print("\n=== Accuracy AT max-usable-t (position; velocity per-component BLOCKED) ===")
    at_operating_point = {}
    for b in BIN_ORDER:
        mt = max_usable_t[b]
        if mt is None:
            print(f"{b}: no feasible T found")
            continue
        r = next(x for x in rows_out if x["bin"] == b and x["T_ms"] == mt)
        at_operating_point[b] = r
        print(f"{b}: T={mt:.0f}ms  margin_p95={r['margin_p95_ms']:.1f}ms  "
              f"pos_err_med={r['position_error_median_mm']:.1f}mm (IQR {r['position_error_iqr_mm']:.1f})  "
              f"n_fit_ok={r['n_fit_ok']}")

    print("\n=== Full per-(bin,T) table ===")
    for b in BIN_ORDER:
        print(f"\n{b} (deadline={DEADLINE_MS[b]:.0f}ms):")
        print(f"{'T_ms':>6s} {'lat_med':>8s} {'lat_p95':>8s} {'Tready_med':>11s} {'Tready_p95':>11s} "
              f"{'margin_med':>11s} {'margin_p95':>11s} {'feas_p95':>9s} {'pos_err_med':>12s}")
        for r in sorted([x for x in rows_out if x["bin"] == b], key=lambda x: x["T_ms"]):
            print(f"{r['T_ms']:>6.0f} {r['latency_median_ms']:>8.1f} {r['latency_p95_ms']:>8.1f} "
                  f"{r['T_ready_median_ms']:>11.1f} {r['T_ready_p95_ms']:>11.1f} "
                  f"{r['margin_median_ms']:>11.1f} {r['margin_p95_ms']:>11.1f} "
                  f"{'YES' if r['feasible_p95'] else 'NO':>9s} {r['position_error_median_mm']:>12.1f}")

    return rows_out, max_usable_t


if __name__ == "__main__":
    main()
