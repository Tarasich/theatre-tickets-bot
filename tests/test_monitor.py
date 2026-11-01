"""Логика уведомлений: без сети, с подменённым сайтом и Telegram."""
import dataclasses
from datetime import date

import pytest

from theatre_bot import main as bot_main
from theatre_bot.config import Config
from theatre_bot.parser import Show


def make_show(id_: str, available: bool, title: str = "Онегин", day: str = "2026-12-01") -> Show:
    return Show(id=id_, title=title, date=day, label=f"{day} 19:00",
                available=available, url=f"https://example/s{id_}")


class FakeTelegram:
    def __init__(self, *_):
        self.sent: list[tuple[str, str]] = []
        self.updates: list[dict] = []

    def get_updates(self, offset, timeout):
        return [u for u in self.updates if u["update_id"] >= offset]

    def send(self, chat_id, text):
        self.sent.append((chat_id, text))

    def broadcast(self, chat_ids, text):
        for chat_id in chat_ids:
            self.send(chat_id, text)


@pytest.fixture
def make_bot(tmp_path, monkeypatch):
    monkeypatch.setattr(bot_main, "Telegram", FakeTelegram)
    monkeypatch.setattr(bot_main, "fetch_min_price", lambda show: 500)
    monkeypatch.setattr(bot_main.time, "sleep", lambda _: None)
    site: dict = {"shows": []}
    monkeypatch.setattr(bot_main, "fetch_shows", lambda: list(site["shows"]))

    def factory(**overrides):
        cfg = Config(
            bot_token="x", chat_id="42", check_interval_min=5, watch_titles=[],
            date_from=None, date_to=None, first_run_summary=False,
            state_file=tmp_path / "state.json", log_file=tmp_path / "bot.log",
        )
        bot = bot_main.Bot(dataclasses.replace(cfg, **overrides))
        return bot, site

    return factory


def notifications(bot) -> list[str]:
    return [text for _, text in bot.tg.sent if "Появились билеты" in text]


def test_first_run_is_silent(make_bot):
    bot, site = make_bot()
    site["shows"] = [make_show("1", True)]
    bot.check()
    assert bot.tg.sent == []


def test_first_run_summary_flag(make_bot):
    bot, site = make_bot(first_run_summary=True)
    site["shows"] = [make_show("1", True)]
    bot.check()
    assert len(bot.tg.sent) == 1 and "Текущее состояние" in bot.tg.sent[0][1]


def test_notifies_when_tickets_appear_once(make_bot):
    bot, site = make_bot()
    site["shows"] = [make_show("1", False)]
    bot.check()
    site["shows"] = [make_show("1", True)]
    bot.check()
    bot.check()  # билеты всё ещё есть — повторно не уведомляем
    assert len(notifications(bot)) == 1
    assert "от 500 ₽" in notifications(bot)[0]


def test_notifies_about_new_available_session(make_bot):
    bot, site = make_bot()
    site["shows"] = [make_show("1", False)]
    bot.check()
    site["shows"] = [make_show("1", False), make_show("2", True), make_show("3", False)]
    bot.check()
    assert len(notifications(bot)) == 1
    assert "s2" in notifications(bot)[0]


def test_state_survives_restart(make_bot):
    bot, site = make_bot()
    site["shows"] = [make_show("1", True)]
    bot.check()
    restarted, _ = make_bot()
    restarted.check()
    assert notifications(restarted) == []


def test_title_and_date_filters(make_bot):
    bot, site = make_bot(watch_titles=["тартюф"], date_to=date(2026, 12, 31))
    site["shows"] = [make_show("1", False, "Тартюф"), make_show("2", False, "Онегин"),
                     make_show("3", False, "Тартюф", "2027-01-10")]
    bot.check()
    site["shows"] = [dataclasses.replace(s, available=True) for s in site["shows"]]
    bot.check()
    assert len(notifications(bot)) == 1
    assert "s1" in notifications(bot)[0]


def test_layout_alert_once_a_day(make_bot):
    bot, site = make_bot()
    site["shows"] = []
    bot.check()
    bot.check()
    alerts = [t for _, t in bot.tg.sent if "вёрстку" in t]
    assert len(alerts) == 1


def test_watch_commands(make_bot):
    bot, _ = make_bot()
    msg = lambda text: {"text": text, "chat": {"id": 42}}
    bot.handle(msg("/watch Онегин"))
    assert bot.state.watch_titles == ["Онегин"]
    bot.handle(msg("/unwatch all"))
    assert bot.state.watch_titles == []
    bot.handle(msg("/status@TheatreBot"))
    assert "Сеансов не найдено" in bot.tg.sent[-1][1]


def test_run_once_checks_and_answers_commands(make_bot):
    bot, site = make_bot()
    site["shows"] = [make_show("1", True)]
    bot.tg.updates = [{"update_id": 10, "message": {"text": "/status", "chat": {"id": 42}}}]
    assert bot.run_once()
    assert "С билетами: 1 из 1" in bot.tg.sent[-1][1]
    # Следующий запуск не отвечает на ту же команду повторно
    restarted, _ = make_bot()
    restarted.tg.updates = bot.tg.updates
    assert restarted.run_once()
    assert restarted.tg.sent == []


def test_run_once_fails_when_site_is_down(make_bot, monkeypatch):
    bot, _ = make_bot()

    def down():
        raise bot_main.requests.ConnectionError("blocked")

    monkeypatch.setattr(bot_main, "fetch_shows", down)
    assert not bot.run_once()


def test_foreign_chat_is_rejected(make_bot):
    bot, _ = make_bot()
    bot.handle({"text": "/watch Онегин", "chat": {"id": 7}})
    assert bot.state.watch_titles == []
    assert "личный бот" in bot.tg.sent[-1][1]
