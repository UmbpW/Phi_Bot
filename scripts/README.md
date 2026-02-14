# Скрипты Phi Bot

## Ежедневное сохранение логов

Логи сохраняются в `exports/` с датой в имени: `dialogs_YYYY-MM-DD.json`, `dialogs_YYYY-MM-DD.jsonl`.

### Вариант 1: Python (рекомендуется)

Работает с Railway и локальными логами:

```bash
python scripts/backup_logs_daily.py
```

### Вариант 2: Bash + curl

Только Railway (требует EXPORT_URL и EXPORT_TOKEN в .env):

```bash
./scripts/fetch_dialogs_daily.sh
```

### Встроенный планировщик (локальный запуск)

Если бот запускаешь локально, добавь в `.env`:

```
BACKUP_DAILY=1
```

Бот будет сохранять логи раз в 24 часа в `exports/dialogs_YYYY-MM-DD.json`.

*На Railway диск временный — для продакшена используй cron на своей машине.*

### Автоматический запуск (cron)

Добавь в crontab (`crontab -e`):

```
# Ежедневно в 9:00
0 9 * * * cd /path/to/Phi_Bot && python scripts/backup_logs_daily.py
```

Или через bash:

```
0 9 * * * cd /path/to/Phi_Bot && ./scripts/fetch_dialogs_daily.sh
```

Замени `/path/to/Phi_Bot` на полный путь к проекту.
