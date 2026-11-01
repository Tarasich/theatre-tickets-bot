"""Настройки бота из переменных окружения (и файла .env рядом с проектом)."""
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SITE_ROOT = "https://quicktickets.ru"
THEATRE_URL = f"{SITE_ROOT}/orel-teatr-svobodnoe-prostranstvo"

# Не нагружаем сайт чаще, чем раз в 2 минуты, даже если в конфиге указано меньше
MIN_INTERVAL_MIN = 2.0


def _date_or_none(value: str) -> date | None:
    value = value.strip()
    return date.fromisoformat(value) if value else None


def _bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "да", "on")


@dataclass(frozen=True)
class Config:
    bot_token: str
    chat_id: str
    check_interval_min: float
    watch_titles: list[str]
    date_from: date | None
    date_to: date | None
    first_run_summary: bool
    state_file: Path
    log_file: Path


def load_config() -> Config:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Не задан TELEGRAM_BOT_TOKEN (см. .env.example)")

    interval = float(os.getenv("CHECK_INTERVAL_MIN", "5") or 5)
    titles = [t.strip() for t in os.getenv("WATCH_TITLES", "").split(",") if t.strip()]

    return Config(
        bot_token=token,
        chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        check_interval_min=max(interval, MIN_INTERVAL_MIN),
        watch_titles=titles,
        date_from=_date_or_none(os.getenv("DATE_FROM", "")),
        date_to=_date_or_none(os.getenv("DATE_TO", "")),
        first_run_summary=_bool(os.getenv("FIRST_RUN_SUMMARY", "false")),
        state_file=BASE_DIR / os.getenv("STATE_FILE", "state.json"),
        log_file=BASE_DIR / os.getenv("LOG_FILE", "bot.log"),
    )
