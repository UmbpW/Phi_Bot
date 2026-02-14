#!/usr/bin/env python3
"""Очистка dataset: дедупликация, формирование user_inputs.txt."""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "dataset" / "reddit_posts.jsonl"
OUTPUT_FILE = PROJECT_ROOT / "dataset" / "user_inputs.txt"


def main() -> None:
    seen_urls: set[str] = set()
    seen_content: set[tuple[str, str]] = set()
    records = []

    if not INPUT_FILE.exists():
        print(f"File not found: {INPUT_FILE}")
        return

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = obj.get("url", "")
            title = obj.get("title", "") or ""
            text = obj.get("text", "") or ""
            if url in seen_urls:
                continue
            key = (title.strip(), text.strip())
            if key in seen_content:
                continue
            seen_urls.add(url)
            seen_content.add(key)
            records.append({"title": title, "text": text})

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(f"TITLE: {r['title']}\n")
            f.write(f"TEXT: {r['text']}\n")
            f.write("---\n")

    print(f"Уникальных записей: {len(records)}")
    print(f"Сохранено в {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
