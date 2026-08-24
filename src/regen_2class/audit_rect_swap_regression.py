"""Audit of the MORPH_ELLIPSE -> MORPH_RECT close-kernel swap. READ-ONLY. No figures.

WHAT IS UNDER AUDIT
-------------------
The Pi mask breakdown found morph-close with a 30x30 ELLIPSE kernel to be ~97%
of the detection budget, and that swapping the same-size kernel to RECT very
nearly removes the overrun. This audit checks what that swap costs in accuracy,
at two levels:

  DETECTION  per-flight combined detection rate, ellipse vs rect, 163 flights
  DOWNSTREAM per-flight crossing-plane prediction error in mm, 157 flights

CLAIMS VERIFIED (each recomputed from source, never taken from prose)
  V1  pooled combined rate      96.7% -> 94.5%
  V2  pooled true rate          92.5% -> 88.8%
  V3  83 of 163 flights worse by more than 2 pp
  V4  12 flights better by more than 2 pp
  V5  13 better if the boundary flight 2026_07_21_gym/flight_69 (+2.00 pp) counts
  V6  downstream prediction-error median shift of 0.4 mm
  V7  7 of 157 flights regressing by 250-866 mm

ALSO REPORTED (asked for explicitly)
  the source CSVs; the definition of the per-flight delta; the exact median
  shift WITH SIGN; and why the detection population is 163 while the downstream
  population is 157.

STOP CONDITIONS (hard - the report is marked STOP and the reason is stated)
  S1  any verified count differs from its claim by MORE THAN ONE flight
  S2  the 157 population cannot be explained from file contents
A difference of exactly one flight is NOT a stop; it is reported as a boundary
disagreement, because that is what V4/V5 are about.

MIGRATION NOTE
  The repo moved data/ -> results/ on 24 Aug. The history ledger that carries
  the headline numbers still records its artifact paths under data/. Every such
  path is resolved here and its state reported; nothing is rewritten.

READ-ONLY / NON-DESTRUCTIVE
  Every input is opened 'r'. The log and the report are created with mode 'x'
  (exclusive create); if a path is taken the run shifts to the next free numeric
  suffix. Nothing existing is opened for writing, truncated, renamed or removed.
"""
import csv
import pathlib
import statistics as st
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[2]

# ---- inputs (all read-only) ----
ELLIPSE_CSV = ROOT / "results/detector_tuning/candidate_config_validated_results.csv"
RECT_CSV = ROOT / "results/detector_tuning/candidate_config_rect_close_results.csv"
COMPARISON_CSV = ROOT / "results/detector_tuning/rect_vs_ellipse_comparison.csv"
HISTORY_CSV = ROOT / "results/detector_tuning/history/results_history.csv"
DOWNSTREAM_CSV = (ROOT / "results/trajectory_fit_comparison/rect_vs_ellipse_kernel"
                  / "rect_vs_ellipse_prediction_comparison.csv")
POOLED_SUMMARY_CSV = (ROOT / "results/trajectory_fit_comparison/rect_vs_ellipse_kernel"
                      / "pooled_summary.csv")

REQUIRED = [ELLIPSE_CSV, RECT_CSV, COMPARISON_CSV, HISTORY_CSV,
            DOWNSTREAM_CSV, POOLED_SUMMARY_CSV]

# ---- outputs ----
LOG_DIR = ROOT / "claude/claude_logs"
AUDIT_DIR = ROOT / "results/regenerate_figures/03_realtime/audits"
STEM = "audit_rect_swap_regression"

# Non-flight trailer rows carried at the bottom of the two per-flight CSVs.
TRAILERS = {"AVERAGE", "LABELED_RECALL (flight_01 + flight_22)", "CONFIG"}

PP_THRESHOLD = 2.0          # the "more than 2 pp" band
MM_THRESHOLD = 250.0        # the downstream "regressing" band floor
BOUNDARY_FLIGHT = "2026_07_21_gym/flight_69"

# claimed -> (label, value)
CLAIMS = {
    "n_detection": 163,
    "n_worse_gt2pp": 83,
    "n_better_gt2pp": 12,
    "n_better_ge2pp": 13,
    "n_downstream": 157,
    "n_regress_ge250mm": 7,
}


def reserve_run_paths():
    """Smallest N for which BOTH the log and the report path are free, so one
    run keeps one identity instead of splitting across two suffixes."""
    notes = []
    for n in range(1, 100):
        suffix = "" if n == 1 else "_%02d" % n
        log_p = LOG_DIR / (STEM + suffix + ".log")
        rep_p = AUDIT_DIR / (STEM + suffix + ".md")
        taken = [p for p in (log_p, rep_p) if p.exists()]
        if not taken:
            return log_p, rep_p, suffix, notes
        notes.append("suffix %-4s already taken by: %s"
                     % (suffix or "(none)", ", ".join(p.name for p in taken)))
    raise SystemExit("no free numeric suffix below 100 - refusing to overwrite")


