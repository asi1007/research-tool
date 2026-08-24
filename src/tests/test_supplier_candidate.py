from src.domain.entities.supplier_candidate import SupplierCandidate
from src.domain.value_objects.offer_id import OfferId


class TestSupplierCandidate:
    def test_商品URLを組み立てる(self) -> None:
        candidate = SupplierCandidate(
            offer_id=OfferId("620082943880"),
            title="源头工厂钕铁硼强磁现货直发圆形磁铁",
            company="雄尊磁铁厂",
            province="浙江",
            local_price=0.03,
        )
        assert candidate.url == "https://detail.1688.com/offer/620082943880.html"

    def test_価格が不明でも生成できる(self) -> None:
        candidate = SupplierCandidate(
            offer_id=OfferId("853573456382"),
            title="现货钕铁硼强力圆形10*2磁铁",
            company="丽嘉磁业工厂",
            province="广东",
            local_price=None,
        )
        assert candidate.local_price is None
        assert candidate.url == "https://detail.1688.com/offer/853573456382.html"
