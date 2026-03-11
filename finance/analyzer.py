"""収支分析エンジン

月次集計、カテゴリ別分析、前月比較、年間推移などの
分析ロジックを提供する。
"""

import pandas as pd


def monthly_summary(df: pd.DataFrame, year: int, month: int) -> dict:
    """指定月の収支サマリーを返す"""
    month_df = df[(df["year"] == year) & (df["month"] == month)]

    income = month_df[month_df["type"] == "income"]["amount"].sum()
    expense = abs(month_df[month_df["type"] == "expense"]["amount"].sum())
    balance = income - expense

    return {
        "year": year,
        "month": month,
        "income": income,
        "expense": expense,
        "balance": balance,
        "transaction_count": len(month_df),
    }


def category_breakdown(df: pd.DataFrame, year: int, month: int, tx_type: str = "expense") -> pd.DataFrame:
    """指定月のカテゴリ別集計を返す

    Args:
        tx_type: "expense" or "income"
    """
    month_df = df[(df["year"] == year) & (df["month"] == month) & (df["type"] == tx_type)]

    if month_df.empty:
        return pd.DataFrame(columns=["category", "amount", "percentage"])

    result = month_df.groupby("category")["amount"].sum().abs().reset_index()
    result = result.sort_values("amount", ascending=False)
    total = result["amount"].sum()
    result["percentage"] = (result["amount"] / total * 100).round(1) if total > 0 else 0
    return result


def monthly_comparison(df: pd.DataFrame, year: int, month: int) -> dict:
    """前月との比較を返す"""
    current = monthly_summary(df, year, month)

    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year = year - 1

    previous = monthly_summary(df, prev_year, prev_month)

    def diff_pct(current_val, previous_val):
        if previous_val == 0:
            return None
        return round((current_val - previous_val) / previous_val * 100, 1)

    return {
        "current": current,
        "previous": previous,
        "income_change": current["income"] - previous["income"],
        "expense_change": current["expense"] - previous["expense"],
        "balance_change": current["balance"] - previous["balance"],
        "income_change_pct": diff_pct(current["income"], previous["income"]),
        "expense_change_pct": diff_pct(current["expense"], previous["expense"]),
    }


def yearly_trend(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """年間の月別収支推移を返す"""
    results = []
    for month in range(1, 13):
        summary = monthly_summary(df, year, month)
        results.append(summary)
    return pd.DataFrame(results)


def top_expenses(df: pd.DataFrame, year: int, month: int, n: int = 10) -> pd.DataFrame:
    """指定月の支出上位N件を返す"""
    month_df = df[
        (df["year"] == year) & (df["month"] == month) & (df["type"] == "expense")
    ].copy()
    month_df["amount"] = month_df["amount"].abs()
    return month_df.nlargest(n, "amount")[["date", "category", "amount", "memo"]]


def average_monthly_expense(df: pd.DataFrame, n_months: int = 6) -> dict:
    """直近N ヶ月の平均月間支出を返す（ライフプラン試算の基礎データ）"""
    periods = df.groupby(["year", "month"]).agg(
        total_expense=("amount", lambda x: abs(x[x < 0].sum()) if (x < 0).any() else 0),
        total_income=("amount", lambda x: x[x > 0].sum()),
    ).reset_index()

    periods = periods.sort_values(["year", "month"], ascending=False).head(n_months)

    return {
        "avg_monthly_expense": periods["total_expense"].mean(),
        "avg_monthly_income": periods["total_income"].mean(),
        "months_analyzed": len(periods),
    }


def savings_rate(df: pd.DataFrame, year: int, month: int):
    """貯蓄率を算出する（(収入-支出)/収入 * 100）"""
    summary = monthly_summary(df, year, month)
    if summary["income"] == 0:
        return None
    return round(summary["balance"] / summary["income"] * 100, 1)
