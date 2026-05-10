from __future__ import annotations

from datetime import datetime, timedelta, timezone

from telegram.ext import Application, ContextTypes, JobQueue

from bot.dates import format_dt_local
from bot.models import Task, TaskStatus
from bot.storage.sqlite_store import SqliteStorage


def remove_all_task_jobs(job_queue: JobQueue, task_id: int) -> None:
    """Удалить все jobs для задачи: дедлайн и напоминания заранее."""
    tid = str(task_id)
    targets = {
        f"due_{tid}",
        f"adv7_{tid}",
        f"adv1_{tid}",
        f"advh_{tid}",
        f"adv2h_{tid}",
        f"adv30m_{tid}",
    }
    for job in job_queue.jobs():
        if (job.name or "") in targets:
            job.schedule_removal()


def _job_name_due(task_id: int) -> str:
    return f"due_{task_id}"


def _job_name_adv(kind: str, task_id: int) -> str:
    return f"{kind}_{task_id}"


def format_time_left_ru(until_utc: datetime, now_utc: datetime) -> str:
    delta = until_utc - now_utc
    sec = max(0, int(delta.total_seconds()))
    if sec < 60:
        return "меньше минуты"
    days = sec // 86400
    sec -= days * 86400
    hours = sec // 3600
    sec -= hours * 3600
    mins = sec // 60
    parts: list[str] = []
    if days:
        parts.append(f"{days} дн.")
    if hours:
        parts.append(f"{hours} ч.")
    if mins and days == 0:
        parts.append(f"{mins} мин.")
    return " ".join(parts) if parts else "меньше минуты"


async def task_due_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: SqliteStorage = context.application.bot_data["storage"]
    tz_name: str = context.application.bot_data["tz_name"]
    task_id: int = context.job.data["task_id"]
    internal_user_id: int = context.job.data["internal_user_id"]
    chat_id: int = context.job.data["chat_id"]

    task = await storage.get_task(internal_user_id, task_id)
    if not task or task.status != TaskStatus.PENDING:
        return

    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    when = format_dt_local(task.due_at, tz) if task.due_at else ""
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"⏰ Дедлайн сейчас\n"
            f"№{task.id} · {task.title}\n"
            f"🕐 {when}\n\n"
            "Откройте «Задачи» → период → номер строки → «Готово»."
        ),
    )


async def task_advance_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: SqliteStorage = context.application.bot_data["storage"]
    tz_name: str = context.application.bot_data["tz_name"]
    task_id: int = context.job.data["task_id"]
    internal_user_id: int = context.job.data["internal_user_id"]
    chat_id: int = context.job.data["chat_id"]
    label: str = context.job.data["label"]

    task = await storage.get_task(internal_user_id, task_id)
    if not task or task.status != TaskStatus.PENDING or not task.due_at:
        return

    from zoneinfo import ZoneInfo

    tz = ZoneInfo(tz_name)
    now = datetime.now(timezone.utc)
    due = task.due_at
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    when = format_dt_local(due, tz)
    left = format_time_left_ru(due, now)
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🔔 Напоминание ({label})\n"
            f"№{task.id} · {task.title}\n"
            f"🕐 Дедлайн: {when}\n"
            f"⏳ Осталось: {left}"
        ),
    )


def schedule_task_reminders(
    application: Application,
    *,
    task: Task,
    chat_id: int,
    internal_user_id: int,
    schedule_deadline: bool = True,
) -> None:
    jq = application.job_queue
    if jq is None:
        return
    remove_all_task_jobs(jq, task.id)

    if not task.due_at:
        return

    due = task.due_at
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)

    data_base = {
        "task_id": task.id,
        "internal_user_id": internal_user_id,
        "chat_id": chat_id,
    }

    if schedule_deadline and due > now:
        jq.run_once(
            task_due_callback,
            when=due,
            chat_id=chat_id,
            name=_job_name_due(task.id),
            data={**data_base},
        )

    if task.remind_week:
        when = due - timedelta(days=7)
        if when > now:
            jq.run_once(
                task_advance_callback,
                when=when,
                chat_id=chat_id,
                name=_job_name_adv("adv7", task.id),
                data={**data_base, "label": "за неделю до срока"},
            )

    if task.remind_day:
        when = due - timedelta(days=1)
        if when > now:
            jq.run_once(
                task_advance_callback,
                when=when,
                chat_id=chat_id,
                name=_job_name_adv("adv1", task.id),
                data={**data_base, "label": "за день до срока"},
            )

    if task.remind_hour:
        when = due - timedelta(hours=1)
        if when > now:
            jq.run_once(
                task_advance_callback,
                when=when,
                chat_id=chat_id,
                name=_job_name_adv("advh", task.id),
                data={**data_base, "label": "за час до срока"},
            )

    if task.remind_2hours:
        when = due - timedelta(hours=2)
        if when > now:
            jq.run_once(
                task_advance_callback,
                when=when,
                chat_id=chat_id,
                name=_job_name_adv("adv2h", task.id),
                data={**data_base, "label": "за 2 часа до срока"},
            )

    if task.remind_30min:
        when = due - timedelta(minutes=30)
        if when > now:
            jq.run_once(
                task_advance_callback,
                when=when,
                chat_id=chat_id,
                name=_job_name_adv("adv30m", task.id),
                data={**data_base, "label": "за 30 минут до срока"},
            )


async def reschedule_all_reminders(application: Application) -> None:
    storage: SqliteStorage = application.bot_data["storage"]
    jq = application.job_queue
    if jq is None:
        return
    now = datetime.now(timezone.utc)
    pairs = await storage.list_schedulable_tasks_from(now)
    for task, telegram_uid in pairs:
        internal = await storage.ensure_user(telegram_uid)
        schedule_task_reminders(
            application,
            task=task,
            chat_id=telegram_uid,
            internal_user_id=internal,
            schedule_deadline=True,
        )


# Совместимость со старыми импортами
def remove_due_job(job_queue: JobQueue, task_id: int) -> None:
    remove_all_task_jobs(job_queue, task_id)


def schedule_task_due(
    application: Application,
    *,
    task: Task,
    chat_id: int,
    internal_user_id: int,
) -> None:
    schedule_task_reminders(
        application,
        task=task,
        chat_id=chat_id,
        internal_user_id=internal_user_id,
        schedule_deadline=True,
    )
