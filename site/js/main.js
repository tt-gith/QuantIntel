// Giriş noktası: veriyi yükler, filtreleri uygular, parçaları çizer.
import { TABS } from "./config.js";
import { adminInfo, detectLock, isLocked, loadBriefs, loadManifest, loadRange, unlockFromStore } from "./data.js";
import { esc } from "./format.js";
import { savedLang, setLang, tt } from "./i18n.js";
import { onChange, rangeBounds, readHash, state, update } from "./state.js";
import { initStarfield } from "./fx/starfield.js";
import { openAdmin, resumeAdmin } from "./ui/admin.js";
import { bindBriefs, renderBriefList, renderBriefReader } from "./ui/briefs.js";
import { renderDeck } from "./ui/deck.js";
import { bindFeed, renderFeed, renderTabs, renderToolbar } from "./ui/feed.js";
import { askPassword } from "./ui/gate.js";
import { bindSide, renderSide } from "./ui/side.js";
import { renderTopbar, syncTopbar } from "./ui/topbar.js";

const $ = (id) => document.getElementById(id);
let manifest = null;
let seq = 0;

// Seçili aralıktaki öğelerden, o anki filtrelere göre ekranda gereken her şeyi hesaplar.
function compute(items) {
  const terms = state.q.toLowerCase().split(/\s+/).filter(Boolean);
  const hay = (i) => (i._hay ??= [i.t, i.s, i.o, ...(i.tg ?? []), ...(i.xt ?? []), i.tr?.tr?.t, i.tr?.tr?.s]
    .filter(Boolean).join(" ").toLowerCase());
  const matchQ = (i) => terms.every((w) => hay(i).includes(w));
  const matchSrc = (i) => !state.src.size || i.src.some((s) => state.src.has(s));
  const matchTopic = (i) => !state.topics.size || (i.tg ?? []).some((t) => state.topics.has(t));
  const tab = TABS.find((t) => t.id === state.tab) ?? TABS[0];

  const base = items.filter(matchQ);
  const filtered = base.filter((i) => matchSrc(i) && matchTopic(i));
  const tabCounts = new Map(TABS.map((t) => [t.id, filtered.filter(t.test).length]));
  const list = filtered.filter(tab.test);

  // Sol menü sayıları: her filtre kendi ekseni dışındaki seçimlere göre sayılır
  const srcCounts = new Map();
  for (const i of base) if (tab.test(i) && matchTopic(i)) for (const s of i.src) srcCounts.set(s, (srcCounts.get(s) || 0) + 1);
  const topicCounts = new Map();
  for (const i of base) if (tab.test(i) && matchSrc(i)) for (const t of i.tg ?? []) topicCounts.set(t, (topicCounts.get(t) || 0) + 1);

  if (state.sort === "pop") list.sort((a, b) => (b.p || 0) - (a.p || 0) || b.date - a.date);
  else list.sort((a, b) => b.date - a.date || b.id - a.id);

  return {
    list, tabCounts, srcCounts, topicCounts,
    activeSources: new Set(list.flatMap((i) => i.src)).size,
    multi: list.filter((i) => i.src.length > 1).length,
    tools: list.filter((i) => i.tool).length,
  };
}

async function refresh() {
  const mine = ++seq;
  const briefsView = state.tab === "briefs";              // Özetler: liste yerine okuma görünümü
  const { from, to } = rangeBounds();
  const [items, briefs] = await Promise.all([loadRange(from, to), briefsView ? loadBriefs().catch(() => []) : null]);
  if (mine !== seq) return;                               // daha yeni bir istek geldi
  const view = compute(items);
  document.body.classList.toggle("view-briefs", briefsView);
  for (const id of ["toolbar", "feed", "feed-end"]) $(id).hidden = briefsView;
  $("briefs").hidden = !briefsView;
  syncTopbar($("topbar"));
  renderDeck($("deck"), view, manifest);
  renderTabs($("tabs"), view, manifest);
  if (briefsView) {
    renderBriefList($("side"), briefs);
    renderBriefReader($("briefs"), briefs);
    return;
  }
  renderSide($("side"), view, manifest);
  renderToolbar($("toolbar"), view);
  renderFeed($("feed"), $("feed-end"), view, manifest);
}

function drawChrome() {
  renderTopbar($("topbar"), {
    locked: isLocked(),
    admin: !!adminInfo(),
    onAdmin: () => openAdmin(),
    onLangChange: async (lang) => { await setLang(lang); drawChrome(); refresh(); },
  });
}

async function boot() {
  const stars = initStarfield($("stars"));
  await setLang(savedLang());
  readHash();
  // Yayındaki site kilitlidir: saklı anahtar yoksa önce parola sorulur.
  if (await detectLock() && !(await unlockFromStore())) await askPassword();
  drawChrome();
  try {
    manifest = await loadManifest();
    if (!manifest) throw new Error("manifest yok");
  } catch {
    $("deck").innerHTML = `<div class="deck-in"><div class="empty"><h3>${esc(tt("error.title"))}</h3><p>${esc(tt("error.body"))}</p></div></div>`;
    document.body.classList.remove("is-booting");
    return;
  }
  bindSide($("side"), manifest);
  bindFeed({ tabs: $("tabs"), toolbar: $("toolbar"), feed: $("feed"), end: $("feed-end") });
  bindBriefs({ side: $("side"), main: $("briefs") });
  $("deck").addEventListener("click", (e) => {            // güvertedeki "yeni özet" satırı
    const b = e.target.closest("[data-open-brief]");
    if (!b) return;
    update({ tab: "briefs", brief: +b.dataset.openBrief });
    $("main").scrollIntoView({ block: "start", behavior: "smooth" });
  });
  await refresh();
  onChange(refresh);
  addEventListener("hashchange", () => { readHash(); refresh(); });

  // Açılış: oturumda bir kez, yıldızlar hızlanır ve paneller yerine oturur.
  let first = true;
  try { first = !sessionStorage.getItem("qin.launched"); sessionStorage.setItem("qin.launched", "1"); } catch { /* yoksay */ }
  document.body.classList.remove("is-booting");
  if (first) { document.body.classList.add("is-launching"); stars.launch(); }
  if (adminInfo()) resumeAdmin();                         // işlem sonrası yenilemede panel kaldığı yerden açılır
}

boot();
