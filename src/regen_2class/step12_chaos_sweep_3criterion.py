"""Step 12 - Figure H: chaos-rally sweep with the position criterion REMOVED.

WHY wrong_position is gone as a pass criterion
----------------------------------------------
Figure F used a four-criterion verdict including wrong_position at 100 mm, derived
as a dead-band containment margin around the aperture perimeter. It duplicates the
hit/miss test and is removed here.

The impulse axis translates the panel along its surface normal at uniform velocity.
Return DIRECTION is therefore set by the commanded panel angle, and return SPEED by
the translation velocity. Neither depends on where on the surface the ball makes
contact. Crossing position governs only WHETHER contact occurs, and hit_miss_match
already tests exactly that. Keeping both counted the same physical requirement
twice.

Position accuracy is still reported, but as a CAPABILITY (median / p90 / max
position_error_mm at the operating point), not as a pass/fail criterion.

VERDICT, precedence first-match-wins
    no_response     status != "ok"
    late            t_obs + latency_ms > launch_to_crossing_ms - A
    wrong_class     hit_miss_match is False
    wrong_velocity  any axis error > VELOCITY_TOL_MM_S
    success         all pass
t_obs = min(observation window, duration_ms). Note the MINUS in the timing test:
chaos rally needs the answer A ms BEFORE arrival, opposite to target mode's +84 ms.

Writes NEW files only. Figures A, D, E, F and G are not touched, and
APERTURE_SIZE_MM is not read or changed anywhere in this module.

    results/regenerate_figures/figure_h_chaos_3criterion.png
    results/regenerate_figures/figure_h_chaos_3criterion.csv
"""
import csv
import math
import statistics as st
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common as C
from step10_chaos_outcome_sweep import (
    A_VALUES, AXIS_TITLE, POSITION_THRESHOLD_MM, VELOCITY_TOL_MM_S,
    evaluate as evaluate_four, flags, load_per_axis,
)

FIG = C.OUT_DIR + "figure_h_chaos_3criterion.png"
OUT_CSV = C.OUT_DIR + "figure_h_chaos_3criterion.csv"

# Three real criteria plus the no-answer case. wrong_position is absent.
FAILURES_H = ["no_response", "late", "wrong_class", "wrong_velocity"]
# Same flags, but with containment reinstated at the END rather than before
# velocity - used for the sensitivity print only.
FAILURES_TAIL = FAILURES_H + ["wrong_position"]
ALL_CRITERIA = ["no_response", "late", "wrong_class", "wrong_velocity",
                "wrong_position"]

# bottom -> top, success on the floor as in Figure D
BAND_ORDER_H = ["success", "wrong_velocity", "wrong_class", "late", "no_response"]
BAND_COLOR_H = {
    "success": "#1baf7a",
    "wrong_velocity": "#e87ba4",
    "wrong_class": "#2a78d6",
    "late": "#4a3aa7",
    "no_response": "#e34948",
}


def verdict_with(order, f):
    """First-match-wins over an explicit precedence order."""
    for name in order:
        if f[name]:
            return name
    return "success"


def evaluate_h(rows, per_axis, windows, A, order, bands):
    """-> per_rows, n_of, counts[class][band][i], rate[class][i], best[class]"""
    per_rows = []
    for r in rows:
        f = flags(r, per_axis, A, POSITION_THRESHOLD_MM)
        per_rows.append({"session": r["session"], "flight": r["flight"],
                         "cls2": r["cls2"], "T_ms": int(r["T_ms"]),
                         "status": r["status"],
                         **{f"f_{k}": v for k, v in f.items()},
                         "verdict": verdict_with(order, f)})
    n_of = {c: len({(p["session"], p["flight"]) for p in per_rows if p["cls2"] == c})
            for c in C.CLASSES}
    counts = {c: {b: [] for b in bands} for c in C.CLASSES}
    rate = {c: [] for c in C.CLASSES}
    for c in C.CLASSES:
        for w in windows:
            sub = [p for p in per_rows if p["cls2"] == c and p["T_ms"] == w]
            k = Counter(p["verdict"] for p in sub)
            total = sum(k[b] for b in bands)
            if total != n_of[c]:
                raise SystemExit(f"ASSERT FAIL: {c} A={A} window={w} bands sum to "
                                 f"{total}, expected {n_of[c]}")
            for b in bands:
                counts[c][b].append(k[b])
            rate[c].append(100.0 * k["success"] / n_of[c])
    best = {}
    for c in C.CLASSES:
        # Step 1: the maximum success rate. Reliability is the pass criterion and
        # decides on its own - position error must NOT enter this step.
        mx = max(rate[c])
        # Step 2: among windows achieving exactly that maximum, take the LATEST.
        # Success is at ceiling across the whole plateau, so a longer window cannot
        # raise the success count but does keep reducing crossing position error.
        # Taking the earliest tied window left that accuracy unclaimed AND put the
        # operating point where position capability was worst - which biased the
        # capability figures, since the window had been chosen by an argument that
        # assumed position did not matter.
        plateau = [j for j, v in enumerate(rate[c]) if v == mx]
        i = plateau[-1]
        best[c] = dict(window=windows[i], rate=rate[c][i], idx=i,
                       feasible=rate[c][i] > 0.0,
                       plateau_idx=plateau,
                       plateau_windows=[windows[j] for j in plateau])
    return per_rows, n_of, counts, rate, best


