from pathlib import Path

from theatre_bot.parser import parse_min_price, parse_shows

FIXTURES = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parses_all_sessions():
    shows = parse_shows(read("theatre.html"))
    assert len(shows) == 23
    assert len({s.id for s in shows}) == 23
    assert all(s.url.startswith("https://quicktickets.ru/orel-teatr-svobodnoe-prostranstvo/s")
               for s in shows)
    assert all(s.date and s.label for s in shows)


def test_session_with_tickets():
    shows = {s.id: s for s in parse_shows(read("theatre.html"))}
    show = shows["3204"]
    assert show.available
    assert show.title == "Спектакль «Главная роль»"
    assert show.date == "2026-12-07"
    assert show.label == "07 декабря (пн) 19:00"


def test_sold_out_session():
    shows = {s.id: s for s in parse_shows(read("theatre.html"))}
    show = shows["3184"]
    assert not show.available
    assert show.title == "Самый правдивый"
    assert show.date == "2026-11-03"


def test_html_entities_in_title_are_decoded():
    titles = {s.title for s in parse_shows(read("theatre.html"))}
    assert 'Спектакль "Дюймовочка"' in titles


def test_empty_page():
    assert parse_shows(read("empty.html")) == []


def test_min_price():
    assert parse_min_price(read("session_available.html")) == 3000
    assert parse_min_price(read("empty.html")) is None
