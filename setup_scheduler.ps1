# Настройка Windows Task Scheduler для автоматической генерации черновиков
# Запускать от имени администратора: правый клик → "Run with PowerShell"

$taskName = "XHybridBot_GenerateDrafts"
$actionPath = Join-Path $PSScriptRoot "run_generate.bat"
$workDir = $PSScriptRoot

# Проверяем, что файл существует
if (-not (Test-Path $actionPath)) {
    Write-Error "Файл не найден: $actionPath"
    exit 1
}

# Удаляем старую задачу, если есть
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Создаём действие: запуск run_generate.bat
$action = New-ScheduledTaskAction -Execute $actionPath -WorkingDirectory $workDir

# Триггер: каждый день в 9:00
$trigger = New-ScheduledTaskTrigger -Daily -At "09:00"

# Настройки: не прерывать при батарее, скрытое окно
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Регистрируем задачу
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "X Hybrid Bot: auto-generate Twitter drafts every morning at 9:00"

Write-Host "✅ Задача '$taskName' создана! Запускается каждый день в 9:00." -ForegroundColor Green
Write-Host "   Путь: $actionPath"
Write-Host ""
Write-Host "Команды управления:"
Write-Host "   schtasks /run /tn $taskName     # запустить сейчас"
Write-Host "   schtasks /end /tn $taskName     # остановить"
Write-Host "   schtasks /delete /tn $taskName  # удалить задачу"
