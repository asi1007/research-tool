/**
 * スプレッドシートの行データを表すクラス
 * ASIN列のみを保持
 */
class SheetRow {
  /**
   * @param {string[]} headers - ヘッダ名の配列
   * @param {Array} rowData - データ行の配列
   */
  constructor(headers, rowData) {
    const asinIndex = headers.indexOf('ASIN');
    this.asin = asinIndex !== -1 ? rowData[asinIndex] : '';
  }

  /**
   * ヘッダ名でデータを取得
   * @param {string} headerName - ヘッダ名
   * @return {*} セルの値
   */
  get(headerName) {
    if (headerName === 'ASIN') {
      return this.asin;
    }
    return undefined;
  }

  /**
   * すべてのデータを取得
   * @return {Object} データオブジェクト
   */
  toObject() {
    return { ASIN: this.asin };
  }
}

/**
 * スプレッドシートデータを読み込み、ヘッダ名でアクセスできるクラス
 */
class SheetDataReader {
  /**
   * @param {string} url - スプレッドシートのURL
   * @param {string} sheetName - シート名
   * @param {number} headerRow - ヘッダ行番号（1始まり、デフォルト: 3）
   */
  constructor(url, sheetName, headerRow = 3) {
    this.url = url;
    this.sheetName = sheetName;
    this.headerRow = headerRow;
    this.headers = [];
    this.sheet = null;
  }
  
  /**
   * ヘッダーのみを読み込む
   */
  loadHeaders() {
    const spreadsheet = SpreadsheetApp.openByUrl(this.url);
    this.sheet = spreadsheet.getSheetByName(this.sheetName);

    if (!this.sheet) {
      throw new Error(`シート "${this.sheetName}" が見つかりません`);
    }

    const lastColumn = this.sheet.getLastColumn();

    // ヘッダを取得（3行目を取得）
    this.headers = this.sheet.getRange(this.headerRow, 1, 1, lastColumn).getValues()[0];

    // 3行目が空の場合は2行目の値を使用（結合セル対応）
    if (this.headerRow > 1) {
      const headerRowAbove = this.sheet.getRange(this.headerRow - 1, 1, 1, lastColumn).getValues()[0];

      this.headers = this.headers.map((header, index) => {
        if (header === '' || header === null || header === undefined) {
          return headerRowAbove[index] || '';
        }
        return header;
      });
    }
  }

  /**
   * 特定の行のみを読み込む
   * @param {number} rowNumber - 読み込む行番号（1始まり）
   * @return {SheetRow} 行オブジェクト
   */
  loadRow(rowNumber) {
    this.loadHeaders();
    if (rowNumber <= this.headerRow) {
      throw new Error(`行番号 ${rowNumber} はヘッダ行以下です`);
    }

    const lastColumn = this.sheet.getLastColumn();
    Logger.log(`loadRow: 行番号=${rowNumber}, 最終列=${lastColumn}`);

    const rowData = this.sheet.getRange(rowNumber, 1, 1, lastColumn).getValues()[0];
    Logger.log(`取得した行データ: ${JSON.stringify(rowData)}`);

    return new SheetRow(this.headers, rowData);
  }

  /**
   * データを読み込む（すべての行）
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

    // ヘッダを取得（3行目を取得）
    this.headers = sheet.getRange(this.headerRow, 1, 1, lastColumn).getValues()[0];

    // 3行目が空の場合は2行目の値を使用（結合セル対応）
    if (this.headerRow > 1) {
      const headerRowAbove = sheet.getRange(this.headerRow - 1, 1, 1, lastColumn).getValues()[0];

      this.headers = this.headers.map((header, index) => {
        if (header === '' || header === null || header === undefined) {
          return headerRowAbove[index] || '';
        }
        return header;
      });
    }

    // データ行を取得
    if (lastRow > this.headerRow) {
      const dataStartRow = this.headerRow + 1;
      Logger.log(`データ取得範囲: R${dataStartRow}C1:R${lastRow}C${lastColumn} （${lastRow - this.headerRow}行, ${lastColumn}列）`);
      const dataValues = sheet.getRange(dataStartRow, 1, lastRow - this.headerRow, lastColumn).getValues();
      Logger.log(`取得したデータ行数: ${dataValues.length}`);
      Logger.log('取得データの中身:');
      dataValues.forEach((row, idx) => {
        Logger.log(`  [${idx}] ${JSON.stringify(row)}`);
      });

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
    console.log(`getRow: ${index}`);
    console.log('this.rows: ' + JSON.stringify(this.rows[index].toObject()));
    return this.rows[index] ;
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

  /**
   * 指定した行番号のデータを更新
   * @param {number} rowNumber - 行番号（1始まり）
   * @param {Object} data - 更新するデータ（ヘッダ名: 値のオブジェクト）
   */
  updateRowByNumber(rowNumber, data) {
    if (!this.sheet) {
      const spreadsheet = SpreadsheetApp.openByUrl(this.url);
      this.sheet = spreadsheet.getSheetByName(this.sheetName);
    }

    if (!this.sheet) {
      throw new Error(`シート "${this.sheetName}" が見つかりません`);
    }

    if (rowNumber <= this.headerRow) {
      throw new Error(`行番号 ${rowNumber} はヘッダ行以下です`);
    }

    Object.keys(data).forEach(headerName => {
      const columnIndex = this.headers.indexOf(headerName);
      if (columnIndex === -1) {
        throw new Error(`ヘッダ "${headerName}" が見つかりません`);
      }

      const cell = this.sheet.getRange(rowNumber, columnIndex + 1);
      cell.setValue(data[headerName]);
    });
  }

