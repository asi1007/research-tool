import pytest

from src.domain.value_objects.asin import Asin
from src.infrastructure.spapi_client import SpApiClient, SpApiError

ASIN = Asin("B0CCX6ZXRV")


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)
        self.headers: dict[str, str] = {}

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls = 0

    def _next(self) -> FakeResponse:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response

    def get(self, url: str, **kwargs) -> FakeResponse:
        return self._next()

    def post(self, url: str, **kwargs) -> FakeResponse:
        return self._next()


class FakeClock:
    def __init__(self) -> None:
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


def _client(session: FakeSession, clock: FakeClock) -> SpApiClient:
    client = SpApiClient("rt", "cid", "secret", session=session, sleep=clock.sleep)
    client._access_token = "dummy"
    client._token_expiry = float("inf")
    return client


class TestThrottling:
    def test_429なら待って再試行する(self) -> None:
        session = FakeSession([FakeResponse(429), FakeResponse(200, {"attributes": {}})])
        clock = FakeClock()

        _client(session, clock).fetch_catalog_item(ASIN)

        assert session.calls == 2
        assert clock.slept == [1.0]

    def test_再試行のたびに待機時間を倍にする(self) -> None:
        session = FakeSession([FakeResponse(429), FakeResponse(429), FakeResponse(200, {})])
        clock = FakeClock()

        _client(session, clock).fetch_catalog_item(ASIN)

        assert clock.slept == [1.0, 2.0]

    def test_リトライ上限を超えたら例外を投げる(self) -> None:
        session, clock = FakeSession([FakeResponse(429)]), FakeClock()

        with pytest.raises(SpApiError):
            _client(session, clock).fetch_catalog_item(ASIN)

    def test_503も再試行の対象にする(self) -> None:
        session = FakeSession([FakeResponse(503), FakeResponse(200, {})])
        clock = FakeClock()

        _client(session, clock).fetch_catalog_item(ASIN)

        assert session.calls == 2

    def test_404は再試行せず例外を投げる(self) -> None:
        session, clock = FakeSession([FakeResponse(404)]), FakeClock()

        with pytest.raises(SpApiError):
            _client(session, clock).fetch_catalog_item(ASIN)

        assert session.calls == 1

    def test_手数料APIも429を再試行する(self) -> None:
        session = FakeSession([FakeResponse(429), FakeResponse(200, {"payload": {}})])
        clock = FakeClock()

        _client(session, clock).fetch_fees_estimate(ASIN, 749)

        assert session.calls == 2
