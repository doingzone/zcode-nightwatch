# ZCode Nightwatch installer: writes nightwatch.json and registers the
# scheduled task. Imperceptible by design - task action is pythonw.exe
# (windowless) and zcode_nightwatch.py spawns all children with
# CREATE_NO_WINDOW.
#
# Usage (from any shell):
#   powershell -NoProfile -ExecutionPolicy Bypass -File install-nightwatch.ps1
# Optional params:
#   -ZcodeExe "D:\path\to\ZCode.exe"   # auto-detected when omitted
#   -NightWindow "23:00-09:00" -IntervalMinutes 30 -HangThresholdMin 15

param(
    [string]$ZcodeExe = "",
    [string]$NightWindow = "23:00-09:00",
    [int]$IntervalMinutes = 30,
    [int]$HangThresholdMin = 15,
    [string]$TaskName = "ZCodeNightwatch"
)

$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "zcode_nightwatch.py"

# --- resolve pythonw.exe (windowless interpreter) ---
$pyw = Get-Command pythonw.exe -ErrorAction SilentlyContinue
if ($pyw) {
    $pyPath = $pyw.Source
} else {
    $pyc = (Get-Command python.exe -ErrorAction Stop).Source
    $candidate = Join-Path (Split-Path $pyc) "pythonw.exe"
    if (-not (Test-Path $candidate)) { Write-Error "pythonw.exe not found"; exit 1 }
    $pyPath = $candidate
}

# --- resolve ZCode.exe: param > registry (NSIS uninstall entries) > common paths ---
# NSIS/electron-builder uninstall entries often leave InstallLocation EMPTY -
# derive the install dir from UninstallString / DisplayIcon instead.
if (-not $ZcodeExe) {
    $uninstallRoots = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    $entry = Get-ItemProperty $uninstallRoots -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like "*ZCode*" } | Select-Object -First 1
    if ($entry) {
        foreach ($field in @($entry.UninstallString, $entry.DisplayIcon)) {
            if (-not $field) { continue }
            $p = $field.Trim()
            if ($p.StartsWith('"')) { $p = $p.Split('"')[1] }
            if (-not (Test-Path $p)) { continue }
            # file (uninstaller exe / icon) -> its dir should contain ZCode.exe
            foreach ($dir in @((Split-Path $p), (Split-Path (Split-Path $p)))) {
                $cand = Join-Path $dir "ZCode.exe"
                if (Test-Path $cand) { $ZcodeExe = $cand; break }
            }
            if ($ZcodeExe) { break }
        }
    }
}
if (-not $ZcodeExe) {
    $cand = Join-Path $env:LOCALAPPDATA "Programs\ZCode\ZCode.exe"
    if (Test-Path $cand) { $ZcodeExe = $cand }
}
if (-not $ZcodeExe -or -not (Test-Path $ZcodeExe)) {
    Write-Error "ZCode.exe not found - pass -ZcodeExe explicitly."
    exit 1
}

# --- write config next to the script ---
$parts = $NightWindow -split "-"
$config = [ordered]@{
    zcode_exe          = $ZcodeExe
    window             = @($parts[0].Trim(), $parts[1].Trim())
    hang_threshold_min = $HangThresholdMin
}
$config | ConvertTo-Json | Set-Content -Path (Join-Path $PSScriptRoot "nightwatch.json") -Encoding UTF8

# --- register the scheduled task (interactive session: os.startfile must land
# on the user's desktop, so no S4U / no "whether logged on" mode) ---
$tr = "`"$pyPath`" `"$script`""
schtasks /Create /TN $TaskName /TR $tr /SC MINUTE /MO $IntervalMinutes /F
if ($LASTEXITCODE -ne 0) { Write-Error "schtasks failed ($LASTEXITCODE)"; exit $LASTEXITCODE }

Write-Host "[OK] $TaskName registered (every $IntervalMinutes min, silent)"
Write-Host "     zcode_exe : $ZcodeExe"
Write-Host "     window    : $NightWindow  hang threshold: ${HangThresholdMin} min"
Write-Host "     config    : $(Join-Path $PSScriptRoot 'nightwatch.json')"
Write-Host "     remove with: uninstall-nightwatch.ps1 -TaskName $TaskName"
