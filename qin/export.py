"""Veritabanını sitenin okuduğu JSON dosyalarına aktarır.

site/data/manifest.json     kaynaklar, aylar, son çekme durumu
site/data/items-YYYY-MM.json   o ayın içerikleri (kümelenmiş: her içerik bir kez)

Site yalnızca bu dosyaları okur; veritabanına dokunmaz. Aynı dosyalar ileride
bulutta da (GitHub Actions) üretilecek.
"""
from __future__ import annotations

import bisect
import json
import os
import re
from collections import defaultdict
from pathlib import Path

from . import vault
from .cluster import cluster
from .common import ROOT, iso, now_utc
from .enrich import is_tool, source_tags, topics
from .storage import DB

SITE_DIR = ROOT / "site"
PALETTE_SLOTS = 8          # sitedeki kaynak renk sayısı (site/css/tokens.css --src-1..8)
_KIND_PRIORITY = ["makale", "video/podcast", "etkinlik", "yazı", "tartışma", "haber", "iş ilanı"]


_UTM = re.compile(r"([?&])utm_[a-z]+=[^&#]*&?", re.I)


def tidy_url(url: str) -> str:
    """Gösterilecek adresten takip parametrelerini atar (bağlantı aynı sayfaya gider)."""
    prev = None
    while prev != url:
        prev, url = url, _UTM.sub(r"\1", url)
    return url.rstrip("?&")


def _source_defs(cfg: dict) -> list[tuple[str, str]]:
    out = [(n, s.get("label", n)) for n, s in cfg["sources"].items()]
    if "arxiv" in cfg:
        out.append(("arxiv", cfg["arxiv"].get("label", "arXiv")))
    return out


def _source_slots(db: DB, source_ids: list[str], active: set[str]) -> dict[str, int]:
    """Her kaynağa kalıcı bir renk yuvası verir: renk kaynağa aittir, sırasına değil.
    Yeni kaynak, etkin kaynakların kullanmadığı en küçük yuvayı alır (kapatılan kaynağın rengi boşa çıkar)."""
    slots = json.loads(db.get_meta("source_slots", "{}"))
    changed = False
    for sid in source_ids:
        if sid not in slots:
            used = {slots[s] for s in active if s in slots}
            free = [n for n in range(1, PALETTE_SLOTS + 1) if n not in used]
            slots[sid] = free[0] if free else len(slots) % PALETTE_SLOTS + 1
            changed = True
    if changed:
        db.set_meta("source_slots", json.dumps(slots))
    return slots


def _percentile_fn(values: list[float]):
    ordered = sorted(v for v in values if v > 0)
    if not ordered:
        return lambda v: 0.0
    return lambda v: 0.0 if v <= 0 else bisect.bisect_right(ordered, v) / len(ordered)


def build_items(db: DB) -> list[dict]:
    rows = db.conn.execute("SELECT * FROM items ORDER BY id").fetchall()
    metrics: dict[int, dict[str, float]] = defaultdict(dict)
    for m in db.conn.execute("SELECT item_id, metric, value FROM metrics"):
        metrics[m["item_id"]][m["metric"]] = m["value"]
    trans: dict[int, dict[str, dict]] = defaultdict(dict)
    for t in db.conn.execute("SELECT item_id, lang, title, summary FROM translations"):
        trans[t["item_id"]][t["lang"]] = {"t": t["title"], "s": t["summary"]}

    cluster_of = cluster(rows)
    groups: dict[int, list] = defaultdict(list)
    for r in rows:
        groups[cluster_of[r["id"]]].append(r)

    out = []
    for cid, members in groups.items():
        # Birincil üye: en dolu özeti olan (eşitlikte en eski kayıt)
        primary = max(members, key=lambda r: (len(r["summary"] or ""), -r["id"]))
        date = min((r["published"] or r["first_seen"]) for r in members)
        title = max((r["title"] for r in members), key=len)
        kinds = {r["kind"] for r in members}
        kind = primary["kind"] if "makale" not in kinds else "makale"
        if kind not in _KIND_PRIORITY:
            kind = "yazı"
        url = primary["url"]
        if "quantocracy.com/redirect" in url:
            url = next((r["url"] for r in members if "quantocracy.com/redirect" not in r["url"]), url)
        origin = primary["origin"] or next((r["origin"] for r in members if r["origin"]), None)
        srcs = [primary["source"]] + sorted({r["source"] for r in members} - {primary["source"]})

        merged: dict[str, float] = {}
        for r in members:
            for k, v in metrics.get(r["id"], {}).items():
                merged[k] = max(merged.get(k, 0), v)
        hot = bool(merged.pop("hot", 0))
        extra: list[str] = []
        for r in members:
            for t in source_tags(r["tags"]):
                if t not in extra:
                    extra.append(t)

        item = {
            "id": cid, "t": title, "u": tidy_url(url), "d": date, "k": kind, "src": srcs,
            "tg": topics(title, primary["summary"]),          # konu etiketleri (filtrelenebilir)
            "m": {k: int(v) for k, v in merged.items() if v},
        }
        if extra:
            item["xt"] = extra[:6]                            # kaynağın kendi etiketleri
        if origin:
            item["o"] = origin
        if primary["summary"]:
            item["s"] = primary["summary"]
        if primary["section"]:
            item["sec"] = primary["section"]
        if hot:
            item["hot"] = 1
        if is_tool(title, primary["summary"], kind):
            item["tool"] = 1
        status = next((r["status"] for r in members if r["status"] != "yeni"), None)
        if status:
            item["st"] = status
        tr = next((trans[r["id"]] for r in members if r["id"] in trans), None)
        if tr:
            item["tr"] = tr
        out.append(item)

    # Popülerlik puanı (0-100): farklı ölçümler doğrudan kıyaslanamaz, bu yüzden her ölçüm
    # kendi içinde yüzdelik sıraya çevrilir; çoklu kaynak ve "en popüler" işareti puan ekler.
    pct = {k: _percentile_fn([i["m"].get(k, 0) for i in out]) for k in ("up", "cit", "views", "likes")}
    for i in out:
        base = max((pct[k](i["m"].get(k, 0)) for k in pct), default=0.0) * 60
        score = base + min(40, 20 * (len(i["src"]) - 1)) + (15 if i.get("hot") else 0)
        i["p"] = round(min(100, score))
    out.sort(key=lambda i: (i["d"], i["id"]), reverse=True)
    return out


