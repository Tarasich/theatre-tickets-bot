"""Минимальный клиент Telegram Bot API и форматирование сообщений."""
import html
import logging

import requests

from .parser import Show

log = logging.getLogger(__name__)

# Telegram не принимает сообщения длиннее 4096 символов
MAX_MESSAGE_LEN = 4000


class Telegram:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"
        self.http = requests.Session()

    def _call(self, method: str, http_timeout: float = 30, **params) -> dict:
        resp = self.http.post(f"{self.base}/{method}", json=params, timeout=http_timeout)
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method}: {data.get('description')}")
        return data["result"]

    def send(self, chat_id: str, text: str) -> None:
        for chunk in _split(text):
            try:
                self._call("sendMessage", chat_id=chat_id, text=chunk,
                           parse_mode="HTML", disable_web_page_preview=True)
            except (requests.RequestException, RuntimeError, ValueError) as exc:
                log.error("Не удалось отправить сообщение в %s: %s", chat_id, exc)

    def broadcast(self, chat_ids: list[str], text: str) -> None:
        for chat_id in chat_ids:
            self.send(chat_id, text)

    def get_updates(self, offset: int, timeout: int) -> list[dict]:
        """Long polling: ждёт новые сообщения до timeout секунд."""
        return self._call("getUpdates", http_timeout=timeout + 10, offset=offset,
                          timeout=timeout, allowed_updates=["message"])

    def set_commands(self) -> None:
        commands = [
            {"command": "start", "description": "Подписаться на уведомления"},
            {"command": "status", "description": "Сеансы и наличие билетов"},
            {"command": "check", "description": "Проверить сейчас"},
            {"command": "watch", "description": "Следить только за спектаклем: /watch Онегин"},
            {"command": "unwatch", "description": "Убрать спектакль из списка (/unwatch all — все)"},
        ]
        try:
            self._call("setMyCommands", commands=commands)
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            log.warning("setMyCommands: %s", exc)


def _split(text: str) -> list[str]:
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_MESSAGE_LEN:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current)
    return chunks


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def format_available(show: Show, min_price: int | None) -> str:
    price = f"\n💰 от {min_price} ₽" if min_price else ""
    return (
        f"🎭 <b>Появились билеты!</b>\n"
        f"<b>{esc(show.title)}</b>\n"
        f"📅 {esc(show.label)}{price}\n"
        f'<a href="{show.url}">Купить билеты</a>'
    )


def format_status(shows: list[Show]) -> str:
    if not shows:
        return "Сеансов не найдено."
    lines = ["<b>Сеансы на сайте:</b>"]
    for s in sorted(shows, key=lambda s: (s.date or "", s.label)):
        mark = "✅" if s.available else "❌"
        lines.append(f'{mark} <a href="{s.url}">{esc(s.label)}</a> — {esc(s.title)}')
    available = sum(s.available for s in shows)
    lines.append(f"\nС билетами: {available} из {len(shows)}")
    return "\n".join(lines)
