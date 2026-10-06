"""Ortak yardımcılar: ayarlar, tarih, metin, veri modeli."""
from __future__ import annotations

import calendar
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- ayarlar
def load_config(path: Path | None = None) -> dict:
    path = path or ROOT / "config.json"
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    for key in ("db_path", "digest_dir", "log_dir"):
        p = Path(cfg[key])
        cfg[key] = p if p.is_absolute() else ROOT / p
    return cfg


# ---------------------------------------------------------------- tarih
def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def struct_to_iso(st) -> str | None:
    if not st:
        return None
    return iso(datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc))


def days_ago_iso(days: int, end: datetime | None = None) -> str:
    return iso((end or now_utc()) - timedelta(days=days))


# ---------------------------------------------------------------- metin
_WS = re.compile(r"\s+")


def clean(text: str | None) -> str:
    if not text:
        return ""
    return _WS.sub(" ", text).strip()


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    return clean(BeautifulSoup(html, "html.parser").get_text(" "))


def norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (title or "").lower())


def shorten(text: str | None, limit: int) -> str:
    text = clean(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + " …"


# ---------------------------------------------------------------- model
@dataclass
class Item:
    """Bir beslemeden çıkarılmış tekil içerik (makale, yazı, video, etkinlik...)."""
    title: str
    source_url: str              # beslemede göründüğü haliyle link (tekilleştirme anahtarı)
    url: str | None = None       # çözülmüş/nihai link
    origin: str | None = None    # orijinal yayıncı / yazarlar
    section: str | None = None   # bülten içindeki bölüm başlığı
    kind: str | None = None      # makale, yazı, video/podcast, etkinlik, iş ilanı, tartışma
    summary: str | None = None
    published: str | None = None
    tags: list[str] = field(default_factory=list)
    hint: str | None = None      # ayrıştırıcıdan gelen ipucu (ör. emoji)
    popular: bool = False        # bültenin "en popülerler" bölümünde yeniden listelenmiş
    metrics: dict = field(default_factory=dict)   # ör. {"up": 214, "cm": 38}


@dataclass
class Post:
    """Beslemedeki ham kayıt (bülten sayısı, günlük özet, blog yazısı...)."""
    guid: str
    title: str
    url: str | None
    published: str | None
    raw_html: str = ""
    items: list[Item] = field(default_factory=list)
