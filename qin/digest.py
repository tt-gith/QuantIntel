"""Haftalık özet: veritabanındaki son N günü Markdown ve HTML olarak yazar."""
from __future__ import annotations

import html
import shutil
from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from .common import iso, now_utc, shorten
from .enrich import TOOL_TAG
from .storage import DB

SUMMARY_LEN = 320


def _label(cfg: dict, source: str) -> str:
    if source == "arxiv":
        return cfg.get("arxiv", {}).get("label", "arXiv")
    return cfg["sources"].get(source, {}).get("label", source)


def _source_order(cfg: dict) -> list[str]:
    order = [n for n, s in cfg["sources"].items() if s.get("enabled", True)]
    if cfg.get("arxiv", {}).get("enabled"):
        order.append("arxiv")
    return order


def build(db: DB, cfg: dict, days: int, end: datetime | None = None) -> dict:
    end = end or now_utc()
    start = end - timedelta(days=days)
    rows = db.items_between(iso(start), iso(end))
    posts = db.posts_between(iso(start), iso(end))

    by_source: dict[str, list] = defaultdict(list)
    for r in rows:
        by_source[r["source"]].append(r)

    # Radar: araç / ürün sinyali taşıyan her şey
    radar = [r for r in rows if TOOL_TAG in (r["tags"] or "")]

    # Birden fazla kaynakta geçenler (aynı link ya da aynı başlık)
    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        groups["u:" + r["url"]].append(r)
        if len(r["title_norm"] or "") > 20:
            groups["t:" + r["title_norm"]].append(r)
    multi, seen_ids = [], set()
    for g in groups.values():
        srcs = {r["source"] for r in g}
        if len(srcs) > 1 and not (seen_ids & {r["id"] for r in g}):
            seen_ids |= {r["id"] for r in g}
            multi.append((g[0], sorted(srcs)))

    sections = []
    for src in _source_order(cfg):
        items = by_source.get(src, [])
        src_posts = [p for p in posts if p["source"] == src] if src not in ("arxiv",) else []
        grouped: OrderedDict[str, list] = OrderedDict()
        if src in ("quantocracy", "quantpedia", "reddit_algotrading"):
            grouped[""] = items
        else:
            for r in items:
                grouped.setdefault(r["section"] or "Diğer", []).append(r)
        sections.append({"source": src, "label": _label(cfg, src), "posts": src_posts,
                         "groups": grouped, "count": len(items)})

    return {"start": start, "end": end, "days": days, "total": len(rows), "radar": radar,
            "multi": multi, "sections": sections, "fetch": db.last_fetch_per_source(),
            "labels": {s: _label(cfg, s) for s in _source_order(cfg)}}


# ------------------------------------------------------------------ Markdown
def _md_item(r, labels=None, show_source=False) -> str:
    meta = [m for m in (r["origin"], r["kind"]) if m]
    if show_source and labels:
        meta.insert(0, labels.get(r["source"], r["source"]))
    if r["status"] != "yeni":
        meta.append(f"durum: {r['status']}")
    line = f"- **[{r['title']}]({r['url']})**"
    if meta:
        line += " — " + " · ".join(meta)
    line += f" `#{r['id']}`"
    if r["summary"]:
        line += "\n  " + shorten(r["summary"], SUMMARY_LEN)
    return line


