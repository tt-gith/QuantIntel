// Sitenin ayar dosyası. Yeni sekme, tarih seçeneği ya da popülerlik ölçümü eklemek için
// çoğu zaman yalnızca bu dosyaya bir satır eklemek yeterlidir.

// Sağ üstteki tarih seçenekleri. days yoksa "tüm zamanlar".
export const RANGES = [
  { id: "7d", days: 7 },
  { id: "30d", days: 30 },
  { id: "90d", days: 90 },
  { id: "all" },
];
export const DEFAULT_RANGE = "7d";

// Sekmeler. kinds: veritabanındaki tür adları. test: özel kural.
// Yeni sekme: buraya bir satır + i18n dosyalarına "tab.<id>" çevirisi.
export const TABS = [
  { id: "all", test: (i) => i.k !== "iş ilanı" },        // akış: ilanlar hariç her şey
  { id: "briefs", view: "briefs", test: () => false },   // günlük/haftalık özetler: liste yerine okuma görünümü
  { id: "papers", kinds: ["makale"] },
  { id: "posts", kinds: ["yazı"] },
  { id: "media", kinds: ["video/podcast"] },
  { id: "tools", test: (i) => !!i.tool },
  { id: "events", kinds: ["etkinlik"] },
  { id: "news", kinds: ["haber"] },
  { id: "talk", kinds: ["tartışma"] },
  { id: "jobs", kinds: ["iş ilanı"] },
];
for (const t of TABS) if (!t.test) t.test = (i) => t.kinds.includes(i.k);

// Öğelerin yanında gösterilen popülerlik ölçümleri (veritabanındaki kısa ad -> ikon).
// Yeni ölçüm: qin/metrics.py'de üret, buraya bir satır ekle, i18n'e "metric.<ad>" yaz.
export const METRICS = [
  { key: "up", icon: "up" },         // Reddit oyu
  { key: "cm", icon: "comment" },    // yorum
  { key: "cit", icon: "cite" },      // akademik atıf
  { key: "views", icon: "eye" },     // görüntülenme (ileride: YouTube)
];

// Güvertedeki "öne çıkanlar" vitrini. Akış sekmesinde her gruptan en güçlü içerik seçilir;
// böylece vitrin tek bir kaynağın (ör. Reddit oylarının) hâkimiyetine girmez.
// Sıra önemlidir: bir içerik ilk uyduğu grupta sayılır. label: i18n anahtarı.
export const SPOTLIGHT_GROUPS = [
  { label: "spot.tool", test: (i) => !!i.tool },
  { label: "kind.makale", test: (i) => i.k === "makale" },
  { label: "kind.yazı", test: (i) => i.k === "yazı" },
  { label: "kind.tartışma", test: (i) => i.k === "tartışma" },
  { label: "kind.video/podcast", test: (i) => i.k === "video/podcast" },
  { label: "kind.etkinlik", test: (i) => i.k === "etkinlik" },
  { label: "kind.haber", test: (i) => i.k === "haber" },
];
export const SPOTLIGHT_SIZE = 5;     // bir büyük kart + dört satır

// "LLM için dışa aktar": bir içeriğin özetinden en fazla kaç karakter alınacağı.
export const EXPORT_SUMMARY_CHARS = 700;
export const BRIEF_TEASER_DAYS = 8;  // güvertede "yeni özet" satırı bu kadar gün görünür

export const SORTS = ["new", "pop"];
export const PAGE_SIZE = 40;         // listede bir seferde gösterilen öğe
export const STALE_DAYS = 21;        // bir kaynak bu kadar gün sessizse uyarı ışığı yanar
export const DEFAULT_LANG = "tr";
export const LANGS = ["tr", "en"];
