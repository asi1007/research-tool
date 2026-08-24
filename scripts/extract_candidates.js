// 1688 の画像検索結果ページで実行し、上位の仕入先候補を JSON で返す。
// 商品カードは React 要素でリンクを持たないため、内部状態から offerId を取る。
(() => {
  const LIMIT = 10;

  function findOffer(element) {
    const key = Object.keys(element).find(k => k.startsWith('__reactFiber$'));
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
  }

  function findPrice(element) {
    let node = element;
    for (let depth = 0; depth < 8 && node; depth++) {
      const innerText = node.innerText || '';
      const matches = innerText.match(/¥\s*\d+(?:\s*\.\d+)?/g);

      if (matches) {
        if (matches.length === 1) {
          // 1回だけ出現 → このカード固有の価格
          const captured = innerText.match(/¥\s*(\d+(?:\s*\.\d+)?)/)[1];
          return parseFloat(captured.replace(/\s/g, ''));
        } else if (matches.length >= 2) {
          // 2回以上出現 → 複数カードにまたがった
          return null;
        }
      }
      // matches.length === 0 or no matches → continue traversing
      node = node.parentElement;
    }
    return null;
  }

  const seen = new Set();
  const items = [];

  for (const image of document.querySelectorAll('img[src*="cbu01.alicdn.com"]')) {
    if (items.length >= LIMIT) break;

    const offer = findOffer(image);
    if (!offer || seen.has(String(offer.offerId))) continue;
    seen.add(String(offer.offerId));

    items.push({
      offerId: String(offer.offerId),
      title: String(offer.title || offer.subject || '').replace(/<[^>]*>/g, '').slice(0, 60),
      company: String(offer.companyName || offer.loginId || '').slice(0, 40),
      province: String(offer.province || ''),
      price: findPrice(image)
    });
  }

  return JSON.stringify(items);
})()
