/**
 * スプレッドシートの行データを表すクラス
 * ヘッダ名でデータにアクセス可能
 */
class SheetRow {
  /**
   * @param {string[]} headers - ヘッダ名の配列
   * @param {Array} rowData - データ行の配列
   */
  constructor(headers, rowData) {
    this.data = {};
    headers.forEach((header, index) => {
      this.data[header] = rowData[index];
    });
  }
  
  /**
   * ヘッダ名でデータを取得
   * @param {string} headerName - ヘッダ名
   * @return {*} セルの値
   */
  get(headerName) {
    return this.data[headerName];
  }
  
  /**
   * すべてのデータを取得
   * @return {Object} データオブジェクト
   */
  toObject() {
    return {...this.data};
  }
}

/**
 * スプレッドシートデータを読み込み、ヘッダ名でアクセスできるクラス
 */
class SheetDataReader {
  /**
   * @param {string} url - スプレッドシートのURL
   * @param {string} sheetName - シート名
   * @param {number} headerRow - ヘッダ行番号（1始まり、デフォルト: 1）
   */
  constructor(url, sheetName, headerRow = 1) {
    this.url = url;
    this.sheetName = sheetName;
    this.headerRow = headerRow;
    this.headers = [];
    this.rows = [];
    this.load();
  }
  
  /**
   * データを読み込む
   */
  load() {
    const spreadsheet = SpreadsheetApp.openByUrl(this.url);
    const sheet = spreadsheet.getSheetByName(this.sheetName);
    
    if (!sheet) {
      throw new Error(`シート "${this.sheetName}" が見つかりません`);
    }
    
    const lastRow = sheet.getLastRow();
    const lastColumn = sheet.getLastColumn();
    
    if (lastRow < this.headerRow) {
      throw new Error(`ヘッダ行 ${this.headerRow} がシートの範囲を超えています`);
    }
    
    // ヘッダを取得
    this.headers = sheet.getRange(this.headerRow, 1, 1, lastColumn).getValues()[0];
    
    // データ行を取得
    if (lastRow > this.headerRow) {
      const dataStartRow = this.headerRow + 1;
      const dataValues = sheet.getRange(dataStartRow, 1, lastRow - this.headerRow, lastColumn).getValues();
      
      this.rows = dataValues.map(rowData => new SheetRow(this.headers, rowData));
    }
  }
  
  /**
   * すべての行を取得
   * @return {SheetRow[]} 行の配列
   */
  getRows() {
    return this.rows;
  }
  
  /**
   * 指定したインデックスの行を取得
   * @param {number} index - 行インデックス（0始まり）
   * @return {SheetRow|null} 行オブジェクト
   */
  getRow(index) {
    return this.rows[index] || null;
  }
  
  /**
   * ヘッダ一覧を取得
   * @return {string[]} ヘッダ名の配列
   */
  getHeaders() {
    return [...this.headers];
  }
  
  /**
   * 行数を取得
   * @return {number} データ行数
   */
  getRowCount() {
    return this.rows.length;
  }
  
  /**
   * 条件に一致する行を検索
   * @param {function(SheetRow): boolean} predicate - 条件関数
   * @return {SheetRow[]} 一致した行の配列
   */
  filter(predicate) {
    return this.rows.filter(predicate);
  }
  
  /**
   * 各行に対して処理を実行
   * @param {function(SheetRow, number): void} callback - コールバック関数
   */
  forEach(callback) {
    this.rows.forEach(callback);
  }
}

// 使用例
function example() {
  // スプレッドシートのURL、シート名、ヘッダ行を指定
  const url = 'https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit';
  const sheetName = 'シート1';
  const headerRow = 1;
  
  // データを読み込む
  const reader = new SheetDataReader(url, sheetName, headerRow);
  
  // すべての行を取得
  const rows = reader.getRows();
  
  // 各行のデータにヘッダ名でアクセス
  rows.forEach((row, index) => {
    Logger.log(`行 ${index + 1}:`);
    Logger.log(`  名前: ${row.get('名前')}`);
    Logger.log(`  年齢: ${row.get('年齢')}`);
    Logger.log(`  メール: ${row.get('メール')}`);
  });
  
  // 特定の行を取得
  const firstRow = reader.getRow(0);
  if (firstRow) {
    Logger.log(`最初の行の名前: ${firstRow.get('名前')}`);
  }
  
  // 条件で絞り込み
  const filtered = reader.filter(row => row.get('年齢') > 20);
  Logger.log(`20歳以上: ${filtered.length}人`);
  
  // ヘッダ一覧を表示
  Logger.log(`ヘッダ: ${reader.getHeaders().join(', ')}`);
  
  // 行数を取得
  Logger.log(`総行数: ${reader.getRowCount()}`);
}
