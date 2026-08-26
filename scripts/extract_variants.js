// 1688 商品ページの規格と価格を読む。レイアウトが2種類あるので両方に対応する。
//
//   A) 表形式   [class*="sku"] の中に 规格型号 の表がある（多規格の商品）
//   B) 選択形式 module-od-sku-selection に「規格名 / ¥価格 / 库存n个」が並ぶ（少規格の商品）
//
// ページ本文を行単位で走査する方法は使えない。おすすめ商品も「名前 ¥価格」の形で
// 並んでいるため、規格ではなく別商品を拾ってしまう（2026-08-26 に発生）。
//
// A の価格セルは innerText を取ると価格と在庫が区切りなく連結される（"¥4.1999898"）。
// 葉ノードまで降りて ["¥4.1", "999898"] に分けてから価格だけを取る。
(() => {
  const leafText = (el) =>
    [...el.querySelectorAll('*')]
      .filter(e => !e.children.length)
      .map(e => (e.innerText || e.textContent || '').trim())
      .filter(Boolean);

  const fromTable = () => {
    const box = [...document.querySelectorAll('[class*="sku"]')]
      .find(el => /规格型号/.test(el.innerText || '') && /¥/.test(el.innerText || ''));
    if (!box) return [];
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
      if (spec) variants.push({ spec, price });
    }
    return variants;
  };

  const fromSelection = () => {
    const box = document.querySelector('[class*="sku-selection"]');
    if (!box) return [];
    // 規格名の直後に ¥価格 が来る並びなので、価格行の1つ前を規格名として拾う。
    // 要素を限定しているため、おすすめ商品を巻き込む心配はない。
    const lines = (box.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
    const variants = [];
    for (let i = 1; i < lines.length; i++) {
      const m = lines[i].match(/^¥\s*([\d.]+)$/);
      if (!m) continue;
      const spec = lines[i - 1];
      if (!spec || /^¥/.test(spec) || spec === '规格') continue;
      const price = parseFloat(m[1]);
      if (isFinite(price)) variants.push({ spec, price });
    }
    return variants;
  };

  const variants = fromTable();
  return JSON.stringify(variants.length ? variants : fromSelection());
})()
