# trajectory_fit.py
# Single source of the trajectory-fitting models shared across this project's
# stereo scripts. Consolidates what used to be 3 independent implementations
# of the same gravity-only fit (predict_sweep.py, label_vs_detection.py,
# triangulate_flight.py) -- see
# claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md
# for why.
#
# Three models, all operating on positions in mm and time in seconds (camera
# frame, no world registration needed -- fitting/prediction error is
# rigid-invariant):
#   Model A -- fit_constant_accel: p(t) = p0 + v0*t + 0.5*a*t^2, all of
#     p0, v0, a free per axis (linear least squares). No imposed gravity
#     direction.
#   Model B -- fit_constant_accel_fixed_g: same parabola, but a fixed at an
#     externally-supplied g (also linear least squares, now solving only for
#     p0, v0).
#   Model C -- fit_drag_given_k / fit_drag_free_k: dv/dt = g - k*|v|*v,
#     integrated numerically (simulate_drag) and fit via nonlinear
#     least-squares.

from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares

G_MAGNITUDE_MM_S2 = 9810.0  # 9.81 m/s^2 in mm/s^2 -- triangulated positions are in mm


# ---- Model A: free gravity, no drag ---------------------------------------

def fit_parabola_axis(t, p):
    """p(t) = p0 + v0*t + 0.5*a*t^2, least squares. Returns (p0, v0, a)."""
    A = np.stack([np.ones_like(t), t, 0.5 * t ** 2], axis=1)
    coef, *_ = np.linalg.lstsq(A, p, rcond=None)
    return coef


def fit_constant_accel(t, xyz):
    """Fit p(t) = p0 + v0*t + 0.5*a*t^2 per axis (free a, no imposed gravity
    direction -- gravity is not axis-aligned in an arbitrary camera frame).
    Returns (p0, v0, a) each as a 3-vector, reusing fit_parabola_axis verbatim
    per axis."""
    p0 = np.zeros(3); v0 = np.zeros(3); a = np.zeros(3)
    for ax in range(3):
        p0[ax], v0[ax], a[ax] = fit_parabola_axis(t, xyz[:, ax])
    return p0, v0, a


def predict_at(p0, v0, a, t):
    return p0 + v0 * t + 0.5 * a * t ** 2


# ---- Model B: fixed gravity, no drag (linear) -----------------------------

def fit_constant_accel_fixed_g(t, xyz, g):
    """Model B: p(t) = p0 + v0*t + 0.5*g*t^2, g FIXED (3-vector, mm/s^2),
    only (p0, v0) fit -- linear least squares per axis:
    p(t) - 0.5*g*t^2 = p0 + v0*t.
    Returns (p0, v0) each as a 3-vector."""
    p0 = np.zeros(3); v0 = np.zeros(3)
    A = np.stack([np.ones_like(t), t], axis=1)
    for ax in range(3):
        y = xyz[:, ax] - 0.5 * g[ax] * t ** 2
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        p0[ax], v0[ax] = coef
    return p0, v0


def predict_at_fixed_g(p0, v0, g, t):
    return p0 + v0 * t + 0.5 * g * t ** 2


# ---- Model C: fixed gravity + quadratic drag (nonlinear) ------------------

def simulate_drag(p0, v0, k, g, t_array):
    """Model C: dv/dt = g - k*|v|*v, integrated via RK45 from (p0, v0) at
    t=0. Returns positions (Nx3) at the requested t_array (must include 0 or
    be sorted ascending with 0 as the implicit start; solve_ivp handles
    arbitrary t_eval as long as it's within [t0, tf])."""
    t_array = np.asarray(t_array, dtype=np.float64)
    t0 = 0.0
    tf = float(max(t_array.max(), t0))

    def deriv(t, state):
        pos = state[:3]
        vel = state[3:]
        speed = np.linalg.norm(vel)
        acc = g - k * speed * vel
        return np.concatenate([vel, acc])

    state0 = np.concatenate([p0, v0])
    # t_eval must be sorted ascending and within [t0, tf]; sort and restore order.
    order = np.argsort(t_array)
    t_sorted = t_array[order]
    sol = solve_ivp(deriv, (t0, tf), state0, t_eval=t_sorted, method="RK45",
                     rtol=1e-8, atol=1e-6)
    if not sol.success:
        raise RuntimeError(f"simulate_drag: integration failed: {sol.message}")
    pos_sorted = sol.y[:3].T  # (len(t_sorted), 3)
    pos = np.empty_like(pos_sorted)
    pos[order] = pos_sorted
    return pos


def fit_drag_given_k(t, xyz, k, g, p0_guess, v0_guess):
    """Model C, K FIXED: nonlinear least-squares fit of (p0, v0) only, via
    scipy.optimize.least_squares against simulate_drag. Returns (p0, v0,
    residual_rms_mm)."""
    x0 = np.concatenate([p0_guess, v0_guess])

    def resid(x):
        p0, v0 = x[:3], x[3:]
        pred = simulate_drag(p0, v0, k, g, t)
        return (pred - xyz).ravel()

    result = least_squares(resid, x0, method="lm", max_nfev=2000)
    p0_fit, v0_fit = result.x[:3], result.x[3:]
    rms = float(np.sqrt(np.mean(result.fun ** 2)))
    return p0_fit, v0_fit, rms


