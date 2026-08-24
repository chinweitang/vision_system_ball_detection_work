"""Phase 2 prediction sweep for Model C ONLY, with the RANSAC robustifier disabled.

A re-run of existing analysis, not new data collection: same 158 flights, same
window grid, same pooled K, same held-out target, same leakage exclusion as
`src/stereo/trajectory_model_prediction_sweep_all_flights.py` - the single
difference is that each window is fitted by calling Model C's plain fit directly
instead of routing it through `ransac_fit`.

Why: `results/regenerate_figures/ransac_implementation.txt` established that the
existing sweep CSV carries NO plain variant at any window at or above the model's
`min_samples` (8 for Model C). Every fit there is a RANSAC fit, so the file
supports no plain-vs-RANSAC comparison at matched N. This produces the missing
arm.

Everything shared with the original is IMPORTED, not reimplemented. The one
exception is the leakage-exclusion block, which lives inline inside
`process_flight_phase2` rather than in a callable and so cannot be imported
without either running RANSAC or editing that file (read-only per the brief).
That block is copied verbatim and protected by `_assert_leakage_block_unchanged`,
which re-reads the original at run time and STOPs if the source has drifted.

Reads (read-only): the two source modules, pooled_k.txt, per-flight calibration
and tracks, and the RANSAC sweep CSV (as the reference population and window
grid). Writes ONLY under results/regenerate_figures/plain_drag_sweep/. Never
touches prediction_sweep_all_flights.csv.

STOP conditions:
  - the flight population that yields rows is not exactly 158
  - that population is not the same set of flights as the RANSAC sweep's
  - any flight's window grid differs from the RANSAC sweep's grid for that flight
  - the copied leakage-exclusion block no longer matches the original source
  - --full is requested without --i-approve-the-projection

Usage:
    python src/regen_2class/plain_drag_sweep.py                 # 3-flight pilot, then stops
    python src/regen_2class/plain_drag_sweep.py --pilot 5       # larger pilot
    python src/regen_2class/plain_drag_sweep.py --full --i-approve-the-projection
    python src/regen_2class/plain_drag_sweep.py --full --i-approve-the-projection --parallel

The full run is SERIAL by default. It takes minutes, and a worker pool buys back
only those minutes while adding swallowed-worker-exception and partial-write
failure modes that cost more to diagnose than they save.
"""

import argparse
import csv
import pathlib
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.stereo.all_flights_common import (  # noqa: E402
    enumerate_eligible_flights, load_session_calib, g_fixed_for, build_corrected_track,
    load_final_point_targets,
)
from src.stereo.label_vs_detection import triangulate  # noqa: E402
from src.stereo.trajectory_fit import build_model_fit_predict  # noqa: E402
# main() is behind an __main__ guard in this module, so importing runs nothing.
from src.stereo.trajectory_model_prediction_sweep_all_flights import (  # noqa: E402
    load_pooled_k, target_time_sec,
)

MODEL = "C"  # fixed gravity + quadratic drag, k fixed at the pooled Phase 1 value

SWEEP_CSV = ROOT / ("results/trajectory_fit_comparison/all_flights/phase2/"
                    "prediction_sweep_all_flights.csv")
ORIGINAL_SRC = ROOT / "src/stereo/trajectory_model_prediction_sweep_all_flights.py"
OUT_DIR = ROOT / "results/regenerate_figures/plain_drag_sweep"
OUT_CSV = OUT_DIR / "plain_drag_sweep.csv"
OUT_SUMMARY = OUT_DIR / "plain_drag_sweep_summary.txt"

EXPECTED_FLIGHTS = 158

# Lines 129-136 of ORIGINAL_SRC, copied verbatim. See module docstring for why a
# copy rather than an import, and _assert_leakage_block_unchanged for the guard.
LEAKAGE_BLOCK_LINES = (129, 136)
LEAKAGE_BLOCK_EXPECTED = """\
    # exclude any fit pair that coincides with the target's own frames (avoid leakage)
    keep_idx = [i for i, fr in enumerate(frames) if fr != f0]
    if len(keep_idx) < 3:
        return dict(session=session, flight=flight_id, status="skipped",
                    reason=f"only {len(keep_idx)} fit points after excluding target frame")
    frames = [frames[i] for i in keep_idx]
    t = t[np.array(keep_idx)]
    xyz = xyz[np.array(keep_idx)]"""


