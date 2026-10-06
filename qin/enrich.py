"""İçerik türü, konu etiketleri ve araç sinyali kuralları.

Hepsi düzenlenebilir anahtar kelime kurallarıdır. Konu etiketleri ve araç sinyali
dışa aktarma sırasında yeniden hesaplanır; yani burada bir kuralı değiştirmek,
arşivdeki eski öğelere de bir sonraki `qin export` ile yansır.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .common import Item

PAPER_HOSTS = (
    "ssrn.com", "arxiv.org", "sciencedirect.com", "academic.oup.com", "nber.org", "jstor.org",
    "wiley.com", "tandfonline.com", "springer.com", "doi.org", "repec.org", "researchgate.net",
    "pm-research.com", "cambridge.org", "mdpi.com", "aeaweb.org",
)
VIDEO_HOSTS = ("youtube.com", "youtu.be", "spotify.com", "podcasts.apple.com", "vimeo.com",
               "soundcloud.com", "buzzsprout.com", "libsyn.com")

# Konu etiketleri: etiket -> düzenli ifade (başlık + özet üzerinde, büyük/küçük harf duyarsız)
TOPICS: dict[str, str] = {
    "LLM/AI": r"\b(llms?|large language models?|gpt|chatgpt|claude|agentic|ai agents?|generative ai|transformers?)\b",
    "Makine öğrenmesi": r"\b(machine learning|neural net\w*|xgboost|lightgbm|deep learning|random forest|gradient boost\w*)\b",
    "Reinforcement learning": r"reinforcement learning",
    "Opsiyon/Volatilite": r"\b(options?|implied vol\w*|volatility|vix|0-?dte|gamma|skew)\b",
    "Mikroyapı/Execution": r"microstructure|order ?book|order flow|\bexecution\b|market impact|transaction costs?|\bhft\b|high[- ]frequency",
    "Faktör/Anomali": r"\bfactors?\b|anomal\w*|cross[- ]section\w*|momentum|value premium",
    "Trend/CTA": r"trend[- ]following|\bcta\b|managed futures|time[- ]series momentum",
    "Portföy/Risk": r"portfolio|allocation|risk parity|drawdown|position sizing|kelly",
    "Kripto": r"crypto\w*|bitcoin|\bbtc\b|ethereum|perpetual",
    "Backtest/Overfitting": r"backtest\w*|overfit\w*|look[- ]ahead|survivorship|walk[- ]forward|data snooping",
    "Makro/Faiz": r"\bmacro\w*|inflation|interest rates?|yield curve|fomc|treasur(y|ies)",
    "Tahmin piyasaları": r"prediction markets?|kalshi|polymarket",
}
_TOPICS = {k: re.compile(v, re.I) for k, v in TOPICS.items()}
TOPIC_LABELS = set(TOPICS)

TOOL_TAG = "Araç sinyali"

# ---- Araç sinyali ------------------------------------------------------------
# Amaç: yeni/kullanılabilir bir araç, kütüphane, platform veya veri seti duyuran içerik.
# İş ilanı, haber ve etkinlikler hiçbir zaman araç sayılmaz ("trading platform" tanıtımları).
NOT_TOOL_KINDS = {"iş ilanı", "haber", "etkinlik"}

# Başlıkta geçmesi yeterli olan güçlü kelimeler
_TOOL_TITLE = re.compile(
    r"open[- ]?sourc\w*|\b(librar(y|ies)|package|framework|toolkit|toolbox|sdk|api|mcp|plugin|"
    r"dashboard|backtester|platform|terminal|simulator|dataset|benchmark|app)\b|"
    r"\b(launch(es|ed|ing)?|introducing|releas(e|ed|ing)|announcing)\b|\bv\d+\.\d+|github", re.I)
# Özette geçerse sayılan, daha açık ifadeler ("platform" gibi tek kelimeler burada yetmez)
_TOOL_SUMMARY = re.compile(
    r"open[- ]sourc\w*|python (package|library|class|module)|\br package\b|github\.com|pip install|"
    r"\b(we|i)( have| just|'ve)? (built|released|launched|open[- ]sourced|published|made)\b|"
    r"now available|introducing|new (tool|platform|library|feature|report|api|dataset|app)\b|"
    r"free (tool|api|dataset|platform)", re.I)
# Makalelerde "we introduce a framework" kalıbı çok yaygın; yalnızca somut çıktı kelimeleri sayılır
_TOOL_PAPER = re.compile(
    r"open[- ]?sourc\w*|\b(librar(y|ies)|toolkit|toolbox|simulator|benchmark|dataset|platform|package)\b|"
    r"github", re.I)


def is_tool(title: str, summary: str | None, kind: str | None) -> bool:
    if kind in NOT_TOOL_KINDS:
        return False
    if kind == "makale":
        return bool(_TOOL_PAPER.search(title or ""))
    return bool(_TOOL_TITLE.search(title or "") or _TOOL_SUMMARY.search(summary or ""))


def topics(title: str, summary: str | None) -> list[str]:
    text = f"{title} {summary or ''}"
    return [label for label, rx in _TOPICS.items() if rx.search(text)]


def classify(it: Item, source: str) -> str:
    host = urlparse(it.url or it.source_url).netloc.lower()
    sec = (it.section or "").lower()
    hint = it.hint or ""
    if source == "arxiv" or any(h in host for h in PAPER_HOSTS):
        return "makale"
    if any(h in host for h in VIDEO_HOSTS) or re.search(r"podcast|video", sec):
        return "video/podcast"
    if hint == "📰" or re.search(r"\bnews\b|headline|haber", sec):
        return "haber"
    if hint == "📆" or re.search(r"event|etkinlik|conference|webinar", sec):
        return "etkinlik"
    if hint == "✨" or re.search(r"\bjobs?\b|intern|career|position|full[- ]time|hiring", sec):
        return "iş ilanı"
    if source.startswith("reddit"):
        return "tartışma"
    return "yazı"


def enrich(it: Item, source: str) -> None:
    it.kind = it.kind or classify(it, source)
    tags = topics(it.title, it.summary)
    if is_tool(it.title, it.summary, it.kind):
        tags.append(TOOL_TAG)
    for t in it.tags:                      # kaynaktan gelen etiketler (Quantpedia, arXiv kategorisi)
        if t and t not in tags:
            tags.append(t)
    it.tags = tags[:14]


def source_tags(stored: str | None) -> list[str]:
    """Kayıtlı etiketlerden yalnızca kaynağın kendi verdiği etiketleri ayırır."""
    out = []
    for t in (stored or "").split(","):
        t = t.strip()
        if t and t not in TOPIC_LABELS and t != TOOL_TAG:
            out.append(t)
    return out
