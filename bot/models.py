from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    PAUSED = "paused"
    DONE = "done"


@dataclass(frozen=True)
class Task:
    id: int
    internal_user_id: int
    title: str
    due_at: Optional[datetime]
    status: TaskStatus
    # Срочность: 0 = ⚪, 1 = 🟡, 2 = 🔴
    priority: int
    # Метка: study / work / life или None
    category: Optional[str]
    # Напоминания до дедлайна (1 = включено)
    remind_week: int
    remind_day: int
    remind_hour: int


@dataclass(frozen=True)
class TimeEntry:
    id: int
    internal_user_id: int
    task_id: Optional[int]
    started_at: datetime
    ended_at: Optional[datetime]
    note: Optional[str]
