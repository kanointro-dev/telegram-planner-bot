import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Задайте переменную окружения {name} (см. .env.example)")
    return value


TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")
DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "Europe/Moscow")
DATABASE_PATH: Path = Path(
    os.getenv("DATABASE_PATH", str(Path(__file__).resolve().parent.parent / "data" / "planner.db"))
)
