#!/usr/bin/env python3
"""
Двухэтапный автопрогон для system_builder_intense и structured_ops_stoic.
Этап 1: smoke (limit 4)
Этап 2: full (limit 12)
Сбор метрик и сохранение отчётов.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = PROJECT_ROOT / "reports"
PERSONAS = ["system_builder_intense", "structured_ops_stoic"]


def count_multi_question_violations(text: str, max_q: int = 1) -> int:
    """Считает ответы с более чем max_q вопросительными знаками."""
    if not text:
        return 0
    qn = (text or "").count("?")
    return 1 if qn > max_q else 0


def is_long_context(user_text: str, min_len: int = 80) -> bool:
    return len((user_text or "").strip()) >= min_len


def looks_like_warmup(text: str) -> bool:
    t = (text or "").lower()
    markers = ["три зоны", "состояние", "смысл", "опора", "выбери угол", "напиши одно слово"]
    return sum(1 for m in markers if m in t) >= 2


def compute_metrics_from_jsonl(out_dir: Path) -> dict:
    """Пост-обработка jsonl для доп. метрик."""
    metrics = {
        "multi_question_violations": 0,
        "warmup_used_on_long_context": 0,
        "avg_answer_length": 0,
        "total_turns": 0,
        "total_len": 0,
    }
    if not out_dir.exists():
        return metrics
    for p in out_dir.rglob("*.jsonl"):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                user = entry.get("user", "") or ""
                bot = entry.get("bot", "") or ""
                metrics["multi_question_violations"] += count_multi_question_violations(bot)
                if is_long_context(user) and looks_like_warmup(bot):
                    metrics["warmup_used_on_long_context"] += 1
                metrics["total_len"] += len(bot)
                metrics["total_turns"] += 1
    if metrics["total_turns"]:
        metrics["avg_answer_length"] = round(metrics["total_len"] / metrics["total_turns"], 1)
    return metrics


def run_synth(persona: str, limit: int, stage: str) -> dict:
    """Запуск run_synth_simulation и сбор результата."""
    out_subdir = f"{stage}_{persona}"
    out_dir = REPORTS_DIR / out_subdir
    report_path = REPORTS_DIR / f"{stage}_{persona}.json"
    cmd = [
        sys.executable,
        "-m", "eval.run_synth_simulation",
        "--persona", persona,
        "--limit", str(limit),
        "--out_dir", str(out_dir),
        "--out", str(report_path),
    ]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError(f"run_synth_simulation failed: {result.returncode}")
    report = {}
    if report_path.exists():
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
    # Найти самый свежий run_id в out_dir
    latest_run = None
    if out_dir.exists():
        subdirs = [d for d in out_dir.iterdir() if d.is_dir()]
        if subdirs:
            latest_run = max(subdirs, key=lambda d: d.name)
    if latest_run:
        extra = compute_metrics_from_jsonl(latest_run)
        report["multi_question_violations"] = extra["multi_question_violations"]
        report["warmup_used_on_long_context"] = extra["warmup_used_on_long_context"]
        if "avg_answer_length" not in report or not report["avg_answer_length"]:
            report["avg_answer_length"] = extra["avg_answer_length"]
    report["completion_guard_repairs"] = report.get("completion_guard_repairs", 0)
    report["philosophy_pipeline_hits"] = report.get("philosophy_pipeline_hits", 0)
    report["short_mode_hits"] = report.get("short_mode_hits", 0)
    return report


def write_summary(persona: str, smoke_report: dict, full_report: dict) -> None:
    """Записывает сводку в reports/summary_{persona}.txt"""
    path = REPORTS_DIR / f"summary_{persona}.txt"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"=== SYNTH RUN COMPLETE ===",
        f"persona: {persona}",
        "",
        "SMOKE:",
        f"  dialogs: {smoke_report.get('dialogs', 'N/A')}",
        f"  explain_short: {smoke_report.get('explain_too_short_count', 'N/A')}",
        f"  multi_question: {smoke_report.get('multi_question_violations', 'N/A')}",
        f"  avg_len: {smoke_report.get('avg_answer_length', 'N/A')}",
        "",
        "FULL:",
        f"  dialogs: {full_report.get('dialogs', 'N/A')}",
        f"  explain_short: {full_report.get('explain_too_short_count', 'N/A')}",
        f"  multi_question: {full_report.get('multi_question_violations', 'N/A')}",
        f"  avg_len: {full_report.get('avg_answer_length', 'N/A')}",
        "",
        "violations:",
        f"  warmup_mismatch: {full_report.get('warmup_mismatch_count', 0)}",
        f"  context_drop: {full_report.get('context_drop_count', 0)}",
        f"  warmup_on_long_context: {full_report.get('warmup_used_on_long_context', 0)}",
        "",
        "=========================",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Сводка: {path}")


def print_final(persona: str, report: dict, stage: str) -> None:
    print(f"""
=== SYNTH RUN COMPLETE ===
persona: {persona}
stage: {stage}
dialogs: {report.get('dialogs', 'N/A')}
violations:
  warmup_mismatch: {report.get('warmup_mismatch_count', 0)}
  context_drop: {report.get('context_drop_count', 0)}
  warmup_on_long: {report.get('warmup_used_on_long_context', 0)}
explain_short: {report.get('explain_too_short_count', 0)}
multi_question: {report.get('multi_question_violations', 0)}
avg_len: {report.get('avg_answer_length', 0)}
=========================""")


def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    print("================================")
    print("ЭТАП 1 — SMOKE TEST")
    print("================================")
    all_smoke = {}
    all_full = {}
    for persona in PERSONAS:
        print(f"\n--- Smoke: {persona} ---")
        try:
            report = run_synth(persona, limit=4, stage="smoke")
            all_smoke[persona] = report
            print_final(persona, report, "smoke")
        except Exception as e:
            print(f"Ошибка: {e}")
            all_smoke[persona] = {"error": str(e)}
    print("\n================================")
    print("ЭТАП 2 — FULL RUN")
    print("================================")
    for persona in PERSONAS:
        print(f"\n--- Full: {persona} ---")
        try:
            report = run_synth(persona, limit=12, stage="full")
            all_full[persona] = report
            print_final(persona, report, "full")
            write_summary(persona, all_smoke.get(persona, {}), report)
        except Exception as e:
            print(f"Ошибка: {e}")
            all_full[persona] = {"error": str(e)}
    print("\nГотово. Отчёты в reports/")


if __name__ == "__main__":
    main()
