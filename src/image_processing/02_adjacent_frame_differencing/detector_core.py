# detector_core.py
#
# The 3-frame min-diff ball detector from 04_stereo_three_frame_diff.py,
# extracted into a parameterized, importable function so it can be called
# in-process by a parameter sweep (06_param_sweep.py) without repeatedly
# editing constants + spawning a fresh interpreter per run.
#
# Logic is unchanged from 04_stereo_three_frame_diff.py: threshold(min(back,
# fwd)) -> open -> close -> exclusion mask -> contour filter (area, circ) ->
# largest-by-area candidate. Only the tunable constants have become
# parameters.

from pathlib import Path
import sys
import numpy as np
import cv2

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT))
from src.image_processing.exclusion_mask import apply_exclusion

FRAME_STEM_RE = None  # set below to avoid importing re at module scope twice
import re
FRAME_STEM_RE = re.compile(r"frame_(\d+)$")


def compute_mask(back, fwd, cam_name, diff_threshold, open_kernel, close_kernel):
    """threshold(min(back,fwd)) -> open -> close -> exclusion mask."""
    min_diff = cv2.min(back, fwd)
    _, mask = cv2.threshold(min_diff, diff_threshold, 255, cv2.THRESH_BINARY)

    if open_kernel and open_kernel > 0:
        open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_kernel, open_kernel))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_k)
    if close_kernel and close_kernel > 0:
        close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_kernel, close_kernel))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_k)

    return apply_exclusion(mask, cam_name)


def extract_candidates(mask, min_area, max_area, min_circ):
    """Contour filter (area, circularity) -> list of {u,v,area,circ,contour}."""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area or area > max_area:
            continue
        perim = cv2.arcLength(c, True)
        if perim == 0:
            continue
        circ = 4 * np.pi * area / (perim * perim)
        if circ < min_circ:
            continue
        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        candidates.append({"u": M["m10"] / M["m00"], "v": M["m01"] / M["m00"],
                            "area": area, "circ": circ, "contour": c})
    return candidates


def _detect_in_pair(back, fwd, cam_name, diff_threshold, open_kernel, close_kernel,
                     min_area, max_area, min_circ):
    mask = compute_mask(back, fwd, cam_name, diff_threshold, open_kernel, close_kernel)
    candidates = extract_candidates(mask, min_area, max_area, min_circ)
    if not candidates:
        return None
    best = max(candidates, key=lambda d: d["area"])
    return (best["u"], best["v"])


def processable_frame_numbers(cam_dir: Path, stride: int) -> set:
    """Frame numbers actually evaluated by the 3-frame diff for this stride:
    sorted ball_in_frame frames with `stride` dropped from each end, by
    position (matches the `for i in range(stride, len-stride)` loop)."""
    frame_paths = sorted(cam_dir.glob("frame_*.png"))
    if len(frame_paths) <= 2 * stride:
        return set()
    kept = frame_paths[stride: len(frame_paths) - stride]
    return {int(FRAME_STEM_RE.search(p.stem).group(1)) for p in kept}


def filter_trajectory_outliers(detections: dict, max_speed_px_per_frame: float = 80.0,
                                min_run_length: int = 2, max_passes: int = 5) -> dict:
    """Reject candidate detections that can't be part of a real flight path.

    A real ball can only move so far between frames; static false positives
    (light fixtures, exit signs, wall corners that only surface at loose
    threshold/kernel settings) sit at a near-fixed pixel location and show up
    as implausible jumps to and from whatever real detections surround them.

    Two earlier approaches were tried and rejected: (1) a single global
    degree-2 polyfit with iterative residual trimming could have its very
    first fit pulled badly off course if enough of the raw detections were
    severe outliers, misclassifying nearly everything in one bad pass; (2)
    comparing each point to the *position* median of its nearby neighbors
    falsely rejected real fast-moving points early in a flight, where the
    ball's own genuine motion across the neighbor window was larger than the
    rejection tolerance; (3) simply splitting into runs at every implausible
    jump and keeping only long-enough runs falsely discarded the real
    trajectory too, when false positives were frequent enough (~every 3
    frames) to fragment it into many runs individually shorter than
    `min_run_length`.

    This version explicitly DE-SPIKES first: repeatedly finds a single point
    whose neighbors-in-time both look implausible relative to it, but whose
    *previous and next surviving points* would reconnect at a plausible
    speed if this one point were skipped - i.e. a lone spike, not a genuine
    break in the trajectory - and drops just that point. Repeats up to
    `max_passes` times (dropping one spike can reveal another). Only after
    de-spiking is the remainder split into runs at any still-implausible
    jump (a genuine gap we can't bridge), keeping runs with at least
    `min_run_length` points.
    """
    frames = sorted(detections)
    pts = {f: detections[f] for f in frames}

    def speed(fa, fb):
        gap = fb - fa
        d = ((pts[fb][0] - pts[fa][0]) ** 2 + (pts[fb][1] - pts[fa][1]) ** 2) ** 0.5
        return d / max(gap, 1)

    for _ in range(max_passes):
        if len(frames) < 3:
            break
        kept = [frames[0]]
        removed_any = False
        for i in range(1, len(frames) - 1):
            prev_f, cur_f, next_f = kept[-1], frames[i], frames[i + 1]
            s_prev = speed(prev_f, cur_f)
            s_next = speed(cur_f, next_f)
            s_skip = speed(prev_f, next_f)
            if (s_prev > max_speed_px_per_frame or s_next > max_speed_px_per_frame) and \
                    s_skip <= max_speed_px_per_frame:
                removed_any = True
                continue  # drop cur_f - skipping it reconnects prev/next fine
            kept.append(cur_f)
        kept.append(frames[-1])
        frames = kept
        if not removed_any:
            break

    if len(frames) < 2:
        return {f: pts[f] for f in frames}

    runs = [[frames[0]]]
    for i in range(1, len(frames)):
        if speed(frames[i - 1], frames[i]) <= max_speed_px_per_frame:
            runs[-1].append(frames[i])
        else:
            runs.append([frames[i]])

    kept_frames = [f for run in runs if len(run) >= min_run_length for f in run]
    return {f: pts[f] for f in kept_frames}


def run_detection(cam_dir: Path, cam_name: str, stride: int, diff_threshold: int,
                   open_kernel: int, close_kernel: int, min_area: float, max_area: float,
                   min_circ: float) -> dict:
    """Run the 3-frame min-diff detector over every processable frame in
    cam_dir (a ball_in_frame folder). Returns {frame_number: (u, v)}."""
    frame_paths = sorted(cam_dir.glob("frame_*.png"))
    detections = {}
    if len(frame_paths) <= 2 * stride:
        return detections

    imgs = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in frame_paths]

    for i in range(stride, len(frame_paths) - stride):
        back = cv2.absdiff(imgs[i], imgs[i - stride])
        fwd = cv2.absdiff(imgs[i + stride], imgs[i])
        best = _detect_in_pair(back, fwd, cam_name, diff_threshold, open_kernel,
                                close_kernel, min_area, max_area, min_circ)
        if best is not None:
            frame_num = int(FRAME_STEM_RE.search(frame_paths[i].stem).group(1))
            detections[frame_num] = best

    return detections
