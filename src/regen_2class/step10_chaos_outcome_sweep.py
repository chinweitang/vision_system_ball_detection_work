"""Step 10 - chaos-rally outcome sweep with the full four-criterion verdict.

Extends the Figure D machinery to chaos rally, where the answer must land A ms
BEFORE the ball arrives (target mode allowed +84 ms AFTER; the sign is opposite and
deliberate).

Per flight per observation window, precedence first-match-wins:
    no_response    status != "ok"
    late           t_obs + latency_ms > launch_to_crossing_ms - A
    wrong_class    hit_miss_match is False
    wrong_position position_error_mm >= POSITION_THRESHOLD_MM
    wrong_velocity any world axis outside its tolerance
    success        all pass
with t_obs = min(observation window, duration_ms).

PER-AXIS VELOCITY IS AVAILABLE, so the conservative scalar fallback is NOT used.
Source: results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/figures2/
velocity_by_axis_raw.csv (2481 rows, exactly the status=="ok" rows), carrying
SIGNED err_vx / err_vy / err_vz plus the scalar velocity_error_mm_s. Produced by
prediction_pipeline_sweep_pi_vaxis.py, a copy of the original sweep script whose
only change was persisting the per-axis components; its regression check against
the original run matched on all 2481 rows.

Outputs (all new, under results/regenerate_figures/):
    figureF_chaos_outcome_sweep.png
    figureG_velocity_by_axis_twoclass.png
    chaos_outcome_by_class_A.csv
    chaos_outcome_cooccurrence.csv
    chaos_outcome_sensitivity_100_vs_150.csv

Reads existing outputs only. Nothing re-runs the Pi sweep, detection or fitting.
"""
import csv
import math
import sys
import statistics as st
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common as C
import clean_figures as CF

VAXIS_CSV = ("results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/"
             "figures2/velocity_by_axis_raw.csv")

A_VALUES = [72.0, 135.0, 220.0]          # panel tilt moves of 2, 10, 30 degrees
POSITION_THRESHOLD_MM = 100.0
POSITION_SENSITIVITY_MM = 150.0

# Velocity tolerance is a PLACEMENT tolerance, not a containment one, and it is
# ISOTROPIC - the same figure on all three world axes.
#     delta_v_max = placement_tolerance / (e * T_return)
# The earlier per-axis court-dimension tolerances (X 6618, Y 3676, Z 2206 mm/s)
# tested only whether the ball stays in play. The game requires the return to land
# near an intended spot, and a player covers roughly 1 m during a 1 s return flight,
# so 1 m is the point beyond which the intended shot difficulty changes.
E_COR = 0.68
T_RETURN_S = 1.0
PLACEMENT_TOLERANCE_M = 1.0
VELOCITY_TOL_MM_S = 1000.0 * PLACEMENT_TOLERANCE_M / (E_COR * T_RETURN_S)  # 1470 mm/s

# print-only sensitivity grid
PLACEMENT_GRID_M = [0.5, 1.0, 1.5]
T_RETURN_GRID_S = [1.0, 2.0]
# decision 77 label-precision floors; Y_world is UNRESOLVED, see caption
LABEL_FLOOR = {"x": 155.0, "y": 282.0, "z": 135.0}
AXIS_TITLE = {"x": "X_world (depth)", "y": "Y_world (width)", "z": "Z_world (up)"}

# Precedence order, used by verdict_of. NOT the stacking order.
FAILURES = ["no_response", "late", "wrong_class", "wrong_position", "wrong_velocity"]
# Stacking order, bottom -> top, matching Figure D's convention of success on the
# floor. Verdict logic is untouched; this affects drawing and the legend only.
BAND_ORDER = ["success", "wrong_velocity", "wrong_position", "wrong_class",
              "late", "no_response"]

# The previous amber family read as one block and caused a misread: wrong_class and
# wrong_position were indistinguishable at bar width. The three wrong bands now take
# separate hues. success, late and no_response still match Figure D exactly so the
# two figures read as a pair. Fixed hexes; the validator is deliberately not run.
BAND_COLOR = {
    "success": "#1baf7a",         # Figure D
    "wrong_velocity": "#e87ba4",  # magenta
    "wrong_position": "#eda100",  # amber, the dominant wrong band
    "wrong_class": "#2a78d6",     # blue
    "late": "#4a3aa7",            # Figure D
    "no_response": "#e34948",     # Figure D
}


