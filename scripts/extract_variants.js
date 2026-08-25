// 1688 の商品ページで実行し、サイズ（規格）別の価格一覧を JSON で返す。
// カードに出る価格は最安バリエーションのものなので、Amazon 側の商品サイズに
// 対応する価格を選ぶにはこの一覧が要る。
(() => {
  const LIMIT = 200;

  // 「規格名 ¥価格」が改行を挟んで並ぶ。規格名は F20*10*3mm / 20x10x3mm /
  // 直径3mm厚1mm など表記が揺れるため、¥ の直前の1行を規格名として拾う。
  function collect(text) {
    const lines = text.split('\n').map(s => s.trim()).filter(Boolean);
    const rows = [];

    for (let i = 0; i < lines.length && rows.length < LIMIT; i++) {
      const priceMatch = lines[i].match(/^¥\s*([\d.]+)$/);
      if (!priceMatch) continue;

      const spec = lines[i - 1];
      if (!spec || /^¥/.test(spec) || spec.length > 30) continue;

      rows.push({ spec, price: parseFloat(priceMatch[1]) });
    }
    return rows;
  }

  // 規格名から数値だけを取り出す。20*10*3mm → [20,10,3]
  function dimensions(spec) {
    return (spec.match(/\d+(?:\.\d+)?/g) || []).map(Number);
  }

  const rows = collect(document.body.innerText);
  const prices = rows.map(r => r.price);

  return JSON.stringify({
    count: rows.length,
    min: prices.length ? Math.min(...prices) : null,
    max: prices.length ? Math.max(...prices) : null,
    variants: rows.map(r => ({ spec: r.spec, price: r.price, dims: dimensions(r.spec) }))
  });
})()
