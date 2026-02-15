#!/usr/bin/env python3
"""Multi-turn синтетический eval: persona × scenario, сбор метрик UX."""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Union

# PHI_EVAL=1 — обход проверки TELEGRAM_TOKEN при импорте
os.environ["PHI_EVAL"] = "1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Импорт после добавления пути
try:
    import yaml
except ImportError:
    yaml = None


def load_yaml(path: Path) -> Union[dict, list]:
    if not yaml:
        raise RuntimeError("Установите PyYAML: pip install pyyaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def _default_state(user_id) -> dict:
    return {
        "turn_index": 0,
        "last_bridge_turn": -10,
        "last_options": None,
        "guidance_turns_count": 0,
        "last_fork_turn": -10,
        "pending": None,
        "last_user_text": "",
        "last_bot_text": "",
        "active_lens": None,
        "lens_lock_turns_left": 0,
        "last_injection_turn": -10,
        "active_philosophy_line": None,
        "practice_cooldown_turns": 0,
        "last_lens_preview_turn": None,
        "onboarding_shown": True,
        "pending_orientation": False,
        "orientation_lock": False,
        "force_expand_next": False,
    }


def run_turn(user_id, user_text: str, history: list) -> dict:
    """Один ход: пользователь → бот. history синхронизируется с HISTORY_STORE для synth."""
    from bot import (
        USER_STATE,
        USER_STAGE,
        USER_MSG_COUNT,
        HISTORY_STORE,
        generate_reply_core,
    )
    # FIX A: synth — изолированная история, сброс на каждый диалог
    HISTORY_STORE[user_id] = list(history)
    if user_id not in USER_STATE:
        USER_STATE[user_id] = _default_state(user_id)
    if user_id not in USER_STAGE:
        USER_STAGE[user_id] = "warmup"
    if user_id not in USER_MSG_COUNT:
        USER_MSG_COUNT[user_id] = 0

    result = generate_reply_core(user_id, user_text)
    # обновить history после append_history внутри core
    history[:] = list(HISTORY_STORE.get(user_id, []))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Макс. диалогов (0=все)")
    parser.add_argument("--only_persona", type=str, default="", help="id персоны")
    parser.add_argument("--persona", type=str, default="", dest="persona_alias", help="alias для --only_persona")
    parser.add_argument("--only_scenario", type=str, default="", help="id сценария")
    parser.add_argument("--out_dir", type=str, default="", help="Папка вывода")
    parser.add_argument("--out", "--report_file", dest="report_file", type=str, default="", help="JSON отчёт")
    args = parser.parse_args()
    if args.persona_alias:
        args.only_persona = args.only_persona or args.persona_alias

    eval_dir = Path(__file__).resolve().parent
    personas_path = eval_dir / "synth_personas.yaml"
    scenarios_path = eval_dir / "synth_scenarios.yaml"

    if not personas_path.exists() or not scenarios_path.exists():
        print(f"Не найдены {personas_path} или {scenarios_path}")
        sys.exit(1)

    personas = load_yaml(personas_path)
    scenarios = load_yaml(scenarios_path)
    if not isinstance(personas, list):
        personas = list(personas.values()) if isinstance(personas, dict) else []
    if not isinstance(scenarios, list):
        scenarios = list(scenarios.values()) if isinstance(scenarios, dict) else []

    if args.only_persona:
        personas = [p for p in personas if p.get("id") == args.only_persona]
    if args.only_scenario:
        scenarios = [s for s in scenarios if s.get("id") == args.only_scenario]

    from eval.checks import run_checks

    out_base = Path(args.out_dir) if args.out_dir else eval_dir / "out"
    run_id = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = out_base / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    counts = {
        "too_short_count": 0,
        "warmup_mismatch_count": 0,
        "context_drop_count": 0,
        "meta_tail_count": 0,
        "incomplete_count": 0,
        "explain_too_short_count": 0,
        "total_turns": 0,
        "total_len": 0,
    }

    dialog_id = 0
    for persona in personas:
        for scenario in scenarios:
            if args.limit and dialog_id >= args.limit:
                break
            persona_id = persona.get("id", "unknown")
            scenario_id = scenario.get("id", "unknown")
            user_id = f"synth:{persona_id}:{scenario_id}:{dialog_id}"
            history = []
            user_text = scenario.get("seed_message", "Привет")
            turns = scenario.get("length_turns", 7)
            prev_user = None
            dialog = []
            for t in range(turns):
                result = run_turn(user_id, user_text, history)
                reply = result.get("reply_text", "")
                history.append({"role": "user", "content": user_text})
                history.append({"role": "assistant", "content": reply})
                dialog.append({"user": user_text, "bot": reply})
                checks = run_checks(user_text, reply, prev_user)
                if checks.get("too_short"):
                    counts["too_short_count"] += 1
                if checks.get("warmup_triage"):
                    counts["warmup_mismatch_count"] += 1
                if checks.get("context_drop"):
                    counts["context_drop_count"] += 1
                if checks.get("meta_tail"):
                    counts["meta_tail_count"] += 1
                if checks.get("incomplete"):
                    counts["incomplete_count"] += 1
                if checks.get("explain_too_short"):
                    counts["explain_too_short_count"] += 1
                counts["total_turns"] += 1
                counts["total_len"] += len(reply or "")
                prev_user = user_text
                from eval.synth_user_agent import synth_user_next
                user_text = synth_user_next(persona, scenario, history)

            out_file = out_dir / f"d{dialog_id}_{persona.get('id','')}_{scenario.get('id','')}.jsonl"
            with open(out_file, "w", encoding="utf-8") as f:
                for entry in dialog:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            dialog_id += 1

    avg_len = counts["total_len"] / counts["total_turns"] if counts["total_turns"] else 0
    report = {
        "persona": args.only_persona or (personas[0].get("id") if personas else ""),
        "dialogs": dialog_id,
        "total_turns": counts["total_turns"],
        "explain_too_short_count": counts["explain_too_short_count"],
        "too_short_count": counts["too_short_count"],
        "warmup_mismatch_count": counts["warmup_mismatch_count"],
        "context_drop_count": counts["context_drop_count"],
        "meta_tail_count": counts["meta_tail_count"],
        "incomplete_count": counts["incomplete_count"],
        "avg_answer_length": round(avg_len, 1),
        "out_dir": str(out_dir),
    }
    if args.report_file:
        Path(args.report_file).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n--- Сводка ---")
    print(f"avg_len: {avg_len:.0f}")
    print(f"too_short_count: {counts['too_short_count']}")
    print(f"warmup_mismatch_count: {counts['warmup_mismatch_count']}")
    print(f"context_drop_count: {counts['context_drop_count']}")
    print(f"meta_tail_count: {counts['meta_tail_count']}")
    print(f"incomplete_count: {counts['incomplete_count']}")
    print(f"explain_too_short_count: {counts['explain_too_short_count']}")
    print(f"Диалогов: {dialog_id}, ходов: {counts['total_turns']}")


if __name__ == "__main__":
    main()
