"""📄 FPレポート - PDF生成 & ダウンロード"""

import streamlit as st
import subprocess
import os
from pathlib import Path

st.set_page_config(page_title="FPレポート", page_icon="📄", layout="wide")
st.title("📄 FPレポート生成")

st.markdown("""
ライフプラン・シミュレーションの結果を **6ページのPDFレポート** として生成します。

**レポート内容:**
1. 表紙（前提条件一覧）
2. 3シナリオ比較 - 純資産推移グラフ
3. 年間収支分析 + 夫の年収カーブ
4. 支出内訳の変化 + 家賃値上がり影響
5. 資産構成推移 + 運用アドバイス（NISA/iDeCo/保険）
6. 具体的アクションプランとタイムライン
""")

REPORT_SCRIPT = Path(__file__).parent.parent / "report.py"
PDF_PATH = Path(__file__).parent.parent / "life_plan_report.pdf"

if st.button("🚀 レポートを生成する", type="primary", width="stretch"):
    with st.spinner("PDFレポートを生成中...（約10秒）"):
        result = subprocess.run(
            ["python", str(REPORT_SCRIPT)],
            capture_output=True, text=True, timeout=60,
        )
    if result.returncode == 0 and PDF_PATH.exists():
        st.success("レポートが生成されました！")
        with open(PDF_PATH, "rb") as f:
            pdf_bytes = f.read()
        st.download_button(
            label="📥 PDFをダウンロード",
            data=pdf_bytes,
            file_name="life_plan_report.pdf",
            mime="application/pdf",
            width="stretch",
        )
        st.info(f"ファイルサイズ: {len(pdf_bytes) / 1024:.0f} KB")
    else:
        st.error("レポート生成に失敗しました")
        if result.stderr:
            st.code(result.stderr)

# 既存PDFがあればダウンロードボタンを常に表示
if PDF_PATH.exists() and not st.session_state.get("_report_just_generated"):
    st.markdown("---")
    st.markdown("**前回生成済みのレポート:**")
    with open(PDF_PATH, "rb") as f:
        pdf_bytes = f.read()
    st.download_button(
        label="📥 既存のPDFをダウンロード",
        data=pdf_bytes,
        file_name="life_plan_report.pdf",
        mime="application/pdf",
        width="stretch",
    )
