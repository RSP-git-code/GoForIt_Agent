# Creates (or updates) a Windows scheduled task that scans job alerts daily at 8:30 AM.
# Light by design: low priority, no window (pythonw), only with internet, stops after 5 min,
# runs at next logon if the laptop was off. Remove it with:
#   Unregister-ScheduledTask -TaskName "GoForIt daily job scan" -Confirm:$false

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$pythonw = Join-Path $backend ".venv\Scripts\pythonw.exe"

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "-m app.inbox --scheduled" -WorkingDirectory $backend
$trigger = New-ScheduledTaskTrigger -Daily -At 8:30am
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -Priority 7 -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "GoForIt daily job scan" -Action $action -Trigger $trigger -Settings $settings `
    -Description "GoForIt: LinkedIn/Indeed alerts (Gmail, read-only) -> Excel tracker -> 9 AM calendar reminder" -Force | Out-Null
Write-Output "Scheduled: GoForIt daily job scan, every day at 8:30 AM (log: Documents\GoForIt\inbox-log.txt)"
