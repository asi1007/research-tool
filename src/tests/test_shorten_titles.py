from src.usecases.shorten_titles import (
    HEADER_ROWS,
    MAX_SHORT_TITLE_LENGTH,
    TitleTarget,
    build_prompt,
    build_updates,
    chunk_targets,
    extract_targets,
    parse_batch_response,
)

CODE_ROW = ["んh", "CHECK2", "ASIN_SELL", "JAN", "UPC", "IMAGE", "TITLE_SELL", "TITLE_BUY"]
LABEL_ROW = ["", "", "ASIN", "", "", "画像URL", "商品名", "商品名(BUY)"]
UNIT_ROW = ["0", "1", "", "", "", "", "", ""]


def _values(data_rows: list[list[str]]) -> list[list[str]]:
    return [CODE_ROW, LABEL_ROW, UNIT_ROW, *data_rows]


class TestExtractTargets:
    def test_商品名がありH列が空の行だけ拾う(self) -> None:
        values = _values(
            [
                ["B000000001", "", "", "", "", "", "対象商品"],
                ["B000000002", "", "", "", "", "", "既に短縮済み", "短縮済"],
                ["B000000003", "", "", "", "", "", ""],
            ]
        )

        targets = extract_targets({"シート1": values})

        assert len(targets) == 1
        assert targets[0] == TitleTarget(
            sheet="シート1", row_number=4, title="対象商品", title_buy_column=7
        )

    def test_H列に値がある行は除く(self) -> None:
        values = _values([["B000000001", "", "", "", "", "", "対象商品", "既存値"]])

        targets = extract_targets({"シート1": values})

        assert targets == []

    def test_商品名が無い行は除く(self) -> None:
        values = _values([["B000000001", "", "", "", "", "", ""]])

        targets = extract_targets({"シート1": values})

        assert targets == []

    def test_ASIN列が無いタブは無視する(self) -> None:
        values = [
            ["んh", "TITLE_SELL", "TITLE_BUY"],
            ["", "商品名", "商品名(BUY)"],
            ["", "", ""],
            ["対象商品", ""],
        ]

        targets = extract_targets({"シート1": values})

        assert targets == []

    def test_TITLE_BUY列が無いタブは無視する(self) -> None:
        values = [
            ["んh", "ASIN_SELL", "TITLE_SELL"],
            ["", "ASIN", "商品名"],
            ["", "", ""],
            ["B000000001", "対象商品"],
        ]

        targets = extract_targets({"シート1": values})

        assert targets == []

    def test_複数タブから集める(self) -> None:
        values_a = _values([["B000000001", "", "", "", "", "", "商品A"]])
        values_b = _values([["B000000002", "", "", "", "", "", "商品B"]])

        targets = extract_targets({"タブA": values_a, "タブB": values_b})

        assert [t.sheet for t in targets] == ["タブA", "タブB"]
        assert [t.title for t in targets] == ["商品A", "商品B"]

    def test_行番号はヘッダー行数を踏まえて計算する(self) -> None:
        values = _values(
            [
                ["B000000001", "", "", "", "", "", "1行目"],
                ["B000000002", "", "", "", "", "", "2行目"],
            ]
        )

        targets = extract_targets({"シート1": values})

        assert [t.row_number for t in targets] == [4, 5]


class TestChunkTargets:
    def test_指定件数ごとに分割する(self) -> None:
        targets = [
            TitleTarget(sheet="s", row_number=n, title=f"商品{n}", title_buy_column=7)
            for n in range(5)
        ]

        batches = chunk_targets(targets, size=2)

        assert [len(b) for b in batches] == [2, 2, 1]
        assert batches[0][0].row_number == 0
        assert batches[2][0].row_number == 4

    def test_空リストなら空になる(self) -> None:
        assert chunk_targets([], size=100) == []

    def test_サイズより少なければ1バッチになる(self) -> None:
        targets = [TitleTarget(sheet="s", row_number=1, title="商品", title_buy_column=7)]

        batches = chunk_targets(targets, size=100)

        assert len(batches) == 1
        assert len(batches[0]) == 1


class TestBuildPrompt:
    def test_商品名が本文に含まれる(self) -> None:
        prompt = build_prompt(["商品A", "商品B"])

        assert "商品A" in prompt
        assert "商品B" in prompt

    def test_JSON形式の指示が含まれる(self) -> None:
        prompt = build_prompt(["商品A"])

        assert "JSON" in prompt
        assert "index" in prompt
        assert "short_title" in prompt

    def test_商品名の改行は1行の番号付きリストが崩れないよう空白に潰す(self) -> None:
        prompt = build_prompt(["改行\n入り\n商品名", "商品B"])

        lines = prompt.splitlines()
        assert "0: 改行 入り 商品名" in lines
        assert "1: 商品B" in lines
        assert "\n入り" not in prompt

    def test_商品名のタブも空白に潰す(self) -> None:
        prompt = build_prompt(["タブ\t入り\t商品名"])

        assert "0: タブ 入り 商品名" in prompt.splitlines()

    def test_商品名の連続する空白は1つに詰める(self) -> None:
        prompt = build_prompt(["空白    多め   商品名"])

        assert "0: 空白 多め 商品名" in prompt.splitlines()


