"""🎯 ライフプラン - 収入・子供・住宅のシミュレーション"""

import os
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import json
from pathlib import Path
from dotenv import load_dotenv

from finance.life_plan import (
    FamilyMember,
    LifePlanInput,
    estimate_education_events,
    estimate_retirement_fund,
    simulate_yearly_cashflow,
    life_plan_to_dict,
    dict_to_life_plan,
)
from finance.data_loader import load_household_data, get_monthly_totals

load_dotenv()

st.set_page_config(page_title="ライフプラン", page_icon="🎯", layout="wide")
st.title("🎯 ライフプラン シミュレーション")

SAVE_PATH = Path("data/life_plan.json")


def save_plan(data):
    SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SAVE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_saved():
    if SAVE_PATH.exists():
        with open(SAVE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return None


# 保存済みデータの復元
saved = load_saved()
defaults = dict_to_life_plan(saved) if saved else LifePlanInput()

# スプシからの実績支出を取得
household_url = st.session_state.get("household_url", os.getenv("HOUSEHOLD_SHEET_URL", ""))
actual_expense = None
if household_url:
    try:
        df = load_household_data(household_url)
        if not df.empty:
            monthly = get_monthly_totals(df)
            recent = monthly.tail(6)
            actual_expense = int(recent["total"].mean())
    except Exception:
        pass

# ===== Step 1: 家族構成 =====
st.subheader("Step 1: 家族構成")

col1, col2 = st.columns(2)
with col1:
    self_name = st.text_input("あなたの名前",
                               value=defaults.family[0].name if defaults.family else "よしき")
    self_birth_year = st.number_input("あなたの生年", min_value=1950, max_value=2010, step=1,
                                       value=defaults.family[0].birth_year if defaults.family else 1993)
with col2:
    spouse_name = st.text_input("配偶者の名前",
                                 value=next((m.name for m in defaults.family if m.role == "spouse"), "なな"))
    spouse_birth_year = st.number_input("配偶者の生年", min_value=1950, max_value=2010, step=1,
                                         value=next((m.birth_year for m in defaults.family if m.role == "spouse"), 1995))

# 子供
st.markdown("**お子さんの予定**")
num_children = st.number_input("子供の人数（予定含む）", min_value=0, max_value=5, step=1,
                                value=max(len([m for m in defaults.family if m.role == "child"]), 1))

children = []
child_defaults = [m for m in defaults.family if m.role == "child"]
for i in range(num_children):
    default_child = child_defaults[i] if i < len(child_defaults) else None
    cols = st.columns(3)
    with cols[0]:
        cname = st.text_input(f"子供{i+1}の名前",
                               value=default_child.name if default_child else f"子供{i+1}",
                               key=f"cn_{i}")
    with cols[1]:
        cyear = st.number_input(f"生年（予定）",
                                 min_value=2000, max_value=2035, step=1,
                                 value=default_child.birth_year if default_child else 2027 + i,
                                 key=f"cy_{i}")
    with cols[2]:
        edu = st.selectbox("教育プラン", ["all_public", "mixed", "all_private"],
                            format_func=lambda x: {"all_public": "全て公立", "mixed": "大学のみ私立", "all_private": "全て私立"}[x],
                            key=f"ep_{i}")
    children.append((FamilyMember(name=cname, birth_year=cyear, role="child"), edu))

st.markdown("---")

# ===== Step 2: 収入・支出 =====
st.subheader("Step 2: 世帯収入・支出")

if actual_expense:
    st.info(f"スプレッドシートの直近6ヶ月平均支出: **¥{actual_expense:,}** / 月")

col1, col2 = st.columns(2)
with col1:
    st.markdown("**月間手取り収入**")
    income_self = st.number_input("あなたの手取り（万円/月）", min_value=0, step=5, value=30, key="inc_self")
    income_spouse = st.number_input("配偶者の手取り（万円/月）", min_value=0, step=5, value=20, key="inc_spouse")
    monthly_income = (income_self + income_spouse) * 10000
    st.markdown(f"**世帯手取り合計: ¥{monthly_income:,} / 月**")

with col2:
    st.markdown("**月間支出**")
    if actual_expense:
        use_actual = st.checkbox("スプシの実績値を使用", value=True)
        monthly_expense = actual_expense if use_actual else st.number_input("月間支出（万円）", min_value=0, step=5, value=30) * 10000
    else:
        monthly_expense = st.number_input("月間支出（万円）", min_value=0, step=5,
                                           value=defaults.monthly_expense // 10000) * 10000
    st.markdown(f"**月間支出: ¥{monthly_expense:,}**")
    st.markdown(f"**月間貯蓄: ¥{monthly_income - monthly_expense:,}**")

current_savings = st.number_input("現在の貯蓄・運用資産（万円）", min_value=0, step=100,
                                   value=defaults.current_savings // 10000 if defaults.current_savings else 1600)

st.markdown("---")

# ===== Step 3: 住宅計画 =====
st.subheader("Step 3: 住宅計画")

housing = st.radio("住宅プラン", ["賃貸継続", "住宅購入予定"], horizontal=True)

housing_events = []
if housing == "住宅購入予定":
    col1, col2, col3 = st.columns(3)
    with col1:
        purchase_year = st.number_input("購入予定年", min_value=2026, max_value=2040, value=2030)
    with col2:
        house_price = st.number_input("物件価格（万円）", min_value=0, step=500, value=4500)
    with col3:
        down_payment = st.number_input("頭金（万円）", min_value=0, step=100, value=500)

    loan_amount = (house_price - down_payment) * 10000
    loan_years = st.slider("ローン年数", 20, 35, 35)
    loan_rate = st.slider("金利（%）", 0.0, 3.0, 1.0, 0.1)

    # 月額返済額の概算
    if loan_rate > 0:
        monthly_rate = loan_rate / 100 / 12
        n_payments = loan_years * 12
        monthly_payment = int(loan_amount * monthly_rate * (1 + monthly_rate)**n_payments / ((1 + monthly_rate)**n_payments - 1))
    else:
        monthly_payment = int(loan_amount / (loan_years * 12))

    st.markdown(f"""
    **住宅ローン試算:**
    - 借入額: ¥{loan_amount:,}
    - 月額返済: **¥{monthly_payment:,}**（現在の家賃と比較してください）
    - 総返済額: ¥{monthly_payment * loan_years * 12:,}
    """)

    from finance.life_plan import LifeEvent
    housing_events.append(LifeEvent(
        name="住宅購入（頭金）",
        year=purchase_year,
        cost=down_payment * 10000,
        category="housing",
    ))

st.markdown("---")

# ===== Step 4: 老後設定 =====
st.subheader("Step 4: 老後・運用設定")

col1, col2, col3, col4 = st.columns(4)
with col1:
    retirement_age = st.number_input("退職予定年齢", min_value=55, max_value=75, value=65)
with col2:
    pension = st.number_input("年金月額（万円）", min_value=0, step=1, value=15)
with col3:
    inflation = st.slider("インフレ率(%)", 0.0, 5.0, 1.0, 0.1)
with col4:
    inv_return = st.slider("運用利回り(%)", 0.0, 10.0, 4.0, 0.5)

st.markdown("---")

# ===== シミュレーション実行 =====
if st.button("🚀 シミュレーション実行", type="primary", width="stretch"):
    # 家族構成
    family = [FamilyMember(name=self_name or "自分", birth_year=self_birth_year, role="self")]
    if spouse_name:
        family.append(FamilyMember(name=spouse_name, birth_year=spouse_birth_year, role="spouse"))
    for child, _ in children:
        family.append(child)

    # イベント
    events = []
    for child, edu_plan in children:
        events.extend(estimate_education_events(child, edu_plan))
    events.extend(housing_events)

    plan = LifePlanInput(
        family=family,
        current_savings=current_savings * 10000,
        monthly_income=monthly_income,
        monthly_expense=monthly_expense,
        retirement_age=retirement_age,
        life_expectancy=90,
        inflation_rate=inflation,
        investment_return=inv_return,
        pension_monthly=pension * 10000,
        events=events,
    )

    save_plan(life_plan_to_dict(plan))

    retirement = estimate_retirement_fund(plan)
    current_age = 2026 - self_birth_year
    years_sim = max(90 - current_age, 30)
    cashflow = simulate_yearly_cashflow(plan, years=years_sim)

    # ===== 結果 =====
    st.markdown("---")
    st.subheader("📊 シミュレーション結果")

    # サマリー
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("月間貯蓄", f"¥{monthly_income - monthly_expense:,}")
    with col2:
        st.metric("老後不足額", f"¥{retirement['shortfall']:,}")
    with col3:
        st.metric("必要月間貯蓄", f"¥{retirement['required_monthly_saving']:,}")
    with col4:
        surplus = (monthly_income - monthly_expense) - retirement["required_monthly_saving"]
        if surplus >= 0:
            st.metric("余裕額", f"¥{surplus:,}/月", delta="達成可能")
        else:
            st.metric("不足額", f"¥{abs(surplus):,}/月", delta="要改善", delta_color="inverse")

    # キャッシュフローグラフ
    st.markdown("#### 資産推移シミュレーション")
    cf_df = pd.DataFrame(cashflow)

    fig = go.Figure()

    # 資産がプラスの部分
    fig.add_trace(go.Scatter(
        x=cf_df["age"], y=cf_df["cumulative_savings"],
        name="累計資産",
        fill="tozeroy",
        fillcolor="rgba(52, 152, 219, 0.3)",
        line=dict(color="#3498db", width=2),
    ))

    fig.add_hline(y=0, line_dash="dash", line_color="red")
    fig.add_vline(x=retirement_age, line_dash="dash", line_color="gray",
                  annotation_text=f"退職({retirement_age}歳)")

    # イベントマーカー
    events_df = cf_df[cf_df["events"] != ""]
    if not events_df.empty:
        fig.add_trace(go.Scatter(
            x=events_df["age"], y=events_df["cumulative_savings"],
            mode="markers",
            name="ライフイベント",
            marker=dict(size=12, color="#e74c3c", symbol="diamond"),
            text=events_df["events"],
            hovertemplate="%{text}<br>%{y:,}円<extra></extra>",
        ))

    fig.update_layout(
        xaxis_title="年齢",
        yaxis_title="累計資産（円）",
        height=500,
        hovermode="x unified",
    )
    st.plotly_chart(fig, width="stretch")

    # 赤字警告
    deficit = cf_df[cf_df["cumulative_savings"] < 0]
    if not deficit.empty:
        st.error(f"⚠️ {int(deficit.iloc[0]['age'])}歳で資金がマイナスになります")
    else:
        min_savings = cf_df["cumulative_savings"].min()
        st.success(f"✅ 生涯を通じて資金がマイナスになりません（最低点: ¥{int(min_savings):,}）")

    # 教育費タイムライン
    edu_events = [e for e in events if e.category == "education"]
    if edu_events:
        st.markdown("#### 📚 教育費タイムライン")
        edu_data = [{"年": e.year, "年齢": e.year - self_birth_year, "イベント": e.name,
                     "費用": f"¥{e.cost:,}", "備考": e.description} for e in edu_events]
        st.dataframe(pd.DataFrame(edu_data), width="stretch", hide_index=True)

    # 住宅ローンの影響
    if housing == "住宅購入予定":
        st.markdown("#### 🏠 住宅ローンの影響")
        st.markdown(f"""
        - 頭金支出: ¥{down_payment * 10000:,}（{purchase_year}年）
        - 月額返済: ¥{monthly_payment:,}
        - ローン完済: {purchase_year + loan_years}年（{purchase_year + loan_years - self_birth_year}歳）

        ※ 住宅購入後は家賃が不要になるため、月間支出からローン返済額との差額が変動します。
        現在の家賃を教えていただければ、より正確なシミュレーションが可能です。
        """)

    # 詳細テーブル
    with st.expander("年次キャッシュフロー詳細"):
        display = cf_df.copy()
        for col in ["annual_income", "annual_expense", "event_costs", "investment_gain", "annual_balance", "cumulative_savings"]:
            display[col] = display[col].apply(lambda x: f"¥{int(x):,}")
        display.columns = ["年", "年齢", "年間収入", "年間支出", "イベント費", "イベント", "運用益", "年間収支", "累計資産"]
        st.dataframe(display, width="stretch", hide_index=True)