def stop(msg):
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def _assert_leakage_block_unchanged():
    """The leakage exclusion below is a verbatim copy of the original's inline
    block. If the original changes, this copy is silently wrong - so check."""
    lines = ORIGINAL_SRC.read_text(encoding="utf-8").splitlines()
    a, b = LEAKAGE_BLOCK_LINES
    actual = "\n".join(lines[a - 1:b])
    if actual != LEAKAGE_BLOCK_EXPECTED:
        stop(f"the leakage-exclusion block at {ORIGINAL_SRC.name} lines {a}-{b} no "
             f"longer matches the copy in this script.\n\n"
             f"--- original now reads ---\n{actual}\n\n"
             f"--- this script copied ---\n{LEAKAGE_BLOCK_EXPECTED}\n\n"
             f"Reconcile them before trusting any output.")


def read_reference_grid():
    """The RANSAC sweep's population and per-flight window grid, from its CSV.

    Grid is taken from Model C's rows: the original appends a row for all three
    models at every N in its loop, so any model gives the same N set, and C is
    the model being reproduced here.
    """
    if not SWEEP_CSV.is_file():
        stop(f"reference sweep CSV not found: {SWEEP_CSV.relative_to(ROOT).as_posix()}")
    grid = {}
    with open(SWEEP_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["model"] != MODEL:
                continue
            grid.setdefault((r["session"], r["flight"]), set()).add(int(r["N"]))
    return grid


def prepare_flight(session, flight_id, targets):
    """Everything up to (but not including) the window loop, matching
    process_flight_phase2's prep exactly. Returns a dict with status."""
    key = (session, flight_id)
    tgt = targets.get(key)
    if tgt is None or "cam0" not in tgt or "cam1" not in tgt:
        return dict(status="skipped", reason="missing final-point label (one or both cams)")

    try:
        K0, D0, K1, D1, P0, P1 = load_session_calib(session)
        g_fixed = g_fixed_for(session, flight_id)
        track = build_corrected_track(session, flight_id, K0, D0, K1, D1, P0, P1)
    except Exception as e:
        return dict(status="error", reason=f"exception: {e!r}")

    if track is None:
        return dict(status="skipped", reason="no corrected detector track")

    frames, t, xyz, t_anchor_ns = track

    u0, v0, f0 = tgt["cam0"]
    u1, v1, f1 = tgt["cam1"]
    target_xyz = triangulate(np.array([[u0, v0]]), np.array([[u1, v1]]),
                             K0, D0, K1, D1, P0, P1)[0]
    t_target = target_time_sec(session, flight_id, f0, f1, t_anchor_ns)
    if t_target is None:
        return dict(status="skipped", reason="target frame not found in timestamps.csv")

    # --- verbatim copy of ORIGINAL_SRC lines 129-136; see the guard above -----
    # exclude any fit pair that coincides with the target's own frames (avoid leakage)
    keep_idx = [i for i, fr in enumerate(frames) if fr != f0]
    if len(keep_idx) < 3:
        return dict(status="skipped",
                    reason=f"only {len(keep_idx)} fit points after excluding target frame")
    frames = [frames[i] for i in keep_idx]
    t = t[np.array(keep_idx)]
    xyz = xyz[np.array(keep_idx)]
    # --- end verbatim copy ---------------------------------------------------

    if t_target <= t[0]:
        return dict(status="skipped",
                    reason="target time is before the fit track starts -- not a forward prediction")

    return dict(status="ok", frames=frames, t=t, xyz=xyz, g_fixed=g_fixed,
                t_target=t_target, target_xyz=target_xyz)


def sweep_flight(session, flight_id, pooled_k, targets, recheck_guard=True):
    """Model C, plain fit, every window. Same N loop and lead-time rule as the
    original -- only the fit call differs.

    The leakage-block guard is re-asserted per flight, not just once at startup:
    a full run takes minutes, and the point of the guard is to stop the run if
    the original source drifts underneath it. Cost is one ~13 KB file read per
    flight, which is nothing next to a nonlinear fit per window.
    """
    if recheck_guard:
        _assert_leakage_block_unchanged()
    prep = prepare_flight(session, flight_id, targets)
    if prep["status"] != "ok":
        return dict(session=session, flight=flight_id, status=prep["status"],
                    reason=prep["reason"], rows=[], elapsed=0.0)

    frames, t, xyz = prep["frames"], prep["t"], prep["xyz"]
    t_target, target_xyz = prep["t_target"], prep["target_xyz"]
    fit_fn, predict_fn = build_model_fit_predict(MODEL, prep["g_fixed"], k_fixed=pooled_k)

    t_start = time.time()
    rows = []
    for N in range(3, len(frames) + 1):
        t_win, xyz_win = t[:N], xyz[:N]
        lead_time_ms = (t_target - t_win[-1]) * 1000.0
        if lead_time_ms <= 0:
            continue  # window has already reached/passed the target time
        try:
            # The plain fit, called directly. This is byte-for-byte the call the
            # original makes on its own sub-min_samples fallback path (lines
            # 91-92) -- the only change is that it now runs at EVERY window
            # rather than only below min_samples.
            params = fit_fn(t_win, xyz_win)
            pred = predict_fn(params, np.array([t_target]))[0]
            err = float(np.linalg.norm(pred - target_xyz))
            status, reason = "ok", ""
        except Exception as e:
            # The original catches only RuntimeError. Catching more here is
            # strictly safer for a batch re-run - without RANSAC's retry loop a
            # single bad window would otherwise abort the whole flight - and it
            # cannot change any value that does succeed.
            err, status, reason = float("nan"), "fit_failed", f"{type(e).__name__}"
        rows.append(dict(session=session, flight=flight_id, N=N,
                         lead_time_ms=lead_time_ms, error_mm=err,
                         status=status, reason=reason))

    return dict(session=session, flight=flight_id, status="ok", rows=rows,
                elapsed=time.time() - t_start, n_windows=len(rows))


def _worker(task):
    return sweep_flight(*task)


def report_fallout(results):
    """Name every enumerated flight that produced no rows, and the rule that
    dropped it. Printed on EVERY run, pass or fail: Figure D quotes 158, so the
    identity of the flights outside that 158 has to be on the record either way,
    not only when a gate trips."""
    fallout = [(r["session"], r["flight"], r["status"], r.get("reason", "?"))
               for r in results if r["status"] != "ok" or not r["rows"]]
    print(f"\nFALLOUT: {len(results)} enumerated - {len(fallout)} dropped = "
          f"{len(results) - len(fallout)} producing rows")
    for s, f, st, why in sorted(fallout):
        print(f"    {s}/{f}  [{st}]  {why}")
    return fallout


def check_population_and_grid(results, reference_grid):
    """Both STOPs: population identity and per-flight window grid."""
    produced = {(r["session"], r["flight"]) for r in results
                if r["status"] == "ok" and r["rows"]}

    if len(produced) != EXPECTED_FLIGHTS:
        stop(f"flight population is {len(produced)}, expected {EXPECTED_FLIGHTS}. "
             f"See the FALLOUT list above for which flights dropped and why.")

    ref_flights = set(reference_grid)
    if produced != ref_flights:
        only_here = sorted(produced - ref_flights)
        only_ref = sorted(ref_flights - produced)
        stop(f"the flight population differs from the RANSAC sweep's, despite both "
             f"being {EXPECTED_FLIGHTS} flights.\n"
             f"  only in this run ({len(only_here)}): {only_here[:10]}\n"
             f"  only in the RANSAC sweep ({len(only_ref)}): {only_ref[:10]}")

    diffs = []
    for r in results:
        if r["status"] != "ok" or not r["rows"]:
            continue
        key = (r["session"], r["flight"])
        mine = {row["N"] for row in r["rows"]}
        theirs = reference_grid[key]
        if mine != theirs:
            diffs.append((key, sorted(mine - theirs), sorted(theirs - mine)))
    if diffs:
        stop(f"the window grid differs from the RANSAC sweep's on "
             f"{len(diffs)} flight(s). NOT aligning them silently:\n"
             + "\n".join(f"    {s}/{f}: extra here {extra[:8]}, missing here {miss[:8]}"
                         for (s, f), extra, miss in diffs[:15]))

    print(f"POPULATION PASS: {len(produced)} flights, identical set to the RANSAC sweep")
    print(f"GRID PASS: per-flight window grid matches on all {len(produced)} flights")


def write_outputs(results, pooled_k, timing_note):
    rows = [row for r in results if r["status"] == "ok" for row in r["rows"]]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["session", "flight", "N", "lead_time_ms", "error_mm", "status", "reason"])
        for r in rows:
            w.writerow([r["session"], r["flight"], r["N"], f"{r['lead_time_ms']:.2f}",
                        "" if np.isnan(r["error_mm"]) else f"{r['error_mm']:.4f}",
                        r["status"], r["reason"]])

    n_ok = sum(1 for r in rows if r["status"] == "ok")
    n_fail = sum(1 for r in rows if r["status"] == "fit_failed")
    flights = {(r["session"], r["flight"]) for r in rows}
    lines = [
        "PLAIN (NON-RANSAC) MODEL C PREDICTION SWEEP",
        "=" * 70,
        "",
        "Model C = fixed gravity + quadratic drag, k fixed at the pooled Phase 1 value.",
        f"pooled K = {pooled_k:.6e} 1/mm",
        "",
        "Identical to the RANSAC Phase 2 sweep in population, window grid, pooled K,",
        "held-out target and leakage exclusion. The ONLY difference is that each",
        "window is fitted by calling Model C's plain fit directly instead of through",
        "ransac_fit, so no point is ever rejected and the residual is over all points.",
        "",
        f"flights: {len(flights)}",
        f"rows   : {len(rows)}  ({n_ok} ok, {n_fail} fit_failed)",
        "",
        timing_note,
        "",
        f"Reference (untouched): {SWEEP_CSV.relative_to(ROOT).as_posix()}",
        f"Output               : {OUT_CSV.relative_to(ROOT).as_posix()}",
    ]
    OUT_SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {OUT_CSV.relative_to(ROOT).as_posix()}")
    print(f"wrote {OUT_SUMMARY.relative_to(ROOT).as_posix()}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pilot", type=int, default=3, help="pilot flight count (default 3)")
    ap.add_argument("--full", action="store_true", help="run the full population")
    ap.add_argument("--i-approve-the-projection", action="store_true",
                    help="required alongside --full; confirms the pilot projection was reviewed")
    ap.add_argument("--parallel", action="store_true",
                    help="opt in to the worker pool; serial is the default for --full")
    opts = ap.parse_args()

    _assert_leakage_block_unchanged()
    print(f"leakage-block guard PASS: {ORIGINAL_SRC.name} lines "
          f"{LEAKAGE_BLOCK_LINES[0]}-{LEAKAGE_BLOCK_LINES[1]} unchanged")

    pooled_k = load_pooled_k()
    print(f"pooled K (same value as the RANSAC sweep): {pooled_k:.6e} 1/mm")

    targets = load_final_point_targets()
    flights = enumerate_eligible_flights()
    reference_grid = read_reference_grid()
    ref_windows = {k: len(v) for k, v in reference_grid.items()}
    total_ref_windows = sum(ref_windows.values())
    print(f"{len(flights)} eligible flights enumerated; RANSAC sweep covers "
          f"{len(reference_grid)} flights / {total_ref_windows} windows")

    if not opts.full:
        # Spread the pilot across the ordering rather than taking the first N,
        # since runtime scales with each flight's window count.
        n = max(1, min(opts.pilot, len(flights)))
        picks = [flights[round(i * (len(flights) - 1) / max(1, n - 1))] for i in range(n)] \
            if n > 1 else [flights[0]]
        print(f"\nPILOT: {n} flight(s) - {', '.join(f'{s}/{f}' for s, f in picks)}")

        per_flight, per_window = [], []
        for s, f in picks:
            r = sweep_flight(s, f, pooled_k, targets)
            nw = len(r["rows"])
            if r["status"] != "ok" or nw == 0:
                print(f"  {s}/{f}: {r['status']} - {r.get('reason', 'no windows')}")
                continue
            fails = sum(1 for x in r["rows"] if x["status"] == "fit_failed")
            print(f"  {s}/{f}: {r['elapsed']:.1f}s over {nw} windows "
                  f"({1000 * r['elapsed'] / nw:.0f} ms/window, {fails} fit_failed)")
            per_flight.append(r["elapsed"])
            per_window.append(r["elapsed"] / nw)

        if not per_window:
            stop("no pilot flight produced any window - cannot project a runtime")

        mean_pw = sum(per_window) / len(per_window)
        mean_pf = sum(per_flight) / len(per_flight)
        naive = mean_pf * EXPECTED_FLIGHTS
        # Better projection: the RANSAC CSV already tells us each flight's exact
        # window count, so scale by total windows rather than by flight count.
        weighted = mean_pw * total_ref_windows
        print(f"\n  mean {mean_pf:.1f}s/flight, {1000 * mean_pw:.0f} ms/window")
        print(f"  PROJECTED TOTAL, serial:")
        print(f"    by flight count  : {naive:.0f}s ({naive / 60:.1f} min)  "
              f"[{mean_pf:.1f}s x {EXPECTED_FLIGHTS} flights]")
        print(f"    by window count  : {weighted:.0f}s ({weighted / 60:.1f} min)  "
              f"[{1000 * mean_pw:.0f} ms x {total_ref_windows} windows]  <-- more reliable")
        import os
        ncpu = max(1, (os.cpu_count() or 2) - 2)
        print(f"    parallel ({ncpu} workers, as the original does): "
              f"~{weighted / ncpu:.0f}s (~{weighted / ncpu / 60:.1f} min)")
        print("\nSTOPPING for approval. Re-run with:")
        print("    python src/regen_2class/plain_drag_sweep.py --full --i-approve-the-projection")
        return 0

    if not opts.i_approve_the_projection:
        stop("--full requires --i-approve-the-projection. Run the pilot first and "
             "review the projected total.")

    mode = "parallel" if opts.parallel else "serial"
    print(f"\nFULL RUN over {len(flights)} enumerated flights ({mode})...")
    t0 = time.time()
    results = []
    if opts.parallel:
        tasks = [(s, f, pooled_k, targets) for s, f in flights]
        with ProcessPoolExecutor() as ex:
            futures = [ex.submit(_worker, t) for t in tasks]
            for done, fut in enumerate(as_completed(futures), 1):
                results.append(fut.result())
                if done % 20 == 0 or done == len(tasks):
                    print(f"  {done}/{len(tasks)} flights processed "
                          f"({time.time() - t0:.0f}s elapsed)")
    else:
        # Serial is the default: this run is minutes, and a worker pool adds a
        # failure mode (swallowed worker exceptions, partial writes) that costs
        # more to debug than the wall-clock it saves. Correctness is the
        # constraint here, not speed.
        for i, (s, f) in enumerate(flights, 1):
            results.append(sweep_flight(s, f, pooled_k, targets))
            if i % 20 == 0 or i == len(flights):
                print(f"  {i}/{len(flights)} flights processed "
                      f"({time.time() - t0:.0f}s elapsed)")
    elapsed = time.time() - t0

    report_fallout(results)
    check_population_and_grid(results, reference_grid)
    n_windows = sum(len(r["rows"]) for r in results if r["status"] == "ok")
    timing_note = (f"runtime: {elapsed:.0f}s ({elapsed / 60:.1f} min) {mode}, "
                   f"{n_windows} windows fitted")
    write_outputs(results, pooled_k, timing_note)
    print(f"\n{timing_note}")
    print("prediction_sweep_all_flights.csv not touched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
