/* Standalone demo behavior. DATA is injected by demo/build_demo.py. */
const STORAGE_KEY = "tcb_benchmark_demo_v1";
const DEMO_NAME = "Demo Linguist";
const ERROR_TYPES = ["Mistranslation", "Addition", "Omission"];
const SEVERITIES = ["Minor", "Major"];
const REASONS = [
  ["no_meaningful_error", "No meaningful error"],
  ["multiple_errors", "Multiple errors"],
  ["grammar_fluency_plausibility", "Grammar / fluency / plausibility problem"],
  ["incorrect_unclear_perturbation", "Incorrect or unclear perturbation"],
  ["other", "Other"],
];
const REASON_LABEL = Object.fromEntries(REASONS);
const EXPORT_COLUMNS = [
  "storage",
  "record_kind",
  "annotator_name",
  "language_pair",
  "batch_number",
  "batch_status",
  "segment_external_id",
  "sample_order",
  "candidate_id",
  "status",
  "source_text",
  "reference_text",
  "original_text",
  "edited_text",
  "original_error_type",
  "final_error_type",
  "original_severity",
  "final_severity",
  "rejection_reason",
  "comment",
  "notes",
  "updated_at",
];

const SEGMENT_INDEX = new Map(DATA.segments.map((segment) => [segment.id, segment]));

const ui = {
  saveMessage: "",
  saveClass: "save-ok",
  claimError: "",
  suggestError: "",
  suggestNotice: "",
  suggestOpen: false,
  guideOpen: false,
  suggestDraft: {},
  rejecting: {},
  rejectDraft: {},
  editing: {},
};

/*__SPAN_START__*/
function countOf(haystack, needle) {
  if (!needle) return 0;
  let count = 0;
  let index = 0;
  while (index <= haystack.length) {
    const found = haystack.indexOf(needle, index);
    if (found === -1) return count;
    count += 1;
    index = found + needle.length;
  }
  return count;
}

function findLongestMatch(a, b, alo, ahi, blo, bhi) {
  let bestLen = 0;
  let bestI = alo;
  let bestJ = blo;
  let prev = new Map();
  for (let i = alo; i < ahi; i += 1) {
    const next = new Map();
    for (let j = blo; j < bhi; j += 1) {
      if (a[i] !== b[j]) continue;
      const len = (prev.get(j - 1) || 0) + 1;
      next.set(j, len);
      if (len > bestLen) {
        bestLen = len;
        bestI = i - len + 1;
        bestJ = j - len + 1;
      }
    }
    prev = next;
  }
  return { i: bestI, j: bestJ, len: bestLen };
}

function matchingBlocks(a, b) {
  const blocks = [];
  const stack = [[0, a.length, 0, b.length]];
  while (stack.length) {
    const [alo, ahi, blo, bhi] = stack.pop();
    if (alo >= ahi || blo >= bhi) continue;
    const match = findLongestMatch(a, b, alo, ahi, blo, bhi);
    if (!match.len) continue;
    blocks.push(match);
    stack.push([alo, match.i, blo, match.j]);
    stack.push([match.i + match.len, ahi, match.j + match.len, bhi]);
  }
  blocks.push({ i: a.length, j: b.length, len: 0 });
  blocks.sort((left, right) => left.i - right.i || left.j - right.j);
  return blocks;
}

function getOpcodes(a, b) {
  const ops = [];
  let i = 0;
  let j = 0;
  matchingBlocks(a, b).forEach((match) => {
    if (i < match.i && j < match.j) ops.push(["replace", i, match.i, j, match.j]);
    else if (i < match.i) ops.push(["delete", i, match.i, j, j]);
    else if (j < match.j) ops.push(["insert", i, i, j, match.j]);
    if (match.len) ops.push(["equal", match.i, match.i + match.len, match.j, match.j + match.len]);
    i = match.i + match.len;
    j = match.j + match.len;
  });
  return ops;
}

function realignSpan(originalText, start, end, newText) {
  if (start == null || end == null) return [null, null, false];
  if (start < 0 || end < start || end > originalText.length) return [null, null, true];
  if (originalText === newText && end <= newText.length) return [start, end, false];
  const snippet = originalText.slice(start, end);
  if (snippet) {
    const count = countOf(newText, snippet);
    if (count === 1) {
      const idx = newText.indexOf(snippet);
      return [idx, idx + snippet.length, false];
    }
    if (count > 1) {
      const idx = newText.indexOf(snippet);
      return [idx, idx + snippet.length, true];
    }
  }
  let mappedStart = null;
  let mappedEnd = null;
  getOpcodes(originalText, newText).forEach(([tag, i1, i2, j1]) => {
    if (tag !== "equal") return;
    const overlapStart = Math.max(i1, start);
    const overlapEnd = Math.min(i2, end);
    if (overlapEnd <= overlapStart) return;
    const delta = overlapStart - i1;
    const chunkStart = j1 + delta;
    const chunkEnd = chunkStart + (overlapEnd - overlapStart);
    if (mappedStart == null) mappedStart = chunkStart;
    mappedEnd = chunkEnd;
  });
  if (mappedStart != null && mappedEnd != null && mappedEnd > mappedStart) {
    return [mappedStart, mappedEnd, true];
  }
  return [null, null, true];
}
/*__SPAN_END__*/

