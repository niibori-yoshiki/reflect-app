"""家計・資産分析レポート生成スクリプト

Google Sheets API経由でスプレッドシートを読み取り、
分析結果をターミナルに出力する。

使い方:
  python analyze.py

GCP未設定の場合はスクリーンショットから取得した
サンプルデータで分析を実行する。
"""

import json
from pathlib import Path
from datetime import datetime

# ============================================================
# データ定義（スクリーンショットから読み取ったデータ）
# ============================================================

# --- 家計簿: 26年2月支払 ---
FEB_2026 = {
    "year": 2026, "month": 2,
    "items": [
        {"genre": "家賃", "item": "家賃", "amount": 160200, "payer": "共同"},
        {"genre": "水道光熱費", "item": "電気代/ガス代(2/5分)", "amount": 17020, "payer": "よしき"},
        {"genre": "食費", "item": "食費", "amount": 4888, "payer": "共同"},
        {"genre": "外食", "item": "外食", "amount": 7606, "payer": "共同"},
        {"genre": "生活雑費", "item": "KEYUKA", "amount": 6918, "payer": "共同"},
        {"genre": "その他", "item": "Snowmanグッズ", "amount": 12600, "payer": "なな"},
        {"genre": "食費", "item": "食費", "amount": 18052, "payer": "共同"},
    ],
    "summary": {
        "total": 227284,
        "per_person": 113642,
    },
    "budget": {
        "食費": {"actual": 22940, "budget": 20000},
        "生活雑費": {"actual": 6918, "budget": 5000},
        "家賃": {"actual": 160200, "budget": 160200},
        "水道光熱費": {"actual": 17020, "budget": 10000},
        "家具・家電": {"actual": 0, "budget": 10000},
        "その他": {"actual": 12600, "budget": 10000},
        "外食": {"actual": 7606, "budget": None},
        "デート": {"actual": 0, "budget": None},
        "旅行": {"actual": 0, "budget": None},
        "嗜好品": {"actual": 0, "budget": None},
    },
    "budget_totals": {
        "生活費": {"actual": 219678, "budget": 215200},
        "娯楽費": {"actual": 7606, "budget": 15000},
    },
    "account_balance": 2320171,
}

# --- ポートフォリオ: 資産割合表 ---
PORTFOLIO = {
    "months": ["2025/07", "2025/08", "2025/09", "2025/10", "2025/11"],
    "assets": {
        "NISA(SP500) よしき": [2400000, 2524960, 2729515, 2901879, 3064653],
        "NISA(オルカン) よしき": [2000000, 2019193, 2098358, 2150496, 2255201],
        "NISA(SP500) なな":     [2400000, 2421225, 2519863, 2587592, 2732736],
        "NISA(オルカン) なな":   [1600000, 1778664, 1949331, 2114435, 2217384],
        "iDeCo(SP500) よしき":  [0, 7000, 17000, 37029, 39288],
    },
    "total_investment": [8400000, 8751042, 9314067, 9791601, 10309262],
    "cash": [1800000, 1600000, 1864587, 1744872, None],
}


# ============================================================
# 分析関数
# ============================================================

def fmt(amount: int | float) -> str:
    """金額をフォーマット"""
    return f"¥{amount:,.0f}"


def pct(part: float, whole: float) -> str:
    """パーセンテージ"""
    if whole == 0:
        return "0.0%"
    return f"{part / whole * 100:.1f}%"


def analyze_monthly_budget(data: dict) -> str:
    """月次予実分析"""
    lines = []
    lines.append(f"{'='*60}")
    lines.append(f"  家計分析レポート: {data['year']}年{data['month']}月")
    lines.append(f"{'='*60}")

    lines.append(f"\n■ 月間支出サマリー")
    lines.append(f"  合計支出:     {fmt(data['summary']['total'])}")
    lines.append(f"  1人あたり:    {fmt(data['summary']['per_person'])}")
    lines.append(f"  口座残高:     {fmt(data['account_balance'])}")

    # 予実比較
    lines.append(f"\n■ 予算 vs 実績（生活費）")
    lines.append(f"  {'カテゴリ':<10} {'実績':>12} {'予算':>12} {'差分':>12} {'判定'}")
    lines.append(f"  {'-'*58}")

    for cat, vals in data["budget"].items():
        if vals["budget"] is not None:
            diff = vals["actual"] - vals["budget"]
            status = "OK" if diff <= 0 else "超過"
            lines.append(
                f"  {cat:<10} {fmt(vals['actual']):>12} "
                f"{fmt(vals['budget']):>12} {fmt(diff):>12} {status}"
            )

    # 生活費・娯楽費の合計
    lines.append(f"\n  {'--- 合計 ---'}")
    for cat, vals in data["budget_totals"].items():
        diff = vals["actual"] - vals["budget"]
        lines.append(
            f"  {cat:<10} {fmt(vals['actual']):>12} "
            f"{fmt(vals['budget']):>12} {fmt(diff):>12}"
        )
    total_actual = sum(v["actual"] for v in data["budget_totals"].values())
    total_budget = sum(v["budget"] for v in data["budget_totals"].values())
    lines.append(
        f"  {'総合計':<10} {fmt(total_actual):>12} "
        f"{fmt(total_budget):>12} {fmt(total_actual - total_budget):>12}"
    )

    # 支出構成比
    lines.append(f"\n■ 支出構成比")
    total = data["summary"]["total"]
    genre_totals = {}
    for item in data["items"]:
        genre_totals[item["genre"]] = genre_totals.get(item["genre"], 0) + item["amount"]

    for genre, amount in sorted(genre_totals.items(), key=lambda x: -x[1]):
        bar_len = int(amount / total * 40)
        bar = "#" * bar_len
        lines.append(f"  {genre:<10} {fmt(amount):>12} ({pct(amount, total):>5}) {bar}")

    # 支払者別
    lines.append(f"\n■ 支払者別内訳")
    payer_totals = {}
    for item in data["items"]:
        payer_totals[item["payer"]] = payer_totals.get(item["payer"], 0) + item["amount"]
    for payer, amount in sorted(payer_totals.items(), key=lambda x: -x[1]):
        lines.append(f"  {payer:<10} {fmt(amount):>12} ({pct(amount, total):>5})")

    return "\n".join(lines)


