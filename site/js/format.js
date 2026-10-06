// Biçimlendirme yardımcıları.
import { getLang, tt } from "./i18n.js";

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ESC[c]);

export const DAY = 86400000;
export const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
export const dayKey = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const parseDay = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };

const locale = () => (getLang() === "tr" ? "tr-TR" : "en-GB");

export const fmtDate = (d) =>
  new Intl.DateTimeFormat(locale(), { day: "2-digit", month: "short", year: "numeric" }).format(d);
export const fmtDayShort = (d) =>
  new Intl.DateTimeFormat(locale(), { day: "numeric", month: "short" }).format(d);

// Kaç gün önce (takvim gününe göre). 7 günden eskiyse null: yalnızca tarih gösterilir.
export function relDays(date, now = new Date()) {
  const n = Math.round((startOfDay(now) - startOfDay(date)) / DAY);
  if (n < 0 || n > 7) return null;
  if (n === 0) return tt("time.today");
  if (n === 1) return tt("time.yesterday");
  return tt("time.days", { n });
}

export function fmtNum(n) {
  if (n >= 10000) return `${Math.round(n / 1000)}k`;
  if (n >= 1000) return `${(n / 1000).toFixed(1).replace(".0", "")}k`;
  return new Intl.NumberFormat(locale()).format(n);
}

// Görev saati: T+ gg:ss:dd ya da gün sayısıyla
export function fmtElapsed(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const d = Math.floor(s / 86400);
  const p = (x) => String(x).padStart(2, "0");
  const hms = `${p(Math.floor((s % 86400) / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}`;
  return d ? `${d}g ${hms}` : hms;
}
