# -*- coding: utf-8 -*-
"""word_list.csv 向けパターン検索エンジン"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class SearchCriteria:
    """検索条件"""

    length: int | None = None
    length_on_surface: bool = False  # False=よみの文字数(CSV列), True=表記の文字数
    positions: dict[int, str] = field(default_factory=dict)  # 1-indexed
    position_target: str = "word"  # "word" | "reading"
    starts_with: str = ""
    ends_with: str = ""
    contains: str = ""
    main_categories: list[str] = field(default_factory=list)
    sub_categories: list[str] = field(default_factory=list)
    hint_keywords: list[str] = field(default_factory=list)
    word_type: str = ""  # 単語 / 空=すべて


def load_words(csv_path: str | Path) -> list[dict]:
    path = Path(csv_path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    supplement_path = path.with_name("word_list_supplement.csv")
    if supplement_path.exists():
        with supplement_path.open(encoding="utf-8-sig", newline="") as f:
            extra = list(csv.DictReader(f))
        existing = {r.get("単語・フレーズ", "") for r in rows}
        for row in extra:
            word = row.get("単語・フレーズ", "")
            if word and word not in existing:
                rows.append(row)
                existing.add(word)

    return rows


def char_at(text: str, index: int) -> str:
    """1-indexed で index 番目の文字を返す（範囲外は空文字）"""
    if index < 1 or index > len(text):
        return ""
    return text[index - 1]


def normalize_kana_char(ch: str) -> str:
    """1文字をひらがなに正規化（カタカナ→ひらがな）"""
    if not ch:
        return ""
    code = ord(ch)
    if 0x30A1 <= code <= 0x30F6:
        return chr(code - 0x60)
    return ch


def normalize_kana_string(text: str) -> str:
    return "".join(normalize_kana_char(c) for c in text)


def kana_equal(a: str, b: str) -> bool:
    return normalize_kana_char(a) == normalize_kana_char(b)


def kana_starts_with(text: str, prefix: str) -> bool:
    if not prefix:
        return True
    return normalize_kana_string(text).startswith(normalize_kana_string(prefix))


def kana_ends_with(text: str, suffix: str) -> bool:
    if not suffix:
        return True
    return normalize_kana_string(text).endswith(normalize_kana_string(suffix))


def kana_includes(text: str, needle: str) -> bool:
    if not needle:
        return True
    return normalize_kana_string(needle) in normalize_kana_string(text)


def match_criteria(row: dict, criteria: SearchCriteria) -> bool:
    word = row.get("単語・フレーズ", "")
    reading = row.get("よみ", "")
    hint = row.get("補足・ヒント", "")
    main_cat = row.get("メインカテゴリ", "")
    sub_cat = row.get("サブカテゴリ", "")
    row_type = row.get("タイプ", "")

    use_reading = criteria.position_target == "reading"
    target = reading if use_reading else word

    if criteria.length is not None:
        if criteria.length_on_surface:
            if len(word) != criteria.length:
                return False
        else:
            try:
                if int(row.get("文字数", 0)) != criteria.length:
                    return False
            except (TypeError, ValueError):
                return False

    for pos, ch in criteria.positions.items():
        if not ch:
            continue
        actual = char_at(target, pos)
        if use_reading:
            if not kana_equal(actual, ch):
                return False
        elif actual != ch:
            return False

    if criteria.starts_with:
        if use_reading:
            if not kana_starts_with(reading, criteria.starts_with):
                return False
        elif not word.startswith(criteria.starts_with):
            return False
    if criteria.ends_with:
        if use_reading:
            if not kana_ends_with(reading, criteria.ends_with):
                return False
        elif not word.endswith(criteria.ends_with):
            return False
    if criteria.contains:
        if use_reading:
            if not kana_includes(reading, criteria.contains):
                return False
        elif criteria.contains not in word:
            return False

    if criteria.main_categories and main_cat not in criteria.main_categories:
        return False
    if criteria.sub_categories and sub_cat not in criteria.sub_categories:
        return False
    if criteria.word_type and row_type != criteria.word_type:
        return False

    searchable = f"{hint} {main_cat} {sub_cat} {word} {reading}"
    if criteria.hint_keywords:
        if not any(
            kw in searchable or kana_includes(searchable, kw)
            for kw in criteria.hint_keywords
            if kw
        ):
            return False

    return True


def search_words(rows: Iterable[dict], criteria: SearchCriteria) -> list[dict]:
    return [row for row in rows if match_criteria(row, criteria)]


def parse_natural_query(query: str) -> SearchCriteria:
    """自然文風クエリを SearchCriteria に変換する。

    例:
      3文字目がマの5文字の言葉
      タから始まる麺料理
      1文字目がプ、4文字目がタの5文字の言葉
    """
    criteria = SearchCriteria()
    text = query.strip()
    if not text:
        return criteria

    if "よみ" in text or "読み" in text:
        criteria.position_target = "reading"
    if "表記" in text:
        criteria.position_target = "word"
    if "表記の文字数" in text or ("表記で" in text and "文字" in text):
        criteria.length_on_surface = True

    length_match = re.search(r"(\d+)文字(?:の言葉|の単語|のフレーズ)", text)
    if length_match:
        criteria.length = int(length_match.group(1))
    else:
        for m in re.finditer(r"(\d+)文字", text):
            end = m.end()
            if end < len(text) and text[end] == "目":
                continue
            criteria.length = int(m.group(1))

    for m in re.finditer(
        r"(\d+)文字目[がは]([^、。\d]+?)(?=、|\d文字目|の\d文字|の言葉|の単語|$)",
        text,
    ):
        pos = int(m.group(1))
        ch = m.group(2).strip("、。 の")
        if ch:
            criteria.positions[pos] = ch[0]

    m = re.search(r"(.+?)から始まる", text)
    if m:
        criteria.starts_with = m.group(1).strip()

    m = re.search(r"(.+?)で終わる", text)
    if m:
        criteria.ends_with = m.group(1).strip()

    remainder = text
    for pattern in (
        r"\d+文字目が[^、]+",
        r"\d+文字(?:の言葉|の単語|のフレーズ|)",
        r".+?から始まる",
        r".+?で終わる",
        r"(よみ|読み|表記)で",
        r"表記の文字数",
    ):
        remainder = re.sub(pattern, "", remainder)

    remainder = remainder.strip("、。 の　")
    if remainder:
        keywords = []
        if "麺料理" in remainder:
            keywords.extend(["麺", "パスタ", "ラーメン", "めん"])
            remainder = remainder.replace("麺料理", "")
        chunk = remainder.strip("、。 ")
        if chunk:
            keywords.append(chunk)
        criteria.hint_keywords = [k for k in keywords if k]

    return criteria


def criteria_summary(criteria: SearchCriteria) -> str:
    parts: list[str] = []
    target_label = "表記" if criteria.position_target == "word" else "よみ"

    if criteria.length is not None:
        kind = "表記" if criteria.length_on_surface else "よみ"
        parts.append(f"{criteria.length}文字（{kind}）")

    for pos in sorted(criteria.positions):
        parts.append(f"{target_label}{pos}文字目={criteria.positions[pos]}")

    if criteria.starts_with:
        parts.append(f"「{criteria.starts_with}」から始まる")
    if criteria.ends_with:
        parts.append(f"「{criteria.ends_with}」で終わる")
    if criteria.contains:
        label = target_label if criteria.position_target == "reading" else "表記"
        parts.append(f"{label}に「{criteria.contains}」を含む")
    if criteria.main_categories:
        parts.append(f"カテゴリ={','.join(criteria.main_categories)}")
    if criteria.hint_keywords:
        parts.append(f"キーワード={','.join(criteria.hint_keywords)}")

    return " / ".join(parts) if parts else "（条件なし）"
