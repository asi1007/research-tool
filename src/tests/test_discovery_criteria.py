from datetime import datetime, timezone

import pytest

from src.domain.value_objects.discovery_criteria import (
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
        assert selection["monthlySold_gte"] == 1000
        assert selection["listedSince_gte"] == to_keepa_minutes(
            datetime(2026, 3, 2, 0, 0, tzinfo=timezone.utc)
        )

    def test_Amazon本体とバリエーション親を除外する(self) -> None:
        selection = DiscoveryCriteria().selection(NOW)

        assert selection["availabilityAmazon"] == [-1]
        assert selection["productType"] == [0]

    def test_除外カテゴリは18件で本と食品を含む(self) -> None:
        assert len(EXCLUDED_ROOT_CATEGORIES) == 18
        assert 465392 in EXCLUDED_ROOT_CATEGORIES
        assert 57239051 in EXCLUDED_ROOT_CATEGORIES

    def test_ビューティーとパソコン周辺は除外しない(self) -> None:
        assert 52374051 not in EXCLUDED_ROOT_CATEGORIES
        assert 2127209051 not in EXCLUDED_ROOT_CATEGORIES

    def test_月販の降順で取り出す(self) -> None:
        assert DiscoveryCriteria().selection(NOW)["sort"] == [["monthlySold", "desc"]]

    def test_ページ番号を差し替えられる(self) -> None:
        assert DiscoveryCriteria().selection(NOW, page=2)["page"] == 2
        assert DiscoveryCriteria().selection(NOW)["perPage"] == 50

    def test_perPageが50未満なら作れない(self) -> None:
        with pytest.raises(ValueError, match="perPage"):
            DiscoveryCriteria(per_page=10)
