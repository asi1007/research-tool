/**
 * ボタンから呼び出す入口関数。
 * スプレッドシート上の図形/ボタンに、この関数名を割り当ててください。
 */
function openSheetRowNavigator() {
  const ui = SpreadsheetApp.getUi();
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getActiveSheet();
  const cell = sheet.getActiveCell();

  if (!cell) {
    ui.alert('アクティブなセルが見つかりません。セルを選択してから実行してください。');
    return;
  }

  const model = SheetRowNavigatorModelFactory.fromActiveSelection_(ss, sheet, cell.getRow());

  const template = HtmlService.createTemplateFromFile('SheetRowNavigatorDialog');
  template.model = model;
  const html = template.evaluate().setWidth(420).setHeight(220);

  // モデルはHTML側で google.script.run から取得する（テンプレ展開で埋め込まない）
  ss.toast(`選択中: ${model.currentSheetName} / ${model.row}行`, 'シート移動', 3);
  ui.showModalDialog(html, '移動先シートを選択');
}

/**
 * ダイアログ（google.script.run）で承認エラーになる場合の代替入口。
 * ボタンにこちらを割り当てると、プロンプトで移動先を選べます（サーバー側のみで完結）。
 */
function openSheetRowNavigatorPrompt() {
  const ui = SpreadsheetApp.getUi();
  const ss = SpreadsheetApp.getActiveSpreadsheet() || SpreadsheetApp.getActive();
  if (!ss) {
    ui.alert('アクティブなスプレッドシートが取得できません');
    return;
  }
  const sheet = ss.getActiveSheet();
  const cell = sheet ? sheet.getActiveCell() : null;
  if (!sheet || !cell) {
    ui.alert('セルを選択してから実行してください');
    return;
  }

  const activeRange = sheet.getActiveRange();
  const rows = SheetRowNavigatorSelection_.getSelectedRows_(activeRange, cell, SHEET_ROW_NAVIGATOR_HEADER_ROW);
  if (rows.length === 0) {
    ui.alert('選択範囲がヘッダ行のみです。データ行を選択してください。');
    return;
  }

  const model = SheetRowNavigatorModelFactory.fromActiveSelection_(ss, sheet, rows[0]);
  if (!model.sheetNames || model.sheetNames.length === 0) {
    ui.alert('移動できるシートがありません（非表示シート・現在シートは候補から除外しています）');
    return;
  }

  const optionsText = model.sheetNames.map((name, idx) => `${idx + 1}: ${name}`).join('\n');
  const rowText = (rows.length === 1)
    ? `${rows[0]}行`
    : `${rows[0]}行〜${rows[rows.length - 1]}行（${rows.length}行）`;
  const prompt = ui.prompt(
    '移動先シートを選択',
    `移動元: ${model.currentSheetName} / ${rowText}\n\n番号を入力してください:\n${optionsText}`,
    ui.ButtonSet.OK_CANCEL
  );

  if (prompt.getSelectedButton() !== ui.Button.OK) return;

  const n = Number(String(prompt.getResponseText() || '').trim());
  if (!Number.isFinite(n) || n < 1 || n > model.sheetNames.length) {
    ui.alert('番号が不正です');
    return;
  }

  const target = model.sheetNames[n - 1];
  const res = moveRowsToBottomOfSheet(target, model.sourceSheetName, rows);
  if (!res || !res.ok) {
    ui.alert(`移動に失敗しました: ${(res && res.message) ? res.message : '不明なエラー'}\ntraceId: ${(res && res.traceId) ? res.traceId : 'n/a'}`);
  }
}

// ===== シート上の「選択式（プルダウン）」版 =====
const SHEET_ROW_NAVIGATOR_CONTROL_SHEET_NAME = '__行移動_設定__';
const SHEET_ROW_NAVIGATOR_TARGET_CELL_A1 = 'B2';
// カラム名（ヘッダ）が書かれている行番号（1始まり）
// ※あなたのシートに合わせて必要なら変更してください（この行を変えるだけでOK）
const SHEET_ROW_NAVIGATOR_HEADER_ROW = 3;

