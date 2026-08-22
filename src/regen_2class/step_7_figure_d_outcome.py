"""Step 7 - Figure D: per-flight outcome sweep across the observation-window grid.

Per flight per window:
    t_obs    = min(window, duration_ms)
    answered = status == "ok"
    in_time  = (t_obs + latency_ms) <= (launch_to_crossing_ms + TARGET_SLACK_MS)
    accurate = position_error_mm < accurate_mm

Verdict precedence, first match wins:
    not answered -> no_response
    not in_time  -> late
    not accurate -> wrong
    otherwise    -> success

fit_failed rows are NOT dropped: they are the no_response band, and the
denominator is always the full panel n.

Runs twice. The 200 mm threshold is the headline. The 170 mm run is a sensitivity
check: position_error_mm is CONVERGENCE against the full-arc Model-C fit, not error
against ground truth, and total error against truth is roughly the quadrature of
convergence and the ~106 mm label-vs-fit accuracy floor. A 200 mm requirement
against truth therefore corresponds to about sqrt(200^2 - 106^2) = 170 mm of
allowable convergence error.

Panel order is POOLED, SHORT, LONG. POOLED is the headline: the deployed system has
no regime classifier and must run one universal window, so pooled is actual
performance while the per-class panels are the classifier-equipped upper bound.
"""
import csv
import math
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import regen_2class.common as C

PANELS = ["POOLED", "SHORT", "LONG"]      # POOLED first: it is the headline
ACCURATE_MM_MAIN = 200.0
ACCURATE_MM_SENS = 170.0                  # sqrt(200^2 - 106^2), see module docstring
LABEL_FLOOR_MM = 106.0


def classify(row, accurate_mm):
    """(verdict, answered, in_time, accurate). in_time/accurate are None when the
    fit failed, since latency and position error do not exist on those rows."""
    t_obs = min(float(row["T_ms"]), float(row["duration_ms"]))
    if row["status"] != "ok":
        return "no_response", False, None, None
    in_time = (t_obs + float(row["latency_ms"])) <= (
        float(row["launch_to_crossing_ms"]) + C.TARGET_SLACK_MS)
    accurate = float(row["position_error_mm"]) < accurate_mm
    if not in_time:
        return "late", True, in_time, accurate
    if not accurate:
        return "wrong", True, in_time, accurate
    return "success", True, in_time, accurate


def evaluate(rows, windows, accurate_mm):
    per_rows = []
    for r in rows:
        verdict, answered, in_time, accurate = classify(r, accurate_mm)
        per_rows.append({
            "session": r["session"], "flight": r["flight"], "cls2": r["cls2"],
            "T_ms": int(r["T_ms"]), "status": r["status"],
            "t_obs_ms": f"{min(float(r['T_ms']), float(r['duration_ms'])):.4f}",
            "duration_ms": r["duration_ms"],
            "launch_to_crossing_ms": r["launch_to_crossing_ms"],
            "latency_ms": r["latency_ms"], "position_error_mm": r["position_error_mm"],
            "answered": answered,
            "in_time": "" if in_time is None else in_time,
            "accurate": "" if accurate is None else accurate,
            "verdict": verdict,
        })

    n_of = {c: len({(p["session"], p["flight"]) for p in per_rows if p["cls2"] == c})
            for c in C.CLASSES}
    n_of["POOLED"] = n_of["SHORT"] + n_of["LONG"]

    def subset(panel, w):
        return [p for p in per_rows if p["T_ms"] == w
                and (panel == "POOLED" or p["cls2"] == panel)]

    counts = {p: {b: [] for b in C.BAND_ORDER} for p in PANELS}
    rate = {p: [] for p in PANELS}
    for panel in PANELS:
        for w in windows:
            sub = subset(panel, w)
            c = Counter(p["verdict"] for p in sub)
            total = sum(c[b] for b in C.BAND_ORDER)
            if total != n_of[panel]:
                raise SystemExit(f"ASSERT FAIL: {panel} window={w} counts sum to "
                                 f"{total}, expected {n_of[panel]}")
            for b in C.BAND_ORDER:
                counts[panel][b].append(c[b])
            rate[panel].append(100.0 * c["success"] / n_of[panel])

    best = {}
    for panel in PANELS:
        i = max(range(len(windows)), key=lambda k: rate[panel][k])
        sub = subset(panel, windows[i])
        both = sum(1 for p in sub if p["answered"]
                   and p["in_time"] is not True and p["accurate"] is not True)
        best[panel] = dict(window=windows[i], rate=rate[panel][i],
                           n_success=counts[panel]["success"][i],
                           n_late=counts[panel]["late"][i],
                           n_wrong=counts[panel]["wrong"][i],
                           n_no_response=counts[panel]["no_response"][i],
                           late_and_wrong=both)
    return per_rows, n_of, counts, rate, best


