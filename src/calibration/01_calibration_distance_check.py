import cv2
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT_IMAGE = ROOT / "data/calibration_captures/cam0_test.jpg"
OUTPUT_DIR = ROOT / "data/calibration_captures"

# Internal corners of the chessboard (columns, rows) — adjust if board differs
PATTERN_SIZE = (7, 11)

img = cv2.imread(str(INPUT_IMAGE))
if img is None:
    raise FileNotFoundError(f"Could not read image: {INPUT_IMAGE}")

gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

found, corners = cv2.findChessboardCorners(gray, PATTERN_SIZE)
print("Found:", found)

if found:
    cv2.drawChessboardCorners(img, PATTERN_SIZE, corners, found)
    output_path = OUTPUT_DIR / "cam0_test_corners.jpg"
    cv2.imwrite(str(output_path), img)
    print(f"Saved annotated image to: {output_path}")
else:
    print("Chessboard not detected — check PATTERN_SIZE or image quality.")
