// Amazon の3経路からライバル候補（ASIN・商品名・順位）を読む。
// claude-in-chrome の javascript_tool でページごとに実行する。
//
//   related  … 商品ページ #sims-simsContainer_feature_div_0（「この商品に関連する商品」）
//   search   … 検索結果 div[data-component-type="s-search-result"]
//   ranking  … 売れ筋ランキング [id^="gridItemRoot"]
//
// 戻り値に URL を含めてはいけない（[BLOCKED: Cookie/query string data] でブロックされる）。

(() => {
  const MODE = 'related'; // related | search | ranking
  const LIMIT = 12;

  const related = () => {
    // スポンサー枠（#desktop-dp-sims_...）は別IDなので、この ID だけを見れば広告は混ざらない
    const root = document.querySelector('#sims-simsContainer_feature_div_0');
    if (!root) return [];
    const seen = new Set();
    const items = [];
    for (const el of root.querySelectorAll('[data-asin]')) {
      const asin = el.getAttribute('data-asin');
      if (!asin || !/^[A-Z0-9]{10}$/.test(asin) || seen.has(asin)) continue;
      seen.add(asin);
      const img = el.querySelector('img[alt]');
      items.push({ rank: items.length + 1, asin, title: (img ? img.alt : '').slice(0, 60) });
    }
    return items;
  };

  const search = () => {
    const items = [];
    let rank = 0;
    for (const el of document.querySelectorAll('div[data-component-type="s-search-result"][data-asin]')) {
      const asin = el.getAttribute('data-asin');
      if (!asin) continue;
      // 「スポンサー」表示は広告枠。オーガニックの順位を数えたいので除く
      if (/スポンサー|Sponsored/.test(el.innerText.slice(0, 200))) continue;
      rank += 1;
      if (rank > LIMIT) break;
      const heading = el.querySelector('h2');
      items.push({ rank, asin, title: ((heading && heading.innerText) || '').trim().slice(0, 60) });
    }
    return items;
  };

  const ranking = () => {
    const seen = new Set();
    const items = [];
    for (const card of document.querySelectorAll('[id^="gridItemRoot"]')) {
      const link = card.querySelector('a[href*="/dp/"]');
      const matched = (link ? link.getAttribute('href') : '').match(/\/dp\/([A-Z0-9]{10})/);
      if (!matched || seen.has(matched[1])) continue;
      seen.add(matched[1]);
      const badge = card.querySelector('.zg-bdg-text');
      const img = card.querySelector('img[alt]');
      items.push({
        rank: badge ? Number(badge.innerText.replace('#', '').trim()) : items.length + 1,
        asin: matched[1],
        title: (img ? img.alt : '').slice(0, 60)
      });
      if (items.length >= LIMIT) break;
    }
    return items;
  };

  const run = { related, search, ranking }[MODE];
  return JSON.stringify(run ? run() : []);
})()
