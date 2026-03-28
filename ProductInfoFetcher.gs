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
    this.monthlySold = data.monthlySold || 0;
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
      buyBoxPrice: this.buyBoxPrice,
      monthlySold: this.monthlySold
    };
  }
}

class InternationalShippingCalculator {
  constructor(ratePerKgCny, cnyToJpyRate) {
    this.ratePerKgCny = ratePerKgCny;
    this.cnyToJpyRate = cnyToJpyRate;
  }

  static fetchCnyToJpyRate() {
    const url = 'https://open.er-api.com/v6/latest/CNY';
    const response = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    if (response.getResponseCode() !== 200) {
      Logger.log('為替レート取得失敗、デフォルト値 21.0 を使用');
      return 21.0;
    }
    const data = JSON.parse(response.getContentText());
    return data.rates.JPY || 21.0;
  }

  calculate(lengthMm, widthMm, heightMm, weightGrams) {
    const volumetricWeightKg = (lengthMm / 10) * (widthMm / 10) * (heightMm / 10) / 5000;
    const actualWeightKg = weightGrams / 1000;
    const chargeableWeightKg = Math.max(volumetricWeightKg, actualWeightKg);
    const shippingCostCny = chargeableWeightKg * this.ratePerKgCny;
    return Math.round(shippingCostCny * this.cnyToJpyRate);
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

    return data.products[0];
  }

  extractProductInfo(keepaData) {
    const product = keepaData;

    // 発売日の取得（0や-1は無効な値として扱う）
    let releaseDate = '';

    if (product.releaseDate && product.releaseDate > 0) {
      releaseDate = this.convertKeepaTime(product.releaseDate);
    } else if (product.publicationDate && product.publicationDate > 0) {
      releaseDate = this.convertReleaseDateFormat(product.publicationDate);
    } else if (product.availabilityAmazon && product.availabilityAmazon > 0) {
      releaseDate = this.convertKeepaTime(product.availabilityAmazon);
    }
    // 上記すべて無効な場合は空文字列のまま（SP-APIから取得する）

    return {
      asin: product.asin || '',
      title: product.title || '',
      imageUrl: product.imagesCSV ? product.imagesCSV.split(',')[0] : '',
      releaseDate: releaseDate,
      size: {
        length: product.packageLength || 0,
        width: product.packageWidth || 0,
        height: product.packageHeight || 0
      },
      weight: product.packageWeight || 0,
      buyBoxPrice: this.extractBuyBoxPrice(product),
      monthlySold: product.monthlySold || 0
    };
  }

  convertReleaseDateFormat(dateValue) {
    if (!dateValue) return '';

    const dateStr = String(dateValue);
    // YYYYMMDD形式（例：20190523）をYYYY-MM-DDに変換
    if (dateStr.length === 8 && /^\d{8}$/.test(dateStr)) {
      const year = dateStr.substring(0, 4);
      const month = dateStr.substring(4, 6);
      const day = dateStr.substring(6, 8);
      return `${year}-${month}-${day}`;
    }

    return dateStr;
  }