function h(tag, props, ...children) {
  const node = document.createElement(tag);
  if (props) {
    Object.entries(props).forEach(([key, value]) => {
      if (value == null) return;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = String(value);
      else if (typeof value === "function" && key.startsWith("on")) {
        node.addEventListener(key.slice(2).toLowerCase(), value);
      } else if (key === "disabled" || key === "checked" || key === "open" || key === "hidden" || key === "selected") {
        node[key] = Boolean(value);
      } else if (value !== false) {
        node.setAttribute(key, value === true ? "" : String(value));
      }
    });
  }
  children.forEach((child) => {
    if (child == null || child === false) return;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  });
  return node;
}

function freshState() {
  return {
    version: 1,
    batches: [],
    annotations: {},
    suggestions: [],
    screen: "dashboard",
    openBatchId: null,
    selectedBatchId: null,
    myOnly: true,
  };
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return freshState();
    const parsed = JSON.parse(raw);
    if (!parsed || parsed.version !== 1 || !Array.isArray(parsed.batches)) return freshState();
    parsed.annotations = parsed.annotations && typeof parsed.annotations === "object" ? parsed.annotations : {};
    parsed.suggestions = Array.isArray(parsed.suggestions) ? parsed.suggestions : [];
    parsed.myOnly = parsed.myOnly !== false;
    parsed.batches = parsed.batches.filter((batch) => {
      batch.segmentIds = (batch.segmentIds || []).filter((id) => SEGMENT_INDEX.has(id));
      const max = Math.max(batch.segmentIds.length, 1);
      batch.position = Math.min(Math.max(parseInt(batch.position, 10) || 1, 1), max);
      batch.owner = DEMO_NAME;
      return batch.segmentIds.length > 0;
    });
    if (!parsed.batches.some((batch) => batch.id === parsed.openBatchId)) {
      parsed.screen = "dashboard";
      parsed.openBatchId = null;
    }
    return parsed;
  } catch (err) {
    return freshState();
  }
}

let state = loadState();

function nowIso() {
  return new Date().toISOString();
}

function uid(prefix) {
  if (window.crypto && crypto.randomUUID) return prefix + crypto.randomUUID();
  return prefix + Date.now().toString(36) + Math.random().toString(36).slice(2);
}

function clip(text, max) {
  const flat = String(text || "").replace(/\s+/g, " ").trim();
  return flat.length > max ? flat.slice(0, max - 1) + "…" : flat;
}

function choice(value, allowed, fallback) {
  return allowed.includes(value) ? value : fallback;
}

function candidatesIn(batch) {
  const rows = [];
  batch.segmentIds.forEach((id) => {
    const segment = SEGMENT_INDEX.get(id);
    if (segment) rows.push(...segment.candidates);
  });
  return rows;
}

function isResolved(candidateId) {
  const ann = state.annotations[candidateId];
  return !!ann && (ann.status === "validated" || ann.status === "rejected");
}

function syncStatuses() {
  state.batches.forEach((batch) => {
    const cards = candidatesIn(batch);
    const resolved = cards.filter((candidate) => isResolved(candidate.id)).length;
    batch.status = cards.length && resolved === cards.length ? "completed" : "active";
  });
}

function persist() {
  syncStatuses();
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    return true;
  } catch (err) {
    ui.saveMessage = "This browser blocked local storage. Use Export Annotations to keep a copy.";
    ui.saveClass = "save-fail";
    return false;
  }
}

function clearFlash() {}

function flash() {}

function markSaved(andRender) {
  ui.saveMessage = "Saved in this browser only. The live database is unchanged.";
  ui.saveClass = "save-ok";
  const ok = persist();
  if (!ok) {
    const node = document.getElementById("saveStatus");
    if (node) {
      node.className = ui.saveClass;
      node.textContent = ui.saveMessage;
    }
    return;
  }
  if (andRender) render();
  else {
    const node = document.getElementById("saveStatus");
    if (node) {
      node.className = "save-ok";
      node.textContent = ui.saveMessage;
    }
  }
}

function ensureAnnotation(candidate) {
  if (!state.annotations[candidate.id]) {
    state.annotations[candidate.id] = {
      status: "draft",
      editedText: candidate.text,
      errorType: candidate.type,
      severity: candidate.severity,
      rejectionReason: null,
      comment: null,
      updatedAt: nowIso(),
    };
  }
  return state.annotations[candidate.id];
}

function viewModel(candidate) {
  const ann = state.annotations[candidate.id];
  const status = ann && (ann.status === "validated" || ann.status === "rejected") ? ann.status : "draft";
  return {
    ann,
    status,
    text: ann && typeof ann.editedText === "string" ? ann.editedText : candidate.text,
    errorType: choice(ann && ann.errorType, ERROR_TYPES, candidate.type),
    severity: choice(ann && ann.severity, SEVERITIES, candidate.severity),
    locked: status === "validated" || status === "rejected",
  };
}

function fillHighlight(container, text, start, end, approximate, strike) {
  container.replaceChildren();
  if (start == null || end == null || start < 0 || end > text.length || start >= end) {
    container.append(document.createTextNode(text));
    return;
  }
  container.append(document.createTextNode(text.slice(0, start)));
  let markClass = strike ? "err-span strike" : "err-span";
  if (approximate) markClass += " approx";
  container.append(h("span", { class: markClass, text: text.slice(start, end) }));
  container.append(document.createTextNode(text.slice(end)));
}

