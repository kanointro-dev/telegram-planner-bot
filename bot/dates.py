from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

_DMY_TIME = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{1,2})[.:](\d{2}))?$"
)


def parse_due_fragment(raw: str, tz: ZoneInfo) -> Optional[datetime]:
    """
    Разбор фрагмента после «|» в /add.
    Примеры: «2026-05-12 15:30», «2026-05-12», «завтра 15:30», «сегодня», «послезавтра 9:00».
    Если время не указано — по умолчанию 09:00 в вашем часовом поясе.
    """
    s = raw.strip().lower()
    if not s:
        return None

    now = datetime.now(tz)
    today = now.date()

    m = _DMY_TIME.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if m.group(4) is None:
            hh, mm = 9, 0
        else:
            hh, mm = int(m.group(4)), int(m.group(5))
        return datetime(y, mo, d, hh, mm, tzinfo=tz)

    tokens = s.split()
    day_offset: Optional[int] = None
    rest_start = 0

    if tokens[0] == "сегодня":
        day_offset = 0
        rest_start = 1
    elif tokens[0] == "завтра":
        day_offset = 1
        rest_start = 1
    elif tokens[0] == "послезавтра":
        day_offset = 2
        rest_start = 1

    if day_offset is not None:
        day = today + timedelta(days=day_offset)
        hh, mm = 9, 0
        if len(tokens) > rest_start:
            tpart = " ".join(tokens[rest_start:])
            tm = re.match(r"^(\d{1,2})[.:](\d{2})$", tpart)
            if tm:
                hh, mm = int(tm.group(1)), int(tm.group(2))
        return datetime.combine(day, time(hh, mm), tzinfo=tz)

    return None


def split_add_command(text: str) -> Tuple[str, Optional[str]]:
    """«Заголовок | срок» → заголовок и необязательный фрагмент срока."""
    if "|" not in text:
        return text.strip(), None
    title, due_raw = text.split("|", 1)
    title = title.strip()
    due_raw = due_raw.strip()
    return title, due_raw or None


def format_dt_local(dt: datetime, tz: ZoneInfo) -> str:
    local = dt.astimezone(tz)
    return local.strftime("%d.%m.%Y %H:%M")
