"""
ビジネス日記アプリ - AI対話型ビジネス振り返りツール
"""

import json
import os
import datetime
from pathlib import Path

import streamlit as st
import anthropic
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
DATA_DIR = Path("data")
DIARY_DIR = DATA_DIR / "diaries"
PROFILE_PATH = DATA_DIR / "profile.json"
MAX_TURNS = 4  # この往復数に達したらまとめモードへ

SKILL_CATEGORIES = [
    "プロジェクト管理",
    "交渉",
    "プレゼンテーション",
    "リーダーシップ",
    "問題解決",
    "コミュニケーション",
]

SYSTEM_PROMPT = """\
あなたはビジネスパーソン向けの日記アシスタントです。
ユーザーが今日の仕事について振り返るのを手助けしてください。

## ルール
- 日本語で会話してください。
- 1回の返答は3〜4文程度で簡潔に。
- 具体的なエピソードを引き出す質問をしてください。
- 感情や学びについても掘り下げてください。
- ユーザーの発言に共感しつつ、深掘りする質問を1つ添えてください。
"""

SUMMARY_PROMPT = """\
以下のビジネス日記の会話をもとに、JSON形式で以下を出力してください。
必ず有効なJSONのみを返してください。マークダウンのコードブロックや説明文は不要です。

{
  "summary": "今日の振り返りの要約（3〜4文）",
  "key_learnings": ["学び1", "学び2", "学び3"],
  "english_phrases": [
    {
      "english": "英語フレーズ",
      "japanese": "日本語訳",
      "context": "どんな場面で使えるか"
    },
    {
      "english": "英語フレーズ",
      "japanese": "日本語訳",
      "context": "どんな場面で使えるか"
    },
    {
      "english": "英語フレーズ",
      "japanese": "日本語訳",
      "context": "どんな場面で使えるか"
    }
  ],
  "skills": {
    "プロジェクト管理": 0,
    "交渉": 0,
    "プレゼンテーション": 0,
    "リーダーシップ": 0,
    "問題解決": 0,
    "コミュニケーション": 0
  },
  "xp_gained": 0
}

## ルール
- english_phrases: 会話内容に関連するビジネス英語フレーズを3つ抽出。実務で使える自然な表現を選んでください。
- skills: 会話内容から判断して、関連するスキルに 0〜5 のスコアをつけてください（0=関連なし）。
- xp_gained: 振り返りの深さに応じて 10〜50 の経験値を設定してください。
- summary, key_learnings は日本語で記述してください。

## 会話内容
"""

QUIZ_PROMPT = """\
以下の英語フレーズについて、穴埋めクイズを1問作ってください。
JSONのみを返してください。

{
  "question": "穴埋め問題文（___で空欄を表示）",
  "answer": "正解の単語・フレーズ",
  "hint": "ヒント"
}

フレーズ: {phrase}
日本語訳: {japanese}
"""


# ---------------------------------------------------------------------------
# データ永続化
# ---------------------------------------------------------------------------
def ensure_dirs():
    DIARY_DIR.mkdir(parents=True, exist_ok=True)


def load_profile() -> dict:
    if PROFILE_PATH.exists():
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    return {"level": 1, "xp": 0, "total_entries": 0, "skills": {s: 0 for s in SKILL_CATEGORIES}}


def save_profile(profile: dict):
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def xp_for_next_level(level: int) -> int:
    return level * 100


def add_xp(profile: dict, xp: int) -> dict:
    profile["xp"] += xp
    while profile["xp"] >= xp_for_next_level(profile["level"]):
        profile["xp"] -= xp_for_next_level(profile["level"])
        profile["level"] += 1
    return profile


