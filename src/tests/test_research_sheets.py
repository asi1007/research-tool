from src.domain.value_objects.research_sheets import (
    MARK_DESTINATION_SHEETS,
    candidate_sheets,
)


class TestCandidateSheets:
    ALL_SHEETS = [
        "リリース",
        "優先",
        "自動調査500円以下",
        "自動調査500円-700円",
        "1000円周辺",
        "単価1500~",
        "保留",
        "idea",
        "サンプル発注管理",
        "調査済み",
        "季節商品",
        "候補外",
        "テンプレ(新)",
    ]

    def test_価格帯を名乗らない候補タブも対象にする(self) -> None:
        assert candidate_sheets(self.ALL_SHEETS) == [
            "優先",
            "自動調査500円以下",
            "自動調査500円-700円",
            "1000円周辺",
            "単価1500~",
        ]

    def test_印の移動先は対象にしない(self) -> None:
        # 移した行をまた移すと無限に往復する
        assert candidate_sheets(list(MARK_DESTINATION_SHEETS)) == []

    def test_全角で書かれたタブ名でも対象外と判定する(self) -> None:
        assert candidate_sheets(["ｉｄｅａ", "テンプレ（新）"]) == []

    def test_タブの並び順を保つ(self) -> None:
        assert candidate_sheets(["単価2000~", "優先"]) == ["単価2000~", "優先"]
