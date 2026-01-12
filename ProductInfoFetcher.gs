class ProductInfo {
  constructor(data) {
    this.asin = data.asin || '';
    this.title = data.title || '';
    this.imageUrl = data.imageUrl || '';
    this.releaseDate = data.releaseDate || '';
    this.size = data.size || {};
    this.weight = data.weight || 0;
    this.salesCommission = data.salesCommission || 0;
    this.fbaFee = data.fbaFee || 0;
    this.buyBoxPrice = data.buyBoxPrice || 0;
  }

  toObject() {
    return {
      asin: this.asin,
      title: this.title,
      imageUrl: this.imageUrl,
      releaseDate: this.releaseDate,
      size: this.size,
      weight: this.weight,
      salesCommission: this.salesCommission,
      fbaFee: this.fbaFee,
      buyBoxPrice: this.buyBoxPrice
    };
  }
}

class KeepaClient {
  constructor(apiKey) {
    this.apiKey = apiKey;
    this.baseUrl = 'https://api.keepa.com';
  }

  fetchProductData(asin) {
    const url = `${this.baseUrl}/product?key=${this.apiKey}&domain=5&asin=${asin}&stats=1`;

    const options = {
      method: 'get',
      muteHttpExceptions: true
    };

    const response = UrlFetchApp.fetch(url, options);
    const statusCode = response.getResponseCode();

    if (statusCode !== 200) {
      throw new Error(`Keepa API error: ${statusCode} - ${response.getContentText()}`);
    }

    const data = JSON.parse(response.getContentText());

    if (!data.products || data.products.length === 0) {
      throw new Error(`Product not found: ${asin}`);
    }

    Logger.log('=== Keepa API レスポンス（販売数関連） ===');
    const product = data.products[0];
    Logger.log(`monthlySold: ${product.monthlySold}`);
    Logger.log(`stats: ${JSON.stringify(product.stats)}`);
    Logger.log(`salesRanks: ${JSON.stringify(product.salesRanks)}`);

    return data.products[0];
  }

  extractProductInfo(keepaData) {
    const product = keepaData;

    return {
      asin: product.asin || '',
      title: product.title || '',
      imageUrl: product.imagesCSV ? product.imagesCSV.split(',')[0] : '',
      releaseDate: this.convertKeepaTime(product.releaseDate),
      size: {
        length: product.packageLength || 0,
        width: product.packageWidth || 0,
        height: product.packageHeight || 0
      },
      weight: product.packageWeight || 0,
      buyBoxPrice: this.extractBuyBoxPrice(product)
    };
  }

  extractBuyBoxPrice(keepaData) {
    if (!keepaData.csv || !keepaData.csv[18]) {
      return null;
    }

    const buyBoxPriceHistory = keepaData.csv[18];

    if (buyBoxPriceHistory.length < 2) {
      return null;
    }

    const latestPrice = buyBoxPriceHistory[buyBoxPriceHistory.length - 1];

    if (latestPrice === -1) {
      return null;
    }

    return latestPrice / 100;
  }

  convertKeepaTime(keepaMinutes) {
    if (!keepaMinutes) return '';
    const keepaEpoch = new Date('2011-01-01T00:00:00Z').getTime();
    const timestamp = keepaEpoch + (keepaMinutes * 60 * 1000);
    return new Date(timestamp).toISOString().split('T')[0];
  }
}

class SpApiClient {
  constructor(config) {
    this.refreshToken = config.refreshToken;
    this.clientId = config.clientId;
    this.clientSecret = config.clientSecret;
    this.marketplaceId = 'A1VC38T7YXB528';
    this.accessToken = null;
    this.tokenExpiry = null;
    this.endpoint = 'https://sellingpartnerapi-fe.amazon.com';
    this.currency = 'JPY';
  }

