"""Two-panel frame-rate comparison: convergence error, and fit-failure rate.

The claim the figure carries: frame rate does not materially change prediction
convergence, but it does set the minimum usable observation window, via the
8-inlier minimum of the robust fit. Panel A is the first half, Panel B the
second, on a shared x axis, because the contrast between them is the argument.

PANEL A USES A COMMON FLIGHT SET, AND THAT IS NOT A DETAIL.
An unpaired median error comparison inverts the result. At 400 ms the unpaired
30 fps median (90 mm) beats 60 fps (137 mm) only because ~21.5% of 30 fps
flights have no fit there, and the flights that fail are the hard ones. The
unpaired number measures which flights survived, not which rate is more
accurate. So a flight enters Panel A at a given window only when EVERY arm
produced a fit for it at that window.

A consequence to keep in view: the 60 fps line here is NOT the all-flights
60 fps curve. It is 60 fps restricted to the flights every rate managed, which
at short windows is a small and relatively easy subset. That restriction is the
price of having one baseline all three rates can be read against; 20 fps fits
the fewest flights, so it sets the common set for everyone.

TERMINOLOGY. The reference is the full-arc fixed-gravity-with-drag fit, so the
error here is CONVERGENCE toward that reference, not accuracy against ground
truth.

TIMINGS ARE VOID. The decimation arms carry NaN latency by construction. This
script reads no timing column and writes none.

Nothing is overwritten: every output path goes through next_free().
"""
import csv
import pathlib
import re
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "regenerate_figures" / "05_framerate_decimation"

BASE_RATE = 60
COMPARE_RATES = [30, 20]
EXPECTED_ROWS = 2568          # 107 flights x 24 windows, per arm
EXPECTED_FLIGHTS = 107
EXPECTED_WINDOWS = 24

# Below this many common flights the surviving set is small and self-selected, so
# the median is not comparable to the solid region even though it is still a
# paired number. Drawn dashed and lighter rather than hidden.
N_PAIR_SOLID_MIN = 60

FAILURE_TARGET = 0.05         # "first drops below 5% and stays below"

RATE_COLOUR = {60: "#1f6fb4", 30: "#e08a00", 20: "#c8352c"}

Key = Tuple[str, str, int]    # (session, flight, T_ms)


def stop(msg: str) -> None:
    """Hard stop. Every caller is an unexpected-condition gate from the brief."""
    raise SystemExit("\n*** STOP ***\n" + msg + "\n")


def next_free(path: pathlib.Path) -> pathlib.Path:
    """Never overwrite: fall back to a numeric suffix if the path is taken."""
    if not path.exists():
        return path
    n = 2
    while path.with_name(f"{path.stem}_{n:02d}{path.suffix}").exists():
        n += 1
    return path.with_name(f"{path.stem}_{n:02d}{path.suffix}")


