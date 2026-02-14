"""Загрузка промптов и линз из файлов."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"
LENSES_DIR = PROJECT_ROOT / "lenses"


def load_file(path: Path) -> str:
    """Загружает содержимое файла."""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def load_system_prompt() -> str:
    """Загружает system_prompt_ru.md."""
    return load_file(PROMPTS_DIR / "system_prompt_ru.md")


def load_router_rules() -> str:
    """Загружает router_rules_ru.md."""
    return load_file(PROMPTS_DIR / "router_rules_ru.md")


def load_warmup_prompt() -> str:
    """Загружает warmup_prompt_ru.md."""
    return load_file(PROMPTS_DIR / "warmup_prompt_ru.md")


def load_philosophy_style() -> str:
    """Загружает philosophy_style_ru.md (дополнение к system prompt)."""
    return load_file(PROMPTS_DIR / "philosophy_style_ru.md")


def load_all_lenses() -> dict[str, str]:
    """Загружает все markdown-файлы из папки lenses.

    Returns:
        dict: имя файла (без расширения) -> содержимое
    """
    result = {}
    if not LENSES_DIR.exists():
        return result
    for path in sorted(LENSES_DIR.glob("*.md")):
        result[path.stem] = load_file(path)
    return result


def build_system_prompt(main_prompt: str, lens_contents: list[str]) -> str:
    """Формирует итоговый system prompt из основного и линз."""
    parts = [main_prompt]
    if lens_contents:
        parts.append("\n\n---\n## Выбранные линзы\n")
        parts.append("\n\n".join(lens_contents))
    return "\n".join(parts)
