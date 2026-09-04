from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from urllib.parse import quote

from src.domain.entities.rival_candidate import RANKING, RELATED, SEARCH

logger = logging.getLogger(__name__)

RANKING_BASE = "https://www.amazon.co.jp"
PRODUCT_BASE = f"{RANKING_BASE}/dp/"
SEARCH_BASE = f"{RANKING_BASE}/s?k="
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
SETTLE_MS = 3000
# Amazon は素の Chromium に「ショッピングを続ける」の中間ページを返す。
# 一度通過すれば Cookie が付くので、プロファイルを残して次回以降を軽くする
PROFILE_DIR = Path.home() / "Library/Caches/ms-playwright/research-amazon"
GATE_TEXT = "ショッピングを続ける"
DEFAULT_LIMIT = 12
SPONSORED_MARKS = ("スポンサー", "Sponsored")
SEARCH_CARD = 'div[data-asin][data-component-type="s-search-result"]'
# 「この商品に関連する商品」。同じ見出しのスポンサー枠は別 id なのでここには混ざらない
RELATED_ROOT = "#sims-simsContainer_feature_div_0"
# pd_zg_hrsr が最も細かいカテゴリのランキング。カテゴリIDは推測せずここから取る
RANKING_LINK = 'a[href*="/gp/bestsellers/"][href*="pd_zg_hrsr"]'
RANKING_CARD = '[id^="gridItemRoot"]'


def product_url(asin: str) -> str:
    return PRODUCT_BASE + asin


def search_url(keyword: str) -> str:
    return SEARCH_BASE + quote(keyword)


def absolute_ranking_url(href: object) -> str | None:
    path = str(href or "").split("/ref=")[0].strip()
    if not path:
        return None
    if path.startswith("http"):
        return path
    return RANKING_BASE + path


def organic_ranks(
    cards: list[tuple[str, bool, str]], limit: int = DEFAULT_LIMIT
) -> list[dict]:
    seen: set[str] = set()
    items: list[dict] = []
    for asin, sponsored, title in cards:
        if sponsored or not asin or asin in seen:
            continue
        seen.add(asin)
        items.append({"rank": len(items) + 1, "asin": asin, "title": title})
        if len(items) >= limit:
            break
    return items


RELATED_SCRIPT = """(root) => {
  const el = document.querySelector(root);
  if (!el) return [];
  const seen = new Set();
  const out = [];
  for (const node of el.querySelectorAll('[data-asin]')) {
    const asin = node.getAttribute('data-asin');
    if (!asin || !/^[A-Z0-9]{10}$/.test(asin) || seen.has(asin)) continue;
    seen.add(asin);
    const img = node.querySelector('img[alt]');
    out.push({ rank: out.length + 1, asin, title: img ? img.alt : '' });
  }
  return out;
}"""

SEARCH_SCRIPT = """(selector) => {
  const out = [];
  for (const el of document.querySelectorAll(selector)) {
    out.push([
      el.getAttribute('data-asin') || '',
      el.innerText.slice(0, 200),
      ((el.querySelector('h2') || {}).innerText || '').trim()
    ]);
  }
  return out;
}"""

RANKING_SCRIPT = """(selector) => {
  const seen = new Set();
  const out = [];
  for (const card of document.querySelectorAll(selector)) {
    const link = card.querySelector('a[href*="/dp/"]');
    const matched = ((link && link.getAttribute('href')) || '').match(/\\/dp\\/([A-Z0-9]{10})/);
    if (!matched || seen.has(matched[1])) continue;
    seen.add(matched[1]);
    const badge = card.querySelector('.zg-bdg-text');
    const img = card.querySelector('img[alt]');
    out.push({
      rank: badge ? Number(badge.innerText.replace('#', '').trim()) : out.length + 1,
      asin: matched[1],
      title: img ? img.alt : ''
    });
  }
  return out;
}"""


class RivalScraper:
    """Amazon の3経路をブラウザで開いて、ライバル候補と画面上の順位を読む。

    SP-API の searchCatalogItems はカタログ検索順であって買い物客が見る並びではなく、
    商品ページの関連商品枠はそもそも API に存在しない。実画面を見るしかない。
    """

    def __init__(self, headless: bool = True, settle_ms: int = SETTLE_MS) -> None:
        self._headless = headless
        self._settle_ms = settle_ms

    async def collect(self, asin: str, keyword: str, limit: int = DEFAULT_LIMIT) -> dict:
        from playwright.async_api import async_playwright

        result: dict = {RELATED: [], SEARCH: [], RANKING: []}
        ranking_url: str | None = None

        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(PROFILE_DIR),
                headless=self._headless,
                locale="ja-JP",
                user_agent=USER_AGENT,
                viewport={"width": 1440, "height": 900},
            )
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                await self._goto(page, product_url(asin))
                result[RELATED] = (await page.evaluate(RELATED_SCRIPT, RELATED_ROOT))[:limit]
                link = page.locator(RANKING_LINK).first
                if await link.count():
                    ranking_url = absolute_ranking_url(await link.get_attribute("href"))

                if keyword:
                    await asyncio.sleep(2)
                    await self._goto(page, search_url(keyword))
                    cards = await page.evaluate(SEARCH_SCRIPT, SEARCH_CARD)
                    result[SEARCH] = organic_ranks(
                        [
                            (row[0], any(mark in row[1] for mark in SPONSORED_MARKS), row[2])
                            for row in cards
                        ],
                        limit=limit,
                    )

                if ranking_url:
                    await asyncio.sleep(2)
                    await self._goto(page, ranking_url)
                    result[RANKING] = (await page.evaluate(RANKING_SCRIPT, RANKING_CARD))[:limit]
            finally:
                await context.close()

        logger.info(
            "3経路を読みました",
            extra={
                "context": {
                    "asin": asin,
                    "keyword": keyword,
                    "ranking_url": ranking_url,
                    "counts": {name: len(rows) for name, rows in result.items()},
                }
            },
        )
        result["ranking_url"] = ranking_url
        return result

    async def _goto(self, page, url: str) -> None:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(self._settle_ms)

        # 中間ページはボタンを押すとトップへ飛ばされるので、通過後に目的の URL を開き直す
        gate = page.locator(f'button:has-text("{GATE_TEXT}")')
        if not await gate.count():
            return

        logger.info("中間ページを通過します", extra={"context": {"url": url}})
        await gate.first.click()
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(2000)
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(self._settle_ms)
