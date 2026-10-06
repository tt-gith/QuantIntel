"""Günlük ve haftalık özetlerin LLM ile üretilmesi.

Akış: dönemin içerikleri seçilir (popülerlik puanı + tür çeşitliliği), numaralı bir liste olarak
modele verilir, model yalnızca bu listeye dayanarak Türkçe bir özet yazar ve her iddiada içerik
numarasını verir ([3]). Numaralar sonra bağlantıya çevrilir; böylece özet her zaman kaynağına iner.

Özetler `briefs` tablosunda durur. Her dönem için en fazla bir otomatik özet üretilir;
e-posta gönderimi burada YAPILMAZ (yalnızca yönetim panelindeki "özeti yayınla" ile).
"""
from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta, timezone

from .common import iso, now_utc, shorten
from .llm import LLM, LLMUnavailable, strip_fence
from .storage import DB

log = logging.getLogger("qin")

KINDS = ("daily", "weekly")
SKIP_KINDS = {"iş ilanı"}
MONTHS_TR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim",
             "Kasım", "Aralık"]
KIND_LABELS = {"makale": "Makale", "yazı": "Yazı", "video/podcast": "Video/podcast", "etkinlik": "Etkinlik",
               "haber": "Haber", "tartışma": "Tartışma"}

SYSTEM = """Sen kantitatif finans alanında çalışan deneyimli bir araştırmacısın ve meslektaşların için \
{label} bir bülten yazıyorsun. Okur: algoritmik trading ve quant araştırma yapan, zamanı kısıtlı bir \
profesyonel. Amaç: bu dönemde yayınlanan içeriklerden hangilerinin gerçekten önemli olduğunu ona beş \
dakikada kavratmak.

Kurallar:
- Yalnızca sana verilen içerik listesine dayan. Listede yazmayan bir bilgi, sayı, sonuç ya da isim ekleme; \
özetinde geçmeyen bir bulguyu tahmin etme. Özeti olmayan içerik için yalnızca başlığından anlaşılanı söyle.
- Bir içerikten söz ettiğin her cümlenin sonunda numarasını köşeli parantezle ver: [3] ya da [3][7].
- Hepsini sıralama. Önemli olanları seç, birbirine benzeyenleri aynı başlık altında birleştir ve okur için \
neden önemli olduğunu söyle.
- "sinyal" satırı ilgiyi gösterir (kaç kaynakta geçtiği, oy, atıf, çok tıklanma); öncelik verirken kullan.
- Türkçe yaz. Yerleşik Türkçe karşılığı olmayan terimleri İngilizce bırak (backtest, momentum, order book, \
overfitting...). Kişi, kurum ve ürün adlarını çevirme.
- Yatırım tavsiyesi verme. Abartılı sıfat ve dolgu cümle kullanma.
- Uzunluk: yaklaşık {words} kelime.

Biçim: yalnızca aşağıdaki düzende Markdown yaz, öncesine ya da sonrasına açıklama ekleme.

# <dönemin en önemli gelişmesini anlatan tek satırlık başlık>

**Kısaca**
- <en önemli üç çıkarım, her biri tek cümle>

## <tema başlığı>
<bir iki kısa paragraf>

(iki ile dört tema)

## Denemeye değer
- <araç, kütüphane, veri seti ya da kod içeren içerikler; yoksa bu bölümü hiç yazma>

## Radar
- <kısaca anılmaya değer diğer içerikler, birer satır>"""


# ------------------------------------------------------------------ dönemler
def local_now(cfg: dict, now: datetime | None = None) -> datetime:
    tz = timezone(timedelta(hours=cfg.get("utc_offset_hours", 3)))     # Türkiye yıl boyu UTC+3
    return (now or now_utc()).astimezone(tz)


def week_key(day) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_bounds(key: str, tz) -> tuple[datetime, datetime]:
    year, week = key.split("-W")
    start = datetime.fromisocalendar(int(year), int(week), 1).replace(tzinfo=tz)
    return start, start + timedelta(days=7)


def fmt_day(d) -> str:
    return f"{d.day} {MONTHS_TR[d.month - 1]} {d.year}"


def period_label(kind: str, period: str) -> str:
    """Okunur dönem adı: '6 Ekim 2026' ya da '28 Eylül – 4 Ekim 2026'."""
    if kind == "daily":
        return fmt_day(datetime.strptime(period, "%Y-%m-%d"))
    start, end = week_bounds(period, timezone.utc)
    last = end - timedelta(days=1)
    first = f"{start.day} {MONTHS_TR[start.month - 1]}" + (f" {start.year}" if start.year != last.year else "")
    return f"{first} – {fmt_day(last)}"