def analyze_portfolio(data: dict) -> str:
    """ポートフォリオ分析"""
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"  ポートフォリオ分析")
    lines.append(f"{'='*60}")

    months = data["months"]
    start_month = months[0]
    end_month = months[-1]

    # 総資産推移
    total_start = data["total_investment"][0]
    total_end = data["total_investment"][-1]
    total_gain = total_end - total_start
    total_return_pct = total_gain / total_start * 100

    lines.append(f"\n■ 運用資産サマリー ({start_month} → {end_month})")
    lines.append(f"  開始時:     {fmt(total_start)}")
    lines.append(f"  現在:       {fmt(total_end)}")
    lines.append(f"  増減:       {fmt(total_gain)} ({total_return_pct:+.1f}%)")

    # 現金を含む総資産
    cash_latest = None
    for c in reversed(data["cash"]):
        if c is not None:
            cash_latest = c
            break
    if cash_latest:
        total_assets = total_end + cash_latest
        lines.append(f"\n  現金(生活費): {fmt(cash_latest)}")
        lines.append(f"  総資産:       {fmt(total_assets)}")
        lines.append(f"  投資比率:     {pct(total_end, total_assets)}")
        lines.append(f"  現金比率:     {pct(cash_latest, total_assets)}")

    # 個別銘柄パフォーマンス
    lines.append(f"\n■ 個別資産パフォーマンス ({start_month} → {end_month})")
    lines.append(f"  {'銘柄':<25} {'開始':>12} {'現在':>12} {'損益':>12} {'利回り':>8}")
    lines.append(f"  {'-'*72}")

    for name, values in data["assets"].items():
        start_val = values[0]
        end_val = values[-1]
        gain = end_val - start_val
        if start_val > 0:
            ret = gain / start_val * 100
            lines.append(
                f"  {name:<25} {fmt(start_val):>12} {fmt(end_val):>12} "
                f"{fmt(gain):>12} {ret:>+7.1f}%"
            )
        else:
            lines.append(
                f"  {name:<25} {'新規':>12} {fmt(end_val):>12} "
                f"{fmt(end_val):>12} {'N/A':>8}"
            )

    # SP500 vs オルカン比較
    lines.append(f"\n■ SP500 vs オルカン パフォーマンス比較")

    sp500_start = sum(data["assets"][k][0] for k in data["assets"] if "SP500" in k)
    sp500_end = sum(data["assets"][k][-1] for k in data["assets"] if "SP500" in k)
    olcan_start = sum(data["assets"][k][0] for k in data["assets"] if "オルカン" in k)
    olcan_end = sum(data["assets"][k][-1] for k in data["assets"] if "オルカン" in k)

    sp500_ret = (sp500_end - sp500_start) / sp500_start * 100 if sp500_start else 0
    olcan_ret = (olcan_end - olcan_start) / olcan_start * 100 if olcan_start else 0

    lines.append(f"  SP500合計:  {fmt(sp500_start)} → {fmt(sp500_end)} ({sp500_ret:+.1f}%)")
    lines.append(f"  オルカン合計: {fmt(olcan_start)} → {fmt(olcan_end)} ({olcan_ret:+.1f}%)")

    if sp500_ret > olcan_ret:
        lines.append(f"  → SP500が {sp500_ret - olcan_ret:.1f}pt 上回っています")
    else:
        lines.append(f"  → オルカンが {olcan_ret - sp500_ret:.1f}pt 上回っています")

    # 名義別
    lines.append(f"\n■ 名義別資産配分")
    yoshiki_end = sum(v[-1] for k, v in data["assets"].items() if "よしき" in k)
    nana_end = sum(v[-1] for k, v in data["assets"].items() if "なな" in k)
    lines.append(f"  よしき:  {fmt(yoshiki_end)} ({pct(yoshiki_end, total_end)})")
    lines.append(f"  なな:    {fmt(nana_end)} ({pct(nana_end, total_end)})")

    # 月次成長率
    lines.append(f"\n■ 月次成長率")
    for i in range(1, len(months)):
        prev = data["total_investment"][i-1]
        curr = data["total_investment"][i]
        growth = (curr - prev) / prev * 100
        lines.append(f"  {months[i]}: {fmt(curr)} ({growth:+.1f}% / 前月比 {fmt(curr - prev)})")

    return "\n".join(lines)


