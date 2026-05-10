from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Protocol

from bot.models import Task, TaskStatus, TimeEntry


class Storage(Protocol):
    """Контракт хранилища: позже можно подставить облако без смены хендлеров."""

    async def ensure_user(self, telegram_user_id: int) -> int: ...

    async def add_task(
        self,
        internal_user_id: int,
        title: str,
        due_at: Optional[datetime],
        priority: int,
        category: Optional[str] = None,
        remind_week: int = 0,
        remind_day: int = 0,
        remind_hour: int = 0,
    ) -> Task: ...

    async def get_task(self, internal_user_id: int, task_id: int) -> Optional[Task]: ...

    async def list_tasks_for_day(
        self, internal_user_id: int, day: date, include_done: bool
    ) -> list[Task]: ...

    async def list_pending_with_due(
        self, internal_user_id: int, from_dt: datetime, until_dt: datetime
    ) -> list[Task]: ...

    async def set_task_status(
        self, internal_user_id: int, task_id: int, status: TaskStatus
    ) -> bool: ...

    async def delete_task(self, internal_user_id: int, task_id: int) -> bool: ...

    async def list_inbox(self, internal_user_id: int, limit: int) -> list[Task]: ...

    async def list_all_active(self, internal_user_id: int, limit: int) -> list[Task]: ...

    async def start_time_entry(
        self, internal_user_id: int, task_id: Optional[int], note: Optional[str]
    ) -> TimeEntry: ...

    async def stop_open_time_entry(
        self, internal_user_id: int
    ) -> Optional[TimeEntry]: ...

    async def today_time_entries(
        self, internal_user_id: int, day: date
    ) -> list[TimeEntry]: ...
