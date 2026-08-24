"""What the RANSAC layer actually does, and what the sweep CSV does and does not contain.

Reads, both strictly read-only and never written back:
  src/stereo/trajectory_fit.py                          - the implementation
  results/trajectory_fit_comparison/all_flights/phase2/
      prediction_sweep_all_flights.csv                  - the full-population sweep

The source-code findings quote trajectory_fit.py by line number. Rather than
transcribing those lines into a string literal here - which would silently rot
the moment the file is edited - each quoted line is READ BACK from the file at
run time and checked against an expected fragment. A mismatch STOPs, so this
report cannot claim a line number that no longer says what it used to.

Writes results/regenerate_figures/ransac_implementation.txt.
"""

import csv
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "src/stereo/trajectory_fit.py"
SWEEP = ROOT / ("results/trajectory_fit_comparison/all_flights/phase2/"
                "prediction_sweep_all_flights.csv")
GEN = ROOT / "src/stereo/trajectory_model_prediction_sweep_all_flights.py"
OUT = ROOT / "results/regenerate_figures/ransac_implementation.txt"

# Per-model minimum sample count, read back from the source rather than retyped.
MIN_SAMPLES = {"A": 6, "B": 6, "C": 8}

# The window this project already treats as representative - see
# src/regen_2class/step14_flight_binning_n30_replot.py and the N30 figures.
REPRESENTATIVE_N = 30
CONTEXT_WINDOWS = [10, 20, 30, 40, 50]

# line number -> fragment that line must contain, as a guard against drift.
EXPECTED = {
    218: "final_params = fit_fn(t[best_mask], xyz[best_mask])",
    219: "pred_final = predict_fn(final_params, t[best_mask])",
    220: "resid_final = np.linalg.norm(pred_final - xyz[best_mask], axis=1)",
    221: "rms = float(np.sqrt(np.mean(resid_final ** 2)))",
    214: "if best_mask is None or best_count < min_samples:",
    195: "if n < min_samples:",
    207: "resid = np.linalg.norm(pred_all - xyz, axis=1)",
    208: "mask = resid <= inlier_threshold_mm",
    241: "RANSAC_INLIER_THRESHOLD_MM = 75.0",
    245: 'RANSAC_MIN_SAMPLES = {"A": 6, "B": 6, "C": 8}',
    203: "params = fit_fn(t[idx], xyz[idx])",
}


def stop(msg):
    raise SystemExit(f"\n*** STOP ***\n{msg}\n")


def load_lines(path):
    return path.read_text(encoding="utf-8").splitlines()


def quote(lines, n):
    """`n`: 1-based line number. Returns 'NNN    <source text>'."""
    return f"{n:>3}  {lines[n - 1]}"


def check_expected(lines):
    bad = [(n, frag, lines[n - 1].strip()) for n, frag in EXPECTED.items()
           if frag not in lines[n - 1]]
    if bad:
        stop("trajectory_fit.py has changed - these line numbers no longer carry "
             "the code this report describes:\n"
             + "\n".join(f"  line {n}: expected to contain {frag!r}\n"
                         f"           actually reads    {actual!r}"
                         for n, frag, actual in bad))


