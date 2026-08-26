// 1688 商品ページの規格表（SKU テーブル）を読む。
//
// ページ本文を行単位で走査する方法は使えない。おすすめ商品も「名前 ¥価格」の形で
// 並んでいるため、規格ではなく別商品を拾ってしまう（2026-08-26 に実際に発生）。
//
// 価格セルは innerText を取ると価格と在庫が区切りなく連結される（"¥4.1999898"）。
// 葉ノードまで降りて ["¥4.1", "999898"] に分けてから価格だけを取る。
(() => {
  const box = [...document.querySelectorAll('[class*="sku"]')]
    .find(el => /规格型号/.test(el.innerText || '') && /¥/.test(el.innerText || ''));
  if (!box) return JSON.stringify({ error: 'sku-table-not-found' });

  const leafText = (el) =>
    [...el.querySelectorAll('*')]
      .filter(e => !e.children.length)
      .map(e => (e.innerText || e.textContent || '').trim())
      .filter(Boolean);

  const variants = [];
  for (const tr of box.querySelectorAll('tr, [class*="row"], [class*="item"]')) {
    const cells = [...tr.children];
    const priceCell = cells.find(c => /^¥/.test((c.innerText || '').trim()));
    if (!priceCell) continue;

    const priceLeaf = leafText(priceCell).find(t => /^¥/.test(t));
    const price = priceLeaf ? parseFloat(priceLeaf.replace(/[^\d.]/g, '')) : null;
    if (price === null || !isFinite(price)) continue;

    const spec = cells
      .filter(c => c !== priceCell)
      .map(c => (c.innerText || '').trim())
      .find(t => t && !/^¥/.test(t));
    if (!spec) continue;

    variants.push({ spec, price });
  }
  return JSON.stringify(variants);
})()
