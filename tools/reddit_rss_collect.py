#!/usr/bin/env python3
"""Сбор постов Reddit через RSS без API. Только публичные данные."""

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import feedparser
import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = PROJECT_ROOT / "dataset"
OUTPUT_FILE = DATASET_DIR / "reddit_posts.jsonl"
USER_AGENT = "phi-bot-dataset/1.0"

RSS_URLS = {
    "hot": "https://old.reddit.com/r/{sub}/hot/.rss",
    "new": "https://old.reddit.com/r/{sub}/new/.rss",
    "top": "https://old.reddit.com/r/{sub}/top/.rss?t=week",
}


def fetch_rss(url: str) -> feedparser.FeedParserDict:
    """Загрузка RSS с User-Agent."""
    return feedparser.parse(
        url,
        request_headers={"User-Agent": USER_AGENT},
    )


def fetch_html(url: str) -> Optional[str]:
    """Загрузка HTML поста."""
    try:
        r = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=15,
            allow_redirects=True,
        )
        r.raise_for_status()
        return r.text
    except Exception:
        return None


def extract_text_from_html(html: str, fallback_summary: str = "") -> str:
    """Извлечение текста поста. Fallback-порядок."""
    soup = BeautifulSoup(html, "lxml")

    # 1) meta og:description
    meta = soup.find("meta", property="og:description")
    if meta and meta.get("content"):
        text = meta["content"].strip()
        if _is_valid_text(text):
            return _clean_text(text)

    # 2) div[data-test-id="post-content"] p
    content = soup.find("div", attrs={"data-test-id": "post-content"})
    if content:
        paras = content.find_all("p")
        if paras:
            text = " ".join(p.get_text(strip=True) for p in paras)
            if _is_valid_text(text):
                return _clean_text(text)

    # 3) article p
    article = soup.find("article")
    if article:
        paras = article.find_all("p")
        if paras:
            text = " ".join(p.get_text(strip=True) for p in paras)
            if _is_valid_text(text):
                return _clean_text(text)

    # 4) entry.summary (переданный fallback) — может быть HTML
    if fallback_summary:
        fallback_text = BeautifulSoup(fallback_summary, "lxml").get_text(
            separator=" ", strip=True
        )
        if _is_valid_text(fallback_text):
            return _clean_text(fallback_text)

    return ""


def _is_valid_text(text: str) -> bool:
    """Проверка: длина 100..4000 символов."""
    cleaned = _clean_text(text)
    return 100 <= len(cleaned) <= 4000


def _clean_text(text: str) -> str:
    """Очистка: убрать лишние пробелы, строки типа 'submitted by'."""
    text = re.sub(r"\s+", " ", text).strip()
    lines = text.split("\n")
    filtered = []
    skip_patterns = (
        r"submitted by",
        r"posted by",
        r"\[removed\]",
        r"\[deleted\]",
    )
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if any(re.search(p, line, re.I) for p in skip_patterns):
            continue
        filtered.append(line)
    result = " ".join(filtered)
    result = re.sub(r"\s+", " ", result).strip()
    if len(result) < 100:
        return ""
    if len(result) > 4000:
        result = result[:4000].rsplit(" ", 1)[0]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Reddit RSS collector (no API)")
    parser.add_argument("--subs", nargs="+", required=True, help="Сабреддиты")
    parser.add_argument("--mode", choices=["hot", "new", "top"], default="hot")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--sleep", type=float, default=1.5)
    args = parser.parse_args()

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    seen_urls: set[str] = set()

    total = 0
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for sub in args.subs:
            sub = sub.strip().lower()
            url = RSS_URLS[args.mode].format(sub=sub)
            print(f"[{sub}] Fetching RSS: {url}")
            feed = fetch_rss(url)
            time.sleep(args.sleep)

            entries = getattr(feed, "entries", [])[: args.limit]
            for i, entry in enumerate(entries):
                link = getattr(entry, "link", "")
                if not link or link in seen_urls:
                    continue
                title = getattr(entry, "title", "")
                summary = getattr(entry, "summary", "") or ""
                if hasattr(entry, "content") and entry.content:
                    summary = entry.content[0].get("value", summary)

                print(f"  [{i+1}/{len(entries)}] {link[:60]}...")
                html = fetch_html(link)
                time.sleep(args.sleep)

                text = ""
                if html:
                    text = extract_text_from_html(html, summary)
                else:
                    raw = BeautifulSoup(summary, "lxml").get_text(separator=" ", strip=True) if summary else ""
                    text = _clean_text(raw) if raw else ""

                if not text or len(text) < 100:
                    continue

                seen_urls.add(link)
                record = {
                    "sub": sub,
                    "title": title,
                    "text": text,
                    "url": link,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                total += 1

    print(f"\nDone. Saved {total} posts to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
