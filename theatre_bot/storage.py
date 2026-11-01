"""Состояние бота в JSON-файле: сеансы, подписчики, список отслеживаемых спектаклей."""
import json
import os
import tempfile
from pathlib import Path


class State:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict = {
            "shows": {},           # id сеанса -> Show.to_dict()
            "subscribers": [],     # chat_id
            "watch_titles": None,  # None = ещё не инициализирован из конфига
            "tg_offset": 0,        # последний обработанный update_id + 1
            "last_layout_alert": 0.0,
            "initialized": False,  # была ли хоть одна успешная проверка
        }
        if path.exists():
            self.data.update(json.loads(path.read_text(encoding="utf-8")))

    def save(self) -> None:
        # Пишем во временный файл и подменяем, чтобы не испортить состояние при сбое
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    @property
    def shows(self) -> dict:
        return self.data["shows"]

    @property
    def subscribers(self) -> list:
        return self.data["subscribers"]

    def subscribe(self, chat_id: str) -> bool:
        if chat_id in self.subscribers:
            return False
        self.subscribers.append(chat_id)
        return True

    @property
    def watch_titles(self) -> list[str]:
        return self.data["watch_titles"] or []

    def set_watch_titles(self, titles: list[str]) -> None:
        self.data["watch_titles"] = titles
