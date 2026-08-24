# Work Log: Drag ODE reading and back-computed drag coefficient

**Session:** 2026-08-24_1250
**Status:** Complete

---

## Original Request

> Read src/stereo/trajectory_fit.py read-only and report the exact ODE integrated by
> the drag model as it appears in source, including the sign convention, the grouping
> of the drag term, and the units of K, quoting the lines. Then, using the pooled K
> from results/trajectory_fit_comparison/all_flights/phase1/pooled_k.txt, back-compute
> the implied drag coefficient for a volleyball taking mass and radius from a stated
> source, and report the arithmetic step by step so it can be checked by hand. Report
> the value only, with the assumptions listed; do not judge whether it is plausible
> and do not search for a literature value. Write to
> results/regenerate_figures/drag_coefficient_check.txt. Log incrementally.

---

## [12:50] Step 1 - the ODE, read from source

`src/stereo/trajectory_fit.py`, `simulate_drag`, lines 77-91. Docstring line 78:

```
    """Model C: dv/dt = g - k*|v|*v, integrated via RK45 from (p0, v0) at
```

and the integrand itself, lines 86-91:

```python
    def deriv(t, state):
        pos = state[:3]
        vel = state[3:]
        speed = np.linalg.norm(vel)
        acc = g - k * speed * vel
        return np.concatenate([vel, acc])
```

- **Sign:** minus. `acc = g - k*speed*vel`, so the drag term subtracts.
- **Grouping:** `k * speed * vel` where `speed = norm(vel)` is scalar and `vel` is
  the 3-vector. So it is k|v|**v**, a vector along +v, subtracted - i.e. drag acts
  along -v with magnitude k|v|^2. Quadratic in speed, direction from the velocity
  vector, NOT a per-axis term.
- **No 1/2, no rho, no area, no mass anywhere.** All of that is folded into the
  single scalar k.

## [12:51] Step 2 - units, established from source rather than assumed

| quantity | value / source |
|---|---|
| position | mm - `fit_drag_given_k` returns `residual_rms_mm`; triangulated points are mm |
| g | **9810 mm/s^2** - `trajectory_fit.py:28` `G_MAGNITUDE_MM_S2 = 9810.0  # 9.81 m/s^2 in mm/s^2 -- triangulated positions are in mm` |
| t | **seconds** - `lead_time_ms = (t_target - t_win[-1]) * 1000.0` in the sweep, so t is in s |
| k | **1/mm** |

k's units follow by dimensional consistency and are stated repeatedly in-repo
(`drag_k_discovery.py:149`, `:277`, `:424`): with [acc] = mm/s^2 and
[|v|*v] = mm^2/s^2, [k] = (mm/s^2)/(mm^2/s^2) = **1/mm**.

## [12:52] Step 3 - the repo already states the physical relation

`src/stereo/drag_k_discovery.py:54-61` documents both the relation and the unit
conversion, so the back-computation inverts the repo's own forward formula rather
than importing an external one:

```python
# K sweep centered on a physically-derived volleyball estimate:
# k ~= 0.5 * rho_air * Cd * A / m, rho_air=1.2, Cd=0.4, A=0.0346 m^2, m=0.27 kg
# -> k ~ 0.0308 (1/m, SI). Units note: simulate_drag's k multiplies |v|*v with
# v in mm/s, so this SI k (1/m = 1/(m/s)^2 * (m/s^2)) must be scaled: a = -k*|v|*v
# with v in m/s gives a in m/s^2; converting v to mm/s (factor 1000) and a to
# mm/s^2 (factor 1000) means k_mm = k_SI / 1000 to keep the same physical drag.
K_SI_ESTIMATE = 0.5 * 1.2 * 0.4 * 0.0346 / 0.27  # ~0.0308 (1/m)
K_MM_ESTIMATE = K_SI_ESTIMATE / 1000.0  # ~3.08e-5 (1/mm)
```

So:  k_SI = 0.5 * rho * Cd * A / m,  and  k_SI = 1000 * k_mm.
Inverting: **Cd = 2 * k_SI * m / (rho * A)**.

Note this makes the K sweep's own centring value (Cd = 0.4) an INPUT the repo
chose, not a measured output - the sweep was centred on it, then K was fitted. The
back-computation below is independent of that centring.

---

## [12:55] Step 4 - the arithmetic

Pooled K, verbatim from `results/trajectory_fit_comparison/all_flights/phase1/pooled_k.txt`:

```
5.26847432e-05
```

