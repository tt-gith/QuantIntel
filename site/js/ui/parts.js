// Liste satırlarında ve vitrin kartlarında ortak kullanılan küçük parçalar.
import { METRICS } from "../config.js";
import { esc, fmtNum } from "../format.js";
import { tt } from "../i18n.js";
import { icon } from "../icons.js";

// Öğenin geldiği kaynaklar: renkli nokta + ad.
export function sourceChips(item, sourceMap) {
  return item.src.map((s) => {
    const def = sourceMap.get(s);
    return `<span class="src" style="--c:var(--src-${def?.slot ?? 1})"><i class="dot"></i>${esc(def?.label ?? s)}</span>`;
  }).join("");
}

// Popülerlik rozetleri: oy, yorum, atıf, kaç kaynakta geçtiği, "çok tıklanan" ve puan çubuğu.
export function signals(item, sourceMap, { gauge = true } = {}) {
  const out = [];
  for (const def of METRICS) {
    const v = item.m?.[def.key];
    if (!v) continue;
    const label = tt(`metric.${def.key}`, { n: fmtNum(v) });
    out.push(`<span class="sig-m" title="${esc(label)}" aria-label="${esc(label)}">${icon(def.icon)}<b>${fmtNum(v)}</b></span>`);
  }
  if (item.src.length > 1) {
    const list = item.src.map((s) => sourceMap.get(s)?.label ?? s).join(", ");
    const label = tt("metric.multi", { n: item.src.length, list });
    out.push(`<span class="sig-m" title="${esc(label)}" aria-label="${esc(label)}">${icon("multi")}<b>${esc(tt("metric.multi.short", { n: item.src.length }))}</b></span>`);
  }
  if (item.hot) {
    out.push(`<span class="sig-m hot" title="${esc(tt("metric.hot"))}">${icon("hot")}<b>${esc(tt("metric.hot.short"))}</b></span>`);
  }
  if (gauge && item.p) {
    const label = tt("metric.score", { n: item.p });
    out.push(`<span class="gauge" title="${esc(label)}" role="img" aria-label="${esc(label)}"><i style="width:${item.p}%"></i></span>`);
  }
  return out.join("");
}
