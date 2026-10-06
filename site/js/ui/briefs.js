// Özetler sekmesi: solda günlük/haftalık özetlerin listesi, sağda seçili özetin okuma görünümü.
import { adminInfo } from "../data.js";
import { DAY, esc, fmtDate, fmtDayShort, relDays } from "../format.js";
import { tt } from "../i18n.js";
import { icon } from "../icons.js";
import { copyText } from "../llmexport.js";
import { readingMinutes, renderMarkdown } from "../md.js";
import { state, update } from "../state.js";

let kindFilter = "all";          // all | daily | weekly
let all = [];

// ISO hafta anahtarından ("2026-W40") o haftanın pazartesisi.
export function weekStart(key) {
  const [year, week] = key.split("-W").map(Number);
  const jan4 = new Date(year, 0, 4);
  return new Date(year, 0, 4 - ((jan4.getDay() + 6) % 7) + (week - 1) * 7);
}

// Özetin kapsadığı dönem: "6 Eki 2026" ya da "28 Eyl – 4 Eki 2026".
export function periodLabel(brief) {
  if (brief.k === "daily") {
    const [y, m, d] = brief.per.split("-").map(Number);
    return fmtDate(new Date(y, m - 1, d));
  }
  const start = weekStart(brief.per);
  return `${fmtDayShort(start)} – ${fmtDate(new Date(start.getTime() + 6 * DAY + DAY / 2))}`;
}

const kindLabel = (brief) => tt(`brief.kind.${brief.k}`);

function current(list) {
  return list.find((b) => b.id === state.brief) ?? all.find((b) => b.id === state.brief) ?? list[0] ?? null;
}

function listRow(brief, selected) {
  return `
    <li>
      <button type="button" class="brief-row" data-brief="${brief.id}" aria-current="${brief.id === selected?.id}">
        <span class="brief-row-meta"><b class="k-${brief.k}">${esc(kindLabel(brief))}</b>${esc(periodLabel(brief))}</span>
        <span class="brief-row-title">${esc(brief.t)}</span>
      </button>
    </li>`;
}

// Sol sütun: özet listesi (dar ekranda açılır kapanır).
export function renderBriefList(root, briefs) {
  all = briefs;
  const list = briefs.filter((b) => kindFilter === "all" || b.k === kindFilter);
  const selected = current(list);
  const wasOpen = root.querySelector("details")?.open;
  const open = wasOpen ?? matchMedia("(min-width: 901px)").matches;
  const counts = { all: briefs.length, daily: briefs.filter((b) => b.k === "daily").length, weekly: briefs.filter((b) => b.k === "weekly").length };
  root.innerHTML = `
    <details ${open ? "open" : ""}>
      <summary>${icon("list")}<span>${esc(tt("brief.list"))}</span><b>${briefs.length}</b></summary>
      <section class="panel">
        <header><h2>${esc(tt("brief.list"))}</h2></header>
        <div class="seg" role="group" aria-label="${esc(tt("brief.filter"))}">
          ${["all", "daily", "weekly"].map((k) => `<button type="button" data-brief-kind="${k}" aria-pressed="${k === kindFilter}">${esc(tt(`brief.filter.${k}`))}<span>${counts[k]}</span></button>`).join("")}
        </div>
        ${list.length ? `<ul class="brief-list">${list.map((b) => listRow(b, selected)).join("")}</ul>`
                      : `<p class="brief-none">${esc(tt("brief.none.kind"))}</p>`}
      </section>
    </details>`;
}

// Sağ sütun: okuma görünümü.
export function renderBriefReader(root, briefs) {
  const list = briefs.filter((b) => kindFilter === "all" || b.k === kindFilter);
  const brief = current(list);
  if (!brief) {
    root.innerHTML = `
      <div class="empty">
        <h3>${esc(tt("brief.empty.title"))}</h3>
        <p>${esc(tt(adminInfo() ? "brief.empty.admin" : "brief.empty.body"))}</p>
      </div>`;
    return;
  }
  const at = list.indexOf(brief);
  const newer = at > 0 ? list[at - 1] : null;
  const older = at >= 0 && at < list.length - 1 ? list[at + 1] : null;
  const rel = relDays(brief.date);
  const nav = (b, key) => (b ? `
      <button type="button" class="reader-nav-btn ${key}" data-brief="${b.id}">
        <small>${esc(tt(`brief.${key}`))}</small><span>${esc(b.t)}</span>
      </button>` : "<span></span>");

  root.innerHTML = `
    <article class="reader">
      <header class="reader-head">
        <p class="reader-kicker"><b>${esc(kindLabel(brief))}</b><span>${esc(periodLabel(brief))}</span></p>
        <h2>${esc(brief.t)}</h2>
        <p class="reader-meta">
          <span>${esc(tt("brief.minutes", { n: readingMinutes(brief.b) }))}</span>
          <span>${esc(tt(`brief.origin.${brief.o}`, null, brief.o))}</span>
          <time datetime="${esc(brief.c)}">${esc(rel ?? fmtDate(brief.date))}</time>
          <button type="button" class="link" data-copy-link="${brief.id}">${esc(tt("brief.copylink"))}</button>
        </p>
      </header>
      <div class="prose">${renderMarkdown(brief.b)}</div>
      <p class="reader-note">${esc(tt(brief.o === "llm" ? "brief.note.llm" : "brief.note.manual"))}</p>
      <nav class="reader-nav" aria-label="${esc(tt("brief.list"))}">${nav(older, "older")}${nav(newer, "newer")}</nav>
    </article>`;
}

// Olaylar bir kez bağlanır. side: liste sütunu, main: okuma alanı.
export function bindBriefs({ side, main }) {
  const open = (e) => {
    const kind = e.target.closest("[data-brief-kind]");
    if (kind) { kindFilter = kind.dataset.briefKind; update({ brief: null }); return true; }
    const row = e.target.closest("[data-brief]");
    if (!row) return false;
    update({ tab: "briefs", brief: +row.dataset.brief });
    return true;
  };
  side.addEventListener("click", (e) => {
    if (!open(e) || !e.target.closest("[data-brief]")) return;
    if (!matchMedia("(min-width: 901px)").matches) side.querySelector("details")?.removeAttribute("open");
    main.scrollIntoView({ block: "start" });
  });
  main.addEventListener("click", async (e) => {
    const link = e.target.closest("[data-copy-link]");
    if (link) {
      const url = `${location.origin}${location.pathname}#tab=briefs&brief=${link.dataset.copyLink}`;
      link.textContent = tt(await copyText(url) ? "brief.copied" : "export.failed");
      return;
    }
    if (open(e)) main.scrollIntoView({ block: "start" });
  });
}
