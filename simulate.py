"""ライフプラン・シミュレーション（会話用）

前提条件:
- 夫（よしき）手取り35万/月、年収480万+残業代、正社員
- 妻（なな）手取り40万/月、正社員
- 2026/05: 妻 産休開始、2026/07: 第1子出産
- 2026/08-12: 夫 育休
- 2028/07頃: 第2子出産（2歳差）
- 住居: 用賀1LDK 16万賃貸 → 子供成長後に購入検討
- 資産: 運用1,426万 + 現金232万 = 1,658万 (2026/03時点)
- 共同支出: 月23万（予算ベース）
"""

from dataclasses import dataclass

# ============================================================
# 定数・前提
# ============================================================

# --- 収入（手取りベース） ---
HUSBAND_MONTHLY_TAKE_HOME = 35.0  # 万円
WIFE_MONTHLY_TAKE_HOME = 40.0
HUSBAND_GROSS_MONTHLY = 48.0  # 額面推定
WIFE_GROSS_MONTHLY = 55.0

# --- ボーナス（年2回、手取りベース推定） ---
HUSBAND_BONUS_YEARLY = 80.0  # 万円（年間手取り推定）
WIFE_BONUS_YEARLY = 100.0

# --- 育休給付金 ---
# 最初180日: 額面67%（非課税・社保免除なので手取りとほぼ同等）
# 180日以降: 額面50%
IKUKYU_RATE_FIRST_6M = 0.67
IKUKYU_RATE_AFTER = 0.50
# 出産手当金: 額面の約2/3
MATERNITY_RATE = 0.67

# --- 支出 ---
CURRENT_MONTHLY_EXPENSE = 33.0  # 共同23万 + 個人計10万の推定
RENT = 16.0  # 家賃（支出内訳）

# --- 子供関連の追加コスト（万円/月） ---
CHILD_COST_0_2 = 3.0    # 0-2歳: おむつ・ミルク等
CHILD_COST_3_5 = 5.0    # 3-5歳: 保育園（無償化後の実費）
CHILD_COST_6_12 = 6.0   # 小学生: 学費+習い事+食費増
CHILD_COST_13_15 = 8.0  # 中学生
CHILD_COST_16_18 = 10.0 # 高校生
CHILD_COST_19_22 = 15.0 # 大学（私立想定、仕送り含む）

# --- 保育園コスト（月額、0-2歳は有料） ---
NURSERY_COST_0_2 = 5.0  # 認可保育園0-2歳クラス（世田谷区目安）

# --- 住居 ---
# 子供が小学生になったら引っ越し（2LDK以上）
RENT_AFTER_MOVE = 22.0  # 用賀周辺2LDK-3LDK想定

# --- 資産 ---
INITIAL_INVESTMENT = 1426.0  # 万円
INITIAL_CASH = 232.0
INVESTMENT_RETURN = 0.04  # 年利4%（インデックス想定）
MONTHLY_NISA_CONTRIBUTION = 30.0  # 月のNISA積立額推定

# --- インフレ ---
INFLATION_RATE = 0.01  # 年1%

# --- 昇給 ---
SALARY_GROWTH_RATE = 0.015  # 年1.5%


# ============================================================
# シミュレーション
# ============================================================

def child_monthly_cost(age):
    """子供の年齢別月額コスト"""
    if age < 0:
        return 0
    elif age <= 2:
        return CHILD_COST_0_2
    elif age <= 5:
        return CHILD_COST_3_5
    elif age <= 12:
        return CHILD_COST_6_12
    elif age <= 15:
        return CHILD_COST_13_15
    elif age <= 18:
        return CHILD_COST_16_18
    elif age <= 22:
        return CHILD_COST_19_22
    else:
        return 0


