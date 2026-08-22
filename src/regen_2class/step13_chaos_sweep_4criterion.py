"""Step 13 - chaos-rally outcome sweep, FOUR-criterion verdict.

A re-read of frozen data at new thresholds. No new experiments, no re-fitting, no
model change. Every input is an existing file read read-only.

WHY POSITION RETURNS AS A PASS CRITERION
----------------------------------------
The three-criterion version removed it, arguing a rigid panel in pure translation
returns the ball independently of contact location. That holds for outgoing
VELOCITY - v_out = e*v_in + (1+e)*u carries no rotation term - but NOT for outgoing
POSITION: the ball departs from wherever it was struck, so a crossing-position error
translates the whole return trajectory by the same amount.

Position error and velocity error displace the SAME landing point in the SAME frame
and both come from the same Model-C fit on the same detected points, so they are
correlated in source and add LINEARLY. Quadrature would assume an independence that
does not hold.

THRESHOLDS
----------
Total landing-error budget at the player 1000 mm, split EQUALLY - a stated budget
choice, not a derived result. No physical basis favours either term, and over a 1 s
return a static offset and an accumulated velocity error are commensurable.
    position: 1000/2 = 500 mm
    velocity: (1000/2) / (e * t) = 500 / (0.68 * 1.0) = 735 mm/s, isotropic
e = 0.68 is the published volleyball-on-rigid-surface coefficient of restitution.
Supersedes 1471 mm/s, which gave the whole budget to velocity and counted no
position term.

Outputs go to a NEW numbered subfolder; nothing existing is overwritten.
"""
import csv
import math
import os
import statistics as st
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common as C
from step10_chaos_outcome_sweep import AXIS_TITLE, load_per_axis

OUT_DIR = "data/regenerate_figures/01_chaos_4criterion/"

# ---- budget -> thresholds (derived, not hardcoded) ----
E_COR = 0.68                     # published volleyball-on-rigid-surface COR
T_RETURN_S = 1.0
TOTAL_BUDGET_MM = 1000.0
SENS_BUDGET_MM = 500.0
Y_WIDTH_LABEL_SD_MM_S = 282.0    # decision 77, the weak axis reference noise floor


def budget_to_thresholds(total_mm):
    """Equal linear split: half to position, half to velocity over the return."""
    pos = total_mm / 2.0
    vel = (total_mm / 2.0) / (E_COR * T_RETURN_S)
    return pos, vel


POS_TOL_MM, VEL_TOL_MM_S = budget_to_thresholds(TOTAL_BUDGET_MM)          # 500, 735
POS_TOL_SENS, VEL_TOL_SENS = budget_to_thresholds(SENS_BUDGET_MM)         # 250, 368
VEL_TOL_THREE_CRITERION = 1000.0 * 1.0 / (E_COR * T_RETURN_S)             # 1471

A_VALUES = [72.0, 135.0, 220.0]

FAILURES_4 = ["no_response", "late", "wrong_class", "wrong_position", "wrong_velocity"]
FAILURES_3 = ["no_response", "late", "wrong_class", "wrong_velocity"]
BAND_ORDER_4 = ["success", "wrong_velocity", "wrong_position", "wrong_class",
                "late", "no_response"]
BAND_ORDER_3 = ["success", "wrong_velocity", "wrong_class", "late", "no_response"]

BAND_COLOR = {
    "success": "#1baf7a", "wrong_velocity": "#e87ba4", "wrong_position": "#eda100",
    "wrong_class": "#2a78d6", "late": "#4a3aa7", "no_response": "#e34948",
}

# regression targets - the published three-criterion result (Figure H)
THREE_CRITERION_EXPECTED = {
    ("SHORT", 72.0): 93.6, ("SHORT", 135.0): 93.6, ("SHORT", 220.0): 74.5,
    ("LONG", 72.0): 98.3, ("LONG", 135.0): 98.3, ("LONG", 220.0): 98.3,
}


def stop(msg):
    raise SystemExit(f"\n*** STOP GATE FAILED ***\n{msg}\n")