function regionOf(candidate, model, segment) {
  const ann = state.annotations[candidate.id];
  if (model.errorType === "Omission") {
    const base = model.text;
    const hasCustom = ann && typeof ann.omittedText === "string";
    const omitted = hasCustom
      ? ann.omittedText
      : (candidate.rs != null && candidate.re != null ? segment.reference.slice(candidate.rs, candidate.re) : "");
    let ip = hasCustom && ann.insertAt != null ? ann.insertAt : candidate.ip;
    if (ip == null || ip < 0 || ip > base.length) ip = base.length;
    return {
      text: base.slice(0, ip) + omitted + base.slice(ip),
      start: omitted ? ip : null,
      end: omitted ? ip + omitted.length : null,
      strike: true,
      approximate: false,
    };
  }
  const edited = model.text;
  if (ann && ann.spanStart != null && ann.spanEnd != null && ann.spanStart >= 0 && ann.spanEnd > ann.spanStart && ann.spanEnd <= edited.length) {
    return { text: edited, start: ann.spanStart, end: ann.spanEnd, strike: false, approximate: false };
  }
  let start = candidate.ts;
  let end = candidate.te;
  let approximate = false;
  if (edited !== candidate.text) {
    const realigned = realignSpan(candidate.text, candidate.ts, candidate.te, edited);
    start = realigned[0];
    end = realigned[1];
    approximate = !!realigned[2];
  }
  return { text: edited, start, end, strike: false, approximate };
}

function withTags(text, start, end) {
  if (start == null || end == null || start < 0 || end > text.length || start >= end) return text;
  return text.slice(0, start) + "<" + text.slice(start, end) + ">" + text.slice(end);
}

function parseTags(raw) {
  const open = raw.indexOf("<");
  const close = open === -1 ? -1 : raw.indexOf(">", open + 1);
  const nested = open === -1 ? -1 : raw.indexOf("<", open + 1);
  if (open === -1 || close === -1 || nested !== -1 || raw.slice(close + 1).includes(">")) {
    return { text: raw.replace(/[<>]/g, ""), start: null, end: null };
  }
  const before = raw.slice(0, open);
  const mid = raw.slice(open + 1, close);
  const after = raw.slice(close + 1);
  return { text: before + mid + after, start: before.length, end: before.length + mid.length };
}

function applyEditor(candidate, raw) {
  const parsed = parseTags(raw);
  const ann = ensureAnnotation(candidate);
  const type = ann.errorType || candidate.type;
  if (type === "Omission") {
    if (parsed.start == null || parsed.end === parsed.start) {
      ann.editedText = parsed.text;
      ann.omittedText = "";
      ann.insertAt = 0;
    } else {
      ann.omittedText = parsed.text.slice(parsed.start, parsed.end);
      ann.insertAt = parsed.start;
      ann.editedText = parsed.text.slice(0, parsed.start) + parsed.text.slice(parsed.end);
    }
    ann.spanStart = null;
    ann.spanEnd = null;
  } else {
    ann.editedText = parsed.text;
    ann.spanStart = parsed.start;
    ann.spanEnd = parsed.end === parsed.start ? null : parsed.end;
    ann.omittedText = null;
    ann.insertAt = null;
  }
  ann.updatedAt = nowIso();
}

function updatePreview(slot, candidate, model, segment) {
  slot.replaceChildren();
  const region = regionOf(candidate, model, segment);
  const row = h("div", { class: "span-preview sentence" });
  fillHighlight(row, region.text, region.start, region.end, region.approximate, region.strike);
  slot.append(row);
  if (region.start == null && model.text !== candidate.text && !region.strike) {
    slot.append(h("div", { class: "span-note", text: "Highlight unavailable after the edit (original span metadata was kept)." }));
  } else if (region.approximate) {
    slot.append(h("div", { class: "span-note", text: "Approximate highlight after editing — original offsets were preserved." }));
  }
}

function remainingSegments() {
  const taken = new Set(state.batches.flatMap((batch) => batch.segmentIds));
  return DATA.segments.filter((segment) => !taken.has(segment.id));
}

function currentBatch() {
  return state.batches.find((batch) => batch.id === state.openBatchId) || null;
}

function statusLabel(status) {
  if (status === "active") return "In progress";
  if (status === "completed") return "Completed";
  return status;
}

function batchStats(batch) {
  const cards = candidatesIn(batch);
  const resolved = cards.filter((candidate) => isResolved(candidate.id)).length;
  return { resolved, total: cards.length };
}

function guide() {
  const details = h("details", { class: "guide", open: ui.guideOpen },
    h("summary", { text: "How To Guide" }),
    h("h3", { text: "This demo" }),
    h("p", { text: "You are looking at a clickable preview of the Translation Commons Benchmark Builder. There is no login. Validate, reject, edit, and suggest as you would in the live tool. Everything you change is stored in this browser only. Reset Demo erases that local copy. Export Annotations downloads a CSV to this computer. The live database is unchanged." }),
    h("h3", { text: "Annotation rules" }),
    h("p", { text: "You are checking synthetic translation errors. Each card is one generated candidate that should contain exactly one intended error." }),
    h("p", { text: "Validate only when all of the following are true:" }),
    h("ol", {},
      h("li", { text: "The target sentence contains exactly one intended error." }),
      h("li", { text: "That error matches the selected type (Mistranslation / Addition / Omission) and severity (Minor / Major)." }),
      h("li", { text: "There are no unrelated grammatical, fluency, or plausibility problems." })
    ),
    h("p", { text: "You may edit the sentence and the labels before validating." }),
    h("p", { text: "Reject a candidate when:" }),
    h("ul", {},
      h("li", { text: "There is no meaningful error." }),
      h("li", { text: "There are multiple errors." }),
      h("li", { text: "Grammar, fluency, or plausibility is broken in a way that is not the intended error." }),
      h("li", { text: "The perturbation is incorrect or unclear." }),
      h("li", { text: "Other (add a comment)." })
    ),
    h("h3", { text: "Interface" }),
    h("ul", {},
      h("li", { text: "The blue panel is the source and the reference. Both are read-only." }),
      h("li", { text: "Each card shows the suggested error. Underlines and strikethroughs are a visual aid only. Use the pen to edit; angle brackets mark the error region and are not part of the sentence." }),
      h("li", { text: "(+) Suggest an additional error is optional and is stored separately from generated candidates." }),
      h("li", { text: "Back and Next keep saved work. You may skip incomplete cards and return later." }),
      h("li", { text: "Work is saved in this browser. Use Save to confirm a local save. Nothing is sent to a server." }),
      h("li", { text: "A segment is resolved when every generated candidate is validated or rejected." })
    ),
    h("h3", { text: "Independence" }),
    h("p", { text: "Do not discuss items with other annotators until you have finished your own annotations. Overlap items exist so agreement can be measured later." })
  );
  details.addEventListener("toggle", () => { ui.guideOpen = details.open; });
  return details;
}

