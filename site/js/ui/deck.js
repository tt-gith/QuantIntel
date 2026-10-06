// Uçuş güvertesi: sitenin tanımı, görev saati ve seçili aralığın öne çıkan içerikleri.
import { SPOTLIGHT_GROUPS, SPOTLIGHT_SIZE } from "../config.js";
import { esc, fmtDate, fmtElapsed, relDays } from "../format.js";
import { itemText, tt } from "../i18n.js";
import { state } from "../state.js";
import { signals, sourceChips } from "./parts.js";

let clockTimer = 0;

// Güç sırası: popülerlik puanı, "çok tıklanan" işareti, özeti olması, yenilik.
const stronger = (a, b) =>
  (b.p || 0) - (a.p || 0) || (b.hot ? 1 : 0) - (a.hot ? 1 : 0) || (b.s ? 1 : 0) - (a.s ? 1 : 0) || b.date - a.date;

// Vitrine girecek içerikleri seçer. Akış sekmesinde her gruptan en güçlüsü alınır;
// tek türlü sekmelerde (Makaleler, Araçlar...) doğrudan en güçlü beş içerik.
export function pickSpotlight(list, tabId) {
  const sorted = [...list].sort(stronger);
  if (tabId !== "all") {
    return sorted.slice(0, SPOTLIGHT_SIZE).map((item) => ({ item, label: item.tool ? "spot.tool" : `kind.${item.k}` }));
  }
  const used = new Set();
  const picks = [];
  for (const group of SPOTLIGHT_GROUPS) {
    const item = sorted.find((i) => !used.has(i.id) && group.test(i));
    if (item) { used.add(item.id); picks.push({ item, label: group.label }); }
  }
  return picks.sort((a, b) => stronger(a.item, b.item)).slice(0, SPOTLIGHT_SIZE);
}

function when(item) {
  return `<time datetime="${esc(item.d)}">${esc(relDays(item.date) ?? fmtDate(item.date))}</time>`;
}

function leadCard({ item, label }, sourceMap) {
  const text = itemText(item);
  return `
    <article class="lead">
      <div class="lead-meta"><span class="lead-kind">${esc(tt(label, null, item.k))}</span>${sourceChips(item, sourceMap)}${when(item)}</div>
      <h3><a href="${esc(item.u)}" target="_blank" rel="noopener noreferrer">${esc(text.title)}</a></h3>
      ${item.o ? `<p class="origin">${esc(item.o)}</p>` : ""}
      ${text.summary ? `<p class="lead-sum">${esc(text.summary)}</p>` : ""}
      <div class="lead-sig">${signals(item, sourceMap)}</div>
    </article>`;
}

function runner({ item, label }, sourceMap) {
  const text = itemText(item);
  return `
    <li>
      <a class="runner" href="${esc(item.u)}" target="_blank" rel="noopener noreferrer">
        <span class="runner-kind">${esc(tt(label, null, item.k))}</span>
        <span class="runner-title">${esc(text.title)}</span>
        <span class="runner-meta">${sourceChips(item, sourceMap)}${when(item)}<span class="runner-sig">${signals(item, sourceMap, { gauge: false })}</span></span>
      </a>
    </li>`;
}

export function renderDeck(root, view, manifest) {
  const sourceMap = new Map(manifest.sources.map((s) => [s.id, s]));
  const generated = new Date(manifest.generated);
  const picks = pickSpotlight(view.list, state.tab);
  const [lead, ...rest] = picks;

  root.innerHTML = `
    <div class="deck-in">
      <div class="deck-head">
        <div class="deck-copy">
          <h1>${esc(tt("deck.title"))}</h1>
          <p>${esc(tt("deck.lead", { n: manifest.sources.length }))}</p>
        </div>
        <div class="clock" title="${esc(generated.toLocaleString())}">
          <div class="clock-read"><span class="clock-t">T+</span><span id="clock">00:00:00</span></div>
          <small>${esc(tt("deck.clock"))}</small>
        </div>
      </div>
      ${lead ? `
      <section class="spot" aria-labelledby="spot-h">
        <h2 id="spot-h">${esc(tt(`spot.title.${state.range}`))}</h2>
        <div class="spot-grid${rest.length ? "" : " solo"}">
          ${leadCard(lead, sourceMap)}
          ${rest.length ? `<ol class="runners">${rest.map((p) => runner(p, sourceMap)).join("")}</ol>` : ""}
        </div>
      </section>` : ""}
    </div>
    <div class="limb" aria-hidden="true"></div>`;

  clearInterval(clockTimer);
  const clock = root.querySelector("#clock");
  const tick = () => { clock.textContent = fmtElapsed(Date.now() - generated.getTime()); };
  tick();
  clockTimer = setInterval(tick, 1000);
}