def flags_of(row, per_axis, A, pos_tol, vel_tol):
    """The failure conditions, evaluated INDEPENDENTLY of precedence so they can
    also be counted per-requirement. Conditions needing a fit return None when the
    fit failed. Thresholds are strict >, matching the brief."""
    if row["status"] != "ok":
        return dict(no_response=True, late=None, wrong_class=None,
                    wrong_position=None, wrong_velocity=None)
    t_obs = min(float(row["T_ms"]), float(row["duration_ms"]))
    err = per_axis[(row["session"], row["flight"], int(row["T_ms"]))]
    return dict(
        no_response=False,
        late=(t_obs + float(row["latency_ms"])) > (float(row["launch_to_crossing_ms"]) - A),
        wrong_class=(row["hit_miss_match"] != "True"),
        wrong_position=float(row["position_error_mm"]) > pos_tol,
        wrong_velocity=max(abs(e) for e in err) > vel_tol,
    )


def evaluate(rows, per_axis, windows, A, pos_tol, vel_tol, order, bands, n_class):
    per_rows = []
    for r in rows:
        f = flags_of(r, per_axis, A, pos_tol, vel_tol)
        verdict = "success"
        for name in order:
            if f[name]:
                verdict = name
                break
        per_rows.append({"session": r["session"], "flight": r["flight"],
                         "cls2": r["cls2"], "T_ms": int(r["T_ms"]),
                         **{f"f_{k}": v for k, v in f.items()}, "verdict": verdict})
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
        mx = max(rate[c])                       # step 1: reliability alone decides
        plateau = [j for j, v in enumerate(rate[c]) if v == mx]
        i = plateau[-1]                         # step 2: latest of the tied windows
        best[c] = dict(window=windows[i], rate=mx, idx=i,
                       plateau_idx=plateau,
                       plateau_windows=[windows[j] for j in plateau])
    return per_rows, counts, rate, best


def position_stats(rows, cls, window):
    v = [float(r["position_error_mm"]) for r in rows
         if r["cls2"] == cls and int(r["T_ms"]) == window and r["status"] == "ok"]
    if not v:
        return None
    return dict(n_ok=len(v), pos_median=st.median(v),
                pos_p90=C.percentile(v, 0.90), pos_max=max(v))


def velocity_stats(rows, per_axis, cls, window):
    errs = [per_axis[(r["session"], r["flight"], window)] for r in rows
            if r["cls2"] == cls and int(r["T_ms"]) == window and r["status"] == "ok"]
    out = {}
    for j, ax in enumerate(("x", "y", "z")):
        vals = [e[j] for e in errs]
        out[f"bias_{ax}"] = st.mean(vals) if vals else None
        out[f"rms_{ax}"] = (math.sqrt(sum(v * v for v in vals) / len(vals))
                            if vals else None)
    return out


def independent_flags(per_rows, cls, window):
    sub = [p for p in per_rows if p["cls2"] == cls and p["T_ms"] == window]
    out = {}
    for name in FAILURES_4:
        out[f"ind_{name}"] = sum(1 for p in sub if p[f"f_{name}"] is True)
        out[f"ind_{name}_evaluable"] = sum(1 for p in sub if p[f"f_{name}"] is not None)
    return out