def read_csv(path: pathlib.Path) -> List[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def median(values: Sequence[float]) -> Optional[float]:
    """Plain median. Returns None for an empty set so callers must handle it
    rather than silently plotting a zero or a NaN."""
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else 0.5 * (s[mid - 1] + s[mid])


def fmt(x: Optional[float], places: int = 4) -> str:
    return "" if x is None else f"{x:.{places}f}"


def cell_ok(row: dict) -> bool:
    """A flight-window counts as a successful fit only if the status says ok AND an error
    was actually written. Verified equivalent on all four arms, but both are
    checked because the brief defines failure as either condition."""
    return row["status"] == "ok" and bool(row["position_error_mm"].strip())


# --------------------------------------------------------------------------
# load
# --------------------------------------------------------------------------

def discover_arms() -> Dict[Tuple[int, int], pathlib.Path]:
    """Map (fps, phase) -> csv path for every arm CSV on disk.

    Arms are discovered rather than hardcoded because only 4 of the 6 planned
    arms completed; the two cut 20 fps phases wrote nothing at all.
    """
    found: Dict[Tuple[int, int], pathlib.Path] = {}
    for path in sorted(OUT_DIR.glob("decimation_*.csv")):
        # skip anything this script or the aggregate step wrote
        if re.search(r"panel|summary|raw", path.stem):
            continue
        rows = read_csv(path)
        if len(rows) != EXPECTED_ROWS:
            stop(f"{path.name} has {len(rows)} data rows, expected {EXPECTED_ROWS}. "
                 f"An arm CSV of the wrong length means a truncated or partial run; "
                 f"refusing to aggregate it.")
        arms = {(int(r["fps"]), int(r["phase"])) for r in rows}
        if len(arms) != 1:
            stop(f"{path.name} mixes arms {sorted(arms)}; expected exactly one.")
        arm = arms.pop()
        if arm in found:
            stop(f"arm {arm[0]}fps/phase{arm[1]} appears in both "
                 f"{found[arm].name} and {path.name} — would be double-counted.")
        flights = {(r["session"], r["flight"]) for r in rows}
        windows = {int(r["T_ms"]) for r in rows}
        if len(flights) != EXPECTED_FLIGHTS or len(windows) != EXPECTED_WINDOWS:
            stop(f"{path.name}: {len(flights)} flights x {len(windows)} windows, "
                 f"expected {EXPECTED_FLIGHTS} x {EXPECTED_WINDOWS}.")
        found[arm] = path
    return found


def load(arms: Dict[Tuple[int, int], pathlib.Path]
         ) -> Tuple[Dict[Tuple[int, int], Dict[Key, dict]], List[int]]:
    """Index every arm by (session, flight, T_ms)."""
    indexed: Dict[Tuple[int, int], Dict[Key, dict]] = {}
    windows: set = set()
    for arm, path in arms.items():
        rows = read_csv(path)
        idx: Dict[Key, dict] = {}
        for r in rows:
            k: Key = (r["session"], r["flight"], int(r["T_ms"]))
            if k in idx:
                stop(f"{path.name} has duplicate key {k}")
            idx[k] = r
            windows.add(k[2])
        indexed[arm] = idx
    return indexed, sorted(windows)


# --------------------------------------------------------------------------
# panel A - common flight set
# --------------------------------------------------------------------------

def build_panel_a(indexed, windows, base_arm) -> List[dict]:
    """Common-set median error per (rate, window) — three comparable series.

    A flight enters a given window only if EVERY arm fitted it: 60 fps, every
    30 fps phase, and every 20 fps phase. All three rates are then averaged over
    that identical flight set, which is what lets a single 60 fps line serve as
    the baseline for both comparisons.

    Why this restriction and not per-comparison pairing: 20 fps fits the fewest
    flights, so it sets the common set for everyone. That costs the 30 fps
    comparison most of its flights at short windows (168 -> 44 at 400 ms). The
    trade was made deliberately, to get one readable baseline instead of two.

    Within a rate, phases are pooled: a flight in the common set contributes one
    observation per phase of that rate, not a per-phase median.
    """
    all_arms = sorted(indexed)
    rates = sorted({f for (f, p) in all_arms}, reverse=True)
    base = indexed[base_arm]

    # the arms must cover identical (flight, window) keys or the intersection is
    # measuring coverage rather than fit success
    for arm, idx in indexed.items():
        missing = set(idx) - set(base)
        if missing:
            k = sorted(missing)[0]
            stop(f"key {k} present in {arm[0]}fps/phase{arm[1]} but absent from "
                 f"the {BASE_RATE} fps arm — the arms do not cover the same "
                 f"flights, so the common set is unsound.")

    out: List[dict] = []
    any_common = False
    for T in windows:
        common: Optional[set] = None
        for arm in all_arms:
            fitted = {(k[0], k[1]) for k, r in indexed[arm].items()
                      if k[2] == T and cell_ok(r)}
            common = fitted if common is None else (common & fitted)
        common = common or set()
        n_common = len(common)
        if n_common:
            any_common = True

        per_rate = {}
        for rate in rates:
            errs: List[float] = []
            pts: List[float] = []
            for (f, p) in all_arms:
                if f != rate:
                    continue
                for k, r in indexed[(f, p)].items():
                    if k[2] != T or (k[0], k[1]) not in common:
                        continue
                    errs.append(float(r["position_error_mm"]))
                    if r.get("n_points_used", "").strip():
                        pts.append(float(r["n_points_used"]))
            per_rate[rate] = (median(errs), median(pts), len(errs))

        m_base = per_rate.get(BASE_RATE, (None, None, 0))[0]
        for rate in rates:
            m, mp, n_obs = per_rate[rate]
            out.append(dict(
                rate=rate,
                T_ms=T,
                n_flights_common=n_common,
                n_phases=sum(1 for (f, p) in all_arms if f == rate),
                n_observations=n_obs,
                median_err_mm=fmt(m),
                median_n_points=fmt(mp, 1),
                # `is None` rather than truthiness: a median of exactly 0.0 is
                # not expected here but would silently blank the ratio
                ratio_vs_60=("" if (m is None or m_base is None or m_base == 0.0)
                             else f"{m / m_base:.4f}"),
            ))
    if not any_common:
        stop("no window has a flight that every arm fitted — the common set is "
             "empty everywhere, so no three-way comparison is possible.")
    return out


# --------------------------------------------------------------------------
# panel B - failure fraction, all flights, no pairing
# --------------------------------------------------------------------------

def build_panel_b(indexed, windows) -> List[dict]:
    """Fit-failure fraction per (rate, window) over all flights.

    Phases are pooled (summed) within a rate rather than averaged as fractions;
    with equal counts per phase the two are identical, and summing keeps
    n_total honest about how much evidence sits behind each point.
    """
    out: List[dict] = []
    rates = sorted({f for (f, p) in indexed}, reverse=True)
    for rate in rates:
        phases = sorted(p for (f, p) in indexed if f == rate)
        for T in windows:
            n_total = 0
            n_failed = 0
            for p in phases:
                for k, row in indexed[(rate, p)].items():
                    if k[2] != T:
                        continue
                    n_total += 1
                    if not cell_ok(row):
                        n_failed += 1
            out.append(dict(
                rate=rate,
                T_ms=T,
                n_phases=len(phases),
                n_total=n_total,
                n_failed=n_failed,
                fail_fraction=f"{n_failed / n_total:.6f}" if n_total else "",
            ))
    return out


def first_stable_below(panel_b: List[dict], rate: int,
                       windows: List[int], target: float) -> Optional[int]:
    """Smallest window where the failure fraction drops below target and stays
    below it for every longer window. Scanned from the long end backwards so a
    single spike at a long window correctly disqualifies everything shorter."""
    by_T = {r["T_ms"]: r for r in panel_b if r["rate"] == rate}
    best: Optional[int] = None
    for T in sorted(windows, reverse=True):
        row = by_T.get(T)
        if row is None or row["fail_fraction"] == "":
            break
        if float(row["fail_fraction"]) < target:
            best = T
        else:
            break
    return best


# --------------------------------------------------------------------------
# figure
# --------------------------------------------------------------------------

def draw(panel_a, panel_b, windows, out_png, arms) -> None:
    fig, (ax_a, ax_b) = plt.subplots(
        2, 1, figsize=(7.6, 8.0), sharex=True,
        gridspec_kw={"height_ratios": [1.25, 1.0], "hspace": 0.13})
    fig.patch.set_facecolor("white")

    handles: List = []
    labels: List[str] = []

    # -- Panel A ---------------------------------------------------------
    ax_a.set_facecolor("white")
    ax_a.grid(True, which="both", color="#e2e2e2", lw=0.7)
    ax_a.set_axisbelow(True)

    # All three rates share one flight set per window, so one line each and one
    # baseline. The solid/dashed split is driven by the SAME n_flights_common for
    # every rate, so the three lines break to dashed at the same window.
    for rate in sorted({r["rate"] for r in panel_a}, reverse=True):
        rows = sorted((r for r in panel_a if r["rate"] == rate),
                      key=lambda r: r["T_ms"])
        xs_solid, ys_solid, xs_dash, ys_dash = [], [], [], []
        for r in rows:
            v = r["median_err_mm"]
            if v == "":
                continue
            if r["n_flights_common"] >= N_PAIR_SOLID_MIN:
                xs_solid.append(r["T_ms"])
                ys_solid.append(float(v))
            else:
                xs_dash.append(r["T_ms"])
                ys_dash.append(float(v))
        if not xs_solid and not xs_dash:
            continue
        if xs_dash:
            ax_a.plot(xs_dash, ys_dash, ls="--", lw=1.3, alpha=0.45,
                      color=RATE_COLOUR[rate], marker="o", ms=3.2)
        # the legend handle always uses the solid style, even when this series
        # is entirely dashed, so the legend reads as an identity not a state
        line, = ax_a.plot(xs_solid, ys_solid, ls="-", lw=1.8,
                          color=RATE_COLOUR[rate], marker="o", ms=4.0)
        handles.append(line)
        labels.append(f"{rate} fps")

    ax_a.set_yscale("log")
    ax_a.set_ylabel("median crossing-position error (mm)", fontsize=10.5)
    ax_a.set_title("A   convergence error — flights every rate fitted",
                   fontsize=11, loc="left", pad=8)
    ax_a.tick_params(labelsize=9.5)

    # -- Panel B ---------------------------------------------------------
    ax_b.set_facecolor("white")
    ax_b.grid(True, color="#e2e2e2", lw=0.7)
    ax_b.set_axisbelow(True)

    for rate in sorted({r["rate"] for r in panel_b}, reverse=True):
        rows = sorted((r for r in panel_b if r["rate"] == rate),
                      key=lambda r: r["T_ms"])
        xs = [r["T_ms"] for r in rows if r["fail_fraction"] != ""]
        ys = [100.0 * float(r["fail_fraction"]) for r in rows
              if r["fail_fraction"] != ""]
        ax_b.plot(xs, ys, ls="-", lw=1.8, marker="o", ms=4.0,
                  color=RATE_COLOUR[rate], label=f"{rate} fps")

    ax_b.axhline(100.0 * FAILURE_TARGET, color="#666666", ls=":", lw=1.1)
    ax_b.set_ylim(0, 100)
    ax_b.set_ylabel("flights with no fit (%)", fontsize=10.5)
    ax_b.set_xlabel("observation window (ms)", fontsize=10.5)
    ax_b.set_title("B   fit-failure fraction — all flights, unpaired",
                   fontsize=11, loc="left", pad=8)
    ax_b.tick_params(labelsize=9.5)

    # one legend for the whole figure
    b_handles, b_labels = ax_b.get_legend_handles_labels()
    for h, l in zip(b_handles, b_labels):
        if l not in labels:
            handles.append(h)
            labels.append(l)
    ax_a.legend(handles, labels, frameon=False, fontsize=9, loc="lower left",
                ncol=2)

    n20 = sum(1 for (f, p) in arms if f == 20)
    fig.text(0.012, 0.006,
             f"Panel A: all rates averaged over the same flights (those every "
             f"rate fitted); dashed where fewer than {N_PAIR_SOLID_MIN} such "
             f"flights. 20 fps rests on {n20} of 3 grid phases; 30 fps on 2 of 2.",
             fontsize=7.6, color="#555555", ha="left")

    fig.savefig(out_png, dpi=300, facecolor="white", bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------

def main() -> None:
    print("=" * 78)
    print("FRAME RATE — TWO-PANEL COMPARISON")
    print("=" * 78)
    print("Reference = full-arc fixed-gravity-with-drag fit: this is CONVERGENCE,")
    print("not accuracy against ground truth. All timings in these arms are VOID.")
    print()

    arms = discover_arms()
    if not arms:
        stop(f"no arm CSVs found in {OUT_DIR}")
    print("arms found:")
    for (fps, phase), path in sorted(arms.items()):
        print(f"   {fps:>3} fps  phase {phase}   {path.name}")
    if not any(f == BASE_RATE for (f, p) in arms):
        stop(f"no {BASE_RATE} fps arm found; Panel A pairs against it and cannot "
             f"be built without it.")
    base_arm = next(a for a in arms if a[0] == BASE_RATE)

    for rate in COMPARE_RATES:
        got = sorted(p for (f, p) in arms if f == rate)
        expected = {30: 2, 20: 3}[rate]
        if len(got) < expected:
            print(f"   NOTE: {rate} fps has phases {got} of {expected} — that "
                  f"rate is not fully phase-averaged.")

    indexed, windows = load(arms)
    print(f"\nwindows: {windows}")

    panel_a = build_panel_a(indexed, windows, base_arm)
    panel_b = build_panel_b(indexed, windows)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pa = next_free(OUT_DIR / "framerate_panelA_paired.csv")
    with open(pa, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(panel_a[0].keys()))
        w.writeheader()
        w.writerows(panel_a)
    print(f"\nwrote {pa.relative_to(ROOT)}  ({len(panel_a)} rows)")

    pb = next_free(OUT_DIR / "framerate_panelB_failures.csv")
    with open(pb, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(panel_b[0].keys()))
        w.writeheader()
        w.writerows(panel_b)
    print(f"wrote {pb.relative_to(ROOT)}  ({len(panel_b)} rows)")

    # ---- Panel A table ----
    print("\n" + "=" * 78)
    print("PANEL A — convergence error over flights EVERY rate fitted")
    print("=" * 78)
    rates_a = sorted({r["rate"] for r in panel_a}, reverse=True)
    print(f"\n  Every rate at a given window is averaged over the SAME flights:")
    print(f"  the ones all of {', '.join(str(x) + ' fps' for x in rates_a)} fitted.\n")
    print(f"  {'T_ms':>6}{'flights':>9}", end="")
    for rate in rates_a:
        print(f"{str(rate) + ' fps err':>14}{'pts':>7}{'x60':>7}", end="")
    print("   note")
    for T in windows:
        rows = {r["rate"]: r for r in panel_a if r["T_ms"] == T}
        if not rows:
            continue
        n_common = next(iter(rows.values()))["n_flights_common"]
        note = ""
        if n_common == 0:
            note = "no common flights"
        elif n_common < N_PAIR_SOLID_MIN:
            note = "self-selected"
        print(f"  {T:>6}{n_common:>9}", end="")
        for rate in rates_a:
            r = rows.get(rate)
            if r is None:
                print(f"{'-':>14}{'-':>7}{'-':>7}", end="")
            else:
                print(f"{r['median_err_mm']:>14}{r['median_n_points']:>7}"
                      f"{r['ratio_vs_60']:>7}", end="")
        print(f"   {note}")

    # ---- Panel B table ----
    print("\n" + "=" * 78)
    print("PANEL B — fit-failure fraction (all flights, unpaired)")
    print("=" * 78)
    rates_b = sorted({r["rate"] for r in panel_b}, reverse=True)
    print(f"  {'T_ms':>6}", end="")
    for rate in rates_b:
        print(f"{str(rate) + ' fps':>24}", end="")
    print()
    print(f"  {'':>6}", end="")
    for _ in rates_b:
        print(f"{'failed/total':>16}{'pct':>8}", end="")
    print()
    for T in windows:
        print(f"  {T:>6}", end="")
        for rate in rates_b:
            r = next((x for x in panel_b
                      if x["rate"] == rate and x["T_ms"] == T), None)
            if r is None:
                print(f"{'-':>16}{'-':>8}", end="")
            else:
                frac = float(r["fail_fraction"]) if r["fail_fraction"] else 0.0
                print(f"{str(r['n_failed']) + '/' + str(r['n_total']):>16}"
                      f"{100 * frac:>7.1f}%", end="")
        print()

    # ---- threshold ----
    print("\n" + "=" * 78)
    print(f"MINIMUM USABLE WINDOW  (failure fraction first below "
          f"{100 * FAILURE_TARGET:.0f}% and staying below)")
    print("=" * 78)
    for rate in rates_b:
        T = first_stable_below(panel_b, rate, windows, FAILURE_TARGET)
        print(f"   {rate:>3} fps : "
              f"{str(T) + ' ms' if T is not None else 'NEVER within the tested windows'}")

    png = next_free(OUT_DIR / "figure_framerate_two_panel.png")
    draw(panel_a, panel_b, windows, png, arms)
    print(f"\nwrote {png.relative_to(ROOT)}")
    print("\n  No latency or timing value was read, plotted or written.")
    print("  No unpaired error comparison was produced.")


if __name__ == "__main__":
    main()