function renderHeader(lines) {
  const box = h("div", { class: "userbox" });
  lines.forEach((line, index) => {
    if (index) box.append(h("br"));
    box.append(document.createTextNode(line));
  });
  return h("header", { class: "app-header" },
    h("div", {},
      h("h1", {}, "Translation Commons Benchmark Builder ", h("span", { class: "badge", text: "Demo" })),
      guide()
    ),
    box
  );
}

const DUMMY_BATCHES = [
  { pair: "English → French", batch: "1", size: "40", status: "Not started", owner: "—", progress: "0 / 40", claimable: true },
  { pair: "English → Portuguese", batch: "1", size: "36", status: "WIP", owner: "Miguel Santos", progress: "11 / 36", claimable: false },
  { pair: "English → German", batch: "1", size: "40", status: "Not started", owner: "—", progress: "0 / 40", claimable: true },
  { pair: "English → Italian", batch: "1", size: "32", status: "Completed", owner: "Giulia Romano", progress: "32 / 32", claimable: false },
  { pair: "English → Dutch", batch: "1", size: "28", status: "Not started", owner: "—", progress: "0 / 28", claimable: true },
  { pair: "English → Polish", batch: "1", size: "30", status: "WIP", owner: "Anna Kowalska", progress: "7 / 30", claimable: false },
  { pair: "English → Chinese", batch: "1", size: "45", status: "Not started", owner: "—", progress: "0 / 45", claimable: true },
  { pair: "English → Japanese", batch: "1", size: "38", status: "Not started", owner: "—", progress: "0 / 38", claimable: true },
  { pair: "English → Korean", batch: "1", size: "34", status: "WIP", owner: "Min-jun Park", progress: "16 / 34", claimable: false },
  { pair: "English → Arabic", batch: "1", size: "42", status: "Not started", owner: "—", progress: "0 / 42", claimable: true },
  { pair: "English → Hindi", batch: "1", size: "30", status: "Completed", owner: "Priya Shah", progress: "30 / 30", claimable: false },
];

function resolvedSegments(batch) {
  let resolved = 0;
  batch.segmentIds.forEach((id) => {
    const segment = SEGMENT_INDEX.get(id);
    if (segment && segment.candidates.length && segment.candidates.every((candidate) => isResolved(candidate.id))) {
      resolved += 1;
    }
  });
  return resolved;
}

function statusPill(status) {
  const kind = status === "WIP" ? "pill-wip" : status === "Completed" ? "pill-done" : "pill-new";
  return h("span", { class: "pill " + kind, text: status });
}

function spanishCatalogRow() {
  const mine = state.batches.find((batch) => batch.segmentIds && batch.segmentIds.length);
  if (!mine) {
    return {
      pair: "English → Spanish",
      batch: "2",
      size: String(DATA.segments.length),
      status: "Not started",
      owner: "—",
      progress: "0 / " + DATA.segments.length,
      action: "claim-spanish",
    };
  }
  const total = mine.segmentIds.length;
  const resolved = resolvedSegments(mine);
  const done = mine.status === "completed" || (total > 0 && resolved === total);
  return {
    pair: "English → Spanish",
    batch: "2",
    size: String(total),
    status: done ? "Completed" : "WIP",
    owner: DEMO_NAME,
    progress: resolved + " / " + total,
    action: done ? "view" : "resume",
    id: mine.id,
  };
}

function rowAction(row) {
  if (row.action === "claim-spanish") {
    return h("button", { class: "primary tiny claim", type: "button", text: "Claim This Batch", onclick: claimBatch });
  }
  if (row.action === "claim-dummy") {
    return h("button", {
      class: "primary tiny claim",
      type: "button",
      text: "Claim This Batch",
      onclick: () => {
        ui.claimError = "Only the English → Spanish sample includes segments in this demo.";
        render();
      },
    });
  }
  if (row.action === "resume" || row.action === "view") {
    return h("button", {
      class: "secondary tiny",
      type: "button",
      text: row.action === "resume" ? "Resume" : "View",
      onclick: () => openBatch(row.id),
    });
  }
  return document.createTextNode("—");
}

