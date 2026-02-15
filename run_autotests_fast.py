#!/usr/bin/env python3
"""
Быстрый автопрогон через eval_runner (фиксированные turns, без LLM).
Использует eval/scenarios/{persona}.yaml — persona-specific сценарии.
Pack B использует eval/scenarios/_default.yaml если файла нет.
"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = PROJECT_ROOT / "reports"

# Персоны с собственными сценариями в eval/scenarios/
PERSONAS_WITH_SCENARIOS = ["system_builder_intense", "structured_ops_stoic"]
# Pack B — без своего файла, нужен _default (eval_runner требует файл)
# eval_runner требует eval/scenarios/{persona}.yaml — для Pack B создаём симлинки или отдельные минимальные файлы
# Проще: run_autotests_fast поддерживает только персоны с существующими сценариями
SCENARIOS_DIR = PROJECT_ROOT / "eval" / "scenarios"


def _personas_to_run() -> list[str]:
    """Персоны, для которых есть eval/scenarios/{persona}.yaml."""
    result = []
    for f in SCENARIOS_DIR.glob("*.yaml"):
        if f.name.startswith("_"):
            continue
        result.append(f.stem)
    return sorted(result) if result else PERSONAS_WITH_SCENARIOS


def count_multi_question(text: str, max_q: int = 1) -> int:
    return 1 if (text or "").count("?") > max_q else 0


def looks_warmup(text: str) -> bool:
    t = (text or "").lower()
    markers = ["три зоны", "состояние", "смысл", "опора", "выбери угол", "напиши одно слово"]
    return sum(1 for m in markers if m in t) >= 2


def compute_metrics(out_dir: Path) -> dict:
    sys.path.insert(0, str(PROJECT_ROOT))
    from eval.checks import run_checks

    m = {
        "multi_question_violations": 0,
        "warmup_on_long": 0,
        "total_len": 0,
        "turns": 0,
        "explain_too_short_count": 0,
    }
    prev_user = None
    for p in out_dir.rglob("*.jsonl"):
        with open(p, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                u, b = (e.get("user") or ""), (e.get("bot") or "")
                checks = run_checks(u, b, prev_user)
                if checks.get("explain_too_short"):
                    m["explain_too_short_count"] += 1
                m["multi_question_violations"] += count_multi_question(b)
                if len(u.strip()) >= 80 and looks_warmup(b):
                    m["warmup_on_long"] += 1
                m["total_len"] += len(b)
                m["turns"] += 1
                prev_user = u
    m["avg_answer_length"] = round(m["total_len"] / m["turns"], 1) if m["turns"] else 0
    return m


def run_eval_runner(persona: str, out_dir: Path) -> tuple[int, dict]:
    """Запуск eval_runner, возвращает (число диалогов, метрики)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "eval_runner.py", "--persona", persona, "--out_dir", str(out_dir)],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    subdirs = [d for d in out_dir.iterdir() if d.is_dir() and persona in d.name]
    if not subdirs:
        return 0, {}
    latest = max(subdirs, key=lambda d: d.name)
    dialogs = len(list(latest.glob("*.jsonl")))
    metrics = compute_metrics(latest)
    metrics["dialogs"] = dialogs
    return dialogs, metrics


def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    personas = _personas_to_run()
    print(f"=== FAST AUTOTEST (eval_runner, {len(personas)} personas) ===\n")
    for persona in personas:
        print(f"--- {persona} ---")
        out_dir = REPORTS_DIR / persona
        try:
            n, m = run_eval_runner(persona, out_dir)
            print(f"""
=== SYNTH RUN COMPLETE ===
persona: {persona}
dialogs: {n}
violations: multi_q={m.get('multi_question_violations',0)} warmup_long={m.get('warmup_on_long',0)}
explain_short: {m.get('explain_too_short_count',0)}
multi_question: {m.get('multi_question_violations',0)}
avg_len: {m.get('avg_answer_length',0)}
=========================""")
            summary = REPORTS_DIR / f"summary_{persona}.txt"
            with open(summary, "w", encoding="utf-8") as f:
                f.write(f"persona: {persona}\ndialogs: {n}\nexplain_short: {m.get('explain_too_short_count',0)}\navg_len: {m.get('avg_answer_length')}\n")
        except Exception as e:
            print(f"Ошибка: {e}")
    print("\nГотово. reports/")


if __name__ == "__main__":
    main()
