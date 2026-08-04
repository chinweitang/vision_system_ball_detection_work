# compute_mask_rect_close_variant.py
#
# Shared rect-close-kernel variant of detector_core.compute_mask, extracted
# here (rather than duplicated inline) once a 3rd script needed it -- see
# claude_rules.md's "extract shared logic into an unnumbered module" rule.
# Consumers: 12_run_full_dataset_rect_close_kernel.py (accuracy validation,
# decision 64), the rect-detections CSV regenerator, and the rect-vs-ellipse
# prediction comparison. See claude/decision_log.md #63 for why this exists:
# the Pi real-time benchmark found detector_core.compute_mask's close-kernel
# morphology (cv2.MORPH_ELLIPSE, 30x30) is ~97% of the per-frame mask cost on
# the Pi; swapping to cv2.MORPH_RECT (same size) cuts it 17.6x.
#
# Does NOT modify detector_core.py -- installed via monkey-patching
# (dc.compute_mask = compute_mask_rect_close) from each consumer script, not
# by editing the file. detector_core.run_detection/_detect_in_pair resolve
# `compute_mask` via the module's own namespace at call time, so the patch
# takes effect throughout without any file changes.

from pathlib import Path
import sys

import cv2

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from src.image_processing.exclusion_mask import apply_exclusion  # noqa: E402  (matches detector_core.py's own import convention)


def compute_mask_rect_close(back, fwd, cam_name, diff_threshold, open_kernel, close_kernel):
    """Identical to detector_core.compute_mask except the CLOSE kernel is
    cv2.MORPH_RECT instead of cv2.MORPH_ELLIPSE (same size). Open kernel,
    threshold, and exclusion are byte-for-byte the same calls as production."""
    min_diff = cv2.min(back, fwd)
    _, mask = cv2.threshold(min_diff, diff_threshold, 255, cv2.THRESH_BINARY)

    if open_kernel and open_kernel > 0:
        open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_kernel, open_kernel))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, open_k)
    if close_kernel and close_kernel > 0:
        close_k = cv2.getStructuringElement(cv2.MORPH_RECT, (close_kernel, close_kernel))  # <-- the one change
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_k)

    return apply_exclusion(mask, cam_name)