def render(windows, n_of, counts, best, accurate_mm, fig_path):
    fig, axes = plt.subplots(3, 1, figsize=(11.5, 11.0), sharex=True)
    fig.patch.set_facecolor(C.SURF)
    x = list(range(len(windows)))
    for ax, panel in zip(axes, PANELS):
        C.style_axes(ax, grid_axis="y")
        bottom = [0] * len(windows)
        for b in C.BAND_ORDER:
            vals = counts[panel][b]
            ax.bar(x, vals, bottom=bottom, color=C.BAND_COLOR[b], width=0.78,
                   edgecolor=C.SURF, linewidth=1.0, zorder=3,
                   label=b if panel == PANELS[0] else None)
            bottom = [a + v for a, v in zip(bottom, vals)]
        bi = windows.index(best[panel]["window"])
        ax.axvline(bi, color=C.INK2, ls=":", lw=1.3, zorder=4)
        ax.annotate(f"best window = {best[panel]['window']} ms   "
                    f"success {best[panel]['rate']:.1f}%",
                    xy=(bi, n_of[panel]), xytext=(bi + 0.5, n_of[panel] * 1.045),
                    color=C.INK, fontsize=9, ha="left", va="bottom", zorder=5)
        ax.set_ylabel("flights", color=C.INK, fontsize=10)
        ax.set_title(f"{panel}  (n={n_of[panel]})", color=C.INK, fontsize=11,
                     loc="left", pad=6)
        ax.set_ylim(0, n_of[panel] * 1.14)
    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels([str(w) for w in windows], rotation=90, fontsize=8)
    axes[-1].set_xlabel(C.X_LABEL, color=C.INK, fontsize=10.5)

    handles, _ = axes[0].get_legend_handles_labels()
    fig.legend(handles, C.BAND_ORDER, frameon=False, fontsize=9.5, labelcolor=C.INK2,
               loc="upper center", bbox_to_anchor=(0.5, 0.975), ncol=4)
    fig.suptitle(f"Per-flight outcome across the observation-window sweep, two-class "
                 f"scheme (accuracy threshold {accurate_mm:.0f} mm)",
                 color=C.INK, fontsize=13, x=0.012, ha="left", y=0.995)

    caption = [
        "POOLED is the performance of a system with no regime classifier. SHORT and LONG are the achievable performance if the class were known at prediction time.",
        f"Verdict precedence, first match wins: not answered -> no_response; not in_time -> late; not accurate -> wrong; otherwise success.  in_time = t_obs + latency <= launch_to_crossing + {C.TARGET_SLACK_MS:.0f} ms,",
        f"t_obs = min(observation window, duration).  accurate = position error < {accurate_mm:.0f} mm, which is CONVERGENCE against the full-arc Model-C fit, NOT ground truth.  fit_failed rows are retained as",
        "no_response; the denominator is always the panel n.",
    ]
    for i, line in enumerate(caption):
        fig.text(0.012, 0.030 - i * 0.0088, line, color=C.INK2, fontsize=7.4)

    fig.tight_layout(rect=[0, 0.038, 1, 0.955])
    fig.savefig(fig_path, dpi=150, facecolor=C.SURF)
    plt.close(fig)


def run(rows, windows, accurate_mm, suffix):
    per_rows, n_of, counts, rate, best = evaluate(rows, windows, accurate_mm)
    print(f"[{accurate_mm:.0f} mm] ASSERT counts sum to panel n at every window: PASS "
          f"({len(PANELS)}x{len(windows)} = {len(PANELS)*len(windows)} cells)")

    with open(C.OUT_DIR + f"outcome_sweep_per_flight{suffix}.csv", "w",
              newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(per_rows[0].keys()))
        w.writeheader()
        w.writerows(per_rows)
    with open(C.OUT_DIR + f"outcome_sweep_by_class_T{suffix}.csv", "w",
              newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["class", "T", "n_success", "n_late", "n_wrong", "n_no_response",
                    "success_rate"])
        for panel in PANELS:
            for i, win in enumerate(windows):
                w.writerow([panel, win, counts[panel]["success"][i],
                            counts[panel]["late"][i], counts[panel]["wrong"][i],
                            counts[panel]["no_response"][i], f"{rate[panel][i]:.4f}"])

    fig_path = C.OUT_DIR + f"figureD_outcome_sweep{suffix}.png"
    render(windows, n_of, counts, best, accurate_mm, fig_path)
    for panel in PANELS:
        b = best[panel]
        print(f"  {panel:7s} best window={b['window']:5d} ms  success {b['rate']:5.1f}% "
              f"({b['n_success']}/{n_of[panel]})  late={b['n_late']} wrong={b['n_wrong']} "
              f"no_response={b['n_no_response']}  late&wrong={b['late_and_wrong']}")
    print(f"  wrote {fig_path}")
    return n_of, best


def main():
    rows = C.load_join()
    windows = C.windows_of(rows)
    print(f"sensitivity threshold check: sqrt(200^2 - {LABEL_FLOOR_MM:.0f}^2) = "
          f"{math.sqrt(200.0**2 - LABEL_FLOOR_MM**2):.1f} mm  -> using "
          f"{ACCURATE_MM_SENS:.0f} mm")
    n_of, best_main = run(rows, windows, ACCURATE_MM_MAIN, "")
    _, best_sens = run(rows, windows, ACCURATE_MM_SENS, "_170mm")

    print()
    print("COMPARISON: 200 mm vs 170 mm accuracy threshold")
    print(f"{'panel':8s} {'n':>4} | {'best win 200':>12} {'succ 200':>9} | "
          f"{'best win 170':>12} {'succ 170':>9} | {'delta pp':>9}")
    for panel in PANELS:
        a, b = best_main[panel], best_sens[panel]
        print(f"{panel:8s} {n_of[panel]:>4} | {a['window']:>10d} ms {a['rate']:>8.1f}% | "
              f"{b['window']:>10d} ms {b['rate']:>8.1f}% | {b['rate'] - a['rate']:>+8.1f}")


if __name__ == "__main__":
    main()