  extractBuyBoxPrice(keepaData) {
    if (!keepaData.csv) {
      return null;
    }

    // csv[18]: Buy Box価格を優先
    if (keepaData.csv[18] && keepaData.csv[18].length >= 2) {
      const latestPrice = keepaData.csv[18][keepaData.csv[18].length - 1];
      if (latestPrice !== -1) {
        return latestPrice;
      }
    }

    // csv[1]: 新品価格をフォールバック
    if (keepaData.csv[1] && keepaData.csv[1].length >= 2) {
      const latestPrice = keepaData.csv[1][keepaData.csv[1].length - 1];
      if (latestPrice !== -1) {
        return latestPrice;
      }
    }

    // csv[0]: Amazon価格を最後のフォールバック
    if (keepaData.csv[0] && keepaData.csv[0].length >= 2) {
      const latestPrice = keepaData.csv[0][keepaData.csv[0].length - 1];
      if (latestPrice !== -1) {
        return latestPrice;
      }
    }

    return null;
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

    // 発売日の取得: street_date -> product_site_launch_date の順で試行
    let releaseDate = '';
    if (attributes.street_date?.[0]?.value) {
      // ISO 8601形式（例: "2019-03-11T08:00:01.000Z"）をYYYY-MM-DD形式に変換
      releaseDate = attributes.street_date[0].value.split('T')[0];
    } else if (attributes.product_site_launch_date?.[0]?.value) {
      releaseDate = attributes.product_site_launch_date[0].value.split('T')[0];
    }

    return {
      title: attributes.item_name?.[0]?.value || '',
      imageUrl: images[0]?.images?.[0]?.link || '',
      releaseDate: releaseDate,
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
    const feesEstimateResult = feesData.payload?.FeesEstimateResult;

    if (!feesEstimateResult || feesEstimateResult.Status !== 'Success') {
      Logger.log('Fees estimate failed or not available');
      return {
        salesCommission: 0,
        fbaFee: 0
      };
    }

    const feesEstimate = feesEstimateResult.FeesEstimate;
    const feeDetails = feesEstimate?.FeeDetailList || [];

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
      buyBoxPrice: 0,
      monthlySold: 0
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
      productData.monthlySold = keepaInfo.monthlySold || 0;

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
        Logger.log(`=== SP-API Fees APIリクエスト ===`);
        Logger.log(`ASIN: ${asin}, 価格: ${buyBoxPrice}`);

        const feesData = this.spApiClient.fetchFeesEstimate(asin, buyBoxPrice);
        Logger.log(`Fees APIレスポンス: ${JSON.stringify(feesData)}`);

        const feesInfo = this.spApiClient.extractFeesInfo(feesData);
        Logger.log(`抽出した手数料: 販売手数料=${feesInfo.salesCommission}, FBA手数料=${feesInfo.fbaFee}`);

        productData.salesCommission = feesInfo.salesCommission;
        productData.fbaFee = feesInfo.fbaFee;
      } catch (error) {
        Logger.log(`SP-API fees error for ${asin}: ${error.message}`);
        Logger.log(`エラー詳細: ${error.stack}`);
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
  const activeRange = sheet.getActiveRange();
  const spreadsheetUrl = SpreadsheetApp.getActiveSpreadsheet().getUrl();
  const sheetName = sheet.getName();

  const reader = new SheetDataReader(spreadsheetUrl, sheetName);
  reader.loadHeaders();

  const fetcher = new ProductInfoFetcher(keepaApiKey, spApiConfig);

  const cnyToJpyRate = InternationalShippingCalculator.fetchCnyToJpyRate();
  Logger.log(`CNY→JPY 為替レート: ${cnyToJpyRate}`);
  const shippingCalculator = new InternationalShippingCalculator(7, cnyToJpyRate);

  const headerRow = reader.headerRow;
  const headers = reader.getHeaders();

  Logger.log('=== ヘッダー情報 ===');
  Logger.log(`ヘッダー行: ${headerRow}`);
  Logger.log(`ヘッダー一覧: ${headers.join(', ')}`);

  // 選択範囲から処理対象の行を取得
  const startRow = activeRange.getRow();
  const numRows = activeRange.getNumRows();
  const targetRows = [];

  for (let i = 0; i < numRows; i++) {
    const rowNumber = startRow + i;
    if (rowNumber > headerRow) {
      targetRows.push(rowNumber);
    }
  }

  if (targetRows.length === 0) {
    Logger.log('ヘッダ行のみが選択されています。データ行を選択してください。');
    return;
  }

  Logger.log(`処理対象行数: ${targetRows.length}`);
  Logger.log(`対象行: ${targetRows.join(', ')}`);

  // 各行を処理
  targetRows.forEach((rowNumber, index) => {
    Logger.log(`\n=== 行 ${rowNumber} の処理開始 (${index + 1}/${targetRows.length}) ===`);

    try {
      const row = reader.loadRow(rowNumber);

      if (!row) {
        Logger.log(`行 ${rowNumber}: データが存在しません。スキップします。`);
        return;
      }

      const rawAsin = row.get(asinColumnName);

      if (!rawAsin || rawAsin === '') {
        Logger.log(`行 ${rowNumber}: ASIN が空です。スキップします。`);
        return;
      }

      const asin = String(rawAsin).trim().replace(/[^A-Z0-9]/gi, '').substring(0, 10);

      if (!asin || asin === '') {
        Logger.log(`行 ${rowNumber}: ASINをクリーニングした結果、空になりました。スキップします。`);
        return;
      }

      Logger.log(`行 ${rowNumber}: ASIN ${asin} の情報を取得中...`);

      const productInfo = fetcher.fetchProductInfo(asin);

      Logger.log(`行 ${rowNumber}: 商品名: ${productInfo.title}`);
      Logger.log(`行 ${rowNumber}: カート価格: ${productInfo.buyBoxPrice}`);

      const amazonUrl = `https://www.amazon.co.jp/dp/${asin}`;
      let imageFormula = '';
      if (productInfo.imageUrl) {
        const fullImageUrl = productInfo.imageUrl.startsWith('http')
          ? productInfo.imageUrl
          : `https://m.media-amazon.com/images/I/${productInfo.imageUrl}`;
        imageFormula = `=HYPERLINK("${amazonUrl}", IMAGE("${fullImageUrl}"))`;
      }

      const allUpdateData = {
        '商品名': productInfo.title,
        '画像URL': imageFormula,
        '発売日': productInfo.releaseDate,
        'カート価格': productInfo.buyBoxPrice,
        '数量': productInfo.monthlySold,
        'サイズ（長さ）': productInfo.size.length || '',
        'サイズ(幅)': productInfo.size.width || '',
        ' サイズ(高さ)': productInfo.size.height || '',
        '重量': productInfo.weight,
        '販売手数料': productInfo.salesCommission,
        '配送代行手数料（FBA手数料）': productInfo.fbaFee,
        '販売数/FBA数': productInfo.monthlySold,
        '国際送料': shippingCalculator.calculate(
          productInfo.size.length || 0,
          productInfo.size.width || 0,
          productInfo.size.height || 0,
          productInfo.weight || 0
        )
      };

      // 存在するヘッダのみに絞り込み
      const updateData = {};
      Object.keys(allUpdateData).forEach(headerName => {
        if (headers.includes(headerName)) {
          updateData[headerName] = allUpdateData[headerName];
        }
      });

      reader.updateRowByNumber(rowNumber, updateData);

      Logger.log(`行 ${rowNumber}: 更新完了 - ${productInfo.title}`);

      // API制限を考慮して待機（最後の行以外）
      if (index < targetRows.length - 1) {
        Logger.log('API制限を考慮して1秒待機...');
        Utilities.sleep(1000);
      }

    } catch (error) {
      Logger.log(`行 ${rowNumber}: エラー - ${error.message}`);
    }
  });

  Logger.log(`\n=== 処理完了 ===`);
  Logger.log(`処理した行数: ${targetRows.length}`);
}

