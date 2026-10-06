"""Besleme ayrıştırıcıları. Her biri feedparser çıktısını Post listesine çevirir.

Bir Post, beslemedeki ham kayıttır (bülten sayısı, günlük özet...). Post.items ise
o kaydın içinden çıkarılan tekil içeriklerdir (makale, blog yazısı, video, etkinlik...).
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .common import Item, Post, clean, html_to_text, shorten, struct_to_iso


def _entry_date(e) -> str | None:
    return struct_to_iso(e.get("published_parsed") or e.get("updated_parsed"))


def _entry_html(e) -> str:
    if e.get("content"):
        return e["content"][0].get("value", "") or ""
    return e.get("summary", "") or ""


def _base_post(e) -> Post:
    return Post(
        guid=e.get("id") or e.get("link") or e.get("title", ""),
        title=clean(e.get("title", "")),
        url=e.get("link"),
        published=_entry_date(e),
        raw_html=_entry_html(e),
    )


# ======================================================================
# Quantocracy: her kayıt bir günlük özet; içinde div.qo-entry blokları var
# ======================================================================
_TITLE_SRC = re.compile(r"^(.*?)\s*\[([^\[\]]+)\]\s*$")


def parse_quantocracy(feed, scfg: dict | None = None) -> list[Post]:
    posts = []
    for e in feed.entries:
        post = _base_post(e)
        soup = BeautifulSoup(post.raw_html, "html.parser")
        for entry in soup.select("div.qo-entry"):
            a = entry.select_one("a.qo-title") or entry.find("a", href=True)
            if not a or not a.get("href"):
                continue
            text = clean(a.get_text(" "))
            m = _TITLE_SRC.match(text)
            title, origin = (m.group(1), m.group(2)) if m else (text, None)
            desc = entry.select_one(".qo-description")
            post.items.append(Item(
                title=title, source_url=a["href"], origin=origin, section="Quant Mashup",
                summary=clean(desc.get_text(" ")) if desc else None, published=post.published,
            ))
        if not post.items:  # site yapısı değişirse yedek: yönlendirme linklerini topla
            for a in soup.find_all("a", href=True):
                if "redirect.php" in a["href"]:
                    text = clean(a.get_text(" "))
                    m = _TITLE_SRC.match(text)
                    post.items.append(Item(
                        title=m.group(1) if m else text, origin=m.group(2) if m else None,
                        source_url=a["href"], section="Quant Mashup", published=post.published))
        posts.append(post)
    return posts


# ======================================================================
# Substack (QuantSeeker, Systematic Traders, OpenQuant)
# Bülten metnini bölüm başlıklarına göre gezip link içeren satırları öğeye çevirir.
# ======================================================================
_BLOCKS = ["h1", "h2", "h3", "h4", "h5", "p", "li", "blockquote"]
_HEADINGS = {"h1", "h2", "h3", "h4", "h5"}
_SKIP_HOSTS = ("substack.com", "substackcdn.com", "open.substack.com")
_SKIP_LINK = ("twitter.com/intent", "x.com/intent",
              "facebook.com/sharer", "linkedin.com/shareArticle", "mailto:", "/subscribe",
              "/comments", "action=share", "utm_content=share")
_SKIP_SECTION = re.compile(r"disclaimer|subscribe|share this", re.I)
_POPULAR_SECTION = re.compile(r"most popular|popular links", re.I)
_SKIP_TEXT = ("disclaimer", "this substack is reader-supported", "thanks for reading",
              "share this post", "subscribe")
_GENERIC = {"here", "link", "read more", "watch", "listen", "video", "[video]", "paper",
            "this", "source", "read", "pdf"}
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")


def _yt_placeholders(soup: BeautifulSoup) -> None:
    """Substack video gömülerini sıradan bir linke çevirir (başlık önceki satırdan alınır)."""
    for div in soup.select('div[data-component-name="Youtube2ToDOM"], div.youtube-wrap'):
        vid = None
        try:
            vid = json.loads(div.get("data-attrs", "{}")).get("videoId")
        except (ValueError, TypeError):
            pass
        if not vid:
            iframe = div.find("iframe", src=True)
            if iframe:
                m = re.search(r"embed/([\w-]{6,})", iframe["src"])
                vid = m.group(1) if m else None
        if vid:
            p = soup.new_tag("p")
            a = soup.new_tag("a", href=f"https://www.youtube.com/watch?v={vid}")
            a.string = "video"
            p.append(a)
            div.replace_with(p)


_SKIP_CLASS = re.compile(r"subscription-widget|captioned-image|captioned-button|footnote|button-wrapper|cta-caption")


def _blocks(soup: BeautifulSoup):
    for el in soup.find_all(_BLOCKS):
        if el.find(_BLOCKS):
            continue
        if _SKIP_CLASS.search(" ".join(el.get("class") or [])) or el.find_parent(class_=_SKIP_CLASS):
            continue
        yield el


def _first_link(block, own_host: str):
    for a in block.find_all("a", href=True):
        href = a["href"].strip()
        if not href.startswith("http"):
            continue
        if any(s in href for s in _SKIP_LINK):
            continue
        host = urlparse(href).netloc.lower().removeprefix("www.")
        if host in _SKIP_HOSTS or host.endswith(".substackcdn.com"):
            continue
        # Bültenin kendi sitesine giden linklerden yalnızca yazıları (/p/...) al
        if own_host and host == own_host and "/p/" not in href:
            continue
        return a
    return None


def _headline_item(b, text: str, section, post_url: str | None) -> Item | None:
    """Linksiz haber satırı: <p><strong>📰 Başlık | </strong>açıklama</p> (OpenQuant 'News')."""
    strong = b.find(["strong", "b"])
    if not (strong and _EMOJI.match(text) and post_url):
        return None
    head = _EMOJI.sub("", clean(strong.get_text(" "))).strip(" |-–—:")
    if len(head) < 8:
        return None
    rest = text.replace(clean(strong.get_text(" ")), "", 1).strip(" |-–—:")
    slug = re.sub(r"[^a-z0-9]+", "-", head.lower()).strip("-")[:80]
    return Item(title=head, source_url=f"{post_url}#{slug}", section=section,
                summary=shorten(rest, 800) if len(rest) > 15 else None, hint=text[0])


def extract_substack_items(html: str, own_host: str = "", post_url: str | None = None) -> list[Item]:
    soup = BeautifulSoup(html or "", "html.parser")
    _yt_placeholders(soup)
    items: list[Item] = []
    section = None
    last: Item | None = None
    last_idx = -10
    bold_title: tuple[str, int] | None = None

    for i, b in enumerate(_blocks(soup)):
        text = clean(b.get_text(" "))
        if not text and not b.find("a"):
            continue
        low = text.lower()
        a = _first_link(b, own_host)

        if b.name in _HEADINGS and a is None:
            section = _EMOJI.sub("", text).strip(" #:-") or section
            last, bold_title = None, None
            continue
        if section and _SKIP_SECTION.search(section):
            continue
        if any(low.startswith(s) for s in _SKIP_TEXT):
            last = None
            continue

        if a is None:
            strong = b.find(["strong", "b"])
            headline = _headline_item(b, text, section, post_url)
            if headline:
                items.append(headline)
                last, last_idx, bold_title = headline, i, None
                continue
            if strong and clean(strong.get_text(" ")) == text and b.name not in _HEADINGS:
                bold_title = (text, i)          # kalın, linksiz satır: sonraki link için başlık adayı
            elif last is not None and i == last_idx + 1 and not last.summary:
                last.summary = shorten(text, 800)   # öğenin hemen altındaki paragraf = özet
            continue

        atext = clean(a.get_text(" "))
        in_bold = a.find_parent(["strong", "b"]) is not None or b.name in _HEADINGS
        starts_with_link = text.startswith(atext[:25]) if atext else False
        emoji_start = bool(_EMOJI.match(text))
        if not (in_bold or starts_with_link or b.name == "li" or emoji_start
                or atext.lower() in _GENERIC):
            continue  # metin içinde geçen sıradan link: öğe değil

        title = atext
        if len(atext) < 4 or atext.lower() in _GENERIC:
            if bold_title and i - bold_title[1] <= 2:
                title = bold_title[0]
            else:
                strong = b.find(["strong", "b"])
                title = clean(strong.get_text(" ")) if strong else shorten(text, 140)
        title = _EMOJI.sub("", title).strip(" |-–—:")

        rest = _EMOJI.sub("", text.replace(atext, "", 1)).strip(" |-–—:·")
        origin = None
        m = re.match(r"^\(([^()]{2,150})\)\s*(.*)$", rest)
        if m:
            origin, rest = m.group(1), m.group(2).strip(" |-–—:·")
        hint = text[0] if emoji_start else None

        it = Item(title=title or shorten(text, 140), source_url=a["href"].strip(), origin=origin,
                  section=section, summary=shorten(rest, 800) if len(rest) > 15 else None, hint=hint,
                  popular=bool(section and _POPULAR_SECTION.search(section)))
        items.append(it)
        last, last_idx, bold_title = it, i, None
    return items


def parse_substack(feed, scfg: dict | None = None) -> list[Post]:
    own = urlparse(feed.feed.get("link", "")).netloc.lower().removeprefix("www.")
    posts = []
    for e in feed.entries:
        post = _base_post(e)
        post.items = extract_substack_items(post.raw_html, own, post.url)
        for it in post.items:
            it.published = post.published
        posts.append(post)
    return posts


# ======================================================================
# WordPress (Quantpedia): her kayıt bir blog yazısı
# ======================================================================
def parse_wordpress(feed, scfg: dict | None = None) -> list[Post]:
    """Her kayıt tek öğe: blog yazısı ya da podcast bölümü.

    Kaynak ayarları: skip_title_patterns (atlanacak başlıklar), kind (tür; ör. "video/podcast"),
    section (bölüm adı).
    """
    scfg = scfg or {}
    skip = [s.lower() for s in scfg.get("skip_title_patterns", [])]
    # Bazı podcast beslemelerinde tüm bölümlerin linki ana sayfadır; o zaman bölümü ayırt eden adres gerekir
    link_counts: dict[str, int] = {}
    for e in feed.entries:
        link_counts[e.get("link", "")] = link_counts.get(e.get("link", ""), 0) + 1
    posts = []
    for e in feed.entries:
        title = clean(e.get("title", ""))
        if any(s in title.lower() for s in skip):
            continue
        post = _base_post(e)
        link = e.get("link") or ""
        if not link or link_counts.get(link, 0) > 1:
            audio = next((x.get("href") for x in e.get("enclosures", []) if x.get("href")), None)
            guid = re.sub(r"[^A-Za-z0-9_-]", "", e.get("id", "") or title)[:60]
            link = audio or (f"{link}{'&' if '?' in link else '?'}ep={guid}" if link else "")
        wp_tags = [clean(t.get("term", "")) for t in e.get("tags", [])]
        wp_tags = [t for t in wp_tags if t and t.lower() not in ("uncategorized", "own-research")]
        post.items.append(Item(
            title=title, source_url=link, origin=clean(e.get("author", "")) or None,
            section=scfg.get("section", "Blog"), kind=scfg.get("kind"),
            summary=shorten(html_to_text(e.get("summary", "")), 900),
            published=post.published, tags=wp_tags[:scfg.get("max_tags", 6)],
        ))
        posts.append(post)
    return posts


# ======================================================================
# Reddit (Atom): her kayıt bir gönderi
# ======================================================================
_REDDIT_TAIL = re.compile(r"submitted by\s+/u/\S+.*$", re.I | re.S)


def parse_reddit(feed, scfg: dict | None = None) -> list[Post]:
    posts = []
    for e in feed.entries:
        post = _base_post(e)
        body = _REDDIT_TAIL.sub("", html_to_text(post.raw_html)).strip()
        author = clean(e.get("author", "")).removeprefix("/u/") or None
        post.items.append(Item(
            title=post.title, source_url=e.get("link"), origin=f"u/{author}" if author else None,
            section="Haftanın en çok oylananları", summary=shorten(body, 600) or None,
            published=post.published,
        ))
        posts.append(post)
    return posts


# ======================================================================
# arXiv API (Atom)
# ======================================================================
def parse_arxiv(feed, label: str) -> list[Post]:
    posts = []
    for e in feed.entries:
        abs_url = re.sub(r"v\d+$", "", e.get("id", "")).replace("http://", "https://")
        authors = [a.get("name", "") for a in e.get("authors", [])]
        origin = ", ".join(authors[:4]) + (" et al." if len(authors) > 4 else "")
        cats = [t.get("term") for t in e.get("tags", []) if t.get("term", "").startswith("q-fin")]
        post = Post(guid=abs_url, title=clean(e.get("title", "")), url=abs_url,
                    published=_entry_date(e), raw_html="")
        post.items.append(Item(
            title=post.title, source_url=abs_url, origin=origin or None, section=label,
            kind="makale", summary=shorten(clean(e.get("summary", "")), 900),
            published=post.published, tags=cats[:3],
        ))
        posts.append(post)
    return posts


# ======================================================================
# Reddit JSON (oy ve yorum sayılarıyla): /r/<sub>/top.json?t=week
# ======================================================================
def parse_reddit_json(data: dict, scfg: dict | None = None) -> list[Post]:
    from datetime import datetime, timezone
    from .common import iso
    posts = []
    for child in data.get("data", {}).get("children", []):
        d = child.get("data", {})
        if not d.get("permalink") or d.get("stickied"):
            continue
        link = "https://www.reddit.com" + d["permalink"]
        published = iso(datetime.fromtimestamp(d.get("created_utc", 0), tz=timezone.utc)) \
            if d.get("created_utc") else None
        post = Post(guid=d.get("name") or link, title=clean(d.get("title", "")), url=link,
                    published=published, raw_html="")
        post.items.append(Item(
            title=post.title, source_url=link,
            origin=f"u/{d['author']}" if d.get("author") else None,
            section="Haftanın en çok oylananları",
            summary=shorten(d.get("selftext", ""), 600) or None, published=published,
            metrics={"up": d.get("score", 0), "cm": d.get("num_comments", 0)},
        ))
        posts.append(post)
    return posts


PARSERS = {
    "quantocracy": parse_quantocracy,
    "substack": parse_substack,
    "wordpress": parse_wordpress,
    "rss": parse_wordpress,       # genel RSS/Atom: her kayıt tek öğe
    "reddit": parse_reddit,
}
