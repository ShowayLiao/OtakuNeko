import pytest

from app.services.bangumi_client import (
    BangumiClient,
    _calendar_has_complete_weekdays,
    _parse_calendar_html,
)


def _calendar_html() -> str:
    weekdays = (
        ("Sun", "星期日", 101),
        ("Mon", "星期一", 102),
        ("Tue", "星期二", 103),
        ("Wed", "星期三", 104),
        ("Thu", "星期四", 105),
        ("Fri", "星期五", 106),
        ("Sat", "星期六", 107),
    )
    sections = []
    for css_name, label, subject_id in weekdays:
        sections.append(
            f"""
            <li class="week {css_name}">
                <h3>{label}</h3>
                <div class="info">
                    <p><a class="l" href="/subject/{subject_id}">{label}番</a></p>
                    <p><a href="/subject/{subject_id}">Original title</a></p>
                </div>
            </li>
            """
        )
    return f'<div class="BgmCalendar"><ul class="large">{"".join(sections)}</ul></div>'


def test_calendar_completeness_requires_all_bangumi_weekday_ids():
    incomplete = [{"weekday": {"id": 1}, "items": []}]
    complete = [{"weekday": {"id": day_id}, "items": []} for day_id in range(1, 8)]

    assert _calendar_has_complete_weekdays(incomplete) is False
    assert _calendar_has_complete_weekdays(complete) is True


def test_parse_calendar_html_returns_all_weekdays_and_deduplicates_subject_links():
    calendar = _parse_calendar_html(_calendar_html())

    assert [day["weekday"]["id"] for day in calendar] == [7, 1, 2, 3, 4, 5, 6]
    assert [day["items"][0]["id"] for day in calendar] == list(range(101, 108))
    assert all(len(day["items"]) == 1 for day in calendar)
    assert calendar[1]["items"][0]["name_cn"] == "星期一番"


@pytest.mark.asyncio
async def test_get_calendar_falls_back_to_web_calendar_and_merges_api_details(monkeypatch):
    api_calendar = [
        {
            "weekday": {"en": "Mon", "cn": "星期一", "ja": "月曜日", "id": 1},
            "items": [
                {
                    "id": 102,
                    "name": "Monday original",
                    "name_cn": "星期一番",
                    "rating": {"score": 8.5, "total": 12},
                }
            ],
        }
    ]

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

        @property
        def text(self):
            return self.payload if isinstance(self.payload, str) else ""

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            self.urls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, **kwargs):
            self.urls.append(url)
            if url.endswith("/calendar") and "api.bgm.tv" in url:
                return FakeResponse(api_calendar)
            return FakeResponse(_calendar_html())

    monkeypatch.setattr("app.services.bangumi_client.httpx.AsyncClient", FakeAsyncClient)

    result = await BangumiClient.get_calendar.__wrapped__(BangumiClient())

    assert [day["weekday"]["id"] for day in result] == [7, 1, 2, 3, 4, 5, 6]
    monday = next(day for day in result if day["weekday"]["id"] == 1)
    assert monday["items"][0]["rating"] == {"score": 8.5, "total": 12}
