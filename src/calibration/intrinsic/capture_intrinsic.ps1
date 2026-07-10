# Laptop-side intrinsic calibration capture.
# Run this from PowerShell (any working directory).
# Requires: OpenSSH for Windows (ssh, scp in PATH). Pi needs rpicam-still.
#
# Workflow:
#   1. Start pi_preview_loop.sh on the Pi first (separate SSH session), e.g.
#      `bash ~/captures/pi_preview_loop.sh 0` - matching camera index to $CAM
#      below. It keeps ~/captures/preview.jpg refreshed for aiming, AND is the
#      only process allowed to touch the camera: this script signals it via a
#      request flag rather than launching a second rpicam-still (which would
#      fail with "Device or resource busy" while the preview loop is running).
#   2. Set $CAM below to "camA" (camera 0) or "camB" (camera 1).
#   3. Run this script. Open IrfanView on $LOCAL_PREVIEW, enable auto-refresh
#      (View > Auto play/refresh > On) to aim the board.
#   4. Press SPACE to capture a full-res lossless PNG frame for the
#      calibration set. HOLD THE BOARD STILL for ~2s after pressing - the
#      fresh capture + scp download takes a moment.
#   5. Press D to delete the most recently saved frame (bad pose, blur, etc).
#   6. Press Q to quit. Aim for 30 frames covering varied poses/positions.

$PI_USER = "chinnywei"
$PI_HOST = "192.168.50.1"
$SSH_KEY = "$HOME\.ssh\id_volley"

$TARGET_COUNT = 30

$CAM = "camB"  # camA = camera 0, camB = camera 1
$CAM_INDEX = if ($CAM -eq "camA") { 0 } else { 1 }

# Local preview file - update IrfanView to watch this path. Aiming only;
# never saved as a calibration frame.
$SCRIPT_ROOT   = Split-Path -Parent $MyInvocation.MyCommand.Path
$LOCAL_PREVIEW = [IO.Path]::GetFullPath((Join-Path $SCRIPT_ROOT "..\..\..\data\calibration_captures\preview.jpg"))
$OUTPUT_DIR    = [IO.Path]::GetFullPath((Join-Path $SCRIPT_ROOT "..\..\..\data\calibration_captures\calib_intrinsic_$CAM"))
New-Item -ItemType Directory -Force -Path $OUTPUT_DIR | Out-Null

$REMOTE_REQUEST = "/home/chinnywei/captures/capture_request"
$REMOTE_RESULT  = "/home/chinnywei/captures/capture_result.png"

# -- Resume frame count from any frames already on disk -------------------------
$frameCount = 0
foreach ($f in Get-ChildItem -Path $OUTPUT_DIR -Filter "img_*.png" -ErrorAction SilentlyContinue) {
    if ($f.BaseName -match '^img_(\d+)$') {
        $n = [int]$Matches[1]
        if ($n -gt $frameCount) { $frameCount = $n }
    }
}
$lastFile = if ($frameCount -gt 0) { "img_{0:D4}.png" -f $frameCount } else { "none" }

Write-Host ""
Write-Host "Camera        : $CAM (index $CAM_INDEX)"
Write-Host "Output folder : $OUTPUT_DIR"
Write-Host "Local preview : $LOCAL_PREVIEW"
Write-Host "Open IrfanView on that file with auto-refresh enabled."
Write-Host ""
Write-Host "  SPACE  =>  capture frame (hold board still ~2s)"
Write-Host "  D      =>  delete last frame"
Write-Host "  Q      =>  quit"
Write-Host ""

# -- Capture / delete functions ---------------------------------------------------
function Capture-Frame {
    $index = $script:frameCount + 1
    $filename = "img_{0:D4}.png" -f $index
    $localDest = Join-Path $OUTPUT_DIR $filename

    Write-Host ""
    Write-Host "  Capturing $filename ... HOLD THE BOARD STILL for ~2s"

    # Signal the running pi_preview_loop.sh to take the next shot at full
    # res/quality instead of racing it for the camera device.
    ssh -i $SSH_KEY "${PI_USER}@${PI_HOST}" "rm -f $REMOTE_RESULT; touch $REMOTE_REQUEST"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  FAILED (could not signal capture request - is pi_preview_loop.sh running?)"
        return
    }

    $gotResult = $false
    for ($attempt = 0; $attempt -lt 8; $attempt++) {
        Start-Sleep -Milliseconds 500
        scp -i $SSH_KEY -q "${PI_USER}@${PI_HOST}:${REMOTE_RESULT}" "$localDest" 2>$null
        if (Test-Path $localDest) { $gotResult = $true; break }
    }

    if (-not $gotResult) {
        Write-Host "  FAILED (no result from Pi - is pi_preview_loop.sh running?)"
        return
    }

    $script:frameCount = $index
    $script:lastFile = $filename
    Write-Host "  Saved $filename"
}

function Remove-LastFrame {
    if ($script:frameCount -le 0) {
        Write-Host ""
        Write-Host "  Nothing to delete."
        return
    }

    $filename = "img_{0:D4}.png" -f $script:frameCount
    $path = Join-Path $OUTPUT_DIR $filename
    if (Test-Path $path) {
        Remove-Item -Force $path
        Write-Host ""
        Write-Host "  Deleted $filename"
    }

    $script:frameCount--
    $script:lastFile = if ($script:frameCount -gt 0) { "img_{0:D4}.png" -f $script:frameCount } else { "none" }
}

# -- Status line -----------------------------------------------------------------
function Show-Status {
    Write-Host -NoNewline ("`r  captured {0} / {1}   last: {2}     " -f $script:frameCount, $TARGET_COUNT, $script:lastFile)
}

# -- Main loop --------------------------------------------------------------------
# Poll every 100 ms; scp the aiming preview every 5th poll (0.5 s).
$iter = 0
while ($true) {
    if ($iter % 5 -eq 0) {
        scp -i $SSH_KEY -q "${PI_USER}@${PI_HOST}:~/captures/preview.jpg" "$LOCAL_PREVIEW" 2>$null
        Show-Status
    }

    if ([Console]::KeyAvailable) {
        $key = [Console]::ReadKey($true)

        if ($key.Key -eq [ConsoleKey]::Spacebar) {
            Capture-Frame
            Show-Status
        }
        elseif ($key.KeyChar.ToString().ToLower() -eq 'd') {
            Remove-LastFrame
            Show-Status
        }
        elseif ($key.KeyChar.ToString().ToLower() -eq 'q') {
            Write-Host "`nSession ended. Captured $frameCount / $TARGET_COUNT frames."
            break
        }
    }

    $iter++
    Start-Sleep -Milliseconds 100
}
