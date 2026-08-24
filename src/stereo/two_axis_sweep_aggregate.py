# two_axis_sweep_aggregate.py
#
# Aggregates the Pi two-axis fit-window sweep (results/pi_benchmarking/
# two_axis_full_20260803.json, 150 flights x 7 W values) into:
#  - a flattened per-(flight,W) CSV (raw data, one row per run)
#  - a per-W summary table (median/p95/IQR of the required metrics)
#  - the headline "largest W where W + compute <= 430ms" result
#  - an explicit agree/diverge statement for velocity methods (a) vs (b)
#
# Read-only against the sweep JSON -- does not touch detector_core.py or
# trajectory_fit.py, no new benchmark runs.

import csv
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
IN_JSON = REPO_ROOT / "results" / "pi_benchmarking" / "two_axis_full_20260803.json"
OUT_DIR = REPO_ROOT / "results" / "pi_benchmarking" / "two_axis_sweep"
RAW_CSV = OUT_DIR / "two_axis_sweep_raw.csv"
SUMMARY_CSV = OUT_DIR / "two_axis_sweep_summary_by_W.csv"
BUDGET_MS = 430.0


def pct(sorted_vals, p):
    n = len(sorted_vals)
    if n == 0:
        return float("nan")
    idx = min(n - 1, max(0, int(round(p * (n - 1)))))
    return sorted_vals[idx]


def iqr(vals):
    s = sorted(vals)
    return pct(s, 0.75) - pct(s, 0.25)


