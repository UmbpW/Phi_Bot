# semantic_blocks.py — PATCH G: Semantic Blocks Markdown Renderer
"""Parse and render semantic blocks (JSON or heuristic) for longform/explain replies."""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

BLOCKS_OPEN = "<BLOCKS_JSON>"
BLOCKS_CLOSE = "</BLOCKS_JSON>"


def _strip_blocks_container(text: str) -> Tuple[str, Optional[str]]:
    """
    Returns: (text_without_blocks_json, blocks_json_str_or_none)
    """
    if not text:
        return text, None
    m = re.search(rf"{re.escape(BLOCKS_OPEN)}(.*?){re.escape(BLOCKS_CLOSE)}", text, flags=re.DOTALL)
    if not m:
        return text, None
    blocks_raw = m.group(1).strip()
    cleaned = (text[: m.start()] + text[m.end() :]).strip()
    return cleaned, blocks_raw


def parse_blocks_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse JSON between <BLOCKS_JSON>..</BLOCKS_JSON>.
    Expected schema:
      {
        "lead": "string",
        "sections": [{"title":"...", "body":"...", "bullets":[...]}],
        "bridge": "string|null",
        "question": "string|null"
      }
    """
    _, raw = _strip_blocks_container(text)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None
    if "sections" in data and not isinstance(data["sections"], list):
        return None
    return data


def _split_title_body(block: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract title and body from block. Try 'Title — body' first, else first line as title."""
    m = re.match(r"^(.{2,80}?)\s+—\s+(.*)$", block, flags=re.DOTALL)
    if m:
        title = m.group(1).strip()
        body = m.group(2).strip()
        return title, body
    # "Title: body" (1) Аналитическая традиция: уточняют...)
    m2 = re.match(r"^(.{3,80}?)\s*[.:]\s+(.{20,})", block, flags=re.DOTALL)
    if m2:
        return m2.group(1).strip(), m2.group(2).strip()
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    if len(lines) >= 2 and len(lines[0]) <= 80:
        return lines[0], "\n".join(lines[1:]).strip()
    return None, None


def extract_blocks_heuristic(text: str) -> Optional[Dict[str, Any]]:
    """
    Best-effort extractor for texts that already contain headings-like patterns.
    We do NOT overfit; only triggers when it looks like multi-section explanation.
    """
    if not text or len(text) < 450:
        return None

    sections: List[Dict[str, Any]] = []
    bridge = None
    question = None

    # Try "1) Title: body" / "2) Title — body" numbered sections
    numbered = re.split(r"\s*(?=\d\)\s)", text)
    if len(numbered) >= 3:  # lead + 2+ sections
        parts = [p.strip() for p in numbered if p.strip() and re.match(r"^\d\)", p.strip())]
        if len(parts) >= 2:
            lead = numbered[0].strip() if numbered[0].strip() and not re.match(r"^\d\)", numbered[0].strip()) else ""
            if not lead and numbered[0].strip():
                lead = re.sub(r"^\d\)\s*", "", numbered[0].strip())
                parts = parts[1:]
            for p in parts:
                p = re.sub(r"^\d\)\s*", "", p)
                title, body = _split_title_body(p)
                if title and body and len(body) > 30:
                    sections.append({"title": title, "body": body, "bullets": []})
            if len(sections) >= 2:
                return {"lead": lead or None, "sections": sections, "bridge": bridge, "question": question}

    # Try "Title on own line, then — body" (works with single \n between sections)
    _QUESTION_START_BLOCK = ("если ", "что ", "как ", "какой", "какая", "какое", "когда ", "почему ")
    title_line_then_dash = re.findall(
        r"(?:^|\n)([A-ZА-ЯЁ][^\n]{2,55})\n\s*—\s+([^\n]+(?:\n(?![A-ZА-ЯЁ][^\n]{2,55}\n\s*—\s)[^\n]*)*)",
        text,
        re.MULTILINE,
    )
    if len(title_line_then_dash) >= 2:
        valid = []
        for title, body in title_line_then_dash:
            title, body = title.strip(), body.strip()
            if not title or not body or len(body) <= 15:
                continue
            if title.lower().startswith(_QUESTION_START_BLOCK):
                continue
            valid.append((title, body))
        if len(valid) >= 2:
            lead_end = text.find(valid[0][0])
            lead = text[:lead_end].strip() if lead_end > 0 else ""
            for title, body in valid:
                sections.append({"title": title, "body": body, "bullets": []})
            return {"lead": lead, "sections": sections, "bridge": bridge, "question": question}

    chunks = [c.strip() for c in re.split(r"\n\s*\n+", text) if c.strip()]
    if len(chunks) < 2:
        return None

    lead = chunks[0]
    rest = chunks[1:]

    last = rest[-1]
    if "?" in last and len(last) < 280:
        question = last.strip()
        rest = rest[:-1]

    buf = "\n\n".join(rest).strip()

    if "•" in buf:
        parts = [p.strip() for p in re.split(r"\n\s*•\s*", "\n" + buf) if p.strip()]
        if parts and not re.match(r"^[A-Za-zА-Яа-я0-9].*", parts[0]):
            parts = parts[1:]
        if len(parts) >= 2:
            for p in parts:
                title, body = _split_title_body(p)
                if title and body:
                    sections.append({"title": title, "body": body, "bullets": []})
            if len(sections) >= 2:
                return {"lead": lead, "sections": sections, "bridge": bridge, "question": question}

    # Same-line: "Title — body"
    candidates = re.split(r"\n(?=[A-ZА-ЯЁ][^\n]{1,60}\s+—\s+)", buf)
    if len(candidates) >= 2:
        for c in candidates:
            c = c.strip()
            if not c:
                continue
            title, body = _split_title_body(c)
            if title and body:
                sections.append({"title": title, "body": body, "bullets": []})
        if len(sections) >= 2:
            return {"lead": lead, "sections": sections, "bridge": bridge, "question": question}

    return None


