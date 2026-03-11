"""スプレッドシートデータのパーサー

月別シートの家計簿データを正規化し、
分析しやすいDataFrame形式に変換する。

対応フォーマット:
- シート名: "2024年1月", "2024/01", "202401" など
- 列: 日付, カテゴリ（項目）, 金額, メモ（備考）など柔軟に対応
"""

import re
from datetime import datetime
import pandas as pd


# シート名から年月を抽出するパターン
SHEET_NAME_PATTERNS = [
    re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月"),  # 2024年1月
    re.compile(r"(\d{4})[/\-](\d{1,2})"),            # 2024/01 or 2024-01
    re.compile(r"(\d{4})(\d{2})$"),                   # 202401
]

# 列名の正規化マッピング
COLUMN_MAPPINGS = {
    "date": ["日付", "日", "date", "Date"],
    "category": ["カテゴリ", "項目", "分類", "種別", "category", "Category"],
    "amount": ["金額", "支出", "収入", "amount", "Amount", "価格"],
    "income": ["収入", "入金", "income", "Income"],
    "expense": ["支出", "出金", "expense", "Expense"],
    "memo": ["メモ", "備考", "内容", "詳細", "memo", "Memo", "note", "Note"],
    "type": ["種類", "収支", "type", "Type"],
}


def parse_sheet_name(sheet_name: str) -> tuple[int, int] | None:
    """シート名から年月を抽出する。マッチしなければNoneを返す"""
    for pattern in SHEET_NAME_PATTERNS:
        match = pattern.search(sheet_name)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            if 1 <= month <= 12:
                return (year, month)
    return None


def normalize_column_name(col_name: str) -> str:
    """列名を正規化する"""
    col_name = col_name.strip()
    for normalized, variants in COLUMN_MAPPINGS.items():
        if col_name in variants:
            return normalized
    return col_name


def parse_amount(value: str | int | float) -> float:
    """金額文字列をfloatに変換する"""
    if isinstance(value, (int, float)):
        return float(value)
    if not value or not str(value).strip():
        return 0.0
    cleaned = str(value).replace(",", "").replace("¥", "").replace("￥", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def sheet_data_to_dataframe(
    records: list[dict],
    year: int,
    month: int,
) -> pd.DataFrame:
    """シートのレコードをDataFrameに変換する

    Args:
        records: get_all_records() の結果
        year: 年
        month: 月

    Returns:
        正規化されたDataFrame (columns: date, category, amount, type, memo, year, month)
    """
    if not records:
        return pd.DataFrame(columns=["date", "category", "amount", "type", "memo", "year", "month"])

    # 列名を正規化
    normalized_records = []
    for record in records:
        normalized = {}
        for key, value in record.items():
            norm_key = normalize_column_name(str(key))
            normalized[norm_key] = value
        normalized_records.append(normalized)

    df = pd.DataFrame(normalized_records)

    # 金額の処理
    if "amount" in df.columns:
        df["amount"] = df["amount"].apply(parse_amount)
    elif "income" in df.columns and "expense" in df.columns:
        df["income"] = df["income"].apply(parse_amount)
        df["expense"] = df["expense"].apply(parse_amount)
        df["amount"] = df["income"] - df["expense"]
        df["type"] = df.apply(
            lambda row: "income" if row["income"] > 0 else "expense", axis=1
        )

    # 収支タイプの判定
    if "type" not in df.columns:
        if "amount" in df.columns:
            df["type"] = df["amount"].apply(
                lambda x: "income" if x > 0 else "expense"
            )

    # メモ列がなければ空文字で追加
    if "memo" not in df.columns:
        df["memo"] = ""

    # 年月の付与
    df["year"] = year
    df["month"] = month

    # 必要な列だけ選択
    available_cols = [c for c in ["date", "category", "amount", "type", "memo", "year", "month"] if c in df.columns]
    return df[available_cols]


def load_all_months(
    spreadsheet,
    get_sheet_data_fn,
) -> pd.DataFrame:
    """全月別シートを読み込んで1つのDataFrameに統合する

    Args:
        spreadsheet: gspread.Spreadsheet オブジェクト
        get_sheet_data_fn: sheets.get_sheet_data 関数

    Returns:
        全月分を統合したDataFrame
    """
    all_dfs = []

    for ws in spreadsheet.worksheets():
        parsed = parse_sheet_name(ws.title)
        if parsed is None:
            continue
        year, month = parsed

        records = get_sheet_data_fn(spreadsheet, ws.title)
        df = sheet_data_to_dataframe(records, year, month)
        if not df.empty:
            all_dfs.append(df)

    if not all_dfs:
        return pd.DataFrame(columns=["date", "category", "amount", "type", "memo", "year", "month"])

    return pd.concat(all_dfs, ignore_index=True)
