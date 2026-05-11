from __future__ import annotations

from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.models import Task, TaskStatus

# —— Главное меню ——
BTN_CREATE = "➕ Создать задачу"
BTN_TASKS = "📋 Задачи"
BTN_RANDOM = "🎲 Случайная"  # Не используется, оставлено для совместимости

# —— Метка (заголовок) ——
BTN_CAT_STUDY = "📚 Учёба"
BTN_CAT_WORK = "💼 Работа"
BTN_CAT_LIFE = "🏠 Жизнь"
BTN_CAT_SKIP = "⭕ Без метки"

CAT_FROM_BTN = {
    BTN_CAT_STUDY: "study",
    BTN_CAT_WORK: "work",
    BTN_CAT_LIFE: "life",
    BTN_CAT_SKIP: None,
}

# —— Период списка ——
BTN_TODAY = "📅 Сегодня"
BTN_TOMORROW = "⏩ Завтра"
BTN_ALL = "📋 Все даты"
BTN_ARCHIVE = "📦 Архив"
BTN_TO_MAIN = "🏠 В меню"
BTN_BACK = "◀️ Назад"

# —— Фильтр в списке ——
BTN_FIL_ALL = "📋 Все метки"
BTN_FIL_STUDY = "📚 Учёба"
BTN_FIL_WORK = "💼 Работа"
BTN_FIL_LIFE = "🏠 Жизнь"
BTN_FIL_NONE = "🏷 Без метки"

# —— Создание: срок ——
BTN_WITH_DUE = "📅 Со сроком"
BTN_NO_DUE = "🚫 Без срока"

# —— Напоминания (есть дедлайн) ——
BTN_REM_WEEK = "📅 За неделю"
BTN_REM_DAY = "📅 За день"
BTN_REM_HOUR = "⏰ За час"
BTN_REM_2HOURS = "⏰ За 2 часа"
BTN_REM_30MIN = "⏰ За 30 минут"
BTN_REM_DEADLINE = "⏰ В момент срока"
BTN_REM_OFF = "🔕 Не напоминать"
BTN_REM_BACK = "◀️ Назад"

# —— Дополнительные меню ——
BTN_FILTER = "🏷 Фильтр"

# —— Срочность ——
BTN_URG_RED = "🔴 Срочно"
BTN_URG_YELLOW = "🟡 Средняя"
BTN_URG_WHITE = "⚪ Не срочно"

URGENCY_BY_LABEL = {
    BTN_URG_RED: 2,
    BTN_URG_YELLOW: 1,
    BTN_URG_WHITE: 0,
}

# —— Действия над задачей ——
BTN_DONE = "✅ Готово"
BTN_DELETE = "🗑️ Удалить"
BTN_PAUSE = "🟡 ⏸ Пауза"
BTN_RESUME = "🟢 ▶️ Снова в работу"
BTN_TO_LIST = "📘 К списку"
BTN_EDIT = "✏️ Редактировать"

# —— Редактирование задачи ——
BTN_EDIT_TITLE = "📝 Текст задачи"
BTN_EDIT_DUE = "📅 Срок"
BTN_EDIT_PRIORITY = "🔴 Срочность"
BTN_EDIT_CATEGORY = "🏷 Метка"
BTN_EDIT_REMINDER = "🔔 Напоминания"
BTN_EDIT_BACK = "◀️ Назад"

def edit_what_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(BTN_EDIT_TITLE, callback_data="edit_title")],
            [InlineKeyboardButton(BTN_EDIT_DUE, callback_data="edit_due")],
            [InlineKeyboardButton(BTN_EDIT_PRIORITY, callback_data="edit_priority")],
            [InlineKeyboardButton(BTN_EDIT_CATEGORY, callback_data="edit_category")],
            [InlineKeyboardButton(BTN_EDIT_REMINDER, callback_data="edit_reminder")],
            [InlineKeyboardButton(BTN_EDIT_BACK, callback_data="edit_back")],
        ]
    )


def main_reply_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Создать задачу", callback_data="create_task"),
                InlineKeyboardButton("📋 Задачи", callback_data="show_tasks"),
            ]
        ]
    )


def category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(BTN_CAT_STUDY, callback_data="cat_study"),
                InlineKeyboardButton(BTN_CAT_WORK, callback_data="cat_work"),
            ],
            [
                InlineKeyboardButton(BTN_CAT_LIFE, callback_data="cat_life"),
                InlineKeyboardButton(BTN_CAT_SKIP, callback_data="cat_skip"),
            ],
            [InlineKeyboardButton(BTN_TO_MAIN, callback_data="to_main")],
        ]
    )