| step | value |
|---|---|
| k (as stored) | 5.26847432e-05 1/mm |
| k_SI = k_mm x 1000 | 0.0526847432 1/m |
| r = C / (2 pi), C = 0.66 m | 0.10504226 m |
| A = pi r^2 | 0.03466395 m^2 |
| A = C^2/(4 pi) (identity cross-check) | 0.03466395 m^2 (diff 6.9e-18) |
| numerator = 2 k_SI m | 0.0284497613 |
| denominator = rho A | 0.0424633346 |
| **Cd = num / den** | **0.669984** |

### Assumptions

| quantity | value | source |
|---|---|---|
| circumference | 0.66 m | FIVB ball spec, 65-67 cm, midpoint |
| mass | 0.270 kg | FIVB ball spec, 260-280 g, midpoint |
| air density | 1.225 kg/m^3 | ISA sea level, 15 C - NOT from the ball spec |

### Sensitivity

Cd scales linearly with m and inversely with rho and A:

| variant | Cd |
|---|--:|
| FIVB minimum circumference and mass | 0.6652 |
| FIVB maximum circumference and mass | 0.6742 |
| rho = 1.2 (the value the repo used) | 0.6839 |
| repo's own A = 0.0346, m = 0.27, rho = 1.2 | 0.6852 |

So the FIVB tolerance band moves the answer by well under 2%, while the choice of
air density moves it by about 2%.

## [12:56] Step 5 - independent verification launched

The chain has three places a silent error would survive casual reading: the factor
of 2 when inverting k = 0.5*rho*Cd*A/m, the DIRECTION of the mm->m conversion, and
radius-vs-diameter in the area. Rather than assert the result on my own reading, a
verification workflow was launched: three independent derivations (source reading,
dimensional analysis, pure arithmetic with no source access) followed by four
targeted refutation attempts, one per failure mode. Subagents were explicitly
constrained not to judge plausibility and not to look up any literature value, per
the brief. Result folded in below.

---

## [13:02] Step 6 - verification returned: 0 of 4 refuted

7 agents, 4 targeted attacks, **none refuted**.

| attack | verdict | key evidence |
|---|---|---|
| factor of 2 in the inversion | NOT REFUTED | round-tripping the repo's own forward numbers (rho=1.2, Cd=0.4, A=0.0346, m=0.27) through the inverted formula returns **exactly 0.4**. Using 1/2 returns 0.1; no factor returns 0.2. |
| direction of mm -> m conversion | NOT REFUTED | at v = 10 m/s the mm form gives 5.26847432 m/s^2; k_SI = k_mm x 1000 reproduces it exactly, k_mm/1000 is off by 1e6. Only x1000 is self-consistent. |
| radius vs diameter, frontal vs surface area | NOT REFUTED | three algebraically distinct routes to A agree to float round-off. A diameter swap OR sphere surface area would each give A = 0.138655786 m^2 and Cd = 0.167496 - a clean 4x tell, and it does not occur. |
| sign and grouping | NOT REFUTED | quadratic in speed, antiparallel to v, not per-axis. |

The independent source reading reproduced the ODE, sign, grouping and 1/mm units
without seeing my version, and independently traced the mm length unit back to
`SQUARE_SIZE_MM = 67.5` in the calibration object rather than relying on the
inline comment - a stronger provenance than I had established.

### One scope gap the verification itself flagged

The unit-direction agent noted it could not find the literal `5.26847432e-05`
anywhere under `src/` (the literals there are `6.053818e-05`, an older pilot K).
That is correct and expected: the pooled value lives in `pooled_k.txt` and is
loaded at runtime. I read that file directly, so the input is confirmed - but the
flag was the right thing to raise rather than assume.

### Quote fidelity checked mechanically

Every source line quoted in the output file was re-read from disk and compared
character for character against what was written. 6 of 6 verbatim.

---

## [13:04] Complete

**Result: Cd = 0.6700** (0.669984), on the stated assumptions.

| output | |
|---|---|
| `results/regenerate_figures/drag_coefficient_check.txt` | the report |
| this log | |

Sources not modified: `trajectory_fit.py` mtime 2026-07-28 11:34,
`pooled_k.txt` 2026-07-28 12:46. (`drag_k_discovery.py` shows 2026-08-24 09:42
from this morning's path migration, not from this task.)

Per the brief, no plausibility judgement is offered and no literature value was
consulted - and the subagents were explicitly constrained the same way so that
neither could leak in through the verification.
