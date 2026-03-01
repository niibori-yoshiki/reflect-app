"""AI 家計アドバイザー

Claude APIを使用して、家計データに基づくアドバイスや
ライフプランの相談に対応する。
"""

import os
import anthropic
from dotenv import load_dotenv

load_dotenv()


def get_client() -> anthropic.Anthropic:
    """Anthropicクライアントを返す"""
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


SYSTEM_PROMPT = """あなたは家計管理とライフプランニングの専門家です。
ユーザーの家計データに基づいて、具体的で実践的なアドバイスを提供してください。

以下のルールに従ってください：
- 日本の税制・社会保障制度を前提とする
- 具体的な数字を交えて回答する
- 無理のない現実的な提案をする
- 節約だけでなく、収入増やバランスの良い生活も考慮する
- 投資に関しては一般的な情報のみ提供し、具体的な銘柄推奨はしない
"""


def analyze_spending(monthly_data: dict, category_data: list[dict]) -> str:
    """月次の支出データを分析してアドバイスを生成する"""
    client = get_client()

    user_message = f"""以下の今月の家計データを分析し、改善ポイントをアドバイスしてください。

【月次サマリー】
- 収入: {monthly_data.get('income', 0):,.0f}円
- 支出: {monthly_data.get('expense', 0):,.0f}円
- 収支: {monthly_data.get('balance', 0):,.0f}円

【カテゴリ別支出】
"""
    for cat in category_data:
        user_message += f"- {cat.get('category', '不明')}: {cat.get('amount', 0):,.0f}円 ({cat.get('percentage', 0)}%)\n"

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return message.content[0].text


def life_plan_advice(retirement_data: dict, cashflow_summary: dict) -> str:
    """ライフプランデータに基づくアドバイスを生成する"""
    client = get_client()

    user_message = f"""以下のライフプランデータに基づいて、アドバイスをお願いします。

【老後資金の試算】
- 現在の年齢: {retirement_data.get('current_age')}歳
- 退職予定: {retirement_data.get('retirement_age')}歳
- 退職までの年数: {retirement_data.get('years_to_retirement')}年
- 老後の月間生活費（インフレ調整後）: {retirement_data.get('adjusted_monthly_expense', 0):,}円
- 老後に必要な総額: {retirement_data.get('total_retirement_cost', 0):,}円
- 年金総額: {retirement_data.get('total_pension', 0):,}円
- 不足額: {retirement_data.get('shortfall', 0):,}円
- 必要な月間貯蓄額: {retirement_data.get('required_monthly_saving', 0):,}円
- 現在の月間貯蓄額: {retirement_data.get('current_monthly_savings', 0):,}円

【キャッシュフロー概要】
- シミュレーション年数: {cashflow_summary.get('years', 0)}年
- 資金がマイナスになる年齢: {cashflow_summary.get('deficit_age', 'なし')}
- 最大貯蓄額: {cashflow_summary.get('max_savings', 0):,}円
"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return message.content[0].text


def chat(messages: list[dict], context: str = "") -> str:
    """自由な家計相談チャット"""
    client = get_client()

    system = SYSTEM_PROMPT
    if context:
        system += f"\n\n【ユーザーの家計データコンテキスト】\n{context}"

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=system,
        messages=messages,
    )
    return response.content[0].text
