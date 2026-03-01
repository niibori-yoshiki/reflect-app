"""📋 月別詳細 - 明細と前月比較"""

import os
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from dotenv import load_dotenv

from finance.data_loader import load_household_data, get_category_totals

load_dotenv()

st.set_page_config(page_title="月別詳細", page_icon="📋", layout="wide")
st.title("📋 月別詳細")

household_url = st.session_state.get("household_url", os.getenv("HOUSEHOLD_SHEET_URL", ""))
if not household_url:
    st.info("トップページでスプレッドシートURLを設定してください。")
    st.stop()


@st.cache_data(ttl=300)
def cached_data(url):
    return load_household_data(url)


try:
    with st.spinner("データ読み込み中..."):
        df = cached_data(household_url)
except Exception as e:
    st.error(f"読み込みエラー: {e}")
    st.stop()

if df.empty:
    st.warning("データがありません")
    st.stop()

# 年月選択
periods = df.groupby(["year", "month"]).size().reset_index()[["year", "month"]]
periods = periods.sort_values(["year", "month"], ascending=False)

col1, col2 = st.columns(2)
with col1:
    sel_year = st.selectbox("年", periods["year"].unique())
with col2:
    months = periods[periods["year"] == sel_year]["month"].tolist()
    sel_month = st.selectbox("月", months)

st.markdown("---")

# 当月データ
curr_df = df[(df["year"] == sel_year) & (df["month"] == sel_month)]
curr_total = curr_df["amount"].sum()

# 前月データ
prev_m = sel_month - 1
prev_y = sel_year
if prev_m == 0:
    prev_m = 12
    prev_y -= 1
prev_df = df[(df["year"] == prev_y) & (df["month"] == prev_m)]
prev_total = prev_df["amount"].sum()

# サマリー
col1, col2, col3 = st.columns(3)
with col1:
    delta = f"¥{int(curr_total - prev_total):,}" if prev_total > 0 else None
    st.metric("当月支出", f"¥{int(curr_total):,}", delta=delta, delta_color="inverse")
with col2:
    st.metric("1人あたり", f"¥{int(curr_total / 2):,}")
with col3:
    if prev_total > 0:
        change_pct = (curr_total - prev_total) / prev_total * 100
        st.metric("前月比", f"{change_pct:+.1f}%")
    else:
        st.metric("前月比", "N/A")

# カテゴリ比較
st.markdown("---")
st.subheader("カテゴリ別 前月比較")

cat_curr = get_category_totals(df, sel_year, sel_month)
cat_prev = get_category_totals(df, prev_y, prev_m)

if not cat_curr.empty:
    merged = cat_curr.rename(columns={"amount": "当月"}).merge(
        cat_prev.rename(columns={"amount": "前月"})[["category", "前月"]],
        on="category", how="outer",
    ).fillna(0)

    fig = go.Figure()
    fig.add_trace(go.Bar(x=merged["category"], y=merged["当月"], name="当月", marker_color="#3498db"))
    fig.add_trace(go.Bar(x=merged["category"], y=merged["前月"], name="前月", marker_color="#bdc3c7"))
    fig.update_layout(barmode="group", height=400, xaxis_title="", yaxis_title="金額（円）")
    st.plotly_chart(fig, use_container_width=True)

# 支払者別
st.markdown("---")
st.subheader("支払者別内訳")

if not curr_df.empty and "payer" in curr_df.columns:
    payer_totals = curr_df.groupby("payer")["amount"].sum().reset_index()
    payer_totals = payer_totals.sort_values("amount", ascending=False)
    if not payer_totals.empty:
        col1, col2 = st.columns(2)
        with col1:
            for _, row in payer_totals.iterrows():
                pct = row["amount"] / curr_total * 100
                st.markdown(f"**{row['payer']}**: ¥{int(row['amount']):,} ({pct:.1f}%)")
        with col2:
            import plotly.express as px
            fig = px.pie(payer_totals, values="amount", names="payer", hole=0.4)
            fig.update_layout(height=300, showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

# 明細
st.markdown("---")
st.subheader("支出明細")

if not curr_df.empty:
    display = curr_df[["category", "item", "amount", "payer"]].copy()
    display = display.sort_values("amount", ascending=False)
    display["amount"] = display["amount"].apply(lambda x: f"¥{int(x):,}")
    display.columns = ["カテゴリ", "項目", "金額", "支払者"]
    st.dataframe(display, use_container_width=True, hide_index=True)