def position_stats(rows, cls, window):
    """median / p90 / max position_error_mm and n_ok at one (class, window).
    Reported as a CAPABILITY only - never used to choose the operating window."""
    v = [float(r["position_error_mm"]) for r in rows
         if r["cls2"] == cls and int(r["T_ms"]) == window and r["status"] == "ok"]
    if not v:
        return None
    return dict(pos_median=st.median(v), pos_p90=C.percentile(v, 0.90),
                pos_max=max(v), n_ok=len(v))


def capability_at(rows, per_axis, cls, window, n_total):
    """Position accuracy as a CAPABILITY, plus class agreement and per-axis velocity."""
    sub = [r for r in rows if r["cls2"] == cls and int(r["T_ms"]) == window]
    ok = [r for r in sub if r["status"] == "ok"]
    pos = [float(r["position_error_mm"]) for r in ok]
    agree = sum(1 for r in ok if r["hit_miss_match"] == "True")
    errs = [per_axis[(r["session"], r["flight"], window)] for r in ok]
    out = dict(n_total=n_total, n_ok=len(ok), n_fit_failed=len(sub) - len(ok),
               pos_median=st.median(pos) if pos else None,
               pos_p90=C.percentile(pos, 0.90) if pos else None,
               pos_max=max(pos) if pos else None,
               hit_miss_rate=(100.0 * agree / len(ok)) if ok else None)
    for j, ax in enumerate(("x", "y", "z")):
        vals = [e[j] for e in errs]
        out[f"bias_{ax}"] = st.mean(vals) if vals else None
        out[f"rms_{ax}"] = math.sqrt(sum(v * v for v in vals) / len(vals)) if vals else None
    return out


def independent_flags(per_rows, cls, window):
    """How often each requirement fails ON ITS OWN, ignoring precedence. The bands
    answer 'what failed first'; this answers 'how often does each test fail'."""
    sub = [p for p in per_rows if p["cls2"] == cls and p["T_ms"] == window]
    out = {}
    for name in ALL_CRITERIA:
        out[name] = sum(1 for p in sub if p[f"f_{name}"] is True)
        out[f"{name}_evaluable"] = sum(1 for p in sub if p[f"f_{name}"] is not None)
    return out


