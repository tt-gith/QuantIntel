// Uygulama durumu. Adres çubuğundaki # kısmıyla eşlenir; böylece bir görünümün
// bağlantısı (sekme, kaynak, tarih, arama) kopyalanıp paylaşılabilir.
import { DEFAULT_RANGE, RANGES, SORTS, TABS } from "./config.js";
import { DAY, parseDay, startOfDay } from "./format.js";

export const state = {
  tab: "all",
  src: new Set(),       // boş = tüm kaynaklar
  topics: new Set(),    // boş = tüm konular
  q: "",
  range: DEFAULT_RANGE, // RANGES id'si ya da "custom"
  from: null,           // custom: "YYYY-MM-DD"
  to: null,
  sort: "new",
  shown: 0,
};

const listeners = new Set();
export const onChange = (fn) => listeners.add(fn);

export function update(patch, { silent = false } = {}) {
  Object.assign(state, patch);
  writeHash();
  if (!silent) for (const fn of listeners) fn();
}

export function resetFilters() {
  update({ tab: "all", src: new Set(), topics: new Set(), q: "" });
}

// Seçili aralığın tarih sınırları (Date ya da null).
export function rangeBounds(now = new Date()) {
  if (state.range === "custom" && state.from && state.to) {
    return { from: parseDay(state.from), to: new Date(parseDay(state.to).getTime() + DAY - 1) };
  }
  const def = RANGES.find((r) => r.id === state.range);
  if (!def?.days) return { from: null, to: null };
  return { from: new Date(startOfDay(now).getTime() - (def.days - 1) * DAY), to: null };
}

function writeHash() {
  const p = new URLSearchParams();
  if (state.tab !== "all") p.set("tab", state.tab);
  if (state.src.size) p.set("src", [...state.src].join(","));
  if (state.topics.size) p.set("topic", [...state.topics].join("|"));
  if (state.q) p.set("q", state.q);
  if (state.range === "custom") { p.set("from", state.from); p.set("to", state.to); }
  else if (state.range !== DEFAULT_RANGE) p.set("range", state.range);
  if (state.sort !== "new") p.set("sort", state.sort);
  const hash = p.toString();
  history.replaceState(null, "", hash ? `#${hash}` : location.pathname + location.search);
}

export function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  const day = /^\d{4}-\d{2}-\d{2}$/;
  state.tab = TABS.some((t) => t.id === p.get("tab")) ? p.get("tab") : "all";
  state.src = new Set((p.get("src") || "").split(",").filter(Boolean));
  state.topics = new Set((p.get("topic") || "").split("|").filter(Boolean));
  state.q = p.get("q") || "";
  state.sort = SORTS.includes(p.get("sort")) ? p.get("sort") : "new";
  if (day.test(p.get("from") || "") && day.test(p.get("to") || "")) {
    state.range = "custom"; state.from = p.get("from"); state.to = p.get("to");
  } else {
    state.range = RANGES.some((r) => r.id === p.get("range")) ? p.get("range") : DEFAULT_RANGE;
    state.from = state.to = null;
  }
}
