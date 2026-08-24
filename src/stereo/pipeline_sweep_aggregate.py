# pipeline_sweep_aggregate.py
#
# Aggregates the Pi prediction-pipeline sweep
# (results/pi_benchmarking/pipeline_sweep_full_20260804.json, 107 crossers x
# 24 cutoff-time T values) into per-elevation-bin summaries: error(T),
# HIT/MISS accuracy(T), eligible_n(T), latency(T) -- split FLAT/MID/LOB,
# NEVER pooled raw across regimes. Produces the t=490ms V1 headline table,
# per-bin t_min (smallest T with median error<100mm AND accuracy>=90%,
# both provisional thresholds), and the per-bin binding-constraint
# (error- vs latency-bound) statement.
#
# ACCURACY IS A CONVERGENCE RESULT (early-cutoff fit vs the full-arc Model-C
# fit already frozen in 01_crossing_plane_setup/crossing_classification.csv)
# -- NOT ground-truth accuracy. Manual crossing-bracket labels are not ready
# yet. Every accuracy number here is labelled as a placeholder, to be
# re-run against real labels later.
#
# Read-only against the sweep JSON + launch_to_crossing.csv (for elevation
# bin assignment, same source used throughout today) -- no new Pi runs.

import csv
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
IN_JSON = REPO_ROOT / "results" / "pi_benchmarking" / "pipeline_sweep_full_20260804.json"
LAUNCH_TO_CROSSING_CSV = REPO_ROOT / "results" / "prediction" / "04_launch_to_crossing_budget" / "launch_to_crossing.csv"
OUT_DIR = REPO_ROOT / "results" / "pi_benchmarking" / "02_pi_pipeline_sweep_parallel_detection"

HEADLINE_T_MS = 490.0
POSITION_ERROR_THRESHOLD_MM = 100.0  # provisional
ACCURACY_THRESHOLD = 0.90  # provisional, "high" HIT/MISS accuracy
BIN_ORDER = ["FLAT", "MID", "LOB"]


def elevation_bin(elevation_deg: float) -> str:
    if elevation_deg < 15.0:
        return "FLAT"
    elif elevation_deg < 45.0:
        return "MID"
    return "LOB"


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


