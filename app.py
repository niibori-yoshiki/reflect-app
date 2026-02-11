"""
English Learning Diary - AI対話型英語学習アプリ
音声会話・クイズ道場・単語帳で英語力をレベルアップ
"""

import json
import os
import datetime
import io
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


def load_all_diaries() -> list[tuple[str, list[dict]]]:
    results = []
    if not DIARY_DIR.exists():
        return results
    for f in sorted(DIARY_DIR.glob("*.json"), reverse=True):
        entries = json.loads(f.read_text(encoding="utf-8"))
        results.append((f.stem, entries))
    return results


def load_vocabulary() -> list[dict]:
    if VOCAB_PATH.exists():
        return json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    return []


def save_vocabulary(vocab: list[dict]):
    VOCAB_PATH.write_text(json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8")


def add_phrases_to_vocabulary(phrases: list[dict]):
    vocab = load_vocabulary()
    existing = {p["english"] for p in vocab}
    today = datetime.date.today().isoformat()
    for p in phrases:
        if p["english"] not in existing:
            vocab.append({
                "english": p["english"],
                "japanese": p["japanese"],
                "context": p.get("context", ""),
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


def chat(client: anthropic.Anthropic, messages: list[dict], system: str = SYSTEM_PROMPT) -> str:
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=system,
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
def transcribe_audio(audio_bytes: bytes) -> str | None:
    """音声データをテキストに変換（speech_recognition使用）"""
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        audio_file = sr.AudioFile(io.BytesIO(audio_bytes))
        with audio_file as source:
            audio_data = recognizer.record(source)
        text = recognizer.recognize_google(audio_data, language="ja-JP")
        return text
    except ImportError:
        st.error("音声認識には `SpeechRecognition` パッケージが必要です。`pip install SpeechRecognition` を実行してください。")
        return None
    except Exception as e:
        st.error(f"音声認識エラー: {e}")
        return None


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
            }
            .stApp { background-color: var(--bg-primary) !important; }
            .stSidebar > div { background-color: var(--bg-secondary) !important; }
            .stMarkdown, .stText { color: var(--text-primary) !important; }
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
            .voice-btn {
                width: 80px; height: 80px; border-radius: 50%; border: none;
                background: linear-gradient(135deg, var(--accent), var(--accent-light));
                color: white; font-size: 32px; cursor: pointer; margin: 20px auto; display: block;
                box-shadow: 0 4px 20px rgba(108,99,255,0.4);
                transition: transform 0.2s, box-shadow 0.2s;
            }
            .voice-btn:hover { transform: scale(1.1); box-shadow: 0 6px 30px rgba(108,99,255,0.6); }
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
            .voice-btn {
                width: 80px; height: 80px; border-radius: 50%; border: none;
                background: linear-gradient(135deg, #1a237e, #3949ab);
                color: white; font-size: 32px; cursor: pointer; margin: 20px auto; display: block;
                box-shadow: 0 4px 20px rgba(26,35,126,0.3);
                transition: transform 0.2s, box-shadow 0.2s;
            }
            .voice-btn:hover { transform: scale(1.1); box-shadow: 0 6px 30px rgba(26,35,126,0.5); }
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

    streak_html = f'<div class="streak-badge">{streak}日連続</div>' if streak > 0 else ''

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
    st.markdown(f"""
    <div class="phrase-card">
        <div class="phrase-en">{index}. {phrase['english']}</div>
        <div class="phrase-ja">{phrase['japanese']}</div>
        <div class="phrase-ctx">{phrase.get('context', '')}</div>
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


# ---------------------------------------------------------------------------
# ページ: 振り返り（テキスト）
# ---------------------------------------------------------------------------
def render_reflection_page(client: anthropic.Anthropic, profile: dict):
    st.title("Today's Reflection")
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
            if st.button("📝 クイズに挑戦する", use_container_width=True):
                st.session_state.phase = "quiz"
                st.rerun()
        with col_b:
            if st.button("🔄 新しい振り返りを始める", use_container_width=True, key="new_from_summary"):
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
        if st.button("🔄 新しい振り返りを始める", key="new_from_quiz", use_container_width=True):
            reset_chat_state()
            st.rerun()


# ---------------------------------------------------------------------------
# ページ: 音声会話
# ---------------------------------------------------------------------------
def render_voice_page(client: anthropic.Anthropic, profile: dict):
    st.title("Voice Conversation")
    st.caption("マイクで話して、AIと英語学習の会話をしよう")

    # 音声会話用セッション状態
    if "voice_messages" not in st.session_state:
        st.session_state.voice_messages = []
    if "voice_speaking" not in st.session_state:
        st.session_state.voice_speaking = False

    # 会話履歴表示
    for msg in st.session_state.voice_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 音声入力
    st.markdown("---")
    st.markdown("**🎤 マイクボタンを押して話してください**")

    audio_data = st.audio_input("音声を録音", key="voice_audio_input", label_visibility="collapsed")

    if audio_data is not None:
        audio_key = f"processed_{hash(audio_data.getvalue())}"
        if audio_key not in st.session_state:
            st.session_state[audio_key] = True

            with st.spinner("音声を認識中..."):
                text = transcribe_audio(audio_data.getvalue())

            if text:
                st.session_state.voice_messages.append({"role": "user", "content": text})

                with st.spinner("考え中..."):
                    ai_messages = [{"role": m["role"], "content": m["content"]} for m in st.session_state.voice_messages]
                    reply = chat(client, ai_messages, system=VOICE_SYSTEM_PROMPT)

                st.session_state.voice_messages.append({"role": "assistant", "content": reply})
                st.session_state.voice_last_reply = reply
                st.rerun()

    # 最後のAI返答を読み上げ
    if st.session_state.get("voice_last_reply"):
        reply = st.session_state.voice_last_reply
        render_tts(reply)
        st.session_state.voice_last_reply = None

    # コントロール
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 会話をリセット", use_container_width=True):
            st.session_state.voice_messages = []
            st.session_state.voice_last_reply = None
            st.rerun()
    with col2:
        if len(st.session_state.voice_messages) >= 4:
            if st.button("📝 まとめを生成", use_container_width=True):
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
    st.title("Vocabulary Notebook")
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
            mastered_mark = " ✅" if phrase.get("mastered") else ""
            st.markdown(f"""
            <div class="phrase-card">
                <div class="phrase-en">{phrase['english']}{mastered_mark}</div>
                <div class="phrase-ja">{phrase['japanese']}</div>
                <div class="phrase-ctx">{phrase.get('context', '')}</div>
                <div style="font-size:11px;color:var(--text-secondary);margin-top:6px;">
                    学習日: {phrase.get('learned_date', '不明')} | 復習回数: {phrase.get('review_count', 0)}
                </div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            if not phrase.get("mastered"):
                if st.button("✅", key=f"master_{i}", help="習得済みにする"):
                    idx = vocab.index(phrase)
                    vocab[idx]["mastered"] = True
                    vocab[idx]["review_count"] = vocab[idx].get("review_count", 0) + 1
                    save_vocabulary(vocab)
                    add_xp(profile, 5)
                    save_profile(profile)
                    st.rerun()
            else:
                if st.button("↩️", key=f"unmaster_{i}", help="未習得に戻す"):
                    idx = vocab.index(phrase)
                    vocab[idx]["mastered"] = False
                    save_vocabulary(vocab)
                    st.rerun()


# ---------------------------------------------------------------------------
# ページ: クイズ道場
# ---------------------------------------------------------------------------
def render_quiz_dojo_page(client: anthropic.Anthropic, profile: dict):
    st.title("Quiz Dojo")
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
        if st.button("🎯 クイズを出題する", use_container_width=True, type="primary"):
            import random
            phrase = random.choice(target_vocab)
            with st.spinner("クイズ作成中..."):
                quiz = generate_quiz(client, phrase["english"], phrase["japanese"])
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
                st.info("🎯 +15 XP!")

                # 復習回数を更新
                phrase_data = quiz.get("_phrase")
                if phrase_data:
                    all_vocab = load_vocabulary()
                    for v in all_vocab:
                        if v["english"] == phrase_data["english"]:
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

    # --- サイドバー ---
    with st.sidebar:
        st.title("📘 English Diary")

        # ダークモード切替
        dark_mode = st.toggle("🌙 Dark Mode", value=st.session_state.dark_mode)
        if dark_mode != st.session_state.dark_mode:
            st.session_state.dark_mode = dark_mode
            st.rerun()

        st.markdown("---")

        # レベルバッジ
        render_level_badge(profile)

        # ナビゲーション
        st.markdown("---")
        page_options = {
            "reflection": "📝 振り返り",
            "voice": "🎤 音声会話",
            "vocabulary": "📚 単語帳",
            "quiz_dojo": "🏋️ クイズ道場",
        }

        for key, label in page_options.items():
            is_active = st.session_state.current_page == key
            if st.button(
                label,
                key=f"nav_{key}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.current_page = key
                st.rerun()

        # 過去の記録
        st.markdown("---")
        st.subheader("過去の記録")
        diaries = load_all_diaries()
        if not diaries:
            st.caption("まだ記録がありません")
        for date_str, entries in diaries[:5]:
            with st.expander(f"📅 {date_str} ({len(entries)}件)"):
                for i, entry in enumerate(entries):
                    st.markdown(f"**{i+1}.** {entry.get('summary', '（要約なし）')}")

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
