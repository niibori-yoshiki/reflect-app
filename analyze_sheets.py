"""Google Sheets 自動分析スクリプト

スプレッドシートから全月分のデータを取得し、分析レポートを出力する。

前提:
  1. credentials/service_account.json が配置済み
  2. スプレッドシートがサービスアカウントに共有済み

使い方:
  python analyze_sheets.py --household "スプレッドシートURL" --portfolio "ポートフォリオURL"

  または .env に以下を設定:
    HOUSEHOLD_SHEET_URL=https://docs.google.com/spreadsheets/d/...
    PORTFOLIO_SHEET_URL=https://docs.google.com/spreadsheets/d/...
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

try:
    import gspread
    from google.oauth2.service_account import Credentials
    import pandas as pd
except ImportError:
    print("必要なパッケージをインストールしてください:")
    print("  pip install gspread google-auth pandas")
    sys.exit(1)

from dotenv import load_dotenv

load_dotenv()

CREDENTIALS_PATH = Path("credentials/service_account.json")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def fmt(amount) -> str:
    """金額フォーマット"""
    try:
        return f"¥{float(amount):,.0f}"
    except (ValueError, TypeError):
        return str(amount)


def get_client() -> gspread.Client:
    """認証済みgspreadクライアントを返す"""
    if not CREDENTIALS_PATH.exists():
        print(f"エラー: {CREDENTIALS_PATH} が見つかりません")
        print("GCPセットアップガイド:")
        print("  1. Google Cloud Console でプロジェクト作成")
        print("  2. Google Sheets API + Google Drive API を有効化")
        print("  3. サービスアカウント作成 → JSONキーをダウンロード")
        print(f"  4. JSONキーを {CREDENTIALS_PATH} に配置")
        print("  5. スプレッドシートをサービスアカウントのメールに共有")
        sys.exit(1)

    creds = Credentials.from_service_account_file(str(CREDENTIALS_PATH), scopes=SCOPES)
    return gspread.authorize(creds)


# ============================================================
# 家計簿分析
# ============================================================

SHEET_NAME_PATTERNS = [
    re.compile(r"(\d{2,4})\s*年?\s*(\d{1,2})\s*月\s*支払"),  # 26年2月支払, 25年11月支払
    re.compile(r"(\d{1,2})\s*月\s*支払"),                       # 10月支払
    re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月"),               # 2024年1月
    re.compile(r"(\d{4})[/\-](\d{1,2})"),                       # 2024/01
]


def parse_sheet_name(name: str) -> Optional[Tuple[int, int]]:
    """シート名から年月を取得"""
    for pattern in SHEET_NAME_PATTERNS:
        m = pattern.search(name)
        if m:
            groups = m.groups()
            if len(groups) == 2:
                year = int(groups[0])
                month = int(groups[1])
                # 2桁年を4桁に変換
                if year < 100:
                    year += 2000
                if 1 <= month <= 12:
                    return (year, month)
            elif len(groups) == 1:
                # 月のみ（年が不明な場合はシート順から推定）
                month = int(groups[0])
                if 1 <= month <= 12:
                    return (None, month)
    return None


def analyze_household_sheet(spreadsheet) -> str:
    """家計簿スプレッドシートの全シートを分析"""
    lines = []
    lines.append(f"{'='*60}")
    lines.append(f"  家計簿 全月分析")
    lines.append(f"{'='*60}")

    monthly_data = []

    for ws in spreadsheet.worksheets():
        parsed = parse_sheet_name(ws.title)
        if parsed is None:
            lines.append(f"\n  スキップ: {ws.title} (家計データではないシート)")
            continue

        year, month = parsed
        label = f"{year}年{month}月" if year else f"{month}月"

        try:
            all_values = ws.get_all_values()
        except Exception as e:
            lines.append(f"\n  エラー ({label}): {e}")
            continue

        if len(all_values) < 2:
            continue

        # データを解析（ヘッダー行を探す）
        header_row = None
        for i, row in enumerate(all_values):
            row_lower = [str(c).strip().lower() for c in row]
            if any(k in row_lower for k in ["ジャンル", "項目", "金額", "カテゴリ"]):
                header_row = i
                break

        if header_row is None:
            # ヘッダーが見つからない場合、全セルから金額情報を抽出
            total = extract_total_from_cells(all_values)
            if total:
                monthly_data.append({"year": year, "month": month, "total": total, "label": label})
            continue

        headers = [str(h).strip() for h in all_values[header_row]]
        data_rows = all_values[header_row + 1:]

        # 金額列のインデックスを探す
        amount_idx = None
        for i, h in enumerate(headers):
            if h in ["金額", "支出", "amount"]:
                amount_idx = i
                break

        if amount_idx is None:
            continue

        # カテゴリ列
        cat_idx = None
        for i, h in enumerate(headers):
            if h in ["ジャンル", "カテゴリ", "項目", "分類"]:
                cat_idx = i
                break

        # 集計
        total = 0
        categories = {}
        for row in data_rows:
            if amount_idx < len(row):
                val = str(row[amount_idx]).replace(",", "").replace("¥", "").replace("￥", "").strip()
                try:
                    amount = float(val)
                    total += amount
                    if cat_idx is not None and cat_idx < len(row):
                        cat = str(row[cat_idx]).strip()
                        if cat:
                            categories[cat] = categories.get(cat, 0) + amount
                except (ValueError, TypeError):
                    pass

        monthly_data.append({
            "year": year, "month": month, "total": total,
            "categories": categories, "label": label,
        })

    # 月次サマリー
    if monthly_data:
        monthly_data.sort(key=lambda x: (x.get("year") or 0, x["month"]))

        lines.append(f"\n■ 月次支出推移")
        lines.append(f"  {'月':>10} {'支出合計':>14} {'1人あたり':>14} {'前月比':>12}")
        lines.append(f"  {'-'*54}")

        prev_total = None
        for m in monthly_data:
            per_person = m["total"] / 2
            if prev_total:
                change = m["total"] - prev_total
                change_pct = change / prev_total * 100
                change_str = f"{fmt(change)} ({change_pct:+.1f}%)"
            else:
                change_str = "-"
            lines.append(
                f"  {m['label']:>10} {fmt(m['total']):>14} {fmt(per_person):>14} {change_str:>12}"
            )
            prev_total = m["total"]

        # 平均
        avg = sum(m["total"] for m in monthly_data) / len(monthly_data)
        lines.append(f"\n  月間平均支出: {fmt(avg)} (1人あたり {fmt(avg/2)})")

        # カテゴリ別累計
        all_cats = {}
        for m in monthly_data:
            for cat, amount in m.get("categories", {}).items():
                all_cats[cat] = all_cats.get(cat, 0) + amount

        if all_cats:
            total_all = sum(all_cats.values())
            lines.append(f"\n■ カテゴリ別累計支出")
            for cat, amount in sorted(all_cats.items(), key=lambda x: -x[1]):
                pct = amount / total_all * 100
                bar = "#" * int(pct / 2)
                lines.append(f"  {cat:<12} {fmt(amount):>14} ({pct:>5.1f}%) {bar}")

    return "\n".join(lines)


def extract_total_from_cells(all_values: list) -> Optional[float]:
    """セルから「合計金額」に対応する値を探す"""
    for row in all_values:
        for i, cell in enumerate(row):
            if "合計" in str(cell) and i + 1 < len(row):
                val = str(row[i + 1]).replace(",", "").replace("¥", "").strip()
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass
    return None


# ============================================================
# ポートフォリオ分析
# ============================================================

def analyze_portfolio_sheet(spreadsheet) -> str:
    """ポートフォリオ スプレッドシートの分析"""
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"  ポートフォリオ分析")
    lines.append(f"{'='*60}")

    # 「資産割合表」シートを探す
    target_sheets = ["資産割合表", "ポートフォリオ", "資産"]
    ws = None
    for name in target_sheets:
        try:
            ws = spreadsheet.worksheet(name)
            break
        except gspread.WorksheetNotFound:
            continue

    if ws is None:
        # 最初のシートを使う
        ws = spreadsheet.sheet1
        lines.append(f"  (シート: {ws.title} を使用)")

    all_values = ws.get_all_values()
    if not all_values:
        lines.append("  データが見つかりません")
        return "\n".join(lines)

    # ヘッダー行（日付が並んでいる行）を探す
    date_pattern = re.compile(r"\d{4}/\d{1,2}")
    header_row = None
    date_cols = []

    for i, row in enumerate(all_values):
        dates_in_row = [(j, cell) for j, cell in enumerate(row) if date_pattern.match(str(cell).strip())]
        if len(dates_in_row) >= 2:
            header_row = i
            date_cols = dates_in_row
            break

    if header_row is None:
        lines.append("  日付ヘッダーが見つかりません")
        lines.append("  シートの内容を表示します:")
        for row in all_values[:10]:
            lines.append(f"  {row}")
        return "\n".join(lines)

    months = [d[1].strip() for d in date_cols]
    col_indices = [d[0] for d in date_cols]

    lines.append(f"\n■ 追跡期間: {months[0]} → {months[-1]}")

    # 各資産行を読み取り
    assets = {}
    for row_idx in range(header_row + 1, len(all_values)):
        row = all_values[row_idx]
        name = str(row[0]).strip() if row else ""
        if not name or name in ["", "合計"]:
            # 合計行かチェック
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
                # パーセンテージを除去
                val = re.sub(r"\(.*?\)", "", val).strip()
                try:
                    values.append(float(val))
                except (ValueError, TypeError):
                    values.append(None)
            else:
                values.append(None)

        if any(v is not None and v > 0 for v in values):
            assets[name] = values

    # 結果表示
    if assets:
        lines.append(f"\n■ 資産別パフォーマンス")
        lines.append(f"  {'銘柄':<25} {'開始':>14} {'最新':>14} {'損益':>14} {'利回り':>8}")
        lines.append(f"  {'-'*78}")

        for name, values in assets.items():
            start = next((v for v in values if v is not None), None)
            end = next((v for v in reversed(values) if v is not None), None)
            if start and end and start > 0:
                gain = end - start
                ret = gain / start * 100
                lines.append(
                    f"  {name:<25} {fmt(start):>14} {fmt(end):>14} "
                    f"{fmt(gain):>14} {ret:>+7.1f}%"
                )

    # キャッシュフロー計算書があれば表示
    try:
        cf_ws = spreadsheet.worksheet("キャッシュフロー計算書")
        cf_values = cf_ws.get_all_values()
        if cf_values:
            lines.append(f"\n■ キャッシュフロー計算書")
            for row in cf_values[:15]:
                cleaned = [str(c).strip() for c in row if str(c).strip()]
                if cleaned:
                    lines.append(f"  {' | '.join(cleaned)}")
    except gspread.WorksheetNotFound:
        pass

    return "\n".join(lines)


# ============================================================
# メイン
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="家計・資産分析レポート")
    parser.add_argument("--household", help="家計簿スプレッドシートのURL")
    parser.add_argument("--portfolio", help="ポートフォリオスプレッドシートのURL")
    args = parser.parse_args()

    household_url = args.household or os.getenv("HOUSEHOLD_SHEET_URL")
    portfolio_url = args.portfolio or os.getenv("PORTFOLIO_SHEET_URL")

    if not household_url and not portfolio_url:
        print("使い方:")
        print("  python analyze_sheets.py --household 'URL' --portfolio 'URL'")
        print("")
        print("または .env に以下を設定:")
        print("  HOUSEHOLD_SHEET_URL=https://docs.google.com/spreadsheets/d/...")
        print("  PORTFOLIO_SHEET_URL=https://docs.google.com/spreadsheets/d/...")
        sys.exit(1)

    client = get_client()

    if household_url:
        print("家計簿データを読み込み中...")
        try:
            ss = client.open_by_url(household_url)
            print(analyze_household_sheet(ss))
        except Exception as e:
            print(f"家計簿の読み込みエラー: {e}")

    if portfolio_url:
        print("\nポートフォリオデータを読み込み中...")
        try:
            ss = client.open_by_url(portfolio_url)
            print(analyze_portfolio_sheet(ss))
        except Exception as e:
            print(f"ポートフォリオの読み込みエラー: {e}")

    print(f"\n{'='*60}")
    print(f"  分析完了")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
