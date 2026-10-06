// Küçük ve güvenli bir Markdown → HTML çevirici (özetler için). qin/md.py ile aynı alt kümeyi destekler:
// başlıklar, paragraflar, kalın/italik, satır içi kod, bağlantılar, (iç içe) listeler, alıntı,
// yatay çizgi, kod bloğu ve basit tablolar.
// Ham HTML hiçbir zaman geçirilmez: metnin tamamı kaçışlanır, bağlantılar yalnızca http(s)/mailto olabilir.
import { esc } from "./format.js";

const HEADING = /^(#{1,4})\s+(.+?)\s*#*\s*$/;
const HR = /^\s*([-*_])(\s*\1){2,}\s*$/;
const ITEM = /^(\s*)([-*+]|\d{1,3}[.)])\s+(.*)$/;
const QUOTE = /^\s*>\s?(.*)$/;
const FENCE = /^\s*```/;
const TABLE_SEP = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;

const CODE = /`([^`\n]+)`/g;
const LINK = /\[([^\]\n]+)\]\(\s*([^\s()]+(?:\([^\s()]*\)[^\s()]*)*)\s*\)/g;
const BARE_URL = /(?<![\p{L}\p{N}_/\x00])(https?:\/\/[^\s<>\x00]+[^\s<>\x00.,;:!?)\]}'"])/gu;
const BOLD = /(\*\*|__)(?=\S)(.+?)(?<=\S)\1/g;
const ITALIC = /(?<![\p{L}\p{N}_*])([*_])(?=[^\s*_])(.+?)(?<=[^\s*_])\1(?![\p{L}\p{N}_*])/gu;
const SAFE_URL = /^(https?:\/\/|mailto:)/i;
const HELD = /\x00(\d+)\x00/;

// Satır içi biçimler. Kod ve bağlantılar önce ham metinden ayıklanıp yer tutucuya alınır;
// geri kalan her şey kaçışlanır, sonra kalın/italik uygulanır.
export function inline(text) {
  const held = [];
  const hold = (html) => `\x00${held.push(html) - 1}\x00`;
  const anchor = (label, url) => {
    if (!SAFE_URL.test(url)) return null;
    const cite = /^\d+$/.test(label) ? ' class="cite"' : "";       // [3](adres): özetlerdeki atıf numarası
    return hold(`<a href="${esc(url)}"${cite} target="_blank" rel="noopener noreferrer">${esc(label)}</a>`);
  };
  let out = String(text).replaceAll("\x00", "")        // yer tutucu işareti metinde bulunamaz
    .replace(CODE, (_, code) => hold(`<code>${esc(code)}</code>`));
  out = out.replace(LINK, (m, label, url) => anchor(label, url) ?? m);
  out = out.replace(BARE_URL, (m, url) => anchor(url, url) ?? m);
  out = esc(out);
  out = out.replace(BOLD, (_, __, body) => `<strong>${body}</strong>`);
  out = out.replace(ITALIC, (_, __, body) => `<em>${body}</em>`);
  while (HELD.test(out)) out = out.replace(/\x00(\d+)\x00/g, (_, i) => held[+i]);   // iç içe: bağlantı adındaki kod
  return out;
}

function cells(line) {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((c) => c.trim());
}

// Girinti düzeyine göre (iç içe) liste. lines: liste satırları ve devam satırları.
function list(lines) {
  const base = ITEM.exec(lines[0])[1].length;
  const ordered = /\d/.test(lines[0].trimStart()[0]);
  const items = [];                                   // { text, sub: [] }
  for (const line of lines) {
    const m = ITEM.exec(line);
    const last = items[items.length - 1];
    if (m && m[1].length <= base + 1) items.push({ text: m[3], sub: [] });
    else if (m || last.sub.length) last.sub.push(line);
    else last.text += ` ${line.trim()}`;
  }
  const tag = ordered ? "ol" : "ul";
  return `<${tag}>${items.map((i) => `<li>${inline(i.text)}${i.sub.length ? list(i.sub) : ""}</li>`).join("")}</${tag}>`;
}

export function renderMarkdown(text, depth = 0) {
  const lines = String(text ?? "").replace(/\r\n?/g, "\n").replaceAll("\x00", "").split("\n");
  const out = [];
  const n = lines.length;
  const quote = (l) => depth < 8 && QUOTE.test(l);     // çok derin iç içe alıntı düz metin sayılır
  const blockStart = (l) => HEADING.test(l) || HR.test(l) || ITEM.test(l) || quote(l) || FENCE.test(l);
  let i = 0;
  while (i < n) {
    const line = lines[i];
    if (!line.trim()) { i += 1; continue; }
    let j = i + 1;
    let m;
    if (FENCE.test(line)) {
      while (j < n && !FENCE.test(lines[j])) j += 1;
      out.push(`<pre>${esc(lines.slice(i + 1, j).join("\n"))}</pre>`);
      i = j + 1;
      continue;
    }
    if ((m = HEADING.exec(line))) {
      const tag = `h${Math.min(m[1].length + 1, 4)}`;   // sayfanın kendi h1'i var: # -> h2
      out.push(`<${tag}>${inline(m[2])}</${tag}>`);
    } else if (HR.test(line)) {
      out.push("<hr>");
    } else if (line.includes("|") && j < n && TABLE_SEP.test(lines[j]) && lines[j].includes("|")) {
      const head = cells(line);
      const rows = [];
      j += 1;
      while (j < n && lines[j].trim() && lines[j].includes("|")) { rows.push(cells(lines[j])); j += 1; }
      const body = rows.map((r) => `<tr>${head.map((_, k) => `<td>${inline(r[k] ?? "")}</td>`).join("")}</tr>`).join("");
      out.push(`<div class="table-wrap"><table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>`);
    } else if (quote(line)) {
      const quoted = [];
      j = i;
      while (j < n && (m = QUOTE.exec(lines[j]))) { quoted.push(m[1]); j += 1; }
      out.push(`<blockquote>${renderMarkdown(quoted.join("\n"), depth + 1)}</blockquote>`);
    } else if (ITEM.test(line)) {
      while (j < n && (ITEM.test(lines[j]) || (lines[j].trim() && /^[ \t]/.test(lines[j])))) j += 1;
      out.push(list(lines.slice(i, j)));
    } else {                                            // paragraf: bir sonraki blok başlangıcına kadar
      while (j < n && lines[j].trim() && !blockStart(lines[j])) j += 1;
      out.push(`<p>${lines.slice(i, j).map((l) => inline(l.trim())).join("<br>")}</p>`);
    }
    i = j;
  }
  return out.join("\n");
}

// Yaklaşık okuma süresi (dakika).
export function readingMinutes(text) {
  const words = String(text ?? "").replace(/\]\([^)]*\)/g, "]").split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(words / 200));
}