def simulate(scenario_name, wife_plan):
    """
    wife_plan: list of (year, monthly_income_万円) タプル
    各年の妻の月収を指定する辞書 {year: monthly_income}
    """
    print(f"\n{'='*80}")
    print(f"  シナリオ: {scenario_name}")
    print(f"{'='*80}")

    # 初期状態
    investment = INITIAL_INVESTMENT
    cash = INITIAL_CASH
    year_start = 2026
    simulation_years = 25  # 2026-2050

    # 子供の誕生年
    child1_birth = 2026  # 7月生まれ → その年は半年分
    child2_birth = 2028

    husband_base = HUSBAND_MONTHLY_TAKE_HOME
    husband_bonus = HUSBAND_BONUS_YEARLY

    print(f"\n  {'年':>6} {'夫収入':>8} {'妻収入':>8} {'支出':>8} {'年間収支':>10} "
          f"{'運用資産':>10} {'現金':>8} {'純資産':>10}  備考")
    print(f"  {'-'*100}")

    for i in range(simulation_years):
        year = year_start + i
        notes = []

        # --- 夫の収入 ---
        h_monthly = husband_base * (1 + SALARY_GROWTH_RATE) ** i
        h_bonus = husband_bonus * (1 + SALARY_GROWTH_RATE) ** i

        # 夫の育休 (2026/08-12: 5ヶ月)
        if year == 2026:
            # 1-7月: 通常 (7ヶ月), 8-12月: 育休 (5ヶ月)
            h_work_months = 7
            h_ikukyu_months = 5
            h_income = (h_monthly * h_work_months +
                       HUSBAND_GROSS_MONTHLY * IKUKYU_RATE_FIRST_6M * h_ikukyu_months +
                       h_bonus * 0.5)  # ボーナス半額想定
            notes.append("夫育休8-12月")
        else:
            h_income = h_monthly * 12 + h_bonus

        # --- 妻の収入 ---
        w_income = wife_plan.get(year, 0) * 12
        if year in wife_plan:
            pass  # プランで指定済み

        # ボーナス（フル勤務の年のみ）
        w_bonus_base = WIFE_BONUS_YEARLY * (1 + SALARY_GROWTH_RATE) ** i
        if wife_plan.get(year, 0) >= WIFE_MONTHLY_TAKE_HOME * 0.9:
            w_income += w_bonus_base
        elif wife_plan.get(year, 0) >= WIFE_MONTHLY_TAKE_HOME * 0.7:
            w_income += w_bonus_base * 0.5  # 時短はボーナス半額

        total_income = h_income + w_income

        # --- 支出 ---
        base_expense = CURRENT_MONTHLY_EXPENSE * (1 + INFLATION_RATE) ** i

        # 子供コスト
        child1_age = year - child1_birth
        child2_age = year - child2_birth
        child_cost_monthly = child_monthly_cost(child1_age) + child_monthly_cost(child2_age)

        # 保育園コスト（共働きの場合）
        nursery_cost = 0
        wife_working = wife_plan.get(year, 0) > 0
        if wife_working:
            if 0 <= child1_age <= 2:
                nursery_cost += NURSERY_COST_0_2
            if 0 <= child2_age <= 2:
                nursery_cost += NURSERY_COST_0_2

        # 住居（子供が小学生になったら広い部屋へ）
        rent = RENT
        if child1_age >= 4:  # 小学校入学前に引っ越し
            rent = RENT_AFTER_MOVE
            if child1_age == 4 and i > 0:
                notes.append("広い部屋に引越")

        monthly_expense = base_expense - RENT + rent + child_cost_monthly + nursery_cost
        yearly_expense = monthly_expense * 12

        # 特別費用
        special = 0
        if child1_age == 0:
            special += 50  # 出産費用（自己負担分）+ ベビー用品
            notes.append("第1子出産")
        if child2_age == 0:
            special += 40
            notes.append("第2子出産")
        if child1_age == 6:
            special += 30  # ランドセル等
            notes.append("第1子小学校入学")
        if child2_age == 6:
            special += 30
            notes.append("第2子小学校入学")
        if child1_age == 15:
            notes.append("第1子高校入学")
        if child1_age == 18:
            special += 100  # 大学入学金等
            notes.append("第1子大学入学")
        if child2_age == 18:
            special += 100
            notes.append("第2子大学入学")

        yearly_expense += special

        # --- 年間収支 ---
        annual_balance = total_income - yearly_expense

        # --- 資産運用 ---
        # NISA積立（収支がプラスの場合のみ追加投資）
        if annual_balance > 0:
            new_investment = min(annual_balance * 0.6, MONTHLY_NISA_CONTRIBUTION * 12)
            cash_addition = annual_balance - new_investment
        else:
            new_investment = 0
            cash_addition = annual_balance  # マイナスなら現金取り崩し

        investment = investment * (1 + INVESTMENT_RETURN) + new_investment
        cash = cash + cash_addition

        # 現金がマイナスになったら投資取り崩し
        if cash < 0:
            investment += cash  # 投資から補填
            cash = 0

        net_worth = investment + cash

        # --- 妻収入の注釈 ---
        w_monthly = wife_plan.get(year, 0)
        if year == 2026 and w_monthly < WIFE_MONTHLY_TAKE_HOME:
            notes.append("妻産休")
        elif w_monthly == 0:
            if year > 2026:
                pass  # 退職/育休
        elif w_monthly < WIFE_MONTHLY_TAKE_HOME * 0.7:
            if "育休" not in " ".join(notes):
                notes.append("妻育休")
        elif w_monthly < WIFE_MONTHLY_TAKE_HOME * 0.9:
            notes.append("妻時短")

        note_str = ", ".join(notes) if notes else ""

        print(f"  {year:>6} {h_income:>7.0f}万 {w_income:>7.0f}万 {yearly_expense:>7.0f}万 "
              f"{annual_balance:>+9.0f}万 {investment:>9.0f}万 {cash:>7.0f}万 "
              f"{net_worth:>9.0f}万  {note_str}")

    print(f"\n  {year}年時点の純資産: {net_worth:,.0f}万円")
    return net_worth


