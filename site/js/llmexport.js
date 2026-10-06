// "LLM için dışa aktar": ekrandaki görünümü (tarih aralığı, sekme, filtreler) hazır bir özet isteğiyle
// birlikte tek bir metne çevirir. Metin Claude, ChatGPT ya da başka bir modele olduğu gibi yapıştırılır;
// modelin yazdığı özet de yönetim panelinden siteye eklenebilir.
import { EXPORT_SUMMARY_CHARS, RANGES } from "./config.js";
import { dayKey, fmtDate } from "./format.js";
import { tt } from "./i18n.js";
import { rangeBounds, state } from "./state.js";

const clip = (s, n) => (s.length <= n ? s : `${s.slice(0, n).replace(/\s+\S*$/, "")} …`);

function signal(item) {
  const m = item.m ?? {};
  const parts = [];
  if (item.src.length > 1) parts.push(tt("export.sig.multi", { n: item.src.length }));
  if (m.up) parts.push(tt("export.sig.up", { n: m.up }));
  if (m.cm) parts.push(tt("export.sig.cm", { n: m.cm }));
  if (m.cit) parts.push(tt("export.sig.cit", { n: m.cit }));
  if (item.hot) parts.push(tt("metric.hot.short"));
  if (item.tool) parts.push(tt("kind.tool"));
  return parts.join(", ");
}

function rangeLabel(list) {
  const b = rangeBounds();
  const def = RANGES.find((r) => r.id === state.range);
  const name = state.range === "custom" ? tt("range.custom") : tt(`range.${def.id}`);
  const from = b.from ?? (list.length ? new Date(Math.min(...list.map((i) => i.date))) : new Date());
  return `${name} (${fmtDate(from)} – ${fmtDate(b.to ?? new Date())})`;
}

// Görünümü metne çevirir. { text, name } döndürür (name: indirilecek dosyanın adı).
export function buildExport(list, manifest) {
  const labels = new Map(manifest.sources.map((s) => [s.id, s.label]));
  const filters = [];
  if (state.src.size) filters.push(`${tt("side.sources")}: ${[...state.src].map((s) => labels.get(s) ?? s).join(", ")}`);
  if (state.topics.size) filters.push(`${tt("side.topics")}: ${[...state.topics].join(", ")}`);
  if (state.q) filters.push(tt("filter.search", { v: state.q }));

  const head = [
    `# Quant Intelligence · ${tt("export.heading")}`,
    "",
    `${tt("range.label")}: ${rangeLabel(list)}`,
    `${tt("export.view")}: ${tt(`tab.${state.tab}`)} · ${tt("sort.label")}: ${tt(`sort.${state.sort}`)} · ${tt("results", { n: list.length })}`,
    ...(filters.length ? [`${tt("export.filters")}: ${filters.join(" · ")}`] : []),
    "",
    `## ${tt("export.task")}`,
    tt("export.prompt"),
    "",
    `## ${tt("export.items")}`,
  ];
  const body = list.map((item, n) => {
    const sig = signal(item);
    const meta = [
      tt(`kind.${item.k}`, null, item.k),
      item.src.map((s) => labels.get(s) ?? s).join(", "),
      item.d.slice(0, 10),
      ...(sig ? [sig] : []),
      ...(item.p ? [tt("export.score", { n: item.p })] : []),
    ].join(" · ");
    return [
      "",
      `### ${n + 1}. ${item.t}`,
      meta,
      ...(item.o ? [`${tt("export.origin")}: ${clip(item.o, 160)}`] : []),
      `${tt("export.link")}: ${item.u}`,
      ...(item.s ? [`${tt("export.summary")}: ${clip(item.s, EXPORT_SUMMARY_CHARS)}`] : []),
    ].join("\n");
  });
  const span = state.range === "custom" ? `${state.from}_${state.to}` : state.range;
  return { text: `${head.join("\n")}\n${body.join("\n")}\n`, name: `quant-intel-${dayKey(new Date())}-${state.tab}-${span}.md` };
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {                                             // izin yoksa ya da güvenli bağlam değilse
    const area = Object.assign(document.createElement("textarea"), { value: text });
    area.style.cssText = "position:fixed;opacity:0";
    document.body.append(area);
    area.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { /* yoksay */ }
    area.remove();
    return ok;
  }
}

export function downloadText(text, name) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
