"""Step 13 (landing-error variant) - chaos-rally sweep on a COMBINED criterion.

A re-read of frozen data at new thresholds. No new experiments, no re-fitting, no
model change. Every input is read read-only.

WHY COMBINED RATHER THAN TWO SEPARATE TOLERANCES
------------------------------------------------
The three-criterion version removed position, arguing a rigid panel in pure
translation returns the ball independently of contact location. True of outgoing
VELOCITY - v_out = e*v_in + (1+e)*u carries no rotation term - but not of outgoing
POSITION: the ball departs from wherever it was struck, so a crossing-position error
translates the whole return trajectory by the same amount.

Position error and velocity error displace the SAME landing point in the SAME frame,
so the requirement is about their SUM. Testing them separately forces an arbitrary
allocation between the two terms that no physics justifies, and produces false
failures where one term is large and the other small. Both come from the same
Model-C fit on the same detected points, so they are correlated in source and add
LINEARLY; quadrature would assume an independence that does not hold.

    landing_error_mm = |dp| + e * |dv| * t
                       [mm] + [-]*[mm/s]*[s] = [mm] + [mm] = [mm]

|dp| is `position_error_mm`. That column is hypot(dY, dZ) - two components - but it
IS the full 3D magnitude, because both the predicted and reference crossing points
lie ON the plane by construction, so the depth component of their displacement is
identically zero.

|dv| is sqrt(err_vx^2 + err_vy^2 + err_vz^2), cross-checked against the stored
scalar velocity_error_mm_s on every row.

Two thresholds are run as full figures. Neither is labelled "the requirement".
"""
import csv
import math
import os
import statistics as st
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import clean_figures as CF
import common as C
from step10_chaos_outcome_sweep import load_per_axis

OUT_DIR = "results/regenerate_figures/02_chaos_landing_error/"

E_COR = 0.68              # published volleyball-on-rigid-surface COR
T_RETURN_S = 1.0
A_VALUES = [72.0, 135.0, 220.0]

# threshold -> (tag, anchor phrase for the caption)
RUNS = [
    (500.0, "500mm", "arm's reach, stationary player"),
    (1000.0, "1000mm", "step plus reach over a 1 s return"),
]
Y_WIDTH_LABEL_SD = 282.0  # decision 77, weak-axis reference noise floor

# three-criterion baseline, for the regression gate and the comparison table
VEL_TOL_THREE_CRITERION = 1000.0 / (E_COR * T_RETURN_S)   # 1470.6 mm/s
THREE_CRITERION_EXPECTED = {
    ("SHORT", 72.0): 93.6, ("SHORT", 135.0): 93.6, ("SHORT", 220.0): 74.5,
    ("LONG", 72.0): 98.3, ("LONG", 135.0): 98.3, ("LONG", 220.0): 98.3,
}

FAILURES_COMBINED = ["no_response", "late", "wrong_class", "wrong_placement"]
FAILURES_THREE = ["no_response", "late", "wrong_class", "wrong_velocity"]
BAND_ORDER = ["success", "wrong_placement", "wrong_class", "late", "no_response"]
BAND_ORDER_THREE = ["success", "wrong_velocity", "wrong_class", "late", "no_response"]
BAND_COLOR = {
    "success": "#1baf7a", "wrong_placement": "#eda100", "wrong_class": "#2a78d6",
    "late": "#4a3aa7", "no_response": "#e34948",
}


def stop(msg):
    raise SystemExit(f"\n*** STOP GATE FAILED ***\n{msg}\n")


def terms_of(row, per_axis):
    """(|dp| mm, e*|dv|*t mm, |dv| mm/s) for a fitted row."""
    dp = float(row["position_error_mm"])
    ex, ey, ez = per_axis[(row["session"], row["flight"], int(row["T_ms"]))]
    dv = math.sqrt(ex * ex + ey * ey + ez * ez)
    return dp, E_COR * dv * T_RETURN_S, dv


