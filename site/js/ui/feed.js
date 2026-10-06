// Sekmeler, sıralama çubuğu ve içerik listesi.
import { PAGE_SIZE, SORTS, TABS } from "../config.js";
import { esc, fmtDate, fmtNum, relDays } from "../format.js";
import { itemText, topicLabel, tt } from "../i18n.js";
import { icon } from "../icons.js";
import { isLiked, likeCount, toggleLike } from "../likes.js";
import { resetFilters, state, update } from "../state.js";
import { signals, sourceChips } from "./parts.js";

let sourceMap = new Map();
let current = [];
let observer = null;

export function renderTabs(root, view) {
  root.innerHTML = TABS.map((t) => {
    const n = view.tabCounts.get(t.id) || 0;
    return `<button type="button" role="tab" data-tab="${t.id}" aria-selected="${t.id === state.tab}"
              class="${n ? "" : "none"}">${esc(tt(`tab.${t.id}`))}<span>${fmtNum(n)}</span></button>`;
  }).join("");
  // Dar ekranda seçili sekmeyi yatayda görünür tut (sayfayı dikeyde kaydırmadan)
  const on = root.querySelector('[aria-selected="true"]');
  if (on && (on.offsetLeft < root.scrollLeft || on.offsetLeft + on.offsetWidth > root.scrollLeft + root.clientWidth)) {
    root.scrollLeft = on.offsetLeft - 16;
  }
}

export function renderToolbar(root, view) {
  const chips = [];
  for (const topic of state.topics) {
    chips.push(`<button type="button" class="chip" data-drop-topic="${esc(topic)}" title="${esc(tt("filter.remove"))}">
      ${esc(tt("filter.topic", { v: topicLabel(topic) }))}${icon("close")}</button>`);
  }
  if (state.q) {
    chips.push(`<button type="button" class="chip" data-drop-q title="${esc(tt("filter.remove"))}">
      ${esc(tt("filter.search", { v: state.q }))}${icon("close")}</button>`);
  }
  root.innerHTML = `
    <div class="tb-left"><strong>${esc(tt("results", { n: fmtNum(view.list.length) }))}</strong>${chips.join("")}</div>
    <div class="sort" role="group" aria-label="${esc(tt("sort.label"))}">
      <span>${esc(tt("sort.label"))}</span>
      ${SORTS.map((s) => `<button type="button" data-sort="${s}" aria-pressed="${s === state.sort}">${esc(tt(`sort.${s}`))}</button>`).join("")}
    </div>`;
}

function row(item) {
  const text = itemText(item);
  const rel = relDays(item.date);
  const first = sourceMap.get(item.src[0]);
  const srcs = sourceChips(item, sourceMap);
  const liked = isLiked(item.id);
  const likes = likeCount(item);
  const long = (text.summary?.length ?? 0) > 230;
  const tags = [
    ...(item.tg ?? []).map((t) => `<button type="button" class="tag" data-topic="${esc(t)}">${esc(topicLabel(t))}</button>`),
    ...(item.xt ?? []).map((t) => `<span class="tag plain">${esc(t)}</span>`),
  ].join("");

  return `
  <li class="row" style="--c:var(--src-${first?.slot ?? 1})">
    <div class="when">
      ${rel ? `<span class="rel">${esc(rel)}</span>` : ""}
      <time datetime="${esc(item.d)}">${esc(fmtDate(item.date))}</time>
    </div>
    <article class="body">
      <div class="meta">
        ${srcs}
        <span class="kind">${esc(tt(`kind.${item.k}`, null, item.k))}</span>
        ${item.tool ? `<span class="flag">${icon("tool")}${esc(tt("kind.tool"))}</span>` : ""}
        ${text.translated ? `<span class="flag ion" title="${esc(item.t)}">${esc(tt("item.translated"))}</span>` : ""}
        ${item.st ? `<span class="flag ion">${esc(tt("item.status", { v: item.st }))}</span>` : ""}
      </div>
      <h3><a href="${esc(item.u)}" target="_blank" rel="noopener noreferrer">${esc(text.title)}</a></h3>
      ${item.o ? `<p class="origin">${esc(item.o)}</p>` : ""}
      ${text.summary ? `<p class="sum${long ? " clamp" : ""}">${esc(text.summary)}</p>` : ""}
      ${long ? `<button type="button" class="more" data-more aria-expanded="false">${esc(tt("item.more"))}</button>` : ""}
      ${tags ? `<div class="tags">${tags}</div>` : ""}
    </article>
    <div class="sig">
      ${signals(item, sourceMap)}
      <button type="button" class="like" data-like="${item.id}" aria-pressed="${liked}"
              title="${esc(tt("like.note"))}" aria-label="${esc(tt(liked ? "like.remove" : "like.add"))}">
        ${icon("heart")}<b>${likes || ""}</b>
      </button>
    </div>
  </li>`;
}

