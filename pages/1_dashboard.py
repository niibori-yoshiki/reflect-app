"""📊 ダッシュボード - 月次収支サマリー"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from pathlib import Path

from finance.sheets import open_spreadsheet_by_url, get_sheet_data
from finance.parser import load_all_months
from finance.analyzer import (
    monthly_summary,
    category_breakdown,
    yearly_trend,
    savings_rate,
)

st.set_page_config(page_title="ダッシュボード", page_icon="📊", layout="wide")
st.title("📊 ダッシュボード")

# データ読み込み
url = st.session_state.get("spreadsheet_url", "")
if not url:
    st.info("サイドバーにスプレッドシートのURLを入力してください。")
    st.stop()

credentials_path = Path("credentials/service_account.json")
if not credentials_path.exists():
    st.warning("credentials/service_account.json が配置されていません。トップページのセットアップガイドをご確認ください。")
    st.stop()


@st.cache_data(ttl=300)
def load_data(spreadsheet_url: str) -> pd.DataFrame:
    """スプレッドシートからデータを読み込む（5分キャッシュ）"""
    spreadsheet = open_spreadsheet_by_url(spreadsheet_url)
    return load_all_months(spreadsheet, get_sheet_data)


try:
    with st.spinner("スプレッドシートからデータを読み込んでいます..."):
        df = load_data(url)
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()
except Exception as e:
    st.error(f"データの読み込みに失敗しました: {e}")
    st.stop()

if df.empty:
    st.warning("月別シートが見つかりませんでした。シート名に年月が含まれているか確認してください。")
    st.stop()

# 年月の選択
available_periods = df.groupby(["year", "month"]).size().reset_index()[["year", "month"]]
available_periods = available_periods.sort_values(["year", "month"], ascending=False)

col1, col2 = st.columns(2)
with col1:
    selected_year = st.selectbox("年", available_periods["year"].unique())
with col2:
    months_in_year = available_periods[available_periods["year"] == selected_year]["month"].tolist()
    selected_month = st.selectbox("月", months_in_year)

st.markdown("---")

# 月次サマリー
summary = monthly_summary(df, selected_year, selected_month)
rate = savings_rate(df, selected_year, selected_month)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("収入", f"¥{summary['income']:,.0f}")
with col2:
    st.metric("支出", f"¥{summary['expense']:,.0f}")
with col3:
    st.metric("収支", f"¥{summary['balance']:,.0f}",
              delta=f"¥{summary['balance']:,.0f}")
with col4:
    st.metric("貯蓄率", f"{rate}%" if rate is not None else "N/A")

st.markdown("---")

# カテゴリ別支出グラフ
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("カテゴリ別支出")
    cat_df = category_breakdown(df, selected_year, selected_month, "expense")
    if not cat_df.empty:
        fig = px.pie(
            cat_df,
            values="amount",
            names="category",
            hole=0.4,
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("支出データがありません")

with col_right:
    st.subheader("カテゴリ別支出ランキング")
    if not cat_df.empty:
        fig = px.bar(
            cat_df,
            x="amount",
            y="category",
            orientation="h",
            text="amount",
        )
        fig.update_traces(texttemplate="¥%{text:,.0f}", textposition="outside")
        fig.update_layout(
            height=400,
            yaxis={"categoryorder": "total ascending"},
            xaxis_title="金額（円）",
            yaxis_title="",
        )
        st.plotly_chart(fig, use_container_width=True)

# 年間推移グラフ
st.markdown("---")
st.subheader(f"{selected_year}年 月別収支推移")

trend = yearly_trend(df, selected_year)
trend_filtered = trend[trend["transaction_count"] > 0]

if not trend_filtered.empty:
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=trend_filtered["month"],
        y=trend_filtered["income"],
        name="収入",
        marker_color="#2ecc71",
    ))
    fig.add_trace(go.Bar(
        x=trend_filtered["month"],
        y=trend_filtered["expense"],
        name="支出",
        marker_color="#e74c3c",
    ))
    fig.add_trace(go.Scatter(
        x=trend_filtered["month"],
        y=trend_filtered["balance"],
        name="収支",
        mode="lines+markers",
        line={"color": "#3498db", "width": 3},
    ))
    fig.update_layout(
        barmode="group",
        xaxis_title="月",
        yaxis_title="金額（円）",
        height=400,
        xaxis={"dtick": 1},
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info(f"{selected_year}年のデータがありません")
