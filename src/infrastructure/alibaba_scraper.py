from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

IMAGE_SEARCH_URL = "https://air.1688.com/kapp/1688-search/pc-image-search/?tab=imageSearch"
DETAIL_URL = "https://detail.1688.com/offer/{offer_id}.html"
# プロファイルは毎回使い捨てる。Cookie が溜まった状態で検索すると、キャプチャも
# エラーも出さずに結果0件を返してくる（2026-09-18 に同じ画像で10件→0件→新プロファイルで10件を確認）
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
# 規格表を開く候補の数。claude は3〜5位の候補を選ぶことがあり、少ないと価格の無い行になる
DEFAULT_VARIANT_OFFERS = 5
UPLOAD_SETTLE_MS = 9000
RESULT_SETTLE_MS = 10000
DETAIL_SETTLE_MS = 9000
# 「拦截」単体は商品名にも出る（沙发床底…拦截器）。遮断ページ特有の言い回しとURLで見る
CAPTCHA_PHRASES = ("验证码拦截", "滑动验证", "安全验证", "请完成验证", "访问异常")
CAPTCHA_URL_MARKERS = ("punish", "captcha", "_____tmd_____")

# 商品カードは React 要素でリンクを持たないため、内部状態から offerId を取る
CANDIDATES_JS = """
() => {
  const seen = new Set();
  const items = [];
  const findOffer = (element) => {
    const key = Object.keys(element).find((k) => k.startsWith('__reactFiber$'));
    if (!key) return null;
    let node = element[key];
    for (let depth = 0; depth < 12 && node; depth++) {
      const props = node.memoizedProps || node.pendingProps;
      if (props && typeof props === 'object') {
        for (const value of Object.values(props)) {
          if (value && typeof value === 'object' && value.offerId) return value;
        }
      }
      node = node.return;
    }
    return null;
  };
  const findPrice = (element) => {
    let node = element;
    for (let depth = 0; depth < 8 && node; depth++) {
      const matches = (node.innerText || '').match(/¥\\s*\\d+(?:\\s*\\.\\d+)?/g);
      if (matches && matches.length === 1) {
        return parseFloat(matches[0].replace(/[^\\d.]/g, ''));
      }
      if (matches && matches.length > 1) return null;
      node = node.parentElement;
    }
    return null;
  };
  for (const image of document.querySelectorAll('img[src*="cbu01.alicdn.com"]')) {
    if (items.length >= 10) break;
    const offer = findOffer(image);
    if (!offer || seen.has(String(offer.offerId))) continue;
    seen.add(String(offer.offerId));
    items.push({
      offer_id: String(offer.offerId),
      title: String(offer.title || offer.subject || '').replace(/<[^>]*>/g, '').slice(0, 60),
      company: String(offer.companyName || offer.loginId || '').slice(0, 40),
      province: String(offer.province || ''),
      card_price: findPrice(image),
    });
  }
  return items;
}
"""