function renderDashboard() {
  const root = h("div");
  root.append(renderHeader([DEMO_NAME, "Demo session"]));
  root.append(h("h2", { text: "Batches" }));
  if (ui.claimError) root.append(h("div", { class: "alert warn", role: "alert", text: ui.claimError }));

  const rows = [
    {
      pair: "English → Spanish",
      batch: "1",
      size: String(DATA.segments.length),
      status: "WIP",
      owner: "Elena Vargas",
      progress: "18 / " + DATA.segments.length,
      action: "none",
    },
    spanishCatalogRow(),
    ...DUMMY_BATCHES.map((row) => ({
      ...row,
      action: row.claimable ? "claim-dummy" : "none",
    })),
  ];

  const table = h("table");
  table.append(h("thead", {}, h("tr", {},
    ...["Language pair", "Batch", "Size", "Status", "Owner", "Progress", "Action"].map((label) => h("th", { scope: "col", text: label }))
  )));
  const body = h("tbody");
  rows.forEach((row) => {
    body.append(h("tr", {},
      h("td", { text: row.pair }),
      h("td", { text: row.batch }),
      h("td", { text: row.size }),
      h("td", {}, statusPill(row.status)),
      h("td", { text: row.owner }),
      h("td", { text: row.progress }),
      h("td", {}, rowAction(row))
    ));
  });
  table.append(body);
  root.append(h("div", { class: "table-wrap" }, table));
  return root;
}

function claimBatch() {
  ui.claimError = "";
  if (state.batches.some((batch) => batch.status === "active")) {
    ui.claimError = "You already have an active batch.";
    render();
    return;
  }
  const available = remainingSegments();
  if (!available.length) {
    ui.claimError = "No eligible segments available to claim for this language pair.";
    render();
    return;
  }
  const chosen = available.slice(0, DATA.batchSize);
  const number = state.batches.reduce((max, batch) => Math.max(max, batch.number || 0), 0) + 1;
  const batch = {
    id: "batch-" + number,
    number,
    status: "active",
    owner: DEMO_NAME,
    segmentIds: chosen.map((segment) => segment.id),
    position: 1,
    claimedAt: nowIso(),
  };
  state.batches.unshift(batch);
  state.selectedBatchId = batch.id;
  state.openBatchId = batch.id;
  state.screen = "workspace";
  ui.saveMessage = "";
  persist();
  render();
  window.scrollTo(0, 0);
}

function openBatch(id) {
  const batch = state.batches.find((item) => item.id === id);
  if (!batch) return;
  state.selectedBatchId = id;
  state.openBatchId = id;
  state.screen = "workspace";
  ui.suggestError = "";
  ui.suggestNotice = "";
  persist();
  render();
  window.scrollTo(0, 0);
}

function goDashboard() {
  flushEditors();
  state.screen = "dashboard";
  ui.suggestError = "";
  persist();
  render();
  window.scrollTo(0, 0);
}

function renderWorkspace() {
  const batch = currentBatch();
  const root = h("div");
  if (!batch) return root;
  const total = batch.segmentIds.length;
  batch.position = Math.min(Math.max(batch.position || 1, 1), Math.max(total, 1));
  const segment = SEGMENT_INDEX.get(batch.segmentIds[batch.position - 1]);
  if (!segment) {
    root.append(renderHeader(["Linguist: " + DEMO_NAME]));
    root.append(h("p", { text: "This segment is missing from the embedded pilot." }));
    root.append(h("button", { class: "secondary", type: "button", text: "← Batches", onclick: goDashboard }));
    return root;
  }
  const counts = { validated: 0, rejected: 0, incomplete: 0 };
  candidatesIn(batch).forEach((candidate) => {
    const status = viewModel(candidate).status;
    if (status === "validated") counts.validated += 1;
    else if (status === "rejected") counts.rejected += 1;
    else counts.incomplete += 1;
  });

  root.append(renderHeader([
    "Target: " + DATA.targetLabel,
    "Batch #: " + batch.number,
    "Linguist: " + DEMO_NAME,
  ]));
  root.append(h("button", { class: "linkish", type: "button", text: "← Batches", onclick: goDashboard }));
  root.append(h("p", { class: "counts", text: "Validated " + counts.validated + " · Rejected " + counts.rejected + " · Incomplete " + counts.incomplete }));
  root.append(h("div", { id: "saveStatus", class: ui.saveClass, role: "status", "aria-live": "polite", text: ui.saveMessage || "" }));

  const banner = h("div", { class: "segment-banner" });
  banner.append(h("div", { class: "progress", text: "Segment " + batch.position + " / " + total }));
  banner.append(h("div", { class: "k", text: "Source" }));
  banner.append(h("div", { class: "line sentence", lang: "en", text: segment.source }));
  banner.append(h("div", { class: "k", text: "Reference" }));
  banner.append(h("div", { class: "line sentence", lang: "es", text: segment.reference }));
  root.append(banner);
  if (segment.candidates.length && segment.candidates.every((candidate) => isResolved(candidate.id))) {
    root.append(h("p", { class: "status-validated", text: "This segment is resolved." }));
  }
  if (batch.status === "completed") {
    root.append(h("div", { class: "alert ok", text: "This batch is complete. Every generated candidate is validated or rejected. Suggestions were optional." }));
  }

  segment.candidates.forEach((candidate) => root.append(renderCard(batch, segment, candidate)));
  root.append(renderSuggestions(batch, segment));

  const jump = h("select", { id: "jumpSegment", "aria-label": "Jump to segment" });
  batch.segmentIds.forEach((id, index) => {
    const item = SEGMENT_INDEX.get(id);
    const option = h("option", { value: String(index + 1), text: (index + 1) + ". " + clip(item.source, 78) });
    if (index + 1 === batch.position) option.selected = true;
    jump.append(option);
  });
  jump.addEventListener("change", () => {
    flushEditors();
    batch.position = parseInt(jump.value, 10);
    ui.suggestError = "";
    ui.suggestNotice = "";
    persist();
    render();
    window.scrollTo(0, 0);
  });
  root.append(h("label", { class: "field" }, h("span", { text: "Jump to segment" }), jump));

  root.append(h("div", { class: "nav" },
    h("button", {
      class: "secondary",
      type: "button",
      text: "← Back",
      disabled: batch.position <= 1,
      onclick: () => move(batch, -1),
    }),
    h("button", { class: "secondary", type: "button", text: "Save", onclick: () => { flushEditors(); markSaved(false); } }),
    h("button", {
      class: "secondary",
      type: "button",
      text: "Next →",
      disabled: batch.position >= total,
      onclick: () => move(batch, 1),
    })
  ));
  return root;
}