/**
 * 「移動先シート」をシート上のプルダウンで選べるように、設定シートを作成/更新します。
 * HTMLダイアログ（google.script.run）が環境で落ちる場合でも確実に使える方式です。
 */
function setupSheetRowNavigatorControl() {
  const ui = SpreadsheetApp.getUi();
  const ss = SpreadsheetApp.getActiveSpreadsheet() || SpreadsheetApp.getActive();
  if (!ss) {
    ui.alert('アクティブなスプレッドシートが取得できません');
    return;
  }

  const controlSheet = SheetRowNavigatorControl_.ensureControlSheet_(ss);
  // 初回は設定シート自身だけ除外（移動元は実行時に除外する）
  SheetRowNavigatorControl_.refreshTargetDropdown_(ss, controlSheet, controlSheet.getName());

  ss.setActiveSheet(controlSheet);
  controlSheet.getRange(SHEET_ROW_NAVIGATOR_TARGET_CELL_A1).activate();
  ui.alert('設定シートを更新しました。B2 のプルダウンで移動先シートを選んでください。');
}

/**
 * ボタンに割り当てる「選択式」入口関数。
 * - 移動元: 現在アクティブなシートのアクティブ行
 * - 移動先: 設定シート B2 のプルダウンで選んだシート
 */
function moveActiveRowToSelectedSheetBottom() {
  const ui = SpreadsheetApp.getUi();
  const ss = SpreadsheetApp.getActiveSpreadsheet() || SpreadsheetApp.getActive();
  if (!ss) {
    ui.alert('アクティブなスプレッドシートが取得できません');
    return;
  }

  const sourceSheet = ss.getActiveSheet();
  const cell = sourceSheet ? sourceSheet.getActiveCell() : null;
  if (!sourceSheet || !cell) {
    ui.alert('移動元シートでセルを選択してから実行してください');
    return;
  }
  const activeRange = sourceSheet.getActiveRange();
  const rows = SheetRowNavigatorSelection_.getSelectedRows_(activeRange, cell, SHEET_ROW_NAVIGATOR_HEADER_ROW);
  if (rows.length === 0) {
    ui.alert('選択範囲がヘッダ行のみです。データ行を選択してください。');
    return;
  }

  const controlSheet = ss.getSheetByName(SHEET_ROW_NAVIGATOR_CONTROL_SHEET_NAME);
  if (!controlSheet) {
    ui.alert(`設定シート "${SHEET_ROW_NAVIGATOR_CONTROL_SHEET_NAME}" がありません。先に setupSheetRowNavigatorControl() を実行してください。`);
    return;
  }

  // 毎回最新の候補に更新（非表示除外・現在シート除外）
  SheetRowNavigatorControl_.refreshTargetDropdown_(ss, controlSheet, sourceSheet.getName());

  const targetSheetName = String(controlSheet.getRange(SHEET_ROW_NAVIGATOR_TARGET_CELL_A1).getValue() || '').trim();
  if (!targetSheetName) {
    ui.alert('移動先シートが未選択です（設定シート B2 のプルダウンで選択してください）');
    return;
  }

  const res = moveRowsToBottomOfSheet(targetSheetName, sourceSheet.getName(), rows);
  if (!res || !res.ok) {
    ui.alert(`移動に失敗しました: ${(res && res.message) ? res.message : '不明なエラー'}\ntraceId: ${(res && res.traceId) ? res.traceId : 'n/a'}`);
    return;
  }

  const rowText = (rows.length === 1)
    ? `${rows[0]}行`
    : `${rows[0]}行〜${rows[rows.length - 1]}行（${rows.length}行）`;
  ui.alert(`移動しました: ${sourceSheet.getName()} ${rowText} → ${targetSheetName} 最下部`);
}

