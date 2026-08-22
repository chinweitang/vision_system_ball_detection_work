"""Step 8 - crossing-TIME convergence across the observation-window sweep.

    timing_error_ms(flight, w) = t_cross_own_ms(w) - t_cross_ms

SIGNED, so a systematic early/late bias at short windows is visible rather than
being hidden by taking absolute values first.

t_cross_own_ms comes from pipeline_sweep_full_20260804.json, which carries it per
(flight, observation window) on 2481 of 2568 records. The 87 absences are exactly
the fit_failed rows; they are excluded from the statistics but counted.

The reference is t_cross_ms from launch_to_crossing.csv. It is deliberately NOT the
sweep's last grid row: only 47 of 107 flights reach their full point count by
w=1250, and for LONG that is 2 of 60, so the last grid row is not a full-arc fit
for almost the entire LONG class.

Everything here reads existing outputs. Nothing re-runs the Pi sweep, detection,
triangulation or any fitting job.

Outputs (all new files under data/regenerate_figures/):
    figureE_timing_convergence.png
    timing_convergence_by_class_T.csv
    label_vs_modelc_timing.csv
"""
import csv
import json
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SWEEP_JSON = "data/pi_benchmarking/pipeline_sweep_full_20260804.json"
SWEEP_CSV = "data/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv"
LTC_CSV = "data/prediction/04_launch_to_crossing_budget/launch_to_crossing.csv"
LABEL_CSV = "data/prediction/06_label_vs_fit/label_vs_fit_per_flight.csv"
CROSSING_CSV = "data/prediction/01_crossing_plane_setup/crossing_classification.csv"
OUT_DIR = "data/regenerate_figures/"

CLASS_OF_BIN = {"FLAT": "SHORT", "MID": "SHORT", "LOB": "LONG"}
CLASSES = ["SHORT", "LONG"]
OPERATING_WINDOW = {"SHORT": 400, "LONG": 850}

SURF, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
CLASS_COLOR = {"SHORT": "#2a78d6", "LONG": "#e34948"}
X_LABEL = "observation window (ms)"