function move(batch, delta) {
  flushEditors();
  const total = batch.segmentIds.length;
  batch.position = Math.min(total, Math.max(1, batch.position + delta));
  ui.suggestError = "";
  ui.suggestNotice = "";
  persist();
  render();
  window.scrollTo(0, 0);
}

function renderCard(batch, segment, candidate) {
  const model = viewModel(candidate);
  const card = h("article", { class: "card", "data-cid": candidate.id });
  const editing = !!ui.editing[candidate.id] && !model.locked;
  const severity = h("select", { class: "pill", "aria-label": "Severity", disabled: model.locked });
  SEVERITIES.forEach((value) => severity.append(h("option", { value, text: value })));
  severity.value = model.severity;
  severity.addEventListener("change", () => {
    if (model.locked) return;
    const ann = ensureAnnotation(candidate);
    ann.severity = severity.value;
    ann.updatedAt = nowIso();
    markSaved(false);
  });
  const errorType = h("select", { class: "pill", "aria-label": "Error type", disabled: model.locked });
  ERROR_TYPES.forEach((value) => errorType.append(h("option", { value, text: value })));
  errorType.value = model.errorType;
  errorType.addEventListener("change", () => {
    if (model.locked) return;
    const ann = ensureAnnotation(candidate);
    ann.errorType = errorType.value;
    ann.updatedAt = nowIso();
    if (ui.editing[candidate.id]) {
      const ta = document.getElementById("text-" + candidate.id);
      if (ta) applyEditor(candidate, ta.value);
      markSaved(false);
      render();
      return;
    }
    markSaved(false);
    updatePreview(preview, candidate, { text: ann.editedText, errorType: ann.errorType }, segment);
  });
  const action = model.locked
    ? h("button", { class: "secondary", type: "button", text: "Reopen", onclick: () => reopenCard(candidate) })
    : h("button", { class: "primary", type: "button", text: "Validate ✓", onclick: () => validateCard(candidate) });
  const lead = h("div", { class: "pills" }, severity, errorType);
  if (model.status !== "draft") {
    lead.append(h("span", { class: "card-state", text: model.status.charAt(0).toUpperCase() + model.status.slice(1) }));
  }
  card.append(h("div", { class: "card-top" },
    lead,
    h("div", { class: "card-actions" },
      h("button", {
        class: editing ? "icon-btn active" : "icon-btn",
        type: "button",
        text: "✏️",
        title: editing ? "Finish editing" : "Edit",
        "aria-label": editing ? "Finish editing" : "Edit",
        disabled: model.locked,
        onclick: () => toggleEdit(candidate),
      }),
      h("button", {
        class: "reject",
        type: "button",
        text: "×",
        title: "Reject",
        "aria-label": "Reject",
        disabled: model.locked,
        onclick: () => startReject(candidate),
      })
    )
  ));
  const preview = h("div", { class: "preview-slot" });
  const region = regionOf(candidate, model, segment);
  if (editing) {
    const textarea = h("textarea", {
      id: "text-" + candidate.id,
      class: "sentence",
      "aria-label": "Edit target. Angle brackets mark the error region.",
      lang: "es",
    });
    textarea.value = withTags(region.text, region.start, region.end);
    card.append(textarea);
    card.append(h("p", { class: "caption", text: model.errorType === "Omission"
      ? "Text inside <> is the omitted span. It is shown with a strikethrough and is not part of the sentence."
      : "Angle brackets mark the error region. They are not part of the sentence." }));
  } else {
    updatePreview(preview, candidate, model, segment);
    card.append(preview);
  }
  card.append(h("div", { class: "card-foot" }, action));

  if (ui.rejecting[candidate.id] && !model.locked) {
    const draft = rejectDraft(candidate);
    const reason = h("select", { id: "rej-reason-" + candidate.id, "aria-label": "Rejection reason" });
    REASONS.forEach(([code, label]) => reason.append(h("option", { value: code, text: label })));
    reason.value = draft.reason;
    reason.addEventListener("change", () => { draft.reason = reason.value; });
    const comment = h("input", { type: "text", "aria-label": "Comment (optional)", value: draft.comment });
    comment.value = draft.comment;
    comment.addEventListener("input", () => { draft.comment = comment.value; });
    card.append(h("label", { class: "field" }, h("span", { text: "Rejection reason" }), reason));
    card.append(h("label", { class: "field" }, h("span", { text: "Comment (optional)" }), comment));
    card.append(h("div", { class: "split" },
      h("button", { class: "primary", type: "button", text: "Confirm reject", onclick: () => confirmReject(candidate) }),
      h("button", { class: "secondary", type: "button", text: "Cancel", onclick: () => cancelReject(candidate) })
    ));
  }
  if (model.ann && model.ann.rejectionReason && model.status === "rejected") {
    const label = REASON_LABEL[model.ann.rejectionReason] || model.ann.rejectionReason;
    card.append(h("p", { class: "caption", text: "Rejection: " + label }));
  }
  return card;
}

