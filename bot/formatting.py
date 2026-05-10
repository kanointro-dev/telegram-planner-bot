from __future__ import annotations

import html
from datetime import datetime
from typing import List, Optional

from zoneinfo import ZoneInfo

from bot import keyboards as kb
from bot.models import Task, TaskStatus


def format_dt_short(dt: datetime, tz: ZoneInfo) -> str:
    local = dt.astimezone(tz)
    return local.strftime("%d.%m %H:%M")


def category_emoji(cat: Optional[str]) -> str:
    if cat == "study":
        return "📚"
    if cat == "work":
        return "💼"
    if cat == "life":
        return "🏠"
    return "·"


def format_tasks_monospace_block(
    heading: str,
    tasks: List[Task],
    tz: ZoneInfo,
    *,
    footer_lines: List[str],
) -> str:
    """Обычный текст с HTML-жирной датой."""
    lines = [heading, ""]
    
    for i, t in enumerate(tasks, start=1):
        u = kb.urgency_emoji(t.priority)
        
        if t.due_at:
            due_s = format_dt_short(t.due_at, tz)
            due_text = f" <b>{due_s}</b>"
        elif t.status == TaskStatus.PAUSED:
            due_text = " ⏸ пауза"
        else:
            due_text = ""
        
        title = t.title.replace("\n", " ")
        lines.append(f"{i}. {u}{due_text} {title}")
    
    lines.append("")
    lines.extend(footer_lines)
    return "\n".join(lines)


def format_tasks_plain_fallback(
    heading: str,
    tasks: List[Task],
    tz: ZoneInfo,
    footer_lines: List[str],
) -> str:
    lines = [heading, ""]
    for i, t in enumerate(tasks, start=1):
        u = kb.urgency_emoji(t.priority)
        due = ""
        if t.due_at:
            due = " " + format_dt_short(t.due_at, tz)
        elif t.status == TaskStatus.PAUSED:
            due = " ⏸ пауза"
        lines.append(f"{i}. {u}{due} {t.title}")
    lines.append("")
    lines.extend(footer_lines)
    return "\n".join(lines)


def _pad_r(s: str, width: int) -> str:
    s = s[:width]
    return s + " " * (width - len(s))


def _pad_center(s: str, width: int) -> str:
    s = s[:width]
    pad = width - len(s)
    left = pad // 2
    right = pad - left
    return " " * left + s + " " * right
