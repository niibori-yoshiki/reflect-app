"""
English Learning Diary - AI対話型英語学習アプリ
音声会話・クイズ道場・単語帳で英語力をレベルアップ
"""

import json
import os
import datetime
import io
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
VOCAB_PATH = DATA_DIR / "vocabulary.json"
MAX_TURNS = 4

SYSTEM_PROMPT = """\
あなたは英語学習をサポートするAIパートナーです。
ユーザーが今日の出来事について振り返るのを手助けしながら、
関連する英語フレーズを教えてください。

## ルール
- 日本語で会話してください。
- 1回の返答は3〜4文程度で簡潔に。
- 具体的なエピソードを引き出す質問をしてください。
- 会話の中で、関連する英語表現を1つ自然に紹介してください。
- ユーザーの発言に共感しつつ、深掘りする質問を1つ添えてください。
"""

VOICE_SYSTEM_PROMPT = """\
あなたは英語学習をサポートするAIパートナーです。音声会話モードです。

## ルール
- 日本語で会話してください。
- 返答は1〜2文で極力短くしてください。音声で聞きやすい長さにしてください。
- 自然な会話のテンポを保ってください。
- 会話の中で英語のフレーズを1つ紹介してください。
- フレンドリーで親しみやすいトーンで話してください。
"""

SUMMARY_PROMPT = """\
以下の会話をもとに、JSON形式で以下を出力してください。
必ず有効なJSONのみを返してください。マークダウンのコードブロックや説明文は不要です。

{
  "summary": "今日の振り返りの要約（3〜4文）",
  "key_learnings": ["学び1", "学び2", "学び3"],
  "english_phrases": [
    {
      "english": "英語フレーズ",
      "japanese": "日本語訳",
      "context": "どんな場面で使えるか"
    }
  ],
  "xp_gained": 0
}

## ルール
- english_phrases: 会話内容に関連する実用的な英語フレーズを3つ抽出。
- xp_gained: 振り返りの深さに応じて 10〜50 の経験値を設定。
- summary, key_learnings は日本語で記述。

## 会話内容
"""

