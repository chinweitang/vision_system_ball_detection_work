"""Step 1 - build the SHORT/LONG classes and cross-check them against elevation.

SHORT = FLAT union MID, LONG = LOB, taken from the bin column of the Pi sweep.
Asserts that this is equivalent to a 45 degree elevation cut, by checking every
SHORT flight has elevation < 45 and every LONG flight >= 45 in launch_to_crossing.csv.

Read-only. Writes nothing.
"""
from collections import Counter

import regen_2class.common as C


def build_classes(sweep_rows):
    """{(session, flight): "SHORT"|"LONG"}, asserting bin is stable across windows."""
    bin_of = {}
    for r in sweep_rows:
        key = (r["session"], r["flight"])
        if key in bin_of and bin_of[key] != r["bin"]:
            raise SystemExit(f"STOP: {key} has inconsistent bin "
                             f"{bin_of[key]} vs {r['bin']} across windows")
        bin_of[key] = r["bin"]
    return bin_of, {k: C.CLASS_OF_BIN[b] for k, b in bin_of.items()}


def main():
    sweep = C.read_csv(C.SWEEP_CSV)
    ltc = C.read_csv(C.LTC_CSV)

    bin_of, cls_of = build_classes(sweep)
    print(f"bin stable across all windows for {len(bin_of)} flights: PASS")
    print(f"source bins: {dict(Counter(bin_of.values()))}")

    counts = Counter(cls_of.values())
    print(f"class counts: SHORT={counts['SHORT']}, LONG={counts['LONG']}, "
          f"total={sum(counts.values())}")
    assert counts["SHORT"] == 47 and counts["LONG"] == 60, "expected 47 / 60"
    assert sum(counts.values()) == 107, "expected 107 total"
    print("expected 47 / 60 / 107: PASS")

    elevation = {(r["session"], r["flight_id"]): float(r["elevation_deg"]) for r in ltc}
    missing = [k for k in cls_of if k not in elevation]
    assert not missing, f"STOP: {len(missing)} sweep flights absent from launch CSV"
    print(f"all {len(cls_of)} flights present in launch_to_crossing.csv: PASS")

    mismatches = []
    for key, cls in cls_of.items():
        e = elevation[key]
        if cls == "SHORT" and not e < C.ELEVATION_CUT_DEG:
            mismatches.append((key, cls, e))
        if cls == "LONG" and not e >= C.ELEVATION_CUT_DEG:
            mismatches.append((key, cls, e))
    if mismatches:
        for key, cls, e in mismatches:
            print(f"  MISMATCH {key} class={cls} elevation={e:.3f}")
        raise SystemExit("STOP: bin/elevation mismatch at the 45 deg cut")
    print(f"elevation cross-check at {C.ELEVATION_CUT_DEG:.0f} deg: PASS, 0 mismatches")

    for cls in C.CLASSES:
        e = [elevation[k] for k, c in cls_of.items() if c == cls]
        print(f"  {cls:5s} elevation range [{min(e):.2f}, {max(e):.2f}] deg  n={len(e)}")
    short_e = [elevation[k] for k, c in cls_of.items() if c == "SHORT"]
    long_e = [elevation[k] for k, c in cls_of.items() if c == "LONG"]
    print(f"  gap across the cut: {min(long_e) - max(short_e):.2f} deg")


if __name__ == "__main__":
    main()
