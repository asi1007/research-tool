from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field

from src.domain.value_objects.asin import Asin
from src.domain.value_objects.research_sheets import SEASONAL_SHEET
from src.domain.value_objects.seasonal_verdicts import SeasonalVerdicts
from src.infrastructure.column_codes import ColumnCodes
from src.usecases.shorten_titles import strip_code_fence

HEADER_ROWS = 3
ASIN_CODE = "ASIN_SELL"
TITLE_CODE = "TITLE_SELL"

# キーワードは Claude に判定させる候補を絞るためだけに使う。商品名には用途・対応機器の説明が
# 混ざるので（「毛布も洗える洗濯ネット」「ファンブレード用スポンジ」）、当たっただけでは移さない
# 夏物。冷房・冷却まわりは「冷蔵」「冷凍」と紛れるので、器具や用途まで含んだ語で拾う
SUMMER_KEYWORDS: tuple[str, ...] = (
    "日傘", "扇風機", "ファン", "冷感", "冷却プレート", "瞬間冷却", "ひんやり",
    "氷嚢", "氷のう", "保冷剤", "熱中症", "暑さ対策", "猛暑", "涼", "クーラー",
    "水着", "スイミング", "スイムゴーグル", "水中メガネ", "プール", "浮き輪",
    "うちわ", "虫よけ", "虫除け", "蚊取り", "蚊帳", "日焼け", "uvカット",
    "サンダル", "麦わら", "冷却タオル", "冷感タオル", "ネッククーラー",
)

# 冬物。既に季節商品タブへ入っているものに合わせる
WINTER_KEYWORDS: tuple[str, ...] = (
    "電熱", "ヒーター", "加熱パンツ", "湯たんぽ", "カイロ", "防寒", "あったか",
    "毛布", "こたつ", "加湿器", "結露", "雪かき", "スノー", "手袋", "マフラー",
)

SEASONAL_KEYWORDS: tuple[str, ...] = SUMMER_KEYWORDS + WINTER_KEYWORDS


def _normalize(title: str) -> str:
    return unicodedata.normalize("NFKC", title).lower()


def is_seasonal_title(title: str) -> bool:
    normalized = _normalize(title)
    if not normalized.strip():
        return False
    return any(_normalize(keyword) in normalized for keyword in SEASONAL_KEYWORDS)


def _cell(row: list, index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index]).strip()


@dataclass(frozen=True)
class SeasonalCandidate:
    row_number: int
    asin: str
    title: str


def seasonal_candidates(values: list[list]) -> list[SeasonalCandidate]:
    codes = ColumnCodes(values)
    asin_index = codes.index_of(ASIN_CODE)
    title_index = codes.index_of(TITLE_CODE)
    if asin_index is None or title_index is None:
        return []

    candidates: list[SeasonalCandidate] = []
    for offset, row in enumerate(values[HEADER_ROWS:]):
        asin = Asin.parse(_cell(row, asin_index))
        title = _cell(row, title_index)
        if asin is None or not is_seasonal_title(title):
            continue
        candidates.append(SeasonalCandidate(HEADER_ROWS + offset + 1, str(asin), title))
    return candidates


def rows_to_move(candidates: list[SeasonalCandidate], verdicts: SeasonalVerdicts) -> list[int]:
    return [
        candidate.row_number
        for candidate in candidates
        if verdicts.is_seasonal(candidate.asin) is True
    ]


def build_judge_prompt(titles: list[str]) -> str:
    lines = "\n".join(f"{index}: {' '.join(title.split())}" for index, title in enumerate(titles))
    return (
        "以下は日本の Amazon で売られている商品名の配列です。各商品が「季節商品」かを判定してください。\n"
        "季節商品とは、夏または冬のどちらかの季節にしか需要がなく、季節外れにはほとんど売れない商品です。\n"
        "例: 日傘、ハンディファン、冷感タオル、氷嚢、浮き輪、水着、水泳帽、スイムゴーグル、プールバッグ、"
        "電熱ベスト、湯たんぽ、カイロ\n"
        "次は季節商品ではありません:\n"
        "- 季節の語が、用途・対応機器・使える場面の説明として書かれているだけの商品\n"
        "  例: 毛布も洗える洗濯ネット、ファンブレードの掃除用スポンジ、プールの水質検査にも使えるPH試験紙、"
        "加湿器等に対応したUSBケーブル、熱中症の目安を表示する温湿度計、本に貼るUVカットフィルム\n"
        "- 一年を通して使う商品\n"
        "出力は次のJSON配列のみ。説明文やコードフェンスは付けない\n"
        '[{"index": 0, "seasonal": true}, ...]\n\n'
        "商品名一覧:\n"
        f"{lines}"
    )


@dataclass(frozen=True)
class JudgeParseResult:
    verdicts: dict[int, bool] = field(default_factory=dict)
    error: str | None = None


def parse_judge_response(response_text: str, batch_size: int) -> JudgeParseResult:
    try:
        data = json.loads(strip_code_fence(response_text))
    except json.JSONDecodeError as error:
        return JudgeParseResult(error=f"JSONとして解析できません: {error}")

    if not isinstance(data, list) or len(data) != batch_size:
        return JudgeParseResult(error=f"{batch_size}件の配列ではありません")

    verdicts: dict[int, bool] = {}
    for item in data:
        index = item.get("index") if isinstance(item, dict) else None
        seasonal = item.get("seasonal") if isinstance(item, dict) else None
        valid_index = isinstance(index, int) and not isinstance(index, bool) and 0 <= index < batch_size
        if not valid_index or not isinstance(seasonal, bool) or index in verdicts:
            return JudgeParseResult(error=f"要素の形式が不正です: {item!r}")
        verdicts[index] = seasonal

    return JudgeParseResult(verdicts=verdicts)
