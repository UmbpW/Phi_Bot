# Синтетический multi-turn eval Phi Bot

Тестовый стенд с LLM-симулятором пользователей для оценки UX-регрессий.

## Запуск

```bash
# Полный прогон (все персоны × все сценарии)
python eval/run_synth_simulation.py

# Ограничить число диалогов
python eval/run_synth_simulation.py --limit 20

# Только одна персона
python eval/run_synth_simulation.py --only_persona impatient_pragmatic_25

# Только один сценарий
python eval/run_synth_simulation.py --only_scenario sc_finance_anxiety

# Папка вывода
python eval/run_synth_simulation.py --out_dir ./my_eval_out
```

## Зависимости

- Python 3.9+
- PyYAML: `pip install pyyaml`
- OpenAI API key в `.env` (OPENAI_API_KEY)
- PHI_EVAL=1 задаётся внутри скрипта — TELEGRAM_TOKEN не требуется

## Структура

```
eval/
  synth_personas.yaml   # 10 персон
  synth_scenarios.yaml  # 18+ сценариев
  synth_user_agent.py   # LLM-симулятор (gpt-4.1-mini)
  checks.py             # Эвристики UX-регрессий
  run_synth_simulation.py
  out/                  # JSONL диалоги YYYYMMDD_HHMM/*.jsonl
```

## Метрики

- `avg_len` — средняя длина ответа бота
- `too_short_count` — ответы < 350 символов
- `warmup_mismatch_count` — triage «состояние/смысл/опора» когда не должен
- `context_drop_count` — generic ответ на конкретный контекст
- `meta_tail_count` — тех.метки [mode: / [pattern: в ответе
- `incomplete_count` — обрыв без точки