class SheetRowNavigatorControl_ {
  static ensureControlSheet_(ss) {
    let sheet = ss.getSheetByName(SHEET_ROW_NAVIGATOR_CONTROL_SHEET_NAME);
    if (!sheet) {
      sheet = ss.insertSheet(SHEET_ROW_NAVIGATOR_CONTROL_SHEET_NAME);
    }

    sheet.getRange('A1').setValue('行移動（選択式）');
    sheet.getRange('A2').setValue('移動先シート');
    sheet.getRange('A4').setValue('使い方');
    sheet.getRange('A5').setValue('1) B2 で移動先シートを選択');
    sheet.getRange('A6').setValue('2) 移動元シートで移動したい行のセルを選択');
    sheet.getRange('A7').setValue('3) ボタンから moveActiveRowToSelectedSheetBottom() を実行');
    sheet.setFrozenRows(1);
    sheet.autoResizeColumns(1, 2);

    return sheet;
  }

  static refreshTargetDropdown_(ss, controlSheet, excludeSheetName) {
    const names = ss.getSheets()
      .filter(s => (typeof s.isSheetHidden === 'function') ? !s.isSheetHidden() : true)
      .map(s => s.getName())
      .filter(n => n !== excludeSheetName);

    const targetCell = controlSheet.getRange(SHEET_ROW_NAVIGATOR_TARGET_CELL_A1);
    const rule = SpreadsheetApp.newDataValidation()
      .requireValueInList(names, true)
      .setAllowInvalid(false)
      .build();
    targetCell.setDataValidation(rule);

    // 現在値が候補外なら先頭をセット
    const current = String(targetCell.getValue() || '').trim();
    if (!current || names.indexOf(current) === -1) {
      targetCell.setValue(names[0] || '');
    }
  }
}

/**
 * 権限（承認）を確実に取得するための関数。
 * Apps Script エディタ上でこの関数を「1回だけ」実行し、表示される承認を完了してください。
 * （一時シートを作成→書き込み→削除して、スプレッドシート編集権限を発火させます）
 */
function authorizeSheetRowNavigator() {
  const ss = SpreadsheetApp.getActiveSpreadsheet() || SpreadsheetApp.getActive();
  if (!ss) throw new Error('アクティブなスプレッドシートが取得できません');

  const tempName = `__sheet_row_navigator_auth_${new Date().getTime()}__`;
  const tempSheet = ss.insertSheet(tempName);

  try {
    tempSheet.getRange(1, 1).setValue('auth');
    tempSheet.getRange(1, 1).clearContent();
  } finally {
    // 作成した一時シートは必ず削除
    ss.deleteSheet(tempSheet);
  }
}

/**
 * 選択したシートへ移動し、アクティブ行をそのシート最下部へ移動する（HTMLから呼ばれる）
 * @param {string} targetSheetName
 * @param {string} sourceSheetName
 * @param {number} row
 */
/**
 * 互換用（単一行）
 */
function moveActiveRowToBottomOfSheet(targetSheetName, sourceSheetName, row) {
  return moveRowsToBottomOfSheet(targetSheetName, sourceSheetName, [row]);
}

/**
 * 選択行（複数行）を、移動先シート最下部へ移動し、移動元の該当行は削除する。
 * - 値/数式は「カラム名（ヘッダ）」一致でマッピング
 * - 位置一致ではない
 * @param {string} targetSheetName
 * @param {string} sourceSheetName
 * @param {number[]} rows
 */
