"""FPレポートPDF生成スクリプト

妻のキャリア3シナリオ（退職/パート/時短復帰）比較 +
資産形成アドバイスを含む多ページPDFを生成する。
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import matplotlib.ticker as mticker
import numpy as np
import os
import io
import tempfile

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

# ============================================================
# フォント設定
# ============================================================
FONT_PATH = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"
JP = FontProperties(fname=FONT_PATH)
pdfmetrics.registerFont(TTFont("IPAGothic", FONT_PATH))
FONT_NAME = "IPAGothic"

# ============================================================
# カラーパレット
# ============================================================
C_BG = "#0f1923"
C_BG2 = "#162230"
C_ACCENT = "#4FC3F7"
C_GREEN = "#2ECC71"
C_ORANGE = "#F39C12"
C_RED = "#E74C3C"
C_WHITE = "#FFFFFF"
C_GRAY = "#8899AA"
C_LIGHT_BG = "#F5F7FA"

# ============================================================
# シミュレーション定数 (chart.py と同一)
# ============================================================
HUSBAND_AGE_2026 = 27
WIFE_AGE_2026 = 31
HUSBAND_GROSS_ANNUAL_2026 = 580.0
HUSBAND_GROSS_ANNUAL_TARGET = 1000.0
HUSBAND_TARGET_AGE = 40
HUSBAND_GROSS_MONTHLY_2026 = 48.0

WIFE_MONTHLY = 40.0
WIFE_GROSS = 55.0
WIFE_BONUS = 100.0

IKUKYU_67 = WIFE_GROSS * 0.67
IKUKYU_50 = WIFE_GROSS * 0.50
MATERNITY = WIFE_GROSS * 0.67

CURRENT_MONTHLY_EXPENSE = 33.0
RENT_BASE_2026 = 16.0
RENT_BIG_PREMIUM = 6.0
RENT_INFLATION = 0.02

CHILD_COSTS = {
    (0, 2): 3.0, (3, 5): 5.0, (6, 12): 6.0,
    (13, 15): 8.0, (16, 18): 10.0, (19, 22): 15.0,
}
NURSERY_0_2 = 5.0

INITIAL_INV = 1426.0
INITIAL_CASH = 232.0
INV_RETURN = 0.04
NISA_MAX = 360.0
INFLATION = 0.01
SALARY_GROWTH = 0.015

YEARS = list(range(2026, 2051))

# ============================================================
# シミュレーションエンジン
# ============================================================

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

def husband_take_home(year):
    age = HUSBAND_AGE_2026 + (year - 2026)
    years_to_target = HUSBAND_TARGET_AGE - HUSBAND_AGE_2026
    if age <= HUSBAND_TARGET_AGE:
        progress = (age - HUSBAND_AGE_2026) / years_to_target
        gross = HUSBAND_GROSS_ANNUAL_2026 + (HUSBAND_GROSS_ANNUAL_TARGET - HUSBAND_GROSS_ANNUAL_2026) * progress
    else:
        years_after = age - HUSBAND_TARGET_AGE
        gross = HUSBAND_GROSS_ANNUAL_TARGET * (1 + SALARY_GROWTH) ** years_after
    if gross <= 600:
        rate = 0.80
    elif gross <= 800:
        rate = 0.80 - (gross - 600) / 200 * 0.05
    elif gross <= 1000:
        rate = 0.75 - (gross - 800) / 200 * 0.03
    elif gross <= 1200:
        rate = 0.72 - (gross - 1000) / 200 * 0.03
    else:
        rate = 0.69
    return gross * rate

def rent_for_year(year, c1_age):
    i = year - 2026
    r = RENT_BASE_2026 * (1 + RENT_INFLATION) ** i
    if c1_age >= 4:
        r += RENT_BIG_PREMIUM * (1 + RENT_INFLATION) ** i
    return r

def simulate_detailed(wife_plan):
    """年ごとの詳細データを辞書リストで返す"""
    inv = INITIAL_INV
    cash = INITIAL_CASH
    rows = []
    for i, year in enumerate(YEARS):
        h_income = husband_take_home(year)
        if year == 2026:
            h_income = h_income * 7 / 12 + HUSBAND_GROSS_MONTHLY_2026 * 0.67 * 5
        w_monthly = wife_plan.get(year, 0)
        w_income = w_monthly * 12
        w_b = WIFE_BONUS * (1 + SALARY_GROWTH) ** i
        if w_monthly >= WIFE_MONTHLY * 0.9:
            w_income += w_b
        elif w_monthly >= WIFE_MONTHLY * 0.7:
            w_income += w_b * 0.5
        total_income = h_income + w_income
        base = (CURRENT_MONTHLY_EXPENSE - RENT_BASE_2026) * (1 + INFLATION) ** i
        c1_age = year - 2026
        c2_age = year - 2028
        cc = child_cost(c1_age) + child_cost(c2_age)
        nursery = 0
        if w_monthly > 0:
            if 0 <= c1_age <= 2: nursery += NURSERY_0_2
            if 0 <= c2_age <= 2: nursery += NURSERY_0_2
        rent = rent_for_year(year, c1_age)
        monthly_exp = base + rent + cc + nursery
        yearly_exp = monthly_exp * 12 + special_costs(c1_age, c2_age)
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
        rows.append({
            "year": year,
            "h_income": h_income, "w_income": w_income,
            "total_income": total_income,
            "expense": yearly_exp, "rent_m": rent,
            "child_cost_m": cc, "balance": balance,
            "investment": inv, "cash": cash,
            "net_worth": inv + cash,
            "h_age": HUSBAND_AGE_2026 + (year - 2026),
            "w_age": WIFE_AGE_2026 + (year - 2026),
        })
    return rows

def build_plans():
    plans = {}
    plan_c = {}
    for y in YEARS:
        if y == 2026: plan_c[y] = (40*4 + 37*3 + 37*5) / 12
        elif y == 2027: plan_c[y] = IKUKYU_50 * 6 / 12
        else: plan_c[y] = 0
    plans["退職（専業主婦）"] = plan_c

    plan_p = {}
    for y in YEARS:
        if y == 2026: plan_p[y] = (40*4 + 37*3 + 37*5) / 12
        elif y == 2027: plan_p[y] = IKUKYU_50 * 6 / 12
        elif y <= 2029: plan_p[y] = 0
        else: plan_p[y] = 8.0
    plans["パート（扶養内 月8万）"] = plan_p

    jitan = WIFE_MONTHLY * 0.75
    plan_b = {}
    for y in YEARS:
        if y == 2026: plan_b[y] = (40*4 + 37*3 + 37*5) / 12
        elif y == 2027: plan_b[y] = (IKUKYU_50*3 + jitan*9) / 12
        elif y == 2028: plan_b[y] = (jitan*4 + MATERNITY*8) / 12
        elif y == 2029: plan_b[y] = (IKUKYU_50*3 + IKUKYU_67*3 + jitan*6) / 12
        elif y <= 2034: plan_b[y] = jitan
        else: plan_b[y] = WIFE_MONTHLY
    plans["時短復帰 → フル復帰"] = plan_b
    return plans

# ============================================================
# チャート生成ヘルパー
# ============================================================

def fig_to_image(fig, dpi=150):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return ImageReader(buf)

def style_ax(ax, bg=C_BG2):
    ax.set_facecolor(bg)
    ax.grid(True, alpha=0.15, color="white")
    ax.tick_params(colors="white", labelsize=9)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontproperties(JP)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))

COLORS = {"退職（専業主婦）": C_RED, "パート（扶養内 月8万）": C_ORANGE, "時短復帰 → フル復帰": C_GREEN}
MARKERS = {"退職（専業主婦）": "v", "パート（扶養内 月8万）": "s", "時短復帰 → フル復帰": "^"}

# --- Chart 1: 純資産推移 ---
def chart_net_worth(all_data):
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor(C_BG)
    style_ax(ax)
    for name, rows in all_data.items():
        ys = [r["net_worth"] for r in rows]
        ax.plot(YEARS, ys, color=COLORS[name], lw=2.5, marker=MARKERS[name],
                markersize=4, markevery=3, label=name)
        ax.annotate(f" {ys[-1]:,.0f}万", xy=(YEARS[-1], ys[-1]),
                    fontproperties=JP, fontsize=11, fontweight="bold",
                    color=COLORS[name], va="center")
    ax.set_title("純資産推移（2026-2050年）", fontproperties=JP, fontsize=15,
                 fontweight="bold", color="white", pad=10)
    ax.set_ylabel("万円", fontproperties=JP, fontsize=11, color="white")
    events = {2026: "第1子出産", 2028: "第2子出産", 2032: "第1子小学校",
              2044: "第1子大学", 2046: "第2子大学"}
    for yr, lb in events.items():
        ax.axvline(x=yr, color="white", alpha=0.12, ls="--", lw=0.8)
        ax.text(yr + 0.2, ax.get_ylim()[1] * 0.01, lb, fontproperties=JP,
                fontsize=7, color=C_GRAY, rotation=90, va="bottom")
    ax.legend(prop=JP, fontsize=10, loc="upper left",
              facecolor=C_BG2, edgecolor=C_GRAY, labelcolor="white")
    return fig_to_image(fig)

# --- Chart 2: 年間収支推移 ---
def chart_annual_balance(all_data):
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.5), sharey=True)
    fig.patch.set_facecolor(C_BG)
    for ax, (name, rows) in zip(axes, all_data.items()):
        style_ax(ax)
        bs = [r["balance"] for r in rows]
        colors_bar = [C_GREEN if b >= 0 else C_RED for b in bs]
        ax.bar(YEARS, bs, color=colors_bar, alpha=0.8, width=0.8)
        ax.axhline(y=0, color="white", alpha=0.3, lw=0.8)
        ax.set_title(name, fontproperties=JP, fontsize=10, color="white", pad=5)
        ax.set_xlabel("")
        ax.tick_params(labelsize=7)
    axes[0].set_ylabel("年間収支（万円）", fontproperties=JP, fontsize=9, color="white")
    fig.suptitle("年間収支の推移", fontproperties=JP, fontsize=13,
                 fontweight="bold", color="white", y=1.02)
    fig.tight_layout(pad=1)
    return fig_to_image(fig)

# --- Chart 3: 夫の収入カーブ ---
def chart_husband_income():
    fig, ax = plt.subplots(figsize=(10, 3.5))
    fig.patch.set_facecolor(C_BG)
    style_ax(ax)
    gross_list, take_home_list = [], []
    for y in YEARS:
        age = HUSBAND_AGE_2026 + (y - 2026)
        yrs = HUSBAND_TARGET_AGE - HUSBAND_AGE_2026
        if age <= HUSBAND_TARGET_AGE:
            p = (age - HUSBAND_AGE_2026) / yrs
            g = HUSBAND_GROSS_ANNUAL_2026 + (HUSBAND_GROSS_ANNUAL_TARGET - HUSBAND_GROSS_ANNUAL_2026) * p
        else:
            g = HUSBAND_GROSS_ANNUAL_TARGET * (1 + SALARY_GROWTH) ** (age - HUSBAND_TARGET_AGE)
        gross_list.append(g)
        take_home_list.append(husband_take_home(y))
    ax.fill_between(YEARS, 0, gross_list, alpha=0.2, color=C_ACCENT)
    ax.plot(YEARS, gross_list, color=C_ACCENT, lw=2, label="額面年収")
    ax.plot(YEARS, take_home_list, color=C_GREEN, lw=2, ls="--", label="手取り年収")
    ax.axhline(y=1000, color=C_ORANGE, alpha=0.5, ls=":", lw=1)
    ax.text(2040, 1020, "年収1,000万ライン", fontproperties=JP, fontsize=8, color=C_ORANGE)
    ax.set_title("夫の年収推移（27歳→51歳）", fontproperties=JP, fontsize=13,
                 fontweight="bold", color="white", pad=8)
    ax.set_ylabel("万円", fontproperties=JP, fontsize=10, color="white")
    ax.legend(prop=JP, fontsize=10, facecolor=C_BG2, edgecolor=C_GRAY, labelcolor="white")
    # 年齢軸
    ax2 = ax.twiny()
    ax2.set_xlim(ax.get_xlim())
    age_ticks = list(range(2026, 2051, 5))
    ax2.set_xticks(age_ticks)
    ax2.set_xticklabels([f"{HUSBAND_AGE_2026 + (y-2026)}歳" for y in age_ticks],
                         fontproperties=JP, fontsize=8, color=C_GRAY)
    ax2.tick_params(colors=C_GRAY, length=0)
    return fig_to_image(fig)

# --- Chart 4: 支出内訳の変化 ---
def chart_expense_breakdown(rows_jitan):
    milestones = [2026, 2030, 2035, 2040, 2045, 2050]
    labels = []
    rent_vals, living_vals, child_vals, special_vals = [], [], [], []
    for y in milestones:
        r = rows_jitan[y - 2026]
        labels.append(f"{y}\n(夫{r['h_age']}歳)")
        rent_vals.append(r["rent_m"] * 12)
        c1a, c2a = y - 2026, y - 2028
        living_base = (CURRENT_MONTHLY_EXPENSE - RENT_BASE_2026) * (1 + INFLATION) ** (y - 2026) * 12
        living_vals.append(living_base)
        child_vals.append(r["child_cost_m"] * 12)
        special_vals.append(special_costs(c1a, c2a))

    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor(C_BG)
    style_ax(ax)
    x = np.arange(len(milestones))
    w = 0.5
    p1 = ax.bar(x, rent_vals, w, color="#3498DB", label="家賃")
    p2 = ax.bar(x, living_vals, w, bottom=rent_vals, color="#1ABC9C", label="生活費")
    bottom2 = [a+b for a, b in zip(rent_vals, living_vals)]
    p3 = ax.bar(x, child_vals, w, bottom=bottom2, color=C_ORANGE, label="子供関連費")
    bottom3 = [a+b for a, b in zip(bottom2, child_vals)]
    p4 = ax.bar(x, special_vals, w, bottom=bottom3, color=C_RED, label="特別費用")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontproperties=JP, fontsize=9, color="white")
    ax.set_title("年間支出内訳の変化（時短復帰シナリオ）", fontproperties=JP, fontsize=13,
                 fontweight="bold", color="white", pad=8)
    ax.set_ylabel("万円/年", fontproperties=JP, fontsize=10, color="white")
    ax.legend(prop=JP, fontsize=9, facecolor=C_BG2, edgecolor=C_GRAY, labelcolor="white",
              loc="upper left")
    return fig_to_image(fig)

# --- Chart 5: 資産構成推移（時短シナリオ） ---
def chart_asset_composition(rows):
    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor(C_BG)
    style_ax(ax)
    invs = [r["investment"] for r in rows]
    cashs = [r["cash"] for r in rows]
    ax.fill_between(YEARS, 0, invs, alpha=0.6, color=C_ACCENT, label="運用資産")
    ax.fill_between(YEARS, invs, [i+c for i, c in zip(invs, cashs)],
                    alpha=0.6, color=C_GREEN, label="現金")
    ax.set_title("資産構成の推移（時短復帰シナリオ）", fontproperties=JP, fontsize=13,
                 fontweight="bold", color="white", pad=8)
    ax.set_ylabel("万円", fontproperties=JP, fontsize=10, color="white")
    ax.legend(prop=JP, fontsize=10, facecolor=C_BG2, edgecolor=C_GRAY, labelcolor="white")
    return fig_to_image(fig)

# --- Chart 6: 家賃推移 ---
def chart_rent():
    fig, ax = plt.subplots(figsize=(10, 3))
    fig.patch.set_facecolor(C_BG)
    style_ax(ax)
    rents = [rent_for_year(y, y - 2026) for y in YEARS]
    rents_no_move = [RENT_BASE_2026 * (1 + RENT_INFLATION) ** (y - 2026) for y in YEARS]
    ax.plot(YEARS, rents, color=C_ORANGE, lw=2, label="実際の家賃（引越込）")
    ax.plot(YEARS, rents_no_move, color=C_GRAY, lw=1.5, ls="--", label="現住居のまま")
    ax.fill_between(YEARS, rents_no_move, rents, alpha=0.15, color=C_ORANGE)
    ax.set_title("月額家賃の推移（年2%上昇）", fontproperties=JP, fontsize=13,
                 fontweight="bold", color="white", pad=8)
    ax.set_ylabel("万円/月", fontproperties=JP, fontsize=10, color="white")
    ax.legend(prop=JP, fontsize=10, facecolor=C_BG2, edgecolor=C_GRAY, labelcolor="white")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}"))
    return fig_to_image(fig)


# ============================================================
# PDF生成
# ============================================================

W, H = A4  # 595 x 842 pt

def draw_header(c, page_num, total_pages):
    """ページヘッダー"""
    c.setFillColor(HexColor(C_BG))
    c.rect(0, H - 25*mm, W, 25*mm, fill=1, stroke=0)
    c.setFillColor(HexColor(C_ACCENT))
    c.setFont(FONT_NAME, 14)
    c.drawString(15*mm, H - 15*mm, "ライフプラン・シミュレーションレポート")
    c.setFillColor(HexColor(C_GRAY))
    c.setFont(FONT_NAME, 8)
    c.drawRightString(W - 15*mm, H - 15*mm, f"作成日: 2026年3月  |  {page_num}/{total_pages}")
    c.setFont(FONT_NAME, 7)
    c.drawString(15*mm, H - 21*mm, "N家  よしき様(27歳) / なな様(31歳)  第1子2026年7月出産予定")

def draw_footer(c):
    c.setFillColor(HexColor(C_GRAY))
    c.setFont(FONT_NAME, 6)
    c.drawCentredString(W/2, 8*mm,
        "※本レポートは簡易シミュレーションであり、実際の運用成果・税制変更等を保証するものではありません。")

def draw_text_block(c, x, y, lines, font_size=9, color=HexColor("#333333"), line_height=14):
    """テキストブロックを描画し、最終y座標を返す"""
    c.setFont(FONT_NAME, font_size)
    c.setFillColor(color)
    for line in lines:
        if line.startswith("###"):
            c.setFont(FONT_NAME, font_size + 2)
            c.setFillColor(HexColor(C_BG))
            c.drawString(x, y, line.replace("### ", ""))
            c.setFont(FONT_NAME, font_size)
            c.setFillColor(color)
            y -= line_height + 4
        elif line.startswith("**"):
            c.setFont(FONT_NAME, font_size)
            c.setFillColor(HexColor("#1a5276"))
            c.drawString(x, y, line.replace("**", ""))
            c.setFillColor(color)
            y -= line_height + 2
        elif line == "":
            y -= line_height * 0.5
        else:
            c.drawString(x, y, line)
            y -= line_height
    return y


def main():
    plans = build_plans()
    all_data = {name: simulate_detailed(plan) for name, plan in plans.items()}

    # チャート画像生成
    img_nw = chart_net_worth(all_data)
    img_balance = chart_annual_balance(all_data)
    img_husband = chart_husband_income()
    img_expense = chart_expense_breakdown(all_data["時短復帰 → フル復帰"])
    img_asset = chart_asset_composition(all_data["時短復帰 → フル復帰"])
    img_rent = chart_rent()

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "life_plan_report.pdf")
    c = canvas.Canvas(out_path, pagesize=A4)
    total_pages = 6

    # ================================================================
    # Page 1: 表紙
    # ================================================================
    c.setFillColor(HexColor(C_BG))
    c.rect(0, 0, W, H, fill=1, stroke=0)
    # アクセント帯
    c.setFillColor(HexColor(C_ACCENT))
    c.rect(0, H*0.45, W, 4*mm, fill=1, stroke=0)
    c.rect(0, H*0.45 + 8*mm, W, 1*mm, fill=1, stroke=0)

    c.setFillColor(HexColor(C_WHITE))
    c.setFont(FONT_NAME, 28)
    c.drawCentredString(W/2, H*0.62, "ライフプラン")
    c.drawCentredString(W/2, H*0.62 - 38, "シミュレーションレポート")

    c.setFillColor(HexColor(C_ACCENT))
    c.setFont(FONT_NAME, 14)
    c.drawCentredString(W/2, H*0.45 - 25*mm, "N家  よしき様 (27歳) ・ なな様 (31歳)")

    c.setFillColor(HexColor(C_GRAY))
    c.setFont(FONT_NAME, 10)
    c.drawCentredString(W/2, H*0.45 - 40*mm, "2026年3月作成")

    c.setFont(FONT_NAME, 9)
    y_info = H * 0.25
    info_lines = [
        "【前提条件】",
        f"  夫 手取り月収35万円  /  年収480万 → 1,000万（40歳到達想定）",
        f"  妻 手取り月収40万円  /  正社員",
        f"  共同支出 月23万 + 個人支出 月10万 = 月33万",
        f"  現在の資産: 運用 1,426万 + 現金 232万 = 1,658万",
        f"  第1子 2026年7月 / 第2子 2028年7月（予定）",
        f"  住居: 用賀 1LDK 月16万（家賃年2%上昇想定）",
        f"  投資リターン: 年4%  /  インフレ: 年1%",
    ]
    c.setFillColor(HexColor(C_GRAY))
    for line in info_lines:
        c.drawCentredString(W/2, y_info, line)
        y_info -= 15

    c.showPage()

    # ================================================================
    # Page 2: 現状分析 + 純資産推移
    # ================================================================
    draw_header(c, 2, total_pages)
    draw_footer(c)

    y = H - 32*mm
    c.setFillColor(HexColor(C_BG))
    c.setFont(FONT_NAME, 14)
    c.drawString(15*mm, y, "1. 現在の家計状況と3シナリオ比較")
    y -= 8*mm

    c.setFont(FONT_NAME, 9)
    c.setFillColor(HexColor("#333333"))
    summary = [
        "お二人の現在の家計は非常に健全です。手取り合計75万円/月に対し支出33万円で、",
        "貯蓄率は約56%と高水準。既に1,658万円の資産基盤があり、資産形成の好スタートです。",
        "",
        "以下、妻のキャリア選択により2050年（夫51歳/妻55歳）時点の純資産がどう変わるか",
        "シミュレーションした結果です。",
    ]
    y = draw_text_block(c, 15*mm, y, summary)
    y -= 5*mm

    c.drawImage(img_nw, 10*mm, y - 85*mm, width=W - 20*mm, height=85*mm, preserveAspectRatio=True)
    y -= 92*mm

    # 結果テーブル
    c.setFillColor(HexColor(C_BG))
    c.rect(15*mm, y - 52*mm, W - 30*mm, 52*mm, fill=1, stroke=0)
    c.setFillColor(HexColor(C_WHITE))
    c.setFont(FONT_NAME, 10)
    ty = y - 8*mm
    c.drawString(20*mm, ty, "【2050年時点の純資産（夫51歳/妻55歳）】")
    ty -= 14
    c.setFont(FONT_NAME, 9)
    for name, color in [("時短復帰 → フル復帰", C_GREEN), ("パート（扶養内 月8万）", C_ORANGE),
                        ("退職（専業主婦）", C_RED)]:
        val = all_data[name][-1]["net_worth"]
        c.setFillColor(HexColor(color))
        c.drawString(25*mm, ty, f"● {name}")
        c.drawRightString(W - 30*mm, ty, f"{val:,.0f}万円")
        ty -= 13
    c.setFillColor(HexColor(C_GRAY))
    c.setFont(FONT_NAME, 8)
    ty -= 5
    diff = all_data["時短復帰 → フル復帰"][-1]["net_worth"] - all_data["退職（専業主婦）"][-1]["net_worth"]
    c.drawString(25*mm, ty, f"→ 時短復帰 vs 退職の差額: {diff:,.0f}万円（約{diff/10000:.1f}億円）")

    c.showPage()

    # ================================================================
    # Page 3: 年間収支 + 夫の収入カーブ
    # ================================================================
    draw_header(c, 3, total_pages)
    draw_footer(c)

    y = H - 32*mm
    c.setFillColor(HexColor(C_BG))
    c.setFont(FONT_NAME, 14)
    c.drawString(15*mm, y, "2. 年間収支分析と夫の収入見通し")
    y -= 6*mm

    c.drawImage(img_balance, 10*mm, y - 62*mm, width=W - 20*mm, height=62*mm, preserveAspectRatio=True)
    y -= 68*mm

    analysis = [
        "**【読み方のポイント】**",
        "  緑のバー = 黒字の年、赤のバー = 赤字の年。退職シナリオでは2030年頃から",
        "  恒常的に赤字化し、資産の取り崩しが続きます。パートでは小幅黒字を維持できますが、",
        "  大学進学時（2044/2046年）に大きく落ち込みます。時短復帰なら全期間を通じて安定黒字。",
    ]
    y = draw_text_block(c, 15*mm, y, analysis)
    y -= 5*mm

    c.drawImage(img_husband, 10*mm, y - 60*mm, width=W - 20*mm, height=60*mm, preserveAspectRatio=True)
    y -= 66*mm

    husband_note = [
        "**【夫の収入について】**",
        "  額面580万(27歳) → 1,000万(40歳)へ線形成長を想定。40歳以降は年1.5%昇給。",
        "  累進課税により、年収1,000万でも手取りは約720万（税率約28%）です。",
        "  「年収1,000万の壁」: 児童手当の所得制限緩和(2024年～)は追い風ですが、",
        "  配偶者控除・各種給付の所得制限に引っかかり始める年収帯でもあります。",
    ]
    draw_text_block(c, 15*mm, y, husband_note)

    c.showPage()

    # ================================================================
    # Page 4: 支出分析 + 家賃
    # ================================================================
    draw_header(c, 4, total_pages)
    draw_footer(c)

    y = H - 32*mm
    c.setFillColor(HexColor(C_BG))
    c.setFont(FONT_NAME, 14)
    c.drawString(15*mm, y, "3. 支出構造の変化と住居費の影響")
    y -= 6*mm

    c.drawImage(img_expense, 10*mm, y - 68*mm, width=W - 20*mm, height=68*mm, preserveAspectRatio=True)
    y -= 74*mm

    exp_note = [
        "**【支出のピークは子供の大学期】**",
        "  2044-2048年が支出のピーク。第1子・第2子の大学が重なる2046年は",
        "  年間支出が約950万円に達します。この期間を乗り越える資金計画が重要です。",
        "",
        "**【住居費は「隠れた大出費」】**",
    ]
    y = draw_text_block(c, 15*mm, y, exp_note)
    y -= 3*mm

    c.drawImage(img_rent, 10*mm, y - 52*mm, width=W - 20*mm, height=52*mm, preserveAspectRatio=True)
    y -= 58*mm

    rent_note = [
        "  現在の家賃16万/月は年2%上昇で2050年には約25万/月に。",
        "  広い部屋に引越すと月28万以上に。25年間の累計家賃は約7,000万円〜8,500万円。",
        "  住宅購入との比較検討は別途必要ですが、賃貸の柔軟性（転職・転居しやすさ）は",
        "  子育て期の大きなメリットです。",
    ]
    draw_text_block(c, 15*mm, y, rent_note)

    c.showPage()

    # ================================================================
    # Page 5: 資産形成 + 運用アドバイス
    # ================================================================
    draw_header(c, 5, total_pages)
    draw_footer(c)

    y = H - 32*mm
    c.setFillColor(HexColor(C_BG))
    c.setFont(FONT_NAME, 14)
    c.drawString(15*mm, y, "4. 資産形成の方向性と運用アドバイス")
    y -= 8*mm

    c.drawImage(img_asset, 10*mm, y - 68*mm, width=W - 20*mm, height=68*mm, preserveAspectRatio=True)
    y -= 74*mm

    advice1 = [
        "### 現状の評価",
        "  現在のポートフォリオはS&P500・オルカン中心のインデックス投資で構成されており、",
        "  27歳・31歳の年齢に対して非常に合理的な配分です。NISA枠の活用も進んでいます。",
        "",
        "### 今後の資産形成5つの柱",
        "",
        "**1. NISA枠の最大活用（最優先）**",
        "  夫婦で年間最大360万円×2 = 720万円の非課税投資枠。",
        "  生涯投資枠3,600万円(2人で7,200万円)を最速で埋めることが最も効率的。",
        "  現在のペース(推定月30万)を維持し、妻の復帰後はさらに積み増しを。",
        "",
        "**2. 投資方針は「退屈なほどシンプル」に**",
        "  現在のeMAXIS Slim系インデックス中心の方針を堅持してください。",
        "  S&P500とオルカンの重複は問題ありません（実質的に米国株ウェイト調整）。",
        "  個別株は資産の10%以下に抑え、「コア・サテライト」戦略を意識。",
    ]
    y = draw_text_block(c, 15*mm, y, advice1, line_height=13)

    c.showPage()

    # ================================================================
    # Page 6: 運用アドバイス続き + アクションプラン
    # ================================================================
    draw_header(c, 6, total_pages)
    draw_footer(c)

    y = H - 32*mm
    c.setFillColor(HexColor(C_BG))
    c.setFont(FONT_NAME, 14)
    c.drawString(15*mm, y, "5. 具体的アクションプランと重要な判断ポイント")
    y -= 8*mm

    advice2 = [
        "**3. 生活防衛資金の確保**",
        "  現金232万円は生活費約7ヶ月分。育休期間中の収入減に備え、",
        "  生活費12ヶ月分（約400万円）まで現金を積み増すことを推奨。",
        "  育休明け・収入安定後は追加分を投資に回す。",
        "",
        "**4. iDeCo（個人型確定拠出年金）の検討**",
        "  夫: 企業型DCがなければ月2.3万円 / 妻: 月2.3万円",
        "  所得控除メリットが大きく、特に夫の年収が上がるほど節税効果が拡大。",
        "  ただし60歳まで引き出せないため、NISA優先の上で余力があれば。",
        "",
        "**5. 保険の見直し**",
        "  子供が生まれるタイミングで以下を検討:",
        "  ・夫の死亡保険: 収入保障保険（月15-20万×子独立まで）で十分。",
        "    終身保険・貯蓄型保険は不要（投資で代替可能）",
        "  ・医療保険: 高額療養費制度+貯蓄で対応可能、最小限に",
        "  ・学資保険: 不要（NISA投資のリターンが上回る）",
        "",
        "### 重要な判断ポイントのタイムライン",
        "",
        "**2026年（今年）**",
        "  ・生活防衛資金を400万円まで積み増し",
        "  ・収入保障保険の加入検討",
        "  ・育休中の家計管理ルール策定（支出を月25万以内に）",
        "",
        "**2027-2028年（育休〜第2子）**",
        "  ・連続育休 or 一旦復帰の最終判断",
        "  ・住居の広さが足りるか検討開始",
        "",
        "**2030年（第1子4歳）**",
        "  ・広い部屋への引越 or 住宅購入の本格検討",
        "  ・妻の時短→フル復帰のタイミング計画",
        "",
        "**2035年（夫36歳/妻40歳）**",
        "  ・下の子が小学校入学、妻フル復帰の目安",
        "  ・ここから資産形成のアクセルを踏む時期",
        "  ・年間黒字が500万円超、NISA枠を夫婦フルで活用",
        "",
        "**2044-2048年（大学ラッシュ）**",
        "  ・教育費ピーク、年間900-950万円の支出",
        "  ・この時期は積立を減額してもOK、投資の取り崩しは最小限に",
        "",
        "### 最後に",
        "  お二人の最大の資産は「若さ」と「共働き」です。特に妻が正社員を維持する",
        "  ことの経済的価値は1.6億円以上。時短勤務を活用しながらキャリアを継続することが、",
        "  家族の将来の選択肢を最大化します。焦らず、長期目線で歩んでください。",
    ]
    draw_text_block(c, 15*mm, y, advice2, font_size=8.5, line_height=12.5)

    c.showPage()
    c.save()
    print(f"PDF saved: {out_path}")


if __name__ == "__main__":
    main()
