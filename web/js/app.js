/** UI コントローラ */

const NL_EXAMPLES = [
  "3文字目がマの5文字の言葉",
  "1文字目がプ、4文字目がタの5文字の言葉",
];

let allRows = [];
let posCount = 2;

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function buildNumberSelect(id, min, max, emptyLabel) {
  const select = $(id);
  select.innerHTML = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = emptyLabel;
  select.appendChild(empty);
  for (let n = min; n <= max; n++) {
    const opt = document.createElement("option");
    opt.value = String(n);
    opt.textContent = `${n}文字`;
    select.appendChild(opt);
  }
}

function buildIndexSelect(id, defaultValue) {
  const select = document.createElement("select");
  select.id = id;
  select.className = "select";
  for (let n = 1; n <= 20; n++) {
    const opt = document.createElement("option");
    opt.value = String(n);
    opt.textContent = `${n}文字目`;
    if (n === defaultValue) opt.selected = true;
    select.appendChild(opt);
  }
  return select;
}

function getPatternTarget() {
  return document.querySelector('input[name="patternTarget"]:checked')?.value || "word";
}

function getSelectedCategories() {
  return [...document.querySelectorAll("#categoryChecks input:checked")].map((el) => el.value);
}

function buildPatternCriteria() {
  const lengthRaw = parseInt($("filterLength").value, 10);
  const positions = {};

  for (let i = 1; i <= posCount; i++) {
    const idxEl = document.getElementById(`posIndex${i}`);
    const chEl = document.getElementById(`posChar${i}`);
    if (!idxEl || !chEl) continue;
    const pos = parseInt(idxEl.value, 10);
    const ch = chEl.value.trim();
    if (pos > 0 && ch) positions[pos] = ch[0];
  }

  const hintRaw = $("hintKeywords").value.trim();
  const hintKeywords = hintRaw
    ? hintRaw.split(/[,、]/).map((s) => s.trim()).filter(Boolean)
    : [];

  return {
    length: Number.isFinite(lengthRaw) && lengthRaw > 0 ? lengthRaw : null,
    lengthOnSurface: $("lengthOnSurface").checked,
    positionTarget: getPatternTarget(),
    startsWith: $("startsWith").value.trim(),
    endsWith: $("endsWith").value.trim(),
    contains: $("contains").value.trim(),
    mainCategories: getSelectedCategories(),
    hintKeywords,
    positions,
  };
}

function renderPosFields() {
  const container = $("posFields");
  container.innerHTML = "";

  for (let i = 1; i <= posCount; i++) {
    const row = document.createElement("div");
    row.className = "pos-row";

    const indexWrap = document.createElement("div");
    indexWrap.className = "pos-row-index";
    const indexLabel = document.createElement("label");
    indexLabel.setAttribute("for", `posIndex${i}`);
    indexLabel.textContent = `条件 ${i}`;
    indexWrap.appendChild(indexLabel);
    indexWrap.appendChild(buildIndexSelect(`posIndex${i}`, i));

    const charWrap = document.createElement("div");
    charWrap.className = "pos-row-char";
    const charLabel = document.createElement("label");
    charLabel.setAttribute("for", `posChar${i}`);
    charLabel.textContent = "この文字";
    const charInput = document.createElement("input");
    charInput.id = `posChar${i}`;
    charInput.type = "text";
    charInput.className = "char-input";
    charInput.maxLength = 1;
    charInput.inputMode = "text";
    charInput.autocomplete = "off";
    charInput.setAttribute("aria-label", `${i}番目の条件の文字`);
    charWrap.appendChild(charLabel);
    charWrap.appendChild(charInput);

    row.appendChild(indexWrap);
    row.appendChild(charWrap);
    container.appendChild(row);
  }
}

function renderNlExamples() {
  const container = $("nlExamples");
  NL_EXAMPLES.forEach((text) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "example-btn";
    btn.textContent = text;
    btn.addEventListener("click", () => {
      $("nlQuery").value = text;
      $("nlQuery").focus();
    });
    container.appendChild(btn);
  });
}

function renderResults(results, summary) {
  $("resultCount").textContent = `検索結果: ${results.length.toLocaleString()} 件`;
  $("resultSummary").textContent = `条件: ${summary}`;

  const cards = $("resultCards");
  const tbody = $("resultTable").querySelector("tbody");
  cards.innerHTML = "";
  tbody.innerHTML = "";

  if (!results.length) {
    $("emptyMessage").classList.remove("hidden");
    return;
  }

  $("emptyMessage").classList.add("hidden");

  const show = results.slice(0, 200);
  show.forEach((row) => {
    const card = document.createElement("article");
    card.className = "word-card";
    card.innerHTML = `
      <div class="word">${escapeHtml(row["単語・フレーズ"] || "")}</div>
      <div class="meta">${escapeHtml(row["よみ"] || "")} · ${escapeHtml(row["文字数"] || "")}文字 · ZIPF ${escapeHtml(row["ZIPF"] || "—")} · ${escapeHtml(row["メインカテゴリ"] || "")}</div>
      <div class="hint">${escapeHtml(row["補足・ヒント"] || "")}</div>`;
    cards.appendChild(card);

    const tr = document.createElement("tr");
    ["単語・フレーズ", "よみ", "文字数", "ZIPF", "メインカテゴリ", "補足・ヒント"].forEach((key) => {
      const td = document.createElement("td");
      td.textContent = row[key] || "";
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  if (results.length > 200) {
    $("resultSummary").textContent += `（表示 ${show.length} / 全 ${results.length.toLocaleString()} 件）`;
  }
}

function runSearch(criteria) {
  if (!allRows.length) return;
  const results = WordSearch.searchWords(allRows, criteria);
  renderResults(results, WordSearch.criteriaSummary(criteria));
  $("resultCount").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function init() {
  const status = $("loadStatus");

  buildNumberSelect("filterLength", 1, 20, "指定なし");
  renderNlExamples();
  renderPosFields();

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      $(`panel-${tab.dataset.tab}`).classList.add("active");
    });
  });

  $("btnAddPos").addEventListener("click", () => {
    if (posCount < 12) {
      posCount += 1;
      renderPosFields();
    }
  });

  $("btnRemovePos").addEventListener("click", () => {
    if (posCount > 0) {
      posCount -= 1;
      renderPosFields();
    }
  });

  $("btnNlSearch").addEventListener("click", () => {
    const criteria = WordSearch.parseNaturalQuery($("nlQuery").value);
    criteria.positionTarget = document.querySelector('input[name="nlTarget"]:checked')?.value || "word";
    runSearch(criteria);
  });

  $("nlQuery").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("btnNlSearch").click();
  });

  $("btnPatternSearch").addEventListener("click", () => {
    runSearch(buildPatternCriteria());
  });

  try {
    const base = window.location.pathname.includes("/web/") ? "../" : "./";
    allRows = await WordSearch.loadWordData(base);
    status.textContent = `${allRows.length.toLocaleString()} 語`;
    status.classList.add("ready");

    const cats = [...new Set(allRows.map((r) => r["メインカテゴリ"]).filter(Boolean))].sort();
    const container = $("categoryChecks");
    cats.forEach((c) => {
      const label = document.createElement("label");
      label.innerHTML = `<input type="checkbox" value="${escapeHtml(c)}"> ${escapeHtml(c)}`;
      container.appendChild(label);
    });
  } catch (err) {
    status.textContent = "読込失敗";
    status.classList.add("error");
    console.error(err);
  }
}

init();
