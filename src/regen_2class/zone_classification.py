"""Zone-classification convergence vs square cell size on the crossing plane.

Pure arithmetic on an existing CSV. No fitting, no detection, no prediction, and
no re-derivation of the world frame or the crossing plane — the plane basis
arrives in the input and is used exactly as it arrives.

TERMINOLOGY. The reference is the full-arc fixed-gravity-with-drag fit, not
ground truth, so every fraction here measures CONVERGENCE toward that reference.
The summary CSV column is `match_fraction`. It is deliberately NOT called
accuracy: the CSV header outlives this session and is what a later reader will
believe, and nothing here is measured against ground truth.

Inputs (read-only):
    results/regenerate_figures/04_zone_classification/pipeline_sweep_positions.csv
    results/regenerate_figures/two_class_join.csv          (column cls2)

GRID PHASE. The corner-anchored grid makes the result depend on where the
boundaries happen to fall: changing D moves every line, impacts are clustered
rather than uniform, and at n=47/60 one line through a cluster costs ~10 points.
Each cell size is therefore evaluated at N_PHASE x N_PHASE grid origins spanning
one full cell, and the MEAN is the headline — a venue cannot tune its wall to
this dataset. The min-max band reports how much the answer depends on placement.
The envelope never moves; only the grid lines inside it do.

Outputs, all into results/regenerate_figures/04_zone_classification/:
    zone_classification_raw.csv          (phase 0 only, not multiplied by 100)
    zone_classification_summary.csv      (mean/min/max/sd/phase0 per class, D)
    zone_classification_by_phase.csv     (one row per class, D, phase - audit trail)
    y_offset_search.csv
    crossing_error_percentiles.csv
    figure_zone_classification.png

Nothing is overwritten: any output path that already exists takes the next free
numeric suffix.

STOP conditions:
    - 400 ms or 850 ms missing from the sweep
    - flight count != 107, or SHORT/LONG != 47/60
    - any cy_own/cz_own/cy_ref/cz_ref NaN or outside +/-10 m
    - any flight failing to join to a class
    - a flight whose reference position is not constant across its windows
"""
import csv
import math
import pathlib
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results/regenerate_figures/04_zone_classification"
POS_CSV = OUT_DIR / "pipeline_sweep_positions.csv"
JOIN_CSV = ROOT / "results/regenerate_figures/two_class_join.csv"

# Operating windows. No other window is analysed.
WINDOW = {"SHORT": 400, "LONG": 850}
CLASSES = ["SHORT", "LONG"]
EXPECTED_N = {"SHORT": 47, "LONG": 60}
EXPECTED_FLIGHTS = 107

# Envelope. Only the Y offset moves; neither span is ever resized.
ENV_W_MM = 5000.0          # Y (width)
ENV_H_MM = 4000.0          # Z (up), pinned at the ground
Y_STEP_MM = 10.0

CELL_SIZES_MM = [200, 250, 300, 400, 500, 600, 800, 1000, 1250, 1670, 2500]
THRESHOLD = 0.942

# Grid-phase averaging: N_PHASE x N_PHASE origin offsets spanning one full cell.
N_PHASE = 10

# n_correct at phase (0,0) from the previous corner-anchored run, kept as a
# regression check. Phase 0 of the phase-aware code must reproduce these exactly
# or the refactor has changed the analysis.
PHASE0_EXPECTED = {
    ("SHORT", 200): 24, ("SHORT", 250): 32, ("SHORT", 300): 31,
    ("SHORT", 400): 39, ("SHORT", 500): 40, ("SHORT", 600): 39,
    ("SHORT", 800): 42, ("SHORT", 1000): 43, ("SHORT", 1250): 42,
    ("SHORT", 1670): 43, ("SHORT", 2500): 46,
    ("LONG", 200): 27, ("LONG", 250): 42, ("LONG", 300): 39,
    ("LONG", 400): 43, ("LONG", 500): 55, ("LONG", 600): 49,
    ("LONG", 800): 52, ("LONG", 1000): 58, ("LONG", 1250): 53,
    ("LONG", 1670): 56, ("LONG", 2500): 60,
}

COORD_LIMIT_MM = 10000.0

CLASS_COLOUR = {"SHORT": "#2a78d6", "LONG": "#e34948"}