export function renderFeed(root, endRoot, view, manifest) {
  sourceMap = new Map(manifest.sources.map((s) => [s.id, s]));
  current = view.list;
  observer?.disconnect();

  if (!current.length) {
    root.innerHTML = "";
    endRoot.innerHTML = `
      <div class="empty">
        <h3>${esc(tt("empty.title"))}</h3>
        <p>${esc(tt("empty.range"))}</p>
        <div>
          ${state.range !== "30d" && state.range !== "90d" && state.range !== "all"
            ? `<button type="button" data-widen>${esc(tt("empty.widen"))}</button>` : ""}
          <button type="button" data-reset>${esc(tt("empty.reset"))}</button>
        </div>
      </div>`;
    return;
  }

  const shown = Math.max(PAGE_SIZE, state.shown || 0);
  root.innerHTML = current.slice(0, shown).map(row).join("");
  drawEnd(root, endRoot, shown);
}

function drawEnd(root, endRoot, shown) {
  if (shown >= current.length) {
    endRoot.innerHTML = `<p class="end-note">${esc(tt("feed.end"))}</p>`;
    return;
  }
  endRoot.innerHTML = `<button type="button" class="more-btn" data-page>${esc(tt("feed.more"))}
    <span>${fmtNum(shown)} / ${fmtNum(current.length)}</span></button>`;
  observer = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) page(root, endRoot);
  }, { rootMargin: "600px" });
  observer.observe(endRoot.firstElementChild);
}

function page(root, endRoot) {
  observer?.disconnect();
  const shown = root.children.length;
  const next = current.slice(shown, shown + PAGE_SIZE);
  root.insertAdjacentHTML("beforeend", next.map(row).join(""));
  state.shown = shown + next.length;                    // yeniden çizimde konum korunur
  drawEnd(root, endRoot, state.shown);
}

export function bindFeed({ tabs, toolbar, feed, end }) {
  tabs.addEventListener("click", (e) => {
    const b = e.target.closest("[data-tab]");
    if (b) update({ tab: b.dataset.tab, shown: 0 });
  });
  toolbar.addEventListener("click", (e) => {
    const sort = e.target.closest("[data-sort]");
    if (sort) return update({ sort: sort.dataset.sort, shown: 0 });
    const topic = e.target.closest("[data-drop-topic]");
    if (topic) { const s = new Set(state.topics); s.delete(topic.dataset.dropTopic); return update({ topics: s, shown: 0 }); }
    if (e.target.closest("[data-drop-q]")) update({ q: "", shown: 0 });
  });
  feed.addEventListener("click", (e) => {
    const like = e.target.closest("[data-like]");
    if (like) {
      const id = +like.dataset.like;
      const on = toggleLike(id);
      const item = current.find((i) => i.id === id);
      like.setAttribute("aria-pressed", String(on));
      like.setAttribute("aria-label", tt(on ? "like.remove" : "like.add"));
      like.querySelector("b").textContent = likeCount(item) || "";
      return;
    }
    const more = e.target.closest("[data-more]");
    if (more) {
      const sum = more.previousElementSibling;
      const open = sum.classList.toggle("clamp") === false;
      more.setAttribute("aria-expanded", String(open));
      more.textContent = tt(open ? "item.less" : "item.more");
      return;
    }
    const tag = e.target.closest("[data-topic]");
    if (tag) { update({ topics: new Set([tag.dataset.topic]), shown: 0 }); scrollTo({ top: 0, behavior: "smooth" }); }
  });
  end.addEventListener("click", (e) => {
    if (e.target.closest("[data-page]")) return page(feed, end);
    if (e.target.closest("[data-widen]")) return update({ range: "30d", from: null, to: null });
    if (e.target.closest("[data-reset]")) resetFilters();
  });
}
