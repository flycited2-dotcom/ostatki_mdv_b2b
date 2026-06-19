"""Доставка готовых файлов JAC на прод-VPS (рядом с Telegram-ботом).

Зачем: B2B-портал JAC отдаёт серверному IP битые/частичные данные (нет брендов,
половина категорий пустая), поэтому скрапим на этой машине, а на VPS только
доставляем готовые файлы. Запускается автоматически из run_scrape.ps1 ПОСЛЕ
успешного `scrape`.

Стабильность (главное требование):
  • ВАЛИДАЦИЯ перед отправкой — не зальём пустой/частичный/бесбрендовый скрап
    (ровно тот случай, что ловили на VPS). Не прошло проверку → НЕ трогаем прод,
    выходим с ошибкой и шлём алерт.
  • АТОМАРНО — пишем во временный файл и `mv` (на одной ФС атомарно), бот никогда
    не прочитает полуфайл.
  • РЕТРАИ на коннект/передачу; SFTP на сервере выключен → льём через exec+base64.
  • ЛОГ в logs/upload_*.log + консоль; при окончательном сбое — Telegram-алерт.

Вход на VPS — безпарольным ключом ~/.ssh/splithub_upload (поставлен в authorized_keys).
"""
import base64
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import paramiko

# ── настройки ──────────────────────────────────────────────────────────────
HOST = '213.109.202.45'
USER = 'root'
KEY = os.path.expanduser('~/.ssh/splithub_upload')      # безпарольный ключ
REMOTE_DIR = '/opt/splithub_api_telegram/data'          # откуда бот читает JAC_*_JSON
OWNER_CHAT_ID = '1264067528'

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('JAC_OUTPUT_DIR') or (ROOT / 'data'))
LOG_DIR = ROOT / 'logs'

# Файлы к доставке: (имя, обязательный?, валидатор). jac_photos — на будущее (Этап 2).
TARGETS = [
    ('jac_stock_latest.json', True, 'stock'),
    ('jac_utp_latest.json', False, 'utp'),
    ('jac_photos_latest.json', False, 'photos'),
]

# Пороги «здоровья» остатков — отсекают частичный/битый скрап (VPS давал 125/без брендов).
MIN_STOCK_ROWS = 300        # полный скрап ~526; меньше — подозрительно, не льём
MIN_ROWS_WITH_BRAND = 100   # битый скрап имел brand='' у всех