def generate_insights(budget_data: dict, portfolio_data: dict) -> str:
    """総合的なインサイトを生成"""
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"  総合分析・改善ポイント")
    lines.append(f"{'='*60}")

    total_investment = portfolio_data["total_investment"][-1]
    cash = None
    for c in reversed(portfolio_data["cash"]):
        if c is not None:
            cash = c
            break
    account_balance = budget_data["account_balance"]
    monthly_expense = budget_data["summary"]["total"]

    lines.append(f"\n■ 資産全体像")
    total = total_investment + (cash or 0) + account_balance
    lines.append(f"  運用資産:   {fmt(total_investment)}")
    if cash:
        lines.append(f"  生活費口座: {fmt(cash)}")
    lines.append(f"  口座残高:   {fmt(account_balance)}")
    lines.append(f"  推定総資産: {fmt(total)}")

    # 生活防衛資金
    emergency_months = (cash or 0 + account_balance) / monthly_expense if monthly_expense > 0 else 0
    lines.append(f"\n■ 生活防衛資金チェック")
    lines.append(f"  月間支出:         {fmt(monthly_expense)}")
    lines.append(f"  現金・預金合計:    {fmt((cash or 0) + account_balance)}")
    lines.append(f"  生活防衛月数:      {emergency_months:.1f}ヶ月分")
    if emergency_months >= 6:
        lines.append(f"  → 6ヶ月以上確保できており安心です")
    elif emergency_months >= 3:
        lines.append(f"  → 最低ラインは確保。6ヶ月分を目標にしましょう")
    else:
        lines.append(f"  → 要注意。最低3ヶ月分の確保を優先しましょう")

    # 投資配分
    lines.append(f"\n■ 投資に関するポイント")
    invest_ratio = total_investment / total * 100 if total > 0 else 0
    lines.append(f"  投資比率: {invest_ratio:.0f}%")
    lines.append(f"  → NISA枠を夫婦で活用しているのは非常に良い戦略です")
    lines.append(f"  → iDeCoも開始済み。所得控除のメリットを最大限活用できます")

    sp500_total = sum(v[-1] for k, v in portfolio_data["assets"].items() if "SP500" in k)
    olcan_total = sum(v[-1] for k, v in portfolio_data["assets"].items() if "オルカン" in k)
    sp500_pct = sp500_total / total_investment * 100
    lines.append(f"  SP500比率: {sp500_pct:.0f}% / オルカン比率: {100-sp500_pct:.0f}%")

    # 予算に関する改善点
    lines.append(f"\n■ 家計に関するポイント")
    budget = budget_data["budget"]

    over_budget = []
    for cat, vals in budget.items():
        if vals["budget"] is not None and vals["actual"] > vals["budget"]:
            over_budget.append((cat, vals["actual"] - vals["budget"]))

    if over_budget:
        lines.append(f"  予算超過カテゴリ:")
        for cat, diff in sorted(over_budget, key=lambda x: -x[1]):
            lines.append(f"    - {cat}: {fmt(diff)} 超過")

    # 固定費率
    fixed = budget_data["budget"]["家賃"]["actual"] + budget_data["budget"]["水道光熱費"]["actual"]
    fixed_ratio = fixed / budget_data["summary"]["total"] * 100
    lines.append(f"\n  固定費(家賃+光熱費): {fmt(fixed)} ({fixed_ratio:.0f}%)")
    if fixed_ratio > 70:
        lines.append(f"  → 固定費率が高め。家賃が支出の大部分を占めています")
    lines.append(f"  → 変動費の余地が小さいため、食費・雑費の管理が重要です")

    # 水道光熱費
    if budget_data["budget"]["水道光熱費"]["actual"] > budget_data["budget"]["水道光熱費"]["budget"]:
        diff = budget_data["budget"]["水道光熱費"]["actual"] - budget_data["budget"]["水道光熱費"]["budget"]
        lines.append(f"\n  水道光熱費が予算を{fmt(diff)}超過（予算の{diff/budget_data['budget']['水道光熱費']['budget']*100:.0f}%増）")
        lines.append(f"  → 冬季の暖房費増加の可能性。予算を¥15,000に見直すか、")
        lines.append(f"    季節別予算を設定するのが現実的です")

    return "\n".join(lines)


# ============================================================
# メイン実行
# ============================================================

def main():
    print(analyze_monthly_budget(FEB_2026))
    print(analyze_portfolio(PORTFOLIO))
    print(generate_insights(FEB_2026, PORTFOLIO))

    print(f"\n{'='*60}")
    print(f"  レポート生成完了: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")
    print(f"\n※ GCP設定後は全月のデータを自動取得して分析できます")
    print(f"  → python analyze_sheets.py で実行")


if __name__ == "__main__":
    main()
