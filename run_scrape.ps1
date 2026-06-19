# Запуск сбора остатков/цен JAC. Можно дёргать руками или из планировщика.
# Использование:  .\run_scrape.ps1            (scrape)
#                 .\run_scrape.ps1 check       (проверить вход)
#                 .\run_scrape.ps1 discover    (калибровка парсера)

param([string]$Command = "scrape")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# UTF-8 в консоли и в Python (иначе кириллица в логах ломается)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
# Ходим напрямую, минуя системный SOCKS-прокси
$env:NO_PROXY = "*"

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Не найден venv ($py). Сначала: python -m venv .venv; .\.venv\Scripts\python -m pip install -r requirements.txt"
    exit 1
}

# Лог с датой
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("scrape_{0}.log" -f (Get-Date -Format "yyyyMMdd"))

Write-Output ("[{0}] jac_scraper {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Command) | Tee-Object -FilePath $log -Append
& $py -m jac_scraper $Command 2>&1 | Tee-Object -FilePath $log -Append
$code = $LASTEXITCODE
Write-Output ("[exit $code]") | Tee-Object -FilePath $log -Append

# После успешного scrape — доставить готовые файлы на прод-VPS (валидация+атомарно
# внутри upload_to_vps.py). Сбой аплоада отражаем в коде выхода задачи.
if ($Command -eq "scrape" -and $code -eq 0) {
    Write-Output ("[{0}] upload_to_vps" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) | Tee-Object -FilePath $log -Append
    & $py (Join-Path $root "upload_to_vps.py") 2>&1 | Tee-Object -FilePath $log -Append
    $ucode = $LASTEXITCODE
    Write-Output ("[upload exit $ucode]") | Tee-Object -FilePath $log -Append
    if ($ucode -ne 0) { $code = $ucode }
}

exit $code
