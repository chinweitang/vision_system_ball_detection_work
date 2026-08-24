# run_pi_benchmark.ps1
#
# Laptop-side orchestrator for the Pi real-time benchmark (Stage 1). Builds a
# local staging tree that mirrors the real repo's relevant paths exactly
# (src/, calibration_outputs/, data/) so every reused module's own internal
# REPO_ROOT-relative path logic (detector_core.py, all_flights_common.py,
# pixel_velocity_correction.py, etc.) resolves unmodified on the Pi -- see
# claude/claude_logs/2026-08-03_pi_realtime_benchmark_worklog.md for why this
# mirroring approach was chosen over flattening files into one folder.
#
# Follows the existing capture_intrinsic.ps1 / capture_extrinsic.ps1 pattern:
# $SSH_KEY, PI_USER/PI_HOST, scp code+data over, ssh-run, scp results back.
# Only ever writes into a NEW ~/benchmark/ folder on the Pi -- never touches
# ~/captures/ or anything else already there.

$ErrorActionPreference = "Stop"

$SSH_KEY  = "$HOME\.ssh\id_volley"
$PI_USER  = "chinnywei"
$PI_HOST  = "192.168.50.1"
$PI       = "${PI_USER}@${PI_HOST}"
$REMOTE_BENCHMARK = "~/benchmark"
$REMOTE_MIRROR    = "$REMOTE_BENCHMARK/mirror"
$REMOTE_VENV_PY   = "$REMOTE_BENCHMARK/venv/bin/python3"

$REPO_ROOT = (Resolve-Path "$PSScriptRoot\..\..").Path
$STAGING   = "$env:TEMP\pi_benchmark_staging"

$FLIGHTS = @(
    @{ session = "2026_07_21_gym"; flight = "flight_17" },
    @{ session = "2026_07_21_gym"; flight = "flight_63" },
    @{ session = "2026_07_21_gym"; flight = "flight_40" },
    @{ session = "2026_07_21_gym"; flight = "flight_59" },
    @{ session = "2026_07_15_gym"; flight = "flight_59" },
    @{ session = "2026_07_15_gym"; flight = "flight_52" },
    @{ session = "2026_07_15_gym"; flight = "flight_45" },
    @{ session = "2026_07_15_gym"; flight = "flight_15" }
)

Write-Host "=== 1. Building local staging tree at $STAGING ===" -ForegroundColor Cyan
if (Test-Path $STAGING) { Remove-Item -Recurse -Force $STAGING }
New-Item -ItemType Directory -Force -Path $STAGING | Out-Null

function Copy-Rel($relPath) {
    $src = Join-Path $REPO_ROOT $relPath
    $dst = Join-Path $STAGING $relPath
    New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
    Copy-Item $src $dst -Force
}

# -- reused code (unmodified) --
Copy-Rel "src\image_processing\exclusion_mask.py"
Copy-Rel "src\image_processing\02_adjacent_frame_differencing\detector_core.py"
Copy-Rel "src\stereo\trajectory_fit.py"
Copy-Rel "src\stereo\label_vs_detection.py"
Copy-Rel "src\stereo\pixel_velocity_correction.py"
Copy-Rel "src\stereo\stereo_flight_sync_table.py"
Copy-Rel "src\stereo\all_flights_common.py"

# -- new benchmark code --
Copy-Rel "src\pi_benchmarking\benchmark_pipeline_pi.py"
Copy-Rel "src\pi_benchmarking\flights_manifest.json"

# -- calibration --
Copy-Rel "calibration_outputs\cam0_intrinsics_fisheye.npz"
Copy-Rel "calibration_outputs\cam1_intrinsics_fisheye.npz"
Copy-Rel "calibration_outputs\2026_07_21\test2\stereo_extrinsic.npz"
Copy-Rel "calibration_outputs\2026_07_15\stereo_extrinsic.npz"

# -- shared config --
Copy-Rel "results\detector_tuning\candidate_config.json"
Copy-Rel "results\trajectory_fit_comparison\all_flights\phase1\pooled_k.txt"

# -- world-frame registration (g_fixed source) --
Copy-Rel "data\2026_07_21_gym\flight_binning\world_frame_validation\registration1_world_transform.npz"
Copy-Rel "data\2026_07_21_gym\flight_binning\world_frame_validation\registration2_world_transform.npz"
Copy-Rel "data\2026_07_15_gym\flight_binning\world_frame_validation\registration_world_transform.npz"

# -- per-flight frames + timestamps --
foreach ($f in $FLIGHTS) {
    $base = "data\$($f.session)\ball_flights\$($f.flight)"
    Write-Host "  staging $base ..."
    Copy-Item (Join-Path $REPO_ROOT "$base\timestamps.csv") `
              (New-Item -ItemType Directory -Force -Path (Join-Path $STAGING $base)).FullName -Force
    foreach ($cam in @("cam0", "cam1")) {
        $srcDir = Join-Path $REPO_ROOT "$base\$cam\ball_in_frame"
        $dstDir = Join-Path $STAGING "$base\$cam\ball_in_frame"
        New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
        Copy-Item "$srcDir\*.png" $dstDir -Force
    }
}

Write-Host "=== 2. Transferring staging tree to Pi ($REMOTE_MIRROR) ===" -ForegroundColor Cyan
ssh -i $SSH_KEY $PI "mkdir -p $REMOTE_BENCHMARK && rm -rf $REMOTE_MIRROR"
scp -i $SSH_KEY -r $STAGING "${PI}:${REMOTE_MIRROR}"

Write-Host "=== 3. Running benchmark on the Pi ===" -ForegroundColor Cyan
$remoteOut = "$REMOTE_BENCHMARK/results/stage1_results.json"
ssh -i $SSH_KEY $PI "$REMOTE_VENV_PY $REMOTE_MIRROR/src/pi_benchmarking/benchmark_pipeline_pi.py --flights $REMOTE_MIRROR/src/pi_benchmarking/flights_manifest.json --out $remoteOut"

Write-Host "=== 4. Pulling results back ===" -ForegroundColor Cyan
$localOutDir = Join-Path $REPO_ROOT "results\pi_benchmarking"
New-Item -ItemType Directory -Force -Path $localOutDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmm"
$localOut = Join-Path $localOutDir "stage1_results_$stamp.json"
scp -i $SSH_KEY "${PI}:${remoteOut}" $localOut

Write-Host "Done. Results at $localOut" -ForegroundColor Green