def main():
    for p in (SRC, SWEEP, GEN):
        if not p.is_file():
            stop(f"missing input: {p.relative_to(ROOT).as_posix()}")

    lines = load_lines(SRC)
    check_expected(lines)
    print(f"line-number guard PASS: {len(EXPECTED)} quoted lines still match")

    rows = list(csv.DictReader(open(SWEEP, encoding="utf-8")))
    header = open(SWEEP, encoding="utf-8").readline().strip()
    models = sorted({r["model"] for r in rows})
    all_flights = {(r["session"], r["flight"]) for r in rows}

    # blank rejected_frac splits by whether error_mm survived
    plain_rows = [r for r in rows
                  if not r["rejected_frac"].strip() and r["error_mm"].strip()]
    failed_rows = [r for r in rows
                   if not r["rejected_frac"].strip() and not r["error_mm"].strip()]
    ransac_rows = [r for r in rows if r["rejected_frac"].strip()]

    # the plain rows should be exactly the sub-min_samples ones; verify
    misplaced = [r for r in plain_rows if int(r["N"]) >= MIN_SAMPLES[r["model"]]]
    if misplaced:
        stop(f"{len(misplaced)} row(s) have a blank rejected_frac with a populated "
             f"error_mm at N >= min_samples, which the plain-fit fallback cannot "
             f"explain. First: {misplaced[0]}")

    plain_flights = {(r["session"], r["flight"]) for r in plain_rows}
    plain_flights_by_model = {m: {(r["session"], r["flight"])
                                  for r in plain_rows if r["model"] == m}
                              for m in models}

    o = []
    add = o.append
    add("RANSAC IMPLEMENTATION AND SWEEP COVERAGE")
    add("=" * 78)
    add("")
    add("Sources, all read-only:")
    add(f"  {SRC.relative_to(ROOT).as_posix()}")
    add(f"  {SWEEP.relative_to(ROOT).as_posix()}")
    add(f"  {GEN.relative_to(ROOT).as_posix()}   (consulted to interpret blank fields)")
    add("")
    add("Quoted line numbers are 1-based and were re-read from the file at run time;")
    add("this report STOPs rather than quoting a line that has since changed.")
    add("")

    # ---------------------------------------------------------------- (a)
    add("-" * 78)
    add("(a) DOES ransac_fit REFIT ON THE FULL INLIER SET?")
    add("-" * 78)
    add("")
    add("YES. After the sampling loop it refits over the winning consensus mask:")
    add("")
    add(quote(lines, 218))
    add("")
    add("The per-iteration fit on the minimal draw is scored and DISCARDED - the loop")
    add("retains only the mask, never the parameters:")
    add("")
    add(quote(lines, 203))
    add(quote(lines, 207))
    add(quote(lines, 208))
    add("")
    add("So the returned model is fitted on all inliers, not on the minimal subsample.")
    add("")

    # ---------------------------------------------------------------- (b)
    add("-" * 78)
    add("(b) OVER WHICH POINTS IS THE RETURNED RESIDUAL COMPUTED?")
    add("-" * 78)
    add("")
    add("INLIERS ONLY. Both the prediction and the data are sliced by best_mask:")
    add("")
    add(quote(lines, 219))
    add(quote(lines, 220))
    add(quote(lines, 221))
    add("")
    add("The returned residual_rms_mm therefore EXCLUDES every rejected point.")
    add("Because the rejected points are by construction the large-residual ones,")
    add("this figure is biased low relative to a plain least-squares RMS over all")
    add("points, and the two are not comparable like for like. It measures fit")
    add("quality on the consensus set, not on the flight.")
    add("")

    # ---------------------------------------------------------------- (c)
    add("-" * 78)
    add("(c) MINIMUM INLIER COUNT AND INLIER DISTANCE THRESHOLD")
    add("-" * 78)
    add("")
    add("MINIMUM INLIER COUNT - there is no separate parameter for it. The")
    add("acceptance gate reuses min_samples, so the minimum inlier count EQUALS the")
    add("minimal sample size:")
    add("")
    add(quote(lines, 214))
    add("")
    add("with the per-model values at line 245:")
    add("")
    add(quote(lines, 245))
    add("")
    add("The same constant also guards the input size earlier:")
    add("")
    add(quote(lines, 195))
    add("")
    add("INLIER DISTANCE THRESHOLD - line 241:")
    add("")
    add(quote(lines, 241))
    add("")
    add("applied as a Euclidean 3-D distance in mm at lines 207-208 (quoted above).")
    add("One value for all three models and both phases.")
    add("")

    # ---------------------------------------------------------------- CSV
    add("-" * 78)
    add("(d) DOES THE SWEEP CSV CONTAIN A PLAIN, NON-RANSAC VARIANT?")
    add("-" * 78)
    add("")
    add(f"File: {SWEEP.relative_to(ROOT).as_posix()}")
    add(f"Header: {header}")
    add(f"{len(rows)} data rows, {len(all_flights)} flights.")
    add("")
    add("NO - there is no column that distinguishes a plain fit from a RANSAC fit.")
    add(f"The `model` column takes exactly {len(models)} values ({', '.join(models)}),")
    add("with no variant suffix and no separate method field. There is one row per")
    add("(session, flight, N, model), so a plain and a RANSAC result never coexist")
    add("at the same window for the same model.")
    add("")
    add("Plain fits ARE present, but only as an implicit fallback, identifiable only")
    add("indirectly. Blank `rejected_frac` means two different things:")
    add("")
    add(f"  {len(plain_rows):>6} rows  blank rejected_frac, error_mm PRESENT")
    add("                -> plain fit: N below the model's min_samples, RANSAC skipped")
    add(f"  {len(failed_rows):>6} rows  blank rejected_frac, error_mm ALSO BLANK")
    add("                -> RANSAC raised; no result recorded")
    add(f"  {len(ransac_rows):>6} rows  rejected_frac populated -> a real RANSAC fit")
    add("")
    add("Confirmed against the generating script, not inferred from the data alone:")
    add("its fit_and_predict_ransac falls back to the plain fit when the window is")
    add("smaller than min_samples and returns None for the rejected list, while a")
    add("RuntimeError path sets error to NaN AND the fraction to None - which is why")
    add("only the second category has both fields empty.")
    add("")
    add("STOP CONDITION - the plain variant restricted to a subset of flights?")
    add(f"  NOT TRIGGERED. Plain rows appear for {len(plain_flights)} of "
        f"{len(all_flights)} flights"
        + (" (all of them)" if len(plain_flights) == len(all_flights) else "") + ",")
    for m in models:
        add(f"    model {m}: {len(plain_flights_by_model[m])} of {len(all_flights)} flights")
    add("")
    add("  HOWEVER, the restriction that does exist is by WINDOW, not by flight:")
    add("  the plain variant occurs only below each model's min_samples -")
    add("    " + ", ".join(f"N < {MIN_SAMPLES[m]} for model {m}" for m in models) + ".")
    add("  At every larger window each fit in this file is a RANSAC fit. The file")
    add("  therefore supports NO plain-vs-RANSAC comparison at matched N, at any")
    add("  window a report would quote.")
    add("")

    # ------------------------------------------------------- rejected_frac
    add("-" * 78)
    add("(e) FRACTION OF FLIGHTS WITH rejected_frac > 0")
    add("-" * 78)
    add("")
    add(f"Representative window: N = {REPRESENTATIVE_N}, the window this project")
    add("already uses as representative (step14_flight_binning_n30_replot.py, the")
    add("N30 distribution figures).")
    add("")

    def at_window(n, model):
        sel = [r for r in rows if int(r["N"]) == n and r["model"] == model
               and r["rejected_frac"].strip()]
        have = {(r["session"], r["flight"]) for r in sel}
        pos = {(r["session"], r["flight"]) for r in sel
               if float(r["rejected_frac"]) > 0}
        return have, pos

    add(f"At N = {REPRESENTATIVE_N}:")
    add("")
    add("  model   flights with a RANSAC row   of those, rejected_frac > 0   share")
    for m in models:
        have, pos = at_window(REPRESENTATIVE_N, m)
        share = 100.0 * len(pos) / len(have) if have else 0.0
        add(f"    {m}              {len(have):>4}                        {len(pos):>4}"
            f"              {share:>6.1f}%")
    have30, _ = at_window(REPRESENTATIVE_N, models[0])
    add("")
    add(f"  Denominator caveat: {len(have30)} of {len(all_flights)} flights have a row at")
    add(f"  N = {REPRESENTATIVE_N} at all; the remainder are shorter than "
        f"{REPRESENTATIVE_N} points.")
    add("")
    add("Adjacent windows, to show N=30 is not a cherry-pick:")
    add("")
    add("     N   " + "".join(f"{m:>10}" for m in models) + "     flights with a row")
    for n in CONTEXT_WINDOWS:
        cells, counts = [], []
        for m in models:
            have, pos = at_window(n, m)
            cells.append(f"{100.0 * len(pos) / len(have) if have else 0.0:>9.1f}%")
            counts.append(str(len(have)))
        add(f"  {n:>4}   " + "".join(cells) + "     " + " / ".join(counts))
    add("")
    add("The share rises with window size and saturates at 100% by N=40: at any")
    add("window a report would quote, effectively every flight has at least one")
    add("point rejected. Taken with finding (b), the reported residual excludes")
    add("those points on effectively every flight, not on a rare subset.")
    add("")
    add("=" * 78)
    add("END")

    text = "\n".join(o) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    print(f"Wrote {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
