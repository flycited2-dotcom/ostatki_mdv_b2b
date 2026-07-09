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

# Порог «здоровья» скрапа — тот же, что в upload_to_vps.py (MIN_STOCK_ROWS).
# Портал изредка отдаёт пустые категории (ночью ~116 вместо ~526). При неполном
# сборе перезапускаем scrape несколько раз с паузой — самовосстановление cron.
$minItems = 300
$maxTries = 3
$retryWaitSec = 900   # 15 мин между попытками

function Get-StockCount {
    $stock = Join-Path $root "data\jac_stock_latest.json"
    if (-not (Test-Path $stock)) { return 0 }
    try { return @(Get-Content $stock -Raw -Encoding UTF8 | ConvertFrom-Json).Count }
    catch { return 0 }
}

$attempt = 1
while ($true) {
    Write-Output ("[{0}] jac_scraper {1} (попытка {2}/{3})" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Command, $attempt, $maxTries) | Tee-Object -FilePath $log -Append
    & $py -m jac_scraper $Command 2>&1 | Tee-Object -FilePath $log -Append
    $code = $LASTEXITCODE
    Write-Output ("[exit $code]") | Tee-Object -FilePath $log -Append

    # Ретрай только для scrape и только при неполном сборе.
    if ($Command -ne "scrape") { break }
    $count = Get-StockCount
    if ($code -eq 0 -and $count -ge $minItems) {
        Write-Output ("[scrape ok: $count позиций]") | Tee-Object -FilePath $log -Append
        break
    }
    if ($attempt -ge $maxTries) {
        Write-Output ("[scrape неполный: $count < $minItems после $maxTries попыток — фото/аплоад пропущены]") | Tee-Object -FilePath $log -Append
        if ($code -eq 0) { $code = 4 }   # неполный скрап -> задача неуспешна, прод не трогаем
        break
    }
    Write-Output ("[scrape неполный: $count < $minItems, повтор через $([int]($retryWaitSec/60)) мин]") | Tee-Object -FilePath $log -Append
    Start-Sleep -Seconds $retryWaitSec
    $attempt++
}

# После ПОЛНОГО scrape (code 0 = сток здоров): обновить карту фото серий, затем
# доставить файлы на прод-VPS (валидация+атомарно внутри upload_to_vps.py).
if ($Command -eq "scrape" -and $code -eq 0) {
    Write-Output ("[{0}] photos" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) | Tee-Object -FilePath $log -Append
    & $py -m jac_scraper photos 2>&1 | Tee-Object -FilePath $log -Append   # фото MDV/MHI(URL)+THAICON/EUROKLIMAT(локально)
    Write-Output ("[photos exit $LASTEXITCODE]") | Tee-Object -FilePath $log -Append

    Write-Output ("[{0}] upload_to_vps" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss")) | Tee-Object -FilePath $log -Append
    & $py (Join-Path $root "upload_to_vps.py") 2>&1 | Tee-Object -FilePath $log -Append
    $ucode = $LASTEXITCODE
    Write-Output ("[upload exit $ucode]") | Tee-Object -FilePath $log -Append
    if ($ucode -ne 0) { $code = $ucode }
}

exit $code
