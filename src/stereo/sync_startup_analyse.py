#!/usr/bin/env python3
"""
sync_startup_analyse.py  -  RUNS ON THE LAPTOP.

Pull the summary first:
    scp -i <key> chinnywei@192.168.50.1:~/captures/sync_startup_summary.csv .

Reads the ~20 rows and answers the only question that matters:
  Is the sub-frame RESIDUAL stable across independent startups?
    - stable (tight spread)  -> correct arc data with a fixed constant, OR
                                measure once per session; software sync is fine.
    - wanders (wide spread)  -> measure the residual EVERY gym session, or if
                                it's wild/unmeasurable, build the hardware trigger.

Also translates the residual spread into POSITION ERROR at your ball speed,
so you can see directly whether uncorrected sync fits the +-100 mm width budget.
"""
import csv
import sys
import statistics

BALL_SPEED_MS = 10.4      # your fast-end toward-leg speed; edit if needed
WIDTH_BUDGET_MM = 100.0
CSV = sys.argv[1] if len(sys.argv) > 1 else "sync_startup_summary.csv"

rows = []
with open(CSV) as f:
    for r in csv.DictReader(f):
        rows.append(r)

# keep only good runs
good = [r for r in rows if r.get("fps_ok","1") == "1"]
junk = len(rows) - len(good)

residuals   = [float(r["residual_ms"]) for r in good]
raw_offsets = [float(r["raw_offset_ms"]) for r in good]
jitters     = [float(r["jitter_ms"]) for r in good]
drifts      = [abs(float(r["drift_total_ms"])) for r in good]
whole       = [int(r["whole_frames"]) for r in good]
maxpair     = [float(r["max_paired_ms"]) for r in good]

def stats(xs):
    return statistics.mean(xs), statistics.pstdev(xs), min(xs), max(xs)

print(f"\n=== Sync startup characterisation  ({len(good)} good runs, {junk} junk) ===\n")

# --- whole-frame slip: expected to vary, it's just bookkeeping ---
print(f"whole-frame slip across runs: {sorted(set(whole))}  "
      f"(varies = normal; it's the startup frame misalignment, removed by index-shift)\n")

# --- THE headline: sub-frame residual stability ---
m, sd, lo, hi = stats([abs(x) for x in residuals])
print(f"SUB-FRAME RESIDUAL |ms|:  mean {m:.2f}  sd {sd:.2f}  range [{lo:.2f}, {hi:.2f}]")
print(f"  signed residuals: {[round(x,1) for x in residuals]}")

# --- alignment sanity ---
mp_m, mp_sd, mp_lo, mp_hi = stats(maxpair)
align_ok = mp_hi < 8.34
print(f"max paired |delta| after alignment: worst {mp_hi:.2f} ms  "
      f"-> {'OK (<8.3)' if align_ok else 'FAIL: alignment broke on some run'}")

# --- jitter and drift, expected negligible ---
jm, jsd, jlo, jhi = stats(jitters)
dm, dsd, dlo, dhi = stats(drifts)
print(f"jitter: mean {jm*1000:.1f} us (irreducible floor)")
print(f"drift per capture: worst {dhi*1000:.1f} us  (negligible if << frame period)\n")

# --- translate to position error at ball speed ---
print(f"--- position error at {BALL_SPEED_MS} m/s ---")
worst_residual = max(abs(x) for x in residuals)
err_uncorrected = worst_residual/1000.0 * BALL_SPEED_MS * 1000.0   # mm
err_jitter      = jhi/1000.0 * BALL_SPEED_MS * 1000.0
err_residual_spread = sd/1000.0 * BALL_SPEED_MS * 1000.0
print(f"  worst-case UNCORRECTED (worst residual x speed): {err_uncorrected:.0f} mm"
      f"  ({'BLOWS' if err_uncorrected>WIDTH_BUDGET_MM else 'within'} the +-{WIDTH_BUDGET_MM:.0f} mm budget)")
print(f"  after CONSTANT correction, leftover from residual spread (sd x speed): {err_residual_spread:.1f} mm")
print(f"  after correction, jitter floor (jitter x speed): {err_jitter:.2f} mm\n")

# --- verdict ---
print("=== VERDICT ===")
spread_mm = err_residual_spread
if spread_mm < 10:
    print(f"Residual is STABLE across startups (spread -> {spread_mm:.1f} mm).")
    print("=> A fixed centroid correction (residual x pixel-velocity) works.")
    print("   Software sync is sufficient. Hardware trigger stays a contingency.")
elif spread_mm < 30:
    print(f"Residual WANDERS moderately (spread -> {spread_mm:.1f} mm).")
    print("=> Measure the residual FRESH each gym session (like extrinsics) and")
    print("   apply that session's number. Software sync still viable per-session.")
else:
    print(f"Residual WANDERS WIDELY (spread -> {spread_mm:.1f} mm).")
    print("=> Per-session correction is fragile. Build the HARDWARE TRIGGER")
    print("   (Arduino Nano, D9/D10, optocoupler - already scoped in context §4.3).")