def main():
    print("=" * 80)
    print("  ライフプラン・シミュレーション")
    print("  前提: 夫35万/妻40万(手取り), 共同支出23万+個人10万≒33万/月")
    print("  資産: 運用1,426万 + 現金232万 = 1,658万 (2026/03)")
    print("  第1子: 2026/07, 第2子: 2028/07予定")
    print("=" * 80)

    wife_gross = WIFE_GROSS_MONTHLY
    wife_take_home = WIFE_MONTHLY_TAKE_HOME

    # 育休中の手取り相当額
    ikukyu_67 = wife_gross * IKUKYU_RATE_FIRST_6M  # ≒37万（非課税）
    ikukyu_50 = wife_gross * IKUKYU_RATE_AFTER      # ≒28万
    maternity = wife_gross * MATERNITY_RATE          # ≒37万

    # ============================================================
    # シナリオA: 妻が育休後フルタイム復帰（各1年育休）
    # ============================================================
    # 2026: 1-4月フル(4ヶ月) + 5-7月産休(3ヶ月) + 8-12月育休(5ヶ月)
    #   → (40*4 + 37*3 + 37*5) / 12 ≒ 38万/月相当
    # 2027: 1-3月育休50%(3ヶ月) + 4-12月フル復帰(9ヶ月)
    #   → (28*3 + 40*9) / 12 ≒ 37万/月相当
    # 2028: 1-4月フル(4ヶ月) + 5-12月産休育休(8ヶ月) ← 第2子
    #   → (40*4 + 37*8) / 12 ≒ 38万/月相当
    # 2029: 1-6月育休(6ヶ月) + 7-12月フル復帰(6ヶ月)
    #   → (28*3 + 37*3 + 40*6) / 12 ≒ 36万/月相当
    # 2030～: フルタイム
    plan_a = {}
    for y in range(2026, 2051):
        if y == 2026:
            plan_a[y] = (40*4 + 37*3 + 37*5) / 12
        elif y == 2027:
            plan_a[y] = (28*3 + 40*9) / 12
        elif y == 2028:
            plan_a[y] = (40*4 + 37*8) / 12
        elif y == 2029:
            plan_a[y] = (28*3 + 37*3 + 40*6) / 12
        else:
            plan_a[y] = wife_take_home
    result_a = simulate("A: 妻 育休→フルタイム復帰（各1年育休）", plan_a)

    # ============================================================
    # シナリオB: 妻が育休後 時短勤務（給与75%）
    # ============================================================
    jitan = wife_take_home * 0.75  # 30万
    plan_b = {}
    for y in range(2026, 2051):
        if y == 2026:
            plan_b[y] = (40*4 + 37*3 + 37*5) / 12
        elif y == 2027:
            plan_b[y] = (28*3 + jitan*9) / 12
        elif y == 2028:
            plan_b[y] = (jitan*4 + 37*8) / 12
        elif y == 2029:
            plan_b[y] = (28*3 + 37*3 + jitan*6) / 12
        elif y <= 2034:  # 下の子が小学生になるまで時短
            plan_b[y] = jitan
        else:
            plan_b[y] = wife_take_home
    result_b = simulate("B: 妻 育休→時短勤務（下の子小学校まで）→フル復帰", plan_b)

    # ============================================================
    # シナリオC: 妻が第1子育休後に退職
    # ============================================================
    plan_c = {}
    for y in range(2026, 2051):
        if y == 2026:
            plan_c[y] = (40*4 + 37*3 + 37*5) / 12
        elif y == 2027:
            plan_c[y] = 28 * 6 / 12  # 半年育休後退職
        else:
            plan_c[y] = 0  # 専業主婦
    result_c = simulate("C: 妻 育休後に退職（専業主婦）", plan_c)

    # ============================================================
    # シナリオD: 連続育休（第2子まで続けて復帰）
    # ============================================================
    plan_d = {}
    for y in range(2026, 2051):
        if y == 2026:
            plan_d[y] = (40*4 + 37*3 + 37*5) / 12
        elif y == 2027:
            plan_d[y] = ikukyu_50  # 育休継続
        elif y == 2028:
            plan_d[y] = (ikukyu_50*4 + maternity*8) / 12  # 第2子産休
        elif y == 2029:
            plan_d[y] = (ikukyu_67*6 + ikukyu_50*6) / 12  # 第2子育休
        elif y == 2030:
            plan_d[y] = (ikukyu_50*3 + wife_take_home*9) / 12  # 復帰
        else:
            plan_d[y] = wife_take_home
    result_d = simulate("D: 妻 連続育休（2人分まとめて）→フル復帰", plan_d)

    # ============================================================
    # まとめ
    # ============================================================
    print(f"\n{'='*80}")
    print(f"  シナリオ比較（2050年時点の純資産）")
    print(f"{'='*80}")
    print(f"  A: フルタイム復帰     → {result_a:>10,.0f}万円")
    print(f"  B: 時短→フル復帰      → {result_b:>10,.0f}万円")
    print(f"  C: 退職（専業主婦）   → {result_c:>10,.0f}万円")
    print(f"  D: 連続育休→フル復帰  → {result_d:>10,.0f}万円")
    print()
    print(f"  A-C差額（退職の機会コスト）: {result_a - result_c:,.0f}万円")
    print(f"  A-B差額（時短の影響）:       {result_a - result_b:,.0f}万円")


if __name__ == "__main__":
    main()