def load_per_axis():
    """{(session, flight, window): (err_vx, err_vy, err_vz)}."""
    out = {}
    for r in C.read_csv(VAXIS_CSV):
        out[(r["session"], r["flight"], int(r["T_ms"]))] = (
            float(r["err_vx"]), float(r["err_vy"]), float(r["err_vz"]))
    return out


def flags(row, per_axis, A, pos_thresh, vel_tol=None):
    """The five failure conditions evaluated INDEPENDENTLY of precedence, so
    co-occurrence can be counted. Conditions that need a fit return None when the
    fit failed."""
    if row["status"] != "ok":
        return dict(no_response=True, late=None, wrong_class=None,
                    wrong_position=None, wrong_velocity=None)
    t_obs = min(float(row["T_ms"]), float(row["duration_ms"]))
    key = (row["session"], row["flight"], int(row["T_ms"]))
    err = per_axis.get(key)
    if err is None:
        raise SystemExit(f"STOP: no per-axis velocity for ok row {key}")
    return dict(
        no_response=False,
        late=(t_obs + float(row["latency_ms"])) > (float(row["launch_to_crossing_ms"]) - A),
        wrong_class=(row["hit_miss_match"] != "True"),
        wrong_position=float(row["position_error_mm"]) >= pos_thresh,
        # isotropic: the same placement-derived tolerance on every axis
        wrong_velocity=max(abs(e) for e in err) > (vel_tol or VELOCITY_TOL_MM_S),
    )


def verdict_of(f):
    for name in FAILURES:
        if f[name]:
            return name
    return "success"


def evaluate(rows, per_axis, windows, A, pos_thresh, vel_tol=None):
    """-> per_rows, counts[class][band][i], rate[class][i], best[class]"""
    per_rows = []
    for r in rows:
        f = flags(r, per_axis, A, pos_thresh, vel_tol)
        per_rows.append({**{"session": r["session"], "flight": r["flight"],
                            "cls2": r["cls2"], "T_ms": int(r["T_ms"]),
                            "status": r["status"]},
                         **{f"f_{k}": v for k, v in f.items()},
                         "verdict": verdict_of(f)})
    n_of = {c: len({(p["session"], p["flight"]) for p in per_rows if p["cls2"] == c})
            for c in C.CLASSES}
    counts = {c: {b: [] for b in BAND_ORDER} for c in C.CLASSES}
    rate = {c: [] for c in C.CLASSES}
    for c in C.CLASSES:
        for w in windows:
            sub = [p for p in per_rows if p["cls2"] == c and p["T_ms"] == w]
            k = Counter(p["verdict"] for p in sub)
            total = sum(k[b] for b in BAND_ORDER)
            if total != n_of[c]:
                raise SystemExit(f"ASSERT FAIL: {c} A={A} window={w} bands sum to "
                                 f"{total}, expected {n_of[c]}")
            for b in BAND_ORDER:
                counts[c][b].append(k[b])
            rate[c].append(100.0 * k["success"] / n_of[c])
    best = {}
    for c in C.CLASSES:
        i = max(range(len(windows)), key=lambda j: rate[c][j])
        best[c] = dict(window=windows[i], rate=rate[c][i], idx=i,
                       feasible=rate[c][i] > 0.0)
    return per_rows, n_of, counts, rate, best