def render(windows, results, max_ltc, n_class, pos_tol, vel_tol, path,
           title_extra, caption_extra):
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
            for b in BAND_ORDER_4:
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
    fig.legend(handles, BAND_ORDER_4, frameon=False, fontsize=9.5, labelcolor=C.INK2,
               loc="upper center", bbox_to_anchor=(0.5, 0.975), ncol=6)
    fig.suptitle(f"Chaos-rally outcome sweep, FOUR-criterion verdict{title_extra}",
                 color=C.INK, fontsize=13.5, x=0.008, ha="left", y=0.995)
    caption = [
        "Position is a pass criterion again. v_out = e*v_in + (1+e)*u carries no rotation term, so outgoing VELOCITY is independent of contact location - but the ball departs from wherever it was struck, so a",
        "crossing-position error translates the whole return trajectory by the same amount. Position error and velocity error displace the SAME landing point in the SAME frame and both come from the same Model-C fit",
        "on the same detected points, so they are correlated in source and add LINEARLY; quadrature would assume an independence that does not hold.",
        f"Total landing-error budget {'1000' if pos_tol > 300 else '500'} mm at the player, split EQUALLY between the two terms - a stated budget choice, not a derived result: no physical basis favours either term, and over a 1 s return a static",
        f"offset and an accumulated velocity error are directly commensurable. Position term {pos_tol:.0f} mm. Velocity term {pos_tol:.0f} mm / (e x t) with e = {E_COR} (published volleyball-on-rigid-surface coefficient of",
        f"restitution, not assumed) and t = {T_RETURN_S:.1f} s -> {vel_tol:.0f} mm/s applied isotropically to all three world axes.",
        "position_error_mm and the per-axis velocity errors are CONVERGENCE against the full-arc Model-C fit, NOT accuracy against ground truth.",
        "Chaos rally needs the answer A ms BEFORE arrival: late is t_obs + latency > launch_to_crossing - A, opposite in sign to target mode's +84 ms after. t_obs = min(observation window, duration). Verdict precedence",
        "first-match-wins: no_response, late, wrong_class, wrong_position, wrong_velocity, success. Where several windows tie at the maximum success rate the LATEST is selected; position never influences that maximisation.",
        "fit_failed rows are retained as no_response; the denominator is always the class n. Each class is truncated at its own maximum launch-to-crossing time. A = 72/135/220 ms are panel tilt moves of 2, 10 and 30 degrees.",
    ] + caption_extra
    # Caption length differs between variants (the sensitivity run adds two lines),
    # so anchor the LAST line at a fixed height and grow upward. A fixed start point
    # clipped the final sensitivity line, which is the one that says it is not the
    # requirement - the single line that most needed to be legible.
    gap, floor_y = 0.0068, 0.010
    start_y = floor_y + (len(caption) - 1) * gap
    for i, line in enumerate(caption):
        fig.text(0.006, start_y - i * gap, line, color=C.INK2, fontsize=6.5)
    fig.tight_layout(rect=[0, start_y + 0.016, 1, 0.955])
    fig.savefig(path, dpi=150, facecolor=C.SURF)
    plt.close(fig)
    print(f"  wrote {path}")


def run_variant(rows, per_axis, windows, max_ltc, n_class, pos_tol, vel_tol,
                tag, title_extra, caption_extra):
    print(f"\n=== VARIANT {tag}: position > {pos_tol:.0f} mm, velocity > "
          f"{vel_tol:.1f} mm/s isotropic ===")
    results = {}
    for A in A_VALUES:
        pr, counts, rate, best = evaluate(rows, per_axis, windows, A, pos_tol,
                                          vel_tol, FAILURES_4, BAND_ORDER_4, n_class)
        results[A] = dict(per_rows=pr, counts=counts, rate=rate, best=best)
        print(f"  [A={A:.0f}] band sums OK at all {len(C.CLASSES)*len(windows)} cells")

    # per-window band counts
    band_rows = []
    for A in A_VALUES:
        for cls in C.CLASSES:
            for i, w in enumerate(windows):
                band_rows.append(dict(cls=cls, A=A, window=w,
                                      success_rate=results[A]["rate"][cls][i],
                                      **{b: results[A]["counts"][cls][b][i]
                                         for b in BAND_ORDER_4}))
    path = OUT_DIR + f"bands_by_class_A_window_{tag}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["cls", "A", "window", "success_rate"] + BAND_ORDER_4)
        w.writeheader()
        for r in band_rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})
    print(f"  wrote {path}  ({len(band_rows)} rows)")

    # operating points
    op_rows = []
    for A in A_VALUES:
        for cls in C.CLASSES:
            best = results[A]["best"][cls]
            w, i = best["window"], best["idx"]
            ps = position_stats(rows, cls, w) or {}
            vs = velocity_stats(rows, per_axis, cls, w)
            ind = independent_flags(results[A]["per_rows"], cls, w)
            band = {b: results[A]["counts"][cls][b][i] for b in BAND_ORDER_4}
            n_ff = n_class[cls] - ps.get("n_ok", 0)
            op_rows.append(dict(cls=cls, A=A, selected_window=w,
                                success_rate=best["rate"],
                                plateau_windows=";".join(str(x) for x in best["plateau_windows"]),
                                plateau_size=len(best["plateau_windows"]),
                                n_total=n_class[cls], n_fit_failed=n_ff,
                                **band, **ps, **vs, **ind))
            print(f"\n  --- {cls}  A={A:.0f} ms   plateau {best['plateau_windows']} "
                  f"-> selected {w} ms   success {best['rate']:.1f}% "
                  f"({band['success']}/{n_class[cls]})")
            print(f"        bands: " + "  ".join(f"{b}={band[b]}" for b in BAND_ORDER_4))
            if ps:
                print(f"        position: median {ps['pos_median']:.1f}, p90 "
                      f"{ps['pos_p90']:.1f}, max {ps['pos_max']:.1f} mm   "
                      f"(n_ok {ps['n_ok']}, n_fit_failed {n_ff})")
            for ax in ("x", "y", "z"):
                print(f"        vel {AXIS_TITLE[ax]:<18s} bias {vs['bias_'+ax]:+8.1f} "
                      f"rms {vs['rms_'+ax]:8.1f} mm/s")
            print(f"        INDEPENDENT flag counts (ignoring precedence):")
            for name in FAILURES_4:
                print(f"            {name:<15s} {ind['ind_'+name]:>3d} of "
                      f"{ind['ind_'+name+'_evaluable']:>3d} evaluable")
    path = OUT_DIR + f"operating_points_{tag}.csv"
    cols = (["cls", "A", "selected_window", "success_rate", "plateau_windows",
             "plateau_size", "n_total", "n_ok", "n_fit_failed"] + BAND_ORDER_4 +
            ["pos_median", "pos_p90", "pos_max"] +
            [f"{p}_{a}" for a in ("x", "y", "z") for p in ("bias", "rms")] +
            [f"ind_{n}" for n in FAILURES_4] +
            [f"ind_{n}_evaluable" for n in FAILURES_4])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in op_rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})
    print(f"\n  wrote {path}")

    render(windows, results, max_ltc, n_class, pos_tol, vel_tol,
           OUT_DIR + f"figure_chaos_4criterion_{tag}.png", title_extra, caption_extra)
    return results