  getAccessToken() {
    const now = new Date().getTime();

    if (this.accessToken && this.tokenExpiry && now < this.tokenExpiry) {
      return this.accessToken;
    }

    const tokenUrl = 'https://api.amazon.com/auth/o2/token';

    const payload = {
      grant_type: 'refresh_token',
      refresh_token: this.refreshToken,
      client_id: this.clientId,
      client_secret: this.clientSecret
    };

    const options = {
      method: 'post',
      payload: payload,
      muteHttpExceptions: true
    };

    const response = UrlFetchApp.fetch(tokenUrl, options);
    const statusCode = response.getResponseCode();

    if (statusCode !== 200) {
      throw new Error(`SP-API token error: ${statusCode} - ${response.getContentText()}`);
    }

    const data = JSON.parse(response.getContentText());
    this.accessToken = data.access_token;
    this.tokenExpiry = now + (data.expires_in * 1000) - 60000;

    return this.accessToken;
  }

  fetchCatalogItem(asin) {
    const accessToken = this.getAccessToken();
    const endpoint = `${this.endpoint}/catalog/2022-04-01/items/${asin}`;

    const params = [
      `marketplaceIds=${this.marketplaceId}`,
      'includedData=attributes,dimensions,images,productTypes,salesRanks'
    ].join('&');

    const url = `${endpoint}?${params}`;

    const options = {
      method: 'get',
      headers: {
        'x-amz-access-token': accessToken
      },
      muteHttpExceptions: true
    };

    const response = UrlFetchApp.fetch(url, options);
    const statusCode = response.getResponseCode();

    if (statusCode !== 200) {
      throw new Error(`SP-API catalog error: ${statusCode} - ${response.getContentText()}`);
    }

    return JSON.parse(response.getContentText());
  }

  fetchFeesEstimate(asin, price) {
    const accessToken = this.getAccessToken();
    const url = `${this.endpoint}/products/fees/v0/items/${asin}/feesEstimate`;

    const payload = {
      FeesEstimateRequest: {
        MarketplaceId: this.marketplaceId,
        PriceToEstimateFees: {
          ListingPrice: {
            CurrencyCode: this.currency,
            Amount: price
          }
        },
        Identifier: asin,
        IsAmazonFulfilled: true
      }
    };

    const options = {
      method: 'post',
      headers: {
        'x-amz-access-token': accessToken,
        'Content-Type': 'application/json'
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    };

    const response = UrlFetchApp.fetch(url, options);
    const statusCode = response.getResponseCode();

    if (statusCode !== 200) {
      throw new Error(`SP-API fees error: ${statusCode} - ${response.getContentText()}`);
    }

    return JSON.parse(response.getContentText());
  }

  extractProductInfo(catalogData) {
    const item = catalogData;
    const attributes = item.attributes || {};
    const dimensions = item.dimensions || [];
    const images = item.images || [];

    const packageDimension = dimensions.find(d => d.type === 'package') || {};

    return {
      title: attributes.item_name?.[0]?.value || '',
      imageUrl: images[0]?.images?.[0]?.link || '',
      releaseDate: attributes.release_date?.[0]?.value || '',
      size: {
        length: packageDimension.length?.value || 0,
        width: packageDimension.width?.value || 0,
        height: packageDimension.height?.value || 0,
        unit: packageDimension.length?.unit || 'centimeters'
      },
      weight: packageDimension.weight?.value || 0,
      weightUnit: packageDimension.weight?.unit || 'grams'
    };
  }

  extractFeesInfo(feesData) {
    const feesEstimate = feesData.payload?.FeesEstimate;

    if (!feesEstimate) {
      return {
        salesCommission: 0,
        fbaFee: 0
      };
    }

    const feeDetails = feesEstimate.FeeDetailList || [];

    let salesCommission = 0;
    let fbaFee = 0;

    feeDetails.forEach(fee => {
      if (fee.FeeType === 'ReferralFee') {
        salesCommission = fee.FeeAmount?.Amount || 0;
      } else if (fee.FeeType === 'FBAFees') {
        fbaFee = fee.FeeAmount?.Amount || 0;
      }
    });

    return {
      salesCommission: salesCommission,
      fbaFee: fbaFee
    };
  }
}

class ProductInfoFetcher {
  constructor(keepaApiKey, spApiConfig) {
    this.keepaClient = new KeepaClient(keepaApiKey);
    this.spApiClient = new SpApiClient(spApiConfig);
  }

