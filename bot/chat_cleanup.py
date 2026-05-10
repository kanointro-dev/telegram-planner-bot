from __future__ import annotations

from typing import Optional

from telegram.error import BadRequest
from telegram.ext import ContextTypes

_TRACK_KEY = "_bot_msg_ids"


def peek_tracked_ids(user_data: dict) -> list[int]:
    return list(user_data.get(_TRACK_KEY, []))


async def purge_message_ids(bot, chat_id: int, ids: list[int]) -> None:
    for mid in ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except BadRequest:
            pass


async def delete_tracked_bot_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    ids = context.user_data.pop(_TRACK_KEY, [])
    await purge_message_ids(context.bot, chat_id, ids)


def remember_bot_message(context: ContextTypes.DEFAULT_TYPE, message_id: int) -> None:
    context.user_data.setdefault(_TRACK_KEY, []).append(message_id)


async def send_panel(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    reply_markup=None,
) -> None:
    await delete_tracked_bot_messages(context, chat_id)
    msg = await context.bot.send_message(
        chat_id=chat_id, text=text, reply_markup=reply_markup
    )
    remember_bot_message(context, msg.message_id)


async def send_panel_html(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    html: str,
    reply_markup=None,
) -> None:
    await delete_tracked_bot_messages(context, chat_id)
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=html,
        parse_mode="HTML",
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )
    remember_bot_message(context, msg.message_id)


async def try_delete_user_message(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int]
) -> None:
    if message_id is None:
        return
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except BadRequest:
        pass
