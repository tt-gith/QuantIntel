// Sol menü: yörünge haritası, kaynak seçimi ve konu filtresi.
import { STALE_DAYS } from "../config.js";
import { DAY, esc, fmtNum } from "../format.js";
import { topicLabel, tt } from "../i18n.js";
import { icon } from "../icons.js";
import { state, update } from "../state.js";
import { hideTip, showTip } from "./tip.js";

function health(src, now) {
  if (src.ok === false) return { cls: "bad", text: tt("src.error", { error: src.error || "?" }) };
  if (src.ok === null) return { cls: "idle", text: tt("src.never") };
  if (src.last_item) {
    const days = Math.floor((now - new Date(src.last_item)) / DAY);
    if (days >= STALE_DAYS) return { cls: "warn", text: tt("src.stale", { days }) };
  }
  return { cls: "ok", text: tt("src.ok") };
}

function orbit(sources, counts, total) {
  const C = 120, n = sources.length;
  const max = Math.max(1, ...sources.map((s) => counts.get(s.id) || 0));
  const rings = sources.map((s, i) => {
    const r = n > 1 ? 44 + (i * 64) / (n - 1) : 76;
    const c = counts.get(s.id) || 0;
    const size = c ? 4 + 5 * Math.sqrt(c / max) : 3;
    const off = state.src.size && !state.src.has(s.id);
    const dur = 70 + i * 26;                              // dış yörüngeler daha yavaş
    const a0 = (i * 137.500) % 360;                         // altın açı: uydular üst üste binmez
    return `
      <circle class="ring" cx="${C}" cy="${C}" r="${r}"/>
      <g class="sat${off ? " off" : ""}${c ? "" : " empty"}" data-src="${esc(s.id)}"
         style="--dur:${dur}s;--a0:${a0}deg;--c:var(--src-${s.slot})">
        <circle class="sat-hit" cx="${C + r}" cy="${C}" r="14"/>
        <circle class="sat-dot" cx="${C + r}" cy="${C}" r="${size.toFixed(1)}"/>
      </g>`;
  }).join("");
  return `
    <svg class="orbit" viewBox="0 0 240 240" aria-hidden="true">
      ${rings}
      <circle class="core" cx="${C}" cy="${C}" r="24"/>
      <text class="core-n" x="${C}" y="${C + 2}" text-anchor="middle">${fmtNum(total)}</text>
      <text class="core-l" x="${C}" y="${C + 14}" text-anchor="middle">${esc(tt("orbit.center"))}</text>
    </svg>`;
}

export function renderSide(root, view, manifest) {
  const now = Date.now();
  const sources = manifest.sources;
  const wasOpen = root.querySelector("details")?.open;
  const open = wasOpen ?? matchMedia("(min-width: 901px)").matches;
  const activeCount = state.src.size + state.topics.size;

  const srcRows = sources.map((s) => {
    const h = health(s, now);
    const on = !state.src.size || state.src.has(s.id);
    const n = view.srcCounts.get(s.id) || 0;
    return `
      <li>
        <button type="button" class="src-row${on ? "" : " off"}" data-src="${esc(s.id)}"
                aria-pressed="${state.src.has(s.id)}" style="--c:var(--src-${s.slot})">
          <i class="dot"></i>
          <span class="src-name">${esc(s.label)}</span>
          <span class="src-n">${fmtNum(n)}</span>
          <span class="lamp ${h.cls}" title="${esc(h.text)}"></span>
          ${h.cls === "ok" ? "" : `<span class="src-note ${h.cls}">${esc(h.text)}</span>`}
        </button>
      </li>`;
  }).join("");

  const topics = [...view.topicCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);
  const tmax = Math.max(1, ...topics.map(([, n]) => n));
  const topicRows = topics.map(([label, n]) => `
      <li>
        <button type="button" class="topic-row" data-topic="${esc(label)}" aria-pressed="${state.topics.has(label)}">
          <span class="topic-name">${esc(topicLabel(label))}</span>
          <span class="topic-bar"><i style="width:${Math.max(3, (n / tmax) * 100)}%"></i></span>
          <span class="topic-n">${fmtNum(n)}</span>
        </button>
      </li>`).join("");

  root.innerHTML = `
    <details ${open ? "open" : ""}>
      <summary>${icon("filter")}<span>${esc(tt("side.filters"))}</span>${activeCount ? `<b>${activeCount}</b>` : ""}</summary>
      <section class="panel">
        <header><h2>${esc(tt("side.sources"))}</h2>
          ${state.src.size ? `<button type="button" class="link" data-clear="src">${esc(tt("side.all"))}</button>` : ""}</header>
        ${orbit(sources, view.srcCounts, view.list.length)}
        <ul class="src-list">${srcRows}</ul>
      </section>
      ${topics.length ? `
      <section class="panel">
        <header><h2>${esc(tt("side.topics"))}</h2>
          ${state.topics.size ? `<button type="button" class="link" data-clear="topics">${esc(tt("side.clear"))}</button>` : ""}</header>
        <ul class="topic-list">${topicRows}</ul>
      </section>` : ""}
    </details>`;
}

const toggled = (set, v) => { const s = new Set(set); s.has(v) ? s.delete(v) : s.add(v); return s; };

// Olaylar bir kez bağlanır (içerik her çizimde değişse de kök aynı kalır).
export function bindSide(root, manifest) {
  root.addEventListener("click", (e) => {
    const src = e.target.closest("[data-src]");
    if (src) return update({ src: toggled(state.src, src.dataset.src), shown: 0 });
    const topic = e.target.closest("[data-topic]");
    if (topic) return update({ topics: toggled(state.topics, topic.dataset.topic), shown: 0 });
    const clear = e.target.closest("[data-clear]");
    if (clear) return update({ [clear.dataset.clear]: new Set(), shown: 0 });
  });
  root.addEventListener("pointermove", (e) => {
    const sat = e.target.closest(".sat");
    if (!sat) return hideTip();
    const s = manifest.sources.find((x) => x.id === sat.dataset.src);
    const row = root.querySelector(`.src-row[data-src="${CSS.escape(sat.dataset.src)}"] .src-n`);
    showTip(`<b>${esc(s.label)}</b><span>${esc(tt("results", { n: row?.textContent ?? "0" }))}</span>`, e.clientX, e.clientY);
  });
  root.addEventListener("pointerleave", hideTip);
}
