// Üst çubuk: marka, arama, tarih aralığı (sağ üst), dil.
import { DEFAULT_RANGE, LANGS, RANGES } from "../config.js";
import { dayKey, esc } from "../format.js";
import { getLang, tt } from "../i18n.js";
import { icon } from "../icons.js";
import { forgetKey } from "../data.js";
import { rangeBounds, resetFilters, state, update } from "../state.js";

let onLang = () => {};

export function renderTopbar(root, { onLangChange, locked = false }) {
  onLang = onLangChange;
  root.innerHTML = `
    <a class="brand" href="./" data-home>
      <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden="true">
        <ellipse cx="16" cy="16" rx="12.500" ry="5" fill="none" stroke="currentColor" stroke-width="1.600" transform="rotate(-28 16 16)"/>
        <circle cx="16" cy="16" r="3.400" fill="currentColor"/>
        <circle cx="26.200" cy="9.600" r="1.700" fill="var(--text)"/>
      </svg>
      <span>${esc(tt("brand"))}</span>
    </a>
    <label class="search">
      <span class="sr-only">${esc(tt("search.label"))}</span>
      ${icon("search")}
      <input id="q" type="search" autocomplete="off" spellcheck="false"
             placeholder="${esc(tt("search.placeholder"))}" value="${esc(state.q)}">
    </label>
    <div class="range" role="group" aria-label="${esc(tt("range.label"))}">
      ${RANGES.map((r) => `<button type="button" data-range="${r.id}">${esc(tt(`range.${r.id}`))}</button>`).join("")}
      <button type="button" data-range="custom" aria-expanded="false" aria-controls="range-pop">
        ${icon("calendar")}<span>${esc(tt("range.custom"))}</span>
      </button>
      <form class="range-pop" id="range-pop" hidden>
        <label>${esc(tt("range.from"))}<input type="date" name="from" required></label>
        <label>${esc(tt("range.to"))}<input type="date" name="to" required></label>
        <button type="submit">${esc(tt("range.apply"))}</button>
      </form>
    </div>
    <div class="lang" role="group" aria-label="${esc(tt("lang.label"))}">
      ${LANGS.map((l) => `<button type="button" data-lang="${l}" aria-pressed="${l === getLang()}">${l.toUpperCase()}</button>`).join("")}
    </div>
    ${locked ? `<button type="button" class="lock-btn" data-lock title="${esc(tt("gate.lock"))}" aria-label="${esc(tt("gate.lock"))}">${icon("lock")}</button>` : ""}`;

  root.querySelector("[data-lock]")?.addEventListener("click", () => { forgetKey(); location.reload(); });

  const pop = root.querySelector("#range-pop");
  const customBtn = root.querySelector('[data-range="custom"]');
  const closePop = () => { pop.hidden = true; customBtn.setAttribute("aria-expanded", "false"); };

  root.querySelector("[data-home]").addEventListener("click", (e) => {
    e.preventDefault();
    root.querySelector("#q").value = "";
    update({ range: DEFAULT_RANGE, from: null, to: null, sort: "new" }, { silent: true });
    resetFilters();
  });

  let timer;
  root.querySelector("#q").addEventListener("input", (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => update({ q: e.target.value.trim(), shown: 0 }), 160);
  });

  root.querySelector(".range").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-range]");
    if (!btn) return;
    if (btn.dataset.range !== "custom") { closePop(); update({ range: btn.dataset.range, from: null, to: null, shown: 0 }); return; }
    if (pop.hidden) {                                   // alanları geçerli aralıkla doldur
      const b = rangeBounds();
      pop.elements.from.value = state.from ?? dayKey(b.from ?? new Date(Date.now() - 6 * 864e5));
      pop.elements.to.value = state.to ?? dayKey(new Date());
      pop.hidden = false; customBtn.setAttribute("aria-expanded", "true");
      pop.elements.from.focus();
    } else closePop();
  });
  pop.addEventListener("submit", (e) => {
    e.preventDefault();
    let { from, to } = pop.elements;
    let a = from.value, b = to.value;
    if (a > b) [a, b] = [b, a];
    closePop();
    update({ range: "custom", from: a, to: b, shown: 0 });
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePop(); });
  document.addEventListener("click", (e) => { if (!e.target.closest(".range")) closePop(); });

  root.querySelector(".lang").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-lang]");
    if (btn && btn.dataset.lang !== getLang()) onLang(btn.dataset.lang);
  });
  syncTopbar(root);
}

// Durum değişince yalnızca etkin düğmeleri günceller (arama kutusunun odağı korunur).
export function syncTopbar(root) {
  for (const b of root.querySelectorAll("[data-range]")) b.setAttribute("aria-pressed", String(b.dataset.range === state.range));
  const q = root.querySelector("#q");
  if (q && document.activeElement !== q) q.value = state.q;
}