function moveRowsToBottomOfSheet(targetSheetName, sourceSheetName, rows) {
  const traceId = Utilities.getUuid();
  const log = (msg, obj) => {
    const suffix = (obj === undefined) ? '' : ` | ${JSON.stringify(obj)}`;
    Logger.log(`[SheetRowNavigator][${traceId}] ${msg}${suffix}`);
    // V8環境では console.log も実行ログに出ることがある
    try { console.log(`[SheetRowNavigator][${traceId}] ${msg}${suffix}`); } catch (_) {}
  };

  try {
    log('start', { targetSheetName, sourceSheetName, rows });

    const ss = SpreadsheetApp.getActiveSpreadsheet() || SpreadsheetApp.getActive();
    if (!ss) {
      log('no active spreadsheet');
      return { ok: false, message: 'アクティブなスプレッドシートが取得できません（コンテナバインドのスクリプトか確認してください）', traceId };
    }

    if (!targetSheetName || !sourceSheetName) {
      log('invalid sheet names');
      return { ok: false, message: 'シート名が不正です（target/source）', traceId };
    }
    if (targetSheetName === sourceSheetName) {
      log('target equals source');
      return { ok: false, message: '移動先に現在シートが選ばれています（候補除外のはずですが念のため）', traceId };
    }
    if (!rows || !Array.isArray(rows) || rows.length === 0) {
      log('rows empty');
      return { ok: false, message: '移動対象の行がありません', traceId };
    }

    const targetSheet = ss.getSheetByName(targetSheetName);
    const sourceSheet = ss.getSheetByName(sourceSheetName);

    if (!targetSheet) {
      log('targetSheet not found');
      return { ok: false, message: `シート "${targetSheetName}" が見つかりません`, traceId };
    }
    if (!sourceSheet) {
      log('sourceSheet not found');
      return { ok: false, message: `移動元シート "${sourceSheetName}" が見つかりません`, traceId };
    }

    const headerRow = SHEET_ROW_NAVIGATOR_HEADER_ROW;
    const normalizedRows = SheetRowNavigatorSelection_.normalizeRows_(rows, headerRow, sourceSheet.getMaxRows());
    if (normalizedRows.length === 0) {
      return { ok: false, message: '移動対象の行がありません（ヘッダ行のみが指定されています）', traceId };
    }

    const sourceHeaders = SheetRowNavigatorHeader_.getResolvedHeaders_(sourceSheet, headerRow);
    const targetHeaders = SheetRowNavigatorHeader_.getResolvedHeaders_(targetSheet, headerRow);

    const sourceHeaderToCol = SheetRowNavigatorHeader_.toHeaderToColMap_(sourceHeaders);
    const targetHeaderToCol = SheetRowNavigatorHeader_.toHeaderToColMap_(targetHeaders);

    const sharedHeaders = Object.keys(targetHeaderToCol).filter(h => sourceHeaderToCol[h] !== undefined);
    log('headers', {
      headerRow,
      sourceHeaderCount: Object.keys(sourceHeaderToCol).length,
      targetHeaderCount: Object.keys(targetHeaderToCol).length,
      sharedHeaderCount: sharedHeaders.length
    });

    if (sharedHeaders.length === 0) {
      return { ok: false, message: '移動できません: 移動元と移動先で一致するカラム名がありません', traceId };
    }

    let destRow = targetSheet.getLastRow() + 1;
    const needRows = normalizedRows.length;
    log('destRow computed', { destRow, needRows, targetMaxRows: targetSheet.getMaxRows(), targetLastRow: targetSheet.getLastRow() });
    const maxRows = targetSheet.getMaxRows();
    const requiredMaxRow = destRow + needRows - 1;
    if (requiredMaxRow > maxRows) {
      const add = requiredMaxRow - maxRows;
      log('inserting rows', { add });
      targetSheet.insertRowsAfter(maxRows, add);
    }

    // 一致するカラム名ベースで、セル単位に移動（値/数式は保持。書式は要件外なので移さない）
    // ※ 1行分なのでセル単位でも性能問題になりにくい
    log('copy by header start');
    const movedSourceRows = [];
    normalizedRows.forEach(r => {
      sharedHeaders.forEach(header => {
        const sCol = sourceHeaderToCol[header];
        const tCol = targetHeaderToCol[header];

        const sCell = sourceSheet.getRange(r, sCol);
        const formula = sCell.getFormula();
        const value = sCell.getValue();

        const tCell = targetSheet.getRange(destRow, tCol);
        if (formula) {
          tCell.setFormula(formula);
        } else {
          tCell.setValue(value);
        }
      });
      movedSourceRows.push(r);
      destRow += 1;
    });
    log('copy by header done', { movedRows: movedSourceRows.length, perRowColumns: sharedHeaders.length });

    // 元のシートの該当行は削除（下から削除して行番号ズレを防ぐ）
    log('delete source rows start', { count: normalizedRows.length });
    const rowsDesc = [...normalizedRows].sort((a, b) => b - a);
    rowsDesc.forEach(r => sourceSheet.deleteRow(r));
    log('delete source rows done');

    const destStartRow = (targetSheet.getLastRow() - needRows + 1);
    log('success', { targetSheetName, destStartRow, movedRows: needRows });
    return { ok: true, destStartRow, movedRows: needRows, targetSheetName: targetSheetName, traceId };
  } catch (e) {
    const msg = e && e.message ? e.message : String(e);
    const stack = e && e.stack ? String(e.stack) : '';
    log('error', { msg, stack });
    return { ok: false, message: msg, stack: stack, traceId };
  }
}