def render(windows, results, max_ltc, n_of):
    fig, axes = plt.subplots(3, 2, figsize=(15.0, 12.5), sharex=True)
    for row_i, A in enumerate(A_VALUES):
        for col_i, cls in enumerate(C.CLASSES):
            ax = axes[row_i][col_i]
            C.style_axes(ax, grid_axis="y")
            counts, best = results[A]["counts"][cls], results[A]["best"][cls]
            keep = [i for i, w in enumerate(windows) if w <= max_ltc[cls]]
            xs = list(range(len(keep)))
            bottom = [0] * len(keep)
            for b in BAND_ORDER_H:
                vals = [counts[b][i] for i in keep]
                ax.bar(xs, vals, bottom=bottom, color=BAND_COLOR_H[b], width=0.8,
                       edgecolor=C.SURF, linewidth=0.8, zorder=3,
                       label=b if (row_i == 0 and col_i == 0) else None)
                bottom = [p + q for p, q in zip(bottom, vals)]
            extra = ""
            if best["feasible"] and best["idx"] in keep:
                bi = keep.index(best["idx"])
                ax.axvline(bi, color=C.INK2, ls=":", lw=1.3, zorder=4)
                ax.annotate(f"best {best['window']} ms   {best['rate']:.1f}%",
                            xy=(bi, n_of[cls]), xytext=(bi + 0.5, n_of[cls] * 1.04),
                            color=C.INK, fontsize=8.5, ha="left", va="bottom", zorder=5)
            else:
                extra = "   INFEASIBLE"
            ax.set_ylim(0, n_of[cls] * 1.16)
            ax.set_title(f"{cls}  (n={n_of[cls]})   A = {A:.0f} ms{extra}",
                         color=C.INK, fontsize=10.5, loc="left", pad=5)
            if col_i == 0:
                ax.set_ylabel("flights", color=C.INK, fontsize=9.5)
            ax.set_xticks(xs)
            ax.set_xticklabels([str(windows[i]) for i in keep], rotation=90, fontsize=7)
    for col_i in range(2):
        axes[-1][col_i].set_xlabel(C.X_LABEL, color=C.INK, fontsize=10)
    fig.patch.set_facecolor(C.SURF)
    handles, _ = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, BAND_ORDER_H, frameon=False, fontsize=9.5, labelcolor=C.INK2,
               loc="upper center", bbox_to_anchor=(0.5, 0.975), ncol=5)
    fig.suptitle("Chaos-rally outcome sweep, THREE-criterion verdict "
                 "(position removed as a pass criterion)",
                 color=C.INK, fontsize=13.5, x=0.008, ha="left", y=0.995)
    caption = [
        "Position is NOT a pass criterion here. The impulse axis translates the panel along its surface normal at uniform velocity, so return direction is set by the commanded panel angle and return",
        "speed by the translation velocity - neither depends on where on the surface contact occurs. Crossing position governs only WHETHER contact occurs, which hit_miss_match already tests. Figure F's",
        "wrong_position band counted that same requirement a second time. Position accuracy is reported as a capability in the companion CSV, not as pass/fail.",
        "Chaos rally requires the answer A ms BEFORE arrival: late is t_obs + latency > launch_to_crossing - A. Target mode's test allowed +84 ms AFTER arrival; the sign is opposite and deliberate.",
        f"Verdict precedence first-match-wins: no_response, late, wrong_class, wrong_velocity, success. Bands stack bottom to top as success, wrong_velocity, wrong_class, late, no_response, matching Figure D.",
        "Where several observation windows achieve the maximum success rate, the latest is selected: reliability is at ceiling across the plateau, so a longer window reduces crossing position error at no cost to success.",
        f"Velocity tolerance is isotropic placement: {VELOCITY_TOL_MM_S:.0f} mm/s on all three world axes, from 1.0 m / (0.68 x 1.0 s). Velocity errors are CONVERGENCE against the full-arc Model-C fit, NOT ground truth.",
        "fit_failed rows are retained as no_response; the denominator is always the class n. Each class is truncated at its own maximum launch-to-crossing time. A = 72 / 135 / 220 ms are panel tilt moves of 2, 10 and 30 degrees.",
    ]
    for i, line in enumerate(caption):
        fig.text(0.006, 0.058 - i * 0.0078, line, color=C.INK2, fontsize=6.8)
    fig.tight_layout(rect=[0, 0.072, 1, 0.955])
    fig.savefig(FIG, dpi=150, facecolor=C.SURF)
    plt.close(fig)
    print(f"wrote {FIG}")


