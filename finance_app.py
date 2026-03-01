"""家計管理・ライフプラン アプリケーション

Streamlit マルチページアプリのエントリポイント。
起動: streamlit run finance_app.py
"""

import streamlit as st
import json
from pathlib import Path

st.set_page_config(
    page_title="家計管理・ライフプラン",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# セッション状態の初期化
if "spreadsheet_url" not in st.session_state:
    st.session_state.spreadsheet_url = ""
if "life_plan_data" not in st.session_state:
    st.session_state.life_plan_data = None
if "finance_df" not in st.session_state:
    st.session_state.finance_df = None

# サイドバー：共通設定
st.sidebar.title("💰 家計管理")
st.sidebar.markdown("---")

# スプレッドシート接続設定
st.sidebar.subheader("📊 データソース")
spreadsheet_url = st.sidebar.text_input(
    "スプレッドシートURL",
    value=st.session_state.spreadsheet_url,
    placeholder="https://docs.google.com/spreadsheets/d/...",
)
st.session_state.spreadsheet_url = spreadsheet_url

# ライフプラン設定の保存・読み込み
LIFE_PLAN_SAVE_PATH = Path("data/life_plan.json")


def save_life_plan(data: dict):
    """ライフプラン設定をJSONに保存"""
    LIFE_PLAN_SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LIFE_PLAN_SAVE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_life_plan() -> dict | None:
    """保存済みのライフプラン設定を読み込む"""
    if LIFE_PLAN_SAVE_PATH.exists():
        with open(LIFE_PLAN_SAVE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return None


# メインページ
st.title("💰 家計管理・ライフプラン")
st.markdown("---")

st.markdown("""
### ようこそ！

このアプリは、Google スプレッドシートの家計簿データを読み取り、
**家計分析**と**ライフプランのシミュレーション**を行うツールです。

#### 📄 ページ一覧

| ページ | 機能 |
|--------|------|
| **📊 ダッシュボード** | 月次収支サマリー・カテゴリ別グラフ |
| **📋 月別詳細** | 月ごとの収支明細・前月比較 |
| **🎯 ライフプラン** | 教育費・老後資金のシミュレーション |
| **🤖 AI 相談** | AIによる家計改善アドバイス |

#### 🚀 はじめに

1. **Google Cloud** でサービスアカウントを作成し、JSONキーを `credentials/service_account.json` に配置
2. スプレッドシートをサービスアカウントのメールアドレスに**共有**
3. サイドバーにスプレッドシートのURLを入力
4. 各ページで分析結果を確認
""")

# GCP設定ガイド
with st.expander("📖 Google Cloud セットアップガイド"):
    st.markdown("""
    #### 1. Google Cloud Console でプロジェクトを作成
    - [Google Cloud Console](https://console.cloud.google.com/) にアクセス
    - 新しいプロジェクトを作成（例：「家計管理」）

    #### 2. API を有効化
    - 「APIとサービス」→「ライブラリ」
    - **Google Sheets API** を検索して有効化
    - **Google Drive API** を検索して有効化

    #### 3. サービスアカウントを作成
    - 「APIとサービス」→「認証情報」→「認証情報を作成」→「サービスアカウント」
    - 名前を入力して作成
    - 作成後、サービスアカウントをクリック→「キー」タブ→「鍵を追加」→「JSONキーを作成」
    - ダウンロードされたJSONファイルを `credentials/service_account.json` として配置

    #### 4. スプレッドシートを共有
    - サービスアカウントのメールアドレス（`xxx@xxx.iam.gserviceaccount.com`）をコピー
    - Google スプレッドシートの「共有」でこのメールアドレスを追加（閲覧者でOK）
    """)

# 認証状態の表示
credentials_path = Path("credentials/service_account.json")
if credentials_path.exists():
    st.sidebar.success("✅ 認証キー設定済み")
else:
    st.sidebar.warning("⚠️ credentials/service_account.json が未配置")
