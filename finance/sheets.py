"""Google Sheets 接続モジュール

サービスアカウントキーを使用してGoogle Sheetsに接続し、
家計簿スプレッドシートのデータを読み書きする。

セットアップ手順:
1. Google Cloud Console (https://console.cloud.google.com/) でプロジェクト作成
2. Google Sheets API と Google Drive API を有効化
3. サービスアカウントを作成し、JSONキーをダウンロード
4. credentials/service_account.json として配置
5. スプレッドシートをサービスアカウントのメールアドレスに共有
"""

from typing import List, Dict

import gspread
from google.oauth2.service_account import Credentials
from pathlib import Path


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

CREDENTIALS_PATH = Path(__file__).parent.parent / "credentials" / "service_account.json"


def get_client() -> gspread.Client:
    """認証済みのgspreadクライアントを返す"""
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            f"サービスアカウントキーが見つかりません: {CREDENTIALS_PATH}\n"
            "credentials/service_account.json にGCPのサービスアカウントキーを配置してください。"
        )
    creds = Credentials.from_service_account_file(str(CREDENTIALS_PATH), scopes=SCOPES)
    return gspread.authorize(creds)


def open_spreadsheet(spreadsheet_name: str) -> gspread.Spreadsheet:
    """スプレッドシートを名前で開く"""
    client = get_client()
    return client.open(spreadsheet_name)


def open_spreadsheet_by_url(url: str) -> gspread.Spreadsheet:
    """スプレッドシートをURLで開く"""
    client = get_client()
    return client.open_by_url(url)


def get_all_sheet_names(spreadsheet: gspread.Spreadsheet) -> List[str]:
    """全シート名を取得（月別シート一覧の確認用）"""
    return [ws.title for ws in spreadsheet.worksheets()]


def get_sheet_data(spreadsheet: gspread.Spreadsheet, sheet_name: str) -> List[Dict]:
    """指定シートの全データを辞書のリストで取得（1行目をヘッダーとして使用）"""
    worksheet = spreadsheet.worksheet(sheet_name)
    return worksheet.get_all_records()


def get_sheet_data_raw(spreadsheet: gspread.Spreadsheet, sheet_name: str) -> list[List[str]]:
    """指定シートの全データを生の2次元リストで取得"""
    worksheet = spreadsheet.worksheet(sheet_name)
    return worksheet.get_all_values()
