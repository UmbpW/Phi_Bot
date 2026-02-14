# Сбор датасета из Reddit (без API)

Сбор публичных постов через RSS. Без Reddit API, без сохранения author/username, комментариев.

## Установка

```bash
pip install -r requirements.txt
```

## Сбор

```bash
python tools/reddit_rss_collect.py --subs existentialism meaningoflife self offmychest relationships --mode hot --limit 200
```

**Аргументы:**
- `--subs` — список сабреддитов
- `--mode` — hot | new | top (default: hot)
- `--limit` — макс. постов на sub (default: 100)
- `--sleep` — пауза между запросами в сек (default: 1.5)

## Очистка

```bash
python tools/reddit_rss_clean.py
```

Удаляет дубли по url и (title+text), формирует `user_inputs.txt`.

## Замечания

- Соблюдать rate limit (1–2 сек между запросами)
- Хранить только текст, без идентификаторов пользователей
- User-Agent: phi-bot-dataset/1.0
