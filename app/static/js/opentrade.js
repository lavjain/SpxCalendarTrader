import { money, num, etime, edate, strike as fmtStrike, DASH } from "./lib/format.js";

// Open Trade dialog. It asks the server for a live quote every couple of seconds and shows what comes back
// (suggested price, contracts, cost, whether Confirm is allowed). No trading math here.
const $ = (id) => document.getElementById(id);
const dlg = $("open-dialog");
let cal = null, timer = null, userPrice = false, last = null, saving = false;

async function errorText(res) {
  try { const j = await res.json(); return typeof j.detail === "string" ? j.detail : (j.detail?.[0]?.msg || res.statusText); }
  catch { return res.statusText; }
}
function show(id, text) { const e = $(id); e.textContent = text || ""; e.classList.toggle("hidden", !text); }
const typedPrice = () => { const v = parseFloat($("od-price").value); return Number.isFinite(v) && v > 0 ? v : null; };

function render(q) {
  last = q;
  $("od-bid").textContent = money(q.bid); $("od-mid").textContent = money(q.mid); $("od-ask").textContent = money(q.ask);
  $("od-suggested").textContent = money(q.suggested_price);
  $("od-time").textContent = `Quote at ${etime(q.time)} · ${q.quotes_seen} quote${q.quotes_seen === 1 ? "" : "s"} seen`;
  if (!userPrice && q.suggested_price != null) $("od-price").value = q.suggested_price.toFixed(2);
  $("od-contracts").textContent = q.contracts == null ? DASH : num(q.contracts);
  $("od-cost").textContent = money(q.cost, 0); $("od-margin").textContent = money(q.margin, 0);
  const waiting = q.stability_required && !q.is_stable;
  show("od-note", waiting ? q.waiting_reason : "");
  const ready = q.contracts != null && typedPrice() != null && (!waiting || userPrice);
  $("od-confirm").disabled = !ready || saving;
}

async function poll() {
  if (!dlg.open) return;
  try {
    const res = await fetch("/api/quote-spread", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ short_symbol: cal.shortSymbol, long_symbol: cal.longSymbol, size_mode: cal.sizeMode,
                             size_value: cal.sizeValue, fill_price: userPrice ? typedPrice() : null }),
    });
    if (!res.ok) throw new Error(await errorText(res));
    show("od-error", ""); render(await res.json());
  } catch (e) { show("od-error", `Could not get a quote: ${e.message}`); }
  if (dlg.open) timer = setTimeout(poll, Number(dlg.dataset.intervalMs) || 2000);
}

function openDialog(btn) {
  const d = btn.dataset;
  cal = { snapshotId: d.snapshotId, shortExpiry: d.shortExpiry, longExpiry: d.longExpiry, strike: Number(d.strike),
          shortSymbol: d.shortSymbol, longSymbol: d.longSymbol, sizeMode: d.sizeMode, sizeValue: Number(d.sizeValue) };
  userPrice = false; last = null; saving = false;
  $("od-title").textContent = `Open SPX ${fmtStrike(cal.strike)} Put Calendar`;
  $("od-sub").textContent = `Short ${edate(cal.shortExpiry)} / Long ${edate(cal.longExpiry)} · ${d.width}-Day Width · ${d.shortDte} / ${d.longDte} DTE`;
  for (const id of ["od-bid", "od-mid", "od-ask", "od-suggested", "od-contracts", "od-cost", "od-margin"]) $(id).textContent = DASH;
  $("od-price").value = ""; $("od-time").textContent = "Getting a live quote…"; $("od-confirm").disabled = true;
  show("od-note", ""); show("od-error", "");
  dlg.showModal(); poll();
}

function closeDialog() { clearTimeout(timer); if (dlg.open) dlg.close(); }

async function confirm() {
  saving = true; $("od-confirm").disabled = true; show("od-error", "");
  try {
    const res = await fetch("/api/trades", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ snapshot_id: cal.snapshotId, short_expiry: cal.shortExpiry, long_expiry: cal.longExpiry,
                             strike: cal.strike, size_mode: cal.sizeMode, size_value: cal.sizeValue,
                             contracts: last.contracts, fill_price: typedPrice(), price_source: cal.pasted ? "pasted" : null }),
    });
    if (!res.ok) throw new Error(await errorText(res));
    const out = await res.json();
    closeDialog();
    const banner = $("banner");
    banner.className = "my-2 rounded border border-emerald-500/50 bg-emerald-500/10 px-3 py-2 text-sm";
    banner.textContent = `Paper trade #${out.trade.id} opened: ${out.trade.contracts} × ${fmtStrike(out.trade.strike)} at ${money(out.trade.open_fill)}.` +
      (out.warnings.length ? ` ${out.warnings.join(" ")}` : "");
  } catch (e) { show("od-error", e.message); saving = false; render(last); }
}

async function copyToTos() {
  if (!last || typedPrice() == null) { show("od-error", "Wait for a quote and a price first"); return; }
  try {
    const res = await fetch("/api/tos-order", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ short_expiry: cal.shortExpiry, long_expiry: cal.longExpiry, strike: cal.strike,
                             contracts: last.contracts, price: typedPrice(), side: "BUY" }),
    });
    if (!res.ok) throw new Error(await errorText(res));
    await navigator.clipboard.writeText((await res.json()).line);
    show("od-error", ""); show("od-note", "Copied: paste it into thinkorswim");
  } catch (e) { show("od-error", `Could not copy: ${e.message}`); }
}

document.addEventListener("click", (ev) => {
  const btn = ev.target.closest("#open-trade-btn");
  if (btn && !btn.disabled) openDialog(btn);
});
$("od-cancel").addEventListener("click", closeDialog);
dlg.addEventListener("close", () => clearTimeout(timer));
$("od-confirm").addEventListener("click", confirm);
$("od-copy").addEventListener("click", copyToTos);
$("od-price").addEventListener("input", () => { userPrice = true; if (last) render(last); });
