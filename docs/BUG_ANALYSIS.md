# Phi Bot — Анализ 3 багов (BUG_ANALYSIS)

> **Реализованные фиксы (2025-02):** BUG3 (guard + logging), BUG2 (ack_close + TOPIC_MARKERS + religion block), BUG1 (hard-guard + telemetry).

### Чек-лист ручных тестов (Telegram)
1. `/start` → приветствие один раз
2. `/start привет` → онбординг + сразу ответ на «привет» (хвост не теряется)
3. «верю в себя» → НЕ religion_short (общая фраза, философский/decision шаблон)
4. «Расскажи про Бога и буддизм» → не money-шаблон, философский ответ
5. «понял, спасибо» → короткий ack_close, без triage
6. «У меня конфликт с верой, мне стыдно» → не orientation, ответ по теме (религия/вина/стыд)
7. Дубли: один update_id ⇒ один send (или part i/total при split)

## BUG 1 — Wrong routing: «Расскажи про Бога и буддизм» → деньги/зона контроля

### Текущее состояние кода (после последних патчей)

**Путь, который ДОЛЖЕН работать корректно:**
1. `generate_reply_core()` → `history_count`, `is_concept = detect_philosophy_topic_intent(user_text)[0] or is_topic_high(user_text)`
2. Для «Расскажи про Бога и буддизм»: `is_topic_high` = True (topic_score ≥ 5), значит `is_concept` = True
3. Условие `should_skip_warmup_first_turn(...) and not is_concept` → False (т.к. is_concept=True)
4. **first_turn gate не срабатывает** → идём дальше в `governor_plan`
5. `governor_plan`: `is_topic_high` → `philosophy_pipeline`, `answer_first_required`
6. Основной LLM flow с philosophy_pipeline

**Доп. защита** — `philosophy/first_turn_templates.py`:
- `_is_religion_topic_question("Расскажи про Бога и буддизм")` = True → `render_first_turn_philosophy` возвращает `(None, "skip")`
- Если бы first_turn gate сработал — `gate_text is None or gate_label == "skip"` → продолжаем pipeline

### Гипотезы, если баг всё ещё есть

1. **Релиз на проде старее фиксов** — проверить, что задеплоен коммит с `_is_religion_topic_question` и `gate_label == "skip"`.
2. **Race / порядок state** — `_load_persisted_state()` перезаписывает state с диска; если `cmd_start` не успел сохраниться до прихода «Расскажи про Бога», может подтянуться старый state с `turn_index` > 0 и другими флагами.
3. **Governor до philosophy_topic** — `RELIGIOUS_MARKERS` в governor (стр. 104–107) не включает «вед»/«вера». «У меня конфликт с верой» → «верой» не совпадает с «вера» (строго). Проверить: `intent_philosophy_topic.PHILOSOPHY_TOPICS` и `pattern_governor.RELIGIOUS_MARKERS`.

### Что проверить в логах

- `telemetry.intent` = ?
- `plan.philosophy_pipeline` = ?
- `stage` = ?
- Добавить лог: `is_concept`, `gate_label`, `history_count`, `turn_index` в начало `generate_reply_core`.

---

## BUG 2 — «Дежурная фраза» (три зоны) вместо ack/close или философского ответа

### Источник «три зоны»

**Файл:** `bot.py`  
**Константа:** `ORIENTATION_MESSAGE_RU` (строки 520–528)

```
"Слышу, что сейчас непросто. Чтобы не стрелять советами мимо, давай выберем угол.
Обычно такие вещи лежат в одной из трёх зон:
— **Состояние**: тревога, усталость...
— **Смысл/выбор**: зачем жить...
— **Опора/мировоззрение**: во что верить..."
```

### Когда срабатывает orientation

**Файл:** `bot.py` строки 927–942

```python
if (
    not handled_orientation_choice
    and not plan.get("force_philosophy_mode")
    and is_unclear_message(user_text)      # ← ключевое
    and stage == "warmup"
    and not plan.get("disable_warmup")
    and not plan.get("philosophy_pipeline")
    and not plan.get("answer_first_required")
    and not plan.get("explain_mode")
):
    state["pending_orientation"] = True
    append_history(..., ORIENTATION_MESSAGE_RU)
    return {...}  # orientation
```

### «понял, спасибо»

- **Файл:** `utils/intent_gate.py`, `is_unclear_message`
- Условие: `len(t) <= 70` → True (≈15 символов)
- `TOPIC_MARKERS` не содержат «понял», «спасибо»
- Если `stage == "warmup"` и governor не выставил `disable_warmup`/`philosophy_pipeline`/`answer_first_required` → orientation

**Файл:** `utils/short_ack.py`  
- «понял, спасибо» нет в `SHORT_ACK_PHRASES` → не считается short_ack
- `is_short_ack` срабатывает только при `state.get("pending")` → для чистого «понял, спасибо» обычно нет pending

### «У меня конфликт с верой, мне стыдно»

