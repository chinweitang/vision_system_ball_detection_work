"""Verification gate for the laptop positions re-run.

Recomputes hypot(cy_own - cy_ref, cz_own - cz_ref) from the new laptop sweep and
compares it against the ORIGINAL Pi sweep's stored position_error_mm, matched on
(session, flight, T_ms).

Read-only against both CSVs. Writes nothing.

MATCH KEY: (session, flight, T_ms), not (flight, T_ms). 32 flight ids exist in
both sessions, so a bare flight id would mis-pair 32 flights' worth of rows.

NOTE: every timing column in the laptop run is VOID and is not read here.
"""
import csv
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
NEW = ROOT / "results/regenerate_figures/04_zone_classification/pipeline_sweep_positions.csv"
OLD = ROOT / "results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv"

TOL_TIGHT = 1e-6
TOL_LOOSE = 1.0


def read(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    new, old = read(NEW), read(OLD)
    print(f"new (laptop) : {NEW.relative_to(ROOT)}  rows={len(new)}")
    print(f"old (Pi)     : {OLD.relative_to(ROOT)}  rows={len(old)}")

    old_by = {(r["session"], r["flight"], int(r["T_ms"])): r for r in old}
    new_by = {(r["session"], r["flight"], int(r["T_ms"])): r for r in new}
    print(f"unique keys  : new={len(new_by)}  old={len(old_by)}")

    missing = sorted(set(old_by) - set(new_by))
    extra = sorted(set(new_by) - set(old_by))
    print(f"\nkeys in Pi but not in laptop : {len(missing)}")
    for k in missing[:20]:
        print(f"   MISSING {k}")
    print(f"keys in laptop but not in Pi : {len(extra)}")
    for k in extra[:20]:
        print(f"   EXTRA   {k}")

    old_flights = {(r["session"], r["flight"]) for r in old}
    new_flights = {(r["session"], r["flight"]) for r in new}
    lost = sorted(old_flights - new_flights)
    print(f"\nflights in Pi but not in laptop: {len(lost)}")
    for f in lost:
        print(f"   LOST FLIGHT {f}")

    compared = tight = loose = 0
    both_blank = old_blank_new_ok = old_ok_new_blank = 0
    fails = []
    for k in sorted(set(old_by) & set(new_by)):
        o, n = old_by[k], new_by[k]
        o_err = o["position_error_mm"].strip()
        has_pos = n["cy_own"].strip() and n["cz_own"].strip() \
            and n["cy_ref"].strip() and n["cz_ref"].strip()
        if not o_err and not has_pos:
            both_blank += 1
            continue
        if not o_err and has_pos:
            old_blank_new_ok += 1
            continue
        if o_err and not has_pos:
            old_ok_new_blank += 1
            fails.append((k, float(o_err), None, None))
            continue
        recomputed = math.hypot(float(n["cy_own"]) - float(n["cy_ref"]),
                                float(n["cz_own"]) - float(n["cz_ref"]))
        stored = float(o_err)
        d = abs(recomputed - stored)
        compared += 1
        if d <= TOL_TIGHT:
            tight += 1
        if d <= TOL_LOOSE:
            loose += 1
        else:
            fails.append((k, stored, recomputed, d))

    print("\n" + "=" * 74)
    print("VERIFICATION GATE")
    print("=" * 74)
    print(f"  rows compared (both sides have values) : {compared}")
    print(f"  matching within {TOL_TIGHT:g} mm{'':14s}: {tight}"
          f"   ({100*tight/compared:.2f}%)" if compared else "")
    print(f"  matching within {TOL_LOOSE:g} mm{'':16s}: {loose}"
          f"   ({100*loose/compared:.2f}%)" if compared else "")
    print(f"  FAILING the {TOL_LOOSE:g} mm gate{'':14s}: {len(fails)}")
    print()
    print(f"  rows blank on BOTH sides (fit_failed)  : {both_blank}")
    print(f"  blank on Pi, present on laptop         : {old_blank_new_ok}")
    print(f"  present on Pi, blank on laptop         : {old_ok_new_blank}")
    print(f"  total rows accounted for               : "
          f"{compared + both_blank + old_blank_new_ok + old_ok_new_blank}")

    if fails:
        print("\n" + "-" * 74)
        print(f"EVERY ROW FAILING THE {TOL_LOOSE:g} mm GATE ({len(fails)})")
        print("-" * 74)
        print(f"  {'session':<16}{'flight':<14}{'T_ms':>6}"
              f"{'Pi stored':>14}{'laptop recomp':>16}{'delta':>12}")
        for (s, fl, t), stored, recomp, d in sorted(fails, key=lambda x: -(x[3] or 0)):
            if recomp is None:
                print(f"  {s:<16}{fl:<14}{t:>6}{stored:>14.4f}{'BLANK':>16}{'n/a':>12}")
            else:
                print(f"  {s:<16}{fl:<14}{t:>6}{stored:>14.4f}{recomp:>16.4f}{d:>12.4f}")
    else:
        print(f"\n  no row fails the {TOL_LOOSE:g} mm gate")

    # distribution of deltas, for context
    if compared:
        ds = []
        for k in sorted(set(old_by) & set(new_by)):
            o, n = old_by[k], new_by[k]
            if not o["position_error_mm"].strip() or not n["cy_own"].strip():
                continue
            ds.append(abs(math.hypot(float(n["cy_own"]) - float(n["cy_ref"]),
                                     float(n["cz_own"]) - float(n["cz_ref"]))
                          - float(o["position_error_mm"])))
        ds.sort()
        def q(p):
            return ds[min(len(ds) - 1, int(p * (len(ds) - 1)))]
        print(f"\n  delta distribution (mm): min {ds[0]:.3e}  median {q(0.5):.3e}  "
              f"p95 {q(0.95):.3e}  p99 {q(0.99):.3e}  max {ds[-1]:.3e}")

    print("\n  NOTE: no timing column from the laptop run was read or reported.")


if __name__ == "__main__":
    main()