def percentile(values, p):
    """Linear-interpolated percentile, matching numpy's default method."""
    v = sorted(values)
    k = (len(v) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def read_csv(path):
    """csv.DictReader, not a naive split - crossing_classification.csv carries a
    quoted JSON-style list inside one field."""
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def style_axes(ax):
    ax.set_facecolor(SURF)
    ax.grid(True, color="#e5e4df", lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#d5d4cf")
    ax.tick_params(colors=INK2, labelsize=9)


def build_classes(sweep_rows):
    """{(session, flight): class}, recomputed from the bin column."""
    bin_of = {}
    for r in sweep_rows:
        key = (r["session"], r["flight"])
        if key in bin_of and bin_of[key] != r["bin"]:
            raise SystemExit(f"STOP: {key} has an inconsistent bin across windows")
        bin_of[key] = r["bin"]
    return {k: CLASS_OF_BIN[b] for k, b in bin_of.items()}


def main():
    sweep_rows = read_csv(SWEEP_CSV)
    cls_of = build_classes(sweep_rows)
    counts = {c: sum(1 for v in cls_of.values() if v == c) for c in CLASSES}
    print(f"classes recomputed from bin: SHORT={counts['SHORT']}, LONG={counts['LONG']}, "
          f"total={sum(counts.values())}")
    assert counts["SHORT"] == 47 and counts["LONG"] == 60, "expected 47 / 60"

    # Reference and per-class truncation bound, both keyed on (session, flight_id).
    ref, ltc_val = {}, {}
    for r in read_csv(LTC_CSV):
        key = (r["session"], r["flight_id"])
        ref[key] = float(r["t_cross_ms"])
        ltc_val[key] = float(r["launch_to_crossing_ms"])
    missing_ref = [k for k in cls_of if k not in ref]
    if missing_ref:
        raise SystemExit(f"STOP: {len(missing_ref)} flights lack a reference t_cross_ms")
    print(f"reference t_cross_ms present for all {len(cls_of)} flights")

    max_ltc = {c: max(v for k, v in ltc_val.items() if cls_of.get(k) == c) for c in CLASSES}
    print(f"max launch_to_crossing_ms per class (line truncation bound): "
          f"SHORT {max_ltc['SHORT']:.1f} ms, LONG {max_ltc['LONG']:.1f} ms")

    # t_cross_own_ms per (flight, window) from the JSON.
    with open(SWEEP_JSON, encoding="utf-8") as f:
        sweep = json.load(f)
    own = {}
    windows = set()
    for flight in sweep["flights"]:
        key = (flight["session"], flight["flight"])
        for row in flight["t_rows"]:
            w = int(row["T_ms"])
            windows.add(w)
            if row.get("t_cross_own_ms") is not None:
                own[(key, w)] = float(row["t_cross_own_ms"])
    windows = sorted(windows)
    total_cells = len(cls_of) * len(windows)
    print(f"t_cross_own_ms present on {len(own)} of {total_cells} (flight, window) cells, "
          f"{total_cells - len(own)} absent")

    # Per class per window statistics on the SIGNED error.
    stats = {c: [] for c in CLASSES}
    for c in CLASSES:
        flights = [k for k, v in cls_of.items() if v == c]
        for w in windows:
            signed = [own[(k, w)] - ref[k] for k in flights if (k, w) in own]
            n_missing = len(flights) - len(signed)
            if not signed:
                stats[c].append(dict(T=w, n_valid=0, n_missing=n_missing))
                continue
            a = [abs(x) for x in signed]
            stats[c].append(dict(
                T=w, n_valid=len(signed), n_missing=n_missing,
                signed_median=st.median(signed),
                signed_q1=percentile(signed, 0.25), signed_q3=percentile(signed, 0.75),
                abs_median=st.median(a), abs_q1=percentile(a, 0.25),
                abs_q3=percentile(a, 0.75), abs_p95=percentile(a, 0.95), abs_max=max(a)))

    csv_path = OUT_DIR + "timing_convergence_by_class_T.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["class", "T", "n_valid", "n_missing", "signed_median",
                    "signed_q1", "signed_q3", "abs_median", "abs_p95", "abs_max"])
        for c in CLASSES:
            for s in stats[c]:
                if s["n_valid"] == 0:
                    w.writerow([c, s["T"], 0, s["n_missing"], "", "", "", "", "", ""])
                    continue
                w.writerow([c, s["T"], s["n_valid"], s["n_missing"],
                            f"{s['signed_median']:.4f}", f"{s['signed_q1']:.4f}",
                            f"{s['signed_q3']:.4f}", f"{s['abs_median']:.4f}",
                            f"{s['abs_p95']:.4f}", f"{s['abs_max']:.4f}"])
    print(f"wrote {csv_path}")

    print()
    hdr = (f"{'class':6s} {'T':>5} {'n_val':>6} {'n_mis':>6} {'signed_med':>11} "
           f"{'abs_med':>9} {'abs_p95':>9} {'abs_max':>9}")
    print(hdr)
    print("-" * len(hdr))
    for c in CLASSES:
        for s in stats[c]:
            if s["n_valid"] == 0:
                print(f"{c:6s} {s['T']:>5} {0:>6} {s['n_missing']:>6}"
                      f"{'  (no valid rows)':>40}")
                continue
            print(f"{c:6s} {s['T']:>5} {s['n_valid']:>6} {s['n_missing']:>6} "
                  f"{s['signed_median']:>11.1f} {s['abs_median']:>9.1f} "
                  f"{s['abs_p95']:>9.1f} {s['abs_max']:>9.1f}")

    print()
    print("=== ACTUATOR PLATEAU SIZING, at each class's operating window ===")
    for c in CLASSES:
        w = OPERATING_WINDOW[c]
        s = next(x for x in stats[c] if x["T"] == w)
        print(f"  {c:5s} window {w:4d} ms   abs p95 = {s['abs_p95']:7.1f} ms   "
              f"signed median = {s['signed_median']:+7.1f} ms   "
              f"IQR [{s['signed_q1']:+.1f}, {s['signed_q3']:+.1f}]   "
              f"n_valid={s['n_valid']}, n_missing={s['n_missing']}")

    # ---- Figure E ----
    fig, ax = plt.subplots(figsize=(10, 6.2))
    fig.patch.set_facecolor(SURF)
    style_axes(ax)
    for c in CLASSES:
        pts = [s for s in stats[c] if s["n_valid"] > 0 and s["T"] <= max_ltc[c]]
        xs = [s["T"] for s in pts]
        ax.fill_between(xs, [s["abs_q1"] for s in pts], [s["abs_q3"] for s in pts],
                        color=CLASS_COLOR[c], alpha=0.15, lw=0, zorder=2)
        ax.plot(xs, [s["abs_median"] for s in pts], color=CLASS_COLOR[c], lw=2.0,
                marker="o", ms=5, mec=SURF, mew=1.2, zorder=3,
                label=f"{c} median |timing error|, n={counts[c]} (shaded = IQR)")
    # Headroom added before annotating so the rotated operating-window labels sit
    # above the data band, and the legend is dropped below that zone - otherwise
    # the LONG label at x=850 runs straight into the legend box.
    lo, hi = ax.get_ylim()
    hi = lo + (hi - lo) * 1.18
    ax.set_ylim(lo, hi)
    for c in CLASSES:
        w = OPERATING_WINDOW[c]
        ax.axvline(w, color=CLASS_COLOR[c], ls=":", lw=1.5, zorder=2)
        ax.annotate(f"{c} operating window {w} ms", xy=(w, hi),
                    xytext=(w - 14, hi - 0.02 * (hi - lo)), color=CLASS_COLOR[c],
                    fontsize=8.5, rotation=90, ha="right", va="top")
    ax.set_xlabel(X_LABEL, color=INK, fontsize=10.5)
    ax.set_ylabel("crossing-time error, median |t_own - t_ref|  (ms)",
                  color=INK, fontsize=10.5)
    ax.set_title("Crossing-TIME convergence vs observation window, two-class scheme",
                 color=INK, fontsize=12.5, loc="left", pad=12)
    ax.legend(frameon=False, fontsize=9.5, labelcolor=INK2, loc="upper right",
              bbox_to_anchor=(1.0, 0.86))

    caption = [
        "CONVERGENCE against the full-arc Model-C crossing time (t_cross_ms from launch_to_crossing.csv), NOT accuracy against ground truth.",
        f"Each class line is truncated at its own maximum launch_to_crossing_ms (SHORT {max_ltc['SHORT']:.0f} ms, LONG {max_ltc['LONG']:.0f} ms); beyond that the window",
        "exceeds every flight in the class. fit_failed rows carry no t_cross_own_ms and are excluded from the statistics; counts are in timing_convergence_by_class_T.csv.",
    ]
    for i, line in enumerate(caption):
        fig.text(0.012, 0.042 - i * 0.018, line, color=INK2, fontsize=7.6)

    fig.tight_layout(rect=[0, 0.075, 1, 1])
    fig_path = OUT_DIR + "figureE_timing_convergence.png"
    fig.savefig(fig_path, dpi=150, facecolor=SURF)
    plt.close(fig)
    print(f"wrote {fig_path}")

    # ---- separate small job: label vs Model-C full-arc timing agreement ----
    print()
    print("=== LABEL vs MODEL-C full-arc crossing-time agreement (n=20 labelled) ===")
    labels = read_csv(LABEL_CSV)
    sess_of = {(r["registration"], r["flight_id"]): r["session"] for r in read_csv(CROSSING_CSV)}
    rows = []
    for L in labels:
        key = (L["registration"], L["flight_id"])
        diff = float(L["t_cross_label"]) * 1000.0 - float(L["t_cross_modelc"]) * 1000.0
        rows.append(dict(session=sess_of[key], flight_id=L["flight_id"],
                         registration=L["registration"], elevation_bin=L["elevation_bin"],
                         symmetric=L["symmetric"],
                         t_cross_label_ms=float(L["t_cross_label"]) * 1000.0,
                         t_cross_modelc_ms=float(L["t_cross_modelc"]) * 1000.0,
                         diff_ms=diff, abs_diff_ms=abs(diff)))
    rows.sort(key=lambda r: -r["abs_diff_ms"])
    lab_csv = OUT_DIR + "label_vs_modelc_timing.csv"
    with open(lab_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v)
                        for k, v in r.items()})
    a = [r["abs_diff_ms"] for r in rows]
    s = [r["diff_ms"] for r in rows]
    print(f"  n={len(rows)}   median|diff| = {st.median(a):.2f} ms   "
          f"p95|diff| = {percentile(a, 0.95):.2f} ms   max|diff| = {max(a):.2f} ms")
    print(f"  signed: median {st.median(s):+.2f} ms, mean {st.mean(s):+.2f} ms, "
          f"range [{min(s):+.2f}, {max(s):+.2f}]")
    print("  largest 5 by |diff|:")
    for r in rows[:5]:
        print(f"    {r['flight_id']:<11s} {r['registration']:<9s} {r['elevation_bin']:<5s} "
              f"label {r['t_cross_label_ms']:8.1f}  modelc {r['t_cross_modelc_ms']:8.1f}  "
              f"diff {r['diff_ms']:+7.2f} ms")
    print(f"  wrote {lab_csv}")


if __name__ == "__main__":
    main()
