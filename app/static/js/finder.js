import { etime, localtime, mdate } from "./lib/format.js";

// Finder page behaviour. Only wires events and swaps server-rendered HTML; no trading math here.
const $ = (id) => document.getElementById(id);
const results = $("results");
const banner = $("banner");

function showUpdated(iso) {
  const el = document.getElementById("updated-at");
  if (el) el.textContent = iso ? "Updated " + localtime(iso) : "";
}
showUpdated(document.getElementById("updated-at")?.dataset.iso);

// The Weekly Comparison starts collapsed and stays however the user leaves it (remembered in this browser).
// It only pulls while open; opening it fires the toggle event, which loads it.
// The strike the Weekly Comparison uses: the box if something is typed there, else the starred row's.
window.compareVals = () => {
  const typed = (document.getElementById("compare-strike") || {}).value || "";
  const starred = (document.querySelector("#calendars tr.strike-row[data-starred]") || { dataset: {} }).dataset.strike || "";
  return typed ? { strike: typed, override: "1" } : { strike: starred, override: "" };
};
const strikeBox = document.getElementById("compare-strike"), strikeReset = document.getElementById("compare-strike-reset");
if (strikeBox) {
  strikeBox.addEventListener("input", () => strikeReset.classList.toggle("hidden", !strikeBox.value));
  strikeReset.addEventListener("click", () => {
    strikeBox.value = ""; strikeReset.classList.add("hidden");
    strikeBox.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

const cmpBox = document.getElementById("compare-box");
if (cmpBox) {
  try { if (localStorage.getItem("compareOpen") === "1") cmpBox.open = true; } catch (e) { /* storage unavailable */ }
  cmpBox.addEventListener("toggle", () => {
    try { localStorage.setItem("compareOpen", cmpBox.open ? "1" : "0"); } catch (e) { /* storage unavailable */ }
  });
}

function showBanner(msg) { banner.textContent = msg; banner.classList.remove("hidden"); }
function clearBanner() { banner.classList.add("hidden"); banner.textContent = ""; }
const snapshotId = () => (results.dataset.snapshotId || document.getElementById("snapshot-marker")?.dataset.snapshotId || "");

async function errorText(res) {
  try { const j = await res.json(); return j.detail || j.message || res.statusText; } catch { return res.statusText; }
}

function currentFilters() {
  const checked = (name) => [...document.querySelectorAll(`input[name=${name}]:checked`)].map((e) => e.value);
  return {
    dte_min: Number($("dte-min").value), dte_max: Number($("dte-max").value),
    widths: checked("widths").map(Number), strike_sets: checked("strike_sets"),
    size_mode: $("size-mode").value, size_value: Number($("size-value").value),
  };
}

let saveTimer;
function saveFilters() {
  const f = currentFilters();
  $("dte-label").textContent = `${f.dte_min}–${f.dte_max}`;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    fetch("/api/settings/finder_filters", {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ value: f }),
    }).catch(() => {});
  }, 300);
}

let busy = false, again = false, autoTimer;

// A changed filter refreshes by itself (after a short pause, so dragging a slider is one pull, not many).
function filtersProblem(f) {
  if (f.dte_min > f.dte_max) return "The shortest short-leg DTE is above the longest one";
  if (!f.widths.length) return "Pick at least one width";
  if (!f.strike_sets.length) return "Pick at least one strike set";
  if (!(f.size_value >= 1)) return "Size must be at least 1";
  return null;
}
function scheduleRefresh() {
  clearTimeout(autoTimer);
  autoTimer = setTimeout(() => {
    const problem = filtersProblem(currentFilters());
    if (problem) { showBanner(problem); return; }
    clearBanner();
    refresh();
  }, 700);
}

// What the user has open, so an automatic refresh puts them back where they were.
function currentSelection() {
  const pair = document.querySelector("tr.pair-row.sel"), strike = document.querySelector("tr.strike-row.sel");
  const sortName = $("calendars-table")?.dataset.sortName, desc = $("calendars-table")?.dataset.sortDesc === "true";
  const panelBox = document.getElementById("risk-box"), panelCal = document.getElementById("calendar-panel");
  const q = {};
  if (pair) q.open = pair.dataset.key;
  else if (document.querySelector("tr.pair-row")) q.open = "-";            // the user collapsed the table
  if (!pair && panelBox) q.panel = `${panelBox.dataset.short}|${panelBox.dataset.long}`;
  const strikeVal = strike ? strike.dataset.strike : (panelCal ? panelCal.dataset.strike : "");
  if (strikeVal) q.strike = strikeVal;
  if (sortName) q.sort = (desc ? "-" : "+") + sortName;
  return q;
}

async function refresh(keepSelection = false) {
  if (keepSelection !== true) keepSelection = false;
  if (busy) { again = true; return; }          // a pull is running: run once more with the newest filters
  busy = true; again = false;
  const btn = $("refresh");
  btn.disabled = true; btn.textContent = "Refreshing…"; clearBanner();
  try {
    const res = await fetch("/api/finder/refresh", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(currentFilters()),
    });
    if (!res.ok) { showBanner(await errorText(res)); return; }
    const snap = await res.json();
    results.dataset.snapshotId = snap.snapshot_id;
    const keep = keepSelection ? currentSelection() : {};
    const q = new URLSearchParams({ snapshot_id: snap.snapshot_id, ...keep });
    await htmx.ajax("GET", `/partials/results?${q}`,
                    { target: "#results", swap: "innerHTML" });
    const when = etime(snap.result.time);          // the server's timestamp is already market time
    const last = $("last-refresh");
    if (last) last.textContent = when;
    showUpdated(snap.result.time);
  } catch (e) {
    showBanner("Could not reach the server: " + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "↻ Refresh";
    busy = false;
    if (again) refresh();
  }
}

