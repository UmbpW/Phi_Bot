# Regression test v19 — Finance Rhythm + Answer-First

## Input: длинный финансовый монолог

Пример (как у Игоря): сообщение >250 символов про волновой доход, «то пусто то густо», тревогу о деньгах, паузы между «добычей».

## Expected

- **НЕТ** lens_preview (guided_path)
- **НЕТ** списков школ (A/B/C оптики)
- **НЕТ** option_close («Хочешь продолжить: (1) про причины или (2) про следующий шаг?»)
- 8–18 строк ответа
- максимум 1 вопрос (fork), без «выберем направление»
- Используется lens_finance_rhythm

---

# Regression test v20.1 — Warmup Hard Guard (Turn 1)

## Input: длинный финансовый монолог на первом ходу

Сообщение >250 символов, финансовые ключи (доход, траты, волнами и т.д.).

## Expected

- stage=guidance (НЕ warmup)
- mode=financial_rhythm
- pattern_engine НЕ выбирает C2_uncertainty_soft_frame
- 8–18 строк ответа
- максимум 1 вопрос (fork), без option_close
