import pytest

from src.domain.value_objects.asin import Asin
from src.infrastructure.keepa_client import KeepaApiError, KeepaClient

ASIN = Asin("B0CCX6ZXRV")


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.request_count = 0

    def get(self, url: str, params: dict, timeout: int) -> FakeResponse:
        response = self.responses[min(self.request_count, len(self.responses) - 1)]
        self.request_count += 1
        return response


class FakeClock:
    def __init__(self) -> None:
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


def _client(session: FakeSession, clock: FakeClock) -> KeepaClient:
    return KeepaClient("dummy-key", session=session, sleep=clock.sleep)


OK_PAYLOAD = {"products": [{"asin": "B0CCX6ZXRV", "title": "商品"}], "tokensLeft": 250}


class TestTokenWait:
    def test_トークンが残っていれば待たない(self) -> None:
        session, clock = FakeSession([FakeResponse(200, OK_PAYLOAD)]), FakeClock()

        _client(session, clock).fetch_product(ASIN)

        assert clock.slept == []

    def test_トークン枯渇なら補充まで待って再試行する(self) -> None:
        depleted = FakeResponse(429, {"tokensLeft": -3, "refillIn": 50000})
        session = FakeSession([depleted, FakeResponse(200, OK_PAYLOAD)])
        clock = FakeClock()

        product = _client(session, clock).fetch_product(ASIN)

        assert session.request_count == 2
        assert clock.slept == [50.0]
        assert product["title"] == "商品"

    def test_ステータス200でもトークンが負なら待って再試行する(self) -> None:
        depleted = FakeResponse(200, {"tokensLeft": -1, "refillIn": 12000, "products": []})
        session = FakeSession([depleted, FakeResponse(200, OK_PAYLOAD)])
        clock = FakeClock()

        _client(session, clock).fetch_product(ASIN)

        assert clock.slept == [12.0]

    def test_リトライ上限を超えたら例外を投げる(self) -> None:
        depleted = FakeResponse(429, {"tokensLeft": -3, "refillIn": 1000})
        session, clock = FakeSession([depleted]), FakeClock()

        with pytest.raises(KeepaApiError):
            _client(session, clock).fetch_product(ASIN)

    def test_待機時間には上限を設ける(self) -> None:
        depleted = FakeResponse(429, {"tokensLeft": -3, "refillIn": 9_999_999})
        session = FakeSession([depleted, FakeResponse(200, OK_PAYLOAD)])
        clock = FakeClock()

        _client(session, clock).fetch_product(ASIN)

        assert clock.slept == [300.0]

    def test_商品が見つからない場合はリトライしない(self) -> None:
        session = FakeSession([FakeResponse(200, {"products": [], "tokensLeft": 100})])
        clock = FakeClock()

        with pytest.raises(KeepaApiError):
            _client(session, clock).fetch_product(ASIN)

        assert session.request_count == 1

    def test_直前のトークン残量を保持する(self) -> None:
        session, clock = FakeSession([FakeResponse(200, OK_PAYLOAD)]), FakeClock()
        client = _client(session, clock)

        client.fetch_product(ASIN)

        assert client.tokens_left == 250
