"""ライフプラン シミュレーション

教育費・老後資金を中心としたライフプラン試算ロジック。
将来の収支を予測し、目標達成に必要な貯蓄額を算出する。
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


CONFIG_PATH = Path(__file__).parent.parent / "config" / "life_events.json"


@dataclass
class FamilyMember:
    """家族メンバー"""
    name: str
    birth_year: int
    role: str  # "self", "spouse", "child"


@dataclass
class LifeEvent:
    """ライフイベント"""
    name: str
    year: int
    cost: int  # 総額（円）
    category: str  # "education", "retirement", "housing", "other"
    description: str = ""


@dataclass
class LifePlanInput:
    """ライフプランの入力パラメータ"""
    family: list[FamilyMember] = field(default_factory=list)
    current_savings: int = 0  # 現在の貯蓄額
    monthly_income: int = 0   # 月間収入
    monthly_expense: int = 0  # 月間支出
    retirement_age: int = 65  # 退職予定年齢
    life_expectancy: int = 90 # 想定寿命
    inflation_rate: float = 1.0  # インフレ率（%）
    investment_return: float = 3.0  # 運用利回り（%）
    pension_monthly: int = 150000  # 年金月額（目安）
    events: list[LifeEvent] = field(default_factory=list)


def load_education_costs() -> dict:
    """教育費のテンプレートデータを読み込む"""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("education_costs", {})
    return {}


def estimate_education_events(
    child: FamilyMember,
    plan: str = "all_public",
) -> list[LifeEvent]:
    """子供の教育費イベントを生成する

    Args:
        child: 子供の情報
        plan: "all_public"（全て公立）, "all_private"（全て私立）, "mixed"（高校まで公立、大学私立）
    """
    costs = load_education_costs()
    if not costs:
        # デフォルト値（文科省データの概算）
        costs = {
            "kindergarten": {"public": 670000, "private": 1590000, "years": 3, "start_age": 3},
            "elementary": {"public": 2110000, "private": 10000000, "years": 6, "start_age": 6},
            "junior_high": {"public": 1610000, "private": 4440000, "years": 3, "start_age": 12},
            "high_school": {"public": 1540000, "private": 3160000, "years": 3, "start_age": 15},
            "university": {"public": 2690000, "private": 5270000, "years": 4, "start_age": 18},
        }

    plan_mapping = {
        "all_public": {s: "public" for s in costs},
        "all_private": {s: "private" for s in costs},
        "mixed": {
            "kindergarten": "public",
            "elementary": "public",
            "junior_high": "public",
            "high_school": "public",
            "university": "private",
        },
    }

    stage_names = {
        "kindergarten": "幼稚園",
        "elementary": "小学校",
        "junior_high": "中学校",
        "high_school": "高校",
        "university": "大学",
    }

    selected = plan_mapping.get(plan, plan_mapping["all_public"])
    events = []

    for stage, info in costs.items():
        school_type = selected.get(stage, "public")
        start_year = child.birth_year + info["start_age"]
        total_cost = info[school_type]

        events.append(LifeEvent(
            name=f"{child.name} {stage_names.get(stage, stage)}（{school_type}）",
            year=start_year,
            cost=total_cost,
            category="education",
            description=f"{info['years']}年間の総額",
        ))

    return events


def estimate_retirement_fund(plan_input: LifePlanInput) -> dict:
    """老後資金の試算"""
    self_member = next((m for m in plan_input.family if m.role == "self"), None)
    if not self_member:
        return {"error": "本人の情報が設定されていません"}

    current_age = 2026 - self_member.birth_year
    years_to_retirement = max(0, plan_input.retirement_age - current_age)
    retirement_years = plan_input.life_expectancy - plan_input.retirement_age

    # 老後の月間生活費（現在の支出の70%を目安）
    retirement_monthly_expense = int(plan_input.monthly_expense * 0.7)

    # インフレ調整
    inflation_factor = (1 + plan_input.inflation_rate / 100) ** years_to_retirement
    adjusted_monthly_expense = int(retirement_monthly_expense * inflation_factor)

    # 老後に必要な総額
    total_retirement_cost = adjusted_monthly_expense * 12 * retirement_years

    # 年金でカバーできる分
    total_pension = plan_input.pension_monthly * 12 * retirement_years

    # 不足額
    shortfall = max(0, total_retirement_cost - total_pension)

    # 必要な月間貯蓄額（運用利回りを考慮した簡易計算）
    if years_to_retirement > 0:
        monthly_rate = plan_input.investment_return / 100 / 12
        if monthly_rate > 0:
            months = years_to_retirement * 12
            # 将来価値の年金現価係数
            fv_factor = ((1 + monthly_rate) ** months - 1) / monthly_rate
            required_monthly_saving = int(shortfall / fv_factor)
        else:
            required_monthly_saving = int(shortfall / (years_to_retirement * 12))
    else:
        required_monthly_saving = 0

    return {
        "current_age": current_age,
        "retirement_age": plan_input.retirement_age,
        "years_to_retirement": years_to_retirement,
        "retirement_years": retirement_years,
        "retirement_monthly_expense": retirement_monthly_expense,
        "adjusted_monthly_expense": adjusted_monthly_expense,
        "total_retirement_cost": total_retirement_cost,
        "total_pension": total_pension,
        "shortfall": shortfall,
        "required_monthly_saving": required_monthly_saving,
        "current_monthly_savings": plan_input.monthly_income - plan_input.monthly_expense,
    }


def simulate_yearly_cashflow(plan_input: LifePlanInput, years: int = 40) -> list[dict]:
    """年ごとのキャッシュフロー シミュレーション"""
    self_member = next((m for m in plan_input.family if m.role == "self"), None)
    if not self_member:
        return []

    current_age = 2026 - self_member.birth_year
    balance = plan_input.current_savings
    monthly_savings = plan_input.monthly_income - plan_input.monthly_expense

    cashflow = []

    for i in range(years):
        year = 2026 + i
        age = current_age + i

        # 収入（退職後は年金のみ）
        if age < plan_input.retirement_age:
            annual_income = plan_input.monthly_income * 12
            annual_expense = plan_input.monthly_expense * 12
        else:
            annual_income = plan_input.pension_monthly * 12
            annual_expense = int(plan_input.monthly_expense * 0.7) * 12

        # インフレ調整（支出のみ）
        inflation_factor = (1 + plan_input.inflation_rate / 100) ** i
        annual_expense = int(annual_expense * inflation_factor)

        # ライフイベントの費用
        event_costs = sum(e.cost for e in plan_input.events if e.year == year)
        event_names = [e.name for e in plan_input.events if e.year == year]

        # 年間収支
        annual_balance = annual_income - annual_expense - event_costs

        # 運用益
        investment_gain = int(balance * plan_input.investment_return / 100) if balance > 0 else 0

        balance = balance + annual_balance + investment_gain

        cashflow.append({
            "year": year,
            "age": age,
            "annual_income": annual_income,
            "annual_expense": annual_expense,
            "event_costs": event_costs,
            "events": ", ".join(event_names) if event_names else "",
            "investment_gain": investment_gain,
            "annual_balance": annual_balance + investment_gain,
            "cumulative_savings": balance,
        })

    return cashflow


def life_plan_to_dict(plan_input: LifePlanInput) -> dict:
    """LifePlanInputを辞書に変換（保存用）"""
    return {
        "family": [asdict(m) for m in plan_input.family],
        "current_savings": plan_input.current_savings,
        "monthly_income": plan_input.monthly_income,
        "monthly_expense": plan_input.monthly_expense,
        "retirement_age": plan_input.retirement_age,
        "life_expectancy": plan_input.life_expectancy,
        "inflation_rate": plan_input.inflation_rate,
        "investment_return": plan_input.investment_return,
        "pension_monthly": plan_input.pension_monthly,
        "events": [asdict(e) for e in plan_input.events],
    }


def dict_to_life_plan(data: dict) -> LifePlanInput:
    """辞書からLifePlanInputを復元"""
    return LifePlanInput(
        family=[FamilyMember(**m) for m in data.get("family", [])],
        current_savings=data.get("current_savings", 0),
        monthly_income=data.get("monthly_income", 0),
        monthly_expense=data.get("monthly_expense", 0),
        retirement_age=data.get("retirement_age", 65),
        life_expectancy=data.get("life_expectancy", 90),
        inflation_rate=data.get("inflation_rate", 1.0),
        investment_return=data.get("investment_return", 3.0),
        pension_monthly=data.get("pension_monthly", 150000),
        events=[LifeEvent(**e) for e in data.get("events", [])],
    )
