from src.domain.value_objects.seasonal_verdicts import (
    DECIDED_BY_CLAUDE,
    DECIDED_BY_HUMAN,
    SeasonalVerdict,
    SeasonalVerdicts,
)
from src.infrastructure.seasonal_verdict_store import JsonSeasonalVerdictStore


class TestSeasonalVerdicts:
    def test_判定していないASINだけを返す(self) -> None:
        verdicts = SeasonalVerdicts({"B000000001": SeasonalVerdict(True, DECIDED_BY_CLAUDE)})

        assert verdicts.unjudged(["B000000001", "B000000002"]) == ["B000000002"]

    def test_判定していなければNone(self) -> None:
        assert SeasonalVerdicts().is_seasonal("B000000001") is None

    def test_Claudeの判定を記録する(self) -> None:
        verdicts = SeasonalVerdicts()

        verdicts.record_claude("B000000001", True)

        assert verdicts.is_seasonal("B000000001") is True

    def test_人の判断はClaudeの判定で上書きしない(self) -> None:
        # 人が季節商品から戻した行を、翌朝の定期実行でまた移さないため
        verdicts = SeasonalVerdicts()
        verdicts.record_human("B000000001", False)

        verdicts.record_claude("B000000001", True)

        assert verdicts.is_seasonal("B000000001") is False

    def test_人の判断はClaudeの判定を上書きする(self) -> None:
        verdicts = SeasonalVerdicts()
        verdicts.record_claude("B000000001", True)

        verdicts.record_human("B000000001", False)

        assert verdicts.is_seasonal("B000000001") is False


class TestJsonSeasonalVerdictStore:
    def test_保存したものを読み戻せる(self, tmp_path) -> None:
        store = JsonSeasonalVerdictStore(tmp_path / "verdicts.json")
        verdicts = SeasonalVerdicts()
        verdicts.record_claude("B000000001", True)
        verdicts.record_human("B000000002", False)

        store.save(verdicts)
        loaded = store.load()

        assert loaded.is_seasonal("B000000001") is True
        assert loaded.is_seasonal("B000000002") is False
        loaded.record_claude("B000000002", True)
        assert loaded.is_seasonal("B000000002") is False

    def test_ファイルが無ければ空(self, tmp_path) -> None:
        store = JsonSeasonalVerdictStore(tmp_path / "missing" / "verdicts.json")

        assert store.load().unjudged(["B000000001"]) == ["B000000001"]
