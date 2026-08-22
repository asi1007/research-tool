const ASIN_BODY_PATTERN = /^[A-Z0-9]{10}$/;
const ASIN_IN_URL_PATTERN = /\/(?:dp|gp\/product|gp\/aw\/d|product)\/([A-Za-z0-9]{10})(?:[/?#]|$)/i;

class Asin {
  constructor(value) {
    this.value = value;
  }

  static parse(raw) {
    if (raw === null || raw === undefined) return null;

    const text = String(raw).normalize('NFKC').trim();
    if (text === '') return null;

    if (text.toLowerCase().indexOf('http') === 0) {
      return Asin.fromUrl_(text);
    }

    const candidate = text.toUpperCase();
    return ASIN_BODY_PATTERN.test(candidate) ? new Asin(candidate) : null;
  }

  static fromUrl_(url) {
    const matched = ASIN_IN_URL_PATTERN.exec(url);
    return matched ? new Asin(matched[1].toUpperCase()) : null;
  }

  get amazonUrl() {
    return `https://www.amazon.co.jp/dp/${this.value}`;
  }

  toString() {
    return this.value;
  }
}

function testAsinParse() {
  const cases = [
    ['B0CCX6ZXRV', 'B0CCX6ZXRV'],
    ['  B0CQ245KMT \n', 'B0CQ245KMT'],
    ['b0fs1xtj16', 'B0FS1XTJ16'],
    ['Ｂ０ＣＣＸ６ＺＸＲＶ', 'B0CCX6ZXRV'],
    ['https://www.amazon.co.jp/TARATI-%E8%B6%85/dp/B0H455Y954/ref=sr_1_18?dib=xxx&th=1', 'B0H455Y954'],
    ['https://www.amazon.co.jp/gp/product/B08N5WRWNW?psc=1', 'B08N5WRWNW'],
    ['https://www.amazon.co.jp/dp/B07XJ8C8F5?th=1', 'B07XJ8C8F5'],
    ['https://amzn.to/3xYzAbC', null],
    ['掃除グッズ　水垢とか', null],
    ['', null],
    ['B0CCX6ZX', null],
    ['B0CCX6ZXRVXX', null],
    ['B0CC-X6ZXR', null]
  ];

  let failed = 0;

  cases.forEach(([input, expected]) => {
    const parsed = Asin.parse(input);
    const actual = parsed ? parsed.value : null;
    if (actual !== expected) {
      failed += 1;
      Logger.log(`NG: parse(${JSON.stringify(input)}) = ${actual} (期待値: ${expected})`);
    }
  });

  Logger.log(failed === 0 ? `OK: ${cases.length}件すべて成功` : `NG: ${failed}件失敗`);
}