  fetchProductInfo(asin, estimatedPrice = null) {
    let productData = {
      asin: asin,
      title: '',
      imageUrl: '',
      releaseDate: '',
      size: {},
      weight: 0,
      salesCommission: 0,
      fbaFee: 0,
      buyBoxPrice: 0
    };

    let buyBoxPrice = estimatedPrice;

    Logger.log('=== Keepa API 呼び出し開始 ===');
    try {
      const keepaData = this.keepaClient.fetchProductData(asin);
      Logger.log('Keepa API からのデータ取得成功');

      const keepaInfo = this.keepaClient.extractProductInfo(keepaData);
      Logger.log(`抽出した情報: ${JSON.stringify(keepaInfo)}`);

      productData.title = keepaInfo.title || productData.title;
      productData.imageUrl = keepaInfo.imageUrl || productData.imageUrl;
      productData.releaseDate = keepaInfo.releaseDate || productData.releaseDate;
      productData.size = keepaInfo.size || productData.size;
      productData.weight = keepaInfo.weight || productData.weight;

      if (keepaInfo.buyBoxPrice !== null) {
        buyBoxPrice = keepaInfo.buyBoxPrice;
        productData.buyBoxPrice = keepaInfo.buyBoxPrice;
        Logger.log(`カート価格取得: ${keepaInfo.buyBoxPrice}`);
      } else {
        Logger.log('カート価格がnullです');
      }
    } catch (error) {
      Logger.log(`Keepa API error for ${asin}: ${error.message}`);
      Logger.log(`エラー詳細: ${error.stack}`);
    }

    try {
      const catalogData = this.spApiClient.fetchCatalogItem(asin);
      const spInfo = this.spApiClient.extractProductInfo(catalogData);

      productData.title = productData.title || spInfo.title;
      productData.imageUrl = productData.imageUrl || spInfo.imageUrl;
      productData.releaseDate = productData.releaseDate || spInfo.releaseDate;
      productData.size = Object.keys(productData.size).length === 0 ? spInfo.size : productData.size;
      productData.weight = productData.weight || spInfo.weight;
    } catch (error) {
      Logger.log(`SP-API catalog error for ${asin}: ${error.message}`);
    }

    if (buyBoxPrice !== null && buyBoxPrice > 0) {
      try {
        const feesData = this.spApiClient.fetchFeesEstimate(asin, buyBoxPrice);
        const feesInfo = this.spApiClient.extractFeesInfo(feesData);

        productData.salesCommission = feesInfo.salesCommission;
        productData.fbaFee = feesInfo.fbaFee;
      } catch (error) {
        Logger.log(`SP-API fees error for ${asin}: ${error.message}`);
      }
    } else {
      Logger.log(`No buy box price available for ${asin}, skipping fees calculation`);
    }

    return new ProductInfo(productData);
  }

