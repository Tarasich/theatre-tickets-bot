"""Точка входа: периодическая проверка сайта и обработка команд Telegram."""
import argparse
import logging
import random
import sys
import time
from datetime import date

import requests

from .config import MIN_INTERVAL_MIN, THEATRE_URL, Config, load_config
from .notifier import Telegram, esc, format_available, format_status
from .parser import Show, fetch_min_price, fetch_shows
from .storage import State

log = logging.getLogger("theatre_bot")

LAYOUT_ALERT_EVERY = 24 * 3600
POLL_TIMEOUT = 25


def setup_logging(cfg: Config) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handlers: list[logging.Handler] = [logging.FileHandler(cfg.log_file, encoding="utf-8")]
    # Под pythonw.exe (запуск без окна) консоли нет, пишем только в файл
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    for handler in handlers:
        handler.setFormatter(fmt)
        root.addHandler(handler)


class Bot:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.tg = Telegram(cfg.bot_token)
        self.state = State(cfg.state_file)
        if cfg.chat_id:
            self.state.subscribe(cfg.chat_id)
        if self.state.data["watch_titles"] is None:
            self.state.set_watch_titles(cfg.watch_titles)
        self.last_check = 0.0
        self.state.save()

    # ---------- фильтры ----------

    def is_watched(self, show: Show) -> bool:
        titles = self.state.watch_titles
        if titles and not any(t.lower() in show.title.lower() for t in titles):
            return False
        if show.date:
            d = date.fromisoformat(show.date)
            if self.cfg.date_from and d < self.cfg.date_from:
                return False
            if self.cfg.date_to and d > self.cfg.date_to:
                return False
        return True

    def cached_shows(self) -> list[Show]:
        return [Show(**d) for d in self.state.shows.values()]

    # ---------- проверка сайта ----------

    def check(self) -> list[Show] | None:
        """Проверяет сайт и рассылает уведомления. Возвращает сеансы или None при ошибке."""
        self.last_check = time.time()
        try:
            shows = fetch_shows()
        except requests.RequestException as exc:
            log.error("Сайт недоступен: %s", exc)
            return None

        if not shows:
            self.layout_alert()
            return shows

        first_run = not self.state.data["initialized"]
        previous = self.state.shows
        appeared = [
            s for s in shows
            if s.available and self.is_watched(s)
            and not (previous.get(s.id) or {}).get("available", False)
        ]
        log.info("Сеансов: %d, с билетами: %d, новых с билетами: %d",
                 len(shows), sum(s.available for s in shows), len(appeared))

        if first_run:
            if self.cfg.first_run_summary:
                watched = [s for s in shows if self.is_watched(s)]
                self.tg.broadcast(self.state.subscribers,
                                  "Бот запущен. Текущее состояние:\n\n" + format_status(watched))
        else:
            for show in appeared:
                price = fetch_min_price(show)
                self.tg.broadcast(self.state.subscribers, format_available(show, price))
                time.sleep(random.uniform(1, 2))

        self.state.data["shows"] = {s.id: s.to_dict() for s in shows}
        self.state.data["initialized"] = True
        self.state.save()
        return shows

    def layout_alert(self) -> None:
        log.warning("На странице не найдено ни одного сеанса — возможно, изменилась вёрстка")
        if time.time() - self.state.data["last_layout_alert"] < LAYOUT_ALERT_EVERY:
            return
        self.state.data["last_layout_alert"] = time.time()
        self.state.save()
        self.tg.broadcast(
            self.state.subscribers,
            "⚠️ На странице театра не нашлось ни одного сеанса. Возможно, сайт поменял "
            f"вёрстку и парсер нужно поправить (theatre_bot/parser.py).\n{THEATRE_URL}",
        )

    # ---------- команды ----------

    def allowed(self, chat_id: str) -> bool:
        # Если chat_id задан в конфиге — бот только для этого чата, иначе открыт всем
        return not self.cfg.chat_id or chat_id == self.cfg.chat_id

    def handle(self, message: dict) -> None:
        text = (message.get("text") or "").strip()
        chat_id = str(message["chat"]["id"])
        if not text.startswith("/"):
            return
        command, _, arg = text.partition(" ")
        command = command[1:].split("@")[0].lower()  # "/check@MyBot" -> "check"
        arg = arg.strip()
        log.info("Команда %s от %s", command, chat_id)

        if not self.allowed(chat_id):
            self.tg.send(chat_id, f"Это личный бот. Ваш chat_id: <code>{chat_id}</code>")
            return

        if command == "start":
            new = self.state.subscribe(chat_id)
            self.state.save()
            self.tg.send(chat_id, (
                ("Вы подписаны на уведомления о билетах." if new else "Вы уже подписаны.")
                + f"\nВаш chat_id: <code>{chat_id}</code>\n\n"
                "/status — сеансы и наличие билетов\n/check — проверить сейчас\n"
                "/watch &lt;название&gt; — следить только за этим спектаклем\n"
                "/unwatch &lt;название&gt; или /unwatch all — убрать из списка"
            ))
        elif command == "status":
            self.tg.send(chat_id, self.status_text())
        elif command == "check":
            if time.time() - self.last_check < MIN_INTERVAL_MIN * 60:
                self.tg.send(chat_id, "Сайт только что проверялся, показываю последние данные.\n\n"
                             + self.status_text())
                return
            shows = self.check()
            if shows is None:
                self.tg.send(chat_id, "Не удалось загрузить сайт, попробую позже.")
            else:
                self.tg.send(chat_id, self.status_text())
        elif command == "watch":
            if not arg:
                self.tg.send(chat_id, "Укажите название: /watch Онегин")
                return
            titles = self.state.watch_titles
            if arg.lower() not in (t.lower() for t in titles):
                self.state.set_watch_titles(titles + [arg])
                self.state.save()
            self.tg.send(chat_id, self.watch_text())
        elif command == "unwatch":
            if arg.lower() in ("all", "все", ""):
                self.state.set_watch_titles([])
            else:
                self.state.set_watch_titles(
                    [t for t in self.state.watch_titles if t.lower() != arg.lower()])
            self.state.save()
            self.tg.send(chat_id, self.watch_text())
        else:
            self.tg.send(chat_id, "Неизвестная команда. /start — список команд.")

    def watch_text(self) -> str:
        titles = self.state.watch_titles
        if not titles:
            return "Слежу за всеми спектаклями."
        return "Слежу только за: " + ", ".join(esc(t) for t in titles)

    def status_text(self) -> str:
        shows = [s for s in self.cached_shows() if self.is_watched(s)]
        return format_status(shows) + "\n\n" + self.watch_text()

    # ---------- главный цикл ----------

    def run(self) -> None:
        self.tg.set_commands()
        interval = self.cfg.check_interval_min * 60
        next_check = 0.0
        log.info("Бот запущен, интервал проверки %.1f мин", self.cfg.check_interval_min)

        while True:
            now = time.time()
            if now >= next_check:
                self.check()
                # Разброс ±15 %, чтобы запросы не шли строго по расписанию
                next_check = time.time() + interval * random.uniform(0.85, 1.15)

            wait = int(max(1, min(POLL_TIMEOUT, next_check - time.time())))
            if not self.process_updates(wait):
                time.sleep(5)

    def process_updates(self, wait: int) -> bool:
        """Забирает и обрабатывает команды из Telegram. False — если Telegram недоступен."""
        try:
            updates = self.tg.get_updates(self.state.data["tg_offset"], wait)
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            log.warning("Ошибка getUpdates: %s", exc)
            return False

        for update in updates:
            self.state.data["tg_offset"] = update["update_id"] + 1
            if "message" in update:
                try:
                    self.handle(update["message"])
                except Exception:
                    log.exception("Ошибка обработки команды")
        if updates:
            self.state.save()
        return True

    def run_once(self) -> bool:
        """Одна проверка и ответы на накопившиеся команды — для запуска по расписанию
        (GitHub Actions, cron). False — если сайт или Telegram были недоступны."""
        site_ok = self.check() is not None
        telegram_ok = self.process_updates(0)
        return site_ok and telegram_ok


def main() -> None:
    parser = argparse.ArgumentParser(prog="theatre_bot")
    parser.add_argument("--once", action="store_true",
                        help="одна проверка и выход (для запуска по расписанию)")
    args = parser.parse_args()

    cfg = load_config()
    setup_logging(cfg)
    bot = Bot(cfg)
    if args.once:
        # Ненулевой код выхода, чтобы GitHub Actions пометил запуск как неудачный
        sys.exit(0 if bot.run_once() else 1)
    try:
        bot.run()
    except KeyboardInterrupt:
        log.info("Остановлено")


if __name__ == "__main__":
    main()