def main():
    rows = C.load_join()
    windows = C.windows_of(rows)
    per_axis = load_per_axis()
    durations = C.class_durations(rows)
    max_ltc = {c: max(v) for c, v in durations.items()}
    n_class = {c: len(v) for c, v in durations.items()}
    print(f"classes recomputed from bin: SHORT={n_class['SHORT']}, LONG={n_class['LONG']}")
    assert n_class["SHORT"] == 47 and n_class["LONG"] == 60
    print(f"velocity tolerance {VELOCITY_TOL_MM_S:.1f} mm/s isotropic; "
          f"position is NOT a pass criterion")
    print(f"truncation at class max launch_to_crossing_ms: "
          f"{ {c: round(v, 1) for c, v in max_ltc.items()} }")
    print()

    results, results_four, results_tail = {}, {}, {}
    for A in A_VALUES:
        pr, n_of, counts, rate, best = evaluate_h(rows, per_axis, windows, A,
                                                  FAILURES_H, BAND_ORDER_H)
        results[A] = dict(per_rows=pr, counts=counts, rate=rate, best=best)
        print(f"[A={A:.0f}] ASSERT bands sum to class n at every window: PASS "
              f"({len(C.CLASSES) * len(windows)} cells)")
        # Figure F's four-criterion result, for the comparison table
        _, _, _, rate4, best4 = evaluate_four(rows, per_axis, windows, A,
                                              POSITION_THRESHOLD_MM)
        results_four[A] = dict(rate=rate4, best=best4)
        # containment reinstated at the END of the chain, for the sensitivity print
        pr_t, _, counts_t, rate_t, best_t = evaluate_h(
            rows, per_axis, windows, A, FAILURES_TAIL,
            BAND_ORDER_H + ["wrong_position"])
        results_tail[A] = dict(per_rows=pr_t, counts=counts_t, rate=rate_t, best=best_t)

    out_rows, plateau_rows = [], []
    print()
    for A in A_VALUES:
        rate_h = results[A]["rate"]
        for cls in C.CLASSES:
            best = results[A]["best"][cls]
            if not best["feasible"]:
                print(f"INFEASIBLE: {cls} at A={A:.0f} ms")
                out_rows.append(dict(cls=cls, A=A, window="INFEASIBLE"))
                continue
            w, i = best["window"], best["idx"]
            band = {b: results[A]["counts"][cls][b][i] for b in BAND_ORDER_H}
            cap = capability_at(rows, per_axis, cls, w, n_class[cls])
            ind = independent_flags(results[A]["per_rows"], cls, w)
            print(f"--- {cls}  A={A:.0f} ms   best window {w} ms   success "
                  f"{best['rate']:.1f}%  ({band['success']}/{n_class[cls]})")
            print(f"      bands: " + "  ".join(f"{b}={band[b]}" for b in BAND_ORDER_H))
            print(f"      position CAPABILITY (not a criterion): median "
                  f"{cap['pos_median']:.1f}, p90 {cap['pos_p90']:.1f}, max "
                  f"{cap['pos_max']:.1f} mm")
            print(f"      hit/miss agreement {cap['hit_miss_rate']:.1f}% over "
                  f"{cap['n_ok']} fitted rows; n_fit_failed={cap['n_fit_failed']}")
            for ax in ("x", "y", "z"):
                print(f"      vel {AXIS_TITLE[ax]:<18s} bias {cap['bias_'+ax]:+8.1f} "
                      f"rms {cap['rms_'+ax]:8.1f} mm/s")
            print(f"      INDEPENDENT flag counts (ignoring precedence, "
                  f"'how often does each requirement fail'):")
            for name in ALL_CRITERIA:
                mark = "  [not a criterion here]" if name == "wrong_position" else ""
                print(f"          {name:<15s} {ind[name]:>3d} of "
                      f"{ind[name+'_evaluable']:>3d} evaluable{mark}")
            # --- plateau: every window achieving the SAME maximum success rate ---
            pw = best["plateau_windows"]
            contiguous = all(b - a == 1 for a, b in zip(best["plateau_idx"],
                                                        best["plateau_idx"][1:]))
            if w > max_ltc[cls]:
                print(f"      *** WARNING: selected window {w} ms exceeds {cls} max "
                      f"launch_to_crossing {max_ltc[cls]:.1f} ms - it is outside the "
                      f"plotted range ***")
            print(f"      PLATEAU (windows at the maximum success rate "
                  f"{best['rate']:.1f}%): {pw}"
                  f"   {'contiguous' if contiguous else '*** NOT CONTIGUOUS ***'}")
            print(f"          {'window':>7} {'success':>8} {'n_ok':>5} "
                  f"{'pos med':>9} {'pos p90':>9} {'pos max':>9}")
            for j in best["plateau_idx"]:
                pwin = windows[j]
                ps = position_stats(rows, cls, pwin)
                sel = "  <- SELECTED (latest)" if j == best["idx"] else ""
                if ps:
                    print(f"          {pwin:>7d} {rate_h[cls][j]:>7.1f}% "
                          f"{ps['n_ok']:>5d} {ps['pos_median']:>9.1f} "
                          f"{ps['pos_p90']:>9.1f} {ps['pos_max']:>9.1f}{sel}")
                else:
                    print(f"          {pwin:>7d} {rate_h[cls][j]:>7.1f}% "
                          f"{0:>5d} {'-':>9} {'-':>9} {'-':>9}{sel}")
                plateau_rows.append(dict(
                    cls=cls, A=A, plateau_window=pwin,
                    is_selected=(j == best["idx"]), plateau_size=len(pw),
                    plateau_contiguous=contiguous, success_rate=rate_h[cls][j],
                    **(ps or dict(pos_median="", pos_p90="", pos_max="", n_ok=0))))
            if len(pw) > 1:
                first, last = position_stats(rows, cls, pw[0]), position_stats(rows, cls, w)
                if first and last:
                    print(f"          earliest {pw[0]} ms -> selected {w} ms: "
                          f"pos median {first['pos_median']:.1f} -> {last['pos_median']:.1f} "
                          f"({last['pos_median']-first['pos_median']:+.1f}), "
                          f"p90 {first['pos_p90']:.1f} -> {last['pos_p90']:.1f} "
                          f"({last['pos_p90']-first['pos_p90']:+.1f}), "
                          f"max {first['pos_max']:.1f} -> {last['pos_max']:.1f} "
                          f"({last['pos_max']-first['pos_max']:+.1f}), "
                          f"n_ok {first['n_ok']} -> {last['n_ok']}")

            out_rows.append(dict(cls=cls, A=A, window=w, success_rate_h=best["rate"],
                                 plateau_windows=";".join(str(x) for x in pw),
                                 plateau_size=len(pw),
                                 **band, **cap,
                                 **{f"ind_{k}": v for k, v in ind.items()}))

    print()
    print("=== COMPARISON: Figure F four-criterion vs Figure H three-criterion ===")
    hdr = (f"{'class':6s} {'A':>5} | {'F window':>9} {'F success':>10} | "
           f"{'H window':>9} {'H success':>10} | {'delta pp':>9}")
    print(hdr)
    print("-" * len(hdr))
    for A in A_VALUES:
        for cls in C.CLASSES:
            b4, bh = results_four[A]["best"][cls], results[A]["best"][cls]
            print(f"{cls:6s} {A:>5.0f} | {b4['window']:>7d}ms {b4['rate']:>9.1f}% | "
                  f"{bh['window']:>7d}ms {bh['rate']:>9.1f}% | "
                  f"{bh['rate'] - b4['rate']:>+8.1f}")
            for r in out_rows:
                if r.get("cls") == cls and r.get("A") == A and r.get("window") != "INFEASIBLE":
                    r["success_rate_f"] = b4["rate"]
                    r["window_f"] = b4["window"]
                    r["delta_pp"] = bh["rate"] - b4["rate"]

    print()
    print("=== SENSITIVITY: wrong_position (100 mm) reinstated at the END of the "
          "precedence chain ===")
    print("    'how many flights fail position alone once everything else has "
          "passed' - the true containment cost, undistorted by ordering")
    hdr2 = (f"{'class':6s} {'A':>5} | {'window':>8} | {'success':>8} "
            f"{'fail pos only':>14} | {'success if pos kept':>20}")
    print(hdr2)
    print("-" * len(hdr2))
    for A in A_VALUES:
        for cls in C.CLASSES:
            bh = results[A]["best"][cls]
            i = bh["idx"]
            n_pos_only = results_tail[A]["counts"][cls]["wrong_position"][i]
            succ_tail = results_tail[A]["counts"][cls]["success"][i]
            print(f"{cls:6s} {A:>5.0f} | {bh['window']:>6d}ms | "
                  f"{bh['rate']:>7.1f}% {n_pos_only:>14d} | "
                  f"{100.0*succ_tail/n_class[cls]:>19.1f}%")
            for r in out_rows:
                if r.get("cls") == cls and r.get("A") == A and r.get("window") != "INFEASIBLE":
                    r["fail_position_only"] = n_pos_only
                    r["success_rate_if_position_kept"] = 100.0 * succ_tail / n_class[cls]

    # Long format: one row per (class, A, plateau window). The per-window position
    # capability varies across the plateau, which is the whole point of reporting
    # it, so those columns come from the plateau row; the (class, A)-level summary
    # is repeated alongside so each row stands alone.
    PER_WINDOW = {"pos_median", "pos_p90", "pos_max", "n_ok"}
    summary_by = {(r["cls"], r["A"]): r for r in out_rows if r.get("window") != "INFEASIBLE"}
    cols = (["cls", "A", "plateau_window", "is_selected", "plateau_size",
             "plateau_contiguous", "success_rate", "n_ok", "pos_median", "pos_p90",
             "pos_max", "selected_window", "success_rate_h", "window_f",
             "success_rate_f", "delta_pp"] + BAND_ORDER_H +
            ["n_total", "n_fit_failed", "hit_miss_rate"] +
            [f"{p}_{a}" for a in ("x", "y", "z") for p in ("bias", "rms")] +
            [f"ind_{n}" for n in ALL_CRITERIA] +
            ["fail_position_only", "success_rate_if_position_kept"])
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for pr in plateau_rows:
            summ = {k: v for k, v in summary_by.get((pr["cls"], pr["A"]), {}).items()
                    if k not in PER_WINDOW}
            summ["selected_window"] = summ.pop("window", "")
            row = {**summ, **pr}
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v)
                        for k, v in row.items()})
    print(f"\nwrote {OUT_CSV}  ({len(plateau_rows)} rows, one per plateau window)")

    render(windows, results, max_ltc, n_class)


if __name__ == "__main__":
    main()
