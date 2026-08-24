from src.infrastructure.candidate_parser import parse_candidates


def raw(offer_id: object, price: object = 0.03, quantity: object = None) -> dict:
    return {
        "offerId": offer_id,
        "title": "强力磁铁",
        "company": "雄尊磁铁厂",
        "province": "浙江",
        "price": price,
        "quantity": quantity,
    }


class TestParseCandidates:
    def test_上位3件を返す(self) -> None:
        items = [raw("1"), raw("2"), raw("3"), raw("4")]
        candidates = parse_candidates(items)
        assert [c.offer_id.value for c in candidates] == ["1", "2", "3"]

    def test_重複するofferIdを除外する(self) -> None:
        items = [raw("620082943880"), raw("620082943880"), raw("853573456382")]
        candidates = parse_candidates(items)
        assert [c.offer_id.value for c in candidates] == ["620082943880", "853573456382"]

    def test_offerIdが無い要素を除外する(self) -> None:
        candidates = parse_candidates([raw(None), raw("abc"), raw("620082943880")])
        assert [c.offer_id.value for c in candidates] == ["620082943880"]

    def test_価格が取れない場合はNoneにする(self) -> None:
        candidates = parse_candidates([raw("1", None), raw("2", "false"), raw("3", "")])
        assert [c.local_price for c in candidates] == [None, None, None]

    def test_文字列の価格を数値にする(self) -> None:
        candidates = parse_candidates([raw("1", "0.03")])
        assert candidates[0].local_price == 0.03

    def test_欠けている項目は空文字にする(self) -> None:
        candidates = parse_candidates([{"offerId": "620082943880"}])
        assert candidates[0].title == ""
        assert candidates[0].company == ""
        assert candidates[0].province == ""

    def test_空の入力なら空リストを返す(self) -> None:
        assert parse_candidates([]) == []

    def test_nanを価格に指定すると除外する(self) -> None:
        candidates = parse_candidates([raw("1", "nan")])
        assert candidates[0].local_price is None

    def test_infを価格に指定すると除外する(self) -> None:
        candidates = parse_candidates([raw("1", "inf")])
        assert candidates[0].local_price is None

    def test_負のinfを価格に指定すると除外する(self) -> None:
        candidates = parse_candidates([raw("1", "-inf")])
        assert candidates[0].local_price is None

    def test_float_nanが渡されるとNoneになる(self) -> None:
        candidates = parse_candidates([raw("1", float("nan"))])
        assert candidates[0].local_price is None

    def test_float_infが渡されるとNoneになる(self) -> None:
        candidates = parse_candidates([raw("1", float("inf"))])
        assert candidates[0].local_price is None

    def test_負のfloat_infが渡されるとNoneになる(self) -> None:
        candidates = parse_candidates([raw("1", float("-inf"))])
        assert candidates[0].local_price is None

    def test_混合型の入力は例外を出さず正常な要素だけ返す(self) -> None:
        items = [raw("1"), "broken_string", None, 42, raw("2")]
        candidates = parse_candidates(items)
        assert [c.offer_id.value for c in candidates] == ["1", "2"]

    def test_数量が正の整数ならそのまま使う(self) -> None:
        candidates = parse_candidates([raw("1", quantity=50)])
        assert candidates[0].quantity == 50

    def test_数量が数値文字列でも整数化する(self) -> None:
        candidates = parse_candidates([raw("1", quantity="50")])
        assert candidates[0].quantity == 50

    def test_数量が無い場合は1にする(self) -> None:
        candidates = parse_candidates([raw("1", quantity=None)])
        assert candidates[0].quantity == 1

    def test_数量がnullの場合は1にする(self) -> None:
        candidates = parse_candidates([{"offerId": "1", "quantity": None}])
        assert candidates[0].quantity == 1

    def test_数量が0の場合は1にする(self) -> None:
        candidates = parse_candidates([raw("1", quantity=0)])
        assert candidates[0].quantity == 1

    def test_数量が負の場合は1にする(self) -> None:
        candidates = parse_candidates([raw("1", quantity=-5)])
        assert candidates[0].quantity == 1

    def test_数量が非数値文字列の場合は1にする(self) -> None:
        candidates = parse_candidates([raw("1", quantity="fifty")])
        assert candidates[0].quantity == 1

    def test_数量が浮動小数の場合は1にする(self) -> None:
        candidates = parse_candidates([raw("1", quantity=2.5)])
        assert candidates[0].quantity == 1

    def test_数量がboolの場合は1にする(self) -> None:
        candidates = parse_candidates([raw("1", quantity=True)])
        assert candidates[0].quantity == 1

    def test_数量キーが無い場合は1にする(self) -> None:
        candidates = parse_candidates([{"offerId": "1"}])
        assert candidates[0].quantity == 1