def manual_period(kind: str, day: str) -> str:
    """Elle eklenen özetin dönemi: verilen günün kendisi ya da içinde bulunduğu hafta."""
    d = datetime.strptime(day, "%Y-%m-%d")
    return day if kind == "daily" else week_key(d)


def due(db: DB, cfg: dict, kind: str, now: datetime | None = None) -> tuple[str, str, str]:
    """(dönem, pencere başı, pencere sonu). Pencere sınırları UTC ISO metnidir."""
    here = local_now(cfg, now)
    if kind == "weekly":                                  # tamamlanmış son hafta (Pzt–Paz)
        period = week_key(here.date() - timedelta(days=7))
        start, end = week_bounds(period, here.tzinfo)
        return period, iso(start), iso(end)
    period = here.strftime("%Y-%m-%d")
    last = db.conn.execute(
        "SELECT MAX(created_at) FROM briefs WHERE kind='daily' AND origin='llm' AND period < ?", (period,)
    ).fetchone()[0]
    floor = iso(here - timedelta(hours=72))
    start = max(last, floor) if last else iso(here - timedelta(hours=30))
    return period, start, iso(here)


# ------------------------------------------------------------------ içerik seçimi
def candidates(items: list[dict], kind: str, start: str, end: str, now: datetime | None = None) -> list[dict]:
    """Döneme giren içerikler. Günlükte ölçüt içeriğin arşive ilk girdiği andır (yeni gelenler);
    haftalıkta yayın tarihidir."""
    pool = [i for i in items if i["k"] not in SKIP_KINDS]
    if kind == "weekly":
        return [i for i in pool if start <= i["d"] < end]
    fresh = iso((now or now_utc()) - timedelta(days=7))   # eski tarihli geriye dönük kayıtlar "yeni" sayılmaz
    return [i for i in pool if start < i.get("_seen", i["d"]) <= end and i["d"] >= fresh]


def _strength(i: dict) -> float:
    return i.get("p", 0) + (10 if i.get("s") else 0) + (10 if i.get("tool") else 0) + (5 if i.get("hot") else 0)


def select(pool: list[dict], max_items: int) -> list[dict]:
    """En güçlü içerikler; tek bir tür listenin yarısından, tartışmalar dörtte birinden fazlasını kaplamaz."""
    caps = {"tartışma": math.ceil(max_items / 4)}
    default_cap = math.ceil(max_items / 2)
    used: dict[str, int] = {}
    picked, rest = [], []
    for i in sorted(pool, key=lambda i: (_strength(i), i["d"]), reverse=True):
        if used.get(i["k"], 0) < caps.get(i["k"], default_cap):
            used[i["k"]] = used.get(i["k"], 0) + 1
            picked.append(i)
        else:
            rest.append(i)
    return (picked + rest)[:max_items]                    # az içerik varsa tavanlar esner


def _signal(i: dict) -> str:
    m = i.get("m", {})
    parts = []
    if len(i["src"]) > 1:
        parts.append(f"{len(i['src'])} kaynakta")
    if m.get("up"):
        parts.append(f"{m['up']} oy")
    if m.get("cm"):
        parts.append(f"{m['cm']} yorum")
    if m.get("cit"):
        parts.append(f"{m['cit']} atıf")
    if i.get("hot"):
        parts.append("çok tıklanan")
    if i.get("tool"):
        parts.append("araç/kod içeriyor")
    return ", ".join(parts)


def _entry(n: int, i: dict, labels: dict[str, str], summary_chars: int) -> str:
    srcs = ", ".join(labels.get(s, s) for s in i["src"])
    head = f"[{n}] {KIND_LABELS.get(i['k'], i['k'])} | {srcs} | {i['d'][:10]}"
    sig = _signal(i)
    lines = [head + (f" | sinyal: {sig}" if sig else ""), f"Başlık: {i['t']}"]
    if i.get("o"):
        lines.append(f"Yazar/yayıncı: {shorten(i['o'], 120)}")
    if i.get("s"):
        lines.append(f"Özet: {shorten(i['s'], summary_chars)}")
    return "\n".join(lines)


def listing(picked: list[dict], labels: dict[str, str], max_chars: int, summary_chars: int) -> tuple[str, list[dict]]:
    """Modele verilecek numaralı liste. Sığmazsa önce özetler kısalır, sonra sondaki içerikler düşer."""
    picked = list(picked)
    while True:
        text = "\n\n".join(_entry(n, i, labels, summary_chars) for n, i in enumerate(picked, 1))
        if len(text) <= max_chars or (summary_chars <= 140 and len(picked) <= 4):
            return text, picked
        if summary_chars > 140:
            summary_chars = max(140, int(summary_chars * 0.8))
        else:
            picked.pop()


# ------------------------------------------------------------------ yanıtın işlenmesi
_CITE_GROUP = re.compile(r"\[(\d{1,3}(?:\s*[,;]\s*\d{1,3})+)\]")
_CITE = re.compile(r"\[(\d{1,3})\](?!\()")
_HEADING = re.compile(r"^#{1,3}\s+(.+?)\s*#*\s*$")