def render_md(d: dict) -> str:
    fmt = "%d.%m.%Y"
    out = [f"# Quant Intelligence · Haftalık Özet",
           f"**{d['start'].strftime(fmt)} – {d['end'].strftime(fmt)}** · toplam {d['total']} öğe", ""]
    out.append("> Bir öğeyi işaretlemek için: `qin mark <id> ilginç` · listelemek için: `qin radar`\n")

    out.append(f"## 🛠 Araç sinyalleri ({len(d['radar'])})")
    out.append("_Yeni platform, kütüphane, API veya lansman geçen içerikler (otomatik, geniş filtre)._\n")
    out += [_md_item(r, d["labels"], True) for r in d["radar"][:40]] or ["_Bu hafta yok._"]
    out.append("")

    if d["multi"]:
        out.append(f"## 🔁 Birden fazla kaynakta geçenler ({len(d['multi'])})\n")
        for r, srcs in d["multi"]:
            out.append(f"- **[{r['title']}]({r['url']})** — " + ", ".join(d["labels"].get(s, s) for s in srcs))
        out.append("")

    for s in d["sections"]:
        out.append(f"## {s['label']} ({s['count']})")
        if s["posts"]:
            out.append("Bu dönemin sayıları: " + " · ".join(
                f"[{p['title'] or 'sayı'}]({p['url']})" for p in s["posts"][:8]))
        out.append("")
        if not s["count"]:
            out.append("_Bu dönemde yeni içerik yok._\n")
            continue
        for sub, items in s["groups"].items():
            if sub:
                out.append(f"### {sub}")
            out += [_md_item(r) for r in items]
            out.append("")

    out.append("## Kaynak durumu (son çekme)\n")
    out.append("| Kaynak | Zaman (UTC) | Durum | Arşive eklenen |\n|---|---|---|---|")
    for f in d["fetch"]:
        status = "✅" if f["ok"] else f"⚠️ {shorten(f['error'] or '', 80)}"
        out.append(f"| {d['labels'].get(f['source'], f['source'])} | {f['ran_at'][:16].replace('T', ' ')} "
                   f"| {status} | {f['new_items']} |")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ HTML
CSS = """
:root{--bg:#f7f7f5;--card:#fff;--fg:#1d1d1f;--muted:#6b6b70;--line:#e4e4e0;--acc:#2f5bd3;--tag:#eef1fb;--warn:#b54708}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1d1d20;--fg:#ececee;--muted:#9a9aa2;--line:#2c2c31;--acc:#7f9cff;--tag:#252a3a;--warn:#f5a25d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:920px;margin:0 auto;padding:28px 16px 60px}h1{font-size:26px;margin:0 0 4px}
.sub{color:var(--muted);margin-bottom:22px}details{background:var(--card);border:1px solid var(--line);border-radius:12px;margin:14px 0;padding:4px 16px}
summary{cursor:pointer;font-weight:650;font-size:17px;padding:10px 0}summary .n{color:var(--muted);font-weight:500}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin:18px 0 6px}
.it{padding:10px 0;border-top:1px solid var(--line)}.it:first-of-type{border-top:0}
.it a{color:var(--fg);font-weight:600;text-decoration:none}.it a:hover{color:var(--acc);text-decoration:underline}
.meta{font-size:12.5px;color:var(--muted);margin-top:2px}.meta code{background:var(--tag);padding:0 5px;border-radius:5px}
.sum{font-size:13.5px;margin-top:4px}.tags span{display:inline-block;font-size:11.5px;background:var(--tag);border-radius:999px;padding:1px 8px;margin:4px 4px 0 0}
.issues{font-size:13px;color:var(--muted);margin-bottom:6px}.issues a{color:var(--acc)}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
.bad{color:var(--warn)}.status{color:var(--acc);font-weight:600}
"""


def _h_item(r, labels=None, show_source=False) -> str:
    e = html.escape
    meta = [m for m in (r["origin"], r["kind"]) if m]
    if show_source and labels:
        meta.insert(0, labels.get(r["source"], r["source"]))
    meta_html = " · ".join(e(m) for m in meta)
    if r["status"] != "yeni":
        meta_html += f' · <span class="status">{e(r["status"])}</span>'
    tags = "".join(f"<span>{e(t.strip())}</span>" for t in (r["tags"] or "").split(",") if t.strip())
    summ = f'<div class="sum">{e(shorten(r["summary"], SUMMARY_LEN))}</div>' if r["summary"] else ""
    return (f'<div class="it"><a href="{e(r["url"])}" target="_blank" rel="noopener">{e(r["title"])}</a>'
            f'<div class="meta">{meta_html} <code>#{r["id"]}</code></div>{summ}'
            f'<div class="tags">{tags}</div></div>')