def save_diary(entry: dict):
    today = datetime.date.today().isoformat()
    path = DIARY_DIR / f"{today}.json"
    entries = []
    if path.exists():
        entries = json.loads(path.read_text(encoding="utf-8"))
    entries.append(entry)
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def load_all_diaries() -> list[tuple[str, list[dict]]]:
    results = []
    if not DIARY_DIR.exists():
        return results
    for f in sorted(DIARY_DIR.glob("*.json"), reverse=True):
        entries = json.loads(f.read_text(encoding="utf-8"))
        results.append((f.stem, entries))
    return results


# ---------------------------------------------------------------------------
# AI呼び出し
# ---------------------------------------------------------------------------
def get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        st.error("ANTHROPIC_API_KEY が設定されていません。`.env` ファイルを確認してください。")
        st.stop()
    return anthropic.Anthropic(api_key=api_key)


def chat(client: anthropic.Anthropic, messages: list[dict]) -> str:
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    return resp.content[0].text


def generate_summary(client: anthropic.Anthropic, messages: list[dict]):
    conversation_text = "\n".join(
        f"{'ユーザー' if m['role'] == 'user' else 'AI'}: {m['content']}" for m in messages
    )
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{"role": "user", "content": SUMMARY_PROMPT + conversation_text}],
    )
    raw = resp.content[0].text.strip()
    # マークダウンのコードブロックを除去
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        st.error("まとめの生成に失敗しました。もう一度お試しください。")
        return None


def generate_quiz(client: anthropic.Anthropic, phrase: str, japanese: str):
    prompt = QUIZ_PROMPT.format(phrase=phrase, japanese=japanese)
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# UI ヘルパー
# ---------------------------------------------------------------------------
def render_skill_chart(skills: dict):
    """スキルをバーチャートで表示"""
    import html as html_module

    bars_html = ""
    for skill, value in skills.items():
        max_val = max(max(skills.values()), 1)
        pct = int((value / max_val) * 100) if max_val > 0 else 0
        skill_escaped = html_module.escape(skill)
        bars_html += f"""
        <div style="margin-bottom:8px;">
            <div style="font-size:14px;margin-bottom:2px;">{skill_escaped}</div>
            <div style="background:#e0e0e0;border-radius:4px;height:20px;width:100%;">
                <div style="background:linear-gradient(90deg,#4CAF50,#81C784);
                            height:100%;border-radius:4px;width:{pct}%;
                            min-width:{'20px' if value > 0 else '0'};
                            display:flex;align-items:center;justify-content:flex-end;
                            padding-right:6px;font-size:12px;color:white;font-weight:bold;">
                    {value}
                </div>
            </div>
        </div>"""
    st.markdown(bars_html, unsafe_allow_html=True)


