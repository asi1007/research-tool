function usecaseSheetDataReader() {
  const url = 'https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit';
  const sheetName = 'シート1';
  const headerRow = 1;

  const reader = new SheetDataReader(url, sheetName, headerRow);

  const rows = reader.getRows();

  rows.forEach((row, index) => {
    Logger.log(`行 ${index + 1}:`);
    Logger.log(`  名前: ${row.get('名前')}`);
    Logger.log(`  年齢: ${row.get('年齢')}`);
    Logger.log(`  メール: ${row.get('メール')}`);
  });

  const firstRow = reader.getRow(0);
  if (firstRow) {
    Logger.log(`最初の行の名前: ${firstRow.get('名前')}`);
  }

  const filtered = reader.filter(row => row.get('年齢') > 20);
  Logger.log(`20歳以上: ${filtered.length}人`);

  Logger.log(`ヘッダ: ${reader.getHeaders().join(', ')}`);
  Logger.log(`総行数: ${reader.getRowCount()}`);
}

function usecaseSheetDataReaderWrite() {
  const url = 'https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit';
  const sheetName = 'シート1';
  const reader = new SheetDataReader(url, sheetName);

  reader.updateRow(0, {
    '名前': '山田太郎',
    '年齢': 30
  });

  const newIndex = reader.addRow({
    '名前': '鈴木花子',
    '年齢': 25,
    'メール': 'hanako@example.com'
  });
  Logger.log(`新しい行が追加されました: インデックス ${newIndex}`);

  const newRows = [
    { '名前': '佐藤次郎', '年齢': 35, 'メール': 'jiro@example.com' },
    { '名前': '田中三郎', '年齢': 28, 'メール': 'saburo@example.com' }
  ];
  const addedIndices = reader.addRows(newRows);
  Logger.log(`${addedIndices.length}行が追加されました`);

  reader.setCellValue(0, '年齢', 31);

  reader.deleteRow(1);
  Logger.log('2行目が削除されました');
}

function usecaseProductInfoFetcher() {
  const keepaApiKey = PropertiesService.getScriptProperties().getProperty('KEEPA_API_KEY');

  const spApiConfig = {
    refreshToken: PropertiesService.getScriptProperties().getProperty('SP_API_REFRESH_TOKEN'),
    clientId: PropertiesService.getScriptProperties().getProperty('SP_API_CLIENT_ID'),
    clientSecret: PropertiesService.getScriptProperties().getProperty('SP_API_CLIENT_SECRET')
  };

  const fetcher = new ProductInfoFetcher(keepaApiKey, spApiConfig);

  const asin = 'B08N5WRWNW';

  const productInfo = fetcher.fetchProductInfo(asin);

  Logger.log('=== Product Information ===');
  Logger.log(`ASIN: ${productInfo.asin}`);
  Logger.log(`Title: ${productInfo.title}`);
  Logger.log(`Image URL: ${productInfo.imageUrl}`);
  Logger.log(`Release Date: ${productInfo.releaseDate}`);
  Logger.log(`Buy Box Price: $${productInfo.buyBoxPrice}`);
  Logger.log(`Size: ${JSON.stringify(productInfo.size)}`);
  Logger.log(`Weight: ${productInfo.weight}`);
  Logger.log(`Sales Commission: $${productInfo.salesCommission}`);
  Logger.log(`FBA Fee: $${productInfo.fbaFee}`);

  const asins = ['B08N5WRWNW', 'B07XJ8C8F5'];
  const products = fetcher.fetchMultipleProducts(asins);

  Logger.log('\n=== Multiple Products ===');
  products.forEach(product => {
    Logger.log(`${product.asin}: ${product.title}`);
  });
}

function usecaseFetchAndWrite() {
  const asinColumnName = 'ASIN';

  fetchAndWriteToSheet(asinColumnName);
}