QUIZ_PROMPT = """\
以下の英語フレーズについて、穴埋めクイズを1問作ってください。
JSONのみを返してください。

{{
  "question": "穴埋め問題文（___で空欄を表示）",
  "answer": "正解の単語・フレーズ",
  "hint": "ヒント",
  "explanation": "解説（1文）"
}}

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
    return {"level": 1, "xp": 0, "total_entries": 0, "total_phrases": 0, "streak_days": 0, "last_date": ""}


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


def update_streak(profile: dict) -> dict:
    today = datetime.date.today().isoformat()
    if profile.get("last_date") == today:
        return profile
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    if profile.get("last_date") == yesterday:
        profile["streak_days"] = profile.get("streak_days", 0) + 1
    else:
        profile["streak_days"] = 1
    profile["last_date"] = today
    return profile


def save_diary(entry: dict):
    today = datetime.date.today().isoformat()
    path = DIARY_DIR / f"{today}.json"
    entries = []
    if path.exists():
        entries = json.loads(path.read_text(encoding="utf-8"))
    entries.append(entry)
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def load_all_diaries() -> List[Tuple[str, List[dict]]]:
    results = []
    if not DIARY_DIR.exists():
        return results
    for f in sorted(DIARY_DIR.glob("*.json"), reverse=True):
        entries = json.loads(f.read_text(encoding="utf-8"))
        results.append((f.stem, entries))
    return results


def normalize_phrase(item) -> dict:
    """文字列またはdictをフレーズdictに正規化する"""
    if isinstance(item, dict):
        return item
    if isinstance(item, str):
        return {
            "english": item,
            "japanese": "",
            "context": "",
            "learned_date": "",
            "review_count": 0,
            "mastered": False,
        }
    return {
        "english": str(item),
        "japanese": "",
        "context": "",
        "learned_date": "",
        "review_count": 0,
        "mastered": False,
    }


def load_vocabulary() -> List[dict]:
    if VOCAB_PATH.exists():
        raw = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
        return [normalize_phrase(item) for item in raw]
    return []


def save_vocabulary(vocab: List[dict]):
    VOCAB_PATH.write_text(json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8")


def add_phrases_to_vocabulary(phrases: List[dict]):
    vocab = load_vocabulary()
    existing = {p["english"] for p in vocab}
    today = datetime.date.today().isoformat()
    for p in phrases:
        ph = normalize_phrase(p)
        if ph["english"] not in existing:
            vocab.append({
                "english": ph["english"],
                "japanese": ph.get("japanese", ""),
                "context": ph.get("context", ""),
                "learned_date": today,
                "review_count": 0,
                "mastered": False,
            })
    save_vocabulary(vocab)


# ---------------------------------------------------------------------------
# AI呼び出し
# ---------------------------------------------------------------------------
def get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        st.error("ANTHROPIC_API_KEY が設定されていません。`.env` ファイルを確認してください。")
        st.stop()
    return anthropic.Anthropic(api_key=api_key)


def chat(client: anthropic.Anthropic, messages: List[dict], system: str = SYSTEM_PROMPT) -> str:
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=system,
        messages=messages,
    )
    return resp.content[0].text


def generate_summary(client: anthropic.Anthropic, messages: List[dict]):
    conversation_text = "\n".join(
        f"{'ユーザー' if m['role'] == 'user' else 'AI'}: {m['content']}" for m in messages
    )
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[{"role": "user", "content": SUMMARY_PROMPT + conversation_text}],
    )
    raw = resp.content[0].text.strip()
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
# 音声機能
# ---------------------------------------------------------------------------
def render_tts(text: str, lang: str = "ja-JP"):
    """ブラウザのSpeechSynthesisでテキストを読み上げ"""
    escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ").replace('"', '\\"')
    html_code = f"""
    <div id="tts-container" style="display:none;">
        <script>
            (function() {{
                window.speechSynthesis.cancel();
                const utterance = new SpeechSynthesisUtterance('{escaped}');
                utterance.lang = '{lang}';
                utterance.rate = 1.0;
                utterance.pitch = 1.0;
                window.speechSynthesis.speak(utterance);
            }})();
        </script>
    </div>
    """
    st.components.v1.html(html_code, height=0)


# ---------------------------------------------------------------------------
# CSS / テーマ
# ---------------------------------------------------------------------------
def inject_css(dark_mode: bool = False):
    if dark_mode:
        st.markdown("""
        <style>
            :root {
                --bg-primary: #1a1a2e;
                --bg-secondary: #16213e;
                --bg-card: #1e2a47;
                --text-primary: #e0e0e0;
                --text-secondary: #a0a0b0;
                --accent: #6c63ff;
                --accent-light: #8b83ff;
                --success: #4caf50;
                --xp-bar: #ffd54f;
                --border: #2a3a5c;
                --menu-bg: #16213e;
            }
            .stApp { background-color: var(--bg-primary) !important; }
            .stMarkdown, .stText { color: var(--text-primary) !important; }
            .top-menu {
                display: flex; align-items: center; justify-content: space-between;
                padding: 8px 16px; background: var(--menu-bg);
                border-bottom: 1px solid var(--border); border-radius: 10px;
                margin-bottom: 16px;
            }
            .top-menu-left { display: flex; align-items: center; gap: 8px; }
            .top-menu-title { font-size: 20px; font-weight: bold; color: var(--accent-light); }
            .nav-pills { display: flex; gap: 4px; }
            .nav-pill {
                padding: 6px 16px; border-radius: 20px; font-size: 14px;
                color: var(--text-secondary); background: transparent; border: none; cursor: pointer;
                text-decoration: none;
            }
            .nav-pill.active {
                background: var(--accent); color: white; font-weight: bold;
            }
            .phrase-card {
                background: var(--bg-card); border-left: 4px solid var(--accent);
                border-radius: 8px; padding: 14px; margin-bottom: 10px;
            }
            .phrase-en { font-size: 16px; font-weight: bold; color: var(--accent-light); }
            .phrase-ja { font-size: 14px; color: var(--text-primary); margin-top: 4px; }
            .phrase-ctx { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
            .level-badge {
                text-align: center; padding: 16px;
                background: linear-gradient(135deg, #2a1a5e, #3a2a7e);
                border-radius: 14px; color: white; margin-bottom: 16px;
                border: 1px solid #4a3a9e;
            }
            .xp-bar-bg { background: rgba(255,255,255,0.15); border-radius: 6px; height: 12px; margin: 6px 16px; }
            .xp-bar-fill { background: var(--xp-bar); height: 100%; border-radius: 6px; transition: width 0.5s ease; }
            .stat-card {
                background: var(--bg-card); border-radius: 12px; padding: 16px; text-align: center;
                border: 1px solid var(--border);
            }
            .stat-number { font-size: 28px; font-weight: bold; color: var(--accent-light); }
            .stat-label { font-size: 13px; color: var(--text-secondary); margin-top: 4px; }
            .streak-badge {
                display: inline-block; background: linear-gradient(135deg, #ff6b35, #ff8c42);
                color: white; padding: 4px 12px; border-radius: 20px; font-size: 14px; font-weight: bold;
            }
            .quiz-box {
                background: var(--bg-card); border-radius: 12px; padding: 20px; margin: 16px 0;
                border: 2px solid var(--accent);
            }
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <style>
            :root {
                --bg-primary: #ffffff;
                --bg-secondary: #f8f9fa;
                --bg-card: #f0f4ff;
                --text-primary: #333333;
                --text-secondary: #666666;
                --accent: #1a237e;
                --accent-light: #3949ab;
                --success: #4caf50;
                --xp-bar: #ffd54f;
                --border: #e0e0e0;
                --menu-bg: #f0f4ff;
            }
            .top-menu {
                display: flex; align-items: center; justify-content: space-between;
                padding: 8px 16px; background: var(--menu-bg);
                border-bottom: 1px solid var(--border); border-radius: 10px;
                margin-bottom: 16px;
            }
            .top-menu-left { display: flex; align-items: center; gap: 8px; }
            .top-menu-title { font-size: 20px; font-weight: bold; color: var(--accent); }
            .nav-pills { display: flex; gap: 4px; }
            .nav-pill {
                padding: 6px 16px; border-radius: 20px; font-size: 14px;
                color: var(--text-secondary); background: transparent; border: none; cursor: pointer;
                text-decoration: none;
            }
            .nav-pill.active {
                background: var(--accent); color: white; font-weight: bold;
            }
            .phrase-card {
                background: var(--bg-card); border-left: 4px solid var(--accent);
                border-radius: 8px; padding: 14px; margin-bottom: 10px;
            }
            .phrase-en { font-size: 16px; font-weight: bold; color: var(--accent); }
            .phrase-ja { font-size: 14px; color: var(--text-primary); margin-top: 4px; }
            .phrase-ctx { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
            .level-badge {
                text-align: center; padding: 16px;
                background: linear-gradient(135deg, #1a237e, #283593);
                border-radius: 14px; color: white; margin-bottom: 16px;
            }
            .xp-bar-bg { background: rgba(255,255,255,0.3); border-radius: 6px; height: 12px; margin: 6px 16px; }
            .xp-bar-fill { background: var(--xp-bar); height: 100%; border-radius: 6px; transition: width 0.5s ease; }
            .stat-card {
                background: var(--bg-card); border-radius: 12px; padding: 16px; text-align: center;
                border: 1px solid var(--border);
            }
            .stat-number { font-size: 28px; font-weight: bold; color: var(--accent); }
            .stat-label { font-size: 13px; color: var(--text-secondary); margin-top: 4px; }
            .streak-badge {
                display: inline-block; background: linear-gradient(135deg, #ff6b35, #ff8c42);
                color: white; padding: 4px 12px; border-radius: 20px; font-size: 14px; font-weight: bold;
            }
            .quiz-box {
                background: #fff8e1; border-radius: 12px; padding: 20px; margin: 16px 0;
                border: 2px solid #ffd54f;
            }
        </style>
        """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# UI コンポーネント
# ---------------------------------------------------------------------------
def render_level_badge(profile: dict):
    level = profile["level"]
    xp = profile["xp"]
    needed = xp_for_next_level(level)
    pct = int((xp / needed) * 100) if needed > 0 else 0
    streak = profile.get("streak_days", 0)
    total_phrases = profile.get("total_phrases", 0)

    streak_html = f'<span class="streak-badge">{streak}日連続</span>' if streak > 0 else ''

    st.markdown(f"""
    <div class="level-badge">
        <div style="font-size:32px;font-weight:bold;">Lv. {level}</div>
        <div style="font-size:13px;margin:6px 0;">XP: {xp} / {needed}</div>
        <div class="xp-bar-bg">
            <div class="xp-bar-fill" style="width:{pct}%;"></div>
        </div>
        <div style="margin-top:10px;">
            {streak_html}
        </div>
        <div style="font-size:12px;margin-top:8px;opacity:0.8;">
            習得フレーズ: {total_phrases}個
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_phrase_card(phrase: dict, index: int = 0):
    p = normalize_phrase(phrase)
    st.markdown(f"""
    <div class="phrase-card">
        <div class="phrase-en">{index}. {p['english']}</div>
        <div class="phrase-ja">{p.get('japanese', '')}</div>
        <div class="phrase-ctx">{p.get('context', '')}</div>
    </div>
    """, unsafe_allow_html=True)


def render_stats_dashboard(profile: dict):
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{profile.get('total_entries', 0)}</div>
            <div class="stat-label">振り返り回数</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{profile.get('total_phrases', 0)}</div>
            <div class="stat-label">習得フレーズ</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        streak = profile.get("streak_days", 0)
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{streak}</div>
            <div class="stat-label">連続学習日数</div>
        </div>
        """, unsafe_allow_html=True)


def render_menu_bar(profile: dict):
    """トップメニューバーを描画"""
    page = st.session_state.current_page
    pages = {
        "reflection": "振り返り",
        "voice": "音声会話",
        "vocabulary": "単語帳",
        "quiz_dojo": "クイズ道場",
    }

    col_nav, col_info, col_dark = st.columns([6, 2, 2])

    with col_nav:
        cols = st.columns(len(pages) + 1)
        with cols[0]:
            st.markdown("**English Diary**")
        for i, (key, label) in enumerate(pages.items(), 1):
            with cols[i]:
                btn_type = "primary" if page == key else "secondary"
                if st.button(label, key=f"menu_{key}", type=btn_type, use_container_width=True):
                    st.session_state.current_page = key
                    st.rerun()

    with col_info:
        level = profile["level"]
        xp = profile["xp"]
        needed = xp_for_next_level(level)
        streak = profile.get("streak_days", 0)
        streak_text = f" | {streak}日連続" if streak > 0 else ""
        st.markdown(f"**Lv.{level}** ({xp}/{needed} XP){streak_text}")

    with col_dark:
        dark_mode = st.toggle("Dark Mode", value=st.session_state.dark_mode, key="dark_toggle")
        if dark_mode != st.session_state.dark_mode:
            st.session_state.dark_mode = dark_mode
            st.rerun()


# ---------------------------------------------------------------------------
# ページ: 振り返り（テキスト）
# ---------------------------------------------------------------------------
def render_reflection_page(client: anthropic.Anthropic, profile: dict):
    st.header("Today's Reflection")
    st.caption("今日の出来事を振り返りながら英語フレーズを学ぼう")

    # チャットフェーズ
    if st.session_state.phase == "chat":
        if not st.session_state.messages:
            greeting = "Hi! 今日はどんな1日でしたか？印象に残ったことを教えてください。"
            st.session_state.messages.append({"role": "assistant", "content": greeting})

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        remaining = MAX_TURNS - st.session_state.turn_count
        if remaining > 0:
            st.caption(f"あと {remaining} 回の会話でまとめに入ります")

        if user_input := st.chat_input("今日のことを話してください..."):
            st.session_state.messages.append({"role": "user", "content": user_input})
            st.session_state.turn_count += 1

            if st.session_state.turn_count >= MAX_TURNS:
                st.session_state.phase = "summarizing"
                st.rerun()
            else:
                ai_messages = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
                reply = chat(client, ai_messages)
                st.session_state.messages.append({"role": "assistant", "content": reply})
                st.rerun()

    # まとめ生成中
    elif st.session_state.phase == "summarizing":
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        with st.spinner("振り返りをまとめています..."):
            summary = generate_summary(client, st.session_state.messages)
            if summary:
                st.session_state.summary_data = summary
                st.session_state.phase = "summary"

                xp = summary.get("xp_gained", 20)
                add_xp(profile, xp)
                profile["total_entries"] += 1
                phrases = summary.get("english_phrases", [])
                profile["total_phrases"] = profile.get("total_phrases", 0) + len(phrases)
                update_streak(profile)
                save_profile(profile)

                add_phrases_to_vocabulary(phrases)
                save_diary(summary)
                st.rerun()
            else:
                st.session_state.phase = "chat"
                st.rerun()

    # まとめ表示
    elif st.session_state.phase == "summary":
        summary = st.session_state.summary_data
        st.success("Great job! 振り返りが完了しました！")

        xp = summary.get("xp_gained", 0)
        st.markdown(f"""
        <div style="text-align:center;margin:16px 0;">
            <div style="font-size:24px;font-weight:bold;color:var(--accent);">+{xp} XP</div>
            <div style="font-size:14px;color:var(--text-secondary);">経験値を獲得しました</div>
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Today's Summary")
            st.write(summary.get("summary", ""))

            st.subheader("Key Learnings")
            for learning in summary.get("key_learnings", []):
                st.markdown(f"- {learning}")

        with col2:
            st.subheader("English Phrases")
            for i, phrase in enumerate(summary.get("english_phrases", []), 1):
                render_phrase_card(phrase, i)

        st.divider()

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("クイズに挑戦する", use_container_width=True):
                st.session_state.phase = "quiz"
                st.rerun()
        with col_b:
            if st.button("新しい振り返りを始める", use_container_width=True, key="new_from_summary"):
                reset_chat_state()
                st.rerun()

    # クイズフェーズ（振り返り後）
    elif st.session_state.phase == "quiz":
        render_inline_quiz(client)


def render_inline_quiz(client: anthropic.Anthropic):
    """振り返り後のインラインクイズ"""
    st.subheader("English Phrase Quiz")

    summary = st.session_state.summary_data
    phrases = summary.get("english_phrases", [])

    if not phrases:
        st.warning("フレーズが見つかりませんでした。")
        st.session_state.phase = "summary"
        st.rerun()

    if st.session_state.quiz_data is None:
        with st.spinner("クイズを作成中..."):
            p = normalize_phrase(phrases[0])
            quiz = generate_quiz(client, p["english"], p.get("japanese", ""))
            if quiz:
                st.session_state.quiz_data = quiz
                st.rerun()
            else:
                st.error("クイズの生成に失敗しました。")
                st.session_state.phase = "summary"
                st.rerun()

    quiz = st.session_state.quiz_data

    st.markdown(f"""
    <div class="quiz-box">
        <div style="font-size:18px;font-weight:bold;margin-bottom:12px;">穴埋め問題</div>
        <div style="font-size:16px;line-height:1.8;">{quiz.get('question', '')}</div>
        <div style="font-size:13px;opacity:0.7;margin-top:8px;">Hint: {quiz.get('hint', '')}</div>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.quiz_answered:
        answer = st.text_input("答えを入力:", key="quiz_answer_input")
        if st.button("回答する", use_container_width=True):
            correct = quiz.get("answer", "")
            if answer.strip().lower() == correct.strip().lower():
                st.balloons()
                st.success(f"Correct! 答え: **{correct}**")
                profile = load_profile()
                add_xp(profile, 10)
                save_profile(profile)
                st.info("Bonus +10 XP!")
            else:
                st.error(f"正解は **{correct}** でした。")
                if quiz.get("explanation"):
                    st.info(f"解説: {quiz['explanation']}")
            st.session_state.quiz_answered = True
            st.rerun()
    else:
        correct = quiz.get("answer", "")
        st.info(f"正解: **{correct}**")
        if quiz.get("explanation"):
            st.caption(f"解説: {quiz['explanation']}")
        if st.button("新しい振り返りを始める", key="new_from_quiz", use_container_width=True):
            reset_chat_state()
            st.rerun()


# ---------------------------------------------------------------------------
# ページ: 音声会話
# ---------------------------------------------------------------------------
def render_voice_page(client: anthropic.Anthropic, profile: dict):
    st.header("Voice Conversation")
    st.caption("AIと英語学習の会話をしよう（テキスト入力も可能）")

    # 音声会話用セッション状態
    if "voice_messages" not in st.session_state:
        st.session_state.voice_messages = []
    if "voice_last_reply" not in st.session_state:
        st.session_state.voice_last_reply = None
    if "voice_auto_speak" not in st.session_state:
        st.session_state.voice_auto_speak = True

    # 挨拶
    if not st.session_state.voice_messages:
        greeting = "Hi! 今日はどんなことがありましたか？英語で表現してみましょう！"
        st.session_state.voice_messages.append({"role": "assistant", "content": greeting})

    # 会話履歴表示
    for msg in st.session_state.voice_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 最後のAI返答を読み上げ
    if st.session_state.get("voice_last_reply") and st.session_state.voice_auto_speak:
        reply = st.session_state.voice_last_reply
        render_tts(reply)
        st.session_state.voice_last_reply = None

    # テキスト入力（メイン入力方法）
    if user_input := st.chat_input("メッセージを入力...（音声は下のマイクボタン）"):
        st.session_state.voice_messages.append({"role": "user", "content": user_input})

        with st.spinner("考え中..."):
            ai_messages = [{"role": m["role"], "content": m["content"]} for m in st.session_state.voice_messages]
            reply = chat(client, ai_messages, system=VOICE_SYSTEM_PROMPT)

        st.session_state.voice_messages.append({"role": "assistant", "content": reply})
        st.session_state.voice_last_reply = reply
        st.rerun()

    # コントロール
    st.markdown("---")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.session_state.voice_auto_speak = st.checkbox(
            "AI返答を読み上げ", value=st.session_state.voice_auto_speak
        )
    with col2:
        if st.button("会話をリセット", use_container_width=True):
            st.session_state.voice_messages = []
            st.session_state.voice_last_reply = None
            st.rerun()
    with col3:
        if len(st.session_state.voice_messages) >= 4:
            if st.button("まとめを生成", use_container_width=True):
                with st.spinner("まとめ生成中..."):
                    summary = generate_summary(client, st.session_state.voice_messages)
                    if summary:
                        xp = summary.get("xp_gained", 20)
                        add_xp(profile, xp)
                        profile["total_entries"] += 1
                        phrases = summary.get("english_phrases", [])
                        profile["total_phrases"] = profile.get("total_phrases", 0) + len(phrases)
                        update_streak(profile)
                        save_profile(profile)
                        add_phrases_to_vocabulary(phrases)
                        save_diary(summary)

                        st.success(f"まとめ完了！ +{xp} XP")
                        st.subheader("学んだフレーズ")
                        for i, p in enumerate(phrases, 1):
                            render_phrase_card(p, i)
                        st.session_state.voice_messages = []


# ---------------------------------------------------------------------------
# ページ: 単語帳
# ---------------------------------------------------------------------------
def render_vocabulary_page(profile: dict):
    st.header("Vocabulary Notebook")
    st.caption("学んだ英語フレーズを復習しよう")

    vocab = load_vocabulary()

    if not vocab:
        st.info("まだフレーズがありません。振り返りや音声会話で英語フレーズを学びましょう！")
        return

    # フィルター
    filter_option = st.radio(
        "表示",
        ["すべて", "未習得", "習得済み"],
        horizontal=True,
    )

    if filter_option == "未習得":
        filtered = [v for v in vocab if not v.get("mastered")]
    elif filter_option == "習得済み":
        filtered = [v for v in vocab if v.get("mastered")]
    else:
        filtered = vocab

    st.markdown(f"**{len(filtered)}** フレーズ")

    for i, phrase in enumerate(filtered):
        col1, col2 = st.columns([5, 1])
        with col1:
            mastered_mark = " (習得済)" if phrase.get("mastered") else ""
            st.markdown(f"""
            <div class="phrase-card">
                <div class="phrase-en">{phrase.get('english', '')}{mastered_mark}</div>
                <div class="phrase-ja">{phrase.get('japanese', '')}</div>
                <div class="phrase-ctx">{phrase.get('context', '')}</div>
                <div style="font-size:11px;color:var(--text-secondary);margin-top:6px;">
                    学習日: {phrase.get('learned_date', '不明')} | 復習回数: {phrase.get('review_count', 0)}
                </div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            if not phrase.get("mastered"):
                if st.button("Done", key=f"master_{i}", help="習得済みにする"):
                    idx = vocab.index(phrase)
                    vocab[idx]["mastered"] = True
                    vocab[idx]["review_count"] = vocab[idx].get("review_count", 0) + 1
                    save_vocabulary(vocab)
                    add_xp(profile, 5)
                    save_profile(profile)
                    st.rerun()
            else:
                if st.button("Undo", key=f"unmaster_{i}", help="未習得に戻す"):
                    idx = vocab.index(phrase)
                    vocab[idx]["mastered"] = False
                    save_vocabulary(vocab)
                    st.rerun()


# ---------------------------------------------------------------------------
# ページ: クイズ道場
# ---------------------------------------------------------------------------
def render_quiz_dojo_page(client: anthropic.Anthropic, profile: dict):
    st.header("Quiz Dojo")
    st.caption("単語帳のフレーズからクイズに挑戦してXPを獲得しよう")

    vocab = load_vocabulary()
    unmastered = [v for v in vocab if not v.get("mastered")]

    if not vocab:
        st.info("まだフレーズがありません。振り返りで英語フレーズを学んでからクイズに挑戦しましょう！")
        return

    target_vocab = unmastered if unmastered else vocab

    # クイズ状態管理
    if "dojo_quiz" not in st.session_state:
        st.session_state.dojo_quiz = None
    if "dojo_answered" not in st.session_state:
        st.session_state.dojo_answered = False
    if "dojo_score" not in st.session_state:
        st.session_state.dojo_score = 0
    if "dojo_count" not in st.session_state:
        st.session_state.dojo_count = 0

    # スコア表示
    if st.session_state.dojo_count > 0:
        st.markdown(f"""
        <div style="text-align:center;margin-bottom:16px;">
            <span style="font-size:20px;font-weight:bold;">
                Score: {st.session_state.dojo_score} / {st.session_state.dojo_count}
            </span>
        </div>
        """, unsafe_allow_html=True)

    # クイズ生成
    if st.session_state.dojo_quiz is None:
        if st.button("クイズを出題する", use_container_width=True, type="primary"):
            import random
            phrase = random.choice(target_vocab)
            with st.spinner("クイズ作成中..."):
                quiz = generate_quiz(client, phrase["english"], phrase.get("japanese", ""))
                if quiz:
                    quiz["_phrase"] = phrase
                    st.session_state.dojo_quiz = quiz
                    st.session_state.dojo_answered = False
                    st.rerun()
                else:
                    st.error("クイズの生成に失敗しました。もう一度試してください。")
        return

    quiz = st.session_state.dojo_quiz

    st.markdown(f"""
    <div class="quiz-box">
        <div style="font-size:18px;font-weight:bold;margin-bottom:12px;">穴埋め問題</div>
        <div style="font-size:16px;line-height:1.8;">{quiz.get('question', '')}</div>
        <div style="font-size:13px;opacity:0.7;margin-top:8px;">Hint: {quiz.get('hint', '')}</div>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.dojo_answered:
        answer = st.text_input("答えを入力:", key="dojo_answer_input")
        if st.button("回答する", use_container_width=True, type="primary"):
            correct = quiz.get("answer", "")
            st.session_state.dojo_count += 1
            if answer.strip().lower() == correct.strip().lower():
                st.balloons()
                st.success(f"Correct! 答え: **{correct}**")
                st.session_state.dojo_score += 1
                add_xp(profile, 15)
                save_profile(profile)
                st.info("+15 XP!")

                # 復習回数を更新
                phrase_data = quiz.get("_phrase")
                if phrase_data:
                    all_vocab = load_vocabulary()
                    for v in all_vocab:
                        if v["english"] == phrase_data.get("english", ""):
                            v["review_count"] = v.get("review_count", 0) + 1
                            break
                    save_vocabulary(all_vocab)
            else:
                st.error(f"正解は **{correct}** でした。")
            if quiz.get("explanation"):
                st.info(f"解説: {quiz['explanation']}")
            st.session_state.dojo_answered = True
            st.rerun()
    else:
        correct = quiz.get("answer", "")
        st.info(f"正解: **{correct}**")
        if quiz.get("explanation"):
            st.caption(f"解説: {quiz['explanation']}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("次の問題へ", use_container_width=True, type="primary"):
                st.session_state.dojo_quiz = None
                st.session_state.dojo_answered = False
                st.rerun()
        with col2:
            if st.button("道場を終了", use_container_width=True):
                score = st.session_state.dojo_score
                count = st.session_state.dojo_count
                st.session_state.dojo_quiz = None
                st.session_state.dojo_answered = False
                st.session_state.dojo_score = 0
                st.session_state.dojo_count = 0
                if count > 0:
                    st.success(f"お疲れさま！ 結果: {score}/{count} 問正解")
                st.rerun()


# ---------------------------------------------------------------------------
# ページ: 過去の記録
# ---------------------------------------------------------------------------
def render_history_sidebar():
    """サイドバーに過去の記録を表示"""
    with st.sidebar:
        st.subheader("過去の記録")
        diaries = load_all_diaries()
        if not diaries:
            st.caption("まだ記録がありません")
        for date_str, entries in diaries[:5]:
            with st.expander(f"{date_str} ({len(entries)}件)"):
                for i, entry in enumerate(entries):
                    if isinstance(entry, dict):
                        st.markdown(f"**{i+1}.** {entry.get('summary', '（要約なし）')}")
                    else:
                        st.markdown(f"**{i+1}.** {entry}")


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------
def reset_chat_state():
    st.session_state.messages = []
    st.session_state.turn_count = 0
    st.session_state.phase = "chat"
    st.session_state.summary_data = None
    st.session_state.quiz_data = None
    st.session_state.quiz_answered = False


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="English Learning Diary", page_icon="📘", layout="wide")
    ensure_dirs()

    # セッション初期化
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "turn_count" not in st.session_state:
        st.session_state.turn_count = 0
    if "phase" not in st.session_state:
        st.session_state.phase = "chat"
    if "summary_data" not in st.session_state:
        st.session_state.summary_data = None
    if "quiz_data" not in st.session_state:
        st.session_state.quiz_data = None
    if "quiz_answered" not in st.session_state:
        st.session_state.quiz_answered = False
    if "current_page" not in st.session_state:
        st.session_state.current_page = "reflection"
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = False

    # ダークモード適用
    inject_css(st.session_state.dark_mode)

    profile = load_profile()

    # --- トップメニューバー ---
    render_menu_bar(profile)

    # --- サイドバー（過去の記録のみ） ---
    render_history_sidebar()

    # --- メインエリア ---
    client = get_client()
    page = st.session_state.current_page

    if page == "reflection":
        render_stats_dashboard(profile)
        render_reflection_page(client, profile)
    elif page == "voice":
        render_voice_page(client, profile)
    elif page == "vocabulary":
        render_vocabulary_page(profile)
    elif page == "quiz_dojo":
        render_quiz_dojo_page(client, profile)


if __name__ == "__main__":
    main()
