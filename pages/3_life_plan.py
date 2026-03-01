"""🎯 ライフプラン - 教育費・老後資金シミュレーション"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import json
from pathlib import Path

from finance.life_plan import (
    FamilyMember,
    LifeEvent,
    LifePlanInput,
    estimate_education_events,
    estimate_retirement_fund,
    simulate_yearly_cashflow,
    life_plan_to_dict,
    dict_to_life_plan,
)

st.set_page_config(page_title="ライフプラン", page_icon="🎯", layout="wide")
st.title("🎯 ライフプラン シミュレーション")

SAVE_PATH = Path("data/life_plan.json")


def save_plan(data: dict):
    SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SAVE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_plan() -> dict | None:
    if SAVE_PATH.exists():
        with open(SAVE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return None


# 保存済みデータの読み込み
saved = load_plan()
defaults = dict_to_life_plan(saved) if saved else LifePlanInput()

# ===== 入力セクション =====
st.subheader("👨‍👩‍👧‍👦 家族構成")

col1, col2 = st.columns(2)
with col1:
    self_name = st.text_input("あなたの名前", value=defaults.family[0].name if defaults.family else "")
    self_birth_year = st.number_input(
        "あなたの生年",
        min_value=1950, max_value=2010, step=1,
        value=defaults.family[0].birth_year if defaults.family else 1990,
    )
with col2:
    spouse_name = st.text_input("配偶者の名前（任意）",
                                value=next((m.name for m in defaults.family if m.role == "spouse"), ""))
    spouse_birth_year = st.number_input(
        "配偶者の生年",
        min_value=1950, max_value=2010, step=1,
        value=next((m.birth_year for m in defaults.family if m.role == "spouse"), 1990),
    )

# 子供の情報
st.markdown("**子供の情報**")
num_children = st.number_input(
    "子供の人数", min_value=0, max_value=5, step=1,
    value=len([m for m in defaults.family if m.role == "child"]),
)

children = []
child_defaults = [m for m in defaults.family if m.role == "child"]
for i in range(num_children):
    cols = st.columns(3)
    default_child = child_defaults[i] if i < len(child_defaults) else None
    with cols[0]:
        cname = st.text_input(f"子供{i+1}の名前", value=default_child.name if default_child else f"子供{i+1}", key=f"child_name_{i}")
    with cols[1]:
        cyear = st.number_input(f"子供{i+1}の生年", min_value=2000, max_value=2030, step=1,
                                value=default_child.birth_year if default_child else 2020, key=f"child_year_{i}")
    with cols[2]:
        edu_plan = st.selectbox(f"教育プラン", ["all_public", "mixed", "all_private"],
                                format_func=lambda x: {"all_public": "全て公立", "mixed": "大学のみ私立", "all_private": "全て私立"}[x],
                                key=f"edu_plan_{i}")
    children.append((FamilyMember(name=cname, birth_year=cyear, role="child"), edu_plan))

st.markdown("---")

# 収支・資産情報
st.subheader("💰 収支・資産")
col1, col2, col3 = st.columns(3)
with col1:
    monthly_income = st.number_input("月間収入（万円）", min_value=0, step=5,
                                      value=defaults.monthly_income // 10000)
with col2:
    monthly_expense = st.number_input("月間支出（万円）", min_value=0, step=5,
                                       value=defaults.monthly_expense // 10000)
with col3:
    current_savings = st.number_input("現在の貯蓄（万円）", min_value=0, step=100,
                                       value=defaults.current_savings // 10000)

st.markdown("---")

# 老後設定
st.subheader("🏖️ 老後設定")
col1, col2, col3 = st.columns(3)
with col1:
    retirement_age = st.number_input("退職予定年齢", min_value=55, max_value=75, step=1,
                                      value=defaults.retirement_age)
with col2:
    pension_monthly = st.number_input("年金月額（万円）", min_value=0, step=1,
                                       value=defaults.pension_monthly // 10000)
with col3:
    life_expectancy = st.number_input("想定寿命", min_value=80, max_value=100, step=1,
                                       value=defaults.life_expectancy)

col1, col2 = st.columns(2)
with col1:
    inflation_rate = st.slider("インフレ率 (%)", 0.0, 5.0, defaults.inflation_rate, 0.1)
with col2:
    investment_return = st.slider("運用利回り (%)", 0.0, 10.0, defaults.investment_return, 0.5)

st.markdown("---")

# ===== シミュレーション実行 =====
if st.button("🚀 シミュレーション実行", type="primary", use_container_width=True):
    # 家族構成の組み立て
    family = [FamilyMember(name=self_name or "自分", birth_year=self_birth_year, role="self")]
    if spouse_name:
        family.append(FamilyMember(name=spouse_name, birth_year=spouse_birth_year, role="spouse"))
    for child, _ in children:
        family.append(child)

    # 教育費イベントの生成
    events = []
    for child, edu_plan in children:
        events.extend(estimate_education_events(child, edu_plan))

    # LifePlanInput の組み立て
    plan_input = LifePlanInput(
        family=family,
        current_savings=current_savings * 10000,
        monthly_income=monthly_income * 10000,
        monthly_expense=monthly_expense * 10000,
        retirement_age=retirement_age,
        life_expectancy=life_expectancy,
        inflation_rate=inflation_rate,
        investment_return=investment_return,
        pension_monthly=pension_monthly * 10000,
        events=events,
    )

    # 設定を保存
    save_plan(life_plan_to_dict(plan_input))

    # 老後資金試算
    retirement = estimate_retirement_fund(plan_input)

    # キャッシュフロー シミュレーション
    years_sim = life_expectancy - (2026 - self_birth_year)
    cashflow = simulate_yearly_cashflow(plan_input, years=max(years_sim, 30))

    # ===== 結果表示 =====
    st.markdown("---")
    st.subheader("📊 シミュレーション結果")

    # 老後資金サマリー
    st.markdown("#### 🏖️ 老後資金")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("老後に必要な総額", f"¥{retirement['total_retirement_cost']:,}")
    with col2:
        st.metric("年金総額", f"¥{retirement['total_pension']:,}")
    with col3:
        st.metric("不足額", f"¥{retirement['shortfall']:,}")
    with col4:
        st.metric("必要月間貯蓄", f"¥{retirement['required_monthly_saving']:,}")

    current_monthly_savings = monthly_income * 10000 - monthly_expense * 10000
    if retirement["required_monthly_saving"] > current_monthly_savings:
        gap = retirement["required_monthly_saving"] - current_monthly_savings
        st.warning(f"⚠️ 現在の月間貯蓄（¥{current_monthly_savings:,}）では月 ¥{gap:,} 不足しています")
    else:
        st.success("✅ 現在の貯蓄ペースで老後資金を確保できる見込みです")

    # キャッシュフローグラフ
    st.markdown("#### 📈 年間キャッシュフロー推移")
    cf_df = pd.DataFrame(cashflow)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=cf_df["age"],
        y=cf_df["cumulative_savings"],
        name="累計貯蓄",
        fill="tozeroy",
        line={"color": "#3498db"},
    ))

    # 赤字ライン
    fig.add_hline(y=0, line_dash="dash", line_color="red", annotation_text="赤字ライン")

    # 退職年齢ライン
    fig.add_vline(x=retirement_age, line_dash="dash", line_color="gray",
                  annotation_text=f"退職({retirement_age}歳)")

    # イベントマーカー
    event_rows = cf_df[cf_df["events"] != ""]
    if not event_rows.empty:
        fig.add_trace(go.Scatter(
            x=event_rows["age"],
            y=event_rows["cumulative_savings"],
            mode="markers+text",
            name="ライフイベント",
            text=event_rows["events"],
            textposition="top center",
            marker={"size": 10, "color": "#e74c3c"},
        ))

    fig.update_layout(
        xaxis_title="年齢",
        yaxis_title="累計貯蓄（円）",
        height=500,
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # 資金がマイナスになるポイント
    deficit_rows = cf_df[cf_df["cumulative_savings"] < 0]
    if not deficit_rows.empty:
        deficit_age = deficit_rows.iloc[0]["age"]
        st.error(f"⚠️ {int(deficit_age)}歳で資金がマイナスになる予測です。支出の見直しや追加の収入源を検討してください。")

    # 教育費タイムライン
    if events:
        st.markdown("#### 📚 教育費タイムライン")
        edu_data = []
        for e in events:
            edu_data.append({
                "年": e.year,
                "イベント": e.name,
                "費用": f"¥{e.cost:,}",
                "備考": e.description,
            })
        st.dataframe(pd.DataFrame(edu_data), use_container_width=True, hide_index=True)

    # 詳細テーブル
    with st.expander("年次キャッシュフロー詳細"):
        display_cf = cf_df.copy()
        for col in ["annual_income", "annual_expense", "event_costs", "investment_gain", "annual_balance", "cumulative_savings"]:
            display_cf[col] = display_cf[col].apply(lambda x: f"¥{x:,}")
        display_cf.columns = ["年", "年齢", "年間収入", "年間支出", "イベント費用", "イベント", "運用益", "年間収支", "累計貯蓄"]
        st.dataframe(display_cf, use_container_width=True, hide_index=True)
