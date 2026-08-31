import pytest

from src.domain.value_objects.asin import Asin
from src.infrastructure.ads_client import AdsApiError, AmazonAdsClient


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
        self.calls: list[dict] = []

    def post(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now


TOKEN = FakeResponse(200, {"access_token": "token-1", "expires_in": 3600})
KEYWORDS = FakeResponse(200, {"keywordTargetList": [{"keyword": "x", "bidInfo": []}]})


def _client(session: FakeSession, clock: FakeClock | None = None) -> AmazonAdsClient:
    return AmazonAdsClient(
        client_id="id",
        client_secret="secret",
        refresh_token="refresh",
        profile_id="profile",
        session=session,
        clock=clock or FakeClock(),
    )


class TestFetchKeywordRecommendations:
    def test_トークンを取ってからASINで問い合わせる(self) -> None:
        session = FakeSession([TOKEN, KEYWORDS])

        payload = _client(session).fetch_keyword_recommendations(Asin("B000000001"))

        assert payload == {"keywordTargetList": [{"keyword": "x", "bidInfo": []}]}
        assert session.calls[0]["url"].endswith("/auth/o2/token")
        assert session.calls[1]["json"]["asins"] == ["B000000001"]
        assert session.calls[1]["headers"]["Amazon-Advertising-API-Scope"] == "profile"

    def test_トークンは期限内なら使い回す(self) -> None:
        session = FakeSession([TOKEN, KEYWORDS, KEYWORDS])
        client = _client(session)

        client.fetch_keyword_recommendations(Asin("B000000001"))
        client.fetch_keyword_recommendations(Asin("B000000002"))

        assert sum(1 for call in session.calls if call["url"].endswith("/auth/o2/token")) == 1

    def test_期限が切れたら取り直す(self) -> None:
        session = FakeSession([TOKEN, KEYWORDS, TOKEN, KEYWORDS])
        clock = FakeClock()
        client = _client(session, clock)

        client.fetch_keyword_recommendations(Asin("B000000001"))
        clock.now = 4000
        client.fetch_keyword_recommendations(Asin("B000000002"))

        assert sum(1 for call in session.calls if call["url"].endswith("/auth/o2/token")) == 2

    def test_エラーは例外にする(self) -> None:
        session = FakeSession([TOKEN, FakeResponse(429, {"code": "429"})])

        with pytest.raises(AdsApiError, match="429"):
            _client(session).fetch_keyword_recommendations(Asin("B000000001"))

    def test_リージョンが不正なら作れない(self) -> None:
        with pytest.raises(ValueError, match="region"):
            AmazonAdsClient("id", "secret", "refresh", "profile", region="JP")
