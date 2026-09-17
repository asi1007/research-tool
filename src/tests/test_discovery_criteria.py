from datetime import datetime, timezone

import pytest

from src.domain.value_objects.discovery_criteria import (
    EXCLUDED_BRANDS,
    EXCLUDED_MAKERS,
    EXCLUDED_CATEGORIES,
    EXCLUDED_ROOT_CATEGORIES,
    DiscoveryCriteria,
    to_keepa_minutes,
)

NOW = datetime(2026, 8, 29, 0, 0, tzinfo=timezone.utc)


class TestKeepaMinutes:
    def test_エポックからの経過分に変換する(self) -> None:
        assert to_keepa_minutes(datetime(2011, 1, 1, 0, 0, tzinfo=timezone.utc)) == 0
        assert to_keepa_minutes(datetime(2011, 1, 1, 1, 0, tzinfo=timezone.utc)) == 60


class TestSelection:
    def test_必須の3条件を組み立てる(self) -> None:
        selection = DiscoveryCriteria().selection(NOW)

        assert selection["current_NEW_gte"] == 1
        assert selection["current_NEW_lte"] == 1000
        assert selection["listedSince_gte"] == to_keepa_minutes(
            datetime(2025, 8, 29, 0, 0, tzinfo=timezone.utc)
        )

    def test_出品からの経過は1年以内(self) -> None:
        assert DiscoveryCriteria().max_age_days == 365

    def test_出品からの経過を延ばせる(self) -> None:
        selection = DiscoveryCriteria(max_age_days=1095).selection(NOW)

        assert selection["listedSince_gte"] == to_keepa_minutes(
            datetime(2023, 8, 30, 0, 0, tzinfo=timezone.utc)
        )

    def test_出品からの経過を問わないときは条件に入れない(self) -> None:
        selection = DiscoveryCriteria(max_age_days=None).selection(NOW)

        assert "listedSince_gte" not in selection

    def test_出品からの経過は1日以上(self) -> None:
        with pytest.raises(ValueError):
            DiscoveryCriteria(max_age_days=0)

    def test_月商50万円に必要な最低販売数をクエリに使う(self) -> None:
        # 1000円で50万円に届くには500個。この帯でこれ未満は価格が上限でも届かない
        assert DiscoveryCriteria().selection(NOW)["monthlySold_gte"] == 500

    def test_価格上限が高い帯ほど必要な販売数は少ない(self) -> None:
        criteria = DiscoveryCriteria(min_price_yen=1001, max_price_yen=2000)

        assert criteria.selection(NOW)["monthlySold_gte"] == 250

    def test_割り切れないときは切り上げる(self) -> None:
        criteria = DiscoveryCriteria(max_price_yen=3000, min_monthly_revenue_yen=500_000)

        assert criteria.selection(NOW)["monthlySold_gte"] == 167

    def test_月商が条件を満たすかを判定する(self) -> None:
        criteria = DiscoveryCriteria()

        assert criteria.meets_revenue(price_yen=1000, monthly_sold=500) is True
        assert criteria.meets_revenue(price_yen=999, monthly_sold=500) is False
        assert criteria.meets_revenue(price_yen=0, monthly_sold=10_000) is False

    def test_Amazon本体とバリエーション親を除外する(self) -> None:
        selection = DiscoveryCriteria().selection(NOW)

        assert selection["availabilityAmazon"] == [-1]
        assert selection["productType"] == [0]

    def test_ルート除外カテゴリは19件で本と食品を含む(self) -> None:
        assert len(EXCLUDED_ROOT_CATEGORIES) == 19
        assert 465392 in EXCLUDED_ROOT_CATEGORIES
        assert 57239051 in EXCLUDED_ROOT_CATEGORIES

    def test_化粧品を含むビューティーは除外する(self) -> None:
        assert 52374051 in EXCLUDED_ROOT_CATEGORIES

    def test_除外カテゴリはルートとサブを合わせたもの(self) -> None:
        assert set(EXCLUDED_ROOT_CATEGORIES) <= set(EXCLUDED_CATEGORIES)
        assert len(EXCLUDED_CATEGORIES) == len(EXCLUDED_ROOT_CATEGORIES) + 2

    def test_ポケモンカードを含むコレクションカードは除外する(self) -> None:
        assert 2189358051 in EXCLUDED_CATEGORIES

    def test_トレーディングカードゲームも除外する(self) -> None:
        assert 10345415051 in EXCLUDED_CATEGORIES

    def test_ホビーそのものは除外しない(self) -> None:
        assert 2277721051 not in EXCLUDED_CATEGORIES

    def test_パソコン周辺は除外しない(self) -> None:
        assert 2127209051 not in EXCLUDED_ROOT_CATEGORIES

    def test_月販の降順で取り出す(self) -> None:
        assert DiscoveryCriteria().selection(NOW)["sort"] == [["monthlySold", "desc"]]

    def test_ページ番号を差し替えられる(self) -> None:
        assert DiscoveryCriteria().selection(NOW, page=2)["page"] == 2
        assert DiscoveryCriteria().selection(NOW)["perPage"] == 50

    def test_perPageが50未満なら作れない(self) -> None:
        with pytest.raises(ValueError, match="perPage"):
            DiscoveryCriteria(per_page=10)


class TestPriceRange:
    def test_価格の下限を指定できる(self) -> None:
        selection = DiscoveryCriteria(min_price_yen=1001, max_price_yen=2000).selection(NOW)

        assert selection["current_NEW_gte"] == 1001
        assert selection["current_NEW_lte"] == 2000

    def test_下限が上限を超えるなら作れない(self) -> None:
        with pytest.raises(ValueError, match="価格"):
            DiscoveryCriteria(min_price_yen=2001, max_price_yen=2000)


class TestExcludedBrands:
    def test_1688に同款が無いブランドを持つ(self) -> None:
        lowered = {brand.lower() for brand in EXCLUDED_BRANDS}

        assert {"タカラトミー", "takara tomy", "オムロン", "omron", "コールマン", "coleman"} <= lowered


class TestExcludedMakers:
    def test_ユーザーが候補外にした有名ブランドを持つ(self) -> None:
        # 2026-09-17 に d を付けて候補外にしたもの
        lowered = {brand.lower() for brand in EXCLUDED_MAKERS}

        assert {"トンボ", "ゼブラ", "パイロット", "ぺんてる", "コクヨ", "パナソニック", "zippo", "エンスカイ", "ikea"} <= lowered

    def test_商品名で探すブランドとは重複させない(self) -> None:
        assert not {b.lower() for b in EXCLUDED_MAKERS} & {b.lower() for b in EXCLUDED_BRANDS}