class SheetRowNavigatorHeader_ {
  static getResolvedHeaders_(sheet, headerRow) {
    const lastCol = Math.max(1, sheet.getLastColumn());
    const headers = sheet.getRange(headerRow, 1, 1, lastCol).getValues()[0];

    // 1行上の値で補完（結合セルなどで空になるケース）
    if (headerRow > 1) {
      const above = sheet.getRange(headerRow - 1, 1, 1, lastCol).getValues()[0];
      return headers.map((h, i) => {
        const v = (h === '' || h === null || h === undefined) ? (above[i] || '') : h;
        return String(v || '').trim();
      });
    }

    return headers.map(h => String(h || '').trim());
  }

  static toHeaderToColMap_(headers) {
    /** @type {{[key: string]: number}} */
    const map = {};
    headers.forEach((h, idx) => {
      const key = String(h || '').trim();
      if (!key) return;
      // 同名ヘッダが複数ある場合は最初を優先
      if (map[key] === undefined) {
        map[key] = idx + 1; // 1始まり
      }
    });
    return map;
  }
}

class SheetRowNavigatorSelection_ {
  static getSelectedRows_(activeRange, activeCell, headerRow) {
    const rows = [];
    if (activeRange) {
      const start = activeRange.getRow();
      const num = activeRange.getNumRows();
      for (let i = 0; i < num; i++) rows.push(start + i);
    } else if (activeCell) {
      rows.push(activeCell.getRow());
    }
    return SheetRowNavigatorSelection_.normalizeRows_(rows, headerRow, Number.MAX_SAFE_INTEGER);
  }

  static normalizeRows_(rows, headerRow, maxRows) {
    const uniq = {};
    (rows || []).forEach(r => {
      const n = Math.floor(Number(r));
      if (!Number.isFinite(n)) return;
      if (n <= headerRow) return;
      if (n < 1) return;
      if (n > maxRows) return;
      uniq[n] = true;
    });
    return Object.keys(uniq).map(k => Number(k)).sort((a, b) => a - b);
  }
}

/**
 * メニュー（任意）。ボタンが無い場合の保険として追加。
 */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('ツール')
    .addItem('アクティブ行のままシートへ移動', 'openSheetRowNavigator')
    .addToUi();
}

/**
 * @typedef {Object} SheetRowNavigatorModel
 * @property {string[]} sheetNames
 * @property {string} currentSheetName
 * @property {string} sourceSheetName
 * @property {number} row
 * @property {string=} error
 */

class SheetRowNavigatorModelFactory {
  static errorModel_(message) {
    return {
      sheetNames: [],
      currentSheetName: '',
      sourceSheetName: '',
      row: 0,
      error: String(message || '不明なエラー')
    };
  }

  static fromActiveSelection_(ss, sheet, row) {
    const currentSheetName = sheet.getName();
    const sheetNames = ss.getSheets()
      .filter(s => (typeof s.isSheetHidden === 'function') ? !s.isSheetHidden() : true)
      .map(s => s.getName())
      .filter(name => name !== currentSheetName);

    return {
      sheetNames,
      currentSheetName,
      sourceSheetName: currentSheetName,
      row: row,
    };
  }
}

class SheetRowNavigatorGuard_ {
  static clampInt_(value, min, max) {
    const n = Math.floor(Number(value));
    if (!Number.isFinite(n)) return min;
    if (n < min) return min;
    if (n > max) return max;
    return n;
  }
}