def flags_of(row, per_axis, A, threshold):
    if row["status"] != "ok":
        return dict(no_response=True, late=None, wrong_class=None,
                    wrong_placement=None, wrong_velocity=None), None
    t_obs = min(float(row["T_ms"]), float(row["duration_ms"]))
    dp, vterm, dv = terms_of(row, per_axis)
    landing = dp + vterm
    return dict(
        no_response=False,
        late=(t_obs + float(row["latency_ms"])) > (float(row["launch_to_crossing_ms"]) - A),
        wrong_class=(row["hit_miss_match"] != "True"),
        wrong_placement=landing > threshold,
        wrong_velocity=dv > VEL_TOL_THREE_CRITERION,
    ), dict(dp=dp, vterm=vterm, dv=dv, landing=landing)


def evaluate(rows, per_axis, windows, A, threshold, order, bands, n_class):
    per_rows = []
    for r in rows:
        f, m = flags_of(r, per_axis, A, threshold)
        verdict = "success"
        for name in order:
            if f[name]:
                verdict = name
                break
        per_rows.append({"session": r["session"], "flight": r["flight"],
                         "cls2": r["cls2"], "T_ms": int(r["T_ms"]),
                         **{f"f_{k}": v for k, v in f.items()},
                         **(m or {}), "verdict": verdict})
    counts = {c: {b: [] for b in bands} for c in C.CLASSES}
    rate = {c: [] for c in C.CLASSES}
    for c in C.CLASSES:
        for w in windows:
            k = Counter(p["verdict"] for p in per_rows
                        if p["cls2"] == c and p["T_ms"] == w)
            total = sum(k[b] for b in bands)
            if total != n_class[c]:
                stop(f"band counts do not sum to class n: {c} A={A:.0f} window={w} "
                     f"-> {total}, expected {n_class[c]}")
            for b in bands:
                counts[c][b].append(k[b])
            rate[c].append(100.0 * k["success"] / n_class[c])
    best = {}
    for c in C.CLASSES:
        mx = max(rate[c])                   # step 1: reliability alone decides
        plateau = [j for j, v in enumerate(rate[c]) if v == mx]
        i = plateau[-1]                     # step 2: latest of the tied windows
        best[c] = dict(window=windows[i], rate=mx, idx=i,
                       plateau_windows=[windows[j] for j in plateau])
    return per_rows, counts, rate, best


def landing_stats(per_rows, cls, window):
    sub = [p for p in per_rows if p["cls2"] == cls and p["T_ms"] == window
           and p["f_no_response"] is False]
    if not sub:
        return {}
    le = [p["landing"] for p in sub]
    return dict(n_ok=len(sub),
                landing_median=st.median(le), landing_p90=C.percentile(le, 0.90),
                landing_max=max(le),
                dp_median=st.median([p["dp"] for p in sub]),
                vterm_median=st.median([p["vterm"] for p in sub]),
                dv_median=st.median([p["dv"] for p in sub]))


def independent_flags(per_rows, cls, window):
    sub = [p for p in per_rows if p["cls2"] == cls and p["T_ms"] == window]
    out = {}
    for name in FAILURES_COMBINED:
        out[f"ind_{name}"] = sum(1 for p in sub if p[f"f_{name}"] is True)
        out[f"ind_{name}_evaluable"] = sum(1 for p in sub if p[f"f_{name}"] is not None)
    return out


