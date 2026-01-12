function getKeepaProductImage(asin) {
  const apiKey = 'enagpdulfn9a9i0k0idlmh1raqn85i04d6kcaq4hmqqp31ch0pk7man9to62q10u'; // ここに自身のAPIキーを入力
  const endpoint = 'https://api.keepa.com/product';
  // パラメータ設定
  const params = {
    method: 'get',
    muteHttpExceptions: true
  };
  // リクエストURL作成
  const url = `${endpoint}?key=${apiKey}&domain=5&asin=${asin}`;
  
  // APIリクエスト
  const response = UrlFetchApp.fetch(url, params);
  const json = JSON.parse(response.getContentText());
  if (json.error) throw new Error(json.error.message);

  // 商品情報取得
  const product = json.products[0];
  // imagesCSVから画像ファイル名を取得（カンマ区切り）
  const imagesCSV = product.imagesCSV;
  if (!imagesCSV) throw new Error('画像情報が取得できませんでした');
  // 最初の画像ファイル名を利用
  const imageUrls = imagesCSV.split(',');
  //const imageUrl = `https://images-na.ssl-images-amazon.com/images/I/${firstImageFile}`;
  //return imageUrl;
  return imageUrls;
}

// 例：ASINを指定して画像URLを取得
function testGetImage() {

  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  const columnB = sheet.getRange("B:B").getValues(); // B列すべて取得
  const nonEmptyRows = columnB.filter(row => row[0] !== ""); // 空でない行だけ抽出
  const asins = nonEmptyRows.map(row => row[0])
  const urls=  asins.map(getKeepaProductImage)
  let i = 3
  for (const row of urls){
     sheet.getRange(i, 3, 1, row.length).setValues([row]);
     i= i+1
  }
  // A1セルを開始地点に配列を書き込む
}