def render_level_badge(profile: dict):
    level = profile["level"]
    xp = profile["xp"]
    needed = xp_for_next_level(level)
    pct = int((xp / needed) * 100)
    st.markdown(
        f"""
        <div style="text-align:center;padding:10px;background:linear-gradient(135deg,#1a237e,#283593);
                    border-radius:12px;color:white;margin-bottom:16px;">
            <div style="font-size:28px;font-weight:bold;">Lv. {level}</div>
            <div style="font-size:13px;margin:4px 0;">XP: {xp} / {needed}</div>
            <div style="background:rgba(255,255,255,0.3);border-radius:6px;height:10px;margin:4px 16px;">
                <div style="background:#FFD54F;height:100%;border-radius:6px;width:{pct}%;"></div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="ビジネス日記", page_icon="📓", layout="wide")
    ensure_dirs()

    # セッション初期化
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "turn_count" not in st.session_state:
        st.session_state.turn_count = 0
    if "phase" not in st.session_state:
        st.session_state.phase = "chat"  # chat -> summary -> quiz
    if "summary_data" not in st.session_state:
        st.session_state.summary_data = None
    if "quiz_data" not in st.session_state:
        st.session_state.quiz_data = None
    if "quiz_answered" not in st.session_state:
        st.session_state.quiz_answered = False
    if "waiting_for_ai" not in st.session_state:
        st.session_state.waiting_for_ai = False

    profile = load_profile()

    # --- サイドバー ---
    with st.sidebar:
        st.title("📓 ビジネス日記")
        render_level_badge(profile)

        st.subheader("スキル")
        render_skill_chart(profile["skills"])

        st.divider()
        st.subheader("過去の記録")
        diaries = load_all_diaries()
        if not diaries:
            st.caption("まだ記録がありません")
        for date_str, entries in diaries:
            with st.expander(f"📅 {date_str} ({len(entries)}件)"):
                for i, entry in enumerate(entries):
                    st.markdown(f"**{i+1}.** {entry.get('summary', '（要約なし）')}")
                    if entry.get("key_learnings"):
                        for learning in entry["key_learnings"]:
                            st.markdown(f"  - {learning}")

        st.divider()
        if st.button("🔄 新しい振り返りを始める"):
            st.session_state.messages = []
            st.session_state.turn_count = 0
            st.session_state.phase = "chat"
            st.session_state.summary_data = None
            st.session_state.quiz_data = None
            st.session_state.quiz_answered = False
            st.session_state.waiting_for_ai = False
            st.rerun()

    # --- メインエリア ---
    st.title("今日の振り返り")

    client = get_client()

    # ---- チャットフェーズ ----
    if st.session_state.phase == "chat":
        # 初回メッセージ
        if not st.session_state.messages:
            greeting = "お疲れさまです！今日のお仕事はいかがでしたか？印象に残ったことを教えてください。"
            st.session_state.messages.append({"role": "assistant", "content": greeting})

        # 会話表示
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # AI応答待ちの場合、生成して表示
        if st.session_state.waiting_for_ai:
            with st.chat_message("assistant"):
                with st.spinner("考え中..."):
                    ai_messages = [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.messages
                    ]
                    reply = chat(client, ai_messages)
                    st.markdown(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                    st.session_state.waiting_for_ai = False
                    st.rerun()

        remaining = MAX_TURNS - st.session_state.turn_count
        if remaining > 0:
            st.caption(f"あと {remaining} 回の会話でまとめに入ります")

        # ユーザー入力
        if user_input := st.chat_input("今日の仕事について話してください..."):
            st.session_state.messages.append({"role": "user", "content": user_input})
            st.session_state.turn_count += 1

            if st.session_state.turn_count >= MAX_TURNS:
                # まとめモードへ移行
                st.session_state.phase = "summarizing"
                st.rerun()
            else:
                # AI応答を次のレンダリングで生成
                st.session_state.waiting_for_ai = True
                st.rerun()

    # ---- まとめ生成中 ----
    elif st.session_state.phase == "summarizing":
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        with st.spinner("振り返りをまとめています..."):
            summary = generate_summary(client, st.session_state.messages)
            if summary:
                st.session_state.summary_data = summary
                st.session_state.phase = "summary"

                # プロフィール更新
                xp = summary.get("xp_gained", 20)
                add_xp(profile, xp)
                profile["total_entries"] += 1
                for skill, val in summary.get("skills", {}).items():
                    if skill in profile["skills"]:
                        profile["skills"][skill] += val
                save_profile(profile)

                # 日記保存
                save_diary(summary)

                st.rerun()
            else:
                st.session_state.phase = "chat"
                st.rerun()

    # ---- まとめ表示フェーズ ----
    elif st.session_state.phase == "summary":
        summary = st.session_state.summary_data

        st.success("振り返りが完了しました！")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📝 今日のまとめ")
            st.write(summary.get("summary", ""))

            st.subheader("💡 学んだこと")
            for learning in summary.get("key_learnings", []):
                st.markdown(f"- {learning}")

        with col2:
            st.subheader("🌐 ビジネス英語フレーズ")
            for i, phrase in enumerate(summary.get("english_phrases", []), 1):
                with st.container():
                    st.markdown(
                        f"""
                        <div style="background:#f0f4ff;border-radius:8px;padding:12px;margin-bottom:8px;
                                    border-left:4px solid #1a237e;">
                            <div style="font-size:16px;font-weight:bold;color:#1a237e;">
                                {i}. {phrase['english']}
                            </div>
                            <div style="font-size:14px;color:#333;margin-top:4px;">
                                {phrase['japanese']}
                            </div>
                            <div style="font-size:12px;color:#666;margin-top:4px;">
                                💬 {phrase['context']}
                            </div>
                        </div>""",
                        unsafe_allow_html=True,
                    )

            st.subheader("📊 今回のスキルポイント")
            session_skills = {k: v for k, v in summary.get("skills", {}).items() if v > 0}
            if session_skills:
                render_skill_chart(session_skills)
            else:
                st.caption("該当するスキルはありませんでした")

        st.divider()

        xp = summary.get("xp_gained", 0)
        st.markdown(f"**🎯 獲得経験値: +{xp} XP**")

        if st.button("📝 クイズに挑戦する"):
            st.session_state.phase = "quiz"
            st.rerun()

        if st.button("🔄 新しい振り返りを始める", key="new_from_summary"):
            st.session_state.messages = []
            st.session_state.turn_count = 0
            st.session_state.phase = "chat"
            st.session_state.summary_data = None
            st.session_state.quiz_data = None
            st.session_state.quiz_answered = False
            st.session_state.waiting_for_ai = False
            st.rerun()

    # ---- クイズフェーズ ----
    elif st.session_state.phase == "quiz":
        st.subheader("📝 ビジネス英語クイズ")

        summary = st.session_state.summary_data
        phrases = summary.get("english_phrases", [])

        if not phrases:
            st.warning("フレーズが見つかりませんでした。")
            st.session_state.phase = "summary"
            st.rerun()

        # クイズ生成
        if st.session_state.quiz_data is None:
            with st.spinner("クイズを作成中..."):
                phrase = phrases[0]
                quiz = generate_quiz(client, phrase["english"], phrase["japanese"])
                if quiz:
                    st.session_state.quiz_data = quiz
                    st.rerun()
                else:
                    st.error("クイズの生成に失敗しました。")
                    st.session_state.phase = "summary"
                    st.rerun()

        quiz = st.session_state.quiz_data

        st.markdown(
            f"""
            <div style="background:#fff8e1;border-radius:12px;padding:20px;margin:16px 0;
                        border:2px solid #FFD54F;color:#1a1a1a;">
                <div style="font-size:18px;font-weight:bold;margin-bottom:12px;color:#1a1a1a;">
                    🤔 穴埋め問題
                </div>
                <div style="font-size:16px;line-height:1.8;color:#1a1a1a;">
                    {quiz.get('question', '')}
                </div>
                <div style="font-size:13px;color:#555;margin-top:8px;">
                    💡 ヒント: {quiz.get('hint', '')}
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

        if not st.session_state.quiz_answered:
            answer = st.text_input("答えを入力してください:", key="quiz_answer_input")
            if st.button("回答する"):
                correct = quiz.get("answer", "")
                if answer.strip().lower() == correct.strip().lower():
                    st.balloons()
                    st.success(f"正解！ 🎉  答え: **{correct}**")
                    # ボーナスXP
                    profile = load_profile()
                    add_xp(profile, 10)
                    save_profile(profile)
                    st.info("ボーナス +10 XP を獲得しました！")
                else:
                    st.error(f"残念！ 正解は **{correct}** でした。")
                st.session_state.quiz_answered = True
                st.rerun()
        else:
            correct = quiz.get("answer", "")
            st.info(f"正解: **{correct}**")
            if st.button("🔄 新しい振り返りを始める", key="new_from_quiz"):
                st.session_state.messages = []
                st.session_state.turn_count = 0
                st.session_state.phase = "chat"
                st.session_state.summary_data = None
                st.session_state.quiz_data = None
                st.session_state.quiz_answered = False
                st.session_state.waiting_for_ai = False
                st.rerun()


if __name__ == "__main__":
    main()
