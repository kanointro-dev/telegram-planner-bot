from __future__ import annotations

import aiosqlite
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from bot.models import Task, TaskStatus, TimeEntry


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_utc_iso(s: str) -> datetime:
    return datetime.fromisoformat(s).astimezone(timezone.utc)


class SqliteStorage:
    def __init__(self, db_path: Path, tz_name: str) -> None:
        self._path = db_path
        self._tz = ZoneInfo(tz_name)

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            CREATE INDEX IF NOT EXISTS idx_tasks_user_due
                ON tasks(user_id, due_at);
            CREATE TABLE IF NOT EXISTS time_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                note TEXT
            );
            """
        )
        await self._db.commit()
        await self._migrate_columns_and_version()

    async def _migrate_columns_and_version(self) -> None:
        cur = await self._db.execute("PRAGMA table_info(tasks)")
        rows = await cur.fetchall()
        names = {r[1] for r in rows}
        if "category" not in names:
            await self._db.execute("ALTER TABLE tasks ADD COLUMN category TEXT")
        if "remind_week" not in names:
            await self._db.execute(
                "ALTER TABLE tasks ADD COLUMN remind_week INTEGER NOT NULL DEFAULT 0"
            )
        if "remind_day" not in names:
            await self._db.execute(
                "ALTER TABLE tasks ADD COLUMN remind_day INTEGER NOT NULL DEFAULT 0"
            )
        if "remind_hour" not in names:
            await self._db.execute(
                "ALTER TABLE tasks ADD COLUMN remind_hour INTEGER NOT NULL DEFAULT 0"
            )
        await self._db.commit()

        cur = await self._db.execute("PRAGMA user_version")
        row = await cur.fetchone()
        uv = int(row[0]) if row else 0
        if uv < 1:
            await self._db.execute(
                "UPDATE tasks SET priority = 2 WHERE priority >= 1"
            )
            await self._db.execute("PRAGMA user_version = 1")
            await self._db.commit()
            uv = 1
        if uv < 2:
            await self._db.execute("PRAGMA user_version = 2")
            await self._db.commit()

    async def close(self) -> None:
        await self._db.close()

    async def ensure_user(self, telegram_user_id: int) -> int:
        cur = await self._db.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?", (telegram_user_id,)
        )
        row = await cur.fetchone()
        if row:
            return int(row["id"])
        cur = await self._db.execute(
            "INSERT INTO users (telegram_user_id) VALUES (?)", (telegram_user_id,)
        )
        await self._db.commit()
        return int(cur.lastrowid)

    def _row_to_task(self, row: aiosqlite.Row) -> Task:
        due = _parse_utc_iso(row["due_at"]) if row["due_at"] else None
        keys = row.keys()
        cat = row["category"] if "category" in keys and row["category"] else None
        rw = int(row["remind_week"]) if "remind_week" in keys else 0
        rd = int(row["remind_day"]) if "remind_day" in keys else 0
        rh = int(row["remind_hour"]) if "remind_hour" in keys else 0
        r2h = int(row["remind_2hours"]) if "remind_2hours" in keys else 0
        r30m = int(row["remind_30min"]) if "remind_30min" in keys else 0
        return Task(
            id=int(row["id"]),
            internal_user_id=int(row["user_id"]),
            title=str(row["title"]),
            due_at=due,
            status=TaskStatus(row["status"]),
            priority=int(row["priority"]),
            category=cat if cat else None,
            remind_week=rw,
            remind_day=rd,
            remind_hour=rh,
            remind_2hours=r2h,
            remind_30min=r30m,
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
        priority = min(2, max(0, int(priority)))
        due_s = _utc_iso(due_at) if due_at else None
        created = _utc_iso(datetime.now(timezone.utc))
        cur = await self._db.execute(
            """
            INSERT INTO tasks (
                user_id, title, due_at, priority, created_at,
                category, remind_week, remind_day, remind_hour, remind_2hours, remind_30min
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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
            ),
        )
        await self._db.commit()
        tid = int(cur.lastrowid)
        task = await self.get_task(internal_user_id, tid)
        assert task is not None
        return task

    async def get_task(self, internal_user_id: int, task_id: int) -> Optional[Task]:
        cur = await self._db.execute(
            """
            SELECT * FROM tasks WHERE id = ? AND user_id = ?
            """,
            (task_id, internal_user_id),
        )
        row = await cur.fetchone()
        return self._row_to_task(row) if row else None

    async def list_tasks_for_day(
        self, internal_user_id: int, day: date, include_done: bool
    ) -> List[Task]:
        """Только задачи с дедлайном в этот календарный день (без «бессрочных»)."""
        start_local = datetime.combine(day, time.min, tzinfo=self._tz)
        end_local = start_local + timedelta(days=1)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)
        su, eu = _utc_iso(start_utc), _utc_iso(end_utc)
        status_sql = "" if include_done else "AND t.status = 'pending'"
        cur = await self._db.execute(
            f"""
            SELECT t.* FROM tasks t
            WHERE t.user_id = ?
            {status_sql}
            AND t.due_at IS NOT NULL
            AND t.due_at >= ? AND t.due_at < ?
            ORDER BY t.due_at ASC, t.priority DESC, t.id
            """,
            (internal_user_id, su, eu),
        )
        rows = await cur.fetchall()
        return [self._row_to_task(r) for r in rows]

    async def due_reminders_from(
        self, from_utc: datetime
    ) -> List[Tuple[int, int, datetime]]:
        cur = await self._db.execute(
            """
            SELECT t.id, u.telegram_user_id, t.due_at
            FROM tasks t
            JOIN users u ON u.id = t.user_id
            WHERE t.status = 'pending'
              AND t.due_at IS NOT NULL
              AND t.due_at >= ?
            ORDER BY t.due_at
            """,
            (_utc_iso(from_utc),),
        )
        rows = await cur.fetchall()
        out: List[Tuple[int, int, datetime]] = []
        for r in rows:
            out.append((int(r["id"]), int(r["telegram_user_id"]), _parse_utc_iso(r["due_at"])))
        return out

    async def list_pending_with_due(
        self, internal_user_id: int, from_dt: datetime, until_dt: datetime
    ) -> List[Task]:
        cur = await self._db.execute(
            """
            SELECT * FROM tasks
            WHERE user_id = ? AND status = 'pending'
              AND due_at IS NOT NULL
              AND due_at >= ? AND due_at < ?
            ORDER BY due_at
            """,
            (internal_user_id, _utc_iso(from_dt), _utc_iso(until_dt)),
        )
        rows = await cur.fetchall()
        return [self._row_to_task(r) for r in rows]

    async def set_task_status(
        self, internal_user_id: int, task_id: int, status: TaskStatus
    ) -> bool:
        cur = await self._db.execute(
            """
            UPDATE tasks SET status = ?
            WHERE id = ? AND user_id = ?
            """,
            (status.value, task_id, internal_user_id),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def delete_task(self, internal_user_id: int, task_id: int) -> bool:
        cur = await self._db.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, internal_user_id),
        )
        await self._db.commit()
        return cur.rowcount > 0

    async def list_inbox(self, internal_user_id: int, limit: int) -> List[Task]:
        cur = await self._db.execute(
            """
            SELECT * FROM tasks
            WHERE user_id = ? AND status = 'pending' AND due_at IS NULL
            ORDER BY priority DESC, id DESC
            LIMIT ?
            """,
            (internal_user_id, limit),
        )
        rows = await cur.fetchall()
        return [self._row_to_task(r) for r in rows]

    async def list_all_active(self, internal_user_id: int, limit: int) -> List[Task]:
        cur = await self._db.execute(
            """
            SELECT * FROM tasks
            WHERE user_id = ? AND status IN ('pending', 'paused')
            ORDER BY (due_at IS NULL), due_at ASC, priority DESC, id
            LIMIT ?
            """,
            (internal_user_id, limit),
        )
        rows = await cur.fetchall()
        return [self._row_to_task(r) for r in rows]

    async def list_done_tasks(self, internal_user_id: int, limit: int) -> List[Task]:
        cur = await self._db.execute(
            """
            SELECT * FROM tasks
            WHERE user_id = ? AND status = 'done'
            ORDER BY (due_at IS NULL), due_at ASC, priority DESC, id
            LIMIT ?
            """,
            (internal_user_id, limit),
        )
        rows = await cur.fetchall()
        return [self._row_to_task(r) for r in rows]

    async def list_schedulable_tasks_from(
        self, from_utc: datetime
    ) -> List[Tuple[Task, int]]:
        """Задачи с дедлайном в будущем для восстановления напоминаний."""
        cur = await self._db.execute(
            """
            SELECT t.*, u.telegram_user_id AS telegram_user_id
            FROM tasks t
            JOIN users u ON u.id = t.user_id
            WHERE t.status = 'pending'
              AND t.due_at IS NOT NULL
              AND t.due_at >= ?
            """,
            (_utc_iso(from_utc),),
        )
        rows = await cur.fetchall()
        out: List[Tuple[Task, int]] = []
        for r in rows:
            tg = int(r["telegram_user_id"])
            out.append((self._row_to_task(r), tg))
        return out

    async def start_time_entry(
        self, internal_user_id: int, task_id: Optional[int], note: Optional[str]
    ) -> TimeEntry:
        now = _utc_iso(datetime.now(timezone.utc))
        cur = await self._db.execute(
            """
            INSERT INTO time_entries (user_id, task_id, started_at, note)
            VALUES (?, ?, ?, ?)
            """,
            (internal_user_id, task_id, now, note),
        )
        await self._db.commit()
        eid = int(cur.lastrowid)
        row = await (
            await self._db.execute("SELECT * FROM time_entries WHERE id = ?", (eid,))
        ).fetchone()
        return self._row_to_entry(row)

    async def stop_open_time_entry(self, internal_user_id: int) -> Optional[TimeEntry]:
        cur = await self._db.execute(
            """
            SELECT * FROM time_entries
            WHERE user_id = ? AND ended_at IS NULL
            ORDER BY id DESC LIMIT 1
            """,
            (internal_user_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        now = _utc_iso(datetime.now(timezone.utc))
        await self._db.execute(
            "UPDATE time_entries SET ended_at = ? WHERE id = ?",
            (now, int(row["id"])),
        )
        await self._db.commit()
        row = await (
            await self._db.execute(
                "SELECT * FROM time_entries WHERE id = ?", (int(row["id"]),)
            )
        ).fetchone()
        return self._row_to_entry(row)

    def _row_to_entry(self, row: aiosqlite.Row) -> TimeEntry:
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
        start_local = datetime.combine(day, time.min, tzinfo=self._tz)
        end_local = start_local + timedelta(days=1)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)
        cur = await self._db.execute(
            """
            SELECT * FROM time_entries
            WHERE user_id = ?
              AND started_at >= ? AND started_at < ?
            ORDER BY started_at
            """,
            (internal_user_id, _utc_iso(start_utc), _utc_iso(end_utc)),
        )
        rows = await cur.fetchall()
        return [self._row_to_entry(r) for r in rows]