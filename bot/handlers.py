from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import html

from telegram import Update
from telegram.ext import ContextTypes

from bot import keyboards as kb
from bot.chat_cleanup import (
    delete_tracked_bot_messages,
    peek_tracked_ids,
    purge_message_ids,
    remember_bot_message,
    send_panel,
    send_panel_html,
    try_delete_user_message,
)
from bot.dates import format_dt_local, parse_due_fragment, split_add_command
from bot.formatting import format_tasks_monospace_block
from bot.models import Task, TaskStatus
from bot.reminders import remove_all_task_jobs, schedule_task_reminders
from bot.storage.postgres_store import PostgresStorage

MODE = "ui_mode"
CREATE = "ui_create"
TASK_ORDER = "ui_task_order"
TASK_SCOPE = "ui_task_scope"
TASK_FILTER = "ui_task_filter"
SELECTED_TASK = "ui_selected_task"
TASK_PAGE = "ui_task_page"
TASKS_PER_PAGE = 15

FILTERS_FROM_BTN: Dict[str, str] = {
    kb.BTN_FIL_ALL: "all",
    kb.BTN_FIL_STUDY: "study",
    kb.BTN_FIL_WORK: "work",
    kb.BTN_FIL_LIFE: "life",
    kb.BTN_FIL_NONE: "none",
}

REMINDER_FROM_BTN: Dict[str, Tuple[int, int, int, int, float, bool]] = {
    kb.BTN_REM_WEEK: (1, 0, 0, 0, 0, True),
    kb.BTN_REM_DAY: (0, 1, 0, 0, 0, True),
    kb.BTN_REM_HOUR: (0, 0, 1, 0, 0, True),
    kb.BTN_REM_2HOURS: (0, 0, 0, 2, 0, True),
    kb.BTN_REM_30MIN: (0, 0, 0, 0, 0.5, True),
    kb.BTN_REM_DEADLINE: (0, 0, 0, 0, 0, True),
    kb.BTN_REM_OFF: (0, 0, 0, 0, 0, False),
}

def _storage(context: ContextTypes.DEFAULT_TYPE) -> PostgresStorage:
    return context.application.bot_data["storage"]

def _tz(context: ContextTypes.DEFAULT_TYPE) -> ZoneInfo:
    return ZoneInfo(context.application.bot_data["tz_name"])

def _set_mode(context: ContextTypes.DEFAULT_TYPE, mode: str) -> None:
    context.user_data[MODE] = mode

