import cv2
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "data/calibration_captures/distance_check"
OUTPUT_DIR = INPUT_DIR / "corners"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Internal corners of the chessboard (columns, rows) — adjust if board differs
PATTERN_SIZE = (7, 11)

image_paths = sorted(INPUT_DIR.glob("*.png")) + sorted(INPUT_DIR.glob("*.jpg"))
if not image_paths:
    raise FileNotFoundError(f"No images found in: {INPUT_DIR}")

results = []
for image_path in image_paths:
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"{image_path.name}: could not read image")
        results.append((image_path.name, False))
        continue

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCorners(gray, PATTERN_SIZE)
    print(f"{image_path.name}: found={found}")
    results.append((image_path.name, found))

    if found:
        cv2.drawChessboardCorners(img, PATTERN_SIZE, corners, found)
        output_path = OUTPUT_DIR / f"{image_path.stem}_corners.png"
        cv2.imwrite(str(output_path), img)

print()
print(f"{sum(1 for _, found in results if found)}/{len(results)} chessboards found")
print(f"Annotated images saved to: {OUTPUT_DIR}")
