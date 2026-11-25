"use strict";

// The page loads the real harnesscalc Python package into Pyodide, so the
// browser and the CLI share one implementation.
const PYODIDE_INDEX = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
const PKG_FILES = ["__init__.py", "tables.py", "calcs.py", "bom.py", "terminals.py", "sizing.py", "report.py", "webapi.py"];
const ROOT = new URL("../", document.baseURI);   // repo root: web/ sits next to harnesscalc/
const EXAMPLE_BOM = "examples/front_lighting.csv";
const EXAMPLE_CATALOG = "harnesscalc/data/terminals.csv";
const STORE_KEY = "harnesscalc:v2";

const SETTINGS = [
  { key: "supply_voltage", label: "Supply voltage", unit: "V", step: "0.1" },
  { key: "max_drop_pct", label: "Max voltage drop", unit: "%", step: "0.5" },
  { key: "ambient_c", label: "Ambient temperature", unit: "°C", step: "5" },
  { key: "thinnest_awg", label: "Thinnest gauge allowed", unit: "AWG", type: "gauge", help: "Mechanical minimum" },
  {
    key: "round_trip", label: "Return path", type: "choice", help: "How the length is counted for voltage drop",
    options: [[true, "Return wire (round trip)"], [false, "Chassis ground (one way)"]],
  },
];

const COLS = [
  { key: "part", label: "Part", w: "11rem" },
  { key: "current_a", label: "Load A", w: "5rem", num: true },
  { key: "length_mm", label: "Length mm", w: "6rem", num: true },
  { key: "terminals", label: "Terminals", w: "12rem", list: "terminal-list", placeholder: "part number(s)" },
];

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmt = (x, d = 2) => (x === null || x === undefined || !Number.isFinite(x) ? "—" : Number(x).toFixed(d));
const num = (x) => (x === null || x === undefined ? "—" : String(+Number(x).toFixed(3)));
const range = (r) => (!r ? "—" : r[0] === r[1] ? String(r[0]) : `${r[0]}–${r[1]}`);

let api = null;
let INFO = null;
let EXAMPLE_CATALOG_TEXT = "";
const state = {
  rows: [], title: "harness", config: {}, result: null, timer: null,
  catalogText: "", catalogName: "example catalog",
};

// ---------------------------------------------------------------- storage

function save() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify({
      rows: state.rows, title: state.title, config: state.config,
      catalogText: state.catalogText, catalogName: state.catalogName,
    }));
  } catch { /* storage unavailable: the app still works, it just won't remember */ }
}

function restore() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY) || "null"); } catch { return null; }
}

// ---------------------------------------------------------------- startup

async function fetchText(path) {
  const res = await fetch(new URL(path, ROOT));
  if (!res.ok) throw new Error(`could not load ${path} (HTTP ${res.status})`);
  return res.text();
}

async function boot() {
  try {
    const py = await loadPyodide({ indexURL: PYODIDE_INDEX });
    const files = await Promise.all(PKG_FILES.map(async (f) => [f, await fetchText(`harnesscalc/${f}`)]));
    EXAMPLE_CATALOG_TEXT = await fetchText(EXAMPLE_CATALOG);
    py.FS.mkdirTree("/home/pyodide/harnesscalc/data");
    for (const [f, text] of files) py.FS.writeFile(`/home/pyodide/harnesscalc/${f}`, text);
    py.FS.writeFile("/home/pyodide/harnesscalc/data/terminals.csv", EXAMPLE_CATALOG_TEXT);
    py.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
    api = py.pyimport("harnesscalc.webapi");
    INFO = JSON.parse(api.info());
  } catch (err) {
    setRuntime("error", "Failed to load");
    const fileHint = location.protocol === "file:"
      ? "<br>Browsers block this page when it is opened as a file. Serve the project folder instead: run <code>python3 -m http.server 8000</code> in it, then open <code>http://localhost:8000/web/</code>."
      : "";
    $("#banner").innerHTML = `<div class="banner warn"><strong>Could not start the Python runtime</strong>${esc(err.message || err)}${fileHint}</div>`;
    console.error(err);
    return;
  }

  setRuntime("ready", "Python ready");
  const saved = restore();
  state.config = { ...INFO.defaults };
  for (const k of Object.keys(INFO.defaults)) {
    if (saved?.config && typeof saved.config[k] === typeof INFO.defaults[k]) state.config[k] = saved.config[k];
  }
  state.catalogText = saved?.catalogText || EXAMPLE_CATALOG_TEXT;
  state.catalogName = saved?.catalogText ? saved.catalogName : "example catalog";
  buildSettings();
  enableControls();
  renderCatalog();

  if (Array.isArray(saved?.rows) && saved.rows.length) {
    state.rows = saved.rows;
    state.title = saved.title || "harness";
    renderEditor();
    analyze();
  } else {
    await loadExample();
  }
}