# 規格表は3通りある。未ログインの選択形式（expand-view-item に item-price-stock が入る）を先に見る
VARIANTS_JS = """
() => {
  const leafText = (el) => [...el.querySelectorAll('*')]
    .filter((e) => !e.children.length)
    .map((e) => (e.innerText || e.textContent || '').trim())
    .filter(Boolean);
  const price = (text) => {
    const m = String(text || '').match(/¥\\s*([\\d.]+)/);
    return m ? parseFloat(m[1]) : null;
  };
  const fromExpandView = () => {
    const rows = [];
    for (const item of document.querySelectorAll('.expand-view-item')) {
      const priceNode = item.querySelector('.item-price-stock');
      if (!priceNode) continue;
      const spec = (item.innerText || '').replace(priceNode.innerText || '', '').trim().split('\\n')[0];
      const value = price(priceNode.innerText);
      if (spec && value !== null) rows.push({ spec, price: value });
    }
    return rows;
  };
  const fromTable = () => {
    const box = [...document.querySelectorAll('[class*="sku"]')]
      .find((el) => /规格型号/.test(el.innerText || '') && /¥/.test(el.innerText || ''));
    if (!box) return [];
    const rows = [];
    for (const tr of box.querySelectorAll('tr, [class*="row"], [class*="item"]')) {
      const cells = [...tr.children];
      const priceCell = cells.find((c) => /^¥/.test((c.innerText || '').trim()));
      if (!priceCell) continue;
      const leaf = leafText(priceCell).find((t) => /^¥/.test(t));
      const value = leaf ? price(leaf) : null;
      const spec = cells.filter((c) => c !== priceCell)
        .map((c) => (c.innerText || '').trim())
        .find((t) => t && !/^¥/.test(t));
      if (spec && value !== null) rows.push({ spec, price: value });
    }
    return rows;
  };
  const fromSelection = () => {
    const box = document.querySelector('[class*="sku-selection"]');
    if (!box) return [];
    const lines = (box.innerText || '').split('\\n').map((s) => s.trim()).filter(Boolean);
    const rows = [];
    for (let i = 1; i < lines.length; i++) {
      const value = price(lines[i]);
      if (value === null || !/^¥/.test(lines[i])) continue;
      const spec = lines[i - 1];
      if (!spec || /^¥/.test(spec) || spec === '规格') continue;
      rows.push({ spec, price: value });
    }
    return rows;
  };
  const expand = fromExpandView();
  if (expand.length) return expand;
  const table = fromTable();
  if (table.length) return table;
  return fromSelection();
}
"""


def is_captcha(url: str, text: str) -> bool:
    if any(marker in url for marker in CAPTCHA_URL_MARKERS):
        return True
    return any(phrase in text for phrase in CAPTCHA_PHRASES)


class CaptchaError(RuntimeError):
    """1688 がキャプチャを出した。人が通すまで先へ進めない。"""


async def _new_page(playwright, profile_dir: Path):
    context = await playwright.chromium.launch_persistent_context(
        str(profile_dir), headless=True, user_agent=USER_AGENT, locale="zh-CN"
    )
    page = context.pages[0] if context.pages else await context.new_page()
    return context, page


async def _raise_if_captcha(page) -> None:
    if is_captcha(page.url, await page.inner_text("body")):
        raise CaptchaError("1688 がキャプチャを出しました")


async def _search_by_image(page, image_path: Path) -> list[dict]:
    await page.goto(IMAGE_SEARCH_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(5000)
    await page.set_input_files("input[type=file]", str(image_path))
    await page.wait_for_timeout(UPLOAD_SETTLE_MS)
    await page.evaluate(
        "() => { const b = document.querySelector('div.search-btn');"
        " if (!b) return; for (const t of ['pointerdown','mousedown','pointerup','mouseup','click'])"
        " b.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, view:window})); }"
    )
    await page.wait_for_timeout(RESULT_SETTLE_MS)
    await _raise_if_captcha(page)
    return await page.evaluate(CANDIDATES_JS)


async def _fetch_variants(page, offer_id: str) -> list[dict]:
    await page.goto(DETAIL_URL.format(offer_id=offer_id), wait_until="domcontentloaded")
    await page.wait_for_timeout(DETAIL_SETTLE_MS)
    await _raise_if_captcha(page)
    return await page.evaluate(VARIANTS_JS)


async def _collect(image_path: Path, variant_offers: int) -> dict:
    from playwright.async_api import async_playwright

    with tempfile.TemporaryDirectory(prefix="research-1688-") as profile_dir:
        async with async_playwright() as playwright:
            context, page = await _new_page(playwright, Path(profile_dir))
            try:
                candidates = await _search_by_image(page, image_path)
                for candidate in candidates[:variant_offers]:
                    candidate["variants"] = await _fetch_variants(page, candidate["offer_id"])
                return {"candidates": candidates}
            finally:
                await context.close()


def collect(image_path: Path, variant_offers: int = DEFAULT_VARIANT_OFFERS) -> dict:
    return asyncio.run(_collect(image_path, variant_offers))