def _dump(data) -> bytes:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _write(path: Path, payload: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload)
    tmp.replace(path)


def _site_key(db: DB, password: str) -> tuple[bytes, bytes]:
    """Site anahtarı. Tuz arşivde kalıcıdır; böylece tarayıcının hatırladığı anahtar her gün geçerli kalır."""
    import base64
    stored = db.get_meta("site_salt")
    if stored:
        salt = base64.b64decode(stored)
    else:
        salt = os.urandom(16)
        db.set_meta("site_salt", vault.b64(salt))
    return vault.derive_key(password, salt), salt


def export_site(db: DB, cfg: dict, out_dir: Path | None = None, password: str | None = None) -> dict:
    """Site verisini yazar. Parola varsa dosyalar şifreli (.bin) yazılır ve düz JSON bırakılmaz."""
    out_dir = out_dir or SITE_DIR / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    password = password or vault.site_password()
    if not password and os.environ.get("QIN_REQUIRE_PASSWORD"):
        raise RuntimeError("Site parolası tanımlı değil; şifresiz veri yayınlanmaz.")
    key = salt = None
    if password:
        vault.check_strength(password)
        key, salt = _site_key(db, password)
    ext = "bin" if key else "json"
    pack = (lambda data: vault.seal(key, _dump(data))) if key else _dump

    items = build_items(db)
    by_month: dict[str, list] = defaultdict(list)
    for i in items:
        by_month[i["d"][:7]].append(i)
    months = []
    for month in sorted(by_month, reverse=True):
        name = f"items-{month}.{ext}"
        _write(out_dir / name, pack({"month": month, "items": by_month[month]}))
        months.append({"m": month, "n": len(by_month[month]), "file": name})
    wanted = {m["file"] for m in months} | {f"manifest.{ext}", ".gitkeep"} | ({"lock.json"} if key else set())
    for old in out_dir.iterdir():           # eski aylar ve diğer kipin (düz/şifreli) dosyaları
        if old.is_file() and old.name not in wanted:
            old.unlink()

    defs = _source_defs(cfg)
    def enabled(sid: str) -> bool:
        return (cfg["arxiv"] if sid == "arxiv" else cfg["sources"][sid]).get("enabled", True)

    # Etkin kaynaklar önce yuva alır; kapalı olanlar renkleri tüketmez
    order = sorted((sid for sid, _ in defs), key=lambda sid: not enabled(sid))
    slots = _source_slots(db, order, {sid for sid, _ in defs if enabled(sid)})
    fetch = {f["source"]: f for f in db.last_fetch_per_source()}
    counts: dict[str, int] = defaultdict(int)
    last: dict[str, str] = {}
    for i in items:
        for s in i["src"]:
            counts[s] += 1
            if i["d"] > last.get(s, ""):
                last[s] = i["d"]
    sources = []
    for sid, label in defs:
        f = fetch.get(sid)
        if not enabled(sid) and not counts.get(sid):
            continue
        sources.append({
            "id": sid, "label": label, "slot": slots[sid], "n": counts.get(sid, 0),
            "last_item": last.get(sid), "last_fetch": f["ran_at"] if f else None,
            "ok": bool(f["ok"]) if f else None, "error": (f["error"] if f and not f["ok"] else None),
        })

    manifest = {
        "generated": iso(now_utc()),
        "total": len(items),
        "first": items[-1]["d"] if items else None,
        "last": items[0]["d"] if items else None,
        "sources": sources,
        "months": months,
    }
    _write(out_dir / f"manifest.{ext}", pack(manifest))
    if key:   # tarayıcının anahtarı türetmesi için gerekenler (gizli değil)
        _write(out_dir / "lock.json", _dump({"v": 1, "kdf": "PBKDF2-SHA256", "iter": vault.ITERATIONS,
                                              "salt": vault.b64(salt), "cipher": "AES-256-GCM+deflate"}))
    manifest["locked"] = bool(key)
    return manifest
