"""🤖 AI 相談 - 家計改善アドバイス"""

import streamlit as st
import pandas as pd
import json
from pathlib import Path

from finance.ai_advisor import analyze_spending, life_plan_advice, chat
from finance.analyzer import monthly_summary, category_breakdown
from finance.life_plan import (
    estimate_retirement_fund,
    simulate_yearly_cashflow,
    dict_to_life_plan,
)

st.set_page_config(page_title="AI 相談", page_icon="🤖", layout="wide")
st.title("🤖 AI 家計アドバイザー")

# セッション管理
if "ai_chat_messages" not in st.session_state:
    st.session_state.ai_chat_messages = []

LIFE_PLAN_PATH = Path("data/life_plan.json")

tab1, tab2, tab3 = st.tabs(["💬 自由相談", "📊 支出分析", "🎯 ライフプラン相談"])

# ===== タブ1: 自由相談 =====
with tab1:
    st.markdown("家計やお金に関することを自由に相談できます。")

    # コンテキスト情報の構築
    context = ""
    if LIFE_PLAN_PATH.exists():
        with open(LIFE_PLAN_PATH, encoding="utf-8") as f:
            plan_data = json.load(f)
        plan = dict_to_life_plan(plan_data)
        context = f"""
家族構成: {len(plan.family)}人
月間収入: ¥{plan.monthly_income:,}
月間支出: ¥{plan.monthly_expense:,}
現在の貯蓄: ¥{plan.current_savings:,}
退職予定: {plan.retirement_age}歳
"""

    # チャット履歴表示
    for msg in st.session_state.ai_chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ユーザー入力
    user_input = st.chat_input("家計について質問してください...")
    if user_input:
        st.session_state.ai_chat_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("考え中..."):
                response = chat(st.session_state.ai_chat_messages, context=context)
            st.markdown(response)

        st.session_state.ai_chat_messages.append({"role": "assistant", "content": response})

    if st.button("チャットをクリア", key="clear_chat"):
        st.session_state.ai_chat_messages = []
        st.rerun()

# ===== タブ2: 支出分析 =====
with tab2:
    st.markdown("スプレッドシートの月次データをAIが分析し、改善ポイントを提案します。")

    url = st.session_state.get("spreadsheet_url", "")
    credentials_path = Path("credentials/service_account.json")

    if not url:
        st.info("サイドバーにスプレッドシートのURLを入力してください。")
    elif not credentials_path.exists():
        st.warning("credentials/service_account.json が配置されていません。")
    else:
        from finance.sheets import open_spreadsheet_by_url, get_sheet_data
        from finance.parser import load_all_months

        @st.cache_data(ttl=300)
        def load_finance_data(spreadsheet_url: str) -> pd.DataFrame:
            spreadsheet = open_spreadsheet_by_url(spreadsheet_url)
            return load_all_months(spreadsheet, get_sheet_data)

        try:
            df = load_finance_data(url)
        except Exception as e:
            st.error(f"データ読み込みエラー: {e}")
            df = pd.DataFrame()

        if not df.empty:
            available_periods = df.groupby(["year", "month"]).size().reset_index()[["year", "month"]]
            available_periods = available_periods.sort_values(["year", "month"], ascending=False)

            col1, col2 = st.columns(2)
            with col1:
                year = st.selectbox("年", available_periods["year"].unique(), key="ai_year")
            with col2:
                months = available_periods[available_periods["year"] == year]["month"].tolist()
                month = st.selectbox("月", months, key="ai_month")

            if st.button("🔍 AIに分析してもらう", type="primary"):
                summary = monthly_summary(df, year, month)
                cats = category_breakdown(df, year, month, "expense")
                cat_list = cats.to_dict("records") if not cats.empty else []

                with st.spinner("AIが分析中..."):
                    advice = analyze_spending(summary, cat_list)
                st.markdown("### 📝 AIの分析結果")
                st.markdown(advice)

# ===== タブ3: ライフプラン相談 =====
with tab3:
    st.markdown("ライフプランのシミュレーション結果をAIが評価し、アドバイスします。")

    if not LIFE_PLAN_PATH.exists():
        st.info("先に「🎯 ライフプラン」ページでシミュレーションを実行してください。")
    else:
        with open(LIFE_PLAN_PATH, encoding="utf-8") as f:
            plan_data = json.load(f)

        plan = dict_to_life_plan(plan_data)

        st.markdown(f"""
        **現在の設定:**
        - 月間収入: ¥{plan.monthly_income:,} / 月間支出: ¥{plan.monthly_expense:,}
        - 貯蓄: ¥{plan.current_savings:,}
        - 退職予定: {plan.retirement_age}歳
        """)

        if st.button("🤖 AIにライフプランを相談", type="primary"):
            retirement = estimate_retirement_fund(plan)
            cashflow = simulate_yearly_cashflow(plan)

            # キャッシュフローのサマリー
            cf_df = pd.DataFrame(cashflow)
            deficit_rows = cf_df[cf_df["cumulative_savings"] < 0]
            deficit_age = int(deficit_rows.iloc[0]["age"]) if not deficit_rows.empty else "なし"

            cashflow_summary = {
                "years": len(cashflow),
                "deficit_age": deficit_age,
                "max_savings": int(cf_df["cumulative_savings"].max()),
            }

            with st.spinner("AIがライフプランを評価中..."):
                advice = life_plan_advice(retirement, cashflow_summary)

            st.markdown("### 📝 AIのアドバイス")
            st.markdown(advice)