  /**
   * 指定した行のデータを更新
   * @param {number} rowIndex - 行インデックス（0始まり）
   * @param {Object} data - 更新するデータ（ヘッダ名: 値のオブジェクト）
   */
  updateRow(rowIndex, data) {
    const spreadsheet = SpreadsheetApp.openByUrl(this.url);
    const sheet = spreadsheet.getSheetByName(this.sheetName);

    if (!sheet) {
      throw new Error(`シート "${this.sheetName}" が見つかりません`);
    }

    if (rowIndex < 0 || rowIndex >= this.rows.length) {
      throw new Error(`行インデックス ${rowIndex} が範囲外です`);
    }

    const actualRow = this.headerRow + 1 + rowIndex;

    Object.keys(data).forEach(headerName => {
      const columnIndex = this.headers.indexOf(headerName);
      if (columnIndex === -1) {
        throw new Error(`ヘッダ "${headerName}" が見つかりません`);
      }

      const cell = sheet.getRange(actualRow, columnIndex + 1);
      cell.setValue(data[headerName]);

      this.rows[rowIndex].data[headerName] = data[headerName];
    });
  }

  /**
   * 新しい行をシートの最後に追加
   * @param {Object} data - 追加するデータ（ヘッダ名: 値のオブジェクト）
   * @return {number} 追加された行のインデックス
   */
  addRow(data) {
    const spreadsheet = SpreadsheetApp.openByUrl(this.url);
    const sheet = spreadsheet.getSheetByName(this.sheetName);

    if (!sheet) {
      throw new Error(`シート "${this.sheetName}" が見つかりません`);
    }

    const lastRow = sheet.getLastRow();
    const newRowNumber = lastRow + 1;

    const rowData = this.headers.map(header => data[header] || '');

    sheet.getRange(newRowNumber, 1, 1, rowData.length).setValues([rowData]);

    const newRow = new SheetRow(this.headers, rowData);
    this.rows.push(newRow);

    return this.rows.length - 1;
  }

  /**
   * 複数の行を一括で追加
   * @param {Object[]} dataArray - 追加するデータの配列
   * @return {number[]} 追加された行のインデックスの配列
   */
  addRows(dataArray) {
    const spreadsheet = SpreadsheetApp.openByUrl(this.url);
    const sheet = spreadsheet.getSheetByName(this.sheetName);

    if (!sheet) {
      throw new Error(`シート "${this.sheetName}" が見つかりません`);
    }

    const lastRow = sheet.getLastRow();
    const newRowStart = lastRow + 1;

    const rowsData = dataArray.map(data =>
      this.headers.map(header => data[header] || '')
    );

    sheet.getRange(newRowStart, 1, rowsData.length, this.headers.length)
      .setValues(rowsData);

    const addedIndices = [];
    rowsData.forEach(rowData => {
      const newRow = new SheetRow(this.headers, rowData);
      this.rows.push(newRow);
      addedIndices.push(this.rows.length - 1);
    });

    return addedIndices;
  }

  /**
   * 指定した行を削除
   * @param {number} rowIndex - 削除する行のインデックス（0始まり）
   */
  deleteRow(rowIndex) {
    const spreadsheet = SpreadsheetApp.openByUrl(this.url);
    const sheet = spreadsheet.getSheetByName(this.sheetName);

    if (!sheet) {
      throw new Error(`シート "${this.sheetName}" が見つかりません`);
    }

    if (rowIndex < 0 || rowIndex >= this.rows.length) {
      throw new Error(`行インデックス ${rowIndex} が範囲外です`);
    }

    const actualRow = this.headerRow + 1 + rowIndex;
    sheet.deleteRow(actualRow);

    this.rows.splice(rowIndex, 1);
  }

  /**
   * 特定のセルの値を更新
   * @param {number} rowIndex - 行インデックス（0始まり）
   * @param {string} headerName - ヘッダ名
   * @param {*} value - 設定する値
   */
  setCellValue(rowIndex, headerName, value) {
    const spreadsheet = SpreadsheetApp.openByUrl(this.url);
    const sheet = spreadsheet.getSheetByName(this.sheetName);

    if (!sheet) {
      throw new Error(`シート "${this.sheetName}" が見つかりません`);
    }

    if (rowIndex < 0 || rowIndex >= this.rows.length) {
      throw new Error(`行インデックス ${rowIndex} が範囲外です`);
    }

    const columnIndex = this.headers.indexOf(headerName);
    if (columnIndex === -1) {
      throw new Error(`ヘッダ "${headerName}" が見つかりません`);
    }

    const actualRow = this.headerRow + 1 + rowIndex;
    const cell = sheet.getRange(actualRow, columnIndex + 1);
    cell.setValue(value);

    this.rows[rowIndex].data[headerName] = value;
  }
}