def load_bins():
    out = {}
    with open(LAUNCH_TO_CROSSING_CSV, newline="") as f:
        for row in csv.DictReader(f):
            out[(row["session"], row["flight_id"])] = elevation_bin(float(row["elevation_deg"]))
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    d = json.loads(IN_JSON.read_text())
    flights = d["flights"]
    T_values = d["T_values_ms"]
    bins = load_bins()

    # -- flatten to per-(flight,T) rows with bin assigned --
    raw_rows = []
    for fl in flights:
        key = (fl["session"], fl["flight"])
        b = bins.get(key)
        for row in fl.get("t_rows", []):
            raw_rows.append({
                "session": fl["session"], "flight": fl["flight"], "bin": b,
                "T_ms": row["T_ms"], "status": row["status"], "airborne": row.get("airborne"),
                "n_detected": row.get("n_detected"), "n_ideal_cadence": row.get("n_ideal_cadence"),
                "position_error_mm": row.get("position_error_mm"),
                "velocity_error_mm_s": row.get("velocity_error_mm_s"),
                "hit_miss_match": row.get("hit_miss_match"),
                "latency_ms": row.get("latency_ms"), "latency_feasible": row.get("latency_feasible"),
                "last_pair_detect_ms": row.get("last_pair_detect_ms"),
                "triangulate_ms": row.get("triangulate_ms"), "ransac_ms": row.get("ransac_ms"),
                "predict_ms": row.get("predict_ms"),
            })

    raw_csv = OUT_DIR / "pipeline_sweep_raw.csv"
    with open(raw_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(raw_rows[0].keys()))
        w.writeheader()
        w.writerows(raw_rows)
    print(f"Wrote {raw_csv}: {len(raw_rows)} rows")

    # -- per-bin, per-T aggregation --
    summary_rows = []
    for b in BIN_ORDER:
        for T in T_values:
            sub = [r for r in raw_rows if r["bin"] == b and r["T_ms"] == T]
            n_airborne = sum(1 for r in sub if r["airborne"])
            n_ok = sum(1 for r in sub if r["status"] == "ok")
            ok_rows = [r for r in sub if r["status"] == "ok"]

            pos_err = sorted(r["position_error_mm"] for r in ok_rows)
            vel_err = sorted(r["velocity_error_mm_s"] for r in ok_rows)
            lat = sorted(r["latency_ms"] for r in ok_rows)
            hit_match = [r["hit_miss_match"] for r in ok_rows]

            summary_rows.append({
                "bin": b, "T_ms": T, "n_airborne": n_airborne, "n_fit_ok": n_ok,
                "position_error_median_mm": pct(pos_err, 0.5) if pos_err else float("nan"),
                "position_error_iqr_mm": iqr([r["position_error_mm"] for r in ok_rows]),
                "velocity_error_median_mm_s": pct(vel_err, 0.5) if vel_err else float("nan"),
                "velocity_error_iqr_mm_s": iqr([r["velocity_error_mm_s"] for r in ok_rows]),
                "hit_miss_accuracy": float(np.mean(hit_match)) if hit_match else float("nan"),
                "latency_median_ms": pct(lat, 0.5) if lat else float("nan"),
                "latency_iqr_ms": iqr([r["latency_ms"] for r in ok_rows]),
                "latency_feasible_frac": float(np.mean([r["latency_feasible"] for r in ok_rows])) if ok_rows else float("nan"),
            })

    summary_csv = OUT_DIR / "pipeline_sweep_summary_by_bin_T.csv"
    with open(summary_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        w.writeheader()
        w.writerows(summary_rows)
    print(f"Wrote {summary_csv}: {len(summary_rows)} rows")

    # -- detection diagnostics (pooled across the whole run) --
    all_last_pair = [r["last_pair_detect_ms"] for r in raw_rows if r["status"] == "ok"]
    detect_stats = {
        "median": pct(sorted(all_last_pair), 0.5), "p95": pct(sorted(all_last_pair), 0.95),
        "p99": pct(sorted(all_last_pair), 0.99), "max": max(all_last_pair), "min": min(all_last_pair),
    }
    over_cadence_total = sum(fl.get("over_cadence_pair_count", 0) for fl in flights)
    over_cadence_detail = []
    for fl in flights:
        for f in fl.get("over_cadence_pairs", []):
            over_cadence_detail.append((fl["session"], fl["flight"], f))

    # thermal-drift diagnostic: flight processing order == wall-clock order
    # (main() iterates sorted(reference.keys()) once, in order) -- compare
    # first-quartile vs last-quartile median per-flight detect time.
    per_flight_median_detect = []
    for fl in flights:
        vals = [row.get("last_pair_detect_ms") for row in fl.get("t_rows", []) if row.get("status") == "ok"]
        if vals:
            per_flight_median_detect.append(float(np.median(vals)))
    n_fl = len(per_flight_median_detect)
    q = max(1, n_fl // 4)
    first_q_median = float(np.median(per_flight_median_detect[:q]))
    last_q_median = float(np.median(per_flight_median_detect[-q:]))
    drift_delta_ms = last_q_median - first_q_median

    # -- t=490ms V1 headline --
    headline = {b: next(r for r in summary_rows if r["bin"] == b and r["T_ms"] == HEADLINE_T_MS) for b in BIN_ORDER}

    # -- per-bin t_min: smallest T with median error<threshold AND accuracy>=threshold --
    t_min = {}
    for b in BIN_ORDER:
        rows_b = sorted([r for r in summary_rows if r["bin"] == b], key=lambda r: r["T_ms"])
        found = None
        for r in rows_b:
            if (not np.isnan(r["position_error_median_mm"]) and
                    r["position_error_median_mm"] < POSITION_ERROR_THRESHOLD_MM and
                    not np.isnan(r["hit_miss_accuracy"]) and
                    r["hit_miss_accuracy"] >= ACCURACY_THRESHOLD):
                found = r["T_ms"]
                break
        t_min[b] = found

    # -- binding constraint at T=490 per bin --
    binding = {}
    for b in BIN_ORDER:
        h = headline[b]
        error_ok = (not np.isnan(h["position_error_median_mm"]) and
                    h["position_error_median_mm"] < POSITION_ERROR_THRESHOLD_MM)
        latency_ok = (not np.isnan(h["latency_median_ms"]) and h["latency_median_ms"] <= HEADLINE_T_MS)
        if error_ok and latency_ok:
            binding[b] = "NEITHER BINDS (both within provisional thresholds -- has slack on both axes)"
        elif not latency_ok:
            binding[b] = "LATENCY-BOUND (median latency exceeds 490ms)"
        elif not error_ok:
            binding[b] = "ERROR-BOUND (latency has slack, position error is the limiter)"
        else:
            binding[b] = "BOTH FAIL (neither error nor latency within provisional thresholds)"

    # -- write summary.txt --
    summary_txt = OUT_DIR / "summary.txt"
    with open(summary_txt, "w") as f:
        f.write("Pi prediction-pipeline sweep -- per-elevation-bin summary\n")
        f.write("=" * 78 + "\n\n")
        f.write("*** ACCURACY IS A CONVERGENCE RESULT (early-cutoff Model-C fit vs the\n")
        f.write("full-arc fit already frozen in 01_crossing_plane_setup/\n")
        f.write("crossing_classification.csv) -- NOT ground-truth accuracy. Manual\n")
        f.write("crossing-bracket labels are not ready yet. Re-run against real labels\n")
        f.write("once available. ***\n\n")

        f.write("--- Step 1 checkpoint (for reference) ---\n")
        f.write("Threaded per-pair detect: median=13.578ms, p95=14.973ms -- BELOW 16.667ms\n")
        f.write("cadence (speedup 1.27x vs serial, well under the 1.7x clean-parallelism bar\n")
        f.write("-- TBB thread-pool contention, not clean 2x). Capture-bound regime assumed\n")
        f.write("throughout this sweep's latency model.\n\n")

        f.write("--- Full-sweep detect diagnostics (n={} pairs sampled via t_rows) ---\n".format(len(all_last_pair)))
        f.write(f"median={detect_stats['median']:.3f}ms p95={detect_stats['p95']:.3f}ms "
                f"p99={detect_stats['p99']:.3f}ms max={detect_stats['max']:.3f}ms "
                f"min={detect_stats['min']:.3f}ms\n")
        f.write(f"Pairs exceeding 16.667ms cadence (whole run, all frames not just sampled): "
                f"{over_cadence_total}\n")
        for session, flight, frame in over_cadence_detail:
            f.write(f"  over-cadence: {session}/{flight} frame {frame}\n")
        f.write(f"Thermal drift check: first-quartile flights (n={q}) median detect="
                f"{first_q_median:.3f}ms, last-quartile (n={q}) median="
                f"{last_q_median:.3f}ms, delta={drift_delta_ms:+.3f}ms "
                f"({'negligible' if abs(drift_delta_ms) < 1.0 else 'NOTABLE -- possible thermal drift'})\n\n")

        f.write(f"--- V1 HEADLINE at T={HEADLINE_T_MS:.0f}ms (per bin) ---\n")
        f.write(f"{'bin':6s} {'n_airborne':>11s} {'n_fit_ok':>9s} {'hit_miss_acc':>13s} "
                f"{'pos_err_med(IQR)':>20s} {'vel_err_med(IQR)':>20s} {'latency_med(IQR)':>20s} "
                f"{'lat_feas_frac':>14s}\n")
        for b in BIN_ORDER:
            h = headline[b]
            f.write(f"{b:6s} {h['n_airborne']:>11d} {h['n_fit_ok']:>9d} "
                    f"{h['hit_miss_accuracy']*100:>12.1f}% "
                    f"{h['position_error_median_mm']:>10.1f} ({h['position_error_iqr_mm']:>6.1f}) "
                    f"{h['velocity_error_median_mm_s']:>10.1f} ({h['velocity_error_iqr_mm_s']:>6.1f}) "
                    f"{h['latency_median_ms']:>10.1f} ({h['latency_iqr_ms']:>6.1f}) "
                    f"{h['latency_feasible_frac']*100:>13.1f}%\n")
        f.write("\n")

        f.write(f"--- Binding constraint at T=490ms (provisional thresholds: "
                f"position error<{POSITION_ERROR_THRESHOLD_MM:.0f}mm, "
                f"accuracy>={ACCURACY_THRESHOLD*100:.0f}%) ---\n")
        for b in BIN_ORDER:
            f.write(f"{b}: {binding[b]}\n")
        f.write("\n")

        f.write(f"--- Per-bin t_min (smallest T with median position error<"
                f"{POSITION_ERROR_THRESHOLD_MM:.0f}mm AND HIT/MISS accuracy>="
                f"{ACCURACY_THRESHOLD*100:.0f}%, both provisional) ---\n")
        for b in BIN_ORDER:
            v = t_min[b]
            f.write(f"{b}: {'t_min=' + str(v) + 'ms' if v is not None else 'NEVER reached within swept range'}\n")
        f.write("\n")

        f.write("--- Full T sweep, per bin (median values) ---\n")
        for b in BIN_ORDER:
            f.write(f"\n{b}:\n")
            f.write(f"{'T_ms':>6s} {'n_air':>6s} {'n_ok':>5s} {'pos_err':>9s} {'vel_err':>9s} "
                    f"{'acc':>6s} {'latency':>9s} {'lat_feas':>9s}\n")
            for r in sorted([x for x in summary_rows if x["bin"] == b], key=lambda x: x["T_ms"]):
                f.write(f"{r['T_ms']:>6.0f} {r['n_airborne']:>6d} {r['n_fit_ok']:>5d} "
                        f"{r['position_error_median_mm']:>9.1f} {r['velocity_error_median_mm_s']:>9.1f} "
                        f"{r['hit_miss_accuracy']*100:>5.1f}% {r['latency_median_ms']:>9.1f} "
                        f"{r['latency_feasible_frac']*100:>8.1f}%\n")

    print(f"Wrote {summary_txt}")

    print("\n=== V1 HEADLINE @ T=490ms ===")
    for b in BIN_ORDER:
        h = headline[b]
        print(f"{b}: n_airborne={h['n_airborne']} n_fit_ok={h['n_fit_ok']} "
              f"hit_miss_acc={h['hit_miss_accuracy']*100:.1f}% "
              f"pos_err_med={h['position_error_median_mm']:.1f}mm "
              f"vel_err_med={h['velocity_error_median_mm_s']:.1f}mm/s "
              f"latency_med={h['latency_median_ms']:.1f}ms "
              f"latency_feasible={h['latency_feasible_frac']*100:.1f}% "
              f"-- {binding[b]}")
    print("\n=== t_min per bin ===")
    for b in BIN_ORDER:
        print(f"{b}: {t_min[b]}")
    print(f"\nDetect: median={detect_stats['median']:.3f}ms p95={detect_stats['p95']:.3f}ms "
          f"p99={detect_stats['p99']:.3f}ms max={detect_stats['max']:.3f}ms, "
          f"over-cadence pairs (whole run)={over_cadence_total}, "
          f"thermal drift delta={drift_delta_ms:+.3f}ms")


if __name__ == "__main__":
    main()
