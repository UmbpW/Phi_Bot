#!/usr/bin/env python3
"""Пост-обработка jsonl и сбор метрик для сводок."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval.checks import run_checks

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"


def multi_q(text: str, max_q: int = 1) -> int:
    return 1 if (text or "").count("?") > max_q else 0


def looks_warmup(text: str) -> bool:
    t = (text or "").lower()
    markers = ["три зоны", "состояние", "смысл", "опора", "выбери угол", "напиши одно слово"]
    return sum(1 for m in markers if m in t) >= 2


def process_dir(d: Path) -> dict:
    m = {
        "dialogs": 0, "turns": 0, "total_len": 0,
        "explain_too_short_count": 0, "multi_question_violations": 0,
        "warmup_on_long": 0, "too_short_count": 0, "warmup_mismatch_count": 0,
        "context_drop_count": 0, "incomplete_count": 0, "meta_tail_count": 0,
    }
    prev_user = None
    for p in sorted(d.rglob("*.jsonl")):
        with open(p, encoding="utf-8") as f:
            m["dialogs"] += 1
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
                if checks.get("too_short"):
                    m["too_short_count"] += 1
                if checks.get("warmup_triage"):
                    m["warmup_mismatch_count"] += 1
                if checks.get("context_drop"):
                    m["context_drop_count"] += 1
                if checks.get("incomplete"):
                    m["incomplete_count"] += 1
                if checks.get("meta_tail"):
                    m["meta_tail_count"] += 1
                m["multi_question_violations"] += multi_q(b)
                if len(u.strip()) >= 80 and looks_warmup(b):
                    m["warmup_on_long"] += 1
                m["total_len"] += len(b)
                m["turns"] += 1
                prev_user = u
    m["avg_answer_length"] = round(m["total_len"] / m["turns"], 1) if m["turns"] else 0
    return m


def main():
    for name in ["system_builder_intense", "structured_ops_stoic"]:
        base = REPORTS_DIR / name
        if not base.exists():
            subdirs = [d for d in REPORTS_DIR.iterdir() if d.is_dir() and name in d.name]
            if not subdirs:
                continue
            base = max(subdirs, key=lambda d: d.name)
        subdirs = [d for d in base.iterdir() if d.is_dir()]
        if not subdirs:
            subdirs = [base]
        for sub in subdirs:
            m = process_dir(sub)
            if m["turns"] == 0:
                continue
            print(f"\n=== {name} ({sub.name}) ===")
            print(f"dialogs: {m['dialogs']}  turns: {m['turns']}")
            print(f"explain_short: {m['explain_too_short_count']}  multi_q: {m['multi_question_violations']}")
            print(f"avg_len: {m['avg_answer_length']}")
            out = REPORTS_DIR / f"summary_{name}.txt"
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w", encoding="utf-8") as f:
                f.write(f"""=== SYNTH RUN COMPLETE ===
persona: {name}
dialogs: {m['dialogs']}
violations:
  warmup_mismatch: {m['warmup_mismatch_count']}
  context_drop: {m['context_drop_count']}
  warmup_on_long_context: {m['warmup_on_long']}
explain_short: {m['explain_too_short_count']}
multi_question: {m['multi_question_violations']}
avg_len: {m['avg_answer_length']}
=========================
""")


if __name__ == "__main__":
    main()
