#!/usr/bin/env python3
"""Eval runner для persona-scenarios: фиксированные turns, без LLM-симулятора."""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ["PHI_EVAL"] = "1"

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import yaml
except ImportError:
    yaml = None


def load_yaml(path: Path):
    if not yaml:
        raise RuntimeError("Установите PyYAML: pip install pyyaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _default_state():
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
    from bot import (
        USER_STATE,
        USER_STAGE,
        USER_MSG_COUNT,
        HISTORY_STORE,
        generate_reply_core,
    )
    HISTORY_STORE[user_id] = list(history)
    if user_id not in USER_STATE:
        USER_STATE[user_id] = _default_state()
    if user_id not in USER_STAGE:
        USER_STAGE[user_id] = "warmup"
    if user_id not in USER_MSG_COUNT:
        USER_MSG_COUNT[user_id] = 0

    result = generate_reply_core(user_id, user_text)
    history[:] = list(HISTORY_STORE.get(user_id, []))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--persona", type=str, required=True, help="id персоны (имя файла в eval/scenarios/)")
    parser.add_argument("--out_dir", type=str, default="", help="Папка вывода")
    args = parser.parse_args()

    scenarios_file = PROJECT_ROOT / "eval" / "scenarios" / f"{args.persona}.yaml"
    if not scenarios_file.exists():
        print(f"Не найден {scenarios_file}")
        sys.exit(1)

    data = load_yaml(scenarios_file)
    persona_id = data.get("persona_id", args.persona)
    scenarios = data.get("scenarios", [])

    out_base = Path(args.out_dir) if args.out_dir else PROJECT_ROOT / "eval" / "out"
    run_id = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = out_base / f"{persona_id}_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, scenario in enumerate(scenarios):
        scenario_id = scenario.get("id", f"sc_{i}")
        turns = scenario.get("turns", [])
        if not turns:
            continue

        user_id = f"synth:{persona_id}:{scenario_id}:{i}"
        history = []
        dialog = []

        for user_text in turns:
            result = run_turn(user_id, user_text, history)
            reply = result.get("reply_text", "")
            dialog.append({"user": user_text, "bot": reply})
            history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": reply})

        out_file = out_dir / f"{scenario_id}.jsonl"
        with open(out_file, "w", encoding="utf-8") as f:
            for entry in dialog:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        print(f"  {scenario_id}: {len(dialog)} ходов")

    print(f"\nГотово. Результаты: {out_dir}")


if __name__ == "__main__":
    main()