  fetchMultipleProducts(asins, estimatedPrice = 10.0) {
    const results = [];

    asins.forEach(asin => {
      try {
        const productInfo = this.fetchProductInfo(asin, estimatedPrice);
        results.push(productInfo);
        Utilities.sleep(1000);
      } catch (error) {
        Logger.log(`Error fetching product ${asin}: ${error.message}`);
        results.push(new ProductInfo({ asin: asin }));
      }
    });

    return results;
  }
}

function fetchAndWriteToSheet(asinColumnName) {
  const keepaApiKey = PropertiesService.getScriptProperties().getProperty('KEEPA_API_KEY');

  const spApiConfig = {
    refreshToken: PropertiesService.getScriptProperties().getProperty('SP_API_REFRESH_TOKEN'),
    clientId: PropertiesService.getScriptProperties().getProperty('SP_API_CLIENT_ID'),
    clientSecret: PropertiesService.getScriptProperties().getProperty('SP_API_CLIENT_SECRET')
  };

  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const activeRow = sheet.getActiveCell().getRow();
  const spreadsheetUrl = SpreadsheetApp.getActiveSpreadsheet().getUrl();
  const sheetName = sheet.getName();

  const reader = new SheetDataReader(spreadsheetUrl, sheetName);
  reader.loadHeaders();

  const fetcher = new ProductInfoFetcher(keepaApiKey, spApiConfig);

  const headerRow = reader.headerRow;
  const headers = reader.getHeaders();

  Logger.log('=== ヘッダー情報 ===');
  Logger.log(`ヘッダー行: ${headerRow}`);
  Logger.log(`ヘッダー一覧: ${headers.join(', ')}`);

  if (activeRow <= headerRow) {
    Logger.log('ヘッダ行が選択されています。データ行を選択してください。');
    return;
  }

  Logger.log(`アクティブ行: ${activeRow}`);

  const row = reader.loadRow(activeRow);

  Logger.log(`row存在チェック: ${row ? 'あり' : 'なし'}`);
  Logger.log(`row data: ${JSON.stringify(row ? row.toObject() : null)}`);

  if (!row) {
    Logger.log('選択された行にデータが存在しません。');
    return;
  }

  Logger.log(`ASIN列名: "${asinColumnName}"`);
  const rawAsin = row.get(asinColumnName);

  Logger.log(`ASIN列の値（生データ）: "${rawAsin}"`);
  Logger.log(`ASIN列の値の型: ${typeof rawAsin}`);

  if (!rawAsin || rawAsin === '') {
    Logger.log('ASIN が空です。');
    return;
  }

  const asin = String(rawAsin).trim().replace(/[^A-Z0-9]/gi, '').substring(0, 10);

  Logger.log(`クリーニング後のASIN: "${asin}"`);

  if (!asin || asin === '') {
    Logger.log('ASINをクリーニングした結果、空になりました。');
    return;
  }

  try {
    Logger.log(`ASIN ${asin} の情報を取得中...`);

    const productInfo = fetcher.fetchProductInfo(asin);

    Logger.log('=== 取得した商品情報 ===');
    Logger.log(`商品名: ${productInfo.title}`);
    Logger.log(`画像URL: ${productInfo.imageUrl}`);
    Logger.log(`発売日: ${productInfo.releaseDate}`);
    Logger.log(`カート価格: ${productInfo.buyBoxPrice}`);
    Logger.log(`サイズ: ${JSON.stringify(productInfo.size)}`);
    Logger.log(`重量: ${productInfo.weight}`);
    Logger.log(`販売手数料: ${productInfo.salesCommission}`);
    Logger.log(`配送代行手数料: ${productInfo.fbaFee}`);

    const amazonUrl = `https://www.amazon.co.jp/dp/${asin}`;
    const imageFormula = productInfo.imageUrl
      ? `=HYPERLINK("${amazonUrl}", IMAGE("${productInfo.imageUrl}"))`
      : '';

    const updateData = {
      '商品名': productInfo.title,
      '画像URL': imageFormula,
      '発売日': productInfo.releaseDate,
      'カート価格': productInfo.buyBoxPrice,
      'サイズ(長さ)': productInfo.size.length || '',
      'サイズ(幅)': productInfo.size.width || '',
      'サイズ(高さ)': productInfo.size.height || '',
      '重量': productInfo.weight,
      '販売手数料': productInfo.salesCommission,
      '配送代行手数料': productInfo.fbaFee
    };

    Logger.log('=== 書き込むデータ ===');
    Logger.log(JSON.stringify(updateData, null, 2));

    reader.updateRowByNumber(activeRow, updateData);

    Logger.log(`更新完了 - ${productInfo.title} (カート価格: $${productInfo.buyBoxPrice})`);

  } catch (error) {
    Logger.log(`エラー: ${error.message}`);
  }
}

