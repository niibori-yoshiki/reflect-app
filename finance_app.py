"""家計管理・ライフプラン

起動: streamlit run finance_app.py
"""

import os
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="家計管理・ライフプラン",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# .env から自動読み込み
default_household = os.getenv("HOUSEHOLD_SHEET_URL", "")
default_portfolio = os.getenv("PORTFOLIO_SHEET_URL", "")

if "household_url" not in st.session_state:
    st.session_state.household_url = default_household
if "portfolio_url" not in st.session_state:
    st.session_state.portfolio_url = default_portfolio

# サイドバー
st.sidebar.title("💰 家計管理")
st.sidebar.markdown("---")

credentials_path = Path("credentials/service_account.json")
if credentials_path.exists():
    st.sidebar.success("認証キー設定済み")
else:
    st.sidebar.error("credentials/service_account.json が未配置")

st.sidebar.subheader("データソース")
st.session_state.household_url = st.sidebar.text_input(
    "家計簿 URL", value=st.session_state.household_url,
)
st.session_state.portfolio_url = st.sidebar.text_input(
    "ポートフォリオ URL", value=st.session_state.portfolio_url,
)

# メインページ
st.title("💰 家計管理・ライフプラン")
st.markdown("---")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.page_link("pages/1_dashboard.py", label="📊 ダッシュボード", icon="📊")
with col2:
    st.page_link("pages/2_monthly_detail.py", label="📋 月別詳細", icon="📋")
with col3:
    st.page_link("pages/3_life_plan.py", label="🎯 ライフプラン", icon="🎯")
with col4:
    st.page_link("pages/4_ai_advice.py", label="🤖 AI 相談", icon="🤖")

st.markdown("""
### ページ案内

| ページ | 機能 |
|--------|------|
| **📊 ダッシュボード** | 月次支出推移・カテゴリ別円グラフ・ポートフォリオ |
| **📋 月別詳細** | 月ごとの支出明細・前月比較 |
| **🎯 ライフプラン** | 収入・子供の教育費・住宅計画のシミュレーション |
| **🤖 AI 相談** | 家計データを踏まえたAIアドバイス |
""")