function setRuntime(kind, text) {
  const el = $("#runtime");
  el.className = `pill ${kind}`;
  el.textContent = text;
}

function enableControls() {
  document.querySelectorAll("button:disabled, input:disabled").forEach((el) => { el.disabled = false; });
  document.querySelectorAll("[aria-disabled]").forEach((el) => el.removeAttribute("aria-disabled"));
}

// ---------------------------------------------------------------- settings

function buildSettings() {
  $("#settings").innerHTML = SETTINGS.map((s) => {
    const v = state.config[s.key];
    let control;
    if (s.type === "gauge") {
      control = `<select name="${s.key}">${INFO.gauges.map((g) => `<option value="${g}" ${g === v ? "selected" : ""}>${g}</option>`).join("")}</select>`;
    } else if (s.type === "choice") {
      control = `<select name="${s.key}" data-bool>${s.options.map(([val, label]) =>
        `<option value="${val}" ${val === v ? "selected" : ""}>${esc(label)}</option>`).join("")}</select>`;
    } else {
      control = `<input type="number" name="${s.key}" step="${s.step}" value="${v}" inputmode="decimal" required>`;
    }
    return `<label class="field ${s.type === "choice" ? "wide" : ""}"><span>${esc(s.label)}</span>
      <span class="input-unit">${control}${s.unit ? `<em>${esc(s.unit)}</em>` : ""}</span>
      ${s.help ? `<small>${esc(s.help)}</small>` : ""}</label>`;
  }).join("");
}

function onSettingInput(e) {
  const el = e.target;
  if (!el.name) return;
  if ("bool" in el.dataset) state.config[el.name] = el.value === "true";
  else state.config[el.name] = el.value === "" ? null : Number(el.value);
  scheduleAnalyze();
}

// ---------------------------------------------------------------- parts editor

function emptyRow() {
  return Object.fromEntries(INFO.columns.map((c) => [c, ""]));
}

function cellControl(col, value) {
  return `<input data-k="${col.key}" value="${esc(value)}" aria-label="${esc(col.label)}" autocomplete="off" spellcheck="false"
    ${col.num ? 'inputmode="decimal" class="num"' : ""} ${col.list ? `list="${col.list}"` : ""}
    ${col.placeholder ? `placeholder="${esc(col.placeholder)}"` : ""}>`;
}

function renderEditor() {
  const head = `<thead><tr><th class="idx">#</th>${COLS.map((c) => `<th style="min-width:${c.w}">${esc(c.label)}</th>`).join("")}<th></th></tr></thead>`;
  const body = state.rows.map((r, i) => `<tr data-i="${i}">
      <td class="idx">${i + 1}</td>
      ${COLS.map((c) => `<td>${cellControl(c, r[c.key])}</td>`).join("")}
      <td><button class="icon-btn" type="button" data-del="${i}" title="Delete part" aria-label="Delete row ${i + 1}">×</button></td>
    </tr>`).join("");
  $("#editor").innerHTML = head + `<tbody>${body}</tbody>`;
  updateBomName();
  markEditorRows();
}

function updateBomName() {
  const n = state.rows.length;
  $("#bom-name").textContent = `${state.title}.csv · ${n} part${n === 1 ? "" : "s"}`;
}

function markEditorRows() {
  const trs = document.querySelectorAll("#editor tbody tr");
  trs.forEach((tr) => { tr.classList.remove("row-error", "row-fail"); tr.removeAttribute("title"); });
  const r = state.result;
  if (!r) return;
  if (!r.ok && r.kind === "bom") {
    for (const p of r.problems) {
      const m = /^row (\d+):/.exec(p);
      const tr = m && trs[Number(m[1]) - 2];   // CSV row 1 is the header
      if (tr) { tr.classList.add("row-error"); tr.title = (tr.title ? tr.title + "\n" : "") + p; }
    }
  } else if (r.ok) {
    for (const res of r.results) if (!res.ok) trs[res.row - 2]?.classList.add("row-fail");
  }
}

function onEditorInput(e) {
  const el = e.target;
  const tr = el.closest("tr[data-i]");
  if (!tr || !el.dataset.k) return;
  state.rows[Number(tr.dataset.i)][el.dataset.k] = el.value;
  scheduleAnalyze();
}

function onEditorClick(e) {
  const del = e.target.closest("[data-del]");
  if (!del) return;
  state.rows.splice(Number(del.dataset.del), 1);
  renderEditor();
  analyze();
}