function rejectDraft(candidate) {
  if (!ui.rejectDraft[candidate.id]) {
    const ann = state.annotations[candidate.id];
    ui.rejectDraft[candidate.id] = {
      reason: choice(ann && ann.rejectionReason, REASONS.map((item) => item[0]), REASONS[0][0]),
      comment: (ann && ann.comment) || "",
    };
  }
  return ui.rejectDraft[candidate.id];
}

function startReject(candidate) {
  const model = viewModel(candidate);
  if (model.locked) return;
  ui.rejecting[candidate.id] = true;
  rejectDraft(candidate);
  render();
  const focus = document.getElementById("rej-reason-" + candidate.id);
  if (focus) focus.focus();
}

function cancelReject(candidate) {
  delete ui.rejecting[candidate.id];
  render();
}

function flushEditors() {
  Object.keys(ui.editing).forEach((id) => {
    const textarea = document.getElementById("text-" + id);
    if (!textarea) return;
    let candidate = null;
    DATA.segments.some((segment) => {
      candidate = segment.candidates.find((item) => item.id === id) || null;
      return !!candidate;
    });
    if (candidate) applyEditor(candidate, textarea.value);
  });
}

function toggleEdit(candidate) {
  const model = viewModel(candidate);
  if (model.locked) return;
  if (ui.editing[candidate.id]) {
    const textarea = document.getElementById("text-" + candidate.id);
    if (textarea) applyEditor(candidate, textarea.value);
    delete ui.editing[candidate.id];
    markSaved(true);
    return;
  }
  ui.editing[candidate.id] = true;
  render();
  const textarea = document.getElementById("text-" + candidate.id);
  if (textarea) textarea.focus();
}

function confirmReject(candidate) {
  const draft = rejectDraft(candidate);
  const ann = ensureAnnotation(candidate);
  const textarea = document.getElementById("text-" + candidate.id);
  if (textarea) applyEditor(candidate, textarea.value);
  delete ui.editing[candidate.id];
  ann.status = "rejected";
  ann.rejectionReason = draft.reason;
  ann.comment = draft.comment ? draft.comment : null;
  ann.updatedAt = nowIso();
  delete ui.rejecting[candidate.id];
  markSaved(true);
}

function validateCard(candidate) {
  const ann = ensureAnnotation(candidate);
  const textarea = document.getElementById("text-" + candidate.id);
  if (textarea) applyEditor(candidate, textarea.value);
  delete ui.editing[candidate.id];
  ann.status = "validated";
  ann.rejectionReason = null;
  ann.updatedAt = nowIso();
  delete ui.rejecting[candidate.id];
  markSaved(true);
}

function reopenCard(candidate) {
  const ann = ensureAnnotation(candidate);
  ann.status = "draft";
  ann.rejectionReason = null;
  ann.updatedAt = nowIso();
  markSaved(true);
}

function suggestionDraft(segmentId) {
  if (!ui.suggestDraft[segmentId]) {
    ui.suggestDraft[segmentId] = { text: "", errorType: ERROR_TYPES[0], severity: SEVERITIES[0], notes: "" };
  }
  return ui.suggestDraft[segmentId];
}

function renderSuggestions(batch, segment) {
  const draft = suggestionDraft(segment.id);
  const text = h("textarea", { "aria-label": "Suggested target sentence", lang: "es" });
  text.value = draft.text;
  text.addEventListener("input", () => { draft.text = text.value; });
  const type = h("select", { "aria-label": "Error type" });
  ERROR_TYPES.forEach((value) => type.append(h("option", { value, text: value })));
  type.value = draft.errorType;
  type.addEventListener("change", () => { draft.errorType = type.value; });
  const severity = h("select", { "aria-label": "Severity" });
  SEVERITIES.forEach((value) => severity.append(h("option", { value, text: value })));
  severity.value = draft.severity;
  severity.addEventListener("change", () => { draft.severity = severity.value; });
  const notes = h("input", { type: "text", "aria-label": "Notes (optional)" });
  notes.value = draft.notes;
  notes.addEventListener("input", () => { draft.notes = notes.value; });
  const body = [
    h("label", { class: "field" }, h("span", { text: "Suggested target sentence" }), text),
    h("div", { class: "split" },
      h("label", { class: "field" }, h("span", { text: "Error type" }), type),
      h("label", { class: "field" }, h("span", { text: "Severity" }), severity)
    ),
    h("label", { class: "field" }, h("span", { text: "Notes (optional)" }), notes),
  ];
  if (ui.suggestError) body.push(h("div", { class: "alert warn", text: ui.suggestError }));
  if (ui.suggestNotice) body.push(h("div", { class: "alert ok", text: ui.suggestNotice }));
  body.push(h("button", { class: "primary", type: "button", text: "Submit suggestion", onclick: () => submitSuggestion(segment, batch) }));
  const mine = state.suggestions.filter((item) => item.segmentId === segment.id && item.batchId === batch.id);
  mine.forEach((item) => {
    body.push(h("div", { class: "suggest-item" },
      h("p", { class: "caption", text: "Your suggestion (" + item.errorType + ", " + item.severity + ")" + (item.notes ? " — " + item.notes : "") }),
      h("p", { lang: "es", text: item.text })
    ));
  });
  const details = h("details", { class: "guide suggest", open: ui.suggestOpen },
    h("summary", { text: "(+) Suggest an additional error" }),
    ...body
  );
  details.addEventListener("toggle", () => { ui.suggestOpen = details.open; });
  return details;
}

