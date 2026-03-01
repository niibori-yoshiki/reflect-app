"""🤖 AI 相談 - 家計アドバイス"""

import os
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from dotenv import load_dotenv

from finance.ai_advisor import chat
from finance.data_loader import load_household_data, get_monthly_totals, get_category_totals
from finance.life_plan import dict_to_life_plan

load_dotenv()

st.set_page_config(page_title="AI 相談", page_icon="🤖", layout="wide")
st.title("🤖 AI 家計アドバイザー")

if "ai_messages" not in st.session_state:
    st.session_state.ai_messages = []

LIFE_PLAN_PATH = Path("data/life_plan.json")
household_url = st.session_state.get("household_url", os.getenv("HOUSEHOLD_SHEET_URL", ""))


def build_context():
    """家計データとライフプランのコンテキストを構築"""
    parts = []

    # 家計データ
    if household_url:
        try:
            df = load_household_data(household_url)
            if not df.empty:
                monthly = get_monthly_totals(df)
                recent = monthly.tail(6)
                avg = int(recent["total"].mean())
                latest = monthly.iloc[-1]

                cat_all = get_category_totals(df)
                cat_str = "\n".join(
                    f"  - {row['category']}: ¥{int(row['amount']):,} ({row['pct']}%)"
                    for _, row in cat_all.iterrows()
                )

                parts.append(f"""【家計データ（スプレッドシートから取得）】
- 直近月: {int(latest['year'])}年{int(latest['month'])}月 支出 ¥{int(latest['total']):,}
- 直近6ヶ月平均: ¥{avg:,} / 月
- 1人あたり: ¥{avg // 2:,} / 月
- データ期間: {len(monthly)}ヶ月分

カテゴリ別累計:
{cat_str}""")
        except Exception:
            pass

    # ライフプラン
    if LIFE_PLAN_PATH.exists():
        with open(LIFE_PLAN_PATH, encoding="utf-8") as f:
            plan_data = json.load(f)
        plan = dict_to_life_plan(plan_data)
        family_str = ", ".join(f"{m.name}({m.role})" for m in plan.family)
        parts.append(f"""【ライフプラン設定】
- 家族: {family_str}
- 月間収入: ¥{plan.monthly_income:,}
- 月間支出: ¥{plan.monthly_expense:,}
- 現在の貯蓄: ¥{plan.current_savings:,}
- 退職予定: {plan.retirement_age}歳""")

    return "\n\n".join(parts)


# コンテキスト読み込み
context = build_context()

if context:
    with st.expander("AIに共有される家計データ（自動取得）"):
        st.code(context)

# チャット履歴表示
for msg in st.session_state.ai_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 初回の提案テンプレート
if not st.session_state.ai_messages:
    st.markdown("**質問の例:**")
    cols = st.columns(3)
    templates = [
        "うちの家計で改善できるポイントは？",
        "子供1人の教育費、いくら貯めれば安心？",
        "住宅購入のベストなタイミングは？",
    ]
    for col, tmpl in zip(cols, templates):
        with col:
            if st.button(tmpl, use_container_width=True):
                st.session_state.ai_messages.append({"role": "user", "content": tmpl})
                st.rerun()

# ユーザー入力
user_input = st.chat_input("家計について質問してください...")
if user_input:
    st.session_state.ai_messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("考え中..."):
            response = chat(st.session_state.ai_messages, context=context)
        st.markdown(response)

    st.session_state.ai_messages.append({"role": "assistant", "content": response})

# クリアボタン
if st.session_state.ai_messages:
    if st.button("チャットをクリア"):
        st.session_state.ai_messages = []
        st.rerun()
