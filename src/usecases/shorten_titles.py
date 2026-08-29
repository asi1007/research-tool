from __future__ import annotations

import json
from dataclasses import dataclass

from src.infrastructure.column_codes import ColumnCodes

HEADER_ROWS = 3
MAX_SHORT_TITLE_LENGTH = 10
DEFAULT_BATCH_SIZE = 100

ASIN_CODE = "ASIN_SELL"
TITLE_SELL_CODE = "TITLE_SELL"
TITLE_BUY_CODE = "TITLE_BUY"


@dataclass(frozen=True)
class TitleTarget:
    sheet: str
    row_number: int
    title: str
    title_buy_column: int


def _cell(row: list, index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index]).strip()


def extract_targets(sheet_values: dict[str, list[list]]) -> list[TitleTarget]:
    targets: list[TitleTarget] = []

    for sheet_name, values in sheet_values.items():
        codes = ColumnCodes(values)
        asin_index = codes.index_of(ASIN_CODE)
        title_sell_index = codes.index_of(TITLE_SELL_CODE)
        title_buy_index = codes.index_of(TITLE_BUY_CODE)
        if asin_index is None or title_sell_index is None or title_buy_index is None:
            continue

        for offset, row in enumerate(values[HEADER_ROWS:]):
            title = _cell(row, title_sell_index)
            if not title:
                continue
            if _cell(row, title_buy_index):
                continue
            targets.append(
                TitleTarget(
                    sheet=sheet_name,
                    row_number=HEADER_ROWS + offset + 1,
                    title=title,
                    title_buy_column=title_buy_index,
                )
            )

    return targets


def chunk_targets(
    targets: list[TitleTarget], size: int = DEFAULT_BATCH_SIZE
) -> list[list[TitleTarget]]:
    return [targets[i : i + size] for i in range(0, len(targets), size)]


def build_prompt(titles: list[str]) -> str:
    lines = "\n".join(f"{index}: {title}" for index, title in enumerate(titles))
    return (
        "以下はECサイトの商品名の配列です。各商品名を全角10文字以内の短縮名にしてください。\n"
        "ルール:\n"
        "- 商品の実体が分かる名前にする\n"
        "- ブランド名・宣伝文句・型番・入数・記号は落とす\n"
        "- 記号や空白で埋めない\n"
        "- 出力は次のJSON配列のみ。説明文やコードフェンスは付けない\n"
        '[{"index": 0, "short_title": "..."}, ...]\n\n'
        "商品名一覧:\n"
        f"{lines}"
    )


@dataclass(frozen=True)
class BatchParseResult:
    short_titles: dict[int, str]
    error: str | None


def parse_batch_response(response_text: str, batch_size: int) -> BatchParseResult:
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as error:
        return BatchParseResult({}, f"JSONとして解析できません: {error}")

    if not isinstance(data, list):
        return BatchParseResult({}, f"配列ではありません: type={type(data).__name__}")

    if len(data) != batch_size:
        return BatchParseResult(
            {}, f"件数が一致しません: 期待{batch_size}件 実際{len(data)}件"
        )

    parsed: dict[int, str] = {}
    for item in data:
        if not isinstance(item, dict) or "index" not in item or "short_title" not in item:
            return BatchParseResult({}, f"要素の形式が不正です: {item!r}")

        index = item["index"]
        if not isinstance(index, int) or isinstance(index, bool) or not (0 <= index < batch_size):
            return BatchParseResult({}, f"indexが不正です: {index!r}")

        if index in parsed:
            return BatchParseResult({}, f"indexが重複しています: {index}")

        short_title = str(item["short_title"]).strip()
        if not short_title:
            return BatchParseResult({}, f"短縮名が空です: index={index}")
        if len(short_title) > MAX_SHORT_TITLE_LENGTH:
            return BatchParseResult(
                {}, f"10文字を超える短縮名が含まれています: index={index} value={short_title}"
            )

        parsed[index] = short_title

    if len(parsed) != batch_size:
        return BatchParseResult({}, "indexの抜けがあります")

    return BatchParseResult(parsed, None)


Updates = dict[str, dict[int, dict[int, object]]]


def build_updates(batch: list[TitleTarget], parsed: dict[int, str]) -> Updates:
    updates: Updates = {}
    for index, target in enumerate(batch):
        if index not in parsed:
            continue
        sheet_updates = updates.setdefault(target.sheet, {})
        row_updates = sheet_updates.setdefault(target.row_number, {})
        row_updates[target.title_buy_column] = parsed[index]
    return updates


def merge_updates(destination: Updates, source: Updates) -> None:
    for sheet_name, row_updates in source.items():
        sheet_destination = destination.setdefault(sheet_name, {})
        for row_number, column_updates in row_updates.items():
            row_destination = sheet_destination.setdefault(row_number, {})
            row_destination.update(column_updates)
