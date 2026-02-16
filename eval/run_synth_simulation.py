#!/usr/bin/env python3
"""Multi-turn синтетический eval: persona × scenario (фиксированные turns), сбор метрик UX.
TEST COST OPTIMIZER V1: --mode fast|product|release, кэш, дешёвые модели.
TEST COST OPTIMIZER V1.1: run-only-failed, cost telemetry."""

import argparse
import glob
import json
import math
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Union, List, Dict, Any, Optional

# PHI_EVAL=1 — обход проверки TELEGRAM_TOKEN при импорте
os.environ["PHI_EVAL"] = "1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import yaml
except ImportError:
    yaml = None


def load_yaml(path: Path) -> Union[dict, list]:
    if not yaml:
        raise RuntimeError("Установите PyYAML: pip install pyyaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def load_personas(personas_path: Path) -> List[Dict[str, Any]]:
    """
    Загрузка персон из YAML.
    - data dict + ключ "personas" -> берём data["personas"]
    - data list -> берём как есть
    - data dict без "personas" -> list(values) (legacy, без persona_defaults как персоны)
    """
    if not personas_path.exists():
        raise FileNotFoundError(
            f"Файл персон не найден: {personas_path}\n"
            f"Укажите путь через --personas-file или создайте файл."
        )
    data = load_yaml(personas_path)
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict) and p.get("id")]
    if isinstance(data, dict):
        if "personas" in data:
            persons = data["personas"]
            if isinstance(persons, list):
                return [p for p in persons if isinstance(p, dict) and p.get("id")]
        return [p for p in data.values() if isinstance(p, dict) and p.get("id")]
    return []


def load_scenarios_for_persona(persona_id: str, scenarios_dir: Path) -> List[Dict[str, Any]]:
    """
    Загрузка сценариев для персоны.
    Сначала eval/scenarios/{persona_id}.yaml, если нет — eval/scenarios/_default.yaml.
    """
    persona_file = scenarios_dir / f"{persona_id}.yaml"
    default_file = scenarios_dir / "_default.yaml"
    path = persona_file if persona_file.exists() else default_file
    if not path.exists():
        return []
    data = load_yaml(path)
    scenarios = data.get("scenarios", []) if isinstance(data, dict) else []
    return [s for s in scenarios if isinstance(s, dict) and (s.get("turns") or s.get("id"))]


def _find_latest_report(path_hint: Optional[str] = None) -> Optional[str]:
    """Найти последний отчёт JSON. path_hint — явный путь."""
    if path_hint and os.path.exists(path_hint):
        return path_hint
    for base in ["eval/reports", "reports", str(PROJECT_ROOT / "eval" / "reports"), str(PROJECT_ROOT / "reports")]:
        if os.path.isdir(base):
            candidates = glob.glob(os.path.join(base, "*.json"))
            if candidates:
                candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                return candidates[0]
    return None


