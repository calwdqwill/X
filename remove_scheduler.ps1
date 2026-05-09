# Удаление задачи из Windows Task Scheduler
# Запускать от имени администратора

$taskName = "XHybridBot_GenerateDrafts"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "✅ Задача '$taskName' удалена." -ForegroundColor Green
} else {
    Write-Host "Задача '$taskName' не найдена." -ForegroundColor Yellow
}
