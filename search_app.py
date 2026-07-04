#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
word_list.csv パターン検索アプリ

起動方法:
    pip install streamlit pandas
    streamlit run search_app.py
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from word_search import (
    SearchCriteria,
    criteria_summary,
    load_words,
    parse_natural_query,
    search_words,
)

CSV_PATH = Path(__file__).resolve().parent / "word_list.csv"
DISPLAY_COLUMNS = [
    "単語・フレーズ",
    "よみ",
    "文字数",
    "メインカテゴリ",
    "サブカテゴリ",
    "タイプ",
    "補足・ヒント",
]


@st.cache_data(show_spinner="word_list.csv を読み込み中...")
def get_data(path: str):
    rows = load_words(path)
    categories = sorted({r["メインカテゴリ"] for r in rows if r.get("メインカテゴリ")})
    sub_categories = sorted({r["サブカテゴリ"] for r in rows if r.get("サブカテゴリ")})
    return rows, categories, sub_categories


def build_criteria_from_ui() -> SearchCriteria:
    criteria = SearchCriteria()

    criteria.length_on_surface = st.session_state.get("length_on_surface", False)
    criteria.position_target = st.session_state.get("position_target", "word")

    length = st.session_state.get("filter_length")
    if length and length > 0:
        criteria.length = int(length)

    criteria.starts_with = st.session_state.get("starts_with", "").strip()
    criteria.ends_with = st.session_state.get("ends_with", "").strip()
    criteria.contains = st.session_state.get("contains", "").strip()

    criteria.main_categories = st.session_state.get("main_categories", [])
    criteria.sub_categories = st.session_state.get("sub_categories", [])

    hint_raw = st.session_state.get("hint_keywords", "").strip()
    if hint_raw:
        criteria.hint_keywords = [k.strip() for k in hint_raw.replace("、", ",").split(",") if k.strip()]

    pos_count = st.session_state.get("pos_count", 0)
    for i in range(1, pos_count + 1):
        pos = st.session_state.get(f"pos_index_{i}")
        ch = st.session_state.get(f"pos_char_{i}", "").strip()
        if pos and ch:
            criteria.positions[int(pos)] = ch[0]

    return criteria


def main():
    st.set_page_config(page_title="謎解き単語検索", page_icon="🔍", layout="wide")
    st.title("🔍 謎解き単語パターン検索")
    st.caption(f"データ: `{CSV_PATH.name}` ＋ `word_list_supplement.csv`（あれば自動統合）")

    if not CSV_PATH.exists():
        st.error(f"{CSV_PATH.name} が見つかりません。")
        st.stop()

    rows, categories, sub_categories = get_data(str(CSV_PATH))
    st.sidebar.metric("登録語数", f"{len(rows):,}")

    tab_nl, tab_pattern = st.tabs(["自然文クエリ", "条件を組み立てる"])

    with tab_nl:
        nl_query = st.text_input("クエリを入力")
        nl_target = st.radio(
            "文字位置の判定対象",
            options=["word", "reading"],
            format_func=lambda x: "表記（単語・フレーズ）" if x == "word" else "よみ",
            horizontal=True,
            key="nl_target",
        )
        st.caption("よみ選択時はカタカナ・ひらがなを区別しません")
        if st.button("自然文で検索", type="primary"):
            criteria = parse_natural_query(nl_query)
            if nl_target:
                criteria.position_target = nl_target
            st.session_state["active_criteria"] = criteria
            st.session_state["active_summary"] = criteria_summary(criteria)

    with tab_pattern:
        col1, col2 = st.columns(2)
        with col1:
            st.session_state.setdefault("filter_length", 0)
            st.number_input("文字数", min_value=0, max_value=20, step=1, key="filter_length",
                            help="0=指定なし。よみの文字数（CSVの文字数列）がデフォルト")
            st.checkbox("表記の文字数で数える", key="length_on_surface")
            st.text_input("先頭の文字（から始まる）", key="starts_with")
            st.text_input("末尾の文字（で終わる）", key="ends_with")
            st.text_input("表記に含む文字", key="contains")
        with col2:
            st.multiselect("メインカテゴリ", categories, key="main_categories")
            st.multiselect("サブカテゴリ", sub_categories, key="sub_categories")
            st.text_input("キーワード（ヒント・カテゴリ）カンマ区切り", key="hint_keywords",
                           help="いずれか1つがヒント・カテゴリ・表記・よみに含まれればヒット")
            st.radio(
                "文字位置の判定対象",
                options=["word", "reading"],
                format_func=lambda x: "表記" if x == "word" else "よみ",
                key="position_target",
            )

        st.markdown("**文字位置の指定**")
        st.session_state.setdefault("pos_count", 2)
        pos_cols = st.columns([1, 1, 2])
        with pos_cols[0]:
            st.number_input("条件数", min_value=0, max_value=12, step=1, key="pos_count")
        for i in range(1, st.session_state["pos_count"] + 1):
            c1, c2 = st.columns(2)
            with c1:
                st.number_input(f"{i}. 何文字目", min_value=1, max_value=20, key=f"pos_index_{i}")
            with c2:
                st.text_input(f"{i}. その文字", max_chars=3, key=f"pos_char_{i}")

        st.caption("よみ選択時はカタカナ・ひらがなを区別しません")

        if st.button("条件で検索", type="primary"):
            criteria = build_criteria_from_ui()
            st.session_state["active_criteria"] = criteria
            st.session_state["active_summary"] = criteria_summary(criteria)

    if "active_criteria" in st.session_state:
        criteria: SearchCriteria = st.session_state["active_criteria"]
        summary = st.session_state.get("active_summary", criteria_summary(criteria))
        results = search_words(rows, criteria)

        st.divider()
        st.subheader(f"検索結果: {len(results):,} 件")
        st.info(f"条件: {summary}")

        if results:
            df = pd.DataFrame(results)[DISPLAY_COLUMNS]
            st.dataframe(df, use_container_width=True, height=480)

            csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "結果をCSVダウンロード",
                data=csv_bytes,
                file_name="search_results.csv",
                mime="text/csv",
            )
        else:
            st.warning("該当する語がありません。条件を緩めてみてください。")


if __name__ == "__main__":
    main()