def render_blocks_md(blocks: Dict[str, Any]) -> str:
    """Render blocks to Markdown. Always produces readable structure."""
    lead = (blocks.get("lead") or "").strip()
    sections = blocks.get("sections") or []
    bridge = blocks.get("bridge")
    question = blocks.get("question")

    out: List[str] = []
    if lead:
        out.append(lead)

    if sections:
        if out:
            out.append("")
        for s in sections:
            title = (s.get("title") or "").strip()
            body = (s.get("body") or "").strip()
            bullets = s.get("bullets") or []
            line = ""
            if title and body:
                line = f"**{title}** — {body}"
            elif title:
                line = f"**{title}**"
            elif body:
                line = body
            if line:
                out.append(line)
            if bullets and isinstance(bullets, list):
                for b in bullets:
                    b = str(b).strip()
                    if b:
                        out.append(f"- {b}")
            out.append("")

        while out and out[-1] == "":
            out.pop()

    if bridge:
        bridge = str(bridge).strip()
        if bridge:
            if out:
                out.append("")
            out.append(bridge)

    if question:
        question = str(question).strip()
        if question:
            if out:
                out.append("")
            out.append(question)

    return "\n".join(out).strip()


def _is_longform_plan(plan: Dict[str, Any]) -> bool:
    if not plan:
        return False
    if plan.get("explain_mode"):
        return True
    if plan.get("philosophy_pipeline"):
        return True
    return False


def format_reply_md(text: str, plan: Dict[str, Any]) -> Tuple[str, str]:
    """
    Returns: (formatted_text, blocks_used)
    blocks_used: "json" | "heuristic" | "none"
    """
    if not text:
        return text, "none"

    if len(text) < 240:
        cleaned, _ = _strip_blocks_container(text)
        return cleaned.strip(), "none"

    if not _is_longform_plan(plan):
        cleaned, _ = _strip_blocks_container(text)
        return cleaned.strip(), "none"

    blocks = parse_blocks_json(text)
    if blocks:
        rendered = render_blocks_md(blocks)
        return rendered, "json"

    cleaned, _ = _strip_blocks_container(text)
    heur = extract_blocks_heuristic(cleaned)
    if heur:
        rendered = render_blocks_md(heur)
        return rendered, "heuristic"

    return cleaned.strip(), "none"