async function swapTable(params) {
  const q = new URLSearchParams({ snapshot_id: snapshotId(), ...params });
  await htmx.ajax("GET", `/partials/calendars?${q}`, { target: "#calendars", swap: "innerHTML" });
}

// pair rows: open one pair at a time (clicking the open pair again closes it back to the default view)
results.addEventListener("click", (ev) => {
  const th = ev.target.closest("th.sort-head");
  if (th) {
    const tbl = $("calendars-table");
    const name = th.dataset.sort;
    const desc = tbl.dataset.sortName === name ? tbl.dataset.sortDesc !== "true" : null;
    const sort = desc === null ? name : (desc ? "-" : "+") + name;
    swapTable({ sort });
    return;
  }
  const pr = ev.target.closest("tr.pair-row");
  if (pr) {
    const tbl = $("calendars-table");
    const sortName = tbl.dataset.sortName, desc = tbl.dataset.sortDesc === "true";
    if (pr.classList.contains("sel")) {                     // the open pair again: collapse it (the panel keeps its calendar)
      swapTable({ sort: (desc ? "-" : "+") + sortName, open: "-" });
      return;
    }
    swapTable({ sort: (desc ? "-" : "+") + sortName, open: pr.dataset.key, strike: pr.dataset.near });
    htmx.ajax("GET", `/partials/calendar-panel?snapshot_id=${encodeURIComponent(snapshotId())}&short=${pr.dataset.short}&long=${pr.dataset.long}&strike=${pr.dataset.near}`,
              { target: "#panel", swap: "innerHTML" });
  }
});

// strike rows are hx-get elements injected after load; mark the clicked one selected
results.addEventListener("htmx:afterRequest", (ev) => {
  const el = ev.detail.elt;
  if (el && el.classList && el.classList.contains("strike-row") && ev.detail.successful) {
    el.closest("table").querySelectorAll("tr.sel").forEach((r) => r.classList.remove("sel"));
    el.classList.add("sel");
  }
});

document.body.addEventListener("htmx:responseError", async (ev) => {
  showBanner(await errorText(ev.detail.xhr.response ? { json: async () => JSON.parse(ev.detail.xhr.response), statusText: ev.detail.xhr.statusText } : ev.detail.xhr).catch(() => "Request failed"));
});

// Grey out the widths that have no expiry pair in the chosen DTE range (a holiday, for example). The server decides.
let widthsTimer;
function updateUnavailableWidths() {
  clearTimeout(widthsTimer);
  widthsTimer = setTimeout(async () => {
    const q = new URLSearchParams({ dte_min: $("dte-min").value, dte_max: $("dte-max").value });
    document.querySelectorAll("input[name=widths]").forEach((e) => q.append("widths", e.value));
    try {
      const res = await fetch(`/api/expirations?${q}`);
      if (!res.ok) return;
      const body = await res.json();
      const gone = new Set(body.unavailable_widths.map(String));
      $("width-notes").replaceChildren(...body.holidays.map((h) => {
        const row = document.createElement("div");
        row.textContent = `Holiday ${mdate(h.date)} (${h.name})`;
        return row;
      }));
      document.querySelectorAll("#width-chips .chip-wrap").forEach((wrap) => {
        const off = gone.has(wrap.querySelector("input").value);
        wrap.querySelector(".chip").classList.toggle("unavailable", off);
        wrap.title = off ? "No expiry for this width in this DTE range (a holiday or a weekend)" : "";
      });
    } catch { /* the greying is a hint only */ }
  }, 200);
}

$("refresh").addEventListener("click", () => refresh());

// The whole page refreshes itself (FINDER_REFRESH_S): only while the tab is visible, a first snapshot exists,
// no dialog is open and the filters are valid. It keeps the open pair, strike and sort.
const everyS = Number(results.dataset.refreshS) || 0;
if (everyS > 0) {
  setInterval(() => {
    if (document.hidden || busy || !snapshotId() || document.querySelector("dialog[open]")) return;
    if (filtersProblem(currentFilters())) return;
    refresh(true);
  }, everyS * 1000);
}
$("filters").addEventListener("input", (ev) => {
  const lo = $("dte-min"), hi = $("dte-max");               // the two DTE sliders push each other, never cross
  if (ev.target === lo && Number(lo.value) > Number(hi.value)) hi.value = lo.value;
  if (ev.target === hi && Number(hi.value) < Number(lo.value)) lo.value = hi.value;
  if (ev.target === lo || ev.target === hi) updateUnavailableWidths();
  if (ev.target.id === "size-mode") {                       // switching Size By starts from that mode's default
    $("size-value").value = ev.target.value === "contracts" ? ev.target.dataset.defaultContracts : ev.target.dataset.defaultMargin;
  }
  saveFilters(); scheduleRefresh();
});
