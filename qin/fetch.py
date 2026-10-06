"""Kaynakları indirir, ayrıştırır ve veritabanına yazar."""
from __future__ import annotations

import json
import logging
import re
import time
from urllib.parse import urlencode, urlparse

import feedparser
import requests

from .common import Item, Post
from .enrich import enrich
from .parsers import PARSERS, parse_arxiv, parse_reddit_json
from .storage import DB

log = logging.getLogger("qin")

ACCEPT = "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5"
ARXIV_API = "https://export.arxiv.org/api/query"
_REDDIT_ID = re.compile(r"/comments/([a-z0-9]+)/")


def make_session(cfg: dict) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": cfg["user_agent"], "Accept": ACCEPT})
    return s


def http_get(session: requests.Session, url: str, tries: int = 3, accept: str | None = None) -> bytes:
    last = None
    headers = {"Accept": accept} if accept else None
    for attempt in range(tries):
        try:
            r = session.get(url, timeout=30, headers=headers)
            if r.status_code == 429 or r.status_code >= 500:
                last = RuntimeError(f"HTTP {r.status_code}")
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.content
        except requests.RequestException as ex:
            last = ex
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"{urlparse(url).netloc} indirilemedi: {last}")


def resolve_redirect(session: requests.Session, url: str) -> str:
    """Quantocracy yönlendirme linkini orijinal yazı adresine çevirir (başarısızsa aynen döner)."""
    for method in ("head", "get"):
        try:
            r = getattr(session, method)(url, allow_redirects=True, timeout=20, stream=(method == "get"))
            final = r.url
            r.close()
            if final and "quantocracy.com" not in urlparse(final).netloc:
                return final
        except requests.RequestException:
            continue
    return url


def _parse_feed(content: bytes):
    feed = feedparser.parse(content, sanitize_html=False)  # sınıf/data özniteliklerini korur
    if feed.bozo and not feed.entries:
        raise RuntimeError(f"Besleme okunamadı: {feed.get('bozo_exception')}")
    return feed


def _find_existing(db: DB, source: str, it: Item) -> int | None:
    item_id = db.item_id(source, it.source_url)
    if item_id is None and source.startswith("reddit"):
        m = _REDDIT_ID.search(it.source_url)
        if m:  # RSS ve JSON aynı gönderiyi farklı yazımla verebilir
            item_id = db.item_id_like(source, f"%/comments/{m.group(1)}/%")
    return item_id


def store_posts(db: DB, source: str, posts: list[Post], session=None, resolve=False) -> tuple[int, int]:
    """Kayıtları eskiden yeniye işler; böylece bir öğe ilk göründüğü sayının tarihini ve bölümünü alır."""
    new_posts = new_items = 0
    for post in sorted(posts, key=lambda p: p.published or ""):
        post_id, is_new = db.upsert_post(source, post)
        new_posts += int(is_new)
        for it in post.items:
            if not it.source_url or not it.title:
                continue
            item_id = _find_existing(db, source, it)
            if item_id is None:
                it.url = it.url or it.source_url
                if resolve and session is not None and "redirect.php" in it.source_url:
                    it.url = resolve_redirect(session, it.source_url)
                it.published = it.published or post.published
                enrich(it, source)
                item_id = db.insert_item(source, post_id, it)
                new_items += int(item_id is not None)
            if item_id is None:
                continue
            if it.popular:      # bültenin "geçen haftanın en popülerleri" bölümünde yeniden listelenmiş
                db.set_metric(item_id, "hot", 1)
            for metric, value in it.metrics.items():
                if value is not None:
                    db.set_metric(item_id, metric, value)
    db.commit()
    return new_posts, new_items


def _reddit_json_url(scfg: dict) -> str:
    if scfg.get("json_url"):
        return scfg["json_url"]
    base, _, query = scfg["url"].partition("?")
    base = re.sub(r"/?\.rss$", "", base).rstrip("/")
    return f"{base}.json?{query}&limit=25&raw_json=1" if query else f"{base}.json?limit=25&raw_json=1"


def _load_posts(session, name: str, scfg: dict) -> tuple[list[Post], str]:
    """Kaynağın kayıtlarını indirir. Reddit'te önce oy sayılı JSON denenir, olmazsa RSS."""
    if scfg["type"] == "reddit":
        try:
            raw = http_get(session, _reddit_json_url(scfg), tries=2, accept="application/json")
            return parse_reddit_json(json.loads(raw), scfg), "json"
        except Exception as ex:
            log.warning("%s: JSON alınamadı (%s), RSS'e düşülüyor", name, str(ex)[-120:])
    feed = _parse_feed(http_get(session, scfg["url"]))
    return PARSERS[scfg["type"]](feed, scfg), "rss"


