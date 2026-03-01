"""📋 月別詳細 - 収支明細と前月比較"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from pathlib import Path

from finance.sheets import open_spreadsheet_by_url, get_sheet_data
from finance.parser import load_all_months
from finance.analyzer import (
    monthly_comparison,
    category_breakdown,
    top_expenses,
)

st.set_page_config(page_title="月別詳細", page_icon="📋", layout="wide")
st.title("📋 月別詳細")

url = st.session_state.get("spreadsheet_url", "")
if not url:
    st.info("サイドバーにスプレッドシートのURLを入力してください。")
    st.stop()

credentials_path = Path("credentials/service_account.json")
if not credentials_path.exists():
    st.warning("credentials/service_account.json が配置されていません。")
    st.stop()


@st.cache_data(ttl=300)
def load_data(spreadsheet_url: str) -> pd.DataFrame:
    spreadsheet = open_spreadsheet_by_url(spreadsheet_url)
    return load_all_months(spreadsheet, get_sheet_data)


try:
    with st.spinner("データ読み込み中..."):
        df = load_data(url)
except Exception as e:
    st.error(f"データの読み込みに失敗しました: {e}")
    st.stop()

if df.empty:
    st.warning("データが見つかりませんでした。")
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

# 前月比較
comparison = monthly_comparison(df, selected_year, selected_month)
curr = comparison["current"]
prev = comparison["previous"]

st.subheader("前月比較")
col1, col2, col3 = st.columns(3)

with col1:
    delta = comparison["income_change"]
    pct = comparison["income_change_pct"]
    pct_str = f" ({pct:+.1f}%)" if pct is not None else ""
    st.metric("収入", f"¥{curr['income']:,.0f}", delta=f"¥{delta:,.0f}{pct_str}")

with col2:
    delta = comparison["expense_change"]
    pct = comparison["expense_change_pct"]
    pct_str = f" ({pct:+.1f}%)" if pct is not None else ""
    st.metric("支出", f"¥{curr['expense']:,.0f}", delta=f"¥{delta:,.0f}{pct_str}", delta_color="inverse")

with col3:
    delta = comparison["balance_change"]
    st.metric("収支", f"¥{curr['balance']:,.0f}", delta=f"¥{delta:,.0f}")

# カテゴリ比較チャート
st.markdown("---")
st.subheader("カテゴリ別 前月比較")

cat_curr = category_breakdown(df, selected_year, selected_month, "expense")
prev_month = selected_month - 1
prev_year = selected_year
if prev_month == 0:
    prev_month = 12
    prev_year -= 1
cat_prev = category_breakdown(df, prev_year, prev_month, "expense")

if not cat_curr.empty:
    # マージして比較
    merged = cat_curr.rename(columns={"amount": "当月"}).merge(
        cat_prev.rename(columns={"amount": "前月"})[["category", "前月"]],
        on="category",
        how="outer",
    ).fillna(0)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=merged["category"],
        y=merged["当月"],
        name="当月",
        marker_color="#3498db",
    ))
    fig.add_trace(go.Bar(
        x=merged["category"],
        y=merged["前月"],
        name="前月",
        marker_color="#bdc3c7",
    ))
    fig.update_layout(
        barmode="group",
        xaxis_title="カテゴリ",
        yaxis_title="金額（円）",
        height=400,
    )
    st.plotly_chart(fig, use_container_width=True)

# 支出上位
st.markdown("---")
st.subheader("支出トップ10")
top = top_expenses(df, selected_year, selected_month, n=10)
if not top.empty:
    top_display = top.copy()
    top_display["amount"] = top_display["amount"].apply(lambda x: f"¥{x:,.0f}")
    st.dataframe(top_display, use_container_width=True, hide_index=True)
else:
    st.info("支出データがありません")

# 全明細
st.markdown("---")
with st.expander("全明細データを表示"):
    month_df = df[(df["year"] == selected_year) & (df["month"] == selected_month)].copy()
    if not month_df.empty:
        month_df["amount_display"] = month_df["amount"].apply(lambda x: f"¥{x:,.0f}")
        st.dataframe(
            month_df[["date", "category", "amount_display", "type", "memo"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "date": "日付",
                "category": "カテゴリ",
                "amount_display": "金額",
                "type": "種別",
                "memo": "メモ",
            },
        )
