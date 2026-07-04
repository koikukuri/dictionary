/** word_list.csv パターン検索エンジン（ブラウザ版） */

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    const next = text[i + 1];

    if (inQuotes) {
      if (c === '"' && next === '"') {
        field += '"';
        i++;
      } else if (c === '"') {
        inQuotes = false;
      } else {
        field += c;
      }
      continue;
    }

    if (c === '"') {
      inQuotes = true;
    } else if (c === ",") {
      row.push(field);
      field = "";
    } else if (c === "\n" || (c === "\r" && next === "\n")) {
      row.push(field);
      if (row.some((cell) => cell.length > 0)) rows.push(row);
      row = [];
      field = "";
      if (c === "\r") i++;
    } else if (c !== "\r") {
      field += c;
    }
  }

  if (field.length || row.length) {
    row.push(field);
    if (row.some((cell) => cell.length > 0)) rows.push(row);
  }

  if (!rows.length) return [];
  const headers = rows[0];
  return rows.slice(1).map((cells) => {
    const obj = {};
    headers.forEach((h, idx) => {
      obj[h] = cells[idx] ?? "";
    });
    return obj;
  });
}

function charAt(text, index) {
  if (index < 1 || index > text.length) return "";
  return text[index - 1];
}

/** 1文字をひらがなに正規化（カタカナ→ひらがな、長音・英数はそのまま） */
function normalizeKanaChar(ch) {
  if (!ch) return "";
  const code = ch.charCodeAt(0);
  if (code >= 0x30a1 && code <= 0x30f6) return String.fromCharCode(code - 0x60);
  return ch;
}

function normalizeKanaString(text) {
  return [...text].map(normalizeKanaChar).join("");
}

function kanaEqual(a, b) {
  return normalizeKanaChar(a) === normalizeKanaChar(b);
}

function kanaStartsWith(text, prefix) {
  if (!prefix) return true;
  return normalizeKanaString(text).startsWith(normalizeKanaString(prefix));
}

function kanaEndsWith(text, suffix) {
  if (!suffix) return true;
  return normalizeKanaString(text).endsWith(normalizeKanaString(suffix));
}

function kanaIncludes(text, needle) {
  if (!needle) return true;
  return normalizeKanaString(text).includes(normalizeKanaString(needle));
}

function matchCriteria(row, criteria) {
  const word = row["単語・フレーズ"] || "";
  const reading = row["よみ"] || "";
  const hint = row["補足・ヒント"] || "";
  const mainCat = row["メインカテゴリ"] || "";
  const subCat = row["サブカテゴリ"] || "";
  const useReading = criteria.positionTarget === "reading";

  const target = useReading ? reading : word;

  if (criteria.length != null && criteria.length > 0) {
    if (criteria.lengthOnSurface) {
      if (word.length !== criteria.length) return false;
    } else if (parseInt(row["文字数"], 10) !== criteria.length) {
      return false;
    }
  }

  for (const [posStr, ch] of Object.entries(criteria.positions || {})) {
    if (!ch) continue;
    const actual = charAt(target, parseInt(posStr, 10));
    if (useReading) {
      if (!kanaEqual(actual, ch)) return false;
    } else if (actual !== ch) {
      return false;
    }
  }

  if (criteria.startsWith) {
    if (useReading) {
      if (!kanaStartsWith(reading, criteria.startsWith)) return false;
    } else if (!word.startsWith(criteria.startsWith)) {
      return false;
    }
  }
  if (criteria.endsWith) {
    if (useReading) {
      if (!kanaEndsWith(reading, criteria.endsWith)) return false;
    } else if (!word.endsWith(criteria.endsWith)) {
      return false;
    }
  }
  if (criteria.contains) {
    if (useReading) {
      if (!kanaIncludes(reading, criteria.contains)) return false;
    } else if (!word.includes(criteria.contains)) {
      return false;
    }
  }

  if (criteria.mainCategories?.length && !criteria.mainCategories.includes(mainCat)) {
    return false;
  }

  const searchable = `${hint} ${mainCat} ${subCat} ${word} ${reading}`;
  if (criteria.hintKeywords?.length) {
    const hit = criteria.hintKeywords.some((kw) => {
      if (!kw) return false;
      return searchable.includes(kw) || kanaIncludes(searchable, kw);
    });
    if (!hit) return false;
  }

  return true;
}

function searchWords(rows, criteria) {
  return rows.filter((row) => matchCriteria(row, criteria));
}