def _extract_failed_dialogue_ids(report_obj: dict) -> set:
    """Максимально терпимый парсер: диалоги с violations > 0."""
    failed = set()

    ds = report_obj.get("dialogues")
    if isinstance(ds, list):
        for d in ds:
            if not isinstance(d, dict):
                continue
            v = d.get("violations") or d.get("checks_failed") or d.get("fails")
            if v and (not isinstance(v, (list, dict)) or len(v) > 0):
                did = d.get("dialogue_id") or d.get("id") or d.get("file")
                if did:
                    failed.add(str(did))
        if failed:
            return failed

    tv = report_obj.get("top_violations")
    if isinstance(tv, list):
        for item in tv:
            if isinstance(item, dict) and item.get("file"):
                failed.add(str(item["file"]))
        if failed:
            return failed

    vbd = report_obj.get("violations_by_dialogue")
    if isinstance(vbd, dict):
        for k, cnt in vbd.items():
            try:
                if int(cnt) > 0:
                    failed.add(str(k))
            except Exception:
                pass
        if failed:
            return failed

    return failed


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
    """Один ход: пользователь → бот."""
    from bot import (
        USER_STATE,
        USER_STAGE,
        USER_MSG_COUNT,
        HISTORY_STORE,
        generate_reply_core,
    )
    HISTORY_STORE[user_id] = list(history)
    if user_id not in USER_STATE:
        USER_STATE[user_id] = _default_state(user_id)
    if user_id not in USER_STAGE:
        USER_STAGE[user_id] = "warmup"
    if user_id not in USER_MSG_COUNT:
        USER_MSG_COUNT[user_id] = 0

    result = generate_reply_core(user_id, user_text)
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
    parser.add_argument(
        "--personas-file",
        type=str,
        default="",
        help="Путь к YAML с персонами (по умолчанию eval/synth_personas.yaml)",
    )
    # TEST COST OPTIMIZER V1
    parser.add_argument("--mode", choices=["fast", "product", "release"], default="fast")
    parser.add_argument("--cache-dir", default="eval/.cache_llm")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--bot-model", default=None)
    parser.add_argument("--user-model", default=None)
    parser.add_argument("--fast-min-chars", type=int, default=320)
    parser.add_argument("--product-min-chars", type=int, default=900)
    parser.add_argument("--max-tokens-fast", type=int, default=450)
    parser.add_argument("--max-tokens-product", type=int, default=900)
    # TEST COST OPTIMIZER V1.1
    parser.add_argument("--only-failed", action="store_true")
    parser.add_argument("--failed-from", default=None, help="Path to previous report JSON")

    args = parser.parse_args()
    if args.persona_alias:
        args.only_persona = args.only_persona or args.persona_alias

    # TEST COST OPTIMIZER V1: конфиг режимов (устанавливаем ДО импорта bot)
    use_cache = not args.no_cache
    if args.mode == "fast":
        BOT_MODEL = args.bot_model or "gpt-5-mini"
        MIN_CHARS = args.fast_min_chars
        BOT_MAX_TOKENS = args.max_tokens_fast
        FORCE_NO_EXPAND = True
    elif args.mode == "product":
        BOT_MODEL = args.bot_model or "gpt-5.2"
        MIN_CHARS = args.product_min_chars
        BOT_MAX_TOKENS = args.max_tokens_product
        FORCE_NO_EXPAND = False
    else:
        BOT_MODEL = args.bot_model or "gpt-5.2"
        MIN_CHARS = args.product_min_chars
        BOT_MAX_TOKENS = args.max_tokens_product + 200
        FORCE_NO_EXPAND = False

    os.environ["EVAL_MODEL"] = BOT_MODEL
    os.environ["EVAL_MAX_TOKENS"] = str(BOT_MAX_TOKENS)
    os.environ["EVAL_MIN_CHARS"] = str(MIN_CHARS)
    os.environ["EVAL_NO_EXPAND"] = "1" if FORCE_NO_EXPAND else "0"
    os.environ["EVAL_CACHE_DIR"] = args.cache_dir if use_cache else ""
    os.environ["EVAL_USE_CACHE"] = "1" if use_cache else "0"

    # TEST COST OPTIMIZER V1.1: оценка стоимости (USD per 1K tokens)
    MODEL_PRICING_USD_PER_1K = {
        "gpt-5.2": {"in": 0.010, "out": 0.030},
        "gpt-5-mini": {"in": 0.002, "out": 0.006},
        "gpt-5.2-mini": {"in": 0.002, "out": 0.006},
        "gpt-4.1-mini": {"in": 0.001, "out": 0.003},
        "_default": {"in": 0.005, "out": 0.015},
    }

    def _estimate_cost_usd(model: str, in_tokens: int, out_tokens: int) -> float:
        p = MODEL_PRICING_USD_PER_1K.get(model) or MODEL_PRICING_USD_PER_1K["_default"]
        return (in_tokens / 1000.0) * p["in"] + (out_tokens / 1000.0) * p["out"]

    eval_dir = Path(__file__).resolve().parent
    personas_path = Path(args.personas_file) if args.personas_file else eval_dir / "synth_personas.yaml"
    personas_path = personas_path.resolve()
    if not personas_path.is_absolute():
        personas_path = (PROJECT_ROOT / personas_path).resolve()

    try:
        personas = load_personas(personas_path)
    except FileNotFoundError as e:
        print(str(e))
        sys.exit(1)

    if not personas:
        print(f"В файле {personas_path} нет персон с полем id.")
        sys.exit(1)

    scenarios_dir = eval_dir / "scenarios"
    if not scenarios_dir.exists():
        print(f"Каталог сценариев не найден: {scenarios_dir}")
        sys.exit(1)

    default_scenarios = load_scenarios_for_persona("_default", scenarios_dir)
    if not default_scenarios:
        print(f"Не найден eval/scenarios/_default.yaml с fallback-сценариями.")
        sys.exit(1)

    if args.only_persona:
        personas = [p for p in personas if p.get("id") == args.only_persona]
        if not personas:
            print(f"Персона не найдена: {args.only_persona}")
            sys.exit(1)

    from eval.checks import run_checks
    from bot import EVAL_CALL_METAS

    only_failed_pairs = None
    if args.only_failed:
        rp = _find_latest_report(args.failed_from)
        if rp:
            try:
                with open(rp, "r", encoding="utf-8") as f:
                    prev_report = json.load(f)
                failed_ids = _extract_failed_dialogue_ids(prev_report)
                dialogues_list = prev_report.get("dialogues") or []
                only_failed_pairs = {
                    (d["persona_id"], d["scenario_id"])
                    for d in dialogues_list
                    if isinstance(d, dict)
                    and d.get("dialogue_id") in failed_ids
                    and d.get("persona_id")
                    and d.get("scenario_id")
                }
                if failed_ids and not only_failed_pairs:
                    print(f"[eval] only-failed: report has no 'dialogues' with persona_id/scenario_id; running full set")
                    only_failed_pairs = None
                print(f"[eval] only-failed=ON report={rp} failed_ids={len(failed_ids)} pairs={len(only_failed_pairs) if only_failed_pairs else 0}")
            except Exception as e:
                print(f"[eval] only-failed=ON but failed to parse report: {e}")
                only_failed_pairs = set()
        else:
            print("[eval] only-failed=ON but no previous report found; running full set")
            only_failed_pairs = None

    print(f"[eval] mode={args.mode} model={BOT_MODEL} cache={'on' if use_cache else 'off'}")

    telemetry = {
        "mode": args.mode,
        "cache_dir": args.cache_dir,
        "use_cache": use_cache,
        "bot_model": BOT_MODEL,
        "user_model": "n/a",
        "calls": 0,
        "cached_hits": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd_est": 0.0,
        "per_model": defaultdict(lambda: {"calls": 0, "cached_hits": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd_est": 0.0}),
    }

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
    persona_ids_run = []
    dialogues_report = []

    dialog_id = 0
    for persona in personas:
        persona_id = persona.get("id", "unknown")
        scenarios = load_scenarios_for_persona(persona_id, scenarios_dir)
        if not scenarios:
            scenarios = default_scenarios

        if args.only_scenario:
            scenarios = [s for s in scenarios if s.get("id") == args.only_scenario]
            if not scenarios:
                continue

        for scenario in scenarios:
            if args.limit and dialog_id >= args.limit:
                break
            scenario_id = scenario.get("id", "unknown")
            turns = scenario.get("turns", [])
            if not turns:
                continue

            if only_failed_pairs is not None and len(only_failed_pairs) > 0:
                if (persona_id, scenario_id) not in only_failed_pairs:
                    continue

            user_id = f"synth:{persona_id}:{scenario_id}:{dialog_id}"
            history = []
            prev_user = None
            dialog = []
            dialog_violations = []

            for user_text in turns:
                user_text = user_text.strip() if isinstance(user_text, str) else str(user_text)
                result = run_turn(user_id, user_text, history)
                reply = result.get("reply_text", "")

                for meta in EVAL_CALL_METAS:
                    telemetry["calls"] += 1
                    telemetry["cached_hits"] += 1 if meta.get("cached_hit") else 0
                    u = meta.get("usage") or {}
                    tin = int(u.get("input_tokens") or 0)
                    tout = int(u.get("output_tokens") or 0)
                    telemetry["tokens_in"] += tin
                    telemetry["tokens_out"] += tout
                    model = meta.get("model", BOT_MODEL)
                    cost = _estimate_cost_usd(model, tin, tout)
                    telemetry["cost_usd_est"] += cost
                    pm = telemetry["per_model"][model]
                    pm["calls"] += 1
                    pm["cached_hits"] += 1 if meta.get("cached_hit") else 0
                    pm["tokens_in"] += tin
                    pm["tokens_out"] += tout
                    pm["cost_usd_est"] += cost

                history.append({"role": "user", "content": user_text})
                history.append({"role": "assistant", "content": reply})
                dialog.append({"user": user_text, "bot": reply})
                checks = run_checks(user_text, reply, prev_user)
                if checks.get("too_short"):
                    counts["too_short_count"] += 1
                    dialog_violations.append("too_short")
                if checks.get("warmup_triage"):
                    counts["warmup_mismatch_count"] += 1
                    dialog_violations.append("warmup_triage")
                if checks.get("context_drop"):
                    counts["context_drop_count"] += 1
                    dialog_violations.append("context_drop")
                    from utils.context_anchor import debug_context_drop
                    dbg = debug_context_drop(prev_user or "", reply)
                    print(f"[context_drop] d{dialog_id} turn: tokens={dbg.get('tokens')} cd_words={dbg.get('cd_words')} in_first={dbg.get('in_first_para')} in_full={dbg.get('in_full_reply')}")
                if checks.get("meta_tail"):
                    counts["meta_tail_count"] += 1
                    dialog_violations.append("meta_tail")
                if checks.get("incomplete"):
                    counts["incomplete_count"] += 1
                    dialog_violations.append("incomplete")
                if checks.get("explain_too_short"):
                    counts["explain_too_short_count"] += 1
                    dialog_violations.append("explain_too_short")
                counts["total_turns"] += 1
                counts["total_len"] += len(reply or "")
                prev_user = user_text

            dialogue_id = f"d{dialog_id}_{persona_id}_{scenario_id}"
            dialogues_report.append({
                "dialogue_id": dialogue_id,
                "persona_id": persona_id,
                "scenario_id": scenario_id,
                "violations": list(dict.fromkeys(dialog_violations)),
            })

            out_file = out_dir / f"{dialogue_id}.jsonl"
            with open(out_file, "w", encoding="utf-8") as f:
                for entry in dialog:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            if persona_id not in persona_ids_run:
                persona_ids_run.append(persona_id)
            dialog_id += 1

    avg_len = counts["total_len"] / counts["total_turns"] if counts["total_turns"] else 0

    telemetry_json = dict(telemetry)
    telemetry_json["per_model"] = dict(telemetry["per_model"])
    telemetry_json["tokens_total"] = telemetry["tokens_in"] + telemetry["tokens_out"]
    telemetry_json["cache_hit_rate"] = (telemetry["cached_hits"] / telemetry["calls"]) if telemetry["calls"] else 0.0

    report = {
        "mode": args.mode,
        "bot_model": BOT_MODEL,
        "persona": args.only_persona or (personas[0].get("id") if personas else ""),
        "persona_ids_run": persona_ids_run,
        "dialogs": dialog_id,
        "dialogues": dialogues_report,
        "total_turns": counts["total_turns"],
        "explain_too_short_count": counts["explain_too_short_count"],
        "too_short_count": counts["too_short_count"],
        "warmup_mismatch_count": counts["warmup_mismatch_count"],
        "context_drop_count": counts["context_drop_count"],
        "meta_tail_count": counts["meta_tail_count"],
        "incomplete_count": counts["incomplete_count"],
        "avg_answer_length": round(avg_len, 1),
        "out_dir": str(out_dir),
        "cost_telemetry": telemetry_json,
    }

    report_path = args.report_file
    if not report_path:
        reports_dir = eval_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = str(reports_dir / f"report_{run_id}.json")
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n--- Сводка ---")
    print(f"personas: {persona_ids_run}")
    print(f"avg_len: {avg_len:.0f}")
    print(f"too_short_count: {counts['too_short_count']}")
    print(f"warmup_mismatch_count: {counts['warmup_mismatch_count']}")
    print(f"context_drop_count: {counts['context_drop_count']}")
    print(f"meta_tail_count: {counts['meta_tail_count']}")
    print(f"incomplete_count: {counts['incomplete_count']}")
    print(f"explain_too_short_count: {counts['explain_too_short_count']}")
    print(f"Диалогов: {dialog_id}, ходов: {counts['total_turns']}")
    print(f"--- Cost telemetry ---")
    print(f"calls: {telemetry['calls']} cached_hits: {telemetry['cached_hits']} hit_rate: {telemetry_json['cache_hit_rate']:.2f}")
    print(f"tokens: in={telemetry['tokens_in']} out={telemetry['tokens_out']} total={telemetry_json['tokens_total']}")
    print(f"cost_usd_est: ${telemetry['cost_usd_est']:.4f}")
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
