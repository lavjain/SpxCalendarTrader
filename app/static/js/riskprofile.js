// Legs / Risk Profile tabs of the calendar panel. The panel is swapped by HTMX, so everything is delegated.
import { RiskGraph } from "./charts/riskgraph.js";
import { money } from "./lib/format.js";

let graph = null, range = 300;
const $ = (s) => document.querySelector(s);

async function load() {
  const box = $("#risk-box"); if (!box) return;
  const q = new URLSearchParams({ snapshot_id: box.dataset.snapshotId, short: box.dataset.short, long: box.dataset.long,
                                  strike: box.dataset.strike, half_range: range });
  const err = $("#risk-error"); err.classList.add("hidden");
  const res = await fetch(`/api/risk-profile?${q}`);
  if (!res.ok) { err.textContent = (await res.json().catch(() => ({}))).detail || "Could not load the risk profile"; err.classList.remove("hidden"); return; }
  const data = await res.json();
  const sm = (v) => (v < 0 ? "−" : "+") + money(Math.abs(v), 0);
  $("#rt-max-profit").textContent = sm(data.max_profit);
  $("#rt-max-loss").textContent = sm(data.max_loss);
  $("#rt-pl-now").textContent = sm(data.pl_now);
  graph = new RiskGraph($("#risk-canvas"));
  graph.set(data);
}

function tab(name) {
  for (const b of document.querySelectorAll("[data-tab]")) b.classList.toggle("chip-on", b.dataset.tab === name);
  $("#tab-legs").classList.toggle("hidden", name !== "legs");
  $("#tab-risk").classList.toggle("hidden", name !== "risk");
  if (name === "risk") load();
}

document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-tab]"); if (t) return tab(t.dataset.tab);
  const r = e.target.closest("[data-range]");
  if (r) { range = Number(r.dataset.range); for (const b of document.querySelectorAll("[data-range]")) b.classList.toggle("chip-on", b === r); load(); }
});
window.addEventListener("resize", () => graph && graph.draw());
