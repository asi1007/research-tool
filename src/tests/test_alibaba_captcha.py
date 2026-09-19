from src.infrastructure.alibaba_scraper import is_captcha

DETAIL_URL = "https://detail.1688.com/offer/713950986850.html"


class TestIsCaptcha:
    def test_遮断ページのURLで判定する(self) -> None:
        assert is_captcha("https://login.1688.com/_____tmd_____/punish?x5secdata=x", "") is True

    def test_遮断ページの言い回しで判定する(self) -> None:
        assert is_captcha(DETAIL_URL, "请完成验证后继续访问") is True
        assert is_captcha(DETAIL_URL, "滑动验证") is True

    def test_商品名の拦截器では止まらない(self) -> None:
        text = "厂家供应沙发底下玩具挡板 沙发床底阻滞器魔术贴固定绑带拦截器"
        assert is_captcha(DETAIL_URL, text) is False

    def test_通報案内の举报文でも止まらない(self) -> None:
        text = "如您发现店铺内有任何违法/侵权信息，请立即向阿里巴巴举报并提供有效线索。"
        assert is_captcha(DETAIL_URL, text) is False