def fit_drag_free_k(t, xyz, g, p0_guess, v0_guess, k_guess):
    """Model C, K FREE: nonlinear least-squares fit of (p0, v0, k), g fixed.
    Returns (p0, v0, k, residual_rms_mm)."""
    x0 = np.concatenate([p0_guess, v0_guess, [k_guess]])

    def resid(x):
        p0, v0, k = x[:3], x[3:6], x[6]
        pred = simulate_drag(p0, v0, k, g, t)
        return (pred - xyz).ravel()

    result = least_squares(resid, x0, method="lm", max_nfev=4000)
    p0_fit, v0_fit, k_fit = result.x[:3], result.x[3:6], float(result.x[6])
    rms = float(np.sqrt(np.mean(result.fun ** 2)))
    return p0_fit, v0_fit, k_fit, rms


# ---- g_fixed loader (decision #2: validated world-frame registration only) -

def load_g_fixed(npz_path: Path):
    """Loads up_vec (camera-frame unit vector) from the existing, validated
    2026_07_15_gym world-frame registration transform. Returns g_fixed =
    9810 * (-up_vec), mm/s^2. Does NOT recompute up_vec or derive it from any
    trajectory fit -- see decisions #2/#3 in the task prompt."""
    data = np.load(npz_path)
    up_vec = data["up_vec"].astype(np.float64)
    up_vec = up_vec / np.linalg.norm(up_vec)
    g_fixed = G_MAGNITUDE_MM_S2 * (-up_vec)
    mag = float(np.linalg.norm(g_fixed))
    print(f"load_g_fixed: up_vec={up_vec}  g_fixed={g_fixed}  |g_fixed|={mag:.2f} mm/s^2 "
          f"(expect ~{G_MAGNITUDE_MM_S2:.0f})")
    assert abs(mag - G_MAGNITUDE_MM_S2) < 1.0, (
        f"g_fixed magnitude {mag:.2f} far from {G_MAGNITUDE_MM_S2:.0f} -- units/sign error")
    return g_fixed


# ---- RANSAC-robustified fitting -------------------------------------------
# Generic wrapper: works uniformly across Models A/B/C because it only calls
# fit_fn(t_subset, xyz_subset) -> params and predict_fn(params, t_array) ->
# xyz_array. It doesn't know or care whether params is (p0,v0,a), (p0,v0), or
# whatever a caller closes over (e.g. Model C's fixed g/k) -- see
# claude/claude_logs/2026-07-27_gravity_vs_drag_trajectory_fitting_worklog.md
# for the RANSAC task and how each model's fit_fn/predict_fn are built.

def ransac_n_iterations(min_samples: int, outlier_fraction: float = 0.3,
                          success_prob: float = 0.999) -> int:
    """Standard RANSAC iteration-count formula:
    N = log(1-p) / log(1-(1-e)^s)
    p = target probability of picking at least one all-inlier sample,
    e = assumed worst-case outlier fraction, s = min_samples per draw."""
    import math
    denom = math.log(1.0 - (1.0 - outlier_fraction) ** min_samples)
    n = math.log(1.0 - success_prob) / denom
    return int(math.ceil(n))


def ransac_fit(t, xyz, fit_fn, predict_fn, min_samples, inlier_threshold_mm,
               n_iterations, random_seed, frame_numbers=None):
    """Generic RANSAC wrapper. t, xyz: full candidate point set (xyz Nx3 mm).
    fit_fn(t_subset, xyz_subset) -> params (any tuple fit_fn/predict_fn agree on).
    predict_fn(params, t_array) -> Nx3 predicted positions.
    frame_numbers: optional, same length as t -- if given, accepted/rejected
    lists are actual frame numbers; otherwise plain indices into t/xyz.

    Repeatedly samples min_samples points, fits, scores every point's
    residual against inlier_threshold_mm, keeps the largest inlier set seen,
    then does one final fit_fn call on that winning set. Raises RuntimeError
    if no candidate ever produced at least min_samples inliers (mirrors
    fit_drag_given_k's own convergence-failure convention so callers can
    catch/skip consistently)."""
    rng = np.random.default_rng(random_seed)
    n = len(t)
    if n < min_samples:
        raise RuntimeError(f"ransac_fit: only {n} points, need >= min_samples={min_samples}")

    best_mask = None
    best_count = -1
    for _ in range(n_iterations):
        idx = rng.choice(n, size=min_samples, replace=False)
        try:
            params = fit_fn(t[idx], xyz[idx])
            pred_all = predict_fn(params, t)
        except Exception:
            continue
        resid = np.linalg.norm(pred_all - xyz, axis=1)
        mask = resid <= inlier_threshold_mm
        count = int(mask.sum())
        if count > best_count:
            best_count = count
            best_mask = mask

    if best_mask is None or best_count < min_samples:
        raise RuntimeError(f"ransac_fit: no candidate model reached >= min_samples "
                            f"({min_samples}) inliers over {n_iterations} iterations")

    final_params = fit_fn(t[best_mask], xyz[best_mask])
    pred_final = predict_fn(final_params, t[best_mask])
    resid_final = np.linalg.norm(pred_final - xyz[best_mask], axis=1)
    rms = float(np.sqrt(np.mean(resid_final ** 2)))

    accepted_idx = np.where(best_mask)[0]
    rejected_idx = np.where(~best_mask)[0]
    if frame_numbers is not None:
        accepted = [frame_numbers[i] for i in accepted_idx]
        rejected = [frame_numbers[i] for i in rejected_idx]
    else:
        accepted = accepted_idx.tolist()
        rejected = rejected_idx.tolist()

    return dict(params=final_params, residual_rms_mm=rms, n_inliers=int(best_count),
                accepted_frames=accepted, rejected_frames=rejected)


