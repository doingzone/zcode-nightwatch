# Removes the ZCode Nightwatch scheduled task and writes the opt-out flag so
# the plugin's SessionStart hook does not resurrect the guardian. Config/log
# files are left in place; delete nightwatch.json / nightwatch.log manually
# if unwanted. Re-arm later by deleting nightwatch.disabled (or reinstalling).
param([string]$TaskName = "ZCodeNightwatch")
schtasks /Delete /TN $TaskName /F
Set-Content -Path (Join-Path $PSScriptRoot "nightwatch.disabled") `
    -Value "opted out $(Get-Date -Format s)" -Encoding ASCII
Write-Host "[OK] task removed; hook opt-out flag written (nightwatch.disabled)"
