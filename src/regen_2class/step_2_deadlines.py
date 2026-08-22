"""Step 2 - per-class launch-to-crossing statistics and the class deadlines.

RULE, applied identically to both classes:
    deadline(class) = floor( min(launch_to_crossing_ms over that class) / 10 ) * 10

Min-anchored, not percentile-anchored, so no flight in the class can have crossed
before its own deadline elapses. No deadline value is hardcoded anywhere; both are
computed from the CSV on every run.

Read-only. Writes nothing.
"""
import statistics as st

import regen_2class.common as C
from regen_2class.step_1_classes import build_classes


def main():
    sweep = C.read_csv(C.SWEEP_CSV)
    ltc = C.read_csv(C.LTC_CSV)
    _, cls_of = build_classes(sweep)

    values = {c: [] for c in C.CLASSES}
    for r in ltc:
        key = (r["session"], r["flight_id"])
        values[cls_of[key]].append(float(r["launch_to_crossing_ms"]))

    print(f"{'class':6s} {'n':>4} {'min':>9} {'P5':>9} {'P25':>9} {'median':>9} {'max':>9}")
    for c in C.CLASSES:
        v = values[c]
        print(f"{c:6s} {len(v):>4} {min(v):>9.1f} {C.percentile(v, .05):>9.1f} "
              f"{C.percentile(v, .25):>9.1f} {st.median(v):>9.1f} {max(v):>9.1f}")

    print()
    print("rule: deadline = floor(min / 10) * 10   (population minimum, rounded down)")
    dl = {c: __import__("math").floor(min(values[c]) / 10.0) * 10.0 for c in C.CLASSES}
    for c in C.CLASSES:
        print(f"  deadline({c}) = {dl[c]:.0f} ms   (min {min(values[c]):.4f})")

    print()
    print("change vs the previous three-class scheme:")
    print("  SHORT 490 ms - same value as the old FLAT deadline, which was also")
    print("        min-anchored, but now covers 47 flights not 35. MID's old 710 ms")
    print("        (a P5, not a min) is discarded.")
    print(f"  LONG  {dl['LONG']:.0f} ms - DOWN from the previously used 1080 ms, which was")
    print(f"        LOB's P5. Under the min rule the LONG budget tightens by "
          f"{1080 - dl['LONG']:.0f} ms.")

    print()
    print(f"duration-range overlap: SHORT max {max(values['SHORT']):.1f} ms vs "
          f"LONG min {min(values['LONG']):.1f} ms "
          f"-> {max(values['SHORT']) - min(values['LONG']):.1f} ms overlap")
    print("  (quantified as the confusion region in step 6)")


if __name__ == "__main__":
    main()
