"""Aynı içeriğin farklı kaynaklardaki kopyalarını tek kümede toplar.

İki öğe şu durumlarda aynı kümeye girer:
  1. Kanonik adresleri aynıysa (takip parametreleri, http/https, www, sondaki /,
     arXiv sürümü, SSRN/YouTube/DOI yazım farkları temizlendikten sonra).
  2. Farklı kaynaklardan geliyorlarsa ve başlıkları yeterince benziyorsa
     (ör. Quantocracy'nin kısalttığı başlık ile orijinali).

Kurallar bilinçli olarak temkinlidir: yanlış birleştirme, kaçırılan eşleşmeden daha kötüdür.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse

_TRACKING = re.compile(
    r"^(utm_\w+|ref|ref_src|source|src|fbclid|gclid|mc_cid|mc_eid|gh_src|r|s|si|feature|"
    r"publication_id|post_id|triedredirect|showwelcome\w*|isfreemail|action|cmpid|trk)$", re.I)
_ARXIV = re.compile(r"arxiv\.org/(?:abs|pdf|html)/([\w.\-/]+?)(?:v\d+)?(?:\.pdf)?/?$", re.I)
_SSRN = re.compile(r"(?:abstract_id=|abstract=|ssrn\.)(\d{5,})", re.I)
_YOUTUBE = re.compile(r"(?:youtube(?:-nocookie)?\.com/(?:watch\?.*?v=|embed/|shorts/|live/)|youtu\.be/)([\w-]{6,})", re.I)
_DOI = re.compile(r"(?:doi\.org/|/doi/(?:abs/|full/|pdf/)?)(10\.\d{4,9}/[^\s?#]+)", re.I)
_REDDIT = re.compile(r"reddit\.com/r/\w+/comments/([a-z0-9]+)", re.I)


def canonical_url(url: str | None, keep_fragment: bool = False) -> str:
    """Karşılaştırma için sadeleştirilmiş adres. Gösterim için değil."""
    if not url:
        return ""
    url = url.strip()
    for prefix, rx in (("arxiv", _ARXIV), ("yt", _YOUTUBE), ("reddit", _REDDIT)):
        m = rx.search(url)
        if m:
            return f"{prefix}:{m.group(1).lower() if prefix != 'yt' else m.group(1)}"
    if "ssrn" in url.lower():
        m = _SSRN.search(url)
        if m:
            return f"ssrn:{m.group(1)}"
    m = _DOI.search(url)
    if m:
        return "doi:" + m.group(1).lower().rstrip("/.")
    p = urlparse(url)
    host = p.netloc.lower()
    for pre in ("www.", "m.", "open."):
        host = host.removeprefix(pre)
    path = re.sub(r"/+$", "", p.path).lower()
    path = re.sub(r"/(index\.html?|amp)$", "", path)
    query = sorted((k, v) for k, v in parse_qsl(p.query) if not _TRACKING.match(k))
    out = host + path
    if query:
        out += "?" + urlencode(query)
    if keep_fragment and p.fragment:
        out += "#" + p.fragment
    return out


# ---------------------------------------------------------------- başlık benzerliği
_STOP = set("""a an the of and or in on for to with from by at as is are was were be been do does did can
could should would will how what why when where which who vs versus via using use into over under about
its it this that these those your our their new not no than then""".split())
_TOKEN = re.compile(r"[a-z0-9]+")


def title_tokens(title: str) -> frozenset[str]:
    return frozenset(t for t in _TOKEN.findall((title or "").lower())
                     if t not in _STOP and (len(t) > 1 or t.isdigit()))


def titles_match(a: frozenset[str], b: frozenset[str]) -> bool:
    """İki başlık aynı içeriği mi anlatıyor? (kelime kümeleri üzerinden)"""
    if len(a) < 4 or len(b) < 4:
        return False                      # kısa/genel başlıklar: yalnızca adres eşleşmesine güven
    na = {t for t in a if t.isdigit()}
    nb = {t for t in b if t.isdigit()}
    if na != nb:
        return False                      # "Part 2" / "Part 3", "Ep.409" / "Ep.410" ayrı içeriklerdir
    common = len(a & b)
    jaccard = common / len(a | b)
    contain = common / min(len(a), len(b))
    return jaccard >= 0.75 or (contain >= 0.85 and common >= 5)


def _day(iso_str: str | None) -> int:
    try:
        return datetime.fromisoformat(iso_str).toordinal()
    except (TypeError, ValueError):
        return 0


class _UnionFind:
    def __init__(self):
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def cluster(rows: list, max_days_apart: int = 45, max_token_freq: int = 40) -> dict[int, int]:
    """rows: id, source, url, title, kind, published/first_seen içeren satırlar.
    Dönen sözlük: öğe id -> küme id (kümedeki en küçük id)."""
    uf = _UnionFind()
    by_url: dict[str, int] = {}
    tokens: dict[int, frozenset[str]] = {}
    info: dict[int, tuple[str, int]] = {}
    index: dict[str, list[int]] = defaultdict(list)

    for r in rows:
        rid = r["id"]
        uf.find(rid)
        key = canonical_url(r["url"], keep_fragment=(r["kind"] == "haber"))
        if key:
            if key in by_url:
                uf.union(rid, by_url[key])
            else:
                by_url[key] = rid
        if r["kind"] in ("iş ilanı", "haber"):
            continue                      # bunlarda başlık benzerliği anlamlı değil
        toks = title_tokens(r["title"])
        tokens[rid] = toks
        info[rid] = (r["source"], _day(r["published"] or r["first_seen"]))
        for t in toks:
            index[t].append(rid)

    # Aday çiftler: nadir kelimelerden en az üçünü paylaşan, farklı kaynaklı öğeler
    shared: dict[tuple[int, int], int] = defaultdict(int)
    for ids in index.values():
        if len(ids) > max_token_freq:
            continue
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if info[a][0] != info[b][0]:
                    shared[(a, b)] += 1
    for (a, b), n in shared.items():
        if n < 3 or uf.find(a) == uf.find(b):
            continue
        da, db_ = info[a][1], info[b][1]
        if da and db_ and abs(da - db_) > max_days_apart:
            continue
        if titles_match(tokens[a], tokens[b]):
            uf.union(a, b)

    return {r["id"]: uf.find(r["id"]) for r in rows}