function addRow() {
  state.rows.push(emptyRow());
  renderEditor();
  analyze();
  const tr = document.querySelector("#editor tbody tr:last-child");
  tr?.querySelector('[data-k="part"]')?.focus();
  tr?.scrollIntoView({ block: "nearest" });
}

function focusRow(csvRow) {
  const tr = document.querySelectorAll("#editor tbody tr")[csvRow - 2];
  if (!tr) return;
  tr.scrollIntoView({ behavior: "smooth", block: "center" });
  tr.classList.remove("flash");
  void tr.offsetWidth;
  tr.classList.add("flash");
  tr.querySelector('[data-k="terminals"]')?.focus({ preventScroll: true });
}

// ---------------------------------------------------------------- catalog

function renderCatalog() {
  const out = JSON.parse(api.catalog(state.catalogText));
  $("#catalog-name").textContent = out.ok
    ? `${state.catalogName} · ${out.terminals.length} terminal${out.terminals.length === 1 ? "" : "s"}`
    : state.catalogName;
  $("#terminal-list").innerHTML = out.ok
    ? out.terminals.map((t) => `<option value="${esc(t.part_number)}">${esc(t.range)} AWG ${esc(t.description)}</option>`).join("")
    : "";
  $("#catalog").innerHTML = !out.ok
    ? `<div class="banner warn"><strong>This catalog has problems</strong><ul>${out.problems.map((p) => `<li>${esc(p)}</li>`).join("")}</ul></div>`
    : !out.terminals.length ? `<p class="table-note">The catalog is empty.</p>`
    : `<table><thead><tr><th>Part number</th><th>Description</th><th class="n">Wire range AWG</th></tr></thead><tbody>
      ${out.terminals.map((t) => `<tr><td><code>${esc(t.part_number)}</code></td><td>${esc(t.description)}</td>
        <td class="n">${esc(t.range.replace("-", "–"))}</td></tr>`).join("")}</tbody></table>`;
}

function setCatalog(text, name) {
  state.catalogText = text;
  state.catalogName = name;
  renderCatalog();
  analyze();
}

// ---------------------------------------------------------------- import / export

function importCsv(text, name) {
  const out = JSON.parse(api.csv_to_rows(text));
  state.rows = out.rows;
  state.title = name.replace(/\.csv$/i, "") || "harness";
  renderEditor();
  analyze();
  if (out.ignored.length) {
    $("#banner").insertAdjacentHTML("afterbegin",
      `<div class="banner info">Ignored column${out.ignored.length > 1 ? "s" : ""}: ${out.ignored.map(esc).join(", ")}</div>`);
  }
}

async function loadExample() {
  try {
    importCsv(await fetchText(EXAMPLE_BOM), EXAMPLE_BOM.split("/").pop());
  } catch (err) {
    console.error(err);
    state.rows = [];
    renderEditor();
    analyze();
  }
}