function submitSuggestion(segment, batch) {
  const draft = suggestionDraft(segment.id);
  ui.suggestOpen = true;
  if (!draft.text.trim()) {
    ui.suggestError = "Enter a suggested target sentence.";
    ui.suggestNotice = "";
    render();
    return;
  }
  state.suggestions.push({
    id: uid("sugg-"),
    segmentId: segment.id,
    batchId: batch.id,
    text: draft.text.trim(),
    errorType: choice(draft.errorType, ERROR_TYPES, ERROR_TYPES[0]),
    severity: choice(draft.severity, SEVERITIES, SEVERITIES[0]),
    notes: (draft.notes || "").trim(),
    createdAt: nowIso(),
  });
  draft.text = "";
  draft.notes = "";
  ui.suggestError = "";
  ui.suggestNotice = "Suggestion saved in this browser only. The live database is unchanged.";
  markSaved(true);
}

function csvEscape(value) {
  if (value == null) return "";
  let text = String(value);
  if (/^[=+\-@]/.test(text)) text = "'" + text;
  if (/[",\r\n]/.test(text)) return '"' + text.replace(/"/g, '""') + '"';
  return text;
}

function exportRows() {
  const rows = [];
  state.batches.forEach((batch) => {
    batch.segmentIds.forEach((segmentId) => {
      const segment = SEGMENT_INDEX.get(segmentId);
      if (!segment) return;
      segment.candidates.forEach((candidate) => {
        const ann = state.annotations[candidate.id];
        rows.push({
          storage: "local-browser-demo",
          record_kind: "annotation",
          annotator_name: DEMO_NAME,
          language_pair: DATA.pairLabel,
          batch_number: batch.number,
          batch_status: statusLabel(batch.status),
          segment_external_id: segment.id,
          sample_order: segment.order,
          candidate_id: candidate.id,
          status: ann && ann.status ? ann.status : "draft",
          source_text: segment.source,
          reference_text: segment.reference,
          original_text: candidate.text,
          edited_text: ann && typeof ann.editedText === "string" ? ann.editedText : candidate.text,
          original_error_type: candidate.type,
          final_error_type: ann && ann.errorType ? ann.errorType : candidate.type,
          original_severity: candidate.severity,
          final_severity: ann && ann.severity ? ann.severity : candidate.severity,
          rejection_reason: ann && ann.rejectionReason ? (REASON_LABEL[ann.rejectionReason] || ann.rejectionReason) : "",
          comment: ann && ann.comment ? ann.comment : "",
          notes: "",
          updated_at: ann && ann.updatedAt ? ann.updatedAt : "",
        });
      });
    });
  });
  state.suggestions.forEach((item) => {
    const segment = SEGMENT_INDEX.get(item.segmentId);
    const batch = state.batches.find((entry) => entry.id === item.batchId);
    rows.push({
      storage: "local-browser-demo",
      record_kind: "suggestion",
      annotator_name: DEMO_NAME,
      language_pair: DATA.pairLabel,
      batch_number: batch ? batch.number : "",
      batch_status: batch ? statusLabel(batch.status) : "",
      segment_external_id: item.segmentId,
      sample_order: segment ? segment.order : "",
      candidate_id: "",
      status: "suggestion",
      source_text: segment ? segment.source : "",
      reference_text: segment ? segment.reference : "",
      original_text: "",
      edited_text: item.text,
      original_error_type: "",
      final_error_type: item.errorType,
      original_severity: "",
      final_severity: item.severity,
      rejection_reason: "",
      comment: "",
      notes: item.notes || "",
      updated_at: item.createdAt || "",
    });
  });
  return rows;
}

function exportAnnotations() {
  const rows = exportRows();
  const lines = [EXPORT_COLUMNS.join(",")];
  rows.forEach((row) => {
    lines.push(EXPORT_COLUMNS.map((column) => csvEscape(row[column])).join(","));
  });
  const blob = new Blob(["\uFEFF" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = h("a", { href: url, download: "tcb-demo-annotations.csv" });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  if (!rows.length) {
    flash("Downloaded tcb-demo-annotations.csv with headers only. Claim a batch to include annotations. The file stayed on this computer.");
  } else {
    flash("Downloaded tcb-demo-annotations.csv (" + rows.length + " rows) to this computer. The live database is unchanged.");
  }
}

function resetDemo() {
  const ok = window.confirm("Reset the demo? Annotations stored in this browser will be erased. The embedded pilot sentences stay, and the live database is unchanged.");
  if (!ok) return;
  try { localStorage.removeItem(STORAGE_KEY); } catch (err) { /* storage may be blocked */ }
  state = freshState();
  ui.saveMessage = "";
  ui.saveClass = "save-ok";
  ui.claimError = "";
  ui.suggestError = "";
  ui.suggestNotice = "";
  ui.suggestOpen = false;
  ui.suggestDraft = {};
  ui.rejecting = {};
  ui.rejectDraft = {};
  ui.editing = {};
  render();
  window.scrollTo(0, 0);
}

function render() {
  clearFlash();
  syncStatuses();
  const app = document.getElementById("app");
  const batch = currentBatch();
  if (state.screen === "workspace" && batch) app.replaceChildren(renderWorkspace());
  else {
    state.screen = "dashboard";
    app.replaceChildren(renderDashboard());
  }
}

document.getElementById("resetBtn").addEventListener("click", resetDemo);
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    if (state.screen === "workspace") {
      flushEditors();
      markSaved(false);
    }
  }
});
render();