# ---- shared RANSAC configuration + per-model fit_fn/predict_fn factory ----
# One place both drag_k_discovery.py and trajectory_model_prediction_sweep.py
# pull from, so the two scripts' RANSAC layers stay consistent (same
# thresholds/seed/min_samples) without duplicating the closures.

RANSAC_INLIER_THRESHOLD_MM = 75.0  # task decision #2's literal value; see
# worklog for why this is kept as ONE value everywhere rather than
# special-cased per phase, after investigating and rejecting a per-phase
# alternative.
RANSAC_MIN_SAMPLES = {"A": 6, "B": 6, "C": 8}  # more than bare theoretical
# minimum (3/axis for A, 2/axis for B, 6 params for C's nonlinear fit),
# C given the most margin per this session's own established
# low-N-nonlinear-instability lesson (Phase 1 K discovery).
RANSAC_OUTLIER_FRACTION = 0.15  # assumed worst-case outlier fraction, ~2x
# the true ~8% (7/89) contamination rate empirically found on flight_22 --
# still conservative, but NOT the initially-chosen 0.3: at min_samples=8
# (Model C), e=0.3 needed 117 iterations, and each iteration is a full
# nonlinear fit_drag_given_k call -- timed at Phase 2's largest N (flight_22,
# N=89): ~13s PER (N, source) point, which extrapolates to ~30+ minutes for
# the full Phase 2 sweep, blowing through the task's ~10 minute budget by
# 3x+. Lowering to 0.15 (still 2x the known real rate, not reverse-fit to
# the answer) cuts Model C to 15 iterations, ~1s per point at the largest N
# -- verified in the worklog before committing to the full run.
RANSAC_SUCCESS_PROB = 0.99  # was 0.999; same timing-budget reasoning above --
# combined with the e change this brings Model C's iteration count from 117
# to 15 (an ~8x reduction) while remaining a principled RANSAC formula
# output, not an arbitrary round number.
RANSAC_SEED = 42

RANSAC_N_ITERATIONS = {
    model: ransac_n_iterations(RANSAC_MIN_SAMPLES[model], RANSAC_OUTLIER_FRACTION, RANSAC_SUCCESS_PROB)
    for model in RANSAC_MIN_SAMPLES
}


def build_model_fit_predict(model: str, g_fixed, k_fixed=None):
    """Returns (fit_fn, predict_fn) for the given model ("A"/"B"/"C"), for use
    with ransac_fit. Does NOT change what any model computes -- just wraps
    the existing fit_constant_accel / fit_constant_accel_fixed_g /
    fit_drag_given_k calls behind the uniform calling convention ransac_fit
    expects."""
    if model == "A":
        def fit_fn(t, xyz):
            return fit_constant_accel(t, xyz)

        def predict_fn(params, t_arr):
            p0, v0, a = params
            return np.array([predict_at(p0, v0, a, tt) for tt in t_arr])

    elif model == "B":
        def fit_fn(t, xyz):
            return fit_constant_accel_fixed_g(t, xyz, g_fixed)

        def predict_fn(params, t_arr):
            p0, v0 = params
            return np.array([predict_at_fixed_g(p0, v0, g_fixed, tt) for tt in t_arr])

    elif model == "C":
        if k_fixed is None:
            raise ValueError("Model C requires k_fixed")

        def fit_fn(t, xyz):
            p0_a, v0_a, _ = fit_constant_accel(t, xyz)
            p0, v0, _rms = fit_drag_given_k(t, xyz, k_fixed, g_fixed, p0_a, v0_a)
            return (p0, v0)

        def predict_fn(params, t_arr):
            p0, v0 = params
            return simulate_drag(p0, v0, k_fixed, g_fixed, t_arr)

    else:
        raise ValueError(f"unknown model {model!r}")

    return fit_fn, predict_fn
