"""Step 3 - join the Pi sweep to the crossing budget and the crossing classification.

    pipeline_sweep_raw.csv        on (session, flight)
      -> launch_to_crossing.csv   on (session, flight_id)   [launch_to_crossing_ms, elevation_deg]
      -> crossing_classification.csv on (session, flight_id) [duration_ms]

Joins on the FULL (session, flight_id) pair, never the bare flight id: flight_13
exists in BOTH sessions, so a bare-id join silently compares two different flights.

Asserts 2568 rows, 107 distinct flights, 24 windows, no duplicates, duration_ms
present for every flight.

Writes data/regenerate_figures/two_class_join.csv. Deterministic: re-running
reproduces the file byte for byte.
"""
import csv
from collections import Counter

import regen_2class.common as C
from regen_2class.step_1_classes import build_classes

OUT_COLUMNS = ["session", "flight", "bin", "cls2", "elevation_deg", "T_ms", "status",
               "airborne", "n_detected", "position_error_mm", "velocity_error_mm_s",
               "hit_miss_match", "latency_ms", "last_pair_detect_ms", "triangulate_ms",
               "ransac_ms", "predict_ms", "launch_to_crossing_ms", "duration_ms"]


def index_unique(rows, label):
    out = {}
    for r in rows:
        key = (r["session"], r["flight_id"])
        if key in out:
            raise SystemExit(f"STOP: duplicate key {key} in {label}")
        out[key] = r
    return out


def main():
    sweep = C.read_csv(C.SWEEP_CSV)
    ltc = index_unique(C.read_csv(C.LTC_CSV), "launch_to_crossing.csv")
    crossing = index_unique(C.read_csv(C.CROSSING_CSV), "crossing_classification.csv")
    _, cls_of = build_classes(sweep)
    print(f"lookups keyed on (session, flight_id): launch={len(ltc)}, "
          f"crossing_classification={len(crossing)}, 0 duplicates")

    shared = sorted({k[1] for k in crossing} & {k[1] for k in ltc})
    dupe_ids = [fid for fid in shared
                if len({s for s, f in crossing if f == fid}) > 1]
    print(f"bare-id hazard present: {len(dupe_ids)} flight id(s) appear in more than "
          f"one session, e.g. {dupe_ids[:3]}")

    joined = []
    for r in sweep:
        key = (r["session"], r["flight"])
        launch, cross = ltc.get(key), crossing.get(key)
        if launch is None:
            raise SystemExit(f"STOP: {key} missing from launch_to_crossing.csv")
        if cross is None:
            raise SystemExit(f"STOP: {key} missing from crossing_classification.csv")
        if not cross.get("duration_ms", "").strip():
            raise SystemExit(f"STOP: duration_ms missing for {key}")
        joined.append({**r, "cls2": cls_of[key],
                       "elevation_deg": launch["elevation_deg"],
                       "launch_to_crossing_ms": launch["launch_to_crossing_ms"],
                       "duration_ms": cross["duration_ms"]})
    print("duration_ms present for all flights: PASS")

    n_rows = len(joined)
    n_flights = len({(r["session"], r["flight"]) for r in joined})
    n_windows = len({r["T_ms"] for r in joined})
    assert n_rows == 2568, f"rows {n_rows} != 2568"
    assert n_flights == 107, f"flights {n_flights} != 107"
    assert n_windows == 24, f"windows {n_windows} != 24"
    dupes = [k for k, v in Counter(
        (r["session"], r["flight"], r["T_ms"]) for r in joined).items() if v > 1]
    assert not dupes, f"{len(dupes)} duplicate keys after join"
    print(f"ASSERT rows==2568: PASS ({n_rows})")
    print(f"ASSERT flights==107: PASS ({n_flights})")
    print(f"ASSERT windows==24: PASS ({n_windows})")
    print("ASSERT no duplicate (session, flight, window): PASS")
    print(f"class row split: {dict(Counter(r['cls2'] for r in joined))}")
    print(f"status split: {dict(Counter(r['status'] for r in joined))}")

    with open(C.JOIN_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(joined)
    print(f"wrote {C.JOIN_CSV} ({n_rows} rows, {len(OUT_COLUMNS)} cols)")


if __name__ == "__main__":
    main()