def tasks_scope_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(BTN_TODAY, callback_data="scope_today"),
                InlineKeyboardButton(BTN_TOMORROW, callback_data="scope_tomorrow"),
            ],
            [InlineKeyboardButton(BTN_ALL, callback_data="scope_all")],
            [InlineKeyboardButton(BTN_ARCHIVE, callback_data="scope_archive")],
            [
                InlineKeyboardButton(BTN_BACK, callback_data="back_to_main"),
                InlineKeyboardButton(BTN_TO_MAIN, callback_data="to_main"),
            ],
        ]
    )


def tasks_list_keyboard() -> InlineKeyboardMarkup:
    """Упрощённая клавиатура — только кнопка выхода."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(BTN_TO_MAIN, callback_data="to_main")]]
    )


def tasks_filter_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(BTN_FIL_ALL, callback_data="filter_all"),
                InlineKeyboardButton(BTN_FIL_STUDY, callback_data="filter_study"),
            ],
            [
                InlineKeyboardButton(BTN_FIL_WORK, callback_data="filter_work"),
                InlineKeyboardButton(BTN_FIL_LIFE, callback_data="filter_life"),
            ],
            [InlineKeyboardButton(BTN_FIL_NONE, callback_data="filter_none")],
            [
                InlineKeyboardButton(BTN_BACK, callback_data="back_to_tasks_scope"),
                InlineKeyboardButton(BTN_TO_MAIN, callback_data="to_main"),
            ],
        ]
    )


def create_due_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(BTN_WITH_DUE, callback_data="due_with"),
                InlineKeyboardButton(BTN_NO_DUE, callback_data="due_without"),
            ],
            [InlineKeyboardButton(BTN_TO_MAIN, callback_data="to_main")],
        ]
    )


def date_step_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(BTN_TO_MAIN, callback_data="to_main")]]
    )


def reminder_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(BTN_REM_ON, callback_data="rem_on"),
                InlineKeyboardButton(BTN_REM_OFF, callback_data="rem_off"),
            ],
            [InlineKeyboardButton(BTN_TO_MAIN, callback_data="to_main")],
        ]
    )


def reminder_time_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(BTN_REM_WEEK, callback_data="rem_week"),
                InlineKeyboardButton(BTN_REM_DAY, callback_data="rem_day"),
            ],
            [
                InlineKeyboardButton(BTN_REM_HOUR, callback_data="rem_hour"),
                InlineKeyboardButton(BTN_REM_2HOURS, callback_data="rem_2hours"),
                InlineKeyboardButton(BTN_REM_30MIN, callback_data="rem_30min"),
            ],
            [
                InlineKeyboardButton(BTN_REM_DEADLINE, callback_data="rem_deadline"),
                InlineKeyboardButton(BTN_REM_OFF, callback_data="rem_off"),
            ],
            [
                InlineKeyboardButton(BTN_REM_BACK, callback_data="rem_back"),
                InlineKeyboardButton(BTN_TO_MAIN, callback_data="to_main"),
            ],
        ]
    )


def create_urgency_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(BTN_URG_RED, callback_data="urg_red"),
                InlineKeyboardButton(BTN_URG_YELLOW, callback_data="urg_yellow"),
            ],
            [InlineKeyboardButton(BTN_URG_WHITE, callback_data="urg_white")],
            [InlineKeyboardButton(BTN_TO_MAIN, callback_data="to_main")],
        ]
    )


def task_actions_keyboard(task: Task) -> InlineKeyboardMarkup:
    row_mid = (
        [InlineKeyboardButton(BTN_RESUME, callback_data=f"task_resume_{task.id}")]
        if task.status in (TaskStatus.PAUSED, TaskStatus.DONE)
        else [InlineKeyboardButton(BTN_PAUSE, callback_data=f"task_pause_{task.id}")]
    )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(BTN_DONE, callback_data=f"task_done_{task.id}"),
                InlineKeyboardButton(BTN_EDIT, callback_data=f"task_edit_{task.id}"),
                InlineKeyboardButton(BTN_DELETE, callback_data=f"task_delete_{task.id}"),
            ],
            row_mid,
            [
                InlineKeyboardButton(BTN_TO_LIST, callback_data="to_list"),
                InlineKeyboardButton(BTN_TO_MAIN, callback_data="to_main"),
            ],
        ]
    )


def urgency_emoji(level: int) -> str:
    if level >= 2:
        return "🔴"
    if level == 1:
        return "🟡"
    return "⚪"


def category_human(cat: Optional[str]) -> str:
    if cat == "study":
        return "Учёба"
    if cat == "work":
        return "Работа"
    if cat == "life":
        return "Жизнь"
    return ""