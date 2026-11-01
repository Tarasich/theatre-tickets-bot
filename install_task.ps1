# Регистрирует бота в Планировщике заданий Windows: запуск при входе в систему, без окна консоли.
# Запуск: powershell -ExecutionPolicy Bypass -File install_task.ps1
$ErrorActionPreference = "Stop"

$taskName = "TheatreTicketsBot"
$dir = $PSScriptRoot
$pythonw = Join-Path $dir ".venv\Scripts\pythonw.exe"

if (-not (Test-Path $pythonw)) { throw "Не найден $pythonw. Сначала создайте .venv (см. README)." }
if (-not (Test-Path (Join-Path $dir ".env"))) { throw "Не найден файл .env рядом со скриптом." }

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "-m theatre_bot" -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Мониторинг билетов театра «Свободное пространство» (quicktickets.ru)" -Force | Out-Null
Start-ScheduledTask -TaskName $taskName

Write-Host "Задача $taskName создана и запущена. Журнал: $(Join-Path $dir 'bot.log')"
