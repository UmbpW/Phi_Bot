#!/bin/bash
# Ежедневный выгруз диалогов — сохраняет в dialogs_YYYY-MM-DD.json
# Использование: задай EXPORT_URL, EXPORT_TOKEN в .env или окружении
# Cron (ежедневно в 9:00): 0 9 * * * cd /path/to/Phi_Bot && ./scripts/fetch_dialogs_daily.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Загрузка .env если есть
[ -f .env ] && set -a && source .env && set +a

URL="${EXPORT_URL:-}"
TOKEN="${EXPORT_TOKEN:-}"
OUTDIR="${OUTPUT_DIR:-$PROJECT_ROOT/exports}"
DATE=$(date +%Y-%m-%d)
OUTFILE="$OUTDIR/dialogs_$DATE.json"

mkdir -p "$OUTDIR"
if [ -z "$URL" ] || [ -z "$TOKEN" ]; then
    echo "[backup] Пропуск: задай EXPORT_URL и EXPORT_TOKEN в .env"
    exit 0
fi
curl -s "${URL}?token=${TOKEN}" -o "$OUTFILE"
echo "[backup] Сохранено: $OUTFILE ($(wc -c < "$OUTFILE") bytes)"