def finish(text: str, picked: list[dict], labels: dict[str, str], fallback_title: str) -> tuple[str, str]:
    """Model yanıtından (başlık, gövde) üretir: atıf numaralarını bağlantıya çevirir, kaynakçayı ekler."""
    lines = strip_fence(text).splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    title = fallback_title
    if lines and (m := _HEADING.match(lines[0])) and lines[0].startswith("# "):
        title = m.group(1).strip("* ")
        lines.pop(0)
    body = "\n".join(lines).strip()

    body = _CITE_GROUP.sub(lambda m: "".join(f"[{n.strip()}]" for n in re.split(r"[,;]", m.group(1))), body)
    cited: list[int] = []

    def link(m: re.Match) -> str:
        n = int(m.group(1))
        if not 1 <= n <= len(picked):
            return ""                                     # listede olmayan numara: uydurma atıf, at
        if n not in cited:
            cited.append(n)
        return f"[{n}]({picked[n - 1]['u']})"

    body = _CITE.sub(link, body)
    if len(body) < 300 or not cited:
        raise ValueError("model yanıtı beklenen biçimde değil (çok kısa ya da atıfsız)")
    plain = str.maketrans({"[": "(", "]": ")"})          # başlıktaki köşeli parantez bağlantıyı bozmasın
    refs = [f"- **[{n}]** [{picked[n - 1]['t'].translate(plain)}]({picked[n - 1]['u']}) · "
            + ", ".join(labels.get(s, s) for s in picked[n - 1]["src"]) for n in sorted(cited)]
    return title[:200], body + "\n\n## Bu özetteki içerikler\n" + "\n".join(refs)


# ------------------------------------------------------------------ üretim
def source_labels(cfg: dict) -> dict[str, str]:
    labels = {n: s.get("label", n) for n, s in cfg["sources"].items()}
    labels["arxiv"] = cfg.get("arxiv", {}).get("label", "arXiv")
    return labels


def generate(db: DB, cfg: dict, llm: LLM, items: list[dict], kind: str,
             now: datetime | None = None, force: bool = False) -> str:
    """Dönemi gelmiş özeti üretir ve kaydeder. Ne olduğunu anlatan tek satır döndürür."""
    bcfg = cfg.get("llm", {}).get("briefs", {})
    name = "Günlük özet" if kind == "daily" else "Haftalık özet"
    if not bcfg.get(kind, True):
        return f"{name}: kapalı"
    period, start, end = due(db, cfg, kind, now)
    existing = db.find_brief(kind, period)
    if existing and not force:
        return f"{name}: {period} zaten var"
    pool = candidates(items, kind, start, end, now)
    need = bcfg.get(f"{kind}_min_items", 4 if kind == "daily" else 6)
    if len(pool) < need:
        return f"{name}: {period} için yeterli içerik yok ({len(pool)}/{need})"

    labels = source_labels(cfg)
    picked = select(pool, bcfg.get(f"{kind}_max_items", 16 if kind == "daily" else 28))
    text, picked = listing(picked, labels, bcfg.get("max_input_chars", 10000),
                           bcfg.get(f"{kind}_summary_chars", 480 if kind == "daily" else 300))
    label = period_label(kind, period)
    system = SYSTEM.format(label="günlük" if kind == "daily" else "haftalık",
                           words=bcfg.get(f"{kind}_words", 450 if kind == "daily" else 650))
    user = (f"Dönem: {label} ({'günlük' if kind == 'daily' else 'haftalık'})\n"
            f"Bu dönemde arşive giren içerik sayısı: {len(pool)}; en güçlü {len(picked)} tanesi aşağıda.\n\n{text}")
    try:
        reply = llm.chat(system, user, max_tokens=bcfg.get("max_output_tokens", 8000), task="brief")
        title, body = finish(reply, picked, labels, f"{name} · {label}")
    except LLMUnavailable as ex:
        return f"{name}: üretilemedi ({str(ex)[:160]})"
    except ValueError as ex:
        log.warning("%s reddedildi: %s", name, ex)
        return f"{name}: üretilemedi ({ex})"
    brief_id = db.save_brief(kind, period, "llm", title, body, model=llm.last_model,
                             brief_id=existing["id"] if existing else None)
    return f"{name}: {period} hazır (#{brief_id}, {len(picked)} içerik, {llm.last_model})"


def generate_due(db: DB, cfg: dict, llm: LLM, items: list[dict], now: datetime | None = None,
                 only: str | None = None, force: bool = False) -> list[str]:
    return [generate(db, cfg, llm, items, kind, now, force) for kind in KINDS if only in (None, kind)]
