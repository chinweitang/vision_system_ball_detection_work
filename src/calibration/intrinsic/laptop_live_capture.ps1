# Laptop-side live calibration capture.
# Run this from PowerShell (any working directory).
# Requires: OpenSSH for Windows (ssh, scp in PATH).
#
# Workflow:
#   1. Start pi_preview_loop.sh on the Pi first (separate SSH session).
#   2. Run this script, enter a distance label when prompted.
#   3. Open IrfanView on $LOCAL_PREVIEW, enable auto-refresh (View > Auto play/refresh > On).
#   4. Press keys to save labelled PNG frames locally (converted on the laptop).

$PI_USER = "chinnywei"
$PI_HOST = "192.168.50.1"
$SSH_KEY  = "$HOME\.ssh\id_volley"

# Local preview file - update IrfanView to watch this path.
$SCRIPT_ROOT   = Split-Path -Parent $MyInvocation.MyCommand.Path
$LOCAL_PREVIEW = [IO.Path]::GetFullPath((Join-Path $SCRIPT_ROOT "..\..\..\data\calibration_captures\preview.jpg"))
$OUTPUT_DIR    = [IO.Path]::GetFullPath((Join-Path $SCRIPT_ROOT "..\..\..\data\calibration_captures\distance_check"))
New-Item -ItemType Directory -Force -Path $OUTPUT_DIR | Out-Null

$CAM = "camA"  # cam0 = camA; change to camB when second camera is live

$positions = [ordered]@{
    'c' = 'center'
    '1' = 'topleft'
    '2' = 'topright'
    '3' = 'bottomleft'
    '4' = 'bottomright'
}

# -- Prompt --------------------------------------------------------------------
$distance = Read-Host "Distance label (e.g. 3m)"

Write-Host ""
Write-Host "Local preview : $LOCAL_PREVIEW"
Write-Host "Open IrfanView on that file with auto-refresh enabled."
Write-Host ""
Write-Host "Keys to save a frame:"
foreach ($k in $positions.Keys) {
    Write-Host ("  {0}  =>  {1}_{2}_{3}.png" -f $k, $CAM, $distance, $positions[$k])
}
Write-Host "  Q  =>  quit"
Write-Host ""

# -- Save function ---------------------------------------------------------------
$saved = @{}

function Save-Frame([string]$label) {
    $filename = "${CAM}_${distance}_${label}.png"
    $dest = Join-Path $OUTPUT_DIR $filename

    # Convert the already-synced local preview JPG to PNG right here on the
    # laptop - cv2 infers format from extension. Piped over stdin so no
    # quoting is needed for the paths.
    $py = "import cv2,sys; img=cv2.imread(r'$LOCAL_PREVIEW'); ok=img is not None and cv2.imwrite(r'$dest',img); sys.exit(0 if ok else 1)"

    Write-Host -NoNewline "  Saving ${filename} ... "
    $py | python -

    if ($LASTEXITCODE -eq 0) {
        $script:saved[$label] = $true
        Write-Host "OK"
    } else {
        Write-Host "FAILED (check local preview.jpg is present and readable)"
    }
}

# -- Status line -----------------------------------------------------------------
function Show-Status {
    $done = $positions.Values | Where-Object { $saved.ContainsKey($_) }
    $rem  = $positions.Values | Where-Object { -not $saved.ContainsKey($_) }
    $dStr = if ($done) { $done -join ', ' } else { "none" }
    $rStr = if ($rem)  { $rem  -join ', ' } else { "all done!" }
    Write-Host -NoNewline ("`r  [done: {0}]  [remaining: {1}]    " -f $dStr, $rStr)
}

# -- Main loop --------------------------------------------------------------------
# Poll every 100 ms; scp every 5th poll (0.5 s).
$iter = 0
while ($true) {
    if ($iter % 5 -eq 0) {
        scp -i $SSH_KEY -q "${PI_USER}@${PI_HOST}:~/captures/preview.jpg" "$LOCAL_PREVIEW" 2>$null
        Show-Status
    }

    if ([Console]::KeyAvailable) {
        $key  = [Console]::ReadKey($true)
        $char = $key.KeyChar.ToString().ToLower()

        if ($char -eq 'q') {
            Write-Host "`nSession ended."
            break
        }
        elseif ($positions.Contains($char)) {
            Write-Host ""
            Save-Frame $positions[$char]
            Show-Status
        }
    }

    $iter++
    Start-Sleep -Milliseconds 100
}
