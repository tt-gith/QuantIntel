// Dil katmanı. t("anahtar", {degisken}) çevrilmiş metni verir.
import { DEFAULT_LANG, LANGS } from "./config.js";

const dicts = {};
let lang = DEFAULT_LANG;

export async function setLang(next) {
  if (!LANGS.includes(next)) next = DEFAULT_LANG;
  if (!dicts[next]) dicts[next] = (await import(`../i18n/${next}.js`)).default;
  lang = next;
  document.documentElement.lang = next;
  try { localStorage.setItem("qin.lang", next); } catch { /* özel pencere: sorun değil */ }
}

export function savedLang() {
  try { return localStorage.getItem("qin.lang") || DEFAULT_LANG; } catch { return DEFAULT_LANG; }
}

export const getLang = () => lang;

export function t(key, vars) {
  let s = dicts[lang]?.[key];
  if (s === undefined) return null;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, v);
  return s;
}

// Çevirisi yoksa anahtarın kendisini (ya da verilen yedeği) gösterir.
export const tt = (key, vars, fallback) => t(key, vars) ?? fallback ?? key;

// Konu etiketleri arşivde Türkçe tutulur; başka dilde varsa çevirisini gösterir.
export const topicLabel = (label) => t(`topic.${label}`) ?? label;

// İçerik metni: seçili dilde çevirisi varsa onu, yoksa orijinali döndürür.
export function itemText(item) {
  const tr = item.tr?.[lang];
  if (tr?.t) return { title: tr.t, summary: tr.s ?? item.s, translated: true };
  return { title: item.t, summary: item.s, translated: false };
}
