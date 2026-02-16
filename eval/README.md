# Синтетический multi-turn eval Phi Bot

Тестовый стенд с LLM-симулятором пользователей для оценки UX-регрессий.

## TEST COST OPTIMIZER V1 (режимы + кэш)

| Режим   | Модель бота | Min chars | Expand retry | Пример                      |
|---------|-------------|-----------|--------------|-----------------------------|
| fast    | gpt-5-mini  | 320       | нет          | Каждый коммит, ~5–10× дешевле |
| product | gpt-5.2     | 900       | да           | Продуктовый прогон          |
| release | gpt-5.2     | 900       | да           | Полный релизный прогон      |

```bash
# FAST — дешёвый прогон каждый коммит
python3 -m eval.run_synth_simulation --mode fast --limit 4

# PRODUCT — продуктовый прогон
python3 -m eval.run_synth_simulation --mode product --limit 9

# RELEASE — полный прогон
python3 -m eval.run_synth_simulation --mode release --limit 20

# Без кэша
python3 -m eval.run_synth_simulation --mode fast --no-cache

# Удалить кэш
rm -rf eval/.cache_llm
```

## TEST COST OPTIMIZER V1.1 (run-only-failed + cost telemetry)

```bash
# FAST — дёшево, каждый коммит
python3 -m eval.run_synth_simulation --mode fast --limit 4

# PRODUCT — качество, реже
python3 -m eval.run_synth_simulation --mode product --limit 9

# RERUN ONLY FAILED — после product, только падающие диалоги
python3 -m eval.run_synth_simulation --mode product --only-failed --limit 9

# Указать отчёт явно
python3 -m eval.run_synth_simulation --mode product --only-failed --failed-from eval/reports/report_20260215_1200.json --limit 9

# Сбросить кэш
rm -rf eval/.cache_llm

# E1.1: cost control — пропустить LLM-классификатор intent для topic_mid (дешевле)
EVAL_SKIP_LLM_INTENT=1 python3 -m eval.run_synth_simulation --mode fast --limit 4
```

Отчёт сохраняется в `eval/reports/report_YYYYMMDD_HHMM.json`. В нём: `dialogues` (per-dialog violations), `cost_telemetry` (calls, cached_hits, tokens, cost_usd_est).

## Запуск (legacy)

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

### Переменные cost control (E1.1)

| Переменная | Значение | Описание |
|------------|----------|----------|
| EVAL_SKIP_LLM_INTENT | 1 | Пропустить LLM-классификатор intent для topic_mid (дешевле eval) |

## Структура

```
eval/
  synth_personas.yaml   # 10 персон
  synth_scenarios.yaml  # 18+ сценариев
  synth_user_agent.py   # LLM-симулятор (gpt-4.1-mini)
  llm_cache.py          # TEST COST OPTIMIZER: кэш LLM-ответов
  .cache_llm/           # Кэш (можно удалить: rm -rf eval/.cache_llm)
  reports/              # Отчёты report_YYYYMMDD_HHMM.json (для --only-failed)
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
