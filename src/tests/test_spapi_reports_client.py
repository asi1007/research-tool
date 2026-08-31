from datetime import date

import pytest

from src.infrastructure.spapi_reports_client import ReportError, SpApiReportsClient


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, content: bytes = b"") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, posts: list[FakeResponse], gets: list[FakeResponse]) -> None:
        self.posts = posts
        self.gets = gets
        self.post_calls: list[dict] = []
        self.get_calls: list[str] = []

    def post(self, url: str, **kwargs) -> FakeResponse:
        self.post_calls.append({"url": url, **kwargs})
        return self.posts[min(len(self.post_calls) - 1, len(self.posts) - 1)]

    def get(self, url: str, **kwargs) -> FakeResponse:
        self.get_calls.append(url)
        return self.gets[min(len(self.get_calls) - 1, len(self.gets) - 1)]


TOKEN = FakeResponse(200, {"access_token": "token"})
CREATED = FakeResponse(202, {"reportId": "R1"})
REPORT_BODY = b'{"dataByDepartmentAndSearchTerm": [{"searchTerm": "x", "searchFrequencyRank": 1}]}'


def _client(session: FakeSession) -> SpApiReportsClient:
    return SpApiReportsClient("id", "secret", "refresh", session=session, sleep=lambda _: None)


class TestFetchSearchTermsReport:
    def test_生成を待ってから中身を返す(self) -> None:
        session = FakeSession(
            posts=[TOKEN, CREATED, TOKEN, TOKEN, TOKEN],
            gets=[
                FakeResponse(200, {"processingStatus": "IN_PROGRESS"}),
                FakeResponse(200, {"processingStatus": "DONE", "reportDocumentId": "D1"}),
                FakeResponse(200, {"url": "https://example.com/doc"}),
                FakeResponse(200, content=REPORT_BODY),
            ],
        )

        report = _client(session).fetch_search_terms_report(date(2026, 8, 16), date(2026, 8, 22))

        assert report["dataByDepartmentAndSearchTerm"][0]["searchFrequencyRank"] == 1
        assert session.post_calls[1]["json"]["dataStartTime"] == "2026-08-16T00:00:00Z"
        assert session.post_calls[1]["json"]["reportOptions"] == {"reportPeriod": "WEEK"}

    def test_生成に失敗したら例外にする(self) -> None:
        session = FakeSession(
            posts=[TOKEN, CREATED, TOKEN],
            gets=[FakeResponse(200, {"processingStatus": "FATAL"})],
        )

        with pytest.raises(ReportError, match="FATAL"):
            _client(session).fetch_search_terms_report(date(2026, 8, 16), date(2026, 8, 22))

    def test_要求が拒まれたら例外にする(self) -> None:
        session = FakeSession(posts=[TOKEN, FakeResponse(403, {"errors": []})], gets=[])

        with pytest.raises(ReportError, match="403"):
            _client(session).fetch_search_terms_report(date(2026, 8, 16), date(2026, 8, 22))