def main():
    if not os.path.isdir(OUT_DIR):
        stop(f"output folder {OUT_DIR} does not exist")
    rows = C.load_join()
    windows = C.windows_of(rows)
    per_axis = load_per_axis()

    # ---- STOP GATE: join shape ----
    n_rows = len(rows)
    n_flights = len({(r["session"], r["flight"]) for r in rows})
    n_windows = len(windows)
    if n_rows != 2568 or n_flights != 107 or n_windows != 24:
        stop(f"join shape wrong: {n_rows} rows (want 2568), {n_flights} flights "
             f"(want 107), {n_windows} windows (want 24)")
    print(f"GATE join shape: {n_rows} rows, {n_flights} flights, {n_windows} windows -> PASS")

    durations = C.class_durations(rows)
    n_class = {c: len(v) for c, v in durations.items()}
    max_ltc = {c: max(v) for c, v in durations.items()}
    if n_class["SHORT"] != 47 or n_class["LONG"] != 60:
        stop(f"class counts wrong: {n_class}, want SHORT 47 / LONG 60")
    print(f"GATE class counts: SHORT {n_class['SHORT']}, LONG {n_class['LONG']} -> PASS")
    # deadlines recomputed min-anchored for the record; the chaos verdict uses
    # launch_to_crossing_ms - A directly and does not consume them
    print(f"deadlines (min-anchored, recomputed, not used by this verdict): "
          f"{ {k: round(v) for k, v in C.deadlines(rows).items()} }")
    print(f"truncation at class max launch_to_crossing_ms: "
          f"{ {c: round(v, 1) for c, v in max_ltc.items()} }")
    print(f"thresholds: position > {POS_TOL_MM:.0f} mm, velocity > {VEL_TOL_MM_S:.2f} mm/s "
          f"(budget {TOTAL_BUDGET_MM:.0f} mm split equally, e={E_COR}, t={T_RETURN_S:.1f}s)")

    # ---- STOP GATE: three-criterion regression ----
    # Position DISABLED and velocity restored to the three-criterion value, so the
    # only difference from the published run is the criterion itself. Using the new
    # 735 mm/s here would change two things at once and the check would be void.
    print(f"\nGATE three-criterion regression (position disabled, velocity restored "
          f"to {VEL_TOL_THREE_CRITERION:.1f} mm/s):")
    for A in A_VALUES:
        _, _, rate3, best3 = evaluate(rows, per_axis, windows, A,
                                      float("inf"), VEL_TOL_THREE_CRITERION,
                                      FAILURES_3, BAND_ORDER_3, n_class)
        for cls in C.CLASSES:
            got = round(best3[cls]["rate"], 1)
            want = THREE_CRITERION_EXPECTED[(cls, A)]
            flag = "PASS" if abs(got - want) < 0.05 else "FAIL"
            print(f"    {cls:5s} A={A:>3.0f}  got {got:>5.1f}%  want {want:>5.1f}%  -> {flag}")
            if flag == "FAIL":
                stop(f"three-criterion regression failed for {cls} A={A:.0f}: "
                     f"got {got}%, expected {want}%")
    print("  -> PASS, machinery unchanged; only the criterion set differs")

    primary = run_variant(
        rows, per_axis, windows, max_ltc, n_class, POS_TOL_MM, VEL_TOL_MM_S,
        "primary", f"  (position > {POS_TOL_MM:.0f} mm, velocity > {VEL_TOL_MM_S:.0f} mm/s)",
        [])
    sens_caption = [
        f"THIS IS A REPORTED SENSITIVITY, NOT THE REQUIREMENT. At a {SENS_BUDGET_MM:.0f} mm total budget the velocity tolerance falls to {VEL_TOL_SENS:.0f} mm/s, but the Y_width label SD is ~{Y_WIDTH_LABEL_SD_MM_S:.0f} mm/s (decision 77),",
        f"so a {VEL_TOL_SENS:.0f} mm/s isotropic tolerance sits at roughly {VEL_TOL_SENS/Y_WIDTH_LABEL_SD_MM_S:.1f}x the reference noise floor on the weak axis and the test stops being informative there.",
    ]
    sens = run_variant(
        rows, per_axis, windows, max_ltc, n_class, POS_TOL_SENS, VEL_TOL_SENS,
        "sensitivity", f"  SENSITIVITY (position > {POS_TOL_SENS:.0f} mm, velocity > {VEL_TOL_SENS:.0f} mm/s)",
        sens_caption)

    # ---- comparison: three-criterion vs four-criterion ----
    print("\n=== COMPARISON: three-criterion vs four-criterion success rate ===")
    comp_rows = []
    hdr = (f"{'class':6s} {'A':>5} | {'3-crit':>8} | {'4-crit':>8} | {'delta pp':>9} | "
           f"{'3-crit win':>11} {'4-crit win':>11}")
    print(hdr)
    print("-" * len(hdr))
    for A in A_VALUES:
        _, _, _, best3 = evaluate(rows, per_axis, windows, A, float("inf"),
                                  VEL_TOL_THREE_CRITERION, FAILURES_3,
                                  BAND_ORDER_3, n_class)
        for cls in C.CLASSES:
            r3, r4 = best3[cls]["rate"], primary[A]["best"][cls]["rate"]
            print(f"{cls:6s} {A:>5.0f} | {r3:>7.1f}% | {r4:>7.1f}% | {r4-r3:>+8.1f} | "
                  f"{best3[cls]['window']:>9d}ms {primary[A]['best'][cls]['window']:>9d}ms")
            comp_rows.append(dict(cls=cls, A=A, success_rate_3crit=r3,
                                  window_3crit=best3[cls]["window"],
                                  success_rate_4crit=r4,
                                  window_4crit=primary[A]["best"][cls]["window"],
                                  delta_pp=r4 - r3,
                                  success_rate_4crit_sensitivity=sens[A]["best"][cls]["rate"],
                                  window_4crit_sensitivity=sens[A]["best"][cls]["window"]))
    path = OUT_DIR + "comparison_3crit_vs_4crit.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(comp_rows[0].keys()))
        w.writeheader()
        for r in comp_rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in r.items()})
    print(f"\nwrote {path}")
    print(f"\nAll outputs in {OUT_DIR}")


if __name__ == "__main__":
    main()
