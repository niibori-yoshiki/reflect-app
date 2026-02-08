"""
ビジネス日記アプリ - AI対話型ビジネス振り返りツール
音声チャット・単語帳・クイズ・文章ストック機能付き
"""

import json
import os
import datetime
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
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

SKILL_CATEGORIES = [
    "プロジェクト管理",
    "交渉",
    "プレゼンテーション",
    "リーダーシップ",
    "問題解決",
    "コミュニケーション",
]

PROFICIENCY_CONFIG = {
    "unlearned":      {"label": "未学習", "color": "#9e9e9e", "bg": "#f5f5f5"},
    "learning":       {"label": "学習中", "color": "#f44336", "bg": "#ffebee"},
    "consolidating":  {"label": "定着中", "color": "#ff9800", "bg": "#fff3e0"},
    "mastered":       {"label": "習得済み", "color": "#4caf50", "bg": "#e8f5e9"},
}

# 音声コンポーネント
VOICE_COMPONENT_DIR = Path(__file__).parent / "components" / "voice_input"
_voice_input_func = components.declare_component("voice_input", path=str(VOICE_COMPONENT_DIR))

# ---------------------------------------------------------------------------
# プロンプト
# ---------------------------------------------------------------------------
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
    }
  ],
  "sentences": [
    {
      "japanese": "ユーザーが話した内容をもとにした日本語文",
      "english": "その英語訳",
      "pattern": "固有名詞（人名・会社名・プロジェクト名など）を___に置き換えた汎用パターン"
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
- sentences: ユーザーの発言内容から2〜3文を選び、英語訳と固有名詞を除いた汎用パターンを作成してください。
  - japanese: ユーザーが実際に話した内容に基づく自然な日本語文
  - english: そのビジネスシーンで使える自然な英語訳
  - pattern: 人名・会社名・プロジェクト名など固有名詞を「___」に置き換えた汎用パターン
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

BATCH_QUIZ_PROMPT = """\
以下の英語フレーズについて、それぞれ穴埋めクイズを1問ずつ作ってください。
JSONの配列のみを返してください。マークダウンのコードブロックや説明文は不要です。

[
  {{
    "word_id": "対応する単語のID",
    "question": "穴埋め問題文（___で空欄を表示）",
    "answer": "正解の単語・フレーズ",
    "hint": "ヒント"
  }}
]

フレーズ一覧:
{phrases}
"""


# ---------------------------------------------------------------------------
# データ永続化
# ---------------------------------------------------------------------------
def ensure_dirs():
    DIARY_DIR.mkdir(parents=True, exist_ok=True)


def load_profile() -> dict:
    if PROFILE_PATH.exists():
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    return {
        "level": 1,
        "xp": 0,
        "total_entries": 0,
        "skills": {s: 0 for s in SKILL_CATEGORIES},
    }


def save_profile(profile: dict):
    PROFILE_PATH.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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
    path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_all_diaries() -> list[tuple[str, list[dict]]]:
    results = []
    if not DIARY_DIR.exists():
        return results
    for f in sorted(DIARY_DIR.glob("*.json"), reverse=True):
        entries = json.loads(f.read_text(encoding="utf-8"))
        results.append((f.stem, entries))
    return results


# ── 単語帳データ ──
def load_vocabulary() -> dict:
    if VOCAB_PATH.exists():
        return json.loads(VOCAB_PATH.read_text(encoding="utf-8"))
    return {"words": [], "sentences": []}


def save_vocabulary(vocab: dict):
    VOCAB_PATH.write_text(
        json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_words_from_summary(summary: dict):
    """サマリーから単語帳にフレーズを追加する（重複排除付き）"""
    vocab = load_vocabulary()
    existing = {w["english"].lower() for w in vocab["words"]}
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().isoformat()

    for phrase in summary.get("english_phrases", []):
        eng = phrase.get("english", "").strip()
        if not eng or eng.lower() in existing:
            continue
        vocab["words"].append({
            "id": f"w_{int(time.time() * 1000)}_{len(vocab['words'])}",
            "english": eng,
            "japanese": phrase.get("japanese", ""),
            "context": phrase.get("context", ""),
            "source_date": today,
            "added_at": now,
            "quiz_history": [],
        })
        existing.add(eng.lower())

    save_vocabulary(vocab)


def add_sentences_from_summary(summary: dict):
    """サマリーから文章ストックに追加する（重複排除付き）"""
    vocab = load_vocabulary()
    existing = {s["english"].lower() for s in vocab["sentences"]}
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().isoformat()

    for sent in summary.get("sentences", []):
        eng = sent.get("english", "").strip()
        if not eng or eng.lower() in existing:
            continue
        vocab["sentences"].append({
            "id": f"s_{int(time.time() * 1000)}_{len(vocab['sentences'])}",
            "japanese": sent.get("japanese", ""),
            "english": eng,
            "pattern": sent.get("pattern", ""),
            "source_date": today,
            "added_at": now,
        })
        existing.add(eng.lower())

    save_vocabulary(vocab)


def calculate_proficiency(word: dict) -> str:
    """クイズ履歴から習熟度を判定する"""
    history = word.get("quiz_history", [])
    if not history:
        return "unlearned"
    total = len(history)
    correct = sum(1 for h in history if h.get("correct"))
    accuracy = correct / total if total > 0 else 0
    if total < 3 or accuracy < 0.4:
        return "learning"
    elif accuracy < 0.75:
        return "consolidating"
    else:
        return "mastered"


def get_word_stats(word: dict) -> dict:
    """単語のクイズ統計を返す"""
    history = word.get("quiz_history", [])
    total = len(history)
    correct = sum(1 for h in history if h.get("correct"))
    return {
        "total": total,
        "correct": correct,
        "accuracy": (correct / total * 100) if total > 0 else 0,
    }


def record_quiz_result(word_id: str, correct: bool):
    """クイズ結果を記録する"""
    vocab = load_vocabulary()
    today = datetime.date.today().isoformat()
    for word in vocab["words"]:
        if word["id"] == word_id:
            word["quiz_history"].append({"date": today, "correct": correct})
            break
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
        f"{'ユーザー' if m['role'] == 'user' else 'AI'}: {m['content']}"
        for m in messages
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


def generate_batch_quiz(client: anthropic.Anthropic, words: list[dict]):
    """複数フレーズのクイズを一括生成する"""
    phrases_text = "\n".join(
        f"- ID: {w['id']} | English: {w['english']} | Japanese: {w['japanese']}"
        for w in words
    )
    prompt = BATCH_QUIZ_PROMPT.format(phrases=phrases_text)
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
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
def voice_input(key: str = "voice_input"):
    """音声入力コンポーネントを表示し、認識テキストを返す"""
    return _voice_input_func(key=key, default=None)


def speak_text(text: str, lang: str = "ja-JP"):
    """テキストを音声で読み上げる（ブラウザのTTS使用）"""
    escaped = json.dumps(text, ensure_ascii=False)
    html_code = f"""
    <script>
        (function() {{
            const synth = window.speechSynthesis;
            synth.cancel();
            const utter = new SpeechSynthesisUtterance({escaped});
            utter.lang = "{lang}";
            utter.rate = 0.9;
            synth.speak(utter);
        }})();
    </script>
    """
    components.html(html_code, height=0)


# ---------------------------------------------------------------------------
# UIヘルパー
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


def render_proficiency_badge(level: str):
    """習熟度バッジを返す"""
    cfg = PROFICIENCY_CONFIG.get(level, PROFICIENCY_CONFIG["unlearned"])
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;'
        f'font-size:12px;font-weight:bold;color:white;background:{cfg["color"]};">'
        f'{cfg["label"]}</span>'
    )


def render_vocab_stats():
    """単語帳の統計サマリーを表示"""
    vocab = load_vocabulary()
    words = vocab.get("words", [])
    if not words:
        return

    counts = {"unlearned": 0, "learning": 0, "consolidating": 0, "mastered": 0}
    for w in words:
        level = calculate_proficiency(w)
        counts[level] += 1

    total = len(words)
    html = f'<div style="font-size:13px;color:#666;margin-bottom:8px;">単語数: {total}</div>'
    html += '<div style="display:flex;gap:4px;height:8px;border-radius:4px;overflow:hidden;margin-bottom:8px;">'
    for key in ["mastered", "consolidating", "learning", "unlearned"]:
        if counts[key] > 0:
            pct = counts[key] / total * 100
            html += f'<div style="width:{pct}%;background:{PROFICIENCY_CONFIG[key]["color"]};"></div>'
    html += "</div>"
    html += '<div style="display:flex;flex-wrap:wrap;gap:6px;font-size:11px;">'
    for key in ["mastered", "consolidating", "learning", "unlearned"]:
        cfg = PROFICIENCY_CONFIG[key]
        html += (
            f'<span style="color:{cfg["color"]};">'
            f'● {cfg["label"]}: {counts[key]}</span>'
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# ページ: 今日の振り返り
# ---------------------------------------------------------------------------
def page_reflection():
    st.title("今日の振り返り")
    client = get_client()
    profile = load_profile()

    voice_mode = st.session_state.get("voice_mode", False)

    # ---- チャットフェーズ ----
    if st.session_state.phase == "chat":
        # 音声モードトグル
        col_v1, col_v2 = st.columns([1, 5])
        with col_v1:
            if st.button("🎤 音声モード" if not voice_mode else "⌨️ テキストモード"):
                st.session_state.voice_mode = not voice_mode
                st.rerun()

        # 初回メッセージ
        if not st.session_state.messages:
            greeting = "お疲れさまです！今日のお仕事はいかがでしたか？印象に残ったことを教えてください。"
            st.session_state.messages.append({"role": "assistant", "content": greeting})

        # 会話表示
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        remaining = MAX_TURNS - st.session_state.turn_count
        if remaining > 0:
            st.caption(f"あと {remaining} 回の会話でまとめに入ります")

        # 音声モードの場合
        if voice_mode:
            voice_result = voice_input(key="voice_chat_input")
            if voice_result and isinstance(voice_result, dict):
                ts = voice_result.get("ts", 0)
                if ts != st.session_state.get("last_voice_ts", 0):
                    st.session_state.last_voice_ts = ts
                    user_text = voice_result.get("text", "").strip()
                    if user_text:
                        _process_user_input(client, user_text)

            # 最新のAIメッセージを読み上げ
            if (st.session_state.messages
                    and st.session_state.messages[-1]["role"] == "assistant"
                    and st.session_state.get("last_spoken_idx", -1)
                    < len(st.session_state.messages) - 1):
                speak_text(st.session_state.messages[-1]["content"])
                st.session_state.last_spoken_idx = len(st.session_state.messages) - 1

        # テキストモードの場合
        else:
            if user_input := st.chat_input("今日の仕事について話してください..."):
                _process_user_input(client, user_input)

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

                # 単語帳・文章ストックに追加
                add_words_from_summary(summary)
                add_sentences_from_summary(summary)

                st.rerun()
            else:
                st.session_state.phase = "chat"
                st.rerun()

    # ---- まとめ表示フェーズ ----
    elif st.session_state.phase == "summary":
        _render_summary_phase(client, profile)

    # ---- クイズフェーズ ----
    elif st.session_state.phase == "quiz":
        _render_quiz_phase(client, profile)


def _process_user_input(client, user_input: str):
    """ユーザー入力を処理する共通ロジック"""
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.turn_count += 1

    if st.session_state.turn_count >= MAX_TURNS:
        st.session_state.phase = "summarizing"
        st.rerun()
    else:
        ai_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages
        ]
        reply = chat(client, ai_messages)
        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.rerun()


def _render_summary_phase(client, profile):
    """まとめ表示フェーズのレンダリング"""
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

        # 文章ストック表示
        sentences = summary.get("sentences", [])
        if sentences:
            st.subheader("💬 文章パターン")
            for i, sent in enumerate(sentences, 1):
                st.markdown(
                    f"""
                    <div style="background:#f3e5f5;border-radius:8px;padding:12px;margin-bottom:8px;
                                border-left:4px solid #7b1fa2;">
                        <div style="font-size:14px;color:#333;">{sent.get('japanese', '')}</div>
                        <div style="font-size:15px;font-weight:bold;color:#4a148c;margin-top:4px;">
                            {sent.get('english', '')}
                        </div>
                        <div style="font-size:13px;color:#666;margin-top:4px;font-style:italic;">
                            型: {sent.get('pattern', '')}
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
    st.info("英語フレーズと文章パターンは自動で単語帳・文章ストックに追加されました。")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("📝 クイズに挑戦する"):
            st.session_state.phase = "quiz"
            st.rerun()
    with col_b:
        if st.button("🔄 新しい振り返りを始める", key="new_from_summary"):
            _reset_session()
            st.rerun()


def _render_quiz_phase(client, profile):
    """クイズフェーズのレンダリング"""
    st.subheader("📝 ビジネス英語クイズ")

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
                # find word_id
                vocab = load_vocabulary()
                for w in vocab["words"]:
                    if w["english"].lower() == phrase["english"].lower():
                        st.session_state.quiz_word_id = w["id"]
                        break
                st.rerun()
            else:
                st.error("クイズの生成に失敗しました。")
                st.session_state.phase = "summary"
                st.rerun()

    quiz = st.session_state.quiz_data

    st.markdown(
        f"""
        <div style="background:#fff8e1;border-radius:12px;padding:20px;margin:16px 0;
                    border:2px solid #FFD54F;">
            <div style="font-size:18px;font-weight:bold;margin-bottom:12px;">
                🤔 穴埋め問題
            </div>
            <div style="font-size:16px;line-height:1.8;">
                {quiz.get('question', '')}
            </div>
            <div style="font-size:13px;color:#888;margin-top:8px;">
                💡 ヒント: {quiz.get('hint', '')}
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

    if not st.session_state.quiz_answered:
        answer = st.text_input("答えを入力してください:", key="quiz_answer_input")
        if st.button("回答する"):
            correct_answer = quiz.get("answer", "")
            is_correct = answer.strip().lower() == correct_answer.strip().lower()

            # クイズ結果記録
            word_id = st.session_state.get("quiz_word_id")
            if word_id:
                record_quiz_result(word_id, is_correct)

            if is_correct:
                st.balloons()
                st.success(f"正解！ 🎉  答え: **{correct_answer}**")
                profile = load_profile()
                add_xp(profile, 10)
                save_profile(profile)
                st.info("ボーナス +10 XP を獲得しました！")
            else:
                st.error(f"残念！ 正解は **{correct_answer}** でした。")

            st.session_state.quiz_answered = True
            st.rerun()
    else:
        correct_answer = quiz.get("answer", "")
        st.info(f"正解: **{correct_answer}**")
        if st.button("🔄 新しい振り返りを始める", key="new_from_quiz"):
            _reset_session()
            st.rerun()


# ---------------------------------------------------------------------------
# ページ: 単語帳
# ---------------------------------------------------------------------------
def page_vocabulary():
    st.title("📚 単語帳")

    vocab = load_vocabulary()
    words = vocab.get("words", [])

    if not words:
        st.info("まだ単語がありません。振り返りを行うと自動で単語が追加されます。")
        return

    # 統計サマリー
    counts = {"unlearned": 0, "learning": 0, "consolidating": 0, "mastered": 0}
    for w in words:
        counts[calculate_proficiency(w)] += 1
    total = len(words)

    # 統計表示
    cols = st.columns(4)
    for i, (key, cfg) in enumerate(PROFICIENCY_CONFIG.items()):
        with cols[i]:
            st.markdown(
                f"""
                <div style="text-align:center;padding:12px;background:{cfg['bg']};
                            border-radius:10px;border:2px solid {cfg['color']};">
                    <div style="font-size:24px;font-weight:bold;color:{cfg['color']};">{counts[key]}</div>
                    <div style="font-size:13px;color:#666;">{cfg['label']}</div>
                </div>""",
                unsafe_allow_html=True,
            )

    st.divider()

    # フィルタ
    filter_options = ["すべて"] + [PROFICIENCY_CONFIG[k]["label"] for k in PROFICIENCY_CONFIG]
    selected_filter = st.selectbox("フィルタ", filter_options)

    # フィルタリング
    label_to_key = {v["label"]: k for k, v in PROFICIENCY_CONFIG.items()}

    for word in words:
        prof = calculate_proficiency(word)
        if selected_filter != "すべて" and label_to_key.get(selected_filter) != prof:
            continue

        stats = get_word_stats(word)
        cfg = PROFICIENCY_CONFIG[prof]

        st.markdown(
            f"""
            <div style="background:white;border-radius:10px;padding:16px;margin-bottom:10px;
                        border:1px solid #e0e0e0;border-left:5px solid {cfg['color']};">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                    <div style="flex:1;">
                        <div style="font-size:17px;font-weight:bold;color:#1a237e;">
                            {word['english']}
                        </div>
                        <div style="font-size:14px;color:#333;margin-top:4px;">
                            {word['japanese']}
                        </div>
                        <div style="font-size:12px;color:#888;margin-top:4px;">
                            💬 {word.get('context', '')}
                        </div>
                    </div>
                    <div style="text-align:right;min-width:120px;">
                        {render_proficiency_badge(prof)}
                        <div style="font-size:11px;color:#888;margin-top:6px;">
                            正答率: {stats['accuracy']:.0f}% ({stats['correct']}/{stats['total']})
                        </div>
                        <div style="font-size:11px;color:#aaa;">
                            追加: {word.get('source_date', '')}
                        </div>
                    </div>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

    # 単語削除機能
    st.divider()
    with st.expander("単語を削除"):
        word_options = {f"{w['english']} - {w['japanese']}": w["id"] for w in words}
        selected = st.selectbox("削除する単語を選択", list(word_options.keys()))
        if st.button("削除する", type="primary"):
            word_id = word_options[selected]
            vocab["words"] = [w for w in vocab["words"] if w["id"] != word_id]
            save_vocabulary(vocab)
            st.success("削除しました")
            st.rerun()


# ---------------------------------------------------------------------------
# ページ: クイズ道場
# ---------------------------------------------------------------------------
def page_quiz_dojo():
    st.title("🥋 クイズ道場")

    vocab = load_vocabulary()
    words = vocab.get("words", [])

    if not words:
        st.info("まだ単語がありません。振り返りを行うと自動で単語が追加されます。")
        return

    client = get_client()

    # クイズ道場の状態管理
    if "dojo_phase" not in st.session_state:
        st.session_state.dojo_phase = "start"
    if "dojo_questions" not in st.session_state:
        st.session_state.dojo_questions = []
    if "dojo_current" not in st.session_state:
        st.session_state.dojo_current = 0
    if "dojo_results" not in st.session_state:
        st.session_state.dojo_results = []
    if "dojo_answered" not in st.session_state:
        st.session_state.dojo_answered = False

    # ── 開始画面 ──
    if st.session_state.dojo_phase == "start":
        # 統計表示
        counts = {"unlearned": 0, "learning": 0, "consolidating": 0, "mastered": 0}
        for w in words:
            counts[calculate_proficiency(w)] += 1

        cols = st.columns(4)
        for i, (key, cfg) in enumerate(PROFICIENCY_CONFIG.items()):
            with cols[i]:
                st.metric(cfg["label"], counts[key])

        st.divider()

        # クイズ設定
        quiz_count = st.slider("出題数", min_value=1, max_value=min(10, len(words)), value=min(5, len(words)))

        mode = st.radio(
            "出題モード",
            ["苦手優先（習熟度が低い順）", "ランダム", "未学習のみ", "学習中のみ"],
            horizontal=True,
        )

        if st.button("クイズを始める", type="primary"):
            # 出題する単語を選定
            selected_words = _select_quiz_words(words, mode, quiz_count)
            if not selected_words:
                st.warning("該当する単語がありません。")
                return

            st.session_state.dojo_selected_words = selected_words
            st.session_state.dojo_phase = "generating"
            st.session_state.dojo_current = 0
            st.session_state.dojo_results = []
            st.session_state.dojo_answered = False
            st.rerun()

    # ── クイズ生成中 ──
    elif st.session_state.dojo_phase == "generating":
        with st.spinner("クイズを生成中..."):
            selected_words = st.session_state.dojo_selected_words
            questions = generate_batch_quiz(client, selected_words)
            if questions:
                st.session_state.dojo_questions = questions
                st.session_state.dojo_phase = "answering"
                st.rerun()
            else:
                st.error("クイズの生成に失敗しました。")
                st.session_state.dojo_phase = "start"
                st.rerun()

    # ── 回答中 ──
    elif st.session_state.dojo_phase == "answering":
        questions = st.session_state.dojo_questions
        current = st.session_state.dojo_current

        if current >= len(questions):
            st.session_state.dojo_phase = "results"
            st.rerun()
            return

        q = questions[current]
        total = len(questions)

        # プログレス
        st.progress((current) / total, text=f"問題 {current + 1} / {total}")

        st.markdown(
            f"""
            <div style="background:#fff8e1;border-radius:12px;padding:24px;margin:16px 0;
                        border:2px solid #FFD54F;">
                <div style="font-size:18px;font-weight:bold;margin-bottom:16px;">
                    🤔 問題 {current + 1}
                </div>
                <div style="font-size:16px;line-height:1.8;margin-bottom:12px;">
                    {q.get('question', '')}
                </div>
                <div style="font-size:13px;color:#888;">
                    💡 ヒント: {q.get('hint', '')}
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

        if not st.session_state.dojo_answered:
            answer = st.text_input("答えを入力:", key=f"dojo_answer_{current}")
            if st.button("回答する", key=f"dojo_submit_{current}"):
                correct_answer = q.get("answer", "")
                is_correct = answer.strip().lower() == correct_answer.strip().lower()
                word_id = q.get("word_id", "")

                if word_id:
                    record_quiz_result(word_id, is_correct)

                st.session_state.dojo_results.append({
                    "question": q.get("question", ""),
                    "user_answer": answer.strip(),
                    "correct_answer": correct_answer,
                    "is_correct": is_correct,
                    "word_id": word_id,
                })

                if is_correct:
                    st.success(f"正解！ 🎉  答え: **{correct_answer}**")
                else:
                    st.error(f"残念！ 正解は **{correct_answer}** でした。")

                st.session_state.dojo_answered = True
                st.rerun()
        else:
            # 回答済み表示
            result = st.session_state.dojo_results[-1]
            if result["is_correct"]:
                st.success(f"正解！ 答え: **{result['correct_answer']}**")
            else:
                st.error(
                    f"不正解 — あなたの回答: **{result['user_answer']}** → "
                    f"正解: **{result['correct_answer']}**"
                )

            if st.button("次の問題へ →", key=f"dojo_next_{current}"):
                st.session_state.dojo_current += 1
                st.session_state.dojo_answered = False
                st.rerun()

    # ── 結果画面 ──
    elif st.session_state.dojo_phase == "results":
        results = st.session_state.dojo_results
        total = len(results)
        correct = sum(1 for r in results if r["is_correct"])
        accuracy = (correct / total * 100) if total > 0 else 0

        # XP付与
        xp_earned = correct * 5
        if xp_earned > 0:
            profile = load_profile()
            add_xp(profile, xp_earned)
            save_profile(profile)

        st.markdown(
            f"""
            <div style="text-align:center;padding:30px;background:linear-gradient(135deg,#e8eaf6,#c5cae9);
                        border-radius:16px;margin-bottom:20px;">
                <div style="font-size:48px;margin-bottom:8px;">
                    {"🎉" if accuracy >= 80 else "💪" if accuracy >= 50 else "📖"}
                </div>
                <div style="font-size:28px;font-weight:bold;color:#1a237e;">
                    {correct} / {total} 正解
                </div>
                <div style="font-size:20px;color:#333;margin-top:4px;">
                    正答率: {accuracy:.0f}%
                </div>
                <div style="font-size:16px;color:#666;margin-top:8px;">
                    +{xp_earned} XP 獲得！
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

        # 詳細結果
        st.subheader("📋 詳細結果")
        for i, r in enumerate(results, 1):
            icon = "✅" if r["is_correct"] else "❌"
            st.markdown(
                f"""
                <div style="padding:10px 14px;margin-bottom:6px;border-radius:8px;
                            background:{'#e8f5e9' if r['is_correct'] else '#ffebee'};
                            border-left:4px solid {'#4caf50' if r['is_correct'] else '#f44336'};">
                    <div style="font-size:14px;">
                        {icon} <strong>Q{i}.</strong> {r['question']}
                    </div>
                    <div style="font-size:13px;color:#555;margin-top:2px;">
                        正解: <strong>{r['correct_answer']}</strong>
                        {f" — あなたの回答: {r['user_answer']}" if not r['is_correct'] else ""}
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )

        # 習熟度変化
        st.subheader("📊 習熟度の更新")
        vocab = load_vocabulary()
        for r in results:
            word_id = r.get("word_id", "")
            for w in vocab["words"]:
                if w["id"] == word_id:
                    prof = calculate_proficiency(w)
                    cfg = PROFICIENCY_CONFIG[prof]
                    st.markdown(
                        f"- **{w['english']}**: {render_proficiency_badge(prof)}",
                        unsafe_allow_html=True,
                    )
                    break

        st.divider()
        if st.button("もう一度挑戦する", type="primary"):
            st.session_state.dojo_phase = "start"
            st.session_state.dojo_questions = []
            st.session_state.dojo_current = 0
            st.session_state.dojo_results = []
            st.session_state.dojo_answered = False
            st.rerun()


def _select_quiz_words(words: list, mode: str, count: int) -> list:
    """クイズに出題する単語を選定する"""
    import random

    if "未学習のみ" in mode:
        filtered = [w for w in words if calculate_proficiency(w) == "unlearned"]
    elif "学習中のみ" in mode:
        filtered = [w for w in words if calculate_proficiency(w) == "learning"]
    elif "苦手優先" in mode:
        # 習熟度順にソート（低い方が先）
        order = {"unlearned": 0, "learning": 1, "consolidating": 2, "mastered": 3}
        filtered = sorted(words, key=lambda w: order.get(calculate_proficiency(w), 0))
    else:
        filtered = list(words)
        random.shuffle(filtered)

    return filtered[:count]


# ---------------------------------------------------------------------------
# ページ: 文章ストック
# ---------------------------------------------------------------------------
def page_sentence_stock():
    st.title("💬 文章ストック")

    vocab = load_vocabulary()
    sentences = vocab.get("sentences", [])

    if not sentences:
        st.info("まだ文章がストックされていません。振り返りを行うと自動で追加されます。")
        return

    # 表示モード切替
    view_mode = st.radio("表示モード", ["一覧表示", "パターン一覧"], horizontal=True)

    if view_mode == "一覧表示":
        for sent in reversed(sentences):
            st.markdown(
                f"""
                <div style="background:white;border-radius:10px;padding:16px;margin-bottom:10px;
                            border:1px solid #e0e0e0;border-left:5px solid #7b1fa2;">
                    <div style="font-size:14px;color:#333;">
                        🇯🇵 {sent.get('japanese', '')}
                    </div>
                    <div style="font-size:16px;font-weight:bold;color:#4a148c;margin-top:6px;">
                        🇺🇸 {sent.get('english', '')}
                    </div>
                    <div style="font-size:14px;color:#1a237e;margin-top:6px;
                                padding:6px 10px;background:#e8eaf6;border-radius:6px;
                                font-family:monospace;">
                        🔧 {sent.get('pattern', '')}
                    </div>
                    <div style="font-size:11px;color:#aaa;margin-top:6px;">
                        追加日: {sent.get('source_date', '')}
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )

    else:
        # パターン一覧: 固有名詞を除いたパターンだけを一覧表示
        st.markdown(
            """
            <div style="background:#f3e5f5;border-radius:10px;padding:16px;margin-bottom:16px;">
                <div style="font-size:14px;color:#666;">
                    固有名詞を「___」に置き換えた、あなたの使える英語の型一覧です。
                    さまざまな場面で応用できます。
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

        for i, sent in enumerate(reversed(sentences), 1):
            pattern = sent.get("pattern", "")
            if not pattern:
                continue
            st.markdown(
                f"""
                <div style="padding:12px 16px;margin-bottom:6px;border-radius:8px;
                            background:#fce4ec;border-left:4px solid #e91e63;">
                    <div style="font-size:15px;font-weight:bold;color:#880e4f;
                                font-family:monospace;">
                        {i}. {pattern}
                    </div>
                    <div style="font-size:12px;color:#666;margin-top:4px;">
                        元の文: {sent.get('english', '')}
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )

    # 文章削除機能
    st.divider()
    with st.expander("文章を削除"):
        sent_options = {
            f"{s['english'][:50]}..." if len(s['english']) > 50 else s['english']: s["id"]
            for s in sentences
        }
        if sent_options:
            selected = st.selectbox("削除する文章を選択", list(sent_options.keys()))
            if st.button("削除する", type="primary", key="delete_sentence"):
                sent_id = sent_options[selected]
                vocab["sentences"] = [s for s in vocab["sentences"] if s["id"] != sent_id]
                save_vocabulary(vocab)
                st.success("削除しました")
                st.rerun()


# ---------------------------------------------------------------------------
# セッションリセット
# ---------------------------------------------------------------------------
def _reset_session():
    st.session_state.messages = []
    st.session_state.turn_count = 0
    st.session_state.phase = "chat"
    st.session_state.summary_data = None
    st.session_state.quiz_data = None
    st.session_state.quiz_answered = False
    st.session_state.quiz_word_id = None
    st.session_state.last_voice_ts = 0
    st.session_state.last_spoken_idx = -1


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="ビジネス日記", page_icon="📓", layout="wide")
    ensure_dirs()

    # セッション初期化
    defaults = {
        "messages": [],
        "turn_count": 0,
        "phase": "chat",
        "summary_data": None,
        "quiz_data": None,
        "quiz_answered": False,
        "quiz_word_id": None,
        "voice_mode": False,
        "last_voice_ts": 0,
        "last_spoken_idx": -1,
        "current_page": "今日の振り返り",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    profile = load_profile()

    # --- サイドバー ---
    with st.sidebar:
        st.title("📓 ビジネス日記")
        render_level_badge(profile)

        # ナビゲーション
        st.subheader("メニュー")
        page = st.radio(
            "ページ選択",
            ["📓 今日の振り返り", "📚 単語帳", "🥋 クイズ道場", "💬 文章ストック"],
            label_visibility="collapsed",
        )
        st.session_state.current_page = page

        st.divider()

        # 単語帳統計
        st.subheader("📚 単語帳")
        render_vocab_stats()

        st.divider()

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
        if st.button("🔄 新しい振り返りを始める", key="sidebar_new"):
            _reset_session()
            st.rerun()

    # --- メインエリア ---
    if "今日の振り返り" in page:
        page_reflection()
    elif "単語帳" in page:
        page_vocabulary()
    elif "クイズ道場" in page:
        page_quiz_dojo()
    elif "文章ストック" in page:
        page_sentence_stock()


if __name__ == "__main__":
    main()
