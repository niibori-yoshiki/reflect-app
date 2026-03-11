"""スプレッドシートデータのロード・解析 共通モジュール

Streamlit UI と CLI スクリプトの両方から利用する。
analyze_sheets.py のデータ取得ロジックを共通化。
"""

import os
import re
from typing import Optional, Tuple, Dict, List
from pathlib import Path

import pandas as pd

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    gspread = None

from dotenv import load_dotenv

load_dotenv()

CREDENTIALS_PATH = Path(__file__).parent.parent / "credentials" / "service_account.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

SHEET_NAME_PATTERNS = [
    re.compile(r"(\d{2,4})\s*年?\s*(\d{1,2})\s*月\s*支払"),
    re.compile(r"(\d{1,2})\s*月\s*支払"),
    re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月"),
    re.compile(r"(\d{4})[/\-](\d{1,2})"),
]


def get_client():
    """認証済みgspreadクライアント"""
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(f"{CREDENTIALS_PATH} が見つかりません")
    creds = Credentials.from_service_account_file(str(CREDENTIALS_PATH), scopes=SCOPES)
    return gspread.authorize(creds)


def parse_sheet_name(name: str) -> Optional[Tuple]:
    """シート名から (year, month) を取得"""
    for pattern in SHEET_NAME_PATTERNS:
        m = pattern.search(name)
        if m:
            groups = m.groups()
            if len(groups) == 2:
                year = int(groups[0])
                month = int(groups[1])
                if year < 100:
                    year += 2000
                if 1 <= month <= 12:
                    return (year, month)
            elif len(groups) == 1:
                month = int(groups[0])
                if 1 <= month <= 12:
                    return (None, month)
    return None


def load_household_data(url: str) -> pd.DataFrame:
    """家計簿スプレッドシートから全月分のデータを読み込んでDataFrameで返す"""
    client = get_client()
    ss = client.open_by_url(url)

    all_rows = []
    for ws in ss.worksheets():
        parsed = parse_sheet_name(ws.title)
        if parsed is None:
            continue

        year, month = parsed
        try:
            all_values = ws.get_all_values()
        except Exception:
            continue

        if len(all_values) < 2:
            continue

        # ヘッダー行を探す
        header_row = None
        for i, row in enumerate(all_values):
            row_str = [str(c).strip() for c in row]
            if any(k in row_str for k in ["ジャンル", "項目", "金額", "カテゴリ"]):
                header_row = i
                break

        if header_row is None:
            continue

        headers = [str(h).strip() for h in all_values[header_row]]
        data_rows = all_values[header_row + 1:]

        # 列インデックス取得
        amount_idx = next((i for i, h in enumerate(headers) if h in ["金額", "支出", "amount"]), None)
        cat_idx = next((i for i, h in enumerate(headers) if h in ["ジャンル", "カテゴリ", "項目", "分類"]), None)
        item_idx = next((i for i, h in enumerate(headers) if h in ["項目", "内容", "明細"]), None)
        payer_idx = next((i for i, h in enumerate(headers) if h in ["支払者", "担当", "payer"]), None)

        if amount_idx is None:
            continue

        for row in data_rows:
            if amount_idx >= len(row):
                continue
            val = str(row[amount_idx]).replace(",", "").replace("¥", "").replace("￥", "").strip()
            try:
                amount = float(val)
            except (ValueError, TypeError):
                continue
            if amount == 0:
                continue

            cat = str(row[cat_idx]).strip() if cat_idx is not None and cat_idx < len(row) else ""
            item = str(row[item_idx]).strip() if item_idx is not None and item_idx < len(row) else ""
            payer = str(row[payer_idx]).strip() if payer_idx is not None and payer_idx < len(row) else ""

            all_rows.append({
                "year": year,
                "month": month,
                "category": cat,
                "item": item,
                "amount": amount,
                "payer": payer,
            })

    if not all_rows:
        return pd.DataFrame(columns=["year", "month", "category", "item", "amount", "payer"])

    df = pd.DataFrame(all_rows)
    df = df.sort_values(["year", "month"]).reset_index(drop=True)
    return df


def load_portfolio_data(url: str) -> Dict:
    """ポートフォリオスプレッドシートから資産データを読み込む"""
    client = get_client()
    ss = client.open_by_url(url)

    # 資産割合表シートを探す
    target_names = ["資産割合表", "ポートフォリオ", "資産"]
    ws = None
    for name in target_names:
        try:
            ws = ss.worksheet(name)
            break
        except gspread.WorksheetNotFound:
            continue
    if ws is None:
        ws = ss.sheet1

    all_values = ws.get_all_values()

    # 日付ヘッダー行を探す
    date_pattern = re.compile(r"\d{4}/\d{1,2}")
    header_row = None
    date_cols = []

    for i, row in enumerate(all_values):
        dates = [(j, str(cell).strip()) for j, cell in enumerate(row) if date_pattern.match(str(cell).strip())]
        if len(dates) >= 2:
            header_row = i
            date_cols = dates
            break

    if header_row is None:
        return {"months": [], "assets": {}}

    months = [d[1] for d in date_cols]
    col_indices = [d[0] for d in date_cols]

    # 各資産行を読む
    assets = {}
    for row_idx in range(header_row + 1, len(all_values)):
        row = all_values[row_idx]
        name = str(row[0]).strip() if row else ""

        # 名前がない行は合計行チェック
        if not name:
            for cell in row:
                if "合計" in str(cell) or "運用資金" in str(cell):
                    name = "運用資金合計"
                    break
            if not name:
                continue

        values = []
        for ci in col_indices:
            if ci < len(row):
                val = str(row[ci]).replace(",", "").replace("¥", "").replace("￥", "").strip()
                val = re.sub(r"\(.*?\)", "", val).strip()
                try:
                    values.append(float(val))
                except (ValueError, TypeError):
                    values.append(None)
            else:
                values.append(None)

        if any(v is not None and v > 0 for v in values):
            assets[name] = values

    return {"months": months, "assets": assets}


def get_monthly_totals(df: pd.DataFrame) -> pd.DataFrame:
    """月別の支出合計を算出"""
    if df.empty:
        return pd.DataFrame(columns=["year", "month", "total", "label"])

    monthly = df.groupby(["year", "month"])["amount"].sum().reset_index()
    monthly.columns = ["year", "month", "total"]
    monthly = monthly.sort_values(["year", "month"])
    monthly["label"] = monthly.apply(
        lambda r: f"{int(r['year'])}年{int(r['month'])}月" if r["year"] else f"{int(r['month'])}月",
        axis=1,
    )
    return monthly


def get_category_totals(df: pd.DataFrame, year: Optional[int] = None, month: Optional[int] = None) -> pd.DataFrame:
    """カテゴリ別集計。year/month指定で特定月のみに絞れる"""
    filtered = df.copy()
    if year is not None:
        filtered = filtered[filtered["year"] == year]
    if month is not None:
        filtered = filtered[filtered["month"] == month]

    if filtered.empty:
        return pd.DataFrame(columns=["category", "amount", "pct"])

    cat_totals = filtered.groupby("category")["amount"].sum().reset_index()
    cat_totals = cat_totals.sort_values("amount", ascending=False)
    total = cat_totals["amount"].sum()
    cat_totals["pct"] = (cat_totals["amount"] / total * 100).round(1) if total > 0 else 0
    return cat_totals
