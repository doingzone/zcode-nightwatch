# Removes the ZCode Nightwatch scheduled task. Config/log files are left in
# place; delete nightwatch.json / nightwatch.log manually if unwanted.
param([string]$TaskName = "ZCodeNightwatch")
schtasks /Delete /TN $TaskName /F
