from __future__ import annotations

import json
import re

from src.domain.value_objects.asin import Asin
from src.domain.value_objects.supplier_skips import SupplierSkips
from src.usecases.select_supplier_targets import SupplierTarget

SKIP_PREFIX = "SKIP:"
EMPTY_CANDIDATES_REASON = "画像検索で候補が1件も出なかった"
# 1688 は累積アクセス量でキャプチャを出す。1回の自動実行はこの件数までにする
DEFAULT_BATCH = 5

_SKIP_LINE = re.compile(rf"^{re.escape(SKIP_PREFIX)}\s*(\S+)\s*(.*)$", re.MULTILINE)


def pick_batch(
    targets_by_sheet: dict[str, list[SupplierTarget]], skips: SupplierSkips, limit: int = DEFAULT_BATCH
) -> list[tuple[str, SupplierTarget]]:
    # 価格帯ごとに1件ずつ順に取る。1タブから固めて取ると安い帯だけが進む
    queues = {
        sheet: [target for target in targets if not skips.contains(target.asin)]
        for sheet, targets in targets_by_sheet.items()
    }
    batch: list[tuple[str, SupplierTarget]] = []
    while len(batch) < limit and any(queues.values()):
        for sheet, queue in queues.items():
            if not queue or len(batch) >= limit:
                continue
            batch.append((sheet, queue.pop(0)))
    return batch


def parse_skips(output: str) -> dict[str, str]:
    skips: dict[str, str] = {}
    for asin, reason in _SKIP_LINE.findall(output):
        parsed = Asin.parse(asin)
        if parsed is not None:
            skips[str(parsed)] = reason.strip()
    return skips


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL)
_BARE_JSON = re.compile(r"(\[\s*\{.*?\}\s*\])", re.DOTALL)


def _variant_lines(candidate: dict, limit: int = 12) -> str:
    variants = candidate.get("variants") or []
    if not variants:
        return "    規格表: 取れていない（カード価格だけ。価格を確定できないなら price を null にする）"
    rows = "\n".join(f"    - {v['spec']} ¥{v['price']}" for v in variants[:limit])
    more = "" if len(variants) <= limit else f"\n    - …ほか{len(variants) - limit}件"
    return rows + more


def build_decision_prompt(target: SupplierTarget, scraped: dict) -> str:
    blocks = []
    for candidate in scraped.get("candidates", [])[:6]:
        blocks.append(
            f"- offerId {candidate['offer_id']} / カード価格 ¥{candidate.get('card_price')}\n"
            f"    {candidate.get('title', '')}（{candidate.get('company', '')} {candidate.get('province', '')}）\n"
            + _variant_lines(candidate)
        )
    return (
        "1688 の画像検索の結果から、Amazon 側の商品と同じものを選んでください。\n"
        "**ブラウザは使いません。** 候補と規格表は下に貼ってあるものが全てです。\n\n"
        f"Amazon側: {target.asin} {target.title}\n\n"
        "候補:\n" + "\n".join(blocks) + "\n\n"
        "選び方:\n"
        "- 別カテゴリの商品しか無い、構成が違う、1688に同款が無いなら "
        f"`{SKIP_PREFIX} {target.asin} <理由>` の1行だけを返す\n"
        "- **次に当たるものは候補が見つかっても書かない。** 同じく SKIP を返す:\n"
        "  ブランド品・ライセンス品・認証品（MFi/PSE等）、生き物と植物、サービス・チケット、\n"
        "  名入れや印鑑のような受注生産品\n"
        "- 規格表が取れている候補を優先する。規格表の無い候補しか合わないときは price を null にする\n"
        "- カード価格は最安規格の値段で当てにならない。規格表の行から Amazon 側の構成に合うものを選ぶ\n"
        "- 構成が揃わない（付属品が別売りなど）ときは price を null にしてURLだけ残す\n"
        "- 1688が個数単価・Amazonがセットなら quantity にセットの入数を入れる。判断できなければ 1\n"
        "- spec は中国語の規格名をそのまま写す\n\n"
        "出力は次のJSON配列だけ（最大3件、1件目が本命）。説明は付けない:\n"
        '```json\n[{"offerId": "…", "spec": "…", "price": 9.46, "quantity": 1}]\n```'
    )


def skip_reason_for(scraped: dict) -> str | None:
    return None if scraped.get("candidates") else EMPTY_CANDIDATES_REASON


def looks_blocked(empty_count: int, found_count: int) -> bool:
    # 遮断された 1688 は結果0件を返す。1件も候補が出ていない実行では、
    # 「同款が無い」のか「遮断された」のか区別できないので飛ばす記録を残さない
    return found_count == 0 and empty_count > 0


def parse_decision(output: str) -> tuple[list[dict], str | None]:
    skips = parse_skips(output)
    if skips:
        return [], next(iter(skips.values())) or "理由なし"

    match = _JSON_BLOCK.search(output) or _BARE_JSON.search(output)
    if match is None:
        return [], "候補を選べなかった（出力にJSONが無い）"
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        return [], f"出力のJSONを読めない: {error}"
    if not isinstance(parsed, list) or not parsed:
        return [], "候補が空"
    return [item for item in parsed if isinstance(item, dict) and item.get("offerId")], None