def summarise_at(rows, per_rows, per_axis, cls, window, n_of):
    """Position, class-agreement and per-axis velocity stats at one operating point."""
    sub = [r for r in rows if r["cls2"] == cls and int(r["T_ms"]) == window]
    ok = [r for r in sub if r["status"] == "ok"]
    pos = [float(r["position_error_mm"]) for r in ok]
    agree = sum(1 for r in ok if r["hit_miss_match"] == "True")
    errs = [per_axis[(r["session"], r["flight"], window)] for r in ok]
    out = dict(
        n_total=n_of[cls], n_fit_failed=len(sub) - len(ok),
        median_pos=st.median(pos) if pos else None,
        p90_pos=C.percentile(pos, 0.90) if pos else None,
        hit_miss_rate=(100.0 * agree / len(ok)) if ok else None,
        n_ok=len(ok))
    for j, ax in enumerate(("x", "y", "z")):
        vals = [e[j] for e in errs]
        out[f"bias_{ax}"] = st.mean(vals) if vals else None
        out[f"rms_{ax}"] = math.sqrt(sum(v * v for v in vals) / len(vals)) if vals else None
        out[f"n_out_{ax}"] = sum(1 for v in vals if abs(v) > VELOCITY_TOL_MM_S)
    return out


def cooccurrence(per_rows, cls, window):
    """Counts of every unordered failure-mode pair co-occurring at one window.
    Pairs are counted only over rows where BOTH flags are defined."""
    sub = [p for p in per_rows if p["cls2"] == cls and p["T_ms"] == window]
    out = {}
    for i, a in enumerate(FAILURES):
        for b in FAILURES[i + 1:]:
            both = sum(1 for p in sub
                       if p[f"f_{a}"] is not None and p[f"f_{b}"] is not None
                       and p[f"f_{a}"] and p[f"f_{b}"])
            out[(a, b)] = both
    return out


def render_figure_f(windows, results, max_ltc, n_of):
    fig, axes = plt.subplots(3, 2, figsize=(15.0, 12.5), sharex=True)
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
            if best["feasible"] and best["idx"] in keep:
                bi = keep.index(best["idx"])
                ax.axvline(bi, color=C.INK2, ls=":", lw=1.3, zorder=4)
                ax.annotate(f"best {best['window']} ms   {best['rate']:.1f}%",
                            xy=(bi, n_of[cls]), xytext=(bi + 0.5, n_of[cls] * 1.04),
                            color=C.INK, fontsize=8.5, ha="left", va="bottom", zorder=5)
                title_extra = ""
            else:
                title_extra = "   INFEASIBLE"
            ax.set_ylim(0, n_of[cls] * 1.16)
            ax.set_title(f"{cls}  (n={n_of[cls]})   A = {A:.0f} ms{title_extra}",
                         color=C.INK, fontsize=10.5, loc="left", pad=5)
            if col_i == 0:
                ax.set_ylabel("flights", color=C.INK, fontsize=9.5)
            ax.set_xticks(xs)
            ax.set_xticklabels([str(windows[i]) for i in keep], rotation=90, fontsize=7)
    for col_i in range(2):
        axes[-1][col_i].set_xlabel(C.X_LABEL, color=C.INK, fontsize=10)
    fig.patch.set_facecolor(C.SURF)
    handles, _ = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, BAND_ORDER, frameon=False, fontsize=9.5, labelcolor=C.INK2,
               loc="upper center", bbox_to_anchor=(0.5, 0.975), ncol=6)
    fig.suptitle("Chaos-rally outcome sweep, four-criterion verdict "
                 f"(position < {POSITION_THRESHOLD_MM:.0f} mm)",
                 color=C.INK, fontsize=13.5, x=0.008, ha="left", y=0.995)
    caption = [
        "Chaos rally requires the answer A ms BEFORE arrival: late is t_obs + latency > launch_to_crossing - A. Target mode's test allowed +84 ms AFTER arrival; the sign is opposite and deliberate.",
        "Verdict precedence first-match-wins: no_response, late, wrong_class, wrong_position, wrong_velocity, success. Bands stack bottom to top as success, wrong_velocity, wrong_position, wrong_class, late, no_response,",
        "matching Figure D's convention of success on the floor. t_obs = min(observation window, duration).",
        f"Velocity tolerance is a PLACEMENT tolerance and is ISOTROPIC - the same {VELOCITY_TOL_MM_S:.0f} mm/s on all three world axes, from placement tolerance / (e x T_return) = {PLACEMENT_TOLERANCE_M:.1f} m / ({E_COR} x {T_RETURN_S:.1f} s).",
        "The earlier per-axis court-dimension tolerances tested only whether the ball stays in play. The game requires the return to land near an intended spot, and a player covers roughly 1 m during a 1 s return flight,",
        "so 1 m is the point beyond which the intended shot difficulty changes.",
        "position_error_mm and the velocity errors are CONVERGENCE against the full-arc Model-C fit, NOT accuracy against ground truth. fit_failed rows are retained as no_response; the denominator is always the class n.",
        "Each class is truncated at its own maximum launch-to-crossing time. A = 72 / 135 / 220 ms correspond to panel tilt moves of 2, 10 and 30 degrees.",
    ]
    path = C.OUT_DIR + "figureF_chaos_outcome_sweep.png"
    if CF.clean():
        CF.write_clean(fig, caption, path)
    else:
        for i, line in enumerate(caption):
            fig.text(0.006, 0.058 - i * 0.0078, line, color=C.INK2, fontsize=6.8)
        fig.tight_layout(rect=[0, 0.072, 1, 0.955])
        fig.savefig(path, dpi=150, facecolor=C.SURF)
        print(f"wrote {path}")
    plt.close(fig)