function parseNaturalQuery(query) {
  const criteria = {
    length: null,
    lengthOnSurface: false,
    positions: {},
    positionTarget: "word",
    startsWith: "",
    endsWith: "",
    contains: "",
    mainCategories: [],
    hintKeywords: [],
  };

  const text = query.trim();
  if (!text) return criteria;

  if (text.includes("よみ") || text.includes("読み")) criteria.positionTarget = "reading";
  if (text.includes("表記")) criteria.positionTarget = "word";
  if (text.includes("表記の文字数") || (text.includes("表記で") && text.includes("文字"))) {
    criteria.lengthOnSurface = true;
  }

  const lengthMatch = text.match(/(\d+)文字(?:の言葉|の単語|のフレーズ)/);
  if (lengthMatch) {
    criteria.length = parseInt(lengthMatch[1], 10);
  } else {
    const re = /(\d+)文字/g;
    let m;
    while ((m = re.exec(text)) !== null) {
      const end = m.index + m[0].length;
      if (end < text.length && text[end] === "目") continue;
      criteria.length = parseInt(m[1], 10);
    }
  }

  const posRe = /(\d+)文字目[がは]([^、。\d]+?)(?=、|\d文字目|の\d文字|の言葉|の単語|$)/g;
  let pm;
  while ((pm = posRe.exec(text)) !== null) {
    const ch = pm[2].trim().replace(/[、。 の]/g, "");
    if (ch) criteria.positions[parseInt(pm[1], 10)] = ch[0];
  }

  const startMatch = text.match(/(.+?)から始まる/);
  if (startMatch) criteria.startsWith = startMatch[1].trim();

  const endMatch = text.match(/(.+?)で終わる/);
  if (endMatch) criteria.endsWith = endMatch[1].trim();

  let remainder = text;
  [
    /\d+文字目[がは][^、]+/g,
    /\d+文字(?:の言葉|の単語|のフレーズ)/g,
    /.+?から始まる/g,
    /.+?で終わる/g,
    /(よみ|読み|表記)で/g,
    /表記の文字数/g,
  ].forEach((pat) => {
    remainder = remainder.replace(pat, "");
  });

  remainder = remainder.trim().replace(/^[、。 の　]+|[、。 の　]+$/g, "");
  if (remainder) {
    const keywords = [];
    if (remainder.includes("麺料理")) {
      keywords.push("麺", "パスタ", "ラーメン", "めん", "スパゲッティ", "中華");
      remainder = remainder.replace("麺料理", "");
    }
    const chunk = remainder.trim().replace(/^[、。 ]+|[、。 ]+$/g, "");
    if (chunk) keywords.push(chunk);
    criteria.hintKeywords = keywords.filter(Boolean);
  }

  return criteria;
}

function criteriaSummary(criteria) {
  const parts = [];
  const targetLabel = criteria.positionTarget === "word" ? "表記" : "よみ";

  if (criteria.length != null && criteria.length > 0) {
    const kind = criteria.lengthOnSurface ? "表記" : "よみ";
    parts.push(`${criteria.length}文字（${kind}）`);
  }

  Object.keys(criteria.positions || {})
    .map(Number)
    .sort((a, b) => a - b)
    .forEach((pos) => {
      parts.push(`${targetLabel}${pos}文字目=${criteria.positions[pos]}`);
    });

  if (criteria.startsWith) parts.push(`「${criteria.startsWith}」から始まる`);
  if (criteria.endsWith) parts.push(`「${criteria.endsWith}」で終わる`);
  if (criteria.contains) {
    const label = criteria.positionTarget === "reading" ? "よみ" : "表記";
    parts.push(`${label}に「${criteria.contains}」を含む`);
  }
  if (criteria.mainCategories?.length) {
    parts.push(`カテゴリ=${criteria.mainCategories.join(",")}`);
  }
  if (criteria.hintKeywords?.length) {
    parts.push(`キーワード=${criteria.hintKeywords.join(",")}`);
  }

  return parts.length ? parts.join(" / ") : "（条件なし）";
}

async function loadWordData(basePath = "") {
  const prefix = basePath.replace(/\/?$/, "/");
  const mainRes = await fetch(`${prefix}word_list.csv`);
  if (!mainRes.ok) throw new Error("word_list.csv を読み込めません");

  let rows = parseCsv(await mainRes.text());

  try {
    const supRes = await fetch(`${prefix}word_list_supplement.csv`);
    if (supRes.ok) {
      const extra = parseCsv(await supRes.text());
      const existing = new Set(rows.map((r) => r["単語・フレーズ"]));
      extra.forEach((row) => {
        const w = row["単語・フレーズ"];
        if (w && !existing.has(w)) {
          rows.push(row);
          existing.add(w);
        }
      });
    }
  } catch (_) {
    /* supplement は任意 */
  }

  return rows;
}

window.WordSearch = {
  parseCsv,
  loadWordData,
  searchWords,
  parseNaturalQuery,
  criteriaSummary,
  matchCriteria,
  normalizeKanaChar,
  kanaEqual,
};
