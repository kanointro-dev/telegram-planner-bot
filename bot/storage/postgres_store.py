from __future__ import annotations

import asyncpg
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from bot.models import Task, TaskStatus, TimeEntry


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_utc_iso(s: str) -> datetime:
    return datetime.fromisoformat(s).astimezone(timezone.utc)


class PostgresStorage:
    def __init__(self, database_url: str, tz_name: str) -> None:
        self._url = database_url
        self._tz = ZoneInfo(tz_name)
        self._pool: Optional[asyncpg.Pool] = None

    async def get_user_timezone(self, telegram_user_id: int) -> str:
        """Получить часовой пояс пользователя."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT timezone FROM users WHERE telegram_user_id = $1",
                telegram_user_id
            )
            if row and row["timezone"]:
                return row["timezone"]
            return "Europe/Moscow"

    async def set_user_timezone(self, telegram_user_id: int, timezone: str) -> None:
        """Установить часовой пояс пользователя."""
        async with self._pool.acquire() as conn:
            internal = await self.ensure_user(telegram_user_id)
            await conn.execute(
                "UPDATE users SET timezone = $1 WHERE id = $2",
                timezone, internal
            )

async def set_user_timezone(self, telegram_user_id: int, timezone: str) -> None:
    """Установить часовой пояс пользователя."""
    async with self._pool.acquire() as conn:
        internal = await self.ensure_user(telegram_user_id)
        await conn.execute(
            "UPDATE users SET timezone = $1 WHERE id = $2",
            timezone, internal
        )

    async def connect(self) -> None:
     """Create connection pool and initialize schema."""
    print("DEBUG: Connecting to PostgreSQL...", flush=True)
    try:
        self._pool = await asyncpg.create_pool(self._url, min_size=1, max_size=10)
        await self._create_tables()
        await self._migrate_add_timezone()
    except Exception as e:
        print(f"FATAL: {e}", flush=True)
        raise

async def _migrate_add_timezone(self) -> None:
    """Добавить колонку timezone в таблицу users, если её нет."""
    async with self._pool.acquire() as conn:
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN timezone TEXT DEFAULT 'Europe/Moscow'")
            print("DEBUG: Added timezone column to users table", flush=True)
        except Exception as e:
            # Колонка уже существует — игнорируем ошибку
            print(f"DEBUG: timezone column already exists or error: {e}", flush=True)
                
        

        

    async def close(self) -> None:
        """Close all connections in the pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def _create_tables(self) -> None:
        """Create all necessary tables if they don't exist."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL UNIQUE,
    timezone TEXT DEFAULT 'Europe/Moscow'
);
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    due_at TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    category TEXT,
                    remind_week INTEGER NOT NULL DEFAULT 0,
                    remind_day INTEGER NOT NULL DEFAULT 0,
                    remind_hour INTEGER NOT NULL DEFAULT 0,
                    remind_2hours INTEGER NOT NULL DEFAULT 0,
                    remind_30min INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tasks_user_due
                    ON tasks(user_id, due_at);
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS time_entries (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    note TEXT
                );
                """
            )

    async def ensure_user(self, telegram_user_id: int) -> int:
        """Get or create user, return internal user ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM users WHERE telegram_user_id = $1", telegram_user_id
            )
            if row:
                return int(row["id"])
            row = await conn.fetchrow(
                "INSERT INTO users (telegram_user_id) VALUES ($1) RETURNING id",
                telegram_user_id,
            )
            return int(row["id"])

    def _row_to_task(self, row: asyncpg.Record) -> Task:
        """Convert database row to Task object."""
        due = _parse_utc_iso(row["due_at"]) if row["due_at"] else None
        return Task(
            id=int(row["id"]),
            internal_user_id=int(row["user_id"]),
            title=str(row["title"]),
            due_at=due,
            status=TaskStatus(row["status"]),
            priority=int(row["priority"]),
            category=row["category"],
            remind_week=int(row["remind_week"]),
            remind_day=int(row["remind_day"]),
            remind_hour=int(row["remind_hour"]),
            remind_2hours=int(row["remind_2hours"]),
            remind_30min=int(row["remind_30min"]),
        )

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
        remind_2hours: int = 0,
        remind_30min: int = 0,
    ) -> Task:
        """Create a new task."""
        priority = min(2, max(0, int(priority)))
        due_s = _utc_iso(due_at) if due_at else None
        created = _utc_iso(datetime.now(timezone.utc))

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO tasks (
                    user_id, title, due_at, priority, created_at,
                    category, remind_week, remind_day, remind_hour, remind_2hours, remind_30min
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING id
                """,
                internal_user_id,
                title.strip(),
                due_s,
                priority,
                created,
                category,
                int(bool(remind_week)),
                int(bool(remind_day)),
                int(bool(remind_hour)),
                int(bool(remind_2hours)),
                int(bool(remind_30min)),
            )
            task_id = int(row["id"])
        task = await self.get_task(internal_user_id, task_id)
        assert task is not None
        return task

    async def get_task(self, internal_user_id: int, task_id: int) -> Optional[Task]:
        """Get a single task by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM tasks WHERE id = $1 AND user_id = $2",
                task_id,
                internal_user_id,
            )
            return self._row_to_task(row) if row else None

    async def list_tasks_for_day(
        self, internal_user_id: int, day: date, include_done: bool
    ) -> List[Task]:
        """List tasks due on a specific calendar day."""
        start_local = datetime.combine(day, time.min, tzinfo=self._tz)
        end_local = start_local + timedelta(days=1)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)
        su, eu = _utc_iso(start_utc), _utc_iso(end_utc)

        status_clause = (
            ""
            if include_done
            else "AND t.status = 'pending'"
        )

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT t.* FROM tasks t
                WHERE t.user_id = $1
                {status_clause}
                AND t.due_at IS NOT NULL
                AND t.due_at >= $2 AND t.due_at < $3
                ORDER BY t.due_at ASC, t.priority DESC, t.id
                """,
                internal_user_id,
                su,
                eu,
            )
            return [self._row_to_task(r) for r in rows]

    async def due_reminders_from(
        self, from_utc: datetime
    ) -> List[Tuple[int, int, datetime]]:
        """Get all pending tasks with due dates >= from_utc."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT t.id, u.telegram_user_id, t.due_at
                FROM tasks t
                JOIN users u ON u.id = t.user_id
                WHERE t.status = 'pending'
                  AND t.due_at IS NOT NULL
                  AND t.due_at >= $1
                ORDER BY t.due_at
                """,
                _utc_iso(from_utc),
            )
            out: List[Tuple[int, int, datetime]] = []
            for r in rows:
                out.append(
                    (int(r["id"]), int(r["telegram_user_id"]), _parse_utc_iso(r["due_at"]))
                )
            return out

    async def list_pending_with_due(
        self, internal_user_id: int, from_dt: datetime, until_dt: datetime
    ) -> List[Task]:
        """List pending tasks with due dates in the given range."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM tasks
                WHERE user_id = $1 AND status = 'pending'
                  AND due_at IS NOT NULL
                  AND due_at >= $2 AND due_at < $3
                ORDER BY due_at
                """,
                internal_user_id,
                _utc_iso(from_dt),
                _utc_iso(until_dt),
            )
            return [self._row_to_task(r) for r in rows]

    async def set_task_status(
        self, internal_user_id: int, task_id: int, status: TaskStatus
    ) -> bool:
        """Update task status."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE tasks SET status = $1
                WHERE id = $2 AND user_id = $3
                """,
                status.value,
                task_id,
                internal_user_id,
            )
            return result != "UPDATE 0"

    async def delete_task(self, internal_user_id: int, task_id: int) -> bool:
        """Delete a task."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM tasks WHERE id = $1 AND user_id = $2",
                task_id,
                internal_user_id,
            )
            return result != "DELETE 0"

    async def list_inbox(self, internal_user_id: int, limit: int) -> List[Task]:
        """List tasks without due dates (inbox)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM tasks
                WHERE user_id = $1 AND status = 'pending' AND due_at IS NULL
                ORDER BY priority DESC, id DESC
                LIMIT $2
                """,
                internal_user_id,
                limit,
            )
            return [self._row_to_task(r) for r in rows]

    async def list_all_active(self, internal_user_id: int, limit: int) -> List[Task]:
        """List all active (pending or paused) tasks."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM tasks
                WHERE user_id = $1 AND status IN ('pending', 'paused')
                ORDER BY (due_at IS NULL), due_at ASC, priority DESC, id
                LIMIT $2
                """,
                internal_user_id,
                limit,
            )
            return [self._row_to_task(r) for r in rows]

    async def list_done_tasks(self, internal_user_id: int, limit: int) -> List[Task]:
        """List completed tasks."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM tasks
                WHERE user_id = $1 AND status = 'done'
                ORDER BY (due_at IS NULL), due_at ASC, priority DESC, id
                LIMIT $2
                """,
                internal_user_id,
                limit,
            )
            return [self._row_to_task(r) for r in rows]

    async def list_schedulable_tasks_from(
        self, from_utc: datetime
    ) -> List[Tuple[Task, int]]:
        """Get pending tasks with due dates >= from_utc for reminder recovery."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT t.*, u.telegram_user_id
                FROM tasks t
                JOIN users u ON u.id = t.user_id
                WHERE t.status = 'pending'
                  AND t.due_at IS NOT NULL
                  AND t.due_at >= $1
                """,
                _utc_iso(from_utc),
            )
            out: List[Tuple[Task, int]] = []
            for r in rows:
                tg = int(r["telegram_user_id"])
                out.append((self._row_to_task(r), tg))
            return out

    async def start_time_entry(
        self, internal_user_id: int, task_id: Optional[int], note: Optional[str]
    ) -> TimeEntry:
        """Start a new time entry."""
        now = _utc_iso(datetime.now(timezone.utc))
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO time_entries (user_id, task_id, started_at, note)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                internal_user_id,
                task_id,
                now,
                note,
            )
            entry_id = int(row["id"])
            row = await conn.fetchrow(
                "SELECT * FROM time_entries WHERE id = $1", entry_id
            )
            return self._row_to_entry(row)

    async def stop_open_time_entry(self, internal_user_id: int) -> Optional[TimeEntry]:
        """Stop the most recent open time entry."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM time_entries
                WHERE user_id = $1 AND ended_at IS NULL
                ORDER BY id DESC LIMIT 1
                """,
                internal_user_id,
            )
            if not row:
                return None
            now = _utc_iso(datetime.now(timezone.utc))
            await conn.execute(
                "UPDATE time_entries SET ended_at = $1 WHERE id = $2",
                now,
                int(row["id"]),
            )
            row = await conn.fetchrow(
                "SELECT * FROM time_entries WHERE id = $1", int(row["id"])
            )
            return self._row_to_entry(row)

    def _row_to_entry(self, row: asyncpg.Record) -> TimeEntry:
        """Convert database row to TimeEntry object."""
        return TimeEntry(
            id=int(row["id"]),
            internal_user_id=int(row["user_id"]),
            task_id=int(row["task_id"]) if row["task_id"] is not None else None,
            started_at=_parse_utc_iso(row["started_at"]),
            ended_at=_parse_utc_iso(row["ended_at"]) if row["ended_at"] else None,
            note=str(row["note"]) if row["note"] is not None else None,
        )

    async def today_time_entries(
        self, internal_user_id: int, day: date
    ) -> List[TimeEntry]:
        """Get all time entries for a specific calendar day."""
        start_local = datetime.combine(day, time.min, tzinfo=self._tz)
        end_local = start_local + timedelta(days=1)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM time_entries
                WHERE user_id = $1
                  AND started_at >= $2 AND started_at < $3
                ORDER BY started_at
                """,
                internal_user_id,
                _utc_iso(start_utc),
                _utc_iso(end_utc),
            )
            return [self._row_to_entry(r) for r in rows]
        
    async def update_task_field(self, internal_user_id: int, task_id: int, field: str, value) -> bool:
        """Обновить одно поле задачи."""
        allowed_fields = ["title", "priority", "category", "due_at", "remind_week", "remind_day", "remind_hour", "remind_2hours", "remind_30min"]
        if field not in allowed_fields:
            return False
        
        async with self._pool.acquire() as conn:
            # Для due_at нужно преобразовать в строку
            if field == "due_at" and value is not None:
                value = _utc_iso(value)
            result = await conn.execute(
                f"UPDATE tasks SET {field} = $1 WHERE id = $2 AND user_id = $3",
                value, task_id, internal_user_id
            )
            return result != "UPDATE 0"