def render(windows, results, max_ltc, n_class, threshold, anchor, path):
    fig, axes = plt.subplots(3, 2, figsize=(15.0, 12.5), sharex=True)
    fig.patch.set_facecolor(C.SURF)
    for row_i, A in enumerate(A_VALUES):
        for col_i, cls in enumerate(C.CLASSES):
            ax = axes[row_i][col_i]
            C.style_axes(ax, grid_axis="y")
            counts, best = results[A]["counts"][cls], results[A]["best"][cls]
            keep = [i for i, w in enumerate(windows) if w <= max_ltc[cls]]
            xs = list(range(len(keep)))
            bottom = [0] * len(keep)
            for b in BAND_ORDER:
                vals = [counts[b][i] for i in keep]
                ax.bar(xs, vals, bottom=bottom, color=BAND_COLOR[b], width=0.8,
                       edgecolor=C.SURF, linewidth=0.8, zorder=3,
                       label=b if (row_i == 0 and col_i == 0) else None)
                bottom = [p + q for p, q in zip(bottom, vals)]
            if best["idx"] in keep:
                bi = keep.index(best["idx"])
                ax.axvline(bi, color=C.INK2, ls=":", lw=1.3, zorder=4)
                ax.annotate(f"best {best['window']} ms   {best['rate']:.1f}%",
                            xy=(bi, n_class[cls]),
                            xytext=(bi + 0.5, n_class[cls] * 1.04),
                            color=C.INK, fontsize=8.5, ha="left", va="bottom", zorder=5)
            ax.set_ylim(0, n_class[cls] * 1.16)
            ax.set_title(f"{cls}  (n={n_class[cls]})   A = {A:.0f} ms",
                         color=C.INK, fontsize=10.5, loc="left", pad=5)
            if col_i == 0:
                ax.set_ylabel("flights", color=C.INK, fontsize=9.5)
            ax.set_xticks(xs)
            ax.set_xticklabels([str(windows[i]) for i in keep], rotation=90, fontsize=7)
    for col_i in range(2):
        axes[-1][col_i].set_xlabel(C.X_LABEL, color=C.INK, fontsize=10)
    handles, _ = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, BAND_ORDER, frameon=False, fontsize=9.5, labelcolor=C.INK2,
               loc="upper center", bbox_to_anchor=(0.5, 0.975), ncol=5)
    fig.suptitle(f"Chaos-rally outcome sweep, combined landing-error criterion "
                 f"<= {threshold:.0f} mm  ({anchor})",
                 color=C.INK, fontsize=13.5, x=0.008, ha="left", y=0.995)
    vel_equiv = threshold / (E_COR * T_RETURN_S)
    caption = [
        f"landing_error = |dp| + e*|dv|*t, e = {E_COR}, t = {T_RETURN_S:.1f} s. A total landing-error allowance at the player of {threshold:.0f} mm. Because the budget is not split between the two terms, a flight with small",
        f"position error may spend the whole allowance on velocity, corresponding to {vel_equiv:.0f} mm/s - {vel_equiv/Y_WIDTH_LABEL_SD:.1f}x the ~{Y_WIDTH_LABEL_SD:.0f} mm/s Y_width label SD, so the test remains above the reference noise floor on the",
        "weak axis. Position and velocity errors are CONVERGENCE against the full-arc Model-C fit, NOT accuracy against ground truth.",
        "|dp| is the crossing-position error magnitude; it is a two-component in-plane distance and that IS its 3D magnitude, because both the predicted and reference crossing points lie on the plane by construction.",
        "Chaos rally needs the answer A ms BEFORE arrival: late is t_obs + latency > launch_to_crossing - A, opposite in sign to target mode's +84 ms after. t_obs = min(observation window, duration).",
        "Verdict precedence first-match-wins: no_response, late, wrong_class, wrong_placement, success. Where several windows tie at the maximum success rate the LATEST is selected; landing error never influences that maximisation.",
        "fit_failed rows are retained as no_response; the denominator is always the class n. Each class is truncated at its own maximum launch-to-crossing time. A = 72/135/220 ms are panel tilt moves of 2, 10 and 30 degrees.",
    ]
    if CF.clean():
        CF.write_clean(fig, caption, path)
    else:
        gap, floor_y = 0.0072, 0.010
        start_y = floor_y + (len(caption) - 1) * gap
        for i, line in enumerate(caption):
            fig.text(0.006, start_y - i * gap, line, color=C.INK2, fontsize=6.6)
        fig.tight_layout(rect=[0, start_y + 0.018, 1, 0.955])
        fig.savefig(path, dpi=150, facecolor=C.SURF)
        print(f"  wrote {path}")
    plt.close(fig)


