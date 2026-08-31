from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from src.domain.value_objects.asin import Asin
from src.infrastructure.column_codes import ColumnCodes

HEADER_ROWS = 3
MAX_SHORT_TITLE_LENGTH = 10
DEFAULT_BATCH_SIZE = 100

ASIN_CODE = "ASIN_SELL"
TITLE_SELL_CODE = "TITLE_SELL"
TITLE_BUY_CODE = "TITLE_BUY"

REASON_TOO_LONG = f"短縮名が{MAX_SHORT_TITLE_LENGTH}文字を超えています"
REASON_EMPTY = "短縮名が空です"
REASON_NOT_A_STRING = "not_a_string"


@dataclass(frozen=True)
class TitleTarget:
    sheet: str
    row_number: int
    title: str
    title_buy_column: int
    asin: str = ""


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
                    asin=_cell(row, asin_index),
                )
            )

    return targets


def chunk_targets(
    targets: list[TitleTarget], size: int = DEFAULT_BATCH_SIZE
) -> list[list[TitleTarget]]:
    return [targets[i : i + size] for i in range(0, len(targets), size)]


def _sanitize_for_prompt(title: str) -> str:
    return " ".join(title.split())


def build_prompt(titles: list[str]) -> str:
    lines = "\n".join(
        f"{index}: {_sanitize_for_prompt(title)}" for index, title in enumerate(titles)
    )
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
class DroppedItem:
    index: int
    short_title: str
    reason: str


@dataclass(frozen=True)
class BatchParseResult:
    short_titles: dict[int, str]
    error: str | None
    dropped: list[DroppedItem] = field(default_factory=list)


_CODE_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_+-]*\s*\n?(.*?)\n?```$", re.DOTALL)


def strip_code_fence(text: str) -> str:
    stripped = text.strip()
    match = _CODE_FENCE_RE.match(stripped)
    if match is None:
        return stripped
    return match.group(1).strip()


def parse_batch_response(response_text: str, batch_size: int) -> BatchParseResult:
    try:
        data = json.loads(strip_code_fence(response_text))
    except json.JSONDecodeError as error:
        return BatchParseResult({}, f"JSONとして解析できません: {error}")

    if not isinstance(data, list):
        return BatchParseResult({}, f"配列ではありません: type={type(data).__name__}")

    if len(data) != batch_size:
        return BatchParseResult(
            {}, f"件数が一致しません: 期待{batch_size}件 実際{len(data)}件"
        )

    parsed: dict[int, str] = {}
    dropped: list[DroppedItem] = []
    seen_indexes: set[int] = set()

    for item in data:
        if not isinstance(item, dict) or "index" not in item or "short_title" not in item:
            return BatchParseResult({}, f"要素の形式が不正です: {item!r}")

        index = item["index"]
        if not isinstance(index, int) or isinstance(index, bool) or not (0 <= index < batch_size):
            return BatchParseResult({}, f"indexが不正です: {index!r}")

        if index in seen_indexes:
            return BatchParseResult({}, f"indexが重複しています: {index}")
        seen_indexes.add(index)

        raw_short_title = item["short_title"]
        if not isinstance(raw_short_title, str):
            dropped.append(
                DroppedItem(index=index, short_title=repr(raw_short_title), reason=REASON_NOT_A_STRING)
            )
            continue

        short_title = raw_short_title.strip()
        if not short_title:
            dropped.append(DroppedItem(index=index, short_title=short_title, reason=REASON_EMPTY))
            continue
        if len(short_title) > MAX_SHORT_TITLE_LENGTH:
            dropped.append(DroppedItem(index=index, short_title=short_title, reason=REASON_TOO_LONG))
            continue

        parsed[index] = short_title

    if len(seen_indexes) != batch_size:
        return BatchParseResult({}, "indexの抜けがあります")

    return BatchParseResult(parsed, None, dropped)


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


@dataclass(frozen=True)
class RelocateResult:
    targets: list[TitleTarget]
    lost_indexes: set[int]


def _rows_by_key(values: list[list], key_of: Callable[[list], str | None]) -> dict[str, list[int]]:
    rows: dict[str, list[int]] = {}

    for offset, row in enumerate(values[HEADER_ROWS:]):
        key = key_of(row)
        if not key:
            continue
        rows.setdefault(key, []).append(HEADER_ROWS + offset + 1)

    return rows


def relocate_batch(batch: list[TitleTarget], values: list[list]) -> RelocateResult:
    # 読み取りから書き込みまでの間に行が挿入・削除されると行番号がずれるため、
    # 書き込む直前に ASIN で引き直す。合致しない対象は書かずに次回へ回す。
    codes = ColumnCodes(values)
    asin_index = codes.index_of(ASIN_CODE)
    title_buy_index = codes.index_of(TITLE_BUY_CODE)
    if asin_index is None or title_buy_index is None:
        return RelocateResult(targets=batch, lost_indexes=set(range(len(batch))))

    title_sell_index = codes.index_of(TITLE_SELL_CODE)
    rows_by_asin = _rows_by_key(values, lambda row: _parsed_asin(_cell(row, asin_index)))
    rows_by_title = _rows_by_key(values, lambda row: _cell(row, title_sell_index))
    relocated: list[TitleTarget] = []
    lost_indexes: set[int] = set()

    for index, target in enumerate(batch):
        row_number = _unique_row(target, rows_by_asin, rows_by_title)
        if row_number is None or not _is_writable(values, row_number, title_buy_index):
            lost_indexes.add(index)
            relocated.append(target)
            continue
        relocated.append(replace(target, row_number=row_number, title_buy_column=title_buy_index))

    return RelocateResult(targets=relocated, lost_indexes=lost_indexes)


def _parsed_asin(value: str) -> str | None:
    asin = Asin.parse(value)
    return None if asin is None else str(asin)


def _unique_row(
    target: TitleTarget,
    rows_by_asin: dict[str, list[int]],
    rows_by_title: dict[str, list[int]],
) -> int | None:
    # ASIN が引ければ ASIN で、無い行（手入力タブ）は商品名で引く。どちらも一意でなければ書かない
    asin = _parsed_asin(target.asin)
    rows = rows_by_asin.get(asin, []) if asin else rows_by_title.get(target.title, [])
    if len(rows) != 1:
        return None
    return rows[0]


def _is_writable(values: list[list], row_number: int, title_buy_index: int) -> bool:
    row = values[row_number - 1]
    return not _cell(row, title_buy_index)