def stop(msg):
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def next_free(p):
    """Never overwrite. file.csv -> file_02.csv -> file_03.csv ..."""
    if not p.exists():
        return p
    n = 2
    while p.with_name(f"{p.stem}_{n:02d}{p.suffix}").exists():
        n += 1
    return p.with_name(f"{p.stem}_{n:02d}{p.suffix}")


def read_csv(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def percentile(values, q):
    """Linear-interpolated percentile, matching numpy's default method."""
    v = sorted(values)
    if not v:
        raise ValueError("percentile of an empty sequence")
    k = (len(v) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def cell_index(value, origin, d, n_cells, clamp_upper_edge):
    """Grid index by floor division from the envelope's bottom-left corner.

    `clamp_upper_edge` is used ONLY for reference points, which are inside the
    envelope by construction: a point sitting exactly on the far edge floors to
    one index past the last cell, which is a boundary artefact rather than a
    point outside. Predicted points are never clamped — see the module notes.
    """
    idx = int(math.floor((value - origin) / d))
    if clamp_upper_edge and idx == n_cells:
        idx = n_cells - 1
    return idx


def main():
    print("=" * 74)
    print("ZONE-CLASSIFICATION CONVERGENCE vs CELL SIZE")
    print("=" * 74)
    print("Reference = full-arc fixed-gravity-with-drag fit. This is CONVERGENCE")
    print("toward that reference, not accuracy against ground truth.")
    print()

    for p in (POS_CSV, JOIN_CSV):
        if not p.is_file():
            stop(f"required input missing: {p.relative_to(ROOT)}")
    rows = read_csv(POS_CSV)
    join = read_csv(JOIN_CSV)
    print(f"read {POS_CSV.relative_to(ROOT)}  ({len(rows)} rows)")
    print(f"read {JOIN_CSV.relative_to(ROOT)}  ({len(join)} rows)")

    # ---- windows present ---------------------------------------------------
    windows = {int(r["T_ms"]) for r in rows}
    for cls, w in WINDOW.items():
        if w not in windows:
            stop(f"operating window {w} ms ({cls}) is not present in the sweep")
    print(f"\nGATE windows PASS: 400 ms and 850 ms both present "
          f"({len(windows)} windows total)")

    # ---- class join --------------------------------------------------------
    cls_of = {}
    for r in join:
        cls_of[(r["session"], r["flight"])] = r["cls2"]
    flights = sorted({(r["session"], r["flight"]) for r in rows})
    unjoined = [f for f in flights if f not in cls_of]
    if unjoined:
        stop(f"{len(unjoined)} flight(s) failed to join to a class: {unjoined[:5]}")
    if len(flights) != EXPECTED_FLIGHTS:
        stop(f"flight count is {len(flights)}, expected {EXPECTED_FLIGHTS}")
    counts = {c: sum(1 for f in flights if cls_of[f] == c) for c in CLASSES}
    if counts != EXPECTED_N:
        stop(f"class counts are {counts}, expected {EXPECTED_N}")
    print(f"GATE join PASS: {len(flights)} flights, {counts}")

    # ---- value sanity ------------------------------------------------------
    bad = []
    for r in rows:
        if r["status"] != "ok":
            continue
        for c in ("cy_own", "cz_own", "cy_ref", "cz_ref"):
            s = r[c].strip()
            if not s or s.lower() == "nan":
                bad.append((r["session"], r["flight"], r["T_ms"], c, s or "<blank>"))
                continue
            if abs(float(s)) > COORD_LIMIT_MM:
                bad.append((r["session"], r["flight"], r["T_ms"], c, s))
    if bad:
        stop(f"{len(bad)} coordinate value(s) are NaN or outside +/-{COORD_LIMIT_MM/1000:.0f} m. "
             f"First few: {bad[:5]}")
    print(f"GATE coordinates PASS: no NaN, none outside +/-{COORD_LIMIT_MM/1000:.0f} m")

    # ---- reference is per-flight, constant across windows ------------------
    ref = {}
    inconsistent = []
    for r in rows:
        if r["status"] != "ok":
            continue
        k = (r["session"], r["flight"])
        v = (float(r["cy_ref"]), float(r["cz_ref"]))
        if k in ref and (abs(ref[k][0] - v[0]) > 1e-9 or abs(ref[k][1] - v[1]) > 1e-9):
            inconsistent.append((k, ref[k], v))
        ref[k] = v
    if inconsistent:
        stop(f"{len(inconsistent)} flight(s) have a reference position that varies "
             f"across windows, which it must not: {inconsistent[:3]}")
    print(f"GATE reference PASS: constant across windows for all {len(ref)} flights")

    # ---- Y-offset search ---------------------------------------------------
    print("\n" + "-" * 74)
    print("Y-OFFSET SEARCH  (inclusion decided on the REFERENCE only)")
    print("-" * 74)
    cys = [v[0] for v in ref.values()]
    lo = math.floor((min(cys) - ENV_W_MM) / Y_STEP_MM) * Y_STEP_MM
    hi = math.ceil((max(cys) + Y_STEP_MM) / Y_STEP_MM) * Y_STEP_MM
    print(f"  reference cy range: {min(cys):.1f} .. {max(cys):.1f} mm")
    print(f"  search grid: {lo:.0f} .. {hi:.0f} mm, step {Y_STEP_MM:.0f} mm "
          f"({int((hi - lo) / Y_STEP_MM) + 1} offsets)")

    def n_inside(y0):
        return sum(1 for (cy, cz) in ref.values()
                   if y0 <= cy <= y0 + ENV_W_MM and 0.0 <= cz <= ENV_H_MM)

    search = []
    off = lo
    while off <= hi + 1e-9:
        search.append((off, n_inside(off)))
        off += Y_STEP_MM
    best_n = max(n for _, n in search)
    # Ties broken by the SMALLEST offset, so the choice is deterministic.
    best_off = min(o for o, n in search if n == best_n)
    n_at_zero = n_inside(0.0)
    print(f"  best offset: {best_off:.0f} mm  -> {best_n} of {len(ref)} flights inside")
    print(f"  offset 0 mm            -> {n_at_zero} of {len(ref)} flights inside")
    print(f"  GAINED over offset 0   : {best_n - n_at_zero} flights")

    # ---- where the winner sits inside the searched range -------------------
    # A winner pinned against an endpoint means the 5000 mm window is being
    # pushed as far as it will go and is still clipping references: the spread
    # exceeds the envelope rather than merely being offset from it.
    span = hi - lo
    pos_frac = (best_off - lo) / span if span > 0 else 0.0
    d_lo, d_hi = best_off - lo, hi - best_off
    print(f"\n  searched range         : {lo:.0f} .. {hi:.0f} mm  (span {span:.0f} mm)")
    print(f"  winning offset         : {best_off:.0f} mm")
    print(f"  position within range  : {pos_frac:.4f} "
          f"({pos_frac*100:.2f}% of the way from {lo:.0f} to {hi:.0f})")
    print(f"  distance to low end    : {d_lo:.0f} mm")
    print(f"  distance to high end   : {d_hi:.0f} mm")
    if d_lo <= 100.0 or d_hi <= 100.0:
        which = "LOW" if d_lo <= 100.0 else "HIGH"
        print(f"  *** WARNING: the winning offset is within 100 mm of the {which} "
              f"endpoint of the searched range.")
        print(f"      References span more than {ENV_W_MM:.0f} mm in Y and no window "
              f"captures all of them.")

    y0 = best_off
    included = {k for k, (cy, cz) in ref.items()
                if y0 <= cy <= y0 + ENV_W_MM and 0.0 <= cz <= ENV_H_MM}
    excluded_by_class = {c: sum(1 for f in flights
                                if cls_of[f] == c and f not in included)
                         for c in CLASSES}
    included_by_class = {c: sum(1 for f in flights
                                if cls_of[f] == c and f in included)
                         for c in CLASSES}
    print(f"\n  included per class: {included_by_class}")
    print(f"  EXCLUDED per class (reference outside the envelope): {excluded_by_class}")
    for f in sorted(set(flights) - included):
        cy, cz = ref[f]
        print(f"    excluded {f[0]}/{f[1]:<14} cls={cls_of[f]:<5} "
              f"cy={cy:9.1f} cz={cz:9.1f}")

    # ---- predictions at the operating windows ------------------------------
    pred = {}
    for r in rows:
        if r["status"] != "ok":
            continue
        k = (r["session"], r["flight"])
        if int(r["T_ms"]) == WINDOW[cls_of[k]]:
            pred[k] = (float(r["cy_own"]), float(r["cz_own"]))
    missing_pred = [f for f in included if f not in pred]
    if missing_pred:
        stop(f"{len(missing_pred)} included flight(s) have no prediction at their "
             f"operating window: {missing_pred[:5]}")

    # ---- cell sweep --------------------------------------------------------
    print("\n" + "-" * 74)
    print("CELL SWEEP")
    print("-" * 74)
    # The grid is anchored to the envelope corner, so changing D moves every
    # boundary at once. Impacts are clustered rather than uniform, so whether a
    # boundary happens to bisect a cluster is arbitrary, and at n=47/60 one badly
    # placed line costs ~10 points. Averaging over grid PHASE removes that
    # arbitrariness. The ENVELOPE never moves; only the grid lines inside it do.
    raw_rows, summary_rows, phase_rows = [], [], []

    def count_matches(fl, d, org_y, org_z, n_cols, n_rows, collect=None):
        """Matches at one grid phase. `collect` receives per-flight detail."""
        n_ok = 0
        for f in fl:
            cy_r, cz_r = ref[f]
            cy_p, cz_p = pred[f]
            r_col = cell_index(cy_r, org_y, d, n_cols, True)
            r_row = cell_index(cz_r, org_z, d, n_rows, True)
            # Predictions are NEVER clamped, at any phase: an out-of-envelope
            # prediction keeps its raw (possibly negative or oversized) index so
            # it can never coincide with an in-envelope reference cell.
            p_col = cell_index(cy_p, org_y, d, n_cols, False)
            p_row = cell_index(cz_p, org_z, d, n_rows, False)
            match = (r_col == p_col and r_row == p_row)
            n_ok += match
            if collect is not None:
                collect.append((f, r_row, r_col, p_row, p_col, match,
                                cy_r, cz_r, cy_p, cz_p))
        return n_ok

    for cls in CLASSES:
        fl = sorted(f for f in included if cls_of[f] == cls)
        n_inc = len(fl)
        for d in CELL_SIZES_MM:
            n_cols = math.ceil(ENV_W_MM / d)
            n_rows = math.ceil(ENV_H_MM / d)
            step = d / N_PHASE

            fracs = []
            for i in range(N_PHASE):
                for j in range(N_PHASE):
                    org_y = y0 + i * step
                    org_z = 0.0 + j * step
                    # Phase (0,0) is exactly the old corner-anchored grid: the
                    # origins reduce to (y0, 0.0) and nothing else differs.
                    detail = [] if (i == 0 and j == 0) else None
                    n_ok = count_matches(fl, d, org_y, org_z, n_cols, n_rows,
                                         collect=detail)
                    fr = n_ok / n_inc if n_inc else 0.0
                    fracs.append(fr)
                    phase_rows.append(dict(
                        cls=cls, window_ms=WINDOW[cls], D_mm=d,
                        phase_i=i, phase_j=j,
                        origin_y_mm=f"{org_y:.4f}", origin_z_mm=f"{org_z:.4f}",
                        n_included=n_inc, n_correct=n_ok,
                        match_fraction=f"{fr:.6f}",
                    ))
                    if detail is not None:
                        # raw CSV stays phase 0 only - it is not multiplied by 100
                        for (f, r_row, r_col, p_row, p_col, match,
                             cy_r, cz_r, cy_p, cz_p) in detail:
                            raw_rows.append(dict(
                                session=f[0], flight=f[1],
                                flight_id=f"{f[0]}/{f[1]}",
                                cls=cls, window_ms=WINDOW[cls], D_mm=d,
                                ref_row=r_row, ref_col=r_col,
                                pred_row=p_row, pred_col=p_col,
                                match=bool(match),
                                cy_ref=f"{cy_r:.4f}", cz_ref=f"{cz_r:.4f}",
                                cy_own=f"{cy_p:.4f}", cz_own=f"{cz_p:.4f}",
                            ))

            if len(fracs) != N_PHASE * N_PHASE:
                stop(f"{cls} D={d}: {len(fracs)} phase evaluations, expected "
                     f"{N_PHASE * N_PHASE}")
            f0 = fracs[0]
            mean = sum(fracs) / len(fracs)
            var = sum((x - mean) ** 2 for x in fracs) / len(fracs)
            summary_rows.append(dict(
                cls=cls, window_ms=WINDOW[cls], D_mm=d,
                grid_rows=n_rows, grid_cols=n_cols, n_included=n_inc,
                # Named match_fraction, never accuracy: measured against the
                # full-arc reference, so this is convergence.
                match_fraction_mean=f"{mean:.6f}",
                match_fraction_min=f"{min(fracs):.6f}",
                match_fraction_max=f"{max(fracs):.6f}",
                match_fraction_sd=f"{math.sqrt(var):.6f}",
                match_fraction_phase0=f"{f0:.6f}",
                # The MEAN is the headline: a venue cannot tune its wall to this
                # dataset, so the expected phase is what it will get.
                clears_94_2=bool(mean >= THRESHOLD),
                clears_94_2_worst=bool(min(fracs) >= THRESHOLD),
            ))
            print(f"  {cls:<5} D={d:>5} mm  grid {n_rows}x{n_cols}  n={n_inc:<3} "
                  f"mean {mean:6.3f}  [min {min(fracs):6.3f}, max {max(fracs):6.3f}]  "
                  f"sd {math.sqrt(var):5.3f}  phase0 {f0:6.3f}"
                  f"{'   MEAN CLEARS' if mean >= THRESHOLD else ''}")

    # ---- PHASE-0 REGRESSION CHECK, before anything downstream --------------
    # Phase 0 must reproduce the previous corner-anchored run exactly. If it does
    # not, the phase refactor has changed the analysis and every number below it
    # is void, so this is checked first and hard-stops.
    print("\n" + "-" * 74)
    print("PHASE-0 REGRESSION CHECK vs the previous corner-anchored run")
    print("-" * 74)
    mismatched = []
    for r in summary_rows:
        exp = PHASE0_EXPECTED.get((r["cls"], int(r["D_mm"])))
        if exp is None:
            mismatched.append((r["cls"], r["D_mm"], "no expected value recorded", ""))
            continue
        got_n = round(float(r["match_fraction_phase0"]) * int(r["n_included"]))
        status = "OK " if got_n == exp else "*** MISMATCH ***"
        if got_n != exp:
            mismatched.append((r["cls"], r["D_mm"], exp, got_n))
        print(f"  {status} {r['cls']:<5} D={r['D_mm']:>5} mm  "
              f"previous {exp:>3}/{r['n_included']}   "
              f"now {got_n:>3}/{r['n_included']}   "
              f"phase0 fraction {r['match_fraction_phase0']}")
    if mismatched:
        stop(f"phase 0 does not reproduce the previous run at "
             f"{len(mismatched)} (class, D) pair(s): {mismatched[:5]}. "
             f"The refactor has changed the analysis; everything downstream is void.")
    print(f"  ALL {len(summary_rows)} (class, D) pairs reproduce phase 0 exactly.")

    # ---- smallest D clearing the threshold ---------------------------------
    def smallest_clearing(key):
        out = {}
        for cls in CLASSES:
            ok = [int(r["D_mm"]) for r in summary_rows
                  if r["cls"] == cls and r[key]]
            out[cls] = min(ok) if ok else None
        return out

    smallest = smallest_clearing("clears_94_2")
    smallest_worst = smallest_clearing("clears_94_2_worst")

    print("\n  smallest D whose MEAN clears 94.2%:")
    for cls in CLASSES:
        print(f"    {cls:<5} "
              f"{str(smallest[cls]) + ' mm' if smallest[cls] else 'NONE on the tested list'}")
    print("\n  smallest D whose MIN (worst phase) clears 94.2%:")
    for cls in CLASSES:
        print(f"    {cls:<5} "
              f"{str(smallest_worst[cls]) + ' mm' if smallest_worst[cls] else 'NONE on the tested list'}")

    print("\n  widest min-max spread across all D:")
    for cls in CLASSES:
        rs = [r for r in summary_rows if r["cls"] == cls]
        worst = max(rs, key=lambda r: float(r["match_fraction_max"])
                    - float(r["match_fraction_min"]))
        sp = float(worst["match_fraction_max"]) - float(worst["match_fraction_min"])
        print(f"    {cls:<5} {sp:.3f} at D={worst['D_mm']} mm "
              f"(min {worst['match_fraction_min']}, max {worst['match_fraction_max']})")

    print("\n  is the MEAN curve monotonically non-decreasing in D?")
    for cls in CLASSES:
        rs = sorted((r for r in summary_rows if r["cls"] == cls),
                    key=lambda r: int(r["D_mm"]))
        drops = []
        for a, b in zip(rs, rs[1:]):
            ma, mb = float(a["match_fraction_mean"]), float(b["match_fraction_mean"])
            if mb < ma:
                drops.append((int(a["D_mm"]), int(b["D_mm"]), ma - mb))
        if not drops:
            print(f"    {cls:<5} YES - non-decreasing at every step")
        else:
            print(f"    {cls:<5} NO - {len(drops)} decrease(s):")
            for d_from, d_to, amt in drops:
                print(f"        {d_from:>5} -> {d_to:<5} mm   falls by {amt:.4f}")

    # ---- structurally-fragile flights, at the smallest passing D -----------
    print("\n" + "-" * 74)
    print("STRUCTURALLY-FRAGILE FLIGHTS, at the smallest D clearing 94.2%")
    print("-" * 74)

    # Given as a mix of bare and session-qualified ids. The joined data keys on
    # (session, flight), so each is resolved against that and the outcome is
    # printed either way - a name that resolves to nothing is reported, never
    # allowed to silently contribute zero rows.
    FRAGILE = ["flight_121", "flight_122", "flight_38", "flight_45", "flight_46",
               "2026_07_21_gym/flight_22", "2026_07_21_gym/flight_125"]
    by_bare = {}
    for (s, f) in flights:
        by_bare.setdefault(f, []).append((s, f))

    resolved, unresolved = {}, []
    for name in FRAGILE:
        if "/" in name:
            s, f = name.split("/", 1)
            if (s, f) in set(flights):
                resolved[name] = (s, f)
            else:
                alt = by_bare.get(f, [])
                unresolved.append((name, "not present as given",
                                   f"flight id '{f}' exists in "
                                   + (", ".join(a[0] for a in alt) if alt
                                      else "no session")))
        else:
            cands = by_bare.get(name, [])
            if len(cands) == 1:
                resolved[name] = cands[0]
            elif not cands:
                unresolved.append((name, "not present", "no flight with this id"))
            else:
                unresolved.append((name, "AMBIGUOUS",
                                   "exists in " + ", ".join(c[0] for c in cands)))

    print(f"  {len(resolved)} of {len(FRAGILE)} names resolved against the joined data")
    for name, key in resolved.items():
        print(f"    resolved  {name:<26} -> {key[0]}/{key[1]}  "
              f"cls={cls_of[key]}  included={'yes' if key in included else 'NO'}")
    if unresolved:
        print(f"\n  {len(unresolved)} name(s) did NOT resolve - reported, not skipped:")
        for name, why, detail in unresolved:
            print(f"    UNRESOLVED  {name:<26} {why:<20} ({detail})")

    def edge_dist(value, origin, d):
        """Distance to the nearest cell boundary along one axis."""
        off = (value - origin) % d
        return min(off, d - off)

    for cls in CLASSES:
        d = smallest[cls]
        print(f"\n  --- {cls} ---")
        if d is None:
            print(f"    no D on the tested list clears 94.2%; nothing to report at "
                  f"a passing cell size")
            continue
        members = [(n, k) for n, k in resolved.items()
                   if cls_of[k] == cls and k in included]
        if not members:
            print(f"    none of the named flights is included in {cls} at "
                  f"D={d} mm")
            continue
        print(f"    at D={d} mm  (grid {math.ceil(ENV_H_MM/d)}x{math.ceil(ENV_W_MM/d)})")
        print(f"    {'flight':<30}{'match':>7}{'ref dY':>10}{'ref dZ':>10}"
              f"{'pred dY':>10}{'pred dZ':>10}")
        for name, k in sorted(members):
            cy_r, cz_r = ref[k]
            cy_p, cz_p = pred[k]
            n_cols = math.ceil(ENV_W_MM / d)
            n_rows = math.ceil(ENV_H_MM / d)
            same = (cell_index(cy_r, y0, d, n_cols, True)
                    == cell_index(cy_p, y0, d, n_cols, False)
                    and cell_index(cz_r, 0.0, d, n_rows, True)
                    == cell_index(cz_p, 0.0, d, n_rows, False))
            print(f"    {k[0] + '/' + k[1]:<30}{'yes' if same else 'NO':>7}"
                  f"{edge_dist(cy_r, y0, d):>10.1f}{edge_dist(cz_r, 0.0, d):>10.1f}"
                  f"{edge_dist(cy_p, y0, d):>10.1f}{edge_dist(cz_p, 0.0, d):>10.1f}")
        print(f"    (distances are mm to the nearest cell boundary on each axis;"
              f" a small value means the point sits near an edge and flips easily)")

    # ---- error percentiles -------------------------------------------------
    print("\n" + "-" * 74)
    print("IN-PLANE CROSSING-POSITION ERROR MAGNITUDE (convergence)")
    print("-" * 74)
    pct_rows = []
    for cls in CLASSES:
        fl = sorted(f for f in included if cls_of[f] == cls)
        errs = [math.hypot(pred[f][0] - ref[f][0], pred[f][1] - ref[f][1]) for f in fl]
        rec = dict(cls=cls, window_ms=WINDOW[cls], n_included=len(errs),
                   median_mm=f"{percentile(errs, 0.50):.4f}",
                   p90_mm=f"{percentile(errs, 0.90):.4f}",
                   p95_mm=f"{percentile(errs, 0.95):.4f}",
                   max_mm=f"{max(errs):.4f}")
        pct_rows.append(rec)
        print(f"  {cls:<5} n={len(errs):<3} median={rec['median_mm']:>10}  "
              f"p90={rec['p90_mm']:>10}  p95={rec['p95_mm']:>10}  max={rec['max_mm']:>10}")

    # ---- write outputs -----------------------------------------------------
    print("\n" + "-" * 74)
    print("OUTPUTS")
    print("-" * 74)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    def write(name, rows_):
        p = next_free(OUT_DIR / name)
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows_[0].keys()))
            w.writeheader()
            w.writerows(rows_)
        print(f"  wrote {p.relative_to(ROOT)}  ({len(rows_)} rows)")

    write("zone_classification_raw.csv", raw_rows)
    write("zone_classification_summary.csv", summary_rows)
    write("y_offset_search.csv",
          [dict(y_offset_mm=f"{o:.0f}", n_inside=n) for o, n in search])
    write("zone_classification_by_phase.csv", phase_rows)
    write("crossing_error_percentiles.csv", pct_rows)

    # ---- figure ------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.grid(True, color="#dddddd", lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for cls in CLASSES:
        rs = sorted((r for r in summary_rows if r["cls"] == cls),
                    key=lambda r: int(r["D_mm"]))
        xs = [int(r["D_mm"]) for r in rs]
        ys = [float(r["match_fraction_mean"]) for r in rs]
        lo_ = [float(r["match_fraction_min"]) for r in rs]
        hi_ = [float(r["match_fraction_max"]) for r in rs]
        # Band spans the best and worst grid phase; the line is the mean over all
        # 100 phases, which is what a venue that cannot tune its wall will get.
        ax.fill_between(xs, lo_, hi_, color=CLASS_COLOUR[cls], alpha=0.16,
                        linewidth=0, zorder=2)
        ax.plot(xs, ys, marker="o", ms=5, lw=1.8, color=CLASS_COLOUR[cls],
                zorder=3, label=f"{cls} ({WINDOW[cls]} ms, n={included_by_class[cls]})")
    ax.axhline(THRESHOLD, color="#444444", ls="--", lw=1.4, zorder=2,
               label=f"{THRESHOLD*100:.1f}%")
    ax.set_xlabel("cell side length (mm)", fontsize=11)
    # Not "accuracy": this is agreement with the full-arc reference.
    ax.set_ylabel("fraction in same cell as reference", fontsize=11)
    ax.set_xscale("log")
    ax.set_xticks(CELL_SIZES_MM)
    ax.set_xticklabels([str(d) for d in CELL_SIZES_MM], fontsize=9)
    ax.tick_params(axis="y", labelsize=9)
    ax.set_ylim(0, 1.02)
    ax.legend(frameon=False, fontsize=9.5, loc="lower right")
    fig.tight_layout()
    fig_path = next_free(OUT_DIR / "figure_zone_classification.png")
    fig.savefig(fig_path, dpi=300, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {fig_path.relative_to(ROOT)}")
    print("\n  (no caption is burned into the image; caption text lives in the log)")

    print("\n" + "=" * 74)
    print("SUMMARY")
    print("=" * 74)
    print(f"  Y offset chosen        : {y0:.0f} mm "
          f"({best_n}/{len(ref)} included, +{best_n - n_at_zero} vs offset 0)")
    print(f"  excluded per class     : {excluded_by_class}")
    for cls in CLASSES:
        s = smallest[cls]
        print(f"  smallest D clearing 94.2%, {cls:<5}: "
              f"{str(s) + ' mm' if s else 'NONE of the tested sizes'}")
    print("=" * 74)


if __name__ == "__main__":
    main()
