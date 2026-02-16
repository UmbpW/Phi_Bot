"""TEST COST OPTIMIZER V1: кэширование LLM-ответов для дешёвых регресс-прогонов."""

import json
import hashlib
import os
from typing import Any, Optional, Dict


def _stable_hash(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_get(cache_dir: str, key_obj: Any) -> Optional[Dict]:
    if not cache_dir:
        return None
    os.makedirs(cache_dir, exist_ok=True)
    key = _stable_hash(key_obj)
    path = os.path.join(cache_dir, key + ".json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def cache_put(cache_dir: str, key_obj: Any, value: Dict) -> None:
    if not cache_dir:
        return
    os.makedirs(cache_dir, exist_ok=True)
    key = _stable_hash(key_obj)
    path = os.path.join(cache_dir, key + ".json")
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        pass
