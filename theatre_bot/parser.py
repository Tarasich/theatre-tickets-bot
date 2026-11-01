"""Загрузка и разбор страниц quicktickets.ru.

Всё, что зависит от вёрстки сайта, собрано здесь: если сайт поменяет разметку,
править нужно только этот файл.
"""
import logging
import random
import re
import time
from dataclasses import asdict, dataclass

import requests
from bs4 import BeautifulSoup

from .config import SITE_ROOT, THEATRE_URL

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

# Селекторы страницы театра
CARD = "div.quick-tickets-event-card"
CARD_SESSION_DATE = "span.event-filter-session"  # скрытый блок с ISO-датами сеансов
SESSION = "div.quick-tickets-session-option"
SESSION_SOLD_CLASS = "quick-tickets-session-option--sold"
SESSION_LINK = "a.sessions__date-link"
SESSION_LABEL = "span.quick-tickets-session-option__label"

# На странице сеанса цены категорий лежат в dataLayer: {name:'Место в зале', ... price:4500, ...}
PRICE_RE = re.compile(r"name:'Место в зале'[^}]*?price:(\d+)")

_http = requests.Session()
_http.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"})


@dataclass
class Show:
    id: str
    title: str
    date: str | None  # ISO, например "2026-12-07"
    label: str        # как на сайте: "07 декабря (пн) 19:00"
    available: bool
    url: str

    def to_dict(self) -> dict:
        return asdict(self)


def fetch(url: str, retries: int = 4, timeout: float = 20) -> str:
    """GET с повторами и экспоненциальной задержкой."""
    delay = 5.0
    for attempt in range(1, retries + 1):
        try:
            resp = _http.get(url, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.text
        except requests.RequestException as exc:
            if attempt == retries:
                raise
            wait = delay + random.uniform(0, delay / 2)
            log.warning("Ошибка загрузки %s (%s), повтор через %.0f с", url, exc, wait)
            time.sleep(wait)
            delay *= 2
    raise AssertionError("unreachable")


def parse_shows(html: str) -> list[Show]:
    """Все сеансы со страницы театра."""
    soup = BeautifulSoup(html, "html.parser")
    shows: list[Show] = []
    for card in soup.select(CARD):
        title = (card.get("data-filter-name") or "").strip()
        if not title:
            heading = card.select_one("h3 span.underline")
            title = heading.get_text(strip=True) if heading else "Без названия"

        dates = {
            span.get("data-session-id"): span.get("data-date")
            for span in card.select(CARD_SESSION_DATE)
        }

        for opt in card.select(SESSION):
            show_id = opt.get("data-event-filter-session-id")
            link = opt.select_one(SESSION_LINK)
            if not show_id or link is None:
                continue
            label = opt.select_one(SESSION_LABEL)
            shows.append(Show(
                id=show_id,
                title=title,
                date=dates.get(show_id),
                label=label.get_text(" ", strip=True) if label else "",
                available=SESSION_SOLD_CLASS not in (opt.get("class") or []),
                url=SITE_ROOT + link["href"],
            ))
    return shows


def parse_min_price(html: str) -> int | None:
    """Минимальная цена со страницы сеанса (None, если не нашли)."""
    prices = [int(p) for p in PRICE_RE.findall(html)]
    return min(prices) if prices else None


def fetch_shows() -> list[Show]:
    return parse_shows(fetch(THEATRE_URL))


def fetch_min_price(show: Show) -> int | None:
    try:
        return parse_min_price(fetch(show.url, retries=2))
    except requests.RequestException as exc:
        log.warning("Не удалось получить цену для %s: %s", show.url, exc)
        return None
