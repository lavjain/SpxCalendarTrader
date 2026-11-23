// Display formatting; mirrors app/formatting.py (checked against tests/format_cases.json).
// No DOM access, so `node --test tests/js/` can import it.
export const DASH = "—";

function body(x, digits) {
  const s = Math.abs(x).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return [s, /[1-9]/.test(s)];
}

export function num(x, digits = 0) {
  if (x === null || x === undefined) return DASH;
  const [s, nonzero] = body(x, digits);
  return (x < 0 && nonzero ? "-" : "") + s;
}

export function money(x, digits = 2) {
  if (x === null || x === undefined) return DASH;
  const [s, nonzero] = body(x, digits);
  return (x < 0 && nonzero ? "-" : "") + "$" + s;
}

export function pct(x, digits = 1) {
  if (x === null || x === undefined) return DASH;
  const [s, nonzero] = body(x * 100, digits);
  return (x < 0 && nonzero ? "-" : "") + s + "%";
}

export function signed(x, digits = 2) {
  if (x === null || x === undefined) return DASH;
  const [s, nonzero] = body(x, digits);
  if (!nonzero) return s;
  return (x < 0 ? "-" : "+") + s;
}

export function pts(x, digits = 2) {
  return x === null || x === undefined ? DASH : num(x, digits);
}

export function edate(iso) {
  if (!iso) return DASH;
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  const wd = dt.toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" });
  const mo = dt.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" });
  return `${wd} ${mo} ${d}`;
}

export function mdate(iso) {
  if (!iso) return DASH;
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const mo = new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", { month: "short", timeZone: "UTC" });
  return `${mo} ${d}`;
}

export function strike(x) {
  return x === null || x === undefined ? DASH : x.toFixed(0);
}

export function etime(iso) {
  if (!iso) return DASH;
  const h = Number(iso.slice(11, 13));
  return `${h % 12 || 12}:${iso.slice(14, 16)}:${iso.slice(17, 19)} ${h < 12 ? "AM" : "PM"} ET`;
}

export function gamma(x, digits = 3) {
  if (x === null || x === undefined) return DASH;
  return Math.abs(x) < 0.001 ? "0.00" : num(x, digits);
}
