import logging
from datetime import datetime, timezone

import pytest

from src.domain.value_objects.discovery_criteria import DiscoveryCriteria
from src.infrastructure.keepa_client import KeepaApiError, KeepaClient

NOW = datetime(2026, 8, 29, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class FakePostSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def post(self, url: str, params: dict, json: dict, timeout: int) -> FakeResponse:
        self.calls.append(json)
        return self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]


def _client(session: FakePostSession) -> KeepaClient:
    return KeepaClient("dummy-key", session=session, sleep=lambda seconds: None)


class TestFindAsins:
    def test_1ページで収まるなら1回で終わる(self) -> None:
        session = FakePostSession(
            [FakeResponse(200, {"asinList": ["B000000001", "B000000002"], "totalResults": 2})]
        )

        asins = _client(session).find_asins(DiscoveryCriteria(), NOW)

        assert [str(asin) for asin in asins] == ["B000000001", "B000000002"]
        assert len(session.calls) == 1

    def test_総件数に達するまでページを進める(self) -> None:
        first = FakeResponse(200, {"asinList": [f"B00000{n:04d}" for n in range(50)], "totalResults": 60})
        second = FakeResponse(200, {"asinList": [f"B00001{n:04d}" for n in range(10)], "totalResults": 60})
        session = FakePostSession([first, second])

        asins = _client(session).find_asins(DiscoveryCriteria(), NOW)

        assert len(asins) == 60
        assert [call["page"] for call in session.calls] == [0, 1]

    def test_空ページが返ったら打ち切る(self) -> None:
        first = FakeResponse(200, {"asinList": [f"B00000{n:04d}" for n in range(50)], "totalResults": 999})
        empty = FakeResponse(200, {"asinList": [], "totalResults": 999})
        session = FakePostSession([first, empty])

        asins = _client(session).find_asins(DiscoveryCriteria(), NOW)

        assert len(asins) == 50
        assert len(session.calls) == 2

    def test_条件の誤りは即座に失敗させる(self) -> None:
        session = FakePostSession(
            [FakeResponse(400, {"error": {"message": "invalidParameter"}})]
        )

        with pytest.raises(KeepaApiError, match="400"):
            _client(session).find_asins(DiscoveryCriteria(), NOW)

    def test_トークン枯渇は待機してから再試行する(self) -> None:
        depleted = FakeResponse(429, {"tokensLeft": -5, "refillIn": 1000})
        ok = FakeResponse(200, {"asinList": ["B000000001"], "totalResults": 1})
        session = FakePostSession([depleted, ok])
        slept: list[float] = []
        client = KeepaClient("dummy-key", session=session, sleep=slept.append)

        asins = client.find_asins(DiscoveryCriteria(), NOW)

        assert [str(asin) for asin in asins] == ["B000000001"]
        assert slept == [1.0]

    def test_解釈できないASINは落とす(self) -> None:
        session = FakePostSession(
            [FakeResponse(200, {"asinList": ["B000000001", "", "短い"], "totalResults": 3})]
        )

        asins = _client(session).find_asins(DiscoveryCriteria(), NOW)

        assert [str(asin) for asin in asins] == ["B000000001"]

    def test_max_pagesの上限で打ち切り実際に叩いたページ数だけログに残す(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        first = FakeResponse(200, {"asinList": [f"B00000{n:04d}" for n in range(50)], "totalResults": 999})
        second = FakeResponse(200, {"asinList": [f"B00001{n:04d}" for n in range(50)], "totalResults": 999})
        session = FakePostSession([first, second])

        with caplog.at_level(logging.INFO, logger="src.infrastructure.keepa_client"):
            asins = _client(session).find_asins(DiscoveryCriteria(), NOW, max_pages=2)

        assert len(session.calls) == 2
        assert len(asins) == 100

        record = next(r for r in caplog.records if r.message == "Product Finder で候補を取得しました")
        assert record.context == {"count": 100, "pages": 2}
