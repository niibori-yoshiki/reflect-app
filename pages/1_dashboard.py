"""📊 ダッシュボード - 月次支出サマリー・ポートフォリオ"""

import os
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from dotenv import load_dotenv

from finance.data_loader import (
    load_household_data,
    load_portfolio_data,
    get_monthly_totals,
    get_category_totals,
)

load_dotenv()

st.set_page_config(page_title="ダッシュボード", page_icon="📊", layout="wide")
st.title("📊 ダッシュボード")

household_url = st.session_state.get("household_url", os.getenv("HOUSEHOLD_SHEET_URL", ""))
portfolio_url = st.session_state.get("portfolio_url", os.getenv("PORTFOLIO_SHEET_URL", ""))

if not household_url:
    st.info("トップページでスプレッドシートURLを設定してください。")
    st.stop()


@st.cache_data(ttl=300)
def cached_household(url):
    return load_household_data(url)


@st.cache_data(ttl=300)
def cached_portfolio(url):
    return load_portfolio_data(url)


# ===== 家計データ =====
try:
    with st.spinner("家計簿を読み込み中..."):
        df = cached_household(household_url)
except Exception as e:
    st.error(f"家計簿の読み込みエラー: {e}")
    st.stop()

if df.empty:
    st.warning("家計データが見つかりません")
    st.stop()

monthly = get_monthly_totals(df)

# ===== 直近月のサマリー =====
latest = monthly.iloc[-1]
prev = monthly.iloc[-2] if len(monthly) >= 2 else None

col1, col2, col3 = st.columns(3)
with col1:
    delta = None
    if prev is not None:
        delta = f"¥{int(latest['total'] - prev['total']):,}"
    st.metric(
        f"{int(latest['year'])}年{int(latest['month'])}月 支出",
        f"¥{int(latest['total']):,}",
        delta=delta,
        delta_color="inverse",
    )
with col2:
    st.metric("1人あたり", f"¥{int(latest['total'] / 2):,}")
with col3:
    # 直近6ヶ月の平均
    recent_avg = monthly.tail(6)["total"].mean()
    st.metric("直近6ヶ月平均", f"¥{int(recent_avg):,}")

st.markdown("---")

# ===== 月次推移グラフ =====
st.subheader("月次支出推移")

# 結婚関連の異常値を除外するオプション
exclude_outliers = st.checkbox("異常値（100万超）を除外して表示", value=True)
chart_data = monthly.copy()
if exclude_outliers:
    chart_data = chart_data[chart_data["total"] < 1000000]

fig = go.Figure()
fig.add_trace(go.Bar(
    x=chart_data["label"],
    y=chart_data["total"],
    marker_color=["#e74c3c" if v > recent_avg else "#3498db" for v in chart_data["total"]],
    text=[f"¥{int(v):,}" for v in chart_data["total"]],
    textposition="outside",
))
fig.add_hline(
    y=recent_avg,
    line_dash="dash",
    line_color="gray",
    annotation_text=f"6ヶ月平均 ¥{int(recent_avg):,}",
)
fig.update_layout(
    height=400,
    xaxis_title="",
    yaxis_title="支出（円）",
    xaxis_tickangle=-45,
    showlegend=False,
)
st.plotly_chart(fig, use_container_width=True)

# ===== カテゴリ別 =====
st.markdown("---")
st.subheader("カテゴリ別支出")

col_left, col_right = st.columns(2)

# 全期間 vs 直近月の切り替え
with col_left:
    scope = st.radio("集計範囲", ["直近月", "全期間累計"], horizontal=True)
    if scope == "直近月":
        cat_df = get_category_totals(df, int(latest["year"]), int(latest["month"]))
    else:
        cat_df = get_category_totals(df)

    if not cat_df.empty:
        fig = px.pie(
            cat_df, values="amount", names="category",
            hole=0.4,
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

with col_right:
    if not cat_df.empty:
        fig = px.bar(
            cat_df, x="amount", y="category", orientation="h",
            text=[f"¥{int(v):,}" for v in cat_df["amount"]],
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(
            height=400,
            yaxis={"categoryorder": "total ascending"},
            xaxis_title="金額（円）", yaxis_title="",
        )
        st.plotly_chart(fig, use_container_width=True)

# ===== ポートフォリオ =====
if portfolio_url:
    st.markdown("---")
    st.subheader("📈 ポートフォリオ")

    try:
        with st.spinner("ポートフォリオを読み込み中..."):
            pf = cached_portfolio(portfolio_url)
    except Exception as e:
        st.error(f"ポートフォリオの読み込みエラー: {e}")
        pf = {"months": [], "assets": {}}

    if pf["months"] and pf["assets"]:
        months = pf["months"]

        # 総資産推移
        total_key = next((k for k in pf["assets"] if "合計" in k), None)
        if total_key:
            total_vals = pf["assets"][total_key]
            valid = [(m, v) for m, v in zip(months, total_vals) if v is not None]
            if valid:
                start_v = valid[0][1]
                end_v = valid[-1][1]
                gain = end_v - start_v
                gain_pct = gain / start_v * 100 if start_v > 0 else 0

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("運用資産", f"¥{int(end_v):,}")
                with col2:
                    st.metric("含み益+追加投資", f"¥{int(gain):,}", delta=f"+{gain_pct:.1f}%")
                with col3:
                    cash_key = next((k for k in pf["assets"] if "現金" in k), None)
                    if cash_key:
                        cash_vals = [v for v in pf["assets"][cash_key] if v is not None]
                        if cash_vals:
                            st.metric("現金(生活費)", f"¥{int(cash_vals[-1]):,}")

        # 資産推移チャート
        chart_rows = []
        for name, values in pf["assets"].items():
            if "合計" in name or "現金" in name:
                continue
            for m, v in zip(months, values):
                if v is not None:
                    chart_rows.append({"月": m, "銘柄": name, "金額": v})

        if chart_rows:
            pf_df = pd.DataFrame(chart_rows)
            fig = px.area(
                pf_df, x="月", y="金額", color="銘柄",
                groupnorm="",
            )
            fig.update_layout(height=400, yaxis_title="金額（円）")
            st.plotly_chart(fig, use_container_width=True)