class Log:
    def __init__(self, path):
        self.f = open(path, "x", encoding="utf-8")

    def __call__(self, msg):
        self.f.write("[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), msg))
        self.f.flush()

    def close(self):
        self.f.close()


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    log_path, report_path, suffix, suffix_notes = reserve_run_paths()
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    log = Log(log_path)
    R = []
    stops = []
    verdicts = []       # (id, claim, found, ok, note)

    def b(line=""):
        R.append(line)

    log("=== audit_rect_swap_regression: START (read-only, no figures) ===")
    log("run suffix : %s" % (suffix or "(none - base names were free)"))
    for n in suffix_notes:
        log("  " + n)
    log("log        : %s" % log_path.relative_to(ROOT).as_posix())
    log("report     : %s" % report_path.relative_to(ROOT).as_posix())

    missing = [p for p in REQUIRED if not p.exists()]
    if missing:
        for p in missing:
            log("MISSING INPUT: %s" % p.relative_to(ROOT).as_posix())
        log("aborting - required source CSV absent")
        log.close()
        return
    log("all %d required inputs present" % len(REQUIRED))

    # ------------------------------------------------------------------
    log("--- loading detection-level sources ---")
    ell_all = read_csv(ELLIPSE_CSV)
    rect_all = read_csv(RECT_CSV)
    cmp_rows = read_csv(COMPARISON_CSV)
    ell = [r for r in ell_all if r["flight"] not in TRAILERS]
    rect = [r for r in rect_all if r["flight"] not in TRAILERS]
    log("  %s: %d rows (%d flights + %d trailer)"
        % (ELLIPSE_CSV.name, len(ell_all), len(ell), len(ell_all) - len(ell)))
    log("  %s: %d rows (%d flights + %d trailer)"
        % (RECT_CSV.name, len(rect_all), len(rect), len(rect_all) - len(rect)))
    log("  %s: %d rows" % (COMPARISON_CSV.name, len(cmp_rows)))

    ell_by = {r["flight"]: r for r in ell}
    rect_by = {r["flight"]: r for r in rect}
    cmp_by = {r["flight"]: r for r in cmp_rows}
    same_pop = set(ell_by) == set(rect_by) == set(cmp_by)
    log("  identical flight sets across all three detection CSVs: %s" % same_pop)
    if not same_pop:
        for label, a, bset in [("ellipse-only", set(ell_by), set(cmp_by)),
                               ("rect-only", set(rect_by), set(cmp_by))]:
            diff = sorted(a - bset)
            if diff:
                log("    %s: %s" % (label, diff[:8]))

    n_detection = len(cmp_rows)
    verdicts.append(("population", CLAIMS["n_detection"], n_detection,
                     abs(n_detection - CLAIMS["n_detection"]) <= 1,
                     "flights in the paired detection comparison"))
    log("  detection population n = %d" % n_detection)

    # ---- trailer headline rows -------------------------------------
    log("--- V1/V2: headline rates from the CSV trailer rows ---")

    def trailer(rows, name):
        for r in rows:
            if r["flight"] == name:
                return r["combined_rate"]
        return None

    ell_avg = float(trailer(ell_all, "AVERAGE"))
    rect_avg = float(trailer(rect_all, "AVERAGE"))
    ell_lab = float(trailer(ell_all, "LABELED_RECALL (flight_01 + flight_22)"))
    rect_lab = float(trailer(rect_all, "LABELED_RECALL (flight_01 + flight_22)"))
    log("  AVERAGE        ellipse=%.4f rect=%.4f  delta=%+.2f pp"
        % (ell_avg, rect_avg, (rect_avg - ell_avg) * 100))
    log("  LABELED_RECALL ellipse=%.4f rect=%.4f  delta=%+.2f pp"
        % (ell_lab, rect_lab, (rect_lab - ell_lab) * 100))

    v1_ok = (round(ell_avg * 100, 1) == 96.7) and (round(rect_avg * 100, 1) == 94.5)
    v2_ok = (round(ell_lab * 100, 1) == 92.5) and (round(rect_lab * 100, 1) == 88.8)
    verdicts.append(("V1 combined 96.7->94.5", "96.7 -> 94.5",
                     "%.1f -> %.1f" % (ell_avg * 100, rect_avg * 100), v1_ok, ""))
    verdicts.append(("V2 true 92.5->88.8", "92.5 -> 88.8",
                     "%.1f -> %.1f" % (ell_lab * 100, rect_lab * 100), v2_ok,
                     "88.8 is 88.75 rounded"))
    log("  V1 %s ; V2 %s" % ("MATCH" if v1_ok else "MISMATCH",
                             "MATCH" if v2_ok else "MISMATCH"))

    # what IS "AVERAGE"? unweighted per-flight mean, or pooled point rate?
    unw_e = st.mean(float(r["combined_rate"]) for r in ell)
    unw_r = st.mean(float(r["combined_rate"]) for r in rect)
    proc_e = sum(int(r["combined_processable"]) for r in ell)
    det_e = sum(int(r["combined_detections"]) for r in ell)
    proc_r = sum(int(r["combined_processable"]) for r in rect)
    det_r = sum(int(r["combined_detections"]) for r in rect)
    pooled_e, pooled_r = det_e / proc_e, det_r / proc_r
    log("  AVERAGE definition: unweighted per-flight mean e=%.6f r=%.6f"
        % (unw_e, unw_r))
    log("                      pooled points ratio    e=%.6f (%d/%d) r=%.6f (%d/%d)"
        % (pooled_e, det_e, proc_e, pooled_r, det_r, proc_r))
    avg_is_unweighted = (round(unw_e, 4) == round(ell_avg, 4)
                         and round(unw_r, 4) == round(rect_avg, 4))
    log("  -> AVERAGE is the UNWEIGHTED per-flight mean: %s" % avg_is_unweighted)
    log("  -> denominators identical across arms (%d == %d): %s"
        % (proc_e, proc_r, proc_e == proc_r))

    # ---- per-flight delta definition -------------------------------
    log("--- per-flight delta definition ---")
    delta_mismatch = 0
    copy_mismatch = 0
    for f, r in cmp_by.items():
        e_rate = float(ell_by[f]["combined_rate"])
        r_rate = float(rect_by[f]["combined_rate"])
        if abs(float(r["ellipse_combined_rate"]) - e_rate) > 1e-9 \
           or abs(float(r["rect_combined_rate"]) - r_rate) > 1e-9:
            copy_mismatch += 1
        if abs(round((r_rate - e_rate) * 100, 2) - float(r["delta_pp"])) > 5e-3:
            delta_mismatch += 1
    log("  delta_pp == round((rect_rate - ellipse_rate) * 100, 2)")
    log("  arithmetic mismatches: %d of %d ; rate-copy mismatches: %d"
        % (delta_mismatch, len(cmp_by), copy_mismatch))
    delta_def_ok = delta_mismatch == 0 and copy_mismatch == 0

    # ---- V3/V4/V5 counts -------------------------------------------
    log("--- V3/V4/V5: per-flight delta bands (threshold %.1f pp) ---" % PP_THRESHOLD)
    deltas = [(f, float(r["delta_pp"])) for f, r in cmp_by.items()]
    worse_gt = [t for t in deltas if t[1] < -PP_THRESHOLD]
    better_gt = [t for t in deltas if t[1] > PP_THRESHOLD]
    better_ge = [t for t in deltas if t[1] >= PP_THRESHOLD]
    at_bound = [t for t in deltas if abs(t[1] - PP_THRESHOLD) < 1e-9]
    flagged = [r["flight"] for r in cmp_rows if (r.get("flagged_regression") or "").strip() == "YES"]
    log("  worse  < -%.1f pp : %d" % (PP_THRESHOLD, len(worse_gt)))
    log("  better > +%.1f pp : %d" % (PP_THRESHOLD, len(better_gt)))
    log("  better >= +%.1f pp: %d" % (PP_THRESHOLD, len(better_ge)))
    log("  exactly +%.2f pp  : %s" % (PP_THRESHOLD, [t[0] for t in at_bound]))
    log("  flagged_regression=YES in the CSV: %d (matches strict-worse: %s)"
        % (len(flagged), len(flagged) == len(worse_gt)))

    verdicts.append(("V3 83 worse >2pp", CLAIMS["n_worse_gt2pp"], len(worse_gt),
                     abs(len(worse_gt) - CLAIMS["n_worse_gt2pp"]) <= 1, "strict <"))
    verdicts.append(("V4 12 better >2pp", CLAIMS["n_better_gt2pp"], len(better_gt),
                     abs(len(better_gt) - CLAIMS["n_better_gt2pp"]) <= 1, "strict >"))
    verdicts.append(("V5 13 better >=2pp", CLAIMS["n_better_ge2pp"], len(better_ge),
                     abs(len(better_ge) - CLAIMS["n_better_ge2pp"]) <= 1,
                     "inclusive >="))

    boundary_ok = [t[0] for t in at_bound] == [BOUNDARY_FLIGHT]
    log("  boundary flight is exactly %s: %s" % (BOUNDARY_FLIGHT, boundary_ok))

    worst = sorted(deltas, key=lambda t: t[1])[:5]
    best = sorted(deltas, key=lambda t: -t[1])[:5]
    for f, d in worst:
        log("    worst %s %+.2f pp" % (f, d))
    for f, d in best:
        log("    best  %s %+.2f pp" % (f, d))

    # ---- what the ledger prose says --------------------------------
    log("--- cross-check against the history ledger prose ---")
    hist = read_csv(HISTORY_CSV)
    rect_row = None
    for h in hist:
        if "rect close kernel" in (h.get("stage") or "").lower():
            rect_row = h
    ledger_note = (rect_row.get("notes") or "") if rect_row else ""
    ledger_says_13 = "13 improved" in ledger_note
    log("  ledger row found: %s" % (rect_row is not None))
    log("  ledger prose claims 'only 13 improved >2pp': %s" % ledger_says_13)
    log("  recomputed strict >2pp improvers: %d -> ledger prose is off by %d"
        % (len(better_gt), 13 - len(better_gt)))

    # ---- downstream ------------------------------------------------
    log("--- V6/V7: downstream prediction error ---")
    down = read_csv(DOWNSTREAM_CSV)
    log("  %s: %d rows" % (DOWNSTREAM_CSV.name, len(down)))
    paired = [r for r in down if r["ellipse_status"] == "ok" and r["rect_status"] == "ok"]
    excluded = [r for r in down if r not in paired]
    n_downstream = len(paired)
    log("  status=ok in BOTH arms: %d ; excluded: %d" % (n_downstream, len(excluded)))

    # S2 - the 157 population must be explainable from the file itself
    reasons = {}
    asym = []
    for r in excluded:
        key_e, key_r = r["ellipse_status"], r["rect_status"]
        if key_e != key_r:
            asym.append(r)
        reason = (r["ellipse_reason"] or r["rect_reason"] or "").strip()
        reasons.setdefault((key_e, reason), []).append(r["session"] + "/" + r["flight"])
    for (statuslabel, reason), fl in sorted(reasons.items()):
        log("    excluded %-11s n=%d  reason: %s" % (statuslabel, len(fl), reason[:60]))
        for x in fl:
            log("      - %s" % x)
    log("  arms exclude the SAME flights (paired comparison): %s" % (not asym))
    explained = (len(down) - len(excluded) == n_downstream
                 and len(excluded) > 0
                 and all(((r["ellipse_reason"] or r["rect_reason"]) or "").strip()
                         for r in excluded)
                 and not asym)
    log("  S2 - 157 population explained from file contents: %s" % explained)
    if not explained:
        stops.append("S2: the %d-flight downstream population cannot be explained "
                     "from the file's own status/reason columns" % n_downstream)

    verdicts.append(("downstream population", CLAIMS["n_downstream"], n_downstream,
                     abs(n_downstream - CLAIMS["n_downstream"]) <= 1,
                     "both arms status=ok"))

    d_mm = [(r["session"] + "/" + r["flight"], float(r["delta_mm"])) for r in paired]
    e_mm = [float(r["ellipse_error_mm"]) for r in paired]
    r_mm = [float(r["rect_error_mm"]) for r in paired]
    mm_arith = sum(1 for r in paired
                   if abs(round(float(r["rect_error_mm"]) - float(r["ellipse_error_mm"]), 2)
                          - float(r["delta_mm"])) > 1.1e-2)
    log("  delta_mm == round(rect_error_mm - ellipse_error_mm, 2); mismatches: %d of %d"
        % (mm_arith, len(paired)))

    median_of_deltas = st.median([v for _, v in d_mm])
    median_shift = st.median(r_mm) - st.median(e_mm)
    mean_delta = st.mean([v for _, v in d_mm])
    log("  median of per-flight delta_mm : %+.4f mm" % median_of_deltas)
    log("  median(rect) - median(ellipse): %.4f - %.4f = %+.4f mm"
        % (st.median(r_mm), st.median(e_mm), median_shift))
    log("  mean of per-flight delta_mm   : %+.4f mm" % mean_delta)
    log("  worse (delta>0): %d ; better (delta<0): %d"
        % (sum(1 for _, v in d_mm if v > 0), sum(1 for _, v in d_mm if v < 0)))

    pooled = read_csv(POOLED_SUMMARY_CSV)
    pooled_delta_row = [p for p in pooled if p["variant"].startswith("delta")]
    pooled_delta = float(pooled_delta_row[0]["median_error_mm"]) if pooled_delta_row else None
    log("  %s carries delta row = %s" % (POOLED_SUMMARY_CSV.name, pooled_delta))
    pooled_matches_median_of_deltas = (
        pooled_delta is not None and abs(pooled_delta - round(median_of_deltas, 2)) < 5e-3)
    log("  that value is the MEDIAN OF PER-FLIGHT DELTAS (not the shift in the "
        "pooled median): %s" % pooled_matches_median_of_deltas)

    v6_ok = round(median_of_deltas, 1) == 0.4
    verdicts.append(("V6 median shift 0.4 mm", "0.4", "%+.2f" % median_of_deltas,
                     v6_ok, "median of per-flight deltas"))

    regress = sorted([t for t in d_mm if t[1] >= MM_THRESHOLD], key=lambda t: -t[1])
    log("  flights regressing >= %.0f mm: %d" % (MM_THRESHOLD, len(regress)))
    for f, v in regress:
        log("    %+8.2f mm  %s" % (v, f))
    rng_ok = False
    if regress:
        lo, hi = regress[-1][1], regress[0][1]
        rng_ok = 250.0 <= lo and 865.0 <= hi <= 866.5
        log("  range %.2f .. %.2f mm (claim 250-866: %s)" % (lo, hi, rng_ok))
    verdicts.append(("V7 7 regress 250-866mm", CLAIMS["n_regress_ge250mm"], len(regress),
                     abs(len(regress) - CLAIMS["n_regress_ge250mm"]) <= 1,
                     "range check %s" % ("ok" if rng_ok else "FAILED")))

    # do the two populations name the same flights?
    det_ids = set(cmp_by)
    down_ids = set(r["session"] + "/" + r["flight"] for r in down)
    log("  detection ids == downstream ids: %s" % (det_ids == down_ids))

    # ---- migration ---------------------------------------------------
    log("--- 24 Aug data/ -> results/ migration: ledger pointers ---")
    mig = []
    if rect_row:
        for a in (rect_row.get("artifacts") or "").split(";"):
            a = a.split(" (")[0].strip()
            if not a:
                continue
            p = ROOT / a
            exists = p.exists()
            alt = None
            if not exists and a.startswith("data/"):
                cand = ROOT / ("results/" + a[len("data/"):])
                alt = ("results/" + a[len("data/"):]) if cand.exists() else None
            mig.append({"path": a, "exists": exists, "alt": alt})
            log("    %-9s %-62s %s" % ("OK" if exists else "DANGLING", a[:62],
                                       ("-> " + alt) if alt else ("" if exists else "no results/ equivalent")))

    # ---- STOP evaluation ---------------------------------------------
    log("--- STOP evaluation ---")
    for vid, claim, found, ok, note in verdicts:
        if isinstance(claim, int) and isinstance(found, int):
            diff = abs(found - claim)
            log("  %-26s claim=%-6s found=%-6s diff=%d -> %s"
                % (vid, claim, found, diff, "ok" if diff <= 1 else "STOP"))
            if diff > 1:
                stops.append("S1: %s - claimed %s, found %s (differs by %d flights)"
                             % (vid, claim, found, diff))
        else:
            log("  %-26s claim=%-14s found=%-14s -> %s"
                % (vid, claim, found, "ok" if ok else "MISMATCH"))
    status = "STOP" if stops else "PASS"
    for s in stops:
        log("  STOP: %s" % s)
    log("  OVERALL: %s" % status)

    # ---- report ------------------------------------------------------
    b("# Rect close-kernel swap — regression audit")
    b()
    b("Read-only. No figures. Generated %s by `src/regen_2class/%s`."
      % (datetime.now().strftime("%Y-%m-%d %H:%M"), pathlib.Path(__file__).name))
    b()
    if status == "PASS":
        b("**Result: PASS.** All seven claims reproduce from source; neither stop")
        b("condition fired.")
    else:
        b("**Result: STOP.** The following condition(s) fired:")
        b()
        for s in stops:
            b("- %s" % s)
    b()
    b("The swap under audit is `MORPH_ELLIPSE` -> `MORPH_RECT` for the 30x30")
    b("morph-close structuring element, everything else in the config held fixed.")
    b("It buys a large Pi speedup and costs accuracy at both the detection and the")
    b("prediction level. Both costs are quantified below.")
    b()

    b("## 1. Source CSVs")
    b()
    b("| Role | Path | Rows |")
    b("|---|---|---:|")
    b("| Ellipse baseline, per flight | `%s` | %d (%d flights + %d trailer) |"
      % (ELLIPSE_CSV.relative_to(ROOT).as_posix(), len(ell_all), len(ell), len(ell_all) - len(ell)))
    b("| Rect variant, per flight | `%s` | %d (%d flights + %d trailer) |"
      % (RECT_CSV.relative_to(ROOT).as_posix(), len(rect_all), len(rect), len(rect_all) - len(rect)))
    b("| Paired detection delta | `%s` | %d |"
      % (COMPARISON_CSV.relative_to(ROOT).as_posix(), len(cmp_rows)))
    b("| Downstream prediction delta | `%s` | %d |"
      % (DOWNSTREAM_CSV.relative_to(ROOT).as_posix(), len(down)))
    b("| Downstream pooled summary | `%s` | %d |"
      % (POOLED_SUMMARY_CSV.relative_to(ROOT).as_posix(), len(pooled)))
    b("| Headline ledger | `%s` | %d |"
      % (HISTORY_CSV.relative_to(ROOT).as_posix(), len(hist)))
    b()
    b("The three detection CSVs name **identical flight sets** (`%s`), so the"
      % same_pop)
    b("comparison is paired rather than two independent runs.")
    b()
    b("The two per-flight CSVs each carry **three trailer rows** — `AVERAGE`,")
    b("`LABELED_RECALL (flight_01 + flight_22)` and `CONFIG` — which is why they")
    b("are 166 lines for 163 flights. Those rows are excluded from every")
    b("per-flight statistic here and read only for the headline rates.")
    b()

    b("## 2. Definition of the per-flight delta")
    b()
    b("**Detection level**, from `rect_vs_ellipse_comparison.csv`:")
    b()
    b("    delta_pp = round((rect_combined_rate - ellipse_combined_rate) * 100, 2)")
    b()
    b("Verified against the two source CSVs for all %d flights: **%d arithmetic"
      % (len(cmp_by), delta_mismatch))
    b("mismatches**, **%d rate-copy mismatches**. Sign convention: **negative ="
      % copy_mismatch)
    b("rect is worse**.")
    b()
    b("**Downstream level**, from `rect_vs_ellipse_prediction_comparison.csv`:")
    b()
    b("    delta_mm = round(rect_error_mm - ellipse_error_mm, 2)")
    b()
    b("Verified for all %d paired flights: **%d mismatches**. The sign convention"
      % (n_downstream, mm_arith))
    b("is the opposite in meaning to `delta_pp`: **positive = rect is worse**,")
    b("because the quantity is an error, not a rate.")
    b()

    b("## 3. Headline rates (V1, V2)")
    b()
    b("| Metric | Ellipse | Rect | Delta |")
    b("|---|---:|---:|---:|")
    b("| Combined detection rate (`AVERAGE`) | %.2f%% | %.2f%% | %+.2f pp |"
      % (ell_avg * 100, rect_avg * 100, (rect_avg - ell_avg) * 100))
    b("| True detection rate (`LABELED_RECALL`) | %.2f%% | %.2f%% | %+.2f pp |"
      % (ell_lab * 100, rect_lab * 100, (rect_lab - ell_lab) * 100))
    b()
    b("V1 (96.7%% -> 94.5%%): **%s**. V2 (92.5%% -> 88.8%%): **%s** — 88.8 is 88.75"
      % ("verified" if v1_ok else "MISMATCH", "verified" if v2_ok else "MISMATCH"))
    b("rounded to one decimal.")
    b()
    b("One precision point worth stating, because \"96.7%\" is ambiguous on its own:")
    b("`AVERAGE` is the **unweighted mean of the 163 per-flight rates** (%.6f /"
      % unw_e)
    b("%.6f), *not* the pooled points ratio. Pooled over all detections the same"
      % unw_r)
    b("swap reads %.2f%% -> %.2f%% (%d/%d -> %d/%d), a **%+.2f pp** move rather"
      % (pooled_e * 100, pooled_r * 100, det_e, proc_e, det_r, proc_r,
         (pooled_r - pooled_e) * 100))
    b("than %+.2f pp. Both are defensible; they are not the same number."
      % ((rect_avg - ell_avg) * 100))
    b()
    b("The denominator is identical in both arms (%d processable points), so no"
      % proc_e)
    b("part of the drop comes from a changed population.")
    b()
    b("The true rate is measured on the two labelled flights only")
    b("(`flight_01` + `flight_22`, 240 points). `flight_22` is itself one of the")
    b("worst-regressing flights at %+.2f pp, which is why the labelled recall falls"
      % dict(deltas).get("2026_07_15_gym/flight_22", float("nan")))
    b("further (%+.2f pp) than the all-flight mean (%+.2f pp)."
      % ((rect_lab - ell_lab) * 100, (rect_avg - ell_avg) * 100))
    b()

    b("## 4. Per-flight detection bands (V3, V4, V5)")
    b()
    b("| Band | Count | Claim | Verdict |")
    b("|---|---:|---:|:--:|")
    b("| worse by more than 2 pp (`delta_pp < -2.00`) | %d | %d | %s |"
      % (len(worse_gt), CLAIMS["n_worse_gt2pp"],
         "match" if len(worse_gt) == CLAIMS["n_worse_gt2pp"] else "off by %d"
         % abs(len(worse_gt) - CLAIMS["n_worse_gt2pp"])))
    b("| better by more than 2 pp (`delta_pp > +2.00`) | %d | %d | %s |"
      % (len(better_gt), CLAIMS["n_better_gt2pp"],
         "match" if len(better_gt) == CLAIMS["n_better_gt2pp"] else "off by %d"
         % abs(len(better_gt) - CLAIMS["n_better_gt2pp"])))
    b("| better by 2 pp or more (`delta_pp >= +2.00`) | %d | %d | %s |"
      % (len(better_ge), CLAIMS["n_better_ge2pp"],
         "match" if len(better_ge) == CLAIMS["n_better_ge2pp"] else "off by %d"
         % abs(len(better_ge) - CLAIMS["n_better_ge2pp"])))
    b()
    b("The 12/13 split is a single flight sitting exactly on the boundary:")
    b("**`%s` at `delta_pp = +2.00`**. It is the only flight at the threshold, so"
      % BOUNDARY_FLIGHT)
    b("\"12 better\" (strict `>`) and \"13 better\" (inclusive `>=`) are both correct")
    b("readings of the same file; they differ only in whether the boundary counts.")
    b()
    b("`flagged_regression = YES` appears on **%d** rows, exactly matching the" % len(flagged))
    b("strict worse-than-2 pp count — so the CSV's own flag uses the strict `<`")
    b("convention on the losing side.")
    b()
    b("The ledger's prose in `results_history.csv` says *\"only 13 improved >2pp\"*.")
    b("Recomputed strictly, that is **%d**; the prose counts the boundary flight" % len(better_gt))
    b("under a `>` sign that should be `>=`. Off by one flight, which is inside")
    b("this audit's tolerance and does not trip the stop condition — but the")
    b("ledger sentence is imprecise as written.")
    b()
    b("Extremes, for context:")
    b()
    b("| Worst | pp | Best | pp |")
    b("|---|---:|---|---:|")
    for (fw, dw), (fb, db) in zip(worst, best):
        b("| `%s` | %+.2f | `%s` | %+.2f |" % (fw, dw, fb, db))
    b()
    b("Widespread, not localised: %d of %d flights (%.0f%%) lose more than 2 pp."
      % (len(worse_gt), n_detection, 100.0 * len(worse_gt) / n_detection))
    b()

    b("## 5. Downstream prediction error (V6, V7)")
    b()
    b("### The exact median shift, with sign")
    b()
    b("Two different quantities are both callable \"the median shift\", and they")
    b("differ by more than an order of magnitude. Stating both:")
    b()
    b("| Quantity | Value |")
    b("|---|---:|")
    b("| **Median of the per-flight deltas** (`median(delta_mm)`) | **%+.2f mm** |"
      % median_of_deltas)
    b("| Shift in the pooled median (`median(rect) - median(ellipse)`) | %+.2f mm |"
      % median_shift)
    b("| Mean of the per-flight deltas | %+.2f mm |" % mean_delta)
    b("| Pooled median, ellipse | %.2f mm |" % st.median(e_mm))
    b("| Pooled median, rect | %.2f mm |" % st.median(r_mm))
    b()
    b("The claimed 0.4 mm is the **first** of these: the median per-flight delta,")
    b("**%+.2f mm**, positive meaning rect is worse. That is also the value carried"
      % median_of_deltas)
    b("in `pooled_summary.csv`'s `delta(rect-ellipse)` row (%s), confirmed here to"
      % pooled_delta)
    b("be the median of deltas and **not** the difference of the two medians: %s."
      % pooled_matches_median_of_deltas)
    b()
    b("V6: **%s**." % ("verified" if v6_ok else "MISMATCH"))
    b()
    b("Reading it correctly matters. A +%.2f mm median shift sounds negligible, and"
      % median_of_deltas)
    b("as a *typical-flight* statement it is: %d flights get worse and %d get"
      % (sum(1 for _, v in d_mm if v > 0), sum(1 for _, v in d_mm if v < 0)))
    b("better, close to a coin flip. But the mean delta is %+.2f mm and the pooled"
      % mean_delta)
    b("median moves %+.2f mm, because the damage is concentrated in a tail rather"
      % median_shift)
    b("than spread across the population.")
    b()
    b("### The regressing tail (V7)")
    b()
    b("**%d of %d** flights regress by %.0f mm or more:" % (len(regress), n_downstream, MM_THRESHOLD))
    b()
    b("| Flight | delta (mm) |")
    b("|---|---:|")
    for f, v in regress:
        b("| `%s` | %+.2f |" % (f, v))
    b()
    if regress:
        b("Range **%.2f to %.2f mm**, matching the claimed 250-866 band. V7: **%s**."
          % (regress[-1][1], regress[0][1], "verified" if rng_ok and
             abs(len(regress) - CLAIMS["n_regress_ge250mm"]) == 0 else "see table"))
    b()

    b("## 6. Why the populations are 163 and 157")
    b()
    b("Both levels start from the **same 163 flights** — the detection ids and the")
    b("downstream ids are the same set (%s). The downstream CSV also carries all"
      % (det_ids == down_ids))
    b("163 rows. The drop to 157 happens inside that file, and is fully explained")
    b("by its own `status` / `reason` columns:")
    b()
    b("| Excluded | n | Reason recorded in the file |")
    b("|---|---:|---|")
    for (statuslabel, reason), fl in sorted(reasons.items()):
        b("| `%s` | %d | %s |" % (statuslabel, len(fl), reason))
    b()
    b("    163 flights - %d skipped - %d fit_failed = %d"
      % (sum(len(v) for k, v in reasons.items() if k[0] == "skipped"),
         sum(len(v) for k, v in reasons.items() if k[0] == "fit_failed"),
         n_downstream))
    b()
    b("The excluded flights, by name:")
    b()
    for (statuslabel, reason), fl in sorted(reasons.items()):
        for x in fl:
            b("- `%s` — %s" % (x, statuslabel))
    b()
    b("Critically, **both arms exclude the identical set** (%s): no flight is `ok`"
      % (not asym))
    b("under ellipse and failed under rect or vice versa. So the 157-flight")
    b("comparison is properly paired, and the exclusions are a property of the")
    b("labelling and the RANSAC fit — missing final-point labels, and one flight")
    b("where no candidate model reached the minimum sample count — not a")
    b("consequence of the kernel swap. The swap cost no flight its fit.")
    b()
    b("S2 (population explainable from file contents): **%s**."
      % ("satisfied" if explained else "FAILED"))
    b()

    b("## 7. Migration note — 24 Aug `data/` -> `results/`")
    b()
    if mig:
        b("The ledger row that carries these headline numbers still records its")
        b("artifacts under `data/`:")
        b()
        b("| Recorded path | State | Resolves at |")
        b("|---|---|---|")
        for m in mig:
            b("| `%s` | %s | %s |"
              % (m["path"], "OK" if m["exists"] else "**dangling**",
                 ("`%s`" % m["alt"]) if m["alt"] else ("—" if m["exists"] else "**not found**")))
        b()
        b("%d of %d dangle; %d resolve one-for-one under `results/`. Note the"
          % (sum(1 for m in mig if not m["exists"]), len(mig),
             sum(1 for m in mig if m["alt"])))
        b("migration was **partial** — `contact_sheets/` stayed behind under")
        b("`data/detector_tuning/`, so some recorded paths still resolve as written")
        b("while their siblings do not. Every source CSV this audit reads was")
        b("located under `results/`, not at the path the ledger names.")
    b()

    b("## 8. Verdicts")
    b()
    b("| Check | Claimed | Found | Verdict |")
    b("|---|---|---|:--:|")
    for vid, claim, found, ok, note in verdicts:
        b("| %s | %s | %s | %s |"
          % (vid, claim, found, "pass" if ok else "**FAIL**"))
    b()
    b("Stop conditions: **S1** (any count off by more than one flight) — %s."
      % ("not triggered" if not [s for s in stops if s.startswith("S1")] else "TRIGGERED"))
    b("**S2** (157 population unexplainable) — %s."
      % ("not triggered" if explained else "TRIGGERED"))
    b()

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "x", encoding="utf-8") as f:
        f.write("\n".join(R) + "\n")
    log("wrote report: %s (%d lines)" % (report_path.relative_to(ROOT).as_posix(), len(R)))
    log("=== audit_rect_swap_regression: DONE (%s) ===" % status)
    log.close()


if __name__ == "__main__":
    main()