- `len(t)` ≈ 35 < 70 → `is_unclear_message` = True
- `TOPIC_MARKERS` (`utils/intent_gate.py` 39–43): «деньг», «финанс», «любов», «смерт» и т.д. — «вера»/«стыд» нет
- Governor: `RELIGIOUS_MARKERS` — есть «грех», но нет «вер», «стыд»
- `intent_philosophy_topic`: «стыд» в `PHILOSOPHY_TOPICS`, «вера» — в `RELIGION_MARKERS` (first_turn)
- При `stage == "warmup"` и отсутствии `philosophy_pipeline`/`answer_first_required` → orientation

### Рекомендации по фиксам

1. **Guard для ack/close** — добавить маркеры «понял», «спасибо», «ясно», «ок, всё» и т.п.:
   - либо отдельный `is_ack_close_intent()` → короткий ack без triage;
   - либо в `is_unclear_message` исключать эти фразы (не считать unclear).
2. **Religion/стыд → philosophy** — в governor добавить:
   - «вер», «стыд», «вина» в `RELIGIOUS_MARKERS` или отдельный gate для «конфликт с верой» → `philosophy_pipeline`.
3. **TOPIC_MARKERS** — расширить на «вер», «стыд», «вина», «религ», чтобы «конфликт с верой» не считался unclear.
4. **stage** — при переходе в guidance и после философского ответа не откатывать в warmup; проверить, что `USER_STAGE[user_id]` и `state["turn_index"]` корректно обновляются во всех ранних return.

---

## BUG 3 — Дубли сообщений (двойное приветствие, двойные ответы)

### Возможные причины

#### A) Несколько реплик на Railway (polling)

**Файл:** `utils/telegram_idempotency.py`  
- `IdempotencyMiddleware` кеширует `update_id` в памяти (`_seen`)
- Кеш не разделяется между процессами
- Если запущено несколько воркеров/реплик, каждая получает один и тот же update → каждая обрабатывает и шлёт ответ → дубли

**Проверка:** количество реплик в Railway, настройки scaling.

#### B) Telegram retry

- При сбоях Telegram может повторно отправить update
- `IdempotencyMiddleware` должен отсекать повторы (по `update_id`) в рамках одного процесса

#### C) Split в send_pipeline

**Файл:** `utils/send_pipeline.py`  
- При длинном тексте (> 3500) — `_split_by_paragraphs` → несколько `send_message`
- Ожидаемо: части разные (1, 2, 3…)
- Риск: если часть после strip пустая или логика strip ошибочна — возможны пустые или лишние сообщения (код уже отфильтровывает `parts = [p for p in parts if p.strip()]`).

#### D) Двойная обработка /start

- `@dp.message(CommandStart())` → `cmd_start` → один `send_text(ONBOARDING_MESSAGE_RU)`
- `@dp.message(F.text)` ловит любой текст, в т.ч. `/start`
- В aiogram 3 при первом совпадении `CommandStart` обработка обычно заканчивается
- Риск: если порядок хэндлеров или конфиг роутера меняется — теоретически оба могут сработать

#### E) Дополнительная отправка после close

- После «понял, спасибо» бот возвращает orientation
- Если есть какой‑то фоновый таск или отложенная логика — возможна лишняя отправка (нужна проверка кода на `asyncio.create_task` и т.п.)

### Рекомендации

1. **Идемпотентность по update_id** — вынести кеш в Redis (или аналог), чтобы дедупликация работала между репликами.
2. **Одна реплика для бота** — до появления shared idempotency держать один инстанс при polling.
3. **Явная защита /start** — в `handle_message` в начале:
   ```python
   if (message.text or "").strip().startswith("/"):
       return  # команды обрабатывают отдельные хэндлеры
   ```
4. **Логирование** — перед `send_text` писать `update_id`, `message_id`, `chat_id`, `text[:50]`, correlation-id.
5. **Проверка split** — добавить assert/логирование, что `len(parts) > 0` и ни одна часть не пустая перед отправкой.

---

## Краткая таблица точек фикса

| Баг | Файл | Функция/условие | Рекомендуемый фикс |
|-----|------|------------------|--------------------|
| BUG 1 | `bot.py` | `is_concept` check, first_turn gate | Уже есть; убедиться в деплое и логах |
| BUG 1 | `first_turn_templates.py` | `_is_religion_topic_question` → skip | Уже есть |
| BUG 2 | `bot.py` 927–942 | orientation gate | Добавить guard для ack/close |
| BUG 2 | `intent_gate.py` | `is_unclear_message` | Исключить «понял», «спасибо»; расширить TOPIC_MARKERS |
| BUG 2 | `pattern_governor.py` | `RELIGIOUS_MARKERS` | Добавить «вер», «стыд», «вина» |
| BUG 3 | Railway | Несколько реплик | 1 реплика или Redis для update_id |
| BUG 3 | `telegram_idempotency.py` | In-memory cache | Shared store (Redis) для multi-replica |
| BUG 3 | `bot.py` handle_message | F.text ловит /start | Guard: `if text.startswith("/"): return` |
