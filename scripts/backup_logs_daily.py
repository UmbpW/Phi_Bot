#!/usr/bin/env python3
"""Ежедневное сохранение логов с датой в имени файла.

Запуск вручную: python scripts/backup_logs_daily.py
Cron (ежедневно в 9:00): 0 9 * * * cd /path/to/Phi_Bot && python scripts/backup_logs_daily.py
"""
import json
import os
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

EXPORT_URL = os.getenv("EXPORT_URL", "").strip()
EXPORT_TOKEN = os.getenv("EXPORT_TOKEN", "").strip()
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(PROJECT_ROOT / "exports")))
LOGS_DIR = PROJECT_ROOT / "logs"


def fetch_from_railway() -> list[dict]:
    """Выгрузка диалогов с Railway API."""
    if not EXPORT_URL or not EXPORT_TOKEN:
        return []
    try:
        import requests
    except ImportError:
        return []
    url = f"{EXPORT_URL.rstrip('/')}?token={EXPORT_TOKEN}"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            return []
        return data.get("dialogs", [])
    except Exception:
        return []


def collect_local_logs() -> list[dict]:
    """Сбор диалогов из локальных logs/users/*/dialogs.jsonl и logs/dialogs.jsonl."""
    records = []
    for path in LOGS_DIR.rglob("dialogs.jsonl"):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue
    return sorted(records, key=lambda r: r.get("ts", ""))


def main():
    today = date.today().isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dialogs = []
    source = None

    # 1. Пробуем Railway
    if EXPORT_URL and EXPORT_TOKEN:
        dialogs = fetch_from_railway()
        if dialogs:
            source = "railway"

    # 2. Если Railway пуст — локальные логи
    if not dialogs:
        dialogs = collect_local_logs()
        if dialogs:
            source = "local"

    if not dialogs:
        print(f"[backup] Нет данных для сохранения ({today})")
        return

    # Сохранение с датой в имени
    out_json = OUTPUT_DIR / f"dialogs_{today}.json"
    out_jsonl = OUTPUT_DIR / f"dialogs_{today}.jsonl"

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(dialogs, f, ensure_ascii=False, indent=2)

    with open(out_jsonl, "w", encoding="utf-8") as f:
        for d in dialogs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print(f"[backup] Сохранено {len(dialogs)} записей → {out_json.name} ({source or 'unknown'})")


if __name__ == "__main__":
    main()
