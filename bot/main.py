from __future__ import annotations

import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot import config
from bot.handlers import (
    cmd_add,
    cmd_cancel,
    cmd_done,
    cmd_focus,
    cmd_help,
    cmd_inbox,
    cmd_log_start,
    cmd_log_stop,
    cmd_log_today,
    cmd_rm,
    cmd_start,
    cmd_today,
    cmd_timezone,
    on_main_text,
)
from bot.reminders import reschedule_all_reminders
from bot.storage.postgres_store import PostgresStorage

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.DEBUG,
)
logger = logging.getLogger(__name__)


async def _post_init(application: Application) -> None:
    print("DEBUG: Starting _post_init", flush=True)
    print(f"DEBUG: DATABASE_URL present: {os.environ.get('DATABASE_URL') is not None}", flush=True)
    storage = PostgresStorage(os.environ["DATABASE_URL"], config.DEFAULT_TIMEZONE)
    await storage.connect()
    application.bot_data["storage"] = storage
    application.bot_data["tz_name"] = config.DEFAULT_TIMEZONE
    await reschedule_all_reminders(application)
    logger.info("База подключена, напоминания перепланированы.")


async def _post_shutdown(application: Application) -> None:
    storage: PostgresStorage = application.bot_data.get("storage")
    if storage:
        await storage.close()
        logger.info("Соединение с базой закрыто.")


def main() -> None:
    application = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("cancel", cmd_cancel))
    application.add_handler(CommandHandler("timezone", cmd_timezone))
    application.add_handler(CommandHandler("add", cmd_add))
    application.add_handler(CommandHandler("today", cmd_today))
    application.add_handler(CommandHandler("inbox", cmd_inbox))
    application.add_handler(CommandHandler("done", cmd_done))
    application.add_handler(CommandHandler("rm", cmd_rm))
    application.add_handler(CommandHandler("focus", cmd_focus))
    application.add_handler(CommandHandler("log_start", cmd_log_start))
    application.add_handler(CommandHandler("log_stop", cmd_log_stop))
    application.add_handler(CommandHandler("log_today", cmd_log_today))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_main_text))

    from telegram.ext import CallbackQueryHandler
    from bot.handlers import handle_task_callback
    from bot.handlers import cmd_reset

    application.add_handler(CommandHandler("reset", cmd_reset))
    
    application.add_handler(CallbackQueryHandler(handle_task_callback))

    # Health check server
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Обрабатываем любой путь (и /, и /health, и любой другой)
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Bot is alive')
        
        def log_message(self, format, *args):
            pass  # Отключаем логи health check

    def run_health():
        port = int(os.environ.get('PORT', 10000))
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        server.serve_forever()

    # Запускаем health-сервер в отдельном потоке
    print("DEBUG: Starting health check server...", flush=True)
    health_thread = threading.Thread(target=run_health, daemon=True)
    health_thread.start()
    print(f"✅ Health check server started on port {os.environ.get('PORT', 10000)}")

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