function download(name, text, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const DOWNLOADS = { report_md: ["_gauges.md", "text/markdown"], results_csv: ["_gauges.csv", "text/csv"] };

// ---------------------------------------------------------------- analysis

function scheduleAnalyze() {
  clearTimeout(state.timer);
  state.timer = setTimeout(analyze, 250);
}

function analyze() {
  if (!api) return;
  clearTimeout(state.timer);
  try {
    state.result = JSON.parse(api.run(
      JSON.stringify(state.rows), JSON.stringify(state.config), state.catalogText, state.title));
  } catch (err) {
    console.error(err);
    state.result = { ok: false, kind: "internal", problems: [`internal error: ${err.message || err}`] };
  }
  document.querySelectorAll("#settings input").forEach((el) => {
    el.classList.toggle("bad", state.result.kind === "config" && el.value === "");
  });
  save();
  updateBomName();
  renderResults();
  markEditorRows();
}

const SET_BY = {
  "current": "Current",
  "voltage drop": "Voltage drop",
  "minimum gauge": "Minimum gauge",
  "terminal": "Terminal",
};

function renderResults() {
  const r = state.result;
  document.querySelectorAll("[data-dl]").forEach((b) => { b.disabled = !r.ok; });

  if (!r.ok) {
    const empty = r.problems.length === 1 && /no parts found|file is empty/.test(r.problems[0]);
    const heading = { config: "Check the design limits", catalog: "Fix the terminal catalog", bom: "Fix the parts list" }[r.kind]
      || "Something went wrong";
    $("#banner").innerHTML = empty
      ? `<div class="banner info">Add a part or import a BOM to start.</div>`
      : `<div class="banner warn"><strong>${heading}</strong><ul>${r.problems.map((p) => `<li>${esc(p)}</li>`).join("")}</ul></div>`;
    $("#results").innerHTML = "";
    return;
  }

  const bad = r.results.filter((x) => !x.ok);
  $("#banner").innerHTML = !bad.length
    ? `<div class="banner pass"><strong>All ${r.results.length} parts sized</strong>Each wire carries its load, stays within the voltage-drop limit and fits its terminals.</div>`
    : `<div class="banner fail"><strong>${bad.length} of ${r.results.length} part${r.results.length > 1 ? "s" : ""} need${bad.length === 1 ? "s" : ""} attention</strong><ul>${bad.map((x) => `
        <li><button class="link" type="button" data-goto="${x.row}">${esc(x.part)}</button> ${esc(x.notes.join("; "))}</li>`).join("")}</ul></div>`;

  $("#results").innerHTML = `<table class="results"><thead><tr>
      <th>Part</th><th class="n">Load A</th><th class="n">Length mm</th><th>Terminals</th>
      <th class="n">Wire gauge</th><th>Set by</th><th class="n">Terminal range</th><th class="n">Drop</th><th>Status</th>
    </tr></thead><tbody>
    ${r.results.map((x) => {
      const note = x.notes.length ? `<span class="${x.ok ? "note" : "why"}">${esc(x.notes.join("; "))}</span>` : "";
      return `<tr>
        <td><button class="link" type="button" data-goto="${x.row}">${esc(x.part)}</button></td>
        <td class="n">${num(x.current_a)}</td><td class="n">${num(x.length_mm)}</td>
        <td>${x.terminals.length ? x.terminals.map((t) => `<code>${esc(t)}</code>`).join(" ") : '<span class="ok-text">—</span>'}</td>
        <td class="n gauge">${x.awg === null ? "—" : `${x.awg}<small> AWG</small>`}</td>
        <td>${esc(SET_BY[x.limited_by] || x.limited_by)}</td>
        <td class="n">${range(x.terminal_range)}</td>
        <td class="n">${x.drop_pct === null ? "—" : fmt(x.drop_pct) + "%"}</td>
        <td><span class="status ${x.ok ? "pass" : "fail"}">${x.ok ? "OK" : "CHECK"}</span>${note}</td>
      </tr>`;
    }).join("")}</tbody></table>
    <p class="table-note">The gauge shown is the thinnest wire that carries the load, keeps the voltage drop within
      ${esc(num(state.config.max_drop_pct))}% and fits every listed terminal.</p>`;
}

function onResultsClick(e) {
  const go = e.target.closest("[data-goto]");
  if (go) { focusRow(Number(go.dataset.goto)); return; }
  const dl = e.target.closest("[data-dl]");
  if (dl && state.result?.ok) {
    const [suffix, type] = DOWNLOADS[dl.dataset.dl];
    download(state.title + suffix, state.result.files[dl.dataset.dl], type);
  }
}

// ---------------------------------------------------------------- wiring

function dropZone(card, onFile) {
  let depth = 0;
  card.addEventListener("dragenter", (e) => { e.preventDefault(); if (api) { depth++; card.classList.add("dragging"); } });
  card.addEventListener("dragleave", () => { depth = Math.max(0, depth - 1); if (!depth) card.classList.remove("dragging"); });
  card.addEventListener("dragover", (e) => e.preventDefault());
  card.addEventListener("drop", (e) => {
    e.preventDefault();
    depth = 0;
    card.classList.remove("dragging");
    const file = e.dataTransfer.files[0];
    if (api && file) onFile(file);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  $("#settings").addEventListener("input", onSettingInput);
  $("#reset-settings").addEventListener("click", () => {
    state.config = { ...INFO.defaults };
    buildSettings();
    analyze();
  });

  $("#editor").addEventListener("input", onEditorInput);
  $("#editor").addEventListener("click", onEditorClick);
  $("#add-row").addEventListener("click", addRow);
  $("#load-example").addEventListener("click", loadExample);
  $("#export-bom").addEventListener("click", () =>
    download(`${state.title}.csv`, api.rows_to_csv(JSON.stringify(state.rows)), "text/csv"));
  $("#file").addEventListener("change", async (e) => {
    const f = e.target.files[0];
    if (f) importCsv(await f.text(), f.name);
    e.target.value = "";
  });
  dropZone($("#editor-card"), async (f) => importCsv(await f.text(), f.name));

  $("#catalog-file").addEventListener("change", async (e) => {
    const f = e.target.files[0];
    if (f) setCatalog(await f.text(), f.name);
    e.target.value = "";
  });
  $("#catalog-reset").addEventListener("click", () => setCatalog(EXAMPLE_CATALOG_TEXT, "example catalog"));
  $("#catalog-export").addEventListener("click", () => download(
    state.catalogName.endsWith(".csv") ? state.catalogName : "terminals.csv", state.catalogText, "text/csv"));

  $("#results-card").addEventListener("click", onResultsClick);
  boot();
});