def render_html(d: dict) -> str:
    e = html.escape
    fmt = "%d.%m.%Y"
    parts = [f'<!doctype html><html lang="tr"><head><meta charset="utf-8">'
             f'<meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>Quant Özet {d["end"].strftime("%Y-W%V")}</title><style>{CSS}</style></head><body><main>',
             f'<h1>Quant Intelligence · Haftalık Özet</h1>'
             f'<div class="sub">{d["start"].strftime(fmt)} – {d["end"].strftime(fmt)} · toplam {d["total"]} öğe · '
             f'işaretlemek için <code>qin mark &lt;id&gt; ilginç</code></div>']

    radar = "".join(_h_item(r, d["labels"], True) for r in d["radar"][:40]) or "<p>Bu hafta yok.</p>"
    parts.append(f'<details open><summary>🛠 Araç sinyalleri <span class="n">({len(d["radar"])})</span></summary>'
                 f'<div class="issues">Yeni platform, kütüphane, API veya lansman geçen içerikler (otomatik, geniş filtre).</div>'
                 f'{radar}</details>')

    if d["multi"]:
        rows = "".join(
            f'<div class="it"><a href="{e(r["url"])}" target="_blank">{e(r["title"])}</a>'
            f'<div class="meta">{e(", ".join(d["labels"].get(s, s) for s in srcs))}</div></div>'
            for r, srcs in d["multi"])
        parts.append(f'<details open><summary>🔁 Birden fazla kaynakta geçenler '
                     f'<span class="n">({len(d["multi"])})</span></summary>{rows}</details>')

    for s in d["sections"]:
        body = []
        if s["posts"]:
            body.append('<div class="issues">Bu dönemin sayıları: ' + " · ".join(
                f'<a href="{e(p["url"] or "#")}" target="_blank">{e(p["title"] or "sayı")}</a>'
                for p in s["posts"][:8]) + "</div>")
        if not s["count"]:
            body.append("<p>Bu dönemde yeni içerik yok.</p>")
        for sub, items in s["groups"].items():
            if sub:
                body.append(f"<h3>{e(sub)}</h3>")
            body.extend(_h_item(r) for r in items)
        is_open = " open" if s["source"] in ("quantseeker", "quantocracy") else ""
        parts.append(f'<details{is_open}><summary>{e(s["label"])} <span class="n">({s["count"]})</span></summary>'
                     f'{"".join(body)}</details>')

    trs = "".join(
        f'<tr><td>{e(d["labels"].get(f["source"], f["source"]))}</td><td>{e(f["ran_at"][:16].replace("T", " "))}</td>'
        + (f'<td>✅</td>' if f["ok"] else f'<td class="bad">⚠️ {e(shorten(f["error"] or "", 120))}</td>')
        + f'<td>{f["new_items"]}</td></tr>' for f in d["fetch"])
    parts.append(f'<details><summary>Kaynak durumu (son çekme)</summary><table><tr><th>Kaynak</th>'
                 f'<th>Zaman (UTC)</th><th>Durum</th><th>Arşive eklenen</th></tr>{trs}</table></details>')
    parts.append("</main></body></html>")
    return "".join(parts)


def write_digest(db: DB, cfg: dict, days: int | None = None) -> tuple[Path, Path]:
    days = days or cfg.get("lookback_days", 7)
    d = build(db, cfg, days)
    out_dir: Path = cfg["digest_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = d["end"].strftime("%G-W%V")
    md_path, html_path = out_dir / f"{stem}.md", out_dir / f"{stem}.html"
    md_path.write_text(render_md(d), encoding="utf-8")
    html_path.write_text(render_html(d), encoding="utf-8")
    shutil.copyfile(md_path, out_dir / "latest.md")
    shutil.copyfile(html_path, out_dir / "latest.html")
    return md_path, html_path
