import streamlit as st
import anthropic
import os
from datetime import datetime
import json
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Reflect - AI ビジネス日記",
    page_icon="💭",
    layout="centered"
)

st.title("💭 Reflect")
st.markdown("**AI と話すビジネス日記**")

api_key = os.getenv("ANTHROPIC_API_KEY")

if not api_key:
    st.warning("⚠️ APIキーが設定されていません。.env ファイルを確認してください。")
    st.stop()

client = anthropic.Anthropic(api_key=api_key)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "exp" not in st.session_state:
    st.session_state.exp = 0
    st.session_state.level = 1

with st.sidebar:
    st.header("📊 あなたの成長")
    st.metric("レベル", st.session_state.level)
    st.progress((st.session_state.exp % 50) / 50)
    st.caption(f"{st.session_state.exp % 50} / 50 EXP")
    st.divider()
    if st.button("🔄 新しい会話"):
        st.session_state.messages = []
        st.rerun()

if len(st.session_state.messages) == 0:
    st.session_state.messages.append({
        "role": "assistant",
        "content": "お疲れ様です！✨\n\n今日はどんな1日でしたか？\n印象に残った出来事を教えてください。"
    })

for message in st.session_state.messages:
    if message["role"] == "assistant":
        st.chat_message("assistant", avatar="🤖").write(message["content"])
    else:
        st.chat_message("user", avatar="👤").write(message["content"])

user_input = st.chat_input("話してみましょう...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.chat_message("user", avatar="👤").write(user_input)

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("考え中..."):
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system="あなたはビジネスパーソンの日記をサポートするAIアシスタントです。ユーザーの今日の仕事について優しく質問して深掘りしてください。3-4回の質問でまとめに入り、学んだことを整理してあげてください。",
                messages=[{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
            )
            ai_message = response.content[0].text
            st.write(ai_message)
            st.session_state.messages.append({"role": "assistant", "content": ai_message})
            st.session_state.exp += 10
            if st.session_state.exp >= st.session_state.level * 50:
                st.session_state.level += 1
                st.balloons()