#!/bin/bash
# Ежедневный выгруз диалогов — сохраняет в dialogs_YYYY-MM-DD.json
# Настрой cron: 0 9 * * * /path/to/scripts/fetch_dialogs_daily.sh

URL="${EXPORT_URL:-https://your-app.railway.app/export}"
TOKEN="${EXPORT_TOKEN:-your_secret_token}"
OUTDIR="${OUTPUT_DIR:-./exports}"
DATE=$(date +%Y-%m-%d)
OUTFILE="$OUTDIR/dialogs_$DATE.json"

mkdir -p "$OUTDIR"
curl -s "${URL}?token=${TOKEN}" -o "$OUTFILE"
echo "Сохранено: $OUTFILE ($(wc -c < "$OUTFILE") bytes)"
