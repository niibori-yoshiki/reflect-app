"""退職 / パート / 時短復帰 の3シナリオ資産推移グラフ"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import os

# --- 日本語フォント設定 ---
JP_FONT = FontProperties(fname="/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf")

# ============================================================
# 定数
# ============================================================
HUSBAND_MONTHLY = 35.0
WIFE_MONTHLY = 40.0
HUSBAND_GROSS = 48.0
WIFE_GROSS = 55.0
HUSBAND_BONUS = 80.0
WIFE_BONUS = 100.0

IKUKYU_67 = WIFE_GROSS * 0.67
IKUKYU_50 = WIFE_GROSS * 0.50
MATERNITY = WIFE_GROSS * 0.67

CURRENT_MONTHLY_EXPENSE = 33.0
RENT = 16.0
RENT_BIG = 22.0

CHILD_COSTS = {
    (0, 2): 3.0, (3, 5): 5.0, (6, 12): 6.0,
    (13, 15): 8.0, (16, 18): 10.0, (19, 22): 15.0,
}
NURSERY_0_2 = 5.0

INITIAL_INV = 1426.0
INITIAL_CASH = 232.0
INV_RETURN = 0.04
NISA_MAX = 30.0 * 12
INFLATION = 0.01
SALARY_GROWTH = 0.015

YEARS = list(range(2026, 2051))


def child_cost(age):
    if age < 0 or age > 22:
        return 0
    for (lo, hi), cost in CHILD_COSTS.items():
        if lo <= age <= hi:
            return cost
    return 0


def special_costs(c1_age, c2_age):
    s = 0
    if c1_age == 0: s += 50
    if c2_age == 0: s += 40
    if c1_age == 6: s += 30
    if c2_age == 6: s += 30
    if c1_age == 18: s += 100
    if c2_age == 18: s += 100
    return s


def simulate(wife_plan):
    """年ごとの純資産リストを返す"""
    inv = INITIAL_INV
    cash = INITIAL_CASH
    results = []

    for i, year in enumerate(YEARS):
        # --- 夫収入 ---
        h_m = HUSBAND_MONTHLY * (1 + SALARY_GROWTH) ** i
        h_b = HUSBAND_BONUS * (1 + SALARY_GROWTH) ** i
        if year == 2026:
            h_income = h_m * 7 + HUSBAND_GROSS * 0.67 * 5 + h_b * 0.5
        else:
            h_income = h_m * 12 + h_b

        # --- 妻収入 ---
        w_monthly = wife_plan.get(year, 0)
        w_income = w_monthly * 12
        w_b = WIFE_BONUS * (1 + SALARY_GROWTH) ** i
        if w_monthly >= WIFE_MONTHLY * 0.9:
            w_income += w_b
        elif w_monthly >= WIFE_MONTHLY * 0.7:
            w_income += w_b * 0.5

        total_income = h_income + w_income

        # --- 支出 ---
        base = CURRENT_MONTHLY_EXPENSE * (1 + INFLATION) ** i
        c1_age = year - 2026
        c2_age = year - 2028
        cc = child_cost(c1_age) + child_cost(c2_age)
        nursery = 0
        if w_monthly > 0:
            if 0 <= c1_age <= 2: nursery += NURSERY_0_2
            if 0 <= c2_age <= 2: nursery += NURSERY_0_2
        rent = RENT_BIG if c1_age >= 4 else RENT
        monthly_exp = base - RENT + rent + cc + nursery
        yearly_exp = monthly_exp * 12 + special_costs(c1_age, c2_age)

        # --- 収支 ---
        balance = total_income - yearly_exp
        if balance > 0:
            new_inv = min(balance * 0.6, NISA_MAX)
            cash += balance - new_inv
        else:
            new_inv = 0
            cash += balance
        inv = inv * (1 + INV_RETURN) + new_inv
        if cash < 0:
            inv += cash
            cash = 0

        results.append(inv + cash)

    return results


def build_plans():
    """3シナリオの妻収入プランを構築"""
    plans = {}

    # --- シナリオ1: 退職（専業主婦） ---
    plan_c = {}
    for y in YEARS:
        if y == 2026:
            plan_c[y] = (40*4 + 37*3 + 37*5) / 12
        elif y == 2027:
            plan_c[y] = IKUKYU_50 * 6 / 12  # 半年で退職
        else:
            plan_c[y] = 0
    plans["退職（専業主婦）"] = plan_c

    # --- シナリオ2: パート（扶養内 月8万） ---
    PART_TIME = 8.0
    plan_p = {}
    for y in YEARS:
        if y == 2026:
            plan_p[y] = (40*4 + 37*3 + 37*5) / 12
        elif y == 2027:
            plan_p[y] = IKUKYU_50 * 6 / 12
        elif y <= 2029:
            plan_p[y] = 0  # 2歳まで育児専念
        else:
            plan_p[y] = PART_TIME
    plans["パート（扶養内 月8万）"] = plan_p

    # --- シナリオ3: 時短復帰 → フル復帰 ---
    jitan = WIFE_MONTHLY * 0.75  # 30万
    plan_b = {}
    for y in YEARS:
        if y == 2026:
            plan_b[y] = (40*4 + 37*3 + 37*5) / 12
        elif y == 2027:
            plan_b[y] = (IKUKYU_50*3 + jitan*9) / 12
        elif y == 2028:
            plan_b[y] = (jitan*4 + MATERNITY*8) / 12
        elif y == 2029:
            plan_b[y] = (IKUKYU_50*3 + IKUKYU_67*3 + jitan*6) / 12
        elif y <= 2034:
            plan_b[y] = jitan
        else:
            plan_b[y] = WIFE_MONTHLY
    plans["時短復帰 → フル復帰"] = plan_b

    return plans


def main():
    plans = build_plans()
    colors = {
        "退職（専業主婦）": "#E74C3C",
        "パート（扶養内 月8万）": "#F39C12",
        "時短復帰 → フル復帰": "#2ECC71",
    }
    markers = {
        "退職（専業主婦）": "v",
        "パート（扶養内 月8万）": "s",
        "時短復帰 → フル復帰": "^",
    }

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 12),
                                    gridspec_kw={"height_ratios": [3, 1]})
    fig.patch.set_facecolor("#1a1a2e")

    # ============================================================
    # 上段: 純資産推移
    # ============================================================
    ax1.set_facecolor("#16213e")
    for name, plan in plans.items():
        data = simulate(plan)
        ax1.plot(YEARS, data, color=colors[name], linewidth=2.5,
                 marker=markers[name], markersize=5, markevery=3,
                 label=name, zorder=3)
        # 最終値ラベル
        ax1.annotate(f"  {data[-1]:,.0f}万",
                     xy=(YEARS[-1], data[-1]),
                     fontproperties=JP_FONT, fontsize=13, fontweight="bold",
                     color=colors[name], va="center")

    ax1.set_title("妻のキャリア選択による純資産推移（2026-2050年）",
                  fontproperties=JP_FONT, fontsize=18, fontweight="bold",
                  color="white", pad=15)
    ax1.set_ylabel("純資産（万円）", fontproperties=JP_FONT, fontsize=13, color="white")
    ax1.set_xlabel("年", fontproperties=JP_FONT, fontsize=13, color="white")

    # グリッド・目盛り
    ax1.grid(True, alpha=0.2, color="white")
    ax1.tick_params(colors="white", labelsize=11)
    for label in ax1.get_xticklabels() + ax1.get_yticklabels():
        label.set_fontproperties(JP_FONT)

    # Y軸フォーマット
    ax1.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    # 凡例
    leg = ax1.legend(prop=JP_FONT, fontsize=13, loc="upper left",
                     facecolor="#16213e", edgecolor="white", labelcolor="white")

    # イベントライン
    events = {2026: "第1子\n出産", 2028: "第2子\n出産",
              2032: "第1子\n小学校", 2044: "第1子\n大学"}
    for yr, label in events.items():
        ax1.axvline(x=yr, color="white", alpha=0.15, linestyle="--", linewidth=1)
        ax1.text(yr, ax1.get_ylim()[1] * 0.02, label,
                 fontproperties=JP_FONT, fontsize=9, color="white",
                 alpha=0.5, ha="center", va="bottom")

    # ============================================================
    # 下段: シナリオ間の差額（退職基準）
    # ============================================================
    ax2.set_facecolor("#16213e")
    base_data = simulate(plans["退職（専業主婦）"])

    for name, plan in plans.items():
        if name == "退職（専業主婦）":
            continue
        data = simulate(plan)
        diff = [d - b for d, b in zip(data, base_data)]
        ax2.fill_between(YEARS, 0, diff, alpha=0.25, color=colors[name])
        ax2.plot(YEARS, diff, color=colors[name], linewidth=2,
                 label=f"{name} との差額", zorder=3)
        ax2.annotate(f"  +{diff[-1]:,.0f}万",
                     xy=(YEARS[-1], diff[-1]),
                     fontproperties=JP_FONT, fontsize=12, fontweight="bold",
                     color=colors[name], va="center")

    ax2.set_title("退職シナリオとの差額（働くことで得られる資産）",
                  fontproperties=JP_FONT, fontsize=15, fontweight="bold",
                  color="white", pad=10)
    ax2.set_ylabel("差額（万円）", fontproperties=JP_FONT, fontsize=13, color="white")
    ax2.set_xlabel("年", fontproperties=JP_FONT, fontsize=13, color="white")
    ax2.grid(True, alpha=0.2, color="white")
    ax2.tick_params(colors="white", labelsize=11)
    for label in ax2.get_xticklabels() + ax2.get_yticklabels():
        label.set_fontproperties(JP_FONT)
    ax2.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax2.axhline(y=0, color="white", alpha=0.3, linewidth=1)
    leg2 = ax2.legend(prop=JP_FONT, fontsize=12, loc="upper left",
                      facecolor="#16213e", edgecolor="white", labelcolor="white")

    plt.tight_layout(pad=2)
    out_path = os.path.join(os.path.dirname(__file__), "life_plan_chart.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
