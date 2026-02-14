#!/usr/bin/env python3
"""Выгрузка диалогов с Railway (PostgreSQL) в exports/."""
import json
import os
import sys
from pathlib import Path

# Загружаем .env как бот
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

EXPORT_URL = os.getenv("EXPORT_URL", "").strip()
EXPORT_TOKEN = os.getenv("EXPORT_TOKEN", "").strip()
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", PROJECT_ROOT / "exports"))


def main():
    if not EXPORT_URL or not EXPORT_TOKEN:
        print("ERROR: Добавь в .env:")
        print("  EXPORT_URL=https://YOUR-APP.up.railway.app/export")
        print("  EXPORT_TOKEN=твой_секретный_токен")
        print("\n(URL смотри в Railway Dashboard → Deployments → Domain)")
        sys.exit(1)

    try:
        import requests
    except ImportError:
        print(" pip install requests")
        sys.exit(1)

    url = f"{EXPORT_URL.rstrip('/')}?token={EXPORT_TOKEN}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()

    if "error" in data:
        print(f"ERROR: {data['error']}")
        sys.exit(1)

    dialogs = data.get("dialogs", [])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    out_json = OUTPUT_DIR / "dialogs_all.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(dialogs, f, ensure_ascii=False, indent=2)

    out_jsonl = OUTPUT_DIR / "dialogs_all.jsonl"
    with open(out_jsonl, "w", encoding="utf-8") as f:
        for d in dialogs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print(f"Сохранено: {len(dialogs)} записей")
    print(f"  {out_json}")
    print(f"  {out_jsonl}")


if __name__ == "__main__":
    main()