def run_threshold(rows, per_axis, windows, max_ltc, n_class, threshold, tag, anchor):
    print(f"\n=== RUN {tag}: landing_error <= {threshold:.0f} mm  ({anchor}) ===")
    results, band_rows, op_rows = {}, [], []
    for A in A_VALUES:
        pr, counts, rate, best = evaluate(rows, per_axis, windows, A, threshold,
                                          FAILURES_COMBINED, BAND_ORDER, n_class)
        results[A] = dict(per_rows=pr, counts=counts, rate=rate, best=best)
        print(f"  [A={A:.0f}] band sums OK at all {len(C.CLASSES)*len(windows)} cells")
        for cls in C.CLASSES:
            for i, w in enumerate(windows):
                band_rows.append(dict(threshold_mm=threshold, cls=cls, A=A, window=w,
                                      success_rate=rate[cls][i],
                                      **{b: counts[cls][b][i] for b in BAND_ORDER}))
    path = OUT_DIR + f"bands_by_class_A_window_{tag}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["threshold_mm", "cls", "A", "window",
                                          "success_rate"] + BAND_ORDER)
        w.writeheader()
        for r in band_rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})
    print(f"  wrote {path}  ({len(band_rows)} rows)")

    for A in A_VALUES:
        for cls in C.CLASSES:
            best = results[A]["best"][cls]
            w, i = best["window"], best["idx"]
            band = {b: results[A]["counts"][cls][b][i] for b in BAND_ORDER}
            ls = landing_stats(results[A]["per_rows"], cls, w)
            ind = independent_flags(results[A]["per_rows"], cls, w)
            op_rows.append(dict(threshold_mm=threshold, cls=cls, A=A,
                                selected_window=w, success_rate=best["rate"],
                                plateau_windows=";".join(str(x) for x in best["plateau_windows"]),
                                plateau_size=len(best["plateau_windows"]),
                                n_total=n_class[cls],
                                n_fit_failed=n_class[cls] - ls.get("n_ok", 0),
                                **band, **ls, **ind))
            print(f"\n  --- {cls}  A={A:.0f} ms   plateau {best['plateau_windows']} "
                  f"-> selected {w} ms   success {best['rate']:.1f}% "
                  f"({band['success']}/{n_class[cls]})")
            print(f"        bands: " + "  ".join(f"{b}={band[b]}" for b in BAND_ORDER))
            if ls:
                print(f"        landing_error: median {ls['landing_median']:.1f}, p90 "
                      f"{ls['landing_p90']:.1f}, max {ls['landing_max']:.1f} mm")
                print(f"        split at the median: |dp| {ls['dp_median']:.1f} mm  +  "
                      f"e*|dv|*t {ls['vterm_median']:.1f} mm   "
                      f"(|dv| median {ls['dv_median']:.1f} mm/s)")
            print(f"        INDEPENDENT flag counts (ignoring precedence):")
            for name in FAILURES_COMBINED:
                print(f"            {name:<16s} {ind['ind_'+name]:>3d} of "
                      f"{ind['ind_'+name+'_evaluable']:>3d} evaluable")
    path = OUT_DIR + f"operating_points_{tag}.csv"
    cols = (["threshold_mm", "cls", "A", "selected_window", "success_rate",
             "plateau_windows", "plateau_size", "n_total", "n_ok", "n_fit_failed"] +
            BAND_ORDER + ["landing_median", "landing_p90", "landing_max",
                          "dp_median", "vterm_median", "dv_median"] +
            [f"ind_{n}" for n in FAILURES_COMBINED] +
            [f"ind_{n}_evaluable" for n in FAILURES_COMBINED])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in op_rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})
    print(f"\n  wrote {path}")
    render(windows, results, max_ltc, n_class, threshold, anchor,
           OUT_DIR + f"figure_chaos_landing_error_{tag}.png")
    return results


