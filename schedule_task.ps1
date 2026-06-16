# Регистрирует ежедневную задачу Windows Task Scheduler, которая собирает
# остатки/цены JAC. Запусти ОДИН раз (от своего пользователя):
#     .\schedule_task.ps1               # ежедневно в 07:30
#     .\schedule_task.ps1 -Time 06:00   # своё время
# Удалить:  Unregister-ScheduledTask -TaskName "JAC_B2B_Stock" -Confirm:$false

param([string]$Time = "07:30", [string]$TaskName = "JAC_B2B_Stock")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $root "run_scrape.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" scrape" `
    -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Ежедневный сбор остатков и цен с b2b-jac.com" -Force

Write-Output "Задача '$TaskName' зарегистрирована: ежедневно в $Time."
Write-Output "Проверить:  Get-ScheduledTask -TaskName $TaskName"
Write-Output "Запустить сейчас:  Start-ScheduledTask -TaskName $TaskName"