def render_velocity_figure(rows, per_axis, windows, max_ltc, op_window):
    """Three per-axis panels, SHORT/LONG, bias line plus scatter-RMS band, with the
    decision-77 label-precision floor shaded on each axis."""
    fig, axes = plt.subplots(1, 3, figsize=(16.0, 5.6))
    fig.patch.set_facecolor(C.SURF)
    for j, ax_key in enumerate(("x", "y", "z")):
        ax = axes[j]
        C.style_axes(ax)
        floor = LABEL_FLOOR[ax_key]
        ax.axhspan(-floor, floor, color="#8a8a84", alpha=0.13, lw=0, zorder=1)
        ax.axhline(0.0, color="#d5d4cf", lw=1.0, zorder=1)
        for cls in C.CLASSES:
            xs, bias, rms = [], [], []
            for w in windows:
                if w > max_ltc[cls]:
                    continue
                vals = [per_axis[(r["session"], r["flight"], w)][j] for r in rows
                        if r["cls2"] == cls and int(r["T_ms"]) == w and r["status"] == "ok"]
                if not vals:
                    continue
                xs.append(w)
                bias.append(st.mean(vals))
                rms.append(math.sqrt(sum(v * v for v in vals) / len(vals)))
            ax.fill_between(xs, [b - r for b, r in zip(bias, rms)],
                            [b + r for b, r in zip(bias, rms)],
                            color=C.CLASS_COLOR[cls], alpha=0.13, lw=0, zorder=2)
            ax.plot(xs, bias, color=C.CLASS_COLOR[cls], lw=2.0, marker="o", ms=4,
                    mec=C.SURF, mew=1.0, zorder=3,
                    label=cls if j == 0 else None)
        lo, hi = ax.get_ylim()
        for cls in C.CLASSES:
            w = op_window[cls]
            if w is None:
                continue
            ax.axvline(w, color=C.CLASS_COLOR[cls], ls=":", lw=1.4, zorder=2)
        ax.set_ylim(lo, hi)
        unresolved = "  UNRESOLVED" if ax_key == "y" else "  validated to label precision"
        ax.set_title(f"{AXIS_TITLE[ax_key]}\nfloor {floor:.0f} mm/s{unresolved}",
                     color=C.INK, fontsize=10, loc="left", pad=6)
        ax.set_xlabel(C.X_LABEL, color=C.INK, fontsize=9.5)
        if j == 0:
            ax.set_ylabel("velocity error: bias (line) +/- scatter RMS (band), mm/s",
                          color=C.INK, fontsize=9.5)
            ax.legend(frameon=False, fontsize=9.5, labelcolor=C.INK2, loc="lower right")
    fig.suptitle("Per-axis velocity error vs observation window, two-class scheme",
                 color=C.INK, fontsize=13, x=0.006, ha="left", y=0.995)
    caption = [
        "CONVERGENCE against the full-arc Model-C fit, NOT accuracy against ground truth. Shaded grey band is that axis's label-precision floor (decision 77).",
        "X_world and Z_world are validated to label precision; Y_world's floor is UNRESOLVED - the reference method was never validated on the width axis, so sitting inside that band means",
        "'not distinguishable from the reference's own unknown noise', NOT 'accurate to that figure'. Dotted verticals mark each class's chaos operating window at A = 135 ms.",
    ]
    path = C.OUT_DIR + "figureG_velocity_by_axis_twoclass.png"
    if CF.clean():
        CF.write_clean(fig, caption, path)
    else:
        for i, line in enumerate(caption):
            fig.text(0.006, 0.062 - i * 0.016, line, color=C.INK2, fontsize=7.2)
        fig.tight_layout(rect=[0, 0.115, 1, 0.95])
        fig.savefig(path, dpi=150, facecolor=C.SURF)
        print(f"wrote {path}")
    plt.close(fig)


