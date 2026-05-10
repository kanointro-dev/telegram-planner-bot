from __future__ import annotations

from typing import Optional

from telegram import KeyboardButton, ReplyKeyboardMarkup

from bot.models import Task, TaskStatus

# —— Главное меню ——
BTN_CREATE = "➕ Создать задачу"
BTN_TASKS = "📋 Задачи"
BTN_RANDOM = "🎲 Случайная"

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
BTN_TO_MAIN = "🟠 🏠 В меню"

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


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_CREATE)],
            [KeyboardButton(BTN_TASKS), KeyboardButton(BTN_RANDOM)],
        ],
        resize_keyboard=True,
    )


def category_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_CAT_STUDY), KeyboardButton(BTN_CAT_WORK)],
            [KeyboardButton(BTN_CAT_LIFE), KeyboardButton(BTN_CAT_SKIP)],
            [KeyboardButton(BTN_TO_MAIN)],
        ],
        resize_keyboard=True,
    )


def tasks_scope_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_TODAY), KeyboardButton(BTN_TOMORROW)],
            [KeyboardButton(BTN_ALL)],
            [KeyboardButton(BTN_ARCHIVE)],
            [KeyboardButton(BTN_TO_MAIN)],
        ],
        resize_keyboard=True,
    )


def tasks_list_keyboard() -> ReplyKeyboardMarkup:
    """Упрощённая клавиатура — только кнопка выхода."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_TO_MAIN)]],
        resize_keyboard=True,
    )


def tasks_filter_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_FIL_ALL), KeyboardButton(BTN_FIL_STUDY)],
            [KeyboardButton(BTN_FIL_WORK), KeyboardButton(BTN_FIL_LIFE)],
            [KeyboardButton(BTN_FIL_NONE)],
            [KeyboardButton(BTN_TO_MAIN)],
        ],
        resize_keyboard=True,
    )


def create_due_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_WITH_DUE), KeyboardButton(BTN_NO_DUE)],
            [KeyboardButton(BTN_TO_MAIN)],
        ],
        resize_keyboard=True,
    )


def date_step_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_TO_MAIN)]],
        resize_keyboard=True,
    )


def reminder_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_REM_ON), KeyboardButton(BTN_REM_OFF)],
            [KeyboardButton(BTN_TO_MAIN)],
        ],
        resize_keyboard=True,
    )


def reminder_time_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_REM_WEEK), KeyboardButton(BTN_REM_DAY)],
            [KeyboardButton(BTN_REM_HOUR), KeyboardButton(BTN_REM_2HOURS), KeyboardButton(BTN_REM_30MIN)],
            [KeyboardButton(BTN_REM_DEADLINE), KeyboardButton(BTN_REM_OFF)],
            [KeyboardButton(BTN_REM_BACK), KeyboardButton(BTN_TO_MAIN)],
        ],
        resize_keyboard=True,
    )


def create_urgency_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_URG_RED), KeyboardButton(BTN_URG_YELLOW)],
            [KeyboardButton(BTN_URG_WHITE)],
            [KeyboardButton(BTN_TO_MAIN)],
        ],
        resize_keyboard=True,
    )


def task_actions_keyboard(task: Task) -> ReplyKeyboardMarkup:
    row_mid = (
        [KeyboardButton(BTN_RESUME)]
        if task.status in (TaskStatus.PAUSED, TaskStatus.DONE)
        else [KeyboardButton(BTN_PAUSE)]
    )
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_DONE), KeyboardButton(BTN_DELETE)],
            row_mid,
            [KeyboardButton(BTN_TO_LIST), KeyboardButton(BTN_TO_MAIN)],
        ],
        resize_keyboard=True,
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