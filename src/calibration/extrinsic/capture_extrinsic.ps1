# Laptop-side extrinsic (stereo) calibration capture.
# Run this from PowerShell (any working directory).
# Requires: OpenSSH for Windows (ssh, scp in PATH). Pi needs rpicam-still.
#
# Workflow:
#   1. Copy pi_preview_loop_stereo.sh to the Pi once (or after any edit to it):
#      `scp -i $HOME\.ssh\id_volley pi_preview_loop_stereo.sh chinnywei@192.168.50.1:~/captures/`
#      Then start it on the Pi (separate SSH session):
#      `bash ~/captures/pi_preview_loop_stereo.sh`
#      It keeps both ~/captures/preview_cam0.jpg and preview_cam1.jpg
#      refreshed for aiming, and is the only thing allowed to touch either
#      camera - this script signals it via per-camera request flags rather
#      than launching a second rpicam-still on the same camera (which would
#      fail with "Device or resource busy" while the preview loop owns it).
#   2. Run this script. Open TWO IrfanView windows, one on $LOCAL_PREVIEW_CAM0
#      and one on $LOCAL_PREVIEW_CAM1, both with auto-refresh enabled
#      (View > Auto play/refresh > On), so you can watch both feeds at once.
#   3. Before every capture, confirm the checkerboard is FULLY VISIBLE IN
#      BOTH views. A pose where the board is cut off in either camera is
#      useless for stereo calibration - skip it.
#   4. Press SPACE to capture a matched PAIR of full-res lossless PNGs (one
#      fresh shot per camera, same pose index in both cam0/ and cam1/).
#      HOLD THE BOARD STILL for ~2s after pressing - the fresh PNG capture
#      on each camera plus the two scp downloads takes a moment.
#   5. Press D to delete the most recently saved pair (bad or cut-off pose).
#   6. Press Q to quit. Vary the TILT of the board between poses, not just
#      its position in one plane - stereoCalibrate needs rotation coverage.

$PI_USER = "chinnywei"
$PI_HOST = "192.168.50.1"
$SSH_KEY = "$HOME\.ssh\id_volley"

$CAMS = @(
    @{ Index = 0; Name = "cam0" },
    @{ Index = 1; Name = "cam1" }
)

# Local preview files - point one IrfanView window at each. Aiming only;
# never saved as calibration frames.
$SCRIPT_ROOT   = Split-Path -Parent $MyInvocation.MyCommand.Path
$CAPTURE_ROOT  = [IO.Path]::GetFullPath((Join-Path $SCRIPT_ROOT "..\..\..\data\calibration_captures\extrinsic"))
$LOCAL_PREVIEW_CAM0 = Join-Path $CAPTURE_ROOT "preview_cam0.jpg"
$LOCAL_PREVIEW_CAM1 = Join-Path $CAPTURE_ROOT "preview_cam1.jpg"

New-Item -ItemType Directory -Force -Path $CAPTURE_ROOT | Out-Null
foreach ($cam in $CAMS) {
    $cam.OutputDir = Join-Path $CAPTURE_ROOT $cam.Name
    New-Item -ItemType Directory -Force -Path $cam.OutputDir | Out-Null
}

# -- Resume pair count from any frames already on disk ---------------------------
# The index must match across cam0/cam1, so resume from the lowest count
# present in either folder (a mismatch would mean a previous run was
# interrupted mid-pair - trust the smaller side).
function Get-MaxIndex([string]$dir) {
    $maxIndex = 0
    foreach ($f in Get-ChildItem -Path $dir -Filter "img_*.png" -ErrorAction SilentlyContinue) {
        if ($f.BaseName -match '^img_(\d+)$') {
            $n = [int]$Matches[1]
            if ($n -gt $maxIndex) { $maxIndex = $n }
        }
    }
    return $maxIndex
}

$counts = @($CAMS | ForEach-Object { Get-MaxIndex $_.OutputDir })
# Cast explicitly: Measure-Object -Minimum returns a [double], and the "D4"
# format specifier below only accepts integer types.
[int]$pairCount = ($counts | Measure-Object -Minimum).Minimum
$lastFile = if ($pairCount -gt 0) { "img_{0:D4}.png" -f $pairCount } else { "none" }

Write-Host ""
Write-Host "cam0 (camera 0) output : $($CAMS[0].OutputDir)"
Write-Host "cam1 (camera 1) output : $($CAMS[1].OutputDir)"
Write-Host "Local previews         : $LOCAL_PREVIEW_CAM0"
Write-Host "                         $LOCAL_PREVIEW_CAM1"
Write-Host "Open one IrfanView window on each, auto-refresh enabled."
Write-Host ""
Write-Host "  SPACE  =>  capture matched stereo pair (hold board still ~2s)"
Write-Host "  D      =>  delete last pair"
Write-Host "  Q      =>  quit"
Write-Host ""
Write-Host "Reminder: confirm the board is FULLY VISIBLE in BOTH previews before"
Write-Host "capturing, and vary the TILT between poses - not just position."
Write-Host ""

$REMOTE_DIR = "/home/chinnywei/captures"

# -- Capture / delete functions ---------------------------------------------------
function Capture-Pair {
    [int]$index = $script:pairCount + 1
    $filename = "img_{0:D4}.png" -f $index

    Write-Host ""
    Write-Host "  Capturing $filename (cam0 + cam1) ... HOLD THE BOARD STILL for ~2s"

    # Sequential per-camera signalling: cameras are independent sensors and
    # concurrent one-shot captures were verified to work, but sustained
    # concurrent loops occasionally raced - sequential keeps the calibration
    # PNGs contention-free, and the board is static so the extra ~1s costs
    # nothing.
    foreach ($cam in $CAMS) {
        $camIdx = $cam.Index
        $request = "$REMOTE_DIR/capture_request_cam$camIdx"
        $result  = "$REMOTE_DIR/capture_result_cam$camIdx.png"
        $localDest = Join-Path $cam.OutputDir $filename

        ssh -i $SSH_KEY "${PI_USER}@${PI_HOST}" "rm -f $result; touch $request"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  FAILED ($($cam.Name)): could not signal capture request - is pi_preview_loop_stereo.sh running?"
            return
        }

        $gotResult = $false
        for ($attempt = 0; $attempt -lt 8; $attempt++) {
            Start-Sleep -Milliseconds 500
            scp -i $SSH_KEY -q "${PI_USER}@${PI_HOST}:${result}" "$localDest" 2>$null
            if (Test-Path $localDest -PathType Leaf) { $gotResult = $true; break }
        }

        if (-not $gotResult) {
            Write-Host "  FAILED ($($cam.Name)): no result from Pi - is pi_preview_loop_stereo.sh running?"
            return
        }
    }

    $script:pairCount = $index
    $script:lastFile = $filename
    Write-Host "  Saved pair $filename (cam0 + cam1)"
}

function Remove-LastPair {
    if ($script:pairCount -le 0) {
        Write-Host ""
        Write-Host "  Nothing to delete."
        return
    }

    $filename = "img_{0:D4}.png" -f $script:pairCount
    foreach ($cam in $CAMS) {
        $path = Join-Path $cam.OutputDir $filename
        if (Test-Path $path) {
            Remove-Item -Force $path
        }
    }
    Write-Host ""
    Write-Host "  Deleted pair $filename (cam0 + cam1)"

    $script:pairCount--
    $script:lastFile = if ($script:pairCount -gt 0) { "img_{0:D4}.png" -f $script:pairCount } else { "none" }
}

# -- Status line -----------------------------------------------------------------
function Show-Status {
    Write-Host -NoNewline ("`r  captured {0} pairs   last: {1}     " -f $script:pairCount, $script:lastFile)
}

# -- Main loop --------------------------------------------------------------------
# Poll every 100 ms; scp both aiming previews every 5th poll (0.5 s).
$iter = 0
while ($true) {
    if ($iter % 5 -eq 0) {
        scp -i $SSH_KEY -q "${PI_USER}@${PI_HOST}:${REMOTE_DIR}/preview_cam0.jpg" "$LOCAL_PREVIEW_CAM0" 2>$null
        scp -i $SSH_KEY -q "${PI_USER}@${PI_HOST}:${REMOTE_DIR}/preview_cam1.jpg" "$LOCAL_PREVIEW_CAM1" 2>$null
        Show-Status
    }

    if ([Console]::KeyAvailable) {
        $key = [Console]::ReadKey($true)

        if ($key.Key -eq [ConsoleKey]::Spacebar) {
            Capture-Pair
            Show-Status
        }
        elseif ($key.KeyChar.ToString().ToLower() -eq 'd') {
            Remove-LastPair
            Show-Status
        }
        elseif ($key.KeyChar.ToString().ToLower() -eq 'q') {
            Write-Host "`nSession ended. Captured $pairCount pairs."
            break
        }
    }

    $iter++
    Start-Sleep -Milliseconds 100
}