def _get_mode(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get(MODE, "main")

def _reset_flow(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in (MODE, CREATE, TASK_ORDER, TASK_SCOPE, TASK_FILTER, SELECTED_TASK):
        context.user_data.pop(key, None)

def apply_task_filter(tasks: List[Task], filt: Optional[str]) -> List[Task]:
    if not filt or filt == "all":
        return list(tasks)
    if filt == "none":
        return [t for t in tasks if not t.category]
    return [t for t in tasks if t.category == filt]

def _parse_index(text: str) -> Optional[int]:
    t = text.strip().rstrip(".").strip()
    return int(t) if t.isdigit() else None

def _urgency_word(level: int) -> str:
    if level >= 2:
        return "срочно"
    if level == 1:
        return "средняя"
    return "не срочно"

def _create_reply_kb(create: dict):
    step = create.get("step")
    if step == "cat":
        return kb.category_keyboard()
    if step == "due_type":
        return kb.create_due_keyboard()
    if step in ("day", "month", "time", "title"):
        return kb.date_step_keyboard()
    if step == "reminder":
        return kb.reminder_time_keyboard()
    if step == "urgency":
        return kb.create_urgency_keyboard()
    return kb.main_reply_keyboard()

def _valid_ymd(year: int, month: int, day: int) -> bool:
    try:
        datetime(year, month, day)
        return True
    except ValueError:
        return False

async def _tasks_for_scope(
    storage: PostgresStorage,
    uid: int,
    tz: ZoneInfo,
    scope: str,
) -> Tuple[List[Task], str]:
    if scope == "today":
        day = datetime.now(tz).date()
        tasks = await storage.list_tasks_for_day(uid, day, include_done=False)
        title = "Сегодня (по дедлайну)"
    elif scope == "tmrw":
        day = datetime.now(tz).date() + timedelta(days=1)
        tasks = await storage.list_tasks_for_day(uid, day, include_done=False)
        title = "Завтра (по дедлайну)"
    elif scope == "archive":
        tasks = await storage.list_done_tasks(uid, 80)
        title = "Готовые задачи"
    else:
        tasks = await storage.list_all_active(uid, 80)
        title = "Все активные"
    return tasks, title

async def _show_task_list(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    storage: PostgresStorage,
    uid: int,
    tz: ZoneInfo,
    scope: str,
) -> None:
    filt = context.user_data.get(TASK_FILTER) or "all"
    tasks, title = await _tasks_for_scope(storage, uid, tz, scope)
    tasks = apply_task_filter(tasks, filt)
    context.user_data[TASK_SCOPE] = scope

    if filt != "all":
        labels = {
            "study": " · метка «Учёба»",
            "work": " · метка «Работа»",
            "life": " · метка «Жизнь»",
            "none": " · без метки",
        }
        title += labels.get(filt, "")

    if not tasks:
        context.user_data.pop(TASK_ORDER, None)
        context.user_data.pop(TASK_PAGE, None)
        _set_mode(context, "tasks_scope")
        await send_panel(
            context,
            chat_id,
            f"{title}\n\nПока пусто.\nВыберите другой период, фильтр или «{kb.BTN_TO_MAIN}».",
            kb.tasks_scope_keyboard(),
        )
        return

    context.user_data[TASK_ORDER] = [t.id for t in tasks]
    context.user_data[TASK_PAGE] = 0
    _set_mode(context, "tasks_list")
    await _show_tasks_page(context, chat_id, storage, uid, tz, title, tasks)

async def _show_tasks_page(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    storage: PostgresStorage,
    uid: int,
    tz: ZoneInfo,
    title: str,
    tasks: List[Task],
) -> None:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    page = context.user_data.get(TASK_PAGE, 0)
    total = len(tasks)
    total_pages = (total + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE

    if page < 0:
        page = 0
        context.user_data[TASK_PAGE] = page
    elif page >= total_pages and total_pages > 0:
        page = total_pages - 1
        context.user_data[TASK_PAGE] = page

    start = page * TASKS_PER_PAGE
    end = min(start + TASKS_PER_PAGE, total)
    page_tasks = tasks[start:end]
    context.user_data[TASK_ORDER] = [t.id for t in tasks]

    footer_lines = [
        "",
        f"📄 Страница {page + 1} из {total_pages} · Всего задач: {total}",
        "👇 Нажмите на номер задачи, чтобы открыть"
    ]
    text = format_tasks_monospace_block(title, page_tasks, tz, footer_lines=footer_lines, start_index=start + 1)

    await send_panel_html(context, chat_id, text, reply_markup=kb.tasks_list_keyboard())

    buttons = []
    row = []
    for local_idx in range(1, len(page_tasks) + 1):
        global_number = start + local_idx
        row.append(InlineKeyboardButton(str(local_idx), callback_data=f"task_page_{page}_{local_idx}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Предыдущая", callback_data=f"task_prev_{page}"))
    if page + 1 < total_pages:
        nav_row.append(InlineKeyboardButton("Следующая ▶️", callback_data=f"task_next_{page}"))
    if nav_row:
        buttons.append(nav_row)
    
    inline_kb = InlineKeyboardMarkup(buttons)
    
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text="🔢 Выберите номер задачи:",
        reply_markup=inline_kb
    )
    remember_bot_message(context, msg.message_id)

async def _show_task_detail(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    storage: PostgresStorage,
    uid: int,
    tz: ZoneInfo,
    task_id: int,
) -> None:
    task = await storage.get_task(uid, task_id)
    if not task:
        await send_panel(
            context,
            chat_id,
            "Задача не найдена.",
            kb.tasks_list_keyboard(),
        )
        sc = context.user_data.get(TASK_SCOPE, "today")
        await _show_task_list(context, chat_id, storage, uid, tz, sc)
        return
    context.user_data[SELECTED_TASK] = task_id
    _set_mode(context, "task_detail")
    u = kb.urgency_emoji(task.priority)
    cat_line = ""
    if task.category:
        cat_line = f"🏷 Метка: {kb.category_human(task.category)}\n"
    
    due = ""
    remaining = ""
    if task.due_at:
        due = f"📅 Срок: {format_dt_local(task.due_at, tz)}"
        now = datetime.now(tz)
        due_local = task.due_at.astimezone(tz)
        
        if due_local > now:
            delta = due_local - now
            days = delta.days
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            
            if days > 0:
                remaining = f"⏳ Осталось: {days} дн. {hours} ч."
            elif hours > 0:
                remaining = f"⏳ Осталось: {hours} ч. {minutes} мин."
            elif minutes > 0:
                remaining = f"⏳ Осталось: {minutes} мин."
            else:
                remaining = "⏳ Осталось: меньше минуты"
        elif due_local <= now and task.status != TaskStatus.DONE:
            remaining = "⏰ Просрочено!"
    else:
        due = "📅 Без даты"
    
    if task.status == TaskStatus.PAUSED:
        st = "\n⏸ На паузе"
    elif task.status == TaskStatus.DONE:
        st = "\n✅ Готово"
    else:
        st = ""
    
    title_html = html.escape(task.title.replace("\n", " "))
    
    text = (
        f"📌 Задача №{task.id}\n\n"
        f"{cat_line}"
        f"{u} Срочность: {_urgency_word(task.priority)}\n\n"
        f"<b>{title_html}</b>\n\n"
        f"{due}\n"
        f"{remaining}{st}\n\n"
        "--- Действия ниже ---"
    )
    await send_panel_html(context, chat_id, text, kb.task_actions_keyboard(task))

def _scope_from_button(text: str) -> Optional[str]:
    if text == kb.BTN_TODAY:
        return "today"
    if text == kb.BTN_TOMORROW:
        return "tmrw"
    if text == kb.BTN_ALL:
        return "all"
    if text == kb.BTN_ARCHIVE:
        return "archive"
    return None

# --- Команды ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    await _storage(context).ensure_user(update.effective_user.id)
    old_ids = peek_tracked_ids(context.user_data)
    context.user_data.clear()
    await purge_message_ids(context.bot, chat_id, old_ids)
    text = (
        "👋 Привет! Я — ваш аккуратный список дел.\n\n"
        "✨ С чего начать:\n"
        "• 📝 Создать задачу — метка, дата по шагам (день → месяц → время), напоминания, текст.\n"
        "• 📋 Задачи — день, фильтр по метке, номер строки → действия.\n"
        "• 🎲 Случайная — если лень выбирать.\n\n"
        "📖 Вся инструкция с картинками-смайлами: /help\n"
        "💬 Автор и поддержка: @kanohka"
    )
    await send_panel(context, chat_id, text, kb.main_reply_keyboard())

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    chat_id = update.effective_chat.id
    _reset_flow(context)
    await send_panel(
        context,
        chat_id,
        "🙌 Отменено. Можно снова выбрать пункт меню.",
        kb.main_reply_keyboard(),
    )
    _set_mode(context, "main")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    chat_id = update.effective_chat.id
    text = (
        "📖 <b>Как пользоваться kanohka</b>\n\n"
        "📝 <b>Создать задачу</b>\n"
        "Сначала метка (или «Без метки»).\n"
        "Потом «Со сроком» → по очереди числами: <b>день</b>, <b>месяц</b>, <b>год</b> "
        "(например 10 → 5 → 2026).\n"
        "Выберите напоминания или «Только в момент срока» / «Не напоминать».\n"
        "Затем текст задачи и цвет срочности 🔴🟡⚪.\n\n"
        "📋 <b>Задачи</b>\n"
        "Сегодня / Завтра / Все → фильтр по метке → в чат только <b>номер строки</b>.\n\n"
        "🔔 <b>Напоминания</b>\n"
        "За неделю, за день, за час — или всё сразу; или только в дедлайн.\n\n"
        "🛠 Команды для продвинутых:\n"
        "/add текст | дата · /today · /inbox · /done № · /rm №\n"
        "/log_start · /log_stop · /log_today\n\n"
        "💬 Что-то сломалось? Напишите автору: @kanohka"
    )
    await delete_tracked_bot_messages(context, chat_id)
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=kb.main_reply_keyboard(),
        disable_web_page_preview=True,
    )
    remember_bot_message(context, msg.message_id)

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    storage = _storage(context)
    
    cur = await storage._db.execute("SELECT id FROM users WHERE telegram_user_id = ?", (user_id,))
    row = await cur.fetchone()
    
    if not row:
        await send_panel(context, chat_id, "❌ У тебя нет задач для удаления.", kb.main_reply_keyboard())
        return
    
    internal_uid = int(row[0])
    jq = context.application.job_queue
    if jq:
        cur = await storage._db.execute("SELECT id FROM tasks WHERE user_id = ?", (internal_uid,))
        rows = await cur.fetchall()
        for task_row in rows:
            remove_all_task_jobs(jq, int(task_row[0]))

    await storage._db.execute("DELETE FROM tasks WHERE user_id = ?", (internal_uid,))
    await storage._db.execute("DELETE FROM time_entries WHERE user_id = ?", (internal_uid,))
    await storage._db.commit()
    _reset_flow(context)
    _set_mode(context, "main")

    await send_panel(
        context,
        chat_id,
        "✅ Все твои задачи и таймеры удалены!",
        kb.main_reply_keyboard(),
    )

async def on_main_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user or not update.message:
        return
    text = (update.message.text or "").strip()
    
    # Редактирование задачи
    edit_step = context.user_data.get("edit_step")
    if edit_step and edit_step.startswith("waiting_"):
        edit_id = context.user_data.get("edit_task_id")
        edit_data = context.user_data.get("edit_task_data")
        edit_field = context.user_data.get("edit_field")
        
        if not edit_id or not edit_data:
            context.user_data.pop("edit_step", None)
            context.user_data.pop("edit_task_id", None)
            context.user_data.pop("edit_task_data", None)
            await update.message.reply_text("❌ Сессия редактирования истекла. Начните заново.")
            return
    
    # Сообщения из группы
    if update.effective_chat.type in ["group", "supergroup"]:
        is_reply_to_bot = (update.message.reply_to_message and update.message.reply_to_message.from_user and update.message.reply_to_message.from_user.is_bot)
        if not is_reply_to_bot and not text.startswith("/"):
            return
        umid = None
    else:
        umid = update.message.message_id
    
    chat_id = update.effective_chat.id
    storage = _storage(context)
    uid = await storage.ensure_user(update.effective_user.id)
    tz = _tz(context)
    mode = _get_mode(context)
    
    # Продолжение редактирования
    if edit_step and edit_step.startswith("waiting_"):
        edit_id = context.user_data.get("edit_task_id")
        
        if edit_step == "waiting_title":
            new_title = text.strip()
            if not new_title:
                await send_panel(context, chat_id, "📝 Текст не может быть пустым.", kb.date_step_keyboard())
                return
            await storage.update_task_field(uid, edit_id, "title", new_title)
            await send_panel(context, chat_id, f"✅ Текст задачи обновлён!", kb.main_reply_keyboard())
        
        elif edit_step == "waiting_due":
            if text.strip() == "/skip":
                await send_panel(context, chat_id, "⏩ Срок не изменён.", kb.main_reply_keyboard())
            else:
                try:
                    parts = text.strip().split()
                    if len(parts) == 4:
                        day, month, hour, minute = map(int, parts)
                        now = datetime.now(tz)
                        year = now.year
                        due_local = datetime(year, month, day, hour, minute, tzinfo=tz)
                        if due_local < now:
                            due_local = datetime(year + 1, month, day, hour, minute, tzinfo=tz)
                        await storage.update_task_field(uid, edit_id, "due_at", due_local)
                        await send_panel(context, chat_id, f"✅ Срок обновлён: {format_dt_local(due_local, tz)}", kb.main_reply_keyboard())
                    else:
                        await send_panel(context, chat_id, "❌ Неверный формат. Используйте: день месяц час минуты", kb.date_step_keyboard())
                        return
                except Exception as e:
                    await send_panel(context, chat_id, f"❌ Ошибка: {e}", kb.date_step_keyboard())
                    return
        
        context.user_data.pop("edit_step", None)
        context.user_data.pop("edit_task_id", None)
        context.user_data.pop("edit_task_data", None)
        context.user_data.pop("edit_field", None)
        await _show_task_detail(context, chat_id, storage, uid, tz, edit_id)
        return

    if text == kb.BTN_TO_MAIN:
        await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
        _reset_flow(context)
        _set_mode(context, "main")
        await send_panel(
            context,
            chat_id,
            "🏠 Главное меню — выберите действие.",
            kb.main_reply_keyboard(),
        )
        return

    create_block = context.user_data.get(CREATE)
    if create_block and text in (kb.BTN_CREATE, kb.BTN_TASKS, kb.BTN_RANDOM):
        await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
        await send_panel(
            context,
            chat_id,
            "Сначала закончите создание или нажмите «В меню».",
            _create_reply_kb(create_block),
        )
        return

    # Карточка задачи
    if mode == "task_detail":
        tid = context.user_data.get(SELECTED_TASK)
        if not isinstance(tid, int):
            _set_mode(context, "main")
            await send_panel(context, chat_id, "Сессия сброшена.", kb.main_reply_keyboard())
            return
        task = await storage.get_task(uid, tid)
        if not task:
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            sc = context.user_data.get(TASK_SCOPE, "today")
            await _show_task_list(context, chat_id, storage, uid, tz, sc)
            return

        if text == kb.BTN_TO_LIST:
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            sc = context.user_data.get(TASK_SCOPE, "today")
            await _show_task_list(context, chat_id, storage, uid, tz, sc)
            return

        if text == kb.BTN_DONE:
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            await storage.set_task_status(uid, tid, TaskStatus.DONE)
            jq = context.application.job_queue
            if jq:
                remove_all_task_jobs(jq, tid)
            sc = context.user_data.get(TASK_SCOPE, "today")
            await _show_task_list(context, chat_id, storage, uid, tz, sc)
            return

        if text == kb.BTN_DELETE:
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            jq = context.application.job_queue
            if jq:
                remove_all_task_jobs(jq, tid)
            await storage.delete_task(uid, tid)
            sc = context.user_data.get(TASK_SCOPE, "today")
            await _show_task_list(context, chat_id, storage, uid, tz, sc)
            return

        if text == kb.BTN_PAUSE and task.status != TaskStatus.PAUSED:
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            await storage.set_task_status(uid, tid, TaskStatus.PAUSED)
            jq = context.application.job_queue
            if jq:
                remove_all_task_jobs(jq, tid)
            await _show_task_detail(context, chat_id, storage, uid, tz, tid)
            return

        if text == kb.BTN_RESUME and task.status == TaskStatus.PAUSED:
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            await storage.set_task_status(uid, tid, TaskStatus.PENDING)
            t2 = await storage.get_task(uid, tid)
            if t2:
                schedule_task_reminders(context.application, task=t2, chat_id=chat_id, internal_user_id=uid, schedule_deadline=True)
            await _show_task_detail(context, chat_id, storage, uid, tz, tid)
            return

        await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
        await send_panel(context, chat_id, "Используйте кнопки ниже.", kb.task_actions_keyboard(task))
        return

    # Список задач
    if mode == "tasks_list":
        scope_btn = _scope_from_button(text)
        if scope_btn:
            await _show_task_list(context, chat_id, storage, uid, tz, scope_btn)
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            return
        
        if text == kb.BTN_FILTER:
            _set_mode(context, "tasks_filter")
            await send_panel(context, chat_id, "Выберите фильтр по метке.", kb.tasks_filter_keyboard())
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            return
        
        idx = _parse_index(text)
        order: List[int] = context.user_data.get(TASK_ORDER) or []
        
        if idx is not None and 1 <= idx <= len(order):
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            await _show_task_detail(context, chat_id, storage, uid, tz, order[idx - 1])
            return
        
        await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
        await send_panel(context, chat_id, f"Нужно число от 1 до {len(order)} или выберите кнопку.", kb.tasks_list_keyboard())
        return

    if mode == "tasks_filter":
        if text == kb.BTN_TO_MAIN:
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            _set_mode(context, "main")
            await send_panel(context, chat_id, "Выберите пункт меню.", kb.main_reply_keyboard())
            return
        if text in FILTERS_FROM_BTN:
            context.user_data[TASK_FILTER] = FILTERS_FROM_BTN[text]
            sc = context.user_data.get(TASK_SCOPE, "all")
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            await _show_task_list(context, chat_id, storage, uid, tz, sc)
            return
        await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
        await send_panel(context, chat_id, "Выберите фильтр кнопкой.", kb.tasks_filter_keyboard())
        return

    if mode == "tasks_scope":
        scope_btn = _scope_from_button(text)
        if scope_btn:
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            await _show_task_list(context, chat_id, storage, uid, tz, scope_btn)
            return
        await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
        await send_panel(context, chat_id, "Нажмите «Сегодня», «Завтра» или «Все даты».", kb.tasks_scope_keyboard())
        return

    # Создание задачи
    create = context.user_data.get(CREATE)
    if create:
        step = create.get("step")

        if step == "cat":
            if text not in kb.CAT_FROM_BTN:
                await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
                await send_panel(context, chat_id, "Выберите метку кнопкой или «Без метки».", kb.category_keyboard())
                return
            create["category"] = kb.CAT_FROM_BTN[text]
            create["step"] = "due_type"
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            await send_panel(context, chat_id, "Нужна конкретная дата у задачи?", kb.create_due_keyboard())
            return

        if step == "due_type":
            if text == kb.BTN_WITH_DUE:
                create["step"] = "day"
                await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
                await send_panel(context, chat_id, "Шаг 1 из 4 · День\nНапишите число от 1 до 31.", kb.date_step_keyboard())
                return
            if text == kb.BTN_NO_DUE:
                create["due_at"] = None
                create["schedule_deadline"] = False
                create["remind_week"] = 0
                create["remind_day"] = 0
                create["remind_hour"] = 0
                create["step"] = "title"
                await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
                await send_panel(context, chat_id, "Опишите задачу одним сообщением (что сделать).", kb.date_step_keyboard())
                return
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            await send_panel(context, chat_id, "Нажмите «Со сроком» или «Без срока».", kb.create_due_keyboard())
            return

        if step == "day":
            if not text.isdigit():
                await send_panel(context, chat_id, "Нужно целое число — день месяца (1–31).", kb.date_step_keyboard())
                return
            d = int(text)
            if not 1 <= d <= 31:
                await send_panel(context, chat_id, "День должен быть от 1 до 31.", kb.date_step_keyboard())
                return
            create["dd"] = d
            create["step"] = "month"
            await send_panel(context, chat_id, "Шаг 2 из 4 · Месяц\nНапишите номер месяца (1 = январь … 12 = декабрь).", kb.date_step_keyboard())
            return

        if step == "month":
            if not text.isdigit():
                await send_panel(context, chat_id, "Месяц — число от 1 до 12.", kb.date_step_keyboard())
                return
            m = int(text)
            if not 1 <= m <= 12:
                await send_panel(context, chat_id, "Месяц от 1 до 12.", kb.date_step_keyboard())
                return
            create["mm"] = m
            d = int(create["dd"])
            if not _valid_ymd(datetime.now(tz).year, m, d) and not (m == 2 and d == 29):
                await send_panel(context, chat_id, "Такой даты не бывает для этого месяца. Попробуйте другой день или месяц.", kb.date_step_keyboard())
                return
            create["step"] = "time"
            await send_panel(context, chat_id, "Шаг 3 из 4 · Время\nФорматы: «15 30», «1530» или «15» (часы: 0–23).", kb.date_step_keyboard())
            return

        if step == "time":
            time_str = text.strip()
            hh = mm = None
            
            if " " in time_str:
                parts = time_str.split()
                if len(parts) == 2 and all(p.isdigit() for p in parts):
                    hh, mm = int(parts[0]), int(parts[1])
            elif time_str.replace(":", "").isdigit():
                time_digits = time_str.replace(":", "")
                if len(time_digits) == 4:
                    hh, mm = int(time_digits[:2]), int(time_digits[2:])
                elif len(time_digits) == 2:
                    hh, mm = int(time_digits), 0
            elif time_str.isdigit():
                if len(time_str) <= 2:
                    hh, mm = int(time_str), 0
            
            if hh is None or mm is None or not (0 <= hh <= 23 and 0 <= mm <= 59):
                await send_panel(context, chat_id, "Введите время: «15 30», «1530» или «15». Часы 0–23, минуты 0–59.", kb.date_step_keyboard())
                return
            d = int(create["dd"])
            m = int(create["mm"])
            now = datetime.now(tz)
            y = now.year
            if not _valid_ymd(y, m, d):
                if m == 2 and d == 29:
                    while not _valid_ymd(y, m, d):
                        y += 1
                else:
                    await send_panel(context, chat_id, f"Такой даты не бывает ({d}.{m}). Начните снова с «Создать задачу».", kb.main_reply_keyboard())
                    context.user_data.pop(CREATE, None)
                    _set_mode(context, "main")
                    return
            due_local = datetime(y, m, d, hh, mm, tzinfo=tz)
            if due_local < now:
                y += 1
                while not _valid_ymd(y, m, d):
                    y += 1
                due_local = datetime(y, m, d, hh, mm, tzinfo=tz)
            create["due_at"] = due_local
            create["step"] = "reminder"
            await send_panel(context, chat_id, "Шаг 4 · Напоминания\nВыберите, когда напомнить о дедлайне.", kb.reminder_time_keyboard())
            return

        if step == "reminder":
            if text == kb.BTN_REM_BACK:
                create["step"] = "due"
                await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
                await send_panel(context, chat_id, "Шаг 3 · Дедлайн\nКогда дедлайн? Формат: 2024-12-31 23:59 или завтра 18:00", kb.date_step_keyboard())
                return
            if text not in REMINDER_FROM_BTN:
                await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
                await send_panel(context, chat_id, "Выберите вариант кнопкой.", kb.reminder_time_keyboard())
                return
            rw, rd, rh, r2h, r30m, sched = REMINDER_FROM_BTN[text]
            create["remind_week"] = rw
            create["remind_day"] = rd
            create["remind_hour"] = rh
            create["remind_2hours"] = r2h
            create["remind_30min"] = r30m
            create["schedule_deadline"] = sched
            create["step"] = "title"
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            await send_panel(context, chat_id, "Теперь текст задачи — одним сообщением, что именно сделать.", kb.date_step_keyboard())
            return

        if step == "title":
            title = text.strip()
            if not title:
                await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
                await send_panel(context, chat_id, "Текст не может быть пустым.", kb.date_step_keyboard())
                return
            create["title_text"] = title
            create["step"] = "urgency"
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            await send_panel(context, chat_id, "Насколько срочно?", kb.create_urgency_keyboard())
            return

        if step == "urgency":
            if text not in kb.URGENCY_BY_LABEL:
                await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
                await send_panel(context, chat_id, "Выберите 🔴 🟡 или ⚪.", kb.create_urgency_keyboard())
                return
            uval = kb.URGENCY_BY_LABEL[text]
            await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
            due_at = create.get("due_at")
            cat = create.get("category")
            rw = int(create.get("remind_week", 0))
            rd = int(create.get("remind_day", 0))
            rh = int(create.get("remind_hour", 0))
            r2h = int(create.get("remind_2hours", 0))
            r30m = int(create.get("remind_30min", 0))
            sched_dl = bool(create.get("schedule_deadline", True))

            task = await storage.add_task(
                uid,
                create["title_text"],
                due_at,
                uval,
                category=cat,
                remind_week=rw,
                remind_day=rd,
                remind_hour=rh,
                remind_2hours=r2h,
                remind_30min=r30m,
            )
            schedule_task_reminders(
                context.application,
                task=task,
                chat_id=chat_id,
                internal_user_id=uid,
                schedule_deadline=sched_dl and due_at is not None,
            )
            context.user_data.pop(CREATE, None)
            _set_mode(context, "main")
            due_s = f"\n📅 {format_dt_local(task.due_at, tz)}" if task.due_at else "\n📅 без даты"
            cat_s = f"\n🏷 {kb.category_human(cat)}" if cat else ""
            await send_panel(
                context,
                chat_id,
                f"✅ Задача №{task.id} сохранена{cat_s}{due_s}\n⚡ {_urgency_word(uval)}",
                kb.main_reply_keyboard(),
            )
            return

    # Старт (если ничего не подошло)
    await try_delete_user_message(context, chat_id, umid, update.effective_chat.type)
    await send_panel(context, chat_id, "Выберите кнопку меню или /help\nПоддержка: @kanohka", kb.main_reply_keyboard())
    _set_mode(context, "main")


# --- Обработчик inline-кнопок ---
async def handle_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.message:
        return

    await query.answer()

    data = query.data
    chat_id = query.message.chat.id
    storage = _storage(context)
    uid = query.from_user.id
    tz = _tz(context)
    internal_uid = await storage.ensure_user(uid)

    # --- Новые главные кнопки ---
    if data == "create_task":
        await query.message.delete()
        context.user_data[CREATE] = {"step": "cat"}
        _set_mode(context, "create_cat")
        await send_panel(context, chat_id, "🏷 Метка задачи — чтобы потом фильтровать списки.\nМожно пропустить.", kb.category_keyboard())
        return

    elif data == "show_tasks":
        await query.message.delete()
        context.user_data[TASK_FILTER] = "all"
        _set_mode(context, "tasks_scope")
        context.user_data.pop(TASK_ORDER, None)
        await send_panel(context, chat_id, "📆 За какой период показать задачи?", kb.tasks_scope_keyboard())
        return

    elif data == "random_task":
        await query.message.delete()
        day = datetime.now(tz).date()
        tasks = await storage.list_tasks_for_day(internal_uid, day, include_done=False)
        if not tasks:
            tasks = await storage.list_inbox(internal_uid, 60)
        if not tasks:
            tasks = await storage.list_all_active(internal_uid, 60)
        tasks = [t for t in tasks if t.status == TaskStatus.PENDING]
        if not tasks:
            await send_panel(context, chat_id, "Пока нечего делать — создайте задачу.", kb.main_reply_keyboard())
            return
        t = random.choice(tasks)
        line = f"{kb.urgency_emoji(t.priority)} {t.title}"
        await send_panel(context, chat_id, f"🎲 Попробуйте начать с этого:\n\n{line}\n\nЗакончите → «Задачи» → номер строки → «Готово».", kb.main_reply_keyboard())
        return

    # --- Обработка категорий (создание) ---
    elif data.startswith("cat_"):
        # Проверяем, не редактирование ли это
        if context.user_data.get("edit_step") == "waiting_category":
            edit_id = context.user_data.get("edit_task_id")
            if not edit_id:
                await query.answer("Сессия редактирования истекла.", show_alert=True)
                return
            cat_map = {"cat_study": "study", "cat_work": "work", "cat_life": "life", "cat_skip": None}
            if data not in cat_map:
                await query.answer("Некорректная категория.", show_alert=False)
                return
            await storage.update_task_field(internal_uid, edit_id, "category", cat_map[data])
            await query.message.delete()
            await send_panel(context, chat_id, "✅ Метка обновлена!", kb.main_reply_keyboard())
            context.user_data.pop("edit_step", None)
            context.user_data.pop("edit_task_id", None)
            context.user_data.pop("edit_task_data", None)
            await _show_task_detail(context, chat_id, storage, internal_uid, tz, edit_id)
            return
        
        # Создание задачи
        create = context.user_data.get(CREATE)
        if not create or create.get("step") != "cat":
            await query.answer("Некорректный шаг.", show_alert=False)
            return
        cat_map = {"cat_study": "study", "cat_work": "work", "cat_life": "life", "cat_skip": None}
        if data not in cat_map:
            await query.answer("Некорректная категория.", show_alert=False)
            return
        create["category"] = cat_map[data]
        create["step"] = "due_type"
        await query.message.edit_text("Нужна конкретная дата у задачи?", reply_markup=kb.create_due_keyboard())
        return

    # --- Обработка срочности (создание и редактирование) ---
    elif data.startswith("urg_"):
        # Редактирование
        if context.user_data.get("edit_step") == "waiting_priority":
            edit_id = context.user_data.get("edit_task_id")
            if not edit_id:
                await query.answer("Сессия редактирования истекла.", show_alert=True)
                return
            urg_map = {"urg_red": 2, "urg_yellow": 1, "urg_white": 0}
            if data not in urg_map:
                await query.answer("Некорректная срочность.", show_alert=False)
                return
            await storage.update_task_field(internal_uid, edit_id, "priority", urg_map[data])
            await query.message.delete()
            await send_panel(context, chat_id, "✅ Срочность обновлена!", kb.main_reply_keyboard())
            context.user_data.pop("edit_step", None)
            context.user_data.pop("edit_task_id", None)
            context.user_data.pop("edit_task_data", None)
            await _show_task_detail(context, chat_id, storage, internal_uid, tz, edit_id)
            return
        
        # Создание задачи
        create = context.user_data.get(CREATE)
        if not create or create.get("step") != "urgency":
            await query.answer("Некорректный шаг.", show_alert=False)
            return
        if "title_text" not in create:
            await query.answer("Сначала введите текст задачи.", show_alert=False)
            return
        urg_map = {"urg_red": 2, "urg_yellow": 1, "urg_white": 0}
        if data not in urg_map:
            await query.answer("Некорректная срочность.", show_alert=False)
            return
        uval = urg_map[data]
        await query.message.delete()
        due_at = create.get("due_at")
        cat = create.get("category")
        rw = int(create.get("remind_week", 0))
        rd = int(create.get("remind_day", 0))
        rh = int(create.get("remind_hour", 0))
        r2h = int(create.get("remind_2hours", 0))
        r30m = int(create.get("remind_30min", 0))
        sched_dl = bool(create.get("schedule_deadline", True))

        task = await storage.add_task(
            internal_uid, create["title_text"], due_at, uval, category=cat,
            remind_week=rw, remind_day=rd, remind_hour=rh, remind_2hours=r2h, remind_30min=r30m
        )
        schedule_task_reminders(
            context.application, task=task, chat_id=chat_id, internal_user_id=internal_uid,
            schedule_deadline=sched_dl and due_at is not None
        )
        context.user_data.pop(CREATE, None)
        _set_mode(context, "main")
        due = f"\n📅 {format_dt_local(task.due_at, tz)}" if task.due_at else ""
        st = "\n🟡 На паузе" if task.status == TaskStatus.PAUSED else ""
        cat_s = f"\n🏷 {kb.category_human(cat)}" if cat else ""
        await send_panel(context, chat_id, f"✅ Задача №{task.id} сохранена{cat_s}{due}{st}\n⚡ {_urgency_word(uval)}", kb.main_reply_keyboard())
        return

    # --- Обработка типа даты ---
    elif data in ("due_with", "due_without"):
        create = context.user_data.get(CREATE)
        if not create or create.get("step") != "due_type":
            await query.answer("Некорректный шаг.", show_alert=False)
            return
        if data == "due_with":
            create["step"] = "day"
            await query.message.edit_text("Шаг 1 из 4 · День\nНапишите число от 1 до 31.", reply_markup=kb.date_step_keyboard())
        else:
            create["due_at"] = None
            create["step"] = "title"
            create.pop("dd", None)
            create.pop("mm", None)
            create.pop("hour", None)
            create.pop("minute", None)
            await query.message.edit_text("Шаг 2 из 2 · Название задачи\nНапишите текст задачи.", reply_markup=kb.date_step_keyboard())
        return

    # --- Обработка scope выбора ---
    elif data.startswith("scope_"):
        scope_map = {"scope_today": "today", "scope_tomorrow": "tmrw", "scope_all": "all", "scope_archive": "archive"}
        if data not in scope_map:
            await query.answer("Некорректный scope.", show_alert=False)
            return
        scope = scope_map[data]
        await query.message.delete()
        await _show_task_list(context, chat_id, storage, internal_uid, tz, scope)
        return

    # --- Обработка фильтров ---
    elif data.startswith("filter_"):
        filter_map = {"filter_all": "all", "filter_study": "study", "filter_work": "work", "filter_life": "life", "filter_none": "none"}
        if data not in filter_map:
            await query.answer("Некорректный фильтр.", show_alert=False)
            return
        context.user_data[TASK_FILTER] = filter_map[data]
        sc = context.user_data.get(TASK_SCOPE, "all")
        await query.message.delete()
        await _show_task_list(context, chat_id, storage, internal_uid, tz, sc)
        return

    # --- Редактирование задачи ---
    elif data.startswith("task_edit_"):
        tid = int(data.split("_")[2])
        task = await storage.get_task(internal_uid, tid)
        if not task:
            await query.answer("Задача не найдена.", show_alert=True)
            return
        context.user_data["edit_task_id"] = tid
        context.user_data["edit_task_data"] = {
            "title": task.title, "due_at": task.due_at, "priority": task.priority,
            "category": task.category, "remind_week": task.remind_week,
            "remind_day": task.remind_day, "remind_hour": task.remind_hour,
            "remind_2hours": task.remind_2hours, "remind_30min": task.remind_30min,
        }
        context.user_data["edit_step"] = "what_to_edit"
        await query.message.delete()
        await send_panel(context, chat_id, "✏️ Что вы хотите редактировать?", kb.edit_what_keyboard())
        return

    # --- Обработка выбора поля для редактирования ---
    elif data.startswith("edit_"):
        edit_step = context.user_data.get("edit_step")
        edit_data = context.user_data.get("edit_task_data")
        edit_id = context.user_data.get("edit_task_id")
        if not edit_data or not edit_id:
            await query.answer("Сессия редактирования истекла.", show_alert=True)
            return
        if data == "edit_title":
            context.user_data["edit_field"] = "title"
            context.user_data["edit_step"] = "waiting_title"
            await query.message.edit_text("📝 Введите новый текст задачи:", reply_markup=kb.date_step_keyboard())
            return
        elif data == "edit_due":
            context.user_data["edit_field"] = "due"
            context.user_data["edit_step"] = "waiting_due"
            await query.message.edit_text("📅 Введите новую дату.\nФормат: день месяц час минуты\nНапример: 15 05 14 30", reply_markup=kb.date_step_keyboard())
            return
        elif data == "edit_priority":
            context.user_data["edit_step"] = "waiting_priority"
            await query.message.edit_text("🔴 Выберите новую срочность:", reply_markup=kb.create_urgency_keyboard())
            return
        elif data == "edit_category":
            context.user_data["edit_step"] = "waiting_category"
            await query.message.edit_text("🏷 Выберите новую метку:", reply_markup=kb.category_keyboard())
            return
        elif data == "edit_reminder":
            context.user_data["edit_step"] = "waiting_reminder"
            await query.message.edit_text("🔔 Выберите новые настройки напоминаний:", reply_markup=kb.reminder_time_keyboard())
            return
        elif data == "edit_back":
            context.user_data.pop("edit_task_id", None)
            context.user_data.pop("edit_task_data", None)
            context.user_data.pop("edit_step", None)
            context.user_data.pop("edit_field", None)
            await query.message.delete()
            await _show_task_detail(context, chat_id, storage, internal_uid, tz, edit_id)
            return

    # --- Обработка напоминаний (создание) ---
    elif data.startswith("rem_"):
        # Редактирование напоминаний
        if context.user_data.get("edit_step") == "waiting_reminder":
            edit_id = context.user_data.get("edit_task_id")
            if not edit_id:
                await query.answer("Сессия редактирования истекла.", show_alert=True)
                return
            rem_map = {
                "rem_week": (1, 0, 0, 0, 0, True), "rem_day": (0, 1, 0, 0, 0, True),
                "rem_hour": (0, 0, 1, 0, 0, True), "rem_2hours": (0, 0, 0, 2, 0, True),
                "rem_30min": (0, 0, 0, 0, 30, True), "rem_deadline": (0, 0, 0, 0, 0, True),
                "rem_off": (0, 0, 0, 0, 0, False),
            }
            if data == "rem_back":
                await query.message.edit_text("🔔 Выберите настройки напоминаний:", reply_markup=kb.reminder_time_keyboard())
                return
            if data not in rem_map:
                await query.answer("Некорректное напоминание.", show_alert=False)
                return
            rw, rd, rh, r2h, r30m, sched = rem_map[data]
            await storage.update_task_field(internal_uid, edit_id, "remind_week", rw)
            await storage.update_task_field(internal_uid, edit_id, "remind_day", rd)
            await storage.update_task_field(internal_uid, edit_id, "remind_hour", rh)
            await storage.update_task_field(internal_uid, edit_id, "remind_2hours", r2h)
            await storage.update_task_field(internal_uid, edit_id, "remind_30min", r30m)
            await query.message.delete()
            await send_panel(context, chat_id, "✅ Настройки напоминаний обновлены!", kb.main_reply_keyboard())
            context.user_data.pop("edit_step", None)
            context.user_data.pop("edit_task_id", None)
            context.user_data.pop("edit_task_data", None)
            await _show_task_detail(context, chat_id, storage, internal_uid, tz, edit_id)
            return
        
        # Создание задачи
        create = context.user_data.get(CREATE)
        if not create or create.get("step") != "reminder":
            await query.answer("Некорректный шаг.", show_alert=False)
            return
        rem_map = {
            "rem_week": (1, 0, 0, 0, 0, True), "rem_day": (0, 1, 0, 0, 0, True),
            "rem_hour": (0, 0, 1, 0, 0, True), "rem_2hours": (0, 0, 0, 2, 0, True),
            "rem_30min": (0, 0, 0, 0, 30, True), "rem_deadline": (0, 0, 0, 0, 0, True),
            "rem_off": (0, 0, 0, 0, 0, False),
        }
        if data == "rem_back":
            create["step"] = "due"
            await query.message.edit_text("Шаг 3 · Дедлайн\nКогда дедлайн? Формат: 2024-12-31 23:59 или завтра 18:00", reply_markup=kb.date_step_keyboard())
            return
        if data not in rem_map:
            await query.answer("Некорректное напоминание.", show_alert=False)
            return
        rw, rd, rh, r2h, r30m, sched = rem_map[data]
        create["remind_week"] = rw
        create["remind_day"] = rd
        create["remind_hour"] = rh
        create["remind_2hours"] = r2h
        create["remind_30min"] = r30m
        create["schedule_deadline"] = sched
        create["step"] = "title"
        await query.message.edit_text("Теперь текст задачи — одним сообщением, что именно сделать.", reply_markup=kb.date_step_keyboard())
        return

    # --- Обработка действий над задачей ---
    elif data.startswith("task_done_"):
        tid = int(data.split("_")[2])
        await query.message.delete()
        await storage.set_task_status(internal_uid, tid, TaskStatus.DONE)
        jq = context.application.job_queue
        if jq:
            remove_all_task_jobs(jq, tid)
        sc = context.user_data.get(TASK_SCOPE, "today")
        await _show_task_list(context, chat_id, storage, internal_uid, tz, sc)
        return

    elif data.startswith("task_delete_"):
        tid = int(data.split("_")[2])
        await query.message.delete()
        jq = context.application.job_queue
        if jq:
            remove_all_task_jobs(jq, tid)
        await storage.delete_task(internal_uid, tid)
        sc = context.user_data.get(TASK_SCOPE, "today")
        await _show_task_list(context, chat_id, storage, internal_uid, tz, sc)
        return

    elif data.startswith("task_pause_"):
        tid = int(data.split("_")[2])
        await query.message.delete()
        await storage.set_task_status(internal_uid, tid, TaskStatus.PAUSED)
        jq = context.application.job_queue
        if jq:
            remove_all_task_jobs(jq, tid)
        await _show_task_detail(context, chat_id, storage, internal_uid, tz, tid)
        return

    elif data.startswith("task_resume_"):
        tid = int(data.split("_")[2])
        await query.message.delete()
        await storage.set_task_status(internal_uid, tid, TaskStatus.PENDING)
        t2 = await storage.get_task(internal_uid, tid)
        if t2:
            schedule_task_reminders(context.application, task=t2, chat_id=chat_id, internal_user_id=internal_uid)
        await _show_task_detail(context, chat_id, storage, internal_uid, tz, tid)
        return

    elif data == "to_list":
        await query.message.delete()
        sc = context.user_data.get(TASK_SCOPE, "today")
        await _show_task_list(context, chat_id, storage, internal_uid, tz, sc)
        return

    # --- Пагинация ---
    elif data.startswith("task_page_"):
        parts = data.split("_")
        if len(parts) != 4:
            await query.answer("Некорректный выбор.", show_alert=False)
            return
        try:
            selected_idx = int(parts[3])
        except ValueError:
            await query.answer("Некорректный выбор.", show_alert=False)
            return
        all_tasks_ids = context.user_data.get(TASK_ORDER) or []
        global_idx = selected_idx - 1
        if 0 <= global_idx < len(all_tasks_ids):
            task_id = all_tasks_ids[global_idx]
            try:
                await query.message.delete()
            except Exception:
                pass
            await _show_task_detail(context, chat_id, storage, internal_uid, tz, task_id)
            return
        await query.answer("Список задач устарел, откройте его заново.", show_alert=False)
        return

    elif data.startswith("task_prev_"):
        old_page = int(data.split("_")[2])
        context.user_data[TASK_PAGE] = old_page - 1
        await query.message.delete()
        tasks, title = await _tasks_for_scope(storage, internal_uid, tz, context.user_data.get(TASK_SCOPE, "all"))
        filt = context.user_data.get(TASK_FILTER) or "all"
        tasks = apply_task_filter(tasks, filt)
        await _show_tasks_page(context, chat_id, storage, internal_uid, tz, title, tasks)
        return

    elif data.startswith("task_next_"):
        old_page = int(data.split("_")[2])
        context.user_data[TASK_PAGE] = old_page + 1
        await query.message.delete()
        tasks, title = await _tasks_for_scope(storage, internal_uid, tz, context.user_data.get(TASK_SCOPE, "all"))
        filt = context.user_data.get(TASK_FILTER) or "all"
        tasks = apply_task_filter(tasks, filt)
        await _show_tasks_page(context, chat_id, storage, internal_uid, tz, title, tasks)
        return

    elif data == "to_main":
        _reset_flow(context)
        _set_mode(context, "main")
        await query.message.delete()
        await send_panel(context, chat_id, "🏠 Главное меню", kb.main_reply_keyboard())
        return


# Остальные команды (cmd_add, cmd_today, cmd_inbox, cmd_done, cmd_rm, cmd_focus, cmd_log_start, cmd_log_stop, cmd_log_today) остаются без изменений

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    if not context.args:
        await send_panel(
            context,
            chat_id,
            "/add Текст | завтра 15:00\n! в начале = 🔴 срочно.",
            kb.main_reply_keyboard(),
        )
        return
    raw = " ".join(context.args)
    title, due_raw = split_add_command(raw)
    if not title:
        await send_panel(context, chat_id, "Нужен текст.", kb.main_reply_keyboard())
        return
    urgency = 0
    if title.startswith("!"):
        urgency = 2
        title = title[1:].strip()
    if not title:
        await send_panel(context, chat_id, "Пусто после !", kb.main_reply_keyboard())
        return

    tz = _tz(context)
    due = parse_due_fragment(due_raw, tz) if due_raw else None
    if due_raw and due is None:
        await send_panel(
            context,
            chat_id,
            "Дата не разобрана. Пример: завтра 15:30",
            kb.main_reply_keyboard(),
        )
        return

    storage = _storage(context)
    uid = await storage.ensure_user(update.effective_user.id)
    task = await storage.add_task(uid, title, due, urgency)
    schedule_task_reminders(
        context.application,
        task=task,
        chat_id=chat_id,
        internal_user_id=uid,
        schedule_deadline=due is not None,
    )
    due_s = f"\n📅 {format_dt_local(task.due_at, tz)}" if task.due_at else ""
    await send_panel(
        context,
        chat_id,
        f"✅ №{task.id}{due_s}\n⚡ {_urgency_word(urgency)}",
        kb.main_reply_keyboard(),
    )


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    storage = _storage(context)
    tz = _tz(context)
    uid = await storage.ensure_user(update.effective_user.id)
    day = datetime.now(tz).date()
    tasks = await storage.list_tasks_for_day(uid, day, include_done=False)
    if not tasks:
        await send_panel(context, chat_id, "На сегодня по дедлайну пусто.", kb.main_reply_keyboard())
        return
    footer = ["", "👉 номера строк для открытия в «Задачи»"]
    html = format_tasks_monospace_block("Сегодня", tasks, tz, footer_lines=footer)
    await send_panel_html(context, chat_id, html, kb.main_reply_keyboard())


async def cmd_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    storage = _storage(context)
    tz = _tz(context)
    uid = await storage.ensure_user(update.effective_user.id)
    tasks = await storage.list_inbox(uid, 40)
    if not tasks:
        await send_panel(context, chat_id, "Без даты задач нет.", kb.main_reply_keyboard())
        return
    footer = ["", "Без дедлайна — только здесь и во «Все»."]
    html = format_tasks_monospace_block("Без даты", tasks, tz, footer_lines=footer)
    await send_panel_html(context, chat_id, html, kb.main_reply_keyboard())


async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    if len(context.args) != 1 or not context.args[0].isdigit():
        await send_panel(context, chat_id, "Формат: /done 7", kb.main_reply_keyboard())
        return
    tid = int(context.args[0])
    storage = _storage(context)
    uid = await storage.ensure_user(update.effective_user.id)
    ok = await storage.set_task_status(uid, tid, TaskStatus.DONE)
    jq = context.application.job_queue
    if jq:
        remove_all_task_jobs(jq, tid)
    if ok:
        await send_panel(context, chat_id, f"✅ №{tid} готово!", kb.main_reply_keyboard())
    else:
        await send_panel(context, chat_id, "Не найдено.", kb.main_reply_keyboard())


async def cmd_rm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    if len(context.args) != 1 or not context.args[0].isdigit():
        await send_panel(context, chat_id, "Формат: /rm 7", kb.main_reply_keyboard())
        return
    tid = int(context.args[0])
    storage = _storage(context)
    uid = await storage.ensure_user(update.effective_user.id)
    jq = context.application.job_queue
    if jq:
        remove_all_task_jobs(jq, tid)
    ok = await storage.delete_task(uid, tid)
    if ok:
        await send_panel(context, chat_id, f"🗑 №{tid} удалена.", kb.main_reply_keyboard())
    else:
        await send_panel(context, chat_id, "Не найдено.", kb.main_reply_keyboard())


async def cmd_focus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    storage = _storage(context)
    tz = _tz(context)
    uid = await storage.ensure_user(update.effective_user.id)
    day = datetime.now(tz).date()
    tasks = await storage.list_tasks_for_day(uid, day, include_done=False)
    if not tasks:
        tasks = await storage.list_inbox(uid, 8)
    if not tasks:
        await send_panel(context, chat_id, "Список пуст.", kb.main_reply_keyboard())
        return
    t = tasks[0]
    await send_panel(
        context,
        chat_id,
        f"🎯 Следующий шаг:\n№{t.id} {t.title}",
        kb.main_reply_keyboard(),
    )


async def cmd_log_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    
    if not update.effective_message or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    storage = _storage(context)
    uid = await storage.ensure_user(update.effective_user.id)
    task_id: Optional[int] = None
    if context.args:
        if not context.args[0].isdigit():
            await send_panel(
                context, chat_id, "/log_start или /log_start 3", kb.main_reply_keyboard()
            )
            return
        task_id = int(context.args[0])
        if not await storage.get_task(uid, task_id):
            await send_panel(context, chat_id, "Нет такой задачи.", kb.main_reply_keyboard())
            return
    prev = await storage.stop_open_time_entry(uid)
    entry = await storage.start_time_entry(uid, task_id, None)
    parts: List[str] = []
    if prev:
        parts.append("Предыдущий интервал закрыт.")
    parts.append(f"⏱ Таймер №{entry.id}")
    if task_id:
        parts[-1] += f" · задача №{task_id}"
    parts.append("Стоп: /log_stop")
    await send_panel(context, chat_id, " ".join(parts), kb.main_reply_keyboard())


async def cmd_log_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    storage = _storage(context)
    uid = await storage.ensure_user(update.effective_user.id)
    entry = await storage.stop_open_time_entry(uid)
    if not entry:
        await send_panel(context, chat_id, "Нет таймера. /log_start", kb.main_reply_keyboard())
        return
    assert entry.ended_at is not None
    minutes = int((entry.ended_at - entry.started_at).total_seconds() // 60)
    await send_panel(
        context,
        chat_id,
        f"✅ Интервал №{entry.id} · ~{minutes} мин",
        kb.main_reply_keyboard(),
    )


async def cmd_log_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user:
        return
    chat_id = update.effective_chat.id
    storage = _storage(context)
    tz = _tz(context)
    uid = await storage.ensure_user(update.effective_user.id)
    day = datetime.now(tz).date()
    entries = await storage.today_time_entries(uid, day)
    if not entries:
        await send_panel(context, chat_id, "Записей нет.", kb.main_reply_keyboard())
        return
    total = 0
    lines: List[str] = []
    for e in entries:
        end = e.ended_at or datetime.now(timezone.utc)
        sec = (end - e.started_at).total_seconds()
        if e.ended_at:
            total += int(sec)
        m = int(sec // 60)
        tail = f"№{e.task_id}" if e.task_id else "—"
        lines.append(f"№{e.id} · {m} мин · {tail}")
    await send_panel(
        context,
        chat_id,
        "📊 Лог:\n" + "\n".join(lines) + f"\n\nВсего ~{total // 60} мин",
        kb.main_reply_keyboard(),
    )
