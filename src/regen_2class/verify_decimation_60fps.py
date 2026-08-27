"""Item-10 regression gate: the 60 fps arm must reproduce the existing sweep.

Compares position_error_mm in the frozen-detection 60 fps arm against the
existing results/pi_benchmarking/.../pipeline_sweep_raw.csv, matched on
(session, flight, T_ms).

This is the test of whether reading the frozen per-camera detection CSVs is
equivalent to running detect_flight_threaded inline. If it passes, those CSVs
are demonstrably what the inline detector produces.

Read-only. Writes nothing. Reads no timing column.
"""
import csv
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
NEW = ROOT / "results/regenerate_figures/05_framerate_decimation/decimation_60fps.csv"
OLD = ROOT / "results/pi_benchmarking/02_pi_pipeline_sweep_parallel_detection/pipeline_sweep_raw.csv"

TOL_TIGHT = 1e-6
TOL_LOOSE = 1.0
MAX_LOOSE_FAILS = 10


def read(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    new, old = read(NEW), read(OLD)
    print(f"new (60 fps, frozen detections): {NEW.relative_to(ROOT)}  rows={len(new)}")
    print(f"old (existing sweep)           : {OLD.relative_to(ROOT)}  rows={len(old)}")

    nb = {(r["session"], r["flight"], int(r["T_ms"])): r for r in new}
    ob = {(r["session"], r["flight"], int(r["T_ms"])): r for r in old}
    print(f"unique keys: new={len(nb)}  old={len(ob)}")

    missing = sorted(set(ob) - set(nb))
    extra = sorted(set(nb) - set(ob))
    print(f"\nkeys in old but not new : {len(missing)}")
    for k in missing[:20]:
        print(f"   MISSING {k}")
    print(f"keys in new but not old : {len(extra)}")
    for k in extra[:20]:
        print(f"   EXTRA   {k}")

    of = {(r["session"], r["flight"]) for r in old}
    nf = {(r["session"], r["flight"]) for r in new}
    print(f"flights old={len(of)}  new={len(nf)}  lost={len(of - nf)}")
    for f in sorted(of - nf):
        print(f"   LOST FLIGHT {f}")

    compared = tight = loose = 0
    both_blank = only_old = only_new = 0
    fails = []
    for k in sorted(set(ob) & set(nb)):
        o, n = ob[k], nb[k]
        oe, ne = o["position_error_mm"].strip(), n["position_error_mm"].strip()
        if not oe and not ne:
            both_blank += 1
            continue
        if not ne:
            only_old += 1
            fails.append((k, float(oe), None, None, o["status"], n["status"]))
            continue
        if not oe:
            only_new += 1
            fails.append((k, None, float(ne), None, o["status"], n["status"]))
            continue
        d = abs(float(ne) - float(oe))
        compared += 1
        if d <= TOL_TIGHT:
            tight += 1
        if d <= TOL_LOOSE:
            loose += 1
        else:
            fails.append((k, float(oe), float(ne), d, o["status"], n["status"]))

    print("\n" + "=" * 78)
    print("ITEM-10 REGRESSION GATE  (60 fps, frozen detections vs existing sweep)")
    print("=" * 78)
    print(f"  rows compared                    : {compared}")
    if compared:
        print(f"  matching within {TOL_TIGHT:g} mm          : {tight}  "
              f"({100*tight/compared:.2f}%)")
        print(f"  matching within {TOL_LOOSE:g} mm             : {loose}  "
              f"({100*loose/compared:.2f}%)")
    n_loose_fail = sum(1 for f in fails if f[3] is None or f[3] > TOL_LOOSE)
    print(f"  FAILING the {TOL_LOOSE:g} mm gate           : {n_loose_fail}")
    print()
    print(f"  blank on both (fit ineligible)   : {both_blank}")
    print(f"  present old, blank new           : {only_old}")
    print(f"  present new, blank old           : {only_new}")
    print(f"  total accounted for              : "
          f"{compared + both_blank + only_old + only_new}")

    if fails:
        print("\n" + "-" * 78)
        print(f"EVERY FAILING ROW ({len(fails)})")
        print("-" * 78)
        print(f"  {'session':<16}{'flight':<14}{'T':>5}{'old':>13}{'new':>13}"
              f"{'delta':>11}  status old/new")
        for (s, fl, t), oe, ne, d, os_, ns_ in sorted(
                fails, key=lambda x: -(x[3] if x[3] is not None else 9e9)):
            oes = f"{oe:.4f}" if oe is not None else "BLANK"
            nes = f"{ne:.4f}" if ne is not None else "BLANK"
            ds = f"{d:.4f}" if d is not None else "n/a"
            print(f"  {s:<16}{fl:<14}{t:>5}{oes:>13}{nes:>13}{ds:>11}  {os_}/{ns_}")
    else:
        print(f"\n  no row fails the {TOL_LOOSE:g} mm gate")

    if compared:
        ds = sorted(abs(float(nb[k]["position_error_mm"]) - float(ob[k]["position_error_mm"]))
                    for k in set(ob) & set(nb)
                    if ob[k]["position_error_mm"].strip() and nb[k]["position_error_mm"].strip())
        def q(p):
            return ds[min(len(ds) - 1, int(p * (len(ds) - 1)))]
        print(f"\n  delta distribution (mm): min {ds[0]:.3e}  median {q(0.5):.3e}  "
              f"p95 {q(0.95):.3e}  p99 {q(0.99):.3e}  max {ds[-1]:.3e}")

    print()
    if n_loose_fail > MAX_LOOSE_FAILS:
        print(f"  *** HARD STOP: {n_loose_fail} rows fail the {TOL_LOOSE:g} mm gate, "
              f"limit is {MAX_LOOSE_FAILS}. The frozen-detection substitution is NOT "
              f"validated; do not run the decimated arms. ***")
    else:
        print(f"  GATE PASS: {n_loose_fail} failures, limit {MAX_LOOSE_FAILS}. The frozen "
              f"per-camera CSVs reproduce the inline detector.")
    print("\n  No timing column was read or reported.")


if __name__ == "__main__":
    main()
