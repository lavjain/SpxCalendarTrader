// Risk profile painted on a canvas: P/L (dollars) over SPX, Today and At Short Expiry, +-1 SD band, break-evens.
// Pure painting from the plain lists /api/risk-profile returns. Red is never a line colour (it means loss/warning).
const PAD = { l: 62, r: 14, t: 14, b: 28 };
const COLORS = { today: "#1C83E1", expiry: "#16a34a", band: "rgba(28,131,225,0.10)", spot: "#94a3b8" };

function nice(v) { return Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(Math.abs(v) >= 10000 ? 0 : 1)}k` : v.toFixed(0); }

export class RiskGraph {
  constructor(canvas) {
    this.c = canvas; this.ctx = canvas.getContext("2d"); this.data = null; this.view = null; this.hover = null;
    canvas.addEventListener("mousemove", (e) => { this.hover = this.toX(e.offsetX); this.draw(); });
    canvas.addEventListener("mouseleave", () => { this.hover = null; this.draw(); });
    canvas.addEventListener("wheel", (e) => { e.preventDefault(); this.zoom(e.deltaY < 0 ? 0.85 : 1 / 0.85, this.toX(e.offsetX)); }, { passive: false });
    canvas.addEventListener("dblclick", () => { this.view = null; this.draw(); });
    let drag = null;
    canvas.addEventListener("mousedown", (e) => { drag = { x: e.offsetX, view: this.range() }; });
    window.addEventListener("mouseup", () => { drag = null; });
    canvas.addEventListener("mousemove", (e) => {
      if (!drag) return;
      const [a, b] = drag.view, dx = (e.offsetX - drag.x) / this.plotW() * (b - a);
      this.view = [a - dx, b - dx]; this.draw();
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
    const ink = dark ? "#cbd5e1" : "#334155", grid = dark ? "#334155" : "#e2e8f0";
    const [x0, x1] = this.range();
    const idx = d.spx.map((x, i) => i).filter((i) => d.spx[i] >= x0 && d.spx[i] <= x1);
    const ys = idx.flatMap((i) => [d.today[i], d.at_expiry[i]]).concat([0]);
    let lo = Math.min(...ys), hi = Math.max(...ys); const padY = (hi - lo) * 0.06 || 1; lo -= padY; hi += padY;
    const X = (x) => PAD.l + (x - x0) / (x1 - x0) * this.plotW();
    const Y = (y) => PAD.t + (hi - y) / (hi - lo) * this.plotH();
    g.font = "11px system-ui, sans-serif"; g.fillStyle = ink; g.strokeStyle = grid; g.lineWidth = 1;
    for (let k = 0; k <= 5; k++) {                               // horizontal grid + $ labels
      const y = lo + (hi - lo) * k / 5; g.beginPath(); g.moveTo(PAD.l, Y(y)); g.lineTo(W - PAD.r, Y(y)); g.stroke();
      g.textAlign = "right"; g.fillText(`${y < 0 ? "-" : ""}$${nice(Math.abs(y))}`, PAD.l - 6, Y(y) + 4);
    }
    g.textAlign = "center";
    for (let k = 0; k <= 6; k++) { const x = x0 + (x1 - x0) * k / 6; g.fillText(x.toFixed(0), X(x), H - 8); }
    g.fillStyle = COLORS.band; g.fillRect(X(Math.max(d.sd_low, x0)), PAD.t, X(Math.min(d.sd_high, x1)) - X(Math.max(d.sd_low, x0)), this.plotH());
    g.strokeStyle = ink; g.lineWidth = 1.2; g.beginPath(); g.moveTo(PAD.l, Y(0)); g.lineTo(W - PAD.r, Y(0)); g.stroke();   // $0
    g.setLineDash([4, 4]); g.strokeStyle = COLORS.spot; g.beginPath(); g.moveTo(X(d.spot), PAD.t); g.lineTo(X(d.spot), H - PAD.b); g.stroke(); g.setLineDash([]);
    const line = (ys, col) => { g.strokeStyle = col; g.lineWidth = 2; g.beginPath();
      idx.forEach((i, n) => (n ? g.lineTo(X(d.spx[i]), Y(ys[i])) : g.moveTo(X(d.spx[i]), Y(ys[i])))); g.stroke(); };
    line(d.at_expiry, COLORS.expiry); line(d.today, COLORS.today);
    if (d.break_evens) for (const x of [d.break_evens.lower, d.break_evens.upper]) {
      if (x < x0 || x > x1) continue; g.fillStyle = COLORS.expiry; g.beginPath(); g.arc(X(x), Y(0), 4, 0, 7); g.fill();
    }
    if (this.hover != null && this.hover >= x0 && this.hover <= x1) {
      const i = d.spx.reduce((b, x, n) => (Math.abs(x - this.hover) < Math.abs(d.spx[b] - this.hover) ? n : b), 0);
      g.strokeStyle = ink; g.lineWidth = 1; g.beginPath(); g.moveTo(X(d.spx[i]), PAD.t); g.lineTo(X(d.spx[i]), H - PAD.b); g.stroke();
      const t = `SPX ${d.spx[i].toFixed(0)}  Today ${fmt(d.today[i])}  Expiry ${fmt(d.at_expiry[i])}`;
      g.font = "12px system-ui, sans-serif"; const w = g.measureText(t).width + 12, bx = Math.min(Math.max(X(d.spx[i]) + 8, PAD.l), W - PAD.r - w);
      g.fillStyle = dark ? "#0f172a" : "#ffffff"; g.strokeStyle = grid; g.fillRect(bx, PAD.t + 4, w, 22); g.strokeRect(bx, PAD.t + 4, w, 22);
      g.fillStyle = ink; g.textAlign = "left"; g.fillText(t, bx + 6, PAD.t + 19);
    }
  }
}
function fmt(v) { return `${v < 0 ? "-" : ""}$${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`; }
