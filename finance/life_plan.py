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
class SpouseIncomePhase:
    """配偶者の収入フェーズ"""
    label: str
    start_year: int
    end_year: int
    monthly_income: int  # 円


@dataclass
class SpouseEmploymentPlan:
    """配偶者の就労プラン"""
    phases: list[SpouseIncomePhase] = field(default_factory=list)

    def get_monthly_income(self, year: int) -> int:
        """指定年の配偶者月収を返す"""
        for phase in self.phases:
            if phase.start_year <= year <= phase.end_year:
                return phase.monthly_income
        return 0


@dataclass
class LifePlanInput:
    """ライフプランの入力パラメータ"""
    family: list[FamilyMember] = field(default_factory=list)
    current_savings: int = 0  # 現在の貯蓄額
    monthly_income: int = 0   # 月間収入（後方互換用: 世帯合計）
    monthly_income_self: int = 0  # 自分の月間手取り
    spouse_employment: SpouseEmploymentPlan | None = None
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


def build_spouse_employment_plan(
    employment_type: str,
    current_income: int,
    children_config: list[dict],
    spouse_birth_year: int,
    spouse_retirement_age: int,
) -> SpouseEmploymentPlan:
    """UIの入力から配偶者の就労プランを生成する

    Args:
        employment_type: "full_time", "part_time", "homemaker"
        current_income: 現在の手取り月収（万円）
        children_config: 子供ごとの産休育休設定リスト
            各要素: {child_name, birth_year, take_leave, leave_years,
                     leave_income(円), after_leave, after_income(円)}
        spouse_birth_year: 配偶者の生年
        spouse_retirement_age: 配偶者の退職予定年齢
    """
    if employment_type == "homemaker":
        return SpouseEmploymentPlan(phases=[])

    phases = []
    current_year = 2026
    income_yen = current_income * 10000
    resigned = False

    configs = sorted(children_config, key=lambda c: c["birth_year"])

    for cfg in configs:
        if resigned:
            break

        birth_year = cfg["birth_year"]

        # この子供の出産前の就労フェーズ
        if current_year < birth_year and income_yen > 0:
            phases.append(SpouseIncomePhase(
                label="就労中",
                start_year=current_year,
                end_year=birth_year - 1,
                monthly_income=income_yen,
            ))

        if cfg.get("take_leave"):
            leave_years = cfg.get("leave_years", 1)
            leave_end = birth_year + leave_years - 1
            leave_income = cfg.get("leave_income", int(income_yen * 0.67))

            actual_start = max(current_year, birth_year)
            if actual_start <= leave_end:
                phases.append(SpouseIncomePhase(
                    label=f"産休・育休（{cfg.get('child_name', '')}）",
                    start_year=actual_start,
                    end_year=leave_end,
                    monthly_income=leave_income,
                ))
            current_year = leave_end + 1
        else:
            current_year = max(current_year, birth_year + 1)

        after = cfg.get("after_leave", "full_time")
        if after == "resign":
            resigned = True
            income_yen = 0
        elif after != "full_time":
            after_income = cfg.get("after_income", 0)
            if after_income > 0:
                income_yen = after_income

    # 退職まで就労
    if not resigned and income_yen > 0:
        retirement_year = spouse_birth_year + spouse_retirement_age
        if current_year <= retirement_year:
            phases.append(SpouseIncomePhase(
                label="就労中",
                start_year=current_year,
                end_year=retirement_year,
                monthly_income=income_yen,
            ))

    return SpouseEmploymentPlan(phases=phases)


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

    # 現在の月間収入（新モデル対応）
    if plan_input.monthly_income_self > 0 and plan_input.spouse_employment:
        spouse_income = plan_input.spouse_employment.get_monthly_income(2026)
        monthly_income = plan_input.monthly_income_self + spouse_income
    else:
        monthly_income = plan_input.monthly_income

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
        "current_monthly_savings": monthly_income - plan_input.monthly_expense,
    }


def simulate_yearly_cashflow(plan_input: LifePlanInput, years: int = 40) -> list[dict]:
    """年ごとのキャッシュフロー シミュレーション"""
    self_member = next((m for m in plan_input.family if m.role == "self"), None)
    if not self_member:
        return []

    current_age = 2026 - self_member.birth_year
    balance = plan_input.current_savings
    use_new_model = (plan_input.monthly_income_self > 0
                     and plan_input.spouse_employment is not None)

    cashflow = []

    for i in range(years):
        year = 2026 + i
        age = current_age + i

        if use_new_model:
            # 新モデル: 自分と配偶者を分離
            if age < plan_input.retirement_age:
                self_monthly = plan_input.monthly_income_self
            else:
                self_monthly = 0
            spouse_monthly = plan_input.spouse_employment.get_monthly_income(year)

            if age < plan_input.retirement_age:
                annual_income = (self_monthly + spouse_monthly) * 12
                annual_expense = plan_input.monthly_expense * 12
            else:
                annual_income = plan_input.pension_monthly * 12 + spouse_monthly * 12
                annual_expense = int(plan_input.monthly_expense * 0.7) * 12
        else:
            # 旧モデル: 世帯合計
            if age < plan_input.retirement_age:
                self_monthly = plan_input.monthly_income
                spouse_monthly = 0
                annual_income = plan_input.monthly_income * 12
                annual_expense = plan_input.monthly_expense * 12
            else:
                self_monthly = 0
                spouse_monthly = 0
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
            "self_income": self_monthly * 12,
            "spouse_income": spouse_monthly * 12,
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
    result = {
        "family": [asdict(m) for m in plan_input.family],
        "current_savings": plan_input.current_savings,
        "monthly_income": plan_input.monthly_income,
        "monthly_income_self": plan_input.monthly_income_self,
        "monthly_expense": plan_input.monthly_expense,
        "retirement_age": plan_input.retirement_age,
        "life_expectancy": plan_input.life_expectancy,
        "inflation_rate": plan_input.inflation_rate,
        "investment_return": plan_input.investment_return,
        "pension_monthly": plan_input.pension_monthly,
        "events": [asdict(e) for e in plan_input.events],
    }
    if plan_input.spouse_employment:
        result["spouse_employment"] = {
            "phases": [asdict(p) for p in plan_input.spouse_employment.phases]
        }
    return result


def dict_to_life_plan(data: dict) -> LifePlanInput:
    """辞書からLifePlanInputを復元"""
    spouse_plan = None
    spouse_data = data.get("spouse_employment")
    if spouse_data:
        spouse_plan = SpouseEmploymentPlan(
            phases=[SpouseIncomePhase(**p) for p in spouse_data.get("phases", [])]
        )

    return LifePlanInput(
        family=[FamilyMember(**m) for m in data.get("family", [])],
        current_savings=data.get("current_savings", 0),
        monthly_income=data.get("monthly_income", 0),
        monthly_income_self=data.get("monthly_income_self", 0),
        spouse_employment=spouse_plan,
        monthly_expense=data.get("monthly_expense", 0),
        retirement_age=data.get("retirement_age", 65),
        life_expectancy=data.get("life_expectancy", 90),
        inflation_rate=data.get("inflation_rate", 1.0),
        investment_return=data.get("investment_return", 3.0),
        pension_monthly=data.get("pension_monthly", 150000),
        events=[LifeEvent(**e) for e in data.get("events", [])],
    )
