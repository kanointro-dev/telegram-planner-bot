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
        # Обрезаем слишком длинные названия (больше 50 символов)
        if len(title) > 50:
            title = title[:47] + "..."
        lines.append(f"{i}. {u}{due_text} {title}")
    
    lines.append("")
    lines.extend(footer_lines)
    
    result = "\n".join(lines)
    
    # Если сообщение длиннее 4000 символов — обрезаем задачи
    if len(result) > 4000:
        # Оставляем только первые 15 задач
        lines = [heading, ""]
        for i, t in enumerate(tasks[:15], start=1):
            u = kb.urgency_emoji(t.priority)
            if t.due_at:
                due_s = format_dt_short(t.due_at, tz)
                due_text = f" <b>{due_s}</b>"
            elif t.status == TaskStatus.PAUSED:
                due_text = " ⏸ пауза"
            else:
                due_text = ""
            title = t.title.replace("\n", " ")
            if len(title) > 50:
                title = title[:47] + "..."
            lines.append(f"{i}. {u}{due_text} {title}")
        lines.append("")
        lines.append(f"⚠️ Показаны первые 15 задач из {len(tasks)}")
        lines.extend(footer_lines)
        result = "\n".join(lines)
    
    return result


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