class TestParseBatchResponse:
    def test_正常な応答をパースできる(self) -> None:
        text = '[{"index": 0, "short_title": "商品A短"}, {"index": 1, "short_title": "商品B短"}]'

        result = parse_batch_response(text, batch_size=2)

        assert result.error is None
        assert result.short_titles == {0: "商品A短", 1: "商品B短"}

    def test_JSONでなければエラーになる(self) -> None:
        result = parse_batch_response("これはJSONではありません", batch_size=1)

        assert result.error is not None
        assert result.short_titles == {}

    def test_配列でなければエラーになる(self) -> None:
        result = parse_batch_response('{"index": 0, "short_title": "商品A"}', batch_size=1)

        assert result.error is not None

    def test_件数が合わなければエラーになる(self) -> None:
        text = '[{"index": 0, "short_title": "商品A"}]'

        result = parse_batch_response(text, batch_size=2)

        assert result.error is not None
        assert result.short_titles == {}

    def test_10文字を超える短縮名が混ざるとエラーになる(self) -> None:
        text = '[{"index": 0, "short_title": "12345678901"}]'

        result = parse_batch_response(text, batch_size=1)

        assert result.error is not None
        assert result.short_titles == {}

    def test_複数件のバッチで途中の1件だけ10文字超だとバッチ全体がエラーになる(self) -> None:
        text = (
            '[{"index": 0, "short_title": "商品A"}, '
            '{"index": 1, "short_title": "商品B"}, '
            '{"index": 2, "short_title": "12345678901"}, '
            '{"index": 3, "short_title": "商品D"}, '
            '{"index": 4, "short_title": "商品E"}]'
        )

        result = parse_batch_response(text, batch_size=5)

        assert result.error is not None
        assert result.short_titles == {}

    def test_複数件のバッチで正常ならすべて反映される(self) -> None:
        text = (
            '[{"index": 0, "short_title": "商品A"}, '
            '{"index": 1, "short_title": "商品B"}, '
            '{"index": 2, "short_title": "商品C"}, '
            '{"index": 3, "short_title": "商品D"}, '
            '{"index": 4, "short_title": "商品E"}]'
        )

        result = parse_batch_response(text, batch_size=5)

        assert result.error is None
        assert result.short_titles == {
            0: "商品A", 1: "商品B", 2: "商品C", 3: "商品D", 4: "商品E",
        }

    def test_10文字ちょうどは許容する(self) -> None:
        text = '[{"index": 0, "short_title": "1234567890"}]'

        result = parse_batch_response(text, batch_size=1)

        assert result.error is None
        assert result.short_titles == {0: "1234567890"}
        assert len("1234567890") == MAX_SHORT_TITLE_LENGTH

    def test_indexが重複するとエラーになる(self) -> None:
        text = '[{"index": 0, "short_title": "商品A"}, {"index": 0, "short_title": "商品B"}]'

        result = parse_batch_response(text, batch_size=2)

        assert result.error is not None

    def test_indexが範囲外だとエラーになる(self) -> None:
        text = '[{"index": 5, "short_title": "商品A"}]'

        result = parse_batch_response(text, batch_size=1)

        assert result.error is not None

    def test_短縮名が空文字だとエラーになる(self) -> None:
        text = '[{"index": 0, "short_title": ""}]'

        result = parse_batch_response(text, batch_size=1)

        assert result.error is not None

    def test_要素の形式が不正だとエラーになる(self) -> None:
        text = '["商品A"]'

        result = parse_batch_response(text, batch_size=1)

        assert result.error is not None

    def test_コードフェンス付きの応答はエラーになる(self) -> None:
        text = '```json\n[{"index": 0, "short_title": "商品A"}]\n```'

        result = parse_batch_response(text, batch_size=1)

        assert result.error is not None


class TestBuildUpdates:
    def test_バッチとパース結果から書き込み計画を作る(self) -> None:
        batch = [
            TitleTarget(sheet="タブA", row_number=4, title="商品A", title_buy_column=7),
            TitleTarget(sheet="タブB", row_number=10, title="商品B", title_buy_column=5),
        ]
        parsed = {0: "商品A短", 1: "商品B短"}

        updates = build_updates(batch, parsed)

        assert updates == {
            "タブA": {4: {7: "商品A短"}},
            "タブB": {10: {5: "商品B短"}},
        }

    def test_parsedに無いindexは書き込まない(self) -> None:
        batch = [TitleTarget(sheet="タブA", row_number=4, title="商品A", title_buy_column=7)]

        updates = build_updates(batch, {})

        assert updates == {}
