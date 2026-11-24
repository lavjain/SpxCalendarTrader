// Risk profile painted on a canvas: P/L (dollars) over SPX, as the mockups draw it: At Short Expiry solid sky blue with
// green/red shading to $0, Today dashed pink, the +-1 SD band with its two levels, SPX now, break-evens with their levels.
// Pure painting from the plain lists /api/risk-profile returns. Red is never a line colour (it means loss).
const PAD = { l: 62, r: 14, t: 14, b: 28 };
const COLORS = { expiry: "#38BDF8", today: "#F472B6", be: "#FCD34D", band: "rgba(148,163,184,0.10)", sd: "#64748B",
                 gain: "rgba(74,222,128,0.12)", loss: "rgba(248,113,113,0.12)", spot: "#E2E8F0" };

function nice(v) { return Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(Math.abs(v) >= 10000 ? 0 : 1)}k` : v.toFixed(0); }
const sgn = (v) => (v < 0 ? "−" : "");

export class RiskGraph {
  constructor(canvas) {
    this.c = canvas; this.ctx = canvas.getContext("2d"); this.data = null; this.view = null; this.hover = null;
    canvas.addEventListener("mouseleave", () => { this.hover = null; this.draw(); });
    // Zoom, pan and reset work only on the SPX values under the chart; over the plot the wheel scrolls the page and
    // a click or drag does nothing, so it cannot be moved by accident.
    const onAxis = (e) => e.offsetY >= this.c.clientHeight - PAD.b - 4;
    canvas.addEventListener("wheel", (e) => {
      if (!onAxis(e)) return;
      e.preventDefault(); this.zoom(e.deltaY < 0 ? 0.85 : 1 / 0.85, this.toX(e.offsetX));
    }, { passive: false });
    canvas.addEventListener("dblclick", (e) => { if (onAxis(e)) { this.view = null; this.draw(); } });
    let drag = null;
    canvas.addEventListener("mousedown", (e) => { if (e.button === 0 && onAxis(e)) drag = { x: e.offsetX, view: this.range() }; });
    window.addEventListener("mouseup", () => { drag = null; });
    canvas.addEventListener("mousemove", (e) => {
      canvas.style.cursor = drag || onAxis(e) ? "ew-resize" : "default";
      if (drag) {
        const [a, b] = drag.view, dx = (e.offsetX - drag.x) / this.plotW() * (b - a);
        this.view = [a - dx, b - dx]; this.hover = null; this.draw(); return;
      }
      this.hover = onAxis(e) ? null : this.toX(e.offsetX); this.draw();
    });
  }
  set(data) { this.data = data; this.view = null; this.draw(); }
  range() { return this.view || [this.data.spx[0], this.data.spx[this.data.spx.length - 1]]; }
  plotW() { return this.c.clientWidth - PAD.l - PAD.r; }
  plotH() { return this.c.clientHeight - PAD.t - PAD.b; }
  toX(px) { const [a, b] = this.range(); return a + (px - PAD.l) / this.plotW() * (b - a); }
  zoom(f, at) { const [a, b] = this.range(); this.view = [at - (at - a) * f, at + (b - at) * f]; this.draw(); }
  draw() {
    const d = this.data; if (!d) return;
    const dpr = window.devicePixelRatio || 1, W = this.c.clientWidth, H = this.c.clientHeight;
    this.c.width = W * dpr; this.c.height = H * dpr;
    const g = this.ctx; g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
    const dark = document.documentElement.classList.contains("dark");
    const ink = dark ? "#cbd5e1" : "#334155", grid = dark ? "#1e293b" : "#e2e8f0", muted = dark ? "#94a3b8" : "#64748b";
    const [x0, x1] = this.range();
    const idx = d.spx.map((x, i) => i).filter((i) => d.spx[i] >= x0 && d.spx[i] <= x1);
    const ys = idx.flatMap((i) => [d.today[i], d.at_expiry[i]]).concat([0]);
    let lo = Math.min(...ys), hi = Math.max(...ys); const span = (hi - lo) || 1; lo -= span * 0.05; hi += span * 0.16;   // headroom for the labels
    const X = (x) => PAD.l + (x - x0) / (x1 - x0) * this.plotW();
    const Y = (y) => PAD.t + (hi - y) / (hi - lo) * this.plotH();
    g.font = "11px system-ui, sans-serif"; g.lineWidth = 1;
    for (let k = 0; k <= 5; k++) {                               // horizontal grid + $ labels
      const y = lo + (hi - lo) * k / 5; g.strokeStyle = grid; g.beginPath(); g.moveTo(PAD.l, Y(y)); g.lineTo(W - PAD.r, Y(y)); g.stroke();
      g.fillStyle = ink; g.textAlign = "right"; g.fillText(`${sgn(y)}$${nice(Math.abs(y))}`, PAD.l - 6, Y(y) + 4);
    }
    g.fillStyle = ink; g.textAlign = "center";
    for (let k = 0; k <= 6; k++) { const x = x0 + (x1 - x0) * k / 6; g.fillText(x.toFixed(0), X(x), H - 8); }
    // the +-1 SD band, its two dotted edges and their levels
    const a = Math.max(d.sd_low, x0), b = Math.min(d.sd_high, x1);
    if (b > a) { g.fillStyle = COLORS.band; g.fillRect(X(a), PAD.t, X(b) - X(a), this.plotH()); }
    g.setLineDash([1, 3]); g.strokeStyle = COLORS.sd; g.fillStyle = muted; g.font = "10px system-ui, sans-serif";
    for (const [v, lab] of [[d.sd_low, "−1σ"], [d.sd_high, "+1σ"]]) {
      if (v < x0 || v > x1) continue;
      g.beginPath(); g.moveTo(X(v), PAD.t); g.lineTo(X(v), H - PAD.b); g.stroke();
      g.textAlign = "center"; g.fillText(`${lab} ${v.toFixed(0)}`, X(v), PAD.t + 26);
    }
    g.setLineDash([]);
    // green above $0 and red below it, under the At Short Expiry line
    const shade = (keep, col) => {
      g.fillStyle = col; g.beginPath(); let open = false;
      idx.forEach((i) => { const y = keep(d.at_expiry[i]) ? d.at_expiry[i] : 0;
        if (!open) { g.moveTo(X(d.spx[i]), Y(0)); open = true; } g.lineTo(X(d.spx[i]), Y(y)); });
      if (open) { g.lineTo(X(d.spx[idx[idx.length - 1]]), Y(0)); g.closePath(); g.fill(); }
    };
    shade((v) => v >= 0, COLORS.gain); shade((v) => v < 0, COLORS.loss);
    g.strokeStyle = muted; g.lineWidth = 1; g.beginPath(); g.moveTo(PAD.l, Y(0)); g.lineTo(W - PAD.r, Y(0)); g.stroke();   // $0
    const line = (vals, col, dash, w) => { g.strokeStyle = col; g.lineWidth = w; g.setLineDash(dash); g.beginPath();
      idx.forEach((i, n) => (n ? g.lineTo(X(d.spx[i]), Y(vals[i])) : g.moveTo(X(d.spx[i]), Y(vals[i])))); g.stroke(); g.setLineDash([]); };
    line(d.at_expiry, COLORS.expiry, [], 2); line(d.today, COLORS.today, [6, 4], 1.6);
    if (d.spot >= x0 && d.spot <= x1) {                          // SPX now: dotted line and a label at the top
      g.strokeStyle = COLORS.spot; g.lineWidth = 0.8; g.setLineDash([1, 3]); g.beginPath(); g.moveTo(X(d.spot), PAD.t + 18); g.lineTo(X(d.spot), H - PAD.b); g.stroke(); g.setLineDash([]);
      const t = `SPX ${d.spot.toFixed(0)}`; g.font = "11px system-ui, sans-serif"; const w = g.measureText(t).width + 10;
      g.fillStyle = dark ? "#0f172a" : "#ffffff"; g.strokeStyle = dark ? "#334155" : "#cbd5e1"; g.lineWidth = 0.8;
      g.fillRect(X(d.spot) - w / 2, PAD.t, w, 17); g.strokeRect(X(d.spot) - w / 2, PAD.t, w, 17);
      g.fillStyle = ink; g.textAlign = "center"; g.fillText(t, X(d.spot), PAD.t + 12);
    }
    if (d.break_evens) for (const x of [d.break_evens.lower, d.break_evens.upper]) {      // break-evens in yellow with their levels
      if (x < x0 || x > x1) continue;
      g.fillStyle = COLORS.be; g.beginPath(); g.arc(X(x), Y(0), 4.5, 0, 7); g.fill();
      g.font = "11px system-ui, sans-serif"; g.textAlign = "left"; g.fillText(` ${x.toFixed(0)}`, X(x) + 4, Y(0) - 6);
    }
    if (this.hover != null && this.hover >= x0 && this.hover <= x1) {
      const i = d.spx.reduce((bi, x, n) => (Math.abs(x - this.hover) < Math.abs(d.spx[bi] - this.hover) ? n : bi), 0);
      g.strokeStyle = muted; g.lineWidth = 1; g.beginPath(); g.moveTo(X(d.spx[i]), PAD.t); g.lineTo(X(d.spx[i]), H - PAD.b); g.stroke();
      const t = `SPX ${d.spx[i].toFixed(0)}  Today ${fmt(d.today[i])}  Expiry ${fmt(d.at_expiry[i])}`;
      g.font = "12px system-ui, sans-serif"; const w = g.measureText(t).width + 12, bx = Math.min(Math.max(X(d.spx[i]) + 8, PAD.l), W - PAD.r - w);
      g.fillStyle = dark ? "#0f172a" : "#ffffff"; g.strokeStyle = dark ? "#334155" : "#cbd5e1"; g.fillRect(bx, PAD.t + 40, w, 22); g.strokeRect(bx, PAD.t + 40, w, 22);
      g.fillStyle = ink; g.textAlign = "left"; g.fillText(t, bx + 6, PAD.t + 55);
    }
  }
}
function fmt(v) { return `${v < 0 ? "−" : ""}$${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`; }