def main():
    if not os.path.isdir(OUT_DIR):
        stop(f"output folder {OUT_DIR} does not exist")
    rows = C.load_join()
    windows = C.windows_of(rows)
    per_axis = load_per_axis()

    n_rows = len(rows)
    n_flights = len({(r["session"], r["flight"]) for r in rows})
    if n_rows != 2568 or n_flights != 107 or len(windows) != 24:
        stop(f"join shape wrong: {n_rows} rows (want 2568), {n_flights} flights "
             f"(want 107), {len(windows)} windows (want 24)")
    print(f"GATE join shape: {n_rows} rows, {n_flights} flights, {len(windows)} windows -> PASS")

    durations = C.class_durations(rows)
    n_class = {c: len(v) for c, v in durations.items()}
    max_ltc = {c: max(v) for c, v in durations.items()}
    if n_class["SHORT"] != 47 or n_class["LONG"] != 60:
        stop(f"class counts wrong: {n_class}, want SHORT 47 / LONG 60")
    print(f"GATE class counts: SHORT {n_class['SHORT']}, LONG {n_class['LONG']} -> PASS")
    print(f"deadlines (min-anchored, recomputed, not used by this verdict): "
          f"{ {k: round(v) for k, v in C.deadlines(rows).items()} }")
    print(f"truncation at class max launch_to_crossing_ms: "
          f"{ {c: round(v, 1) for c, v in max_ltc.items()} }")

    # units + |dv| cross-check against the stored scalar
    print(f"\nUNITS: landing_error = |dp| + e*|dv|*t = [mm] + [-]*[mm/s]*[s] = [mm]. "
          f"e = {E_COR} dimensionless, t = {T_RETURN_S:.1f} s.")
    bad = 0
    for r in rows:
        if r["status"] != "ok":
            continue
        _, _, dv = terms_of(r, per_axis)
        if abs(dv - float(r["velocity_error_mm_s"])) > 1e-6:
            bad += 1
    print(f"|dv| from components vs stored velocity_error_mm_s: {bad} mismatches "
          f"over {len(per_axis)} fitted rows")
    if bad:
        stop(f"{bad} rows disagree between the per-axis norm and the stored scalar")

    # ---- GATE: three-criterion regression ----
    print(f"\nGATE three-criterion regression (placement disabled, velocity restored "
          f"to {VEL_TOL_THREE_CRITERION:.1f} mm/s):")
    three = {}
    for A in A_VALUES:
        _, _, _, best3 = evaluate(rows, per_axis, windows, A, float("inf"),
                                  FAILURES_THREE, BAND_ORDER_THREE, n_class)
        three[A] = best3
        for cls in C.CLASSES:
            got, want = round(best3[cls]["rate"], 1), THREE_CRITERION_EXPECTED[(cls, A)]
            ok = abs(got - want) < 0.05
            print(f"    {cls:5s} A={A:>3.0f}  got {got:>5.1f}%  want {want:>5.1f}%  "
                  f"-> {'PASS' if ok else 'FAIL'}")
            if not ok:
                stop(f"three-criterion regression failed for {cls} A={A:.0f}: "
                     f"got {got}%, expected {want}%")
    print("  -> PASS, machinery unchanged; only the criterion set differs")

    # ---- GATE: bug detector ----
    # Failing BOTH separate tests puts the sum above 1000, so it cannot pass <=500.
    sep_pos, sep_vel = 500.0, 500.0 / (E_COR * T_RETURN_S)
    viol = 0
    for r in rows:
        if r["status"] != "ok":
            continue
        dp, vterm, dv = terms_of(r, per_axis)
        if (dp + vterm) <= 500.0 and dp > sep_pos and dv > sep_vel:
            viol += 1
    print(f"\nGATE bug detector (rows passing combined<=500 while failing BOTH "
          f"separate tests at {sep_pos:.0f} mm and {sep_vel:.0f} mm/s): {viol} "
          f"-> {'PASS' if viol == 0 else 'FAIL'}")
    if viol:
        stop(f"{viol} rows passed combined<=500 while failing both separate tests - "
             f"mathematically impossible, indicates an implementation bug")

    res = {}
    for threshold, tag, anchor in RUNS:
        res[threshold] = run_threshold(rows, per_axis, windows, max_ltc, n_class,
                                       threshold, tag, anchor)

    # ---- comparison across the three schemes ----
    print("\n=== COMPARISON: three-criterion vs combined-500 vs combined-1000 ===")
    hdr = (f"{'class':6s} {'A':>5} | {'3-crit':>8} | {'comb-1000':>10} {'delta':>8} | "
           f"{'comb-500':>9} {'delta':>8}")
    print(hdr)
    print("-" * len(hdr))
    comp = []
    for A in A_VALUES:
        for cls in C.CLASSES:
            r3 = three[A][cls]["rate"]
            r1000 = res[1000.0][A]["best"][cls]["rate"]
            r500 = res[500.0][A]["best"][cls]["rate"]
            print(f"{cls:6s} {A:>5.0f} | {r3:>7.1f}% | {r1000:>9.1f}% {r1000-r3:>+7.1f} | "
                  f"{r500:>8.1f}% {r500-r3:>+7.1f}")
            comp.append(dict(cls=cls, A=A, success_3crit=r3,
                             window_3crit=three[A][cls]["window"],
                             success_combined_1000=r1000,
                             window_combined_1000=res[1000.0][A]["best"][cls]["window"],
                             delta_1000_vs_3crit=r1000 - r3,
                             success_combined_500=r500,
                             window_combined_500=res[500.0][A]["best"][cls]["window"],
                             delta_500_vs_3crit=r500 - r3))
    path = OUT_DIR + "comparison_three_schemes.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(comp[0].keys()))
        w.writeheader()
        for r in comp:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})
    print(f"\nwrote {path}")

    # ---- separate gates vs combined-500, over every fitted flight-window row ----
    pass_sep = pass_comb = sep_not_comb = comb_not_sep = n_fit = 0
    for r in rows:
        if r["status"] != "ok":
            continue
        n_fit += 1
        dp, vterm, dv = terms_of(r, per_axis)
        s = (dp <= sep_pos) and (dv <= sep_vel)
        c = (dp + vterm) <= 500.0
        pass_sep += s
        pass_comb += c
        sep_not_comb += (s and not c)
        comb_not_sep += (c and not s)
    print(f"\n=== SEPARATE GATES ({sep_pos:.0f} mm AND {sep_vel:.0f} mm/s) vs "
          f"COMBINED <= 500 mm, over {n_fit} fitted rows ===")
    print(f"  pass separate            : {pass_sep:>5d}  ({100.0*pass_sep/n_fit:.1f}%)")
    print(f"  pass combined-500        : {pass_comb:>5d}  ({100.0*pass_comb/n_fit:.1f}%)")
    print(f"  pass separate, FAIL comb : {sep_not_comb:>5d}  "
          f"({100.0*sep_not_comb/n_fit:.1f}%)   <- how much stricter combined is")
    print(f"  pass combined, FAIL sep  : {comb_not_sep:>5d}  "
          f"({100.0*comb_not_sep/n_fit:.1f}%)   <- necessarily 0, see log")
    with open(OUT_DIR + "separate_vs_combined_500.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "n_rows", "pct_of_fitted"])
        for name, v in (("n_fitted_rows", n_fit), ("pass_separate", pass_sep),
                        ("pass_combined_500", pass_comb),
                        ("pass_separate_fail_combined", sep_not_comb),
                        ("pass_combined_fail_separate", comb_not_sep)):
            w.writerow([name, v, f"{100.0*v/n_fit:.4f}"])
    print(f"  wrote {OUT_DIR}separate_vs_combined_500.csv")
    print(f"\nAll outputs in {OUT_DIR}")


if __name__ == "__main__":
    main()
