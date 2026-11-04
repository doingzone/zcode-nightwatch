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
    [string]$TaskName = "ZCodeNightwatch",
    [string]$ZcodeDataDir = "",
    [switch]$NoCliShim
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

# --- resolve ZCode.exe: param > existing config > registry > common paths ---
# Re-run friendliness: preserve values that cannot be re-detected when the
# caller left the parameter at its default (empty string).
$cfgPath = Join-Path $PSScriptRoot "nightwatch.json"
$existing = $null
if (Test-Path $cfgPath) {
    try { $existing = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $existing = $null }
}
if (-not $ZcodeExe -and $existing -and $existing.zcode_exe) { $ZcodeExe = $existing.zcode_exe }
if (-not $ZcodeDataDir -and $existing -and $existing.zcode_data_dir) { $ZcodeDataDir = $existing.zcode_data_dir }

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
# zcode_data_dir: ZCode desktop data dir (v2\logs and tasks-index.sqlite live
# there) - defaults to %USERPROFILE%\.zcode; override with -ZcodeDataDir.
if (-not $ZcodeDataDir) {
    $ZcodeDataDir = Join-Path $env:USERPROFILE ".zcode"
}
$parts = $NightWindow -split "-"
$config = [ordered]@{
    zcode_exe          = $ZcodeExe
    zcode_data_dir     = $ZcodeDataDir
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

# --- global CLI shim: `nightwatch` prints the effectiveness report in any terminal ---
if (-not $NoCliShim) {
    $pyDir = Split-Path $pyPath
    $shim = Join-Path $pyDir "nightwatch.cmd"
    $reportPy = Join-Path $PSScriptRoot "nightwatch_report.py"
    $pyConsole = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    $shimBody = "@echo off`r`nchcp 65001 >nul`r`nset PYTHONIOENCODING=utf-8`r`n`"$pyConsole`" `"$reportPy`" %*"
    Set-Content -Path $shim -Value $shimBody -Encoding ASCII
    Write-Host "     cli shim  : nightwatch (report, utf-8) -> $shim"
}
Write-Host "     remove with: uninstall-nightwatch.ps1 -TaskName $TaskName"
