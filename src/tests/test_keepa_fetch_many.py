from src.domain.value_objects.asin import Asin
from src.infrastructure.keepa_client import KeepaClient


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class RecordingSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.params: list[dict] = []

    def get(self, url: str, params: dict, timeout: int) -> FakeResponse:
        self.params.append(params)
        return self.responses[min(len(self.params) - 1, len(self.responses) - 1)]


def _payload(asins: list[str]) -> dict:
    return {"products": [{"asin": asin, "monthlySold": 100, "csv": {18: [0, 1500]}} for asin in asins]}


class TestFetchProducts:
    def test_複数ASINを1リクエストでまとめて取る(self) -> None:
        session = RecordingSession([FakeResponse(200, _payload(["B000000001", "B000000002"]))])
        client = KeepaClient("key", session=session)

        products = client.fetch_products([Asin("B000000001"), Asin("B000000002")])

        assert len(session.params) == 1
        assert session.params[0]["asin"] == "B000000001,B000000002"
        assert [str(product.asin) for product in products] == ["B000000001", "B000000002"]
        assert products[0].buy_box_price == 1500
        assert products[0].monthly_sold == 100

    def test_上限を超えたら分割して取る(self) -> None:
        asins = [Asin(f"B{index:09d}") for index in range(101)]
        session = RecordingSession(
            [
                FakeResponse(200, _payload([str(asin) for asin in asins[:100]])),
                FakeResponse(200, _payload([str(asin) for asin in asins[100:]])),
            ]
        )
        client = KeepaClient("key", session=session)

        products = client.fetch_products(asins)

        assert len(session.params) == 2
        assert len(products) == 101

    def test_ASINが空なら問い合わせない(self) -> None:
        session = RecordingSession([])
        client = KeepaClient("key", session=session)

        assert client.fetch_products([]) == []
        assert session.params == []

    def test_返らなかったASINは黙って落とす(self) -> None:
        session = RecordingSession([FakeResponse(200, _payload(["B000000001"]))])
        client = KeepaClient("key", session=session)

        products = client.fetch_products([Asin("B000000001"), Asin("B000000002")])

        assert [str(product.asin) for product in products] == ["B000000001"]