def fetch_feed_source(db: DB, cfg: dict, name: str, scfg: dict, session) -> str:
    label = scfg.get("label", name)
    try:
        posts, via = _load_posts(session, name, scfg)
        resolve = scfg["type"] == "quantocracy" and cfg.get("resolve_quantocracy_redirects", True)
        np, ni = store_posts(db, name, posts, session, resolve)
        db.log_fetch(name, True, np, ni)
        note = "  (oy sayıları alınamadı)" if scfg["type"] == "reddit" and via == "rss" else ""
        return f"{label:<38} OK   {len(posts):>3} kayıt, {np:>3} yeni sayı, {ni:>4} yeni öğe{note}"
    except Exception as ex:  # bir kaynak bozulsa da diğerleri çalışmaya devam eder
        log.exception("%s başarısız", name)
        db.log_fetch(name, False, error=str(ex)[:500])
        return f"{label:<38} HATA {str(ex)[-160:]}"


def arxiv_url(acfg: dict, query: str) -> str:
    cats = " OR ".join(f"cat:{c}" for c in acfg["categories"])
    params = {
        "search_query": f"({cats}) AND ({query})",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "start": 0,
        "max_results": acfg.get("max_results_per_query", 40),
    }
    return f"{ARXIV_API}?{urlencode(params)}"


def fetch_arxiv(db: DB, cfg: dict, session) -> list[str]:
    acfg = cfg["arxiv"]
    lines = []
    total_np = total_ni = 0
    errors = []
    for i, (label, query) in enumerate(acfg["queries"].items()):
        if i:
            time.sleep(3.5)  # arXiv API kuralı: istekler arasında en az 3 sn
        try:
            feed = _parse_feed(http_get(session, arxiv_url(acfg, query)))
            np, ni = store_posts(db, "arxiv", parse_arxiv(feed, label))
            total_np += np
            total_ni += ni
            lines.append(f"  arXiv · {label:<30} {len(feed.entries):>3} sonuç, {ni:>3} yeni")
        except Exception as ex:
            log.exception("arXiv '%s' başarısız", label)
            errors.append(f"{label}: {ex}")
            lines.append(f"  arXiv · {label:<30} HATA {str(ex)[-160:]}")
    db.log_fetch("arxiv", not errors, total_np, total_ni, "; ".join(errors)[:500] or None)
    return lines


def fetch_all(db: DB, cfg: dict, only: list[str] | None = None) -> list[str]:
    session = make_session(cfg)
    out = []
    for name, scfg in cfg["sources"].items():
        if not scfg.get("enabled", True) or (only and name not in only):
            continue
        out.append(fetch_feed_source(db, cfg, name, scfg, session))
    if cfg.get("arxiv", {}).get("enabled") and (not only or "arxiv" in only):
        out.extend(fetch_arxiv(db, cfg, session))
    return out


# ---------------------------------------------------------------- onarım
def reparse(db: DB, cfg: dict) -> int:
    """Kayıtlı ham HTML'den Substack bültenlerini yeniden ayrıştırır.

    Ayrıştırma kuralı değiştiğinde ya da eski sürümün bıraktığı hataları
    (ör. "en popülerler" bölümünden alınmış yanlış tarih/bölüm) düzeltmek için.
    Öğe numaraları, durum ve notlar korunur.
    """
    from .parsers import extract_substack_items

    changed = 0
    for name, scfg in cfg["sources"].items():
        if scfg.get("type") != "substack":
            continue
        own = urlparse(scfg["url"]).netloc.lower().removeprefix("www.")
        seen: set[str] = set()
        rows = db.conn.execute(
            "SELECT id, url, published, raw_html FROM posts WHERE source=? "
            "ORDER BY COALESCE(published, fetched_at)", (name,)).fetchall()
        for post in rows:
            for it in extract_substack_items(post["raw_html"] or "", own, post["url"]):
                if not it.source_url or not it.title:
                    continue
                it.published = post["published"]
                item_id = db.item_id(name, it.source_url)
                if it.popular:
                    if item_id is None:
                        it.url = it.source_url
                        enrich(it, name)
                        item_id = db.insert_item(name, post["id"], it)
                        changed += 1
                    if item_id is not None:
                        db.set_metric(item_id, "hot", 1)
                    continue
                if it.source_url in seen:       # daha eski bir sayıda zaten işlendi: ilk görülme geçerli
                    continue
                seen.add(it.source_url)
                it.url = it.source_url
                enrich(it, name)
                if item_id is None:
                    db.insert_item(name, post["id"], it)
                else:
                    db.update_item(item_id, it)
                    db.conn.execute("UPDATE items SET post_id=? WHERE id=?", (post["id"], item_id))
                changed += 1
    db.commit()
    return changed
