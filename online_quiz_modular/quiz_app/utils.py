"""Small, framework-independent helper functions (no Streamlit imports).

Keeping these pure makes them easy to unit-test and reuse from any module.
"""

from __future__ import annotations

import html
import re
import uuid
from datetime import datetime
from typing import Any, Optional

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def now_str() -> str:
    """Current local time as ``YYYY-MM-DD HH:MM:SS`` (the format stored in SQLite)."""
    return datetime.now().strftime(DATE_FORMAT)


def parse_date(value: Any) -> Optional[datetime]:
    """Parse a stored date string; returns ``None`` when it cannot be understood."""
    if not value:
        return None
    text = str(value).strip()
    for fmt in (DATE_FORMAT, "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def pretty_date(value: Any, with_time: bool = False) -> str:
    """Human friendly date such as ``06 November 2026`` (or with the time)."""
    parsed = parse_date(value)
    if parsed is None:
        return str(value) if value else "—"
    return parsed.strftime("%d %B %Y, %H:%M" if with_time else "%d %B %Y")


def esc(value: Any) -> str:
    """HTML-escape any value so it is safe inside ``unsafe_allow_html`` markup."""
    return html.escape("" if value is None else str(value), quote=True)


def esc_br(value: Any) -> str:
    """Like :func:`esc` but keeps line breaks (as ``<br>``) for multi-line text."""
    return esc(value).replace("\r\n", "\n").replace("\n", "<br>")


_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#~$<>|&])")


def md_escape(value: Any) -> str:
    """Escape Markdown control characters so user text is displayed literally."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", "" if value is None else str(value))


def initials(name: str) -> str:
    """Up to two capital letters for an avatar (``"Asha Nair"`` -> ``"AN"``)."""
    parts = [p for p in re.split(r"[\s._\-]+", (name or "").strip()) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def safe_filename(text: str, default: str = "file") -> str:
    """Reduce arbitrary text to a safe file-name fragment."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text or "").strip("_")
    return cleaned or default


def percentage_of(score: int, total: int) -> float:
    """Percentage helper that never divides by zero."""
    return (score / total * 100.0) if total else 0.0


def grade_label(percentage: float) -> str:
    """Achievement level printed on certificates."""
    if percentage >= 90:
        return "Distinction"
    if percentage >= 75:
        return "Merit"
    return "Pass"


def new_certificate_id() -> str:
    """Create a unique certificate identifier such as ``QUIZ-3F9A1C07BD``."""
    return "QUIZ-" + uuid.uuid4().hex[:10].upper()


def display_name(user: Optional[dict]) -> str:
    """Full name if the user has one, otherwise the username."""
    if not user:
        return ""
    return (user.get("full_name") or "").strip() or user.get("username", "")