def main():
    print("=== PER-AXIS VELOCITY AVAILABILITY (reported before computing) ===")
    per_axis = load_per_axis()
    print(f"  AVAILABLE per flight per observation window. Source: {VAXIS_CSV}")
    print(f"  {len(per_axis)} (session, flight, window) keys carrying SIGNED "
          f"err_vx / err_vy / err_vz.")
    print("  The conservative scalar fallback (2206 mm/s on velocity_error_mm_s) is "
          "NOT used.")

    rows = C.load_join()
    windows = C.windows_of(rows)
    durations = C.class_durations(rows)
    max_ltc = {c: max(v) for c, v in durations.items()}
    n_class = {c: len(v) for c, v in durations.items()}
    print(f"\nclasses recomputed from bin: SHORT={n_class['SHORT']}, LONG={n_class['LONG']}")
    assert n_class["SHORT"] == 47 and n_class["LONG"] == 60
    print(f"truncation at class max launch_to_crossing_ms: "
          f"{ {c: round(v, 1) for c, v in max_ltc.items()} }")

    # cross-check the per-axis components against the stored scalar
    bad = 0
    for r in rows:
        if r["status"] != "ok":
            continue
        e = per_axis[(r["session"], r["flight"], int(r["T_ms"]))]
        if abs(math.hypot(math.hypot(e[0], e[1]), e[2])
               - float(r["velocity_error_mm_s"])) > 1e-6:
            bad += 1
    print(f"per-axis vs stored scalar consistency: {bad} mismatches over "
          f"{len(per_axis)} rows")

    results = {}
    for A in A_VALUES:
        pr, n_of, counts, rate, best = evaluate(rows, per_axis, windows, A,
                                                POSITION_THRESHOLD_MM)
        results[A] = dict(per_rows=pr, counts=counts, rate=rate, best=best)
        print(f"[A={A:.0f}] ASSERT bands sum to class n at every window: PASS "
              f"({len(C.CLASSES) * len(windows)} cells)")

    # Does the velocity criterion ever bind? Counted over every A, class and window,
    # both as a verdict and as an independent flag, since precedence can mask it.
    print()
    for A in A_VALUES:
        pr = results[A]["per_rows"]
        as_verdict = sum(1 for p in pr if p["verdict"] == "wrong_velocity")
        as_flag = sum(1 for p in pr if p["f_wrong_velocity"] is True)
        print(f"[A={A:.0f}] wrong_velocity as verdict: {as_verdict} of {len(pr)} rows; "
              f"as an independent flag (ignoring precedence): {as_flag}")
    worst = {ax: max(abs(e[j]) for e in per_axis.values())
             for j, ax in enumerate(("x", "y", "z"))}
    print(f"  primary isotropic tolerance {VELOCITY_TOL_MM_S:.0f} mm/s "
          f"(placement {PLACEMENT_TOLERANCE_M:.1f} m, e={E_COR}, T_return={T_RETURN_S:.1f} s)")
    print("  worst single-row |error| per axis: " + ", ".join(
        f"{ax.upper()} {worst[ax]:.0f} mm/s ({100*worst[ax]/VELOCITY_TOL_MM_S:.1f}% of tol)"
        for ax in ("x", "y", "z")))

    # PRINT ONLY - the verdict and the figure keep the primary tolerance above.
    print()
    print("=== PLACEMENT-TOLERANCE SENSITIVITY (print only) ===")
    print(f"    delta_v_max = placement / (e x T_return), e = {E_COR}. "
          f"Rows evaluated: {len(per_axis)} (the status==ok rows).")
    print()
    hdr = (f"    {'placement':>10} {'T_ret':>6} {'tol mm/s':>9} | {'X':>6} {'Y':>6} "
           f"{'Z':>6} | {'ANY':>6} {'% rows':>8}")
    print(hdr)
    print("    " + "-" * (len(hdr) - 4))
    grid_tol = {}
    for place in PLACEMENT_GRID_M:
        for T_ret in T_RETURN_GRID_S:
            tol = 1000.0 * place / (E_COR * T_ret)
            grid_tol[(place, T_ret)] = tol
            per_ax, any_rows = [], set()
            for j in range(3):
                n = 0
                for key, e in per_axis.items():
                    if abs(e[j]) > tol:
                        n += 1
                        any_rows.add(key)
                per_ax.append(n)
            star = "  <- primary" if (place == PLACEMENT_TOLERANCE_M
                                      and T_ret == T_RETURN_S) else ""
            print(f"    {place:>9.1f}m {T_ret:>5.1f}s {tol:>9.0f} | {per_ax[0]:>6d} "
                  f"{per_ax[1]:>6d} {per_ax[2]:>6d} | {len(any_rows):>6d} "
                  f"{100.0*len(any_rows)/len(per_axis):>7.2f}%{star}")

    print()
    print("    best window and success rate across the same grid:")
    hdr2 = (f"    {'placement':>10} {'T_ret':>6} {'tol':>7} | " +
            " | ".join(f"{c} A={A:.0f}" for A in A_VALUES for c in C.CLASSES))
    print(hdr2)
    print("    " + "-" * (len(hdr2) - 4))
    for place in PLACEMENT_GRID_M:
        for T_ret in T_RETURN_GRID_S:
            tol = grid_tol[(place, T_ret)]
            cells = []
            for A in A_VALUES:
                _, _, _, _, bst = evaluate(rows, per_axis, windows, A,
                                           POSITION_THRESHOLD_MM, tol)
                for c in C.CLASSES:
                    b = bst[c]
                    cells.append(f"{b['window']:>5d}ms {b['rate']:>5.1f}%"
                                 if b["feasible"] else f"{'INFEASIBLE':>13}")
            print(f"    {place:>9.1f}m {T_ret:>5.1f}s {tol:>7.0f} | " + " | ".join(cells))

    # ---- summary CSV + console ----
    summary_rows, cooc_rows = [], []
    print()
    for A in A_VALUES:
        for cls in C.CLASSES:
            best = results[A]["best"][cls]
            counts = results[A]["counts"][cls]
            i = best["idx"]
            if not best["feasible"]:
                print(f"INFEASIBLE: {cls} at A={A:.0f} ms - no observation window "
                      f"achieves any success")
                summary_rows.append(dict(cls=cls, A=A, window="INFEASIBLE"))
                continue
            w = best["window"]
            s = summarise_at(rows, results[A]["per_rows"], per_axis, cls, w, n_class)
            band = {b: counts[b][i] for b in BAND_ORDER}
            summary_rows.append(dict(cls=cls, A=A, window=w, rate=best["rate"],
                                     **band, **s))
            print(f"--- {cls}  A={A:.0f} ms   best window {w} ms   success "
                  f"{best['rate']:.1f}%  ({band['success']}/{n_class[cls]})")
            print(f"      bands: " + "  ".join(f"{b}={band[b]}" for b in BAND_ORDER))
            print(f"      position: median {s['median_pos']:.1f} mm, p90 "
                  f"{s['p90_pos']:.1f} mm")
            print(f"      hit/miss agreement {s['hit_miss_rate']:.1f}% over "
                  f"{s['n_ok']} fitted rows; n_fit_failed={s['n_fit_failed']} "
                  f"(reported separately, excluded from that rate)")
            for ax_key in ("x", "y", "z"):
                print(f"      vel {AXIS_TITLE[ax_key]:<18s} bias {s['bias_'+ax_key]:+8.1f} "
                      f"rms {s['rms_'+ax_key]:8.1f} mm/s   outside tol: "
                      f"{s['n_out_'+ax_key]}/{s['n_ok']}")
            co = cooccurrence(results[A]["per_rows"], cls, w)
            nz = {k: v for k, v in co.items() if v > 0}
            print(f"      failure-mode co-occurrence at that window: "
                  f"{nz if nz else 'none - all failure modes disjoint'}")
            for (a, b), v in co.items():
                cooc_rows.append(dict(cls=cls, A=A, window=w, mode_a=a, mode_b=b, n=v))

    with open(C.OUT_DIR + "chaos_outcome_by_class_A.csv", "w", newline="",
              encoding="utf-8") as f:
        cols = (["cls", "A", "window", "rate"] + BAND_ORDER +
                ["n_total", "n_ok", "n_fit_failed", "median_pos", "p90_pos",
                 "hit_miss_rate"] +
                [f"{p}_{a}" for a in ("x", "y", "z") for p in ("bias", "rms", "n_out")])
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in summary_rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v)
                        for k, v in r.items()})
    with open(C.OUT_DIR + "chaos_outcome_cooccurrence.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["cls", "A", "window", "mode_a", "mode_b", "n"])
        w.writeheader()
        w.writerows(cooc_rows)
    print(f"\nwrote {C.OUT_DIR}chaos_outcome_by_class_A.csv")
    print(f"wrote {C.OUT_DIR}chaos_outcome_cooccurrence.csv")

    render_figure_f(windows, results, max_ltc, n_class)

    # ---- sensitivity, 100 mm vs 150 mm ----
    print()
    print("=== SENSITIVITY: position threshold 100 mm vs 150 mm (no second figure) ===")
    sens_rows = []
    hdr = (f"{'class':6s} {'A':>5} | {'win100':>7} {'succ100':>8} | "
           f"{'win150':>7} {'succ150':>8} | {'delta pp':>9}")
    print(hdr)
    print("-" * len(hdr))
    for A in A_VALUES:
        _, _, _, _, best150 = evaluate(rows, per_axis, windows, A,
                                       POSITION_SENSITIVITY_MM)
        for cls in C.CLASSES:
            b1, b2 = results[A]["best"][cls], best150[cls]
            w1 = b1["window"] if b1["feasible"] else None
            w2 = b2["window"] if b2["feasible"] else None
            print(f"{cls:6s} {A:>5.0f} | {str(w1):>7} {b1['rate']:>7.1f}% | "
                  f"{str(w2):>7} {b2['rate']:>7.1f}% | {b2['rate'] - b1['rate']:>+8.1f}")
            sens_rows.append(dict(cls=cls, A=A, window_100=w1, rate_100=b1["rate"],
                                  window_150=w2, rate_150=b2["rate"],
                                  delta_pp=b2["rate"] - b1["rate"]))
    with open(C.OUT_DIR + "chaos_outcome_sensitivity_100_vs_150.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(sens_rows[0].keys()))
        w.writeheader()
        for r in sens_rows:
            w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v)
                        for k, v in r.items()})
    print(f"wrote {C.OUT_DIR}chaos_outcome_sensitivity_100_vs_150.csv")

    # velocity figure verticals use the nominal A = 135 ms operating windows
    op = {c: (results[135.0]["best"][c]["window"]
              if results[135.0]["best"][c]["feasible"] else None) for c in C.CLASSES}
    # Figure G is NOT rendered by default. A previous rerun of this script rewrote it
    # as a side effect while only Figure F was meant to change; pass --figure-g to
    # regenerate it deliberately.
    if "--figure-g" in sys.argv:
        print(f"\nvelocity-figure verticals at the A=135 ms operating windows: {op}")
        render_velocity_figure(rows, per_axis, windows, max_ltc, op)
    else:
        print(f"\nFigure G NOT regenerated (pass --figure-g to rebuild it). "
              f"A=135 ms operating windows would be: {op}")


if __name__ == "__main__":
    main()