def main():
    d = json.loads(IN_JSON.read_text())
    flights = d["flights"]

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    raw_rows = []
    for fl in flights:
        session, flight = fl["session"], fl["flight"]
        vel_a = fl.get("vel_method_a")
        vel_b = fl.get("vel_method_b")
        for row in fl["w_rows"]:
            raw_rows.append({
                "session": session, "flight": flight,
                "W_ms": row["W_ms"], "status": row["status"],
                "n_points": row.get("n_points"),
                "detect_sum_ms": row.get("detect_sum_ms"),
                "triangulate_ms": row.get("triangulate_ms"),
                "ransac_ms": row.get("ransac_ms"),
                "total_compute_ms": row.get("total_compute_ms"),
                "w_plus_compute_ms": row.get("w_plus_compute_ms"),
                "position_error_mm": row.get("position_error_mm"),
                "velocity_error_a_mm_s": row.get("velocity_error_a_mm_s"),
                "velocity_error_b_mm_s": row.get("velocity_error_b_mm_s"),
                "lead_time_ms": row.get("lead_time_ms"),
                "reason": row.get("reason", ""),
            })

    with open(RAW_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(raw_rows[0].keys()))
        w.writeheader()
        w.writerows(raw_rows)
    print(f"Wrote {RAW_CSV}: {len(raw_rows)} rows")

    W_values = d["W_values_ms"]
    summary_rows = []
    for W in W_values:
        ok_rows = [r for r in raw_rows if r["W_ms"] == W and r["status"] == "ok"]
        skipped = [r for r in raw_rows if r["W_ms"] == W and r["status"] != "ok"]
        n_ok = len(ok_rows)

        n_points_vals = sorted(r["n_points"] for r in ok_rows)
        total_compute_vals = sorted(r["total_compute_ms"] for r in ok_rows)
        w_plus_compute_vals = sorted(r["w_plus_compute_ms"] for r in ok_rows)
        pos_err_vals = [r["position_error_mm"] for r in ok_rows if r["position_error_mm"] is not None]
        vel_a_vals = [r["velocity_error_a_mm_s"] for r in ok_rows if r["velocity_error_a_mm_s"] is not None]
        vel_b_vals = [r["velocity_error_b_mm_s"] for r in ok_rows if r["velocity_error_b_mm_s"] is not None]
        pos_err_vals_s = sorted(pos_err_vals)
        vel_a_vals_s = sorted(vel_a_vals)
        vel_b_vals_s = sorted(vel_b_vals)

        row = {
            "W_ms": W,
            "n_ok": n_ok,
            "n_skipped": len(skipped),
            "n_points_median": pct(n_points_vals, 0.5) if n_points_vals else None,
            "total_compute_ms_median": pct(total_compute_vals, 0.5) if total_compute_vals else None,
            "total_compute_ms_p95": pct(total_compute_vals, 0.95) if total_compute_vals else None,
            "w_plus_compute_ms_median": pct(w_plus_compute_vals, 0.5) if w_plus_compute_vals else None,
            "w_plus_compute_ms_p95": pct(w_plus_compute_vals, 0.95) if w_plus_compute_vals else None,
            "position_error_mm_median": pct(pos_err_vals_s, 0.5) if pos_err_vals_s else None,
            "position_error_mm_iqr": iqr(pos_err_vals) if pos_err_vals else None,
            "velocity_error_a_mm_s_median": pct(vel_a_vals_s, 0.5) if vel_a_vals_s else None,
            "velocity_error_a_mm_s_iqr": iqr(vel_a_vals) if vel_a_vals else None,
            "velocity_error_b_mm_s_median": pct(vel_b_vals_s, 0.5) if vel_b_vals_s else None,
            "velocity_error_b_mm_s_iqr": iqr(vel_b_vals) if vel_b_vals else None,
            "under_430ms_budget_p95": (pct(w_plus_compute_vals, 0.95) <= BUDGET_MS) if w_plus_compute_vals else False,
            "under_430ms_budget_median": (pct(w_plus_compute_vals, 0.5) <= BUDGET_MS) if w_plus_compute_vals else False,
        }
        summary_rows.append(row)

    with open(SUMMARY_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        w.writeheader()
        w.writerows(summary_rows)
    print(f"Wrote {SUMMARY_CSV}: {len(summary_rows)} rows")

    print()
    print("=== Per-W summary ===")
    for r in summary_rows:
        print(f"W={r['W_ms']:.0f}ms  n_ok={r['n_ok']}/150  n_pts_med={r['n_points_median']:.1f}  "
              f"compute_med={r['total_compute_ms_median']:.1f}ms  compute_p95={r['total_compute_ms_p95']:.1f}ms  "
              f"W+C_med={r['w_plus_compute_ms_median']:.1f}ms  W+C_p95={r['w_plus_compute_ms_p95']:.1f}ms  "
              f"pos_err_med={r['position_error_mm_median']:.1f}mm (IQR {r['position_error_mm_iqr']:.1f})  "
              f"vel_a_med={r['velocity_error_a_mm_s_median']:.1f}mm/s (IQR {r['velocity_error_a_mm_s_iqr']:.1f})  "
              f"vel_b_med={r['velocity_error_b_mm_s_median']:.1f}mm/s (IQR {r['velocity_error_b_mm_s_iqr']:.1f})  "
              f"under430(med/p95)={r['under_430ms_budget_median']}/{r['under_430ms_budget_p95']}")

    # Headline: largest W where median W+compute stays under 430ms (report both
    # median and p95 criteria explicitly, don't silently pick one)
    under_median = [r for r in summary_rows if r["under_430ms_budget_median"]]
    under_p95 = [r for r in summary_rows if r["under_430ms_budget_p95"]]
    headline_median = max(under_median, key=lambda r: r["W_ms"]) if under_median else None
    headline_p95 = max(under_p95, key=lambda r: r["W_ms"]) if under_p95 else None

    print()
    print("=== HEADLINE ===")
    if headline_median:
        r = headline_median
        print(f"Largest W with MEDIAN(W+compute) <= 430ms: W={r['W_ms']:.0f}ms "
              f"(W+C median={r['w_plus_compute_ms_median']:.1f}ms, p95={r['w_plus_compute_ms_p95']:.1f}ms)")
        print(f"  position_error median={r['position_error_mm_median']:.1f}mm IQR={r['position_error_mm_iqr']:.1f}mm")
        print(f"  velocity_error(a, full-traj self-consistency) median={r['velocity_error_a_mm_s_median']:.1f}mm/s IQR={r['velocity_error_a_mm_s_iqr']:.1f}")
        print(f"  velocity_error(b, finite-difference) median={r['velocity_error_b_mm_s_median']:.1f}mm/s IQR={r['velocity_error_b_mm_s_iqr']:.1f}")
    else:
        print("No W satisfies median(W+compute) <= 430ms.")

    if headline_p95:
        r = headline_p95
        print(f"Largest W with P95(W+compute) <= 430ms (stricter, tail-safe): W={r['W_ms']:.0f}ms")
    else:
        print("No W satisfies p95(W+compute) <= 430ms -- even the smallest swept W's tail exceeds budget.")

    # Method (a) vs (b) agreement check, pooled across all W and flights
    print()
    print("=== Velocity method (a) vs (b) agreement ===")
    all_a = [r["velocity_error_a_mm_s"] for r in raw_rows if r["status"] == "ok" and r["velocity_error_a_mm_s"] is not None]
    all_b = [r["velocity_error_b_mm_s"] for r in raw_rows if r["status"] == "ok" and r["velocity_error_b_mm_s"] is not None]
    med_a, med_b = statistics.median(all_a), statistics.median(all_b)
    print(f"Pooled median velocity error -- method(a) full-traj self-consistency: {med_a:.1f}mm/s")
    print(f"Pooled median velocity error -- method(b) finite-difference (independent): {med_b:.1f}mm/s")
    ratio = med_b / med_a if med_a else float("inf")
    print(f"Ratio b/a: {ratio:.2f}x")
    if ratio > 3 or ratio < 1 / 3:
        print("=> DIVERGE meaningfully -- method (b) is much noisier/larger than (a), as expected for a "
              "2-3-point finite-difference estimate amplifying small-dt detection noise. Flagging per "
              "instruction, not picking one as authoritative.")
    else:
        print("=> Roughly agree (same order of magnitude).")

    b_outliers = [v for v in all_b if v > 10 * med_b]
    print(f"Method(b) extreme outliers (>10x its own median, small-dt amplification): "
          f"{len(b_outliers)}/{len(all_b)} ({100*len(b_outliers)/len(all_b):.1f}%)")


if __name__ == "__main__":
    main()