def log(msg):
    line = f'{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}'
    print(line, flush=True)
    try:
        LOG_DIR.mkdir(exist_ok=True)
        with open(LOG_DIR / f'upload_{dt.date.today():%Y%m%d}.log', 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


def validate(path: Path, kind: str):
    """Бросает ValueError, если файл не годен к заливке на прод."""
    data = json.loads(path.read_text(encoding='utf-8'))
    if kind == 'stock':
        if not isinstance(data, list) or len(data) < MIN_STOCK_ROWS:
            raise ValueError(f'{path.name}: позиций {len(data) if isinstance(data, list) else "?"}'
                             f' < {MIN_STOCK_ROWS} (частичный/битый скрап)')
        with_brand = sum(1 for r in data if isinstance(r, dict) and (r.get('brand') or '').strip())
        if with_brand < MIN_ROWS_WITH_BRAND:
            raise ValueError(f'{path.name}: строк с брендом {with_brand} < {MIN_ROWS_WITH_BRAND}'
                             f' (портал отдал без брендов?)')
        return f'{len(data)} позиций, с брендом {with_brand}'
    if kind == 'utp':
        if not isinstance(data, dict) or not data:
            raise ValueError(f'{path.name}: УТП пустой/не словарь')
        return f'{len(data)} брендов'
    if kind == 'photos':
        if not isinstance(data, dict) or not data:
            raise ValueError(f'{path.name}: фото-маппинг пустой/не словарь')
        return f'{len(data)} брендов'
    return 'ok'


def connect(retries=3):
    last = None
    for i in range(1, retries + 1):
        try:
            c = paramiko.SSHClient()
            c.load_system_host_keys()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(HOST, username=USER, key_filename=KEY, timeout=30,
                      banner_timeout=30, auth_timeout=30, look_for_keys=False, allow_agent=False)
            return c
        except Exception as e:                       # noqa: BLE001 — хотим любой сбой ретраить
            last = e
            log(f'  connect попытка {i}/{retries} не удалась: {e}')
            time.sleep(3)
    raise last


def _run(c, cmd, timeout=120):
    si, so, se = c.exec_command(cmd, timeout=timeout)
    rc = so.channel.recv_exit_status()
    return rc, so.read().decode('utf-8', 'replace'), se.read().decode('utf-8', 'replace')


def upload_atomic(c, local: Path, remote_name: str, retries=3):
    """Заливает local → REMOTE_DIR/remote_name атомарно (через .tmp + mv). Сверяет размер."""
    data = local.read_bytes()
    b64 = base64.b64encode(data)
    tmp = f'{REMOTE_DIR}/.{remote_name}.tmp'
    final = f'{REMOTE_DIR}/{remote_name}'
    for i in range(1, retries + 1):
        try:
            cmd = ("python3 -c \"import sys,base64,pathlib; p=pathlib.Path('%s'); "
                   "p.parent.mkdir(parents=True, exist_ok=True); "
                   "p.write_bytes(base64.b64decode(sys.stdin.buffer.read()))\"" % tmp)
            si, so, se = c.exec_command(cmd, timeout=180)
            si.write(b64)
            si.flush()
            si.channel.shutdown_write()
            if so.channel.recv_exit_status() != 0:
                raise IOError('запись tmp не удалась: ' + se.read().decode('utf-8', 'replace'))
            # сверить размер и атомарно переименовать
            rc, out, err = _run(c, f'stat -c%s "{tmp}"')
            remote_size = int(out.strip() or -1)
            if remote_size != len(data):
                raise IOError(f'размер не сошёлся: локально {len(data)}, на VPS {remote_size}')
            rc, out, err = _run(c, f'mv -f "{tmp}" "{final}"')
            if rc != 0:
                raise IOError('mv не удался: ' + err)
            log(f'  ✓ {remote_name}: {len(data)} байт доставлено атомарно')
            return
        except Exception as e:                       # noqa: BLE001
            log(f'  {remote_name} попытка {i}/{retries}: {e}')
            _run(c, f'rm -f "{tmp}"')                 # подчистить хвост
            if i == retries:
                raise
            time.sleep(3)


def alert(text):
    """Telegram-алерт владельцу при сбое (токен — из config/.env скрапера)."""
    try:
        token = ''
        env = ROOT / 'config' / '.env'
        if env.exists():
            for line in env.read_text(encoding='utf-8').splitlines():
                if line.strip().startswith('TELEGRAM_BOT_TOKEN='):
                    token = line.split('=', 1)[1].strip()
        if not token:
            return
        import urllib.request
        body = json.dumps({'chat_id': OWNER_CHAT_ID, 'text': text}).encode('utf-8')
        req = urllib.request.Request(
            f'https://api.telegram.org/bot{token}/sendMessage', data=body,
            headers={'Content-Type': 'application/json; charset=utf-8'})
        urllib.request.urlopen(req, timeout=20)
    except Exception as e:                            # noqa: BLE001 — алерт не должен ронять процесс
        log(f'  (не удалось отправить Telegram-алерт: {e})')


def main():
    log('=== upload_to_vps: старт ===')
    # 1) собрать и провалидировать то, что есть
    ready = []
    for name, required, kind in TARGETS:
        p = DATA / name
        if not p.exists():
            if required:
                msg = f'НЕТ обязательного файла {p} — отмена (прод не трогаем)'
                log('✗ ' + msg)
                alert('⚠️ JAC upload отменён: ' + msg)
                return 2
            log(f'  · {name} нет — пропускаю (необязательный)')
            continue
        try:
            info = validate(p, kind)
            log(f'  · {name}: валиден ({info})')
            ready.append((name, p))
        except (ValueError, json.JSONDecodeError) as e:
            if required:
                log('✗ валидация провалена: ' + str(e))
                alert('⚠️ JAC upload отменён (битые данные, прод не тронут): ' + str(e))
                return 3
            log(f'  · {name}: невалиден, пропускаю ({e})')

    # 2) доставить
    try:
        c = connect()
    except Exception as e:                            # noqa: BLE001
        log('✗ не удалось подключиться к VPS: ' + str(e))
        alert('⚠️ JAC upload: нет связи с VPS: ' + str(e))
        return 4
    try:
        for name, p in ready:
            upload_atomic(c, p, name)
    except Exception as e:                            # noqa: BLE001
        log('✗ сбой доставки: ' + str(e))
        alert('⚠️ JAC upload: сбой доставки на VPS: ' + str(e))
        return 5
    finally:
        c.close()

    log(f'=== upload_to_vps: успех, доставлено файлов: {len(ready)} ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())
