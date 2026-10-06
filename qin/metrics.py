"""Dış popülerlik ölçümleri.

Şu an: makaleler için atıf sayısı (Semantic Scholar, ücretsiz ve anahtarsız).
Reddit oy/yorum sayıları çekme sırasında gelir (fetch.py).

Yeni bir ölçüm eklemek için: bir fonksiyon yaz, db.set_metric(item_id, "<kısa ad>", değer)
çağır ve refresh_all içine ekle. Sitede göstermek için site/js/config.js > METRICS'e bir satır yeter.
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta

from .common import iso, now_utc
from .storage import DB

log = logging.getLogger("qin")

S2_BATCH = "https://api.semanticscholar.org/graph/v1/paper/batch"
_ARXIV_ID = re.compile(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})", re.I)
_SSRN_ID = re.compile(r"ssrn\.com/.*?(?:abstract_id=|abstract=)(\d{5,})", re.I)


def paper_ref(url: str) -> str | None:
    m = _ARXIV_ID.search(url or "")
    if m:
        return f"ARXIV:{m.group(1)}"
    m = _SSRN_ID.search(url or "")
    if m:
        return f"DOI:10.2139/ssrn.{m.group(1)}"
    return None


def refresh_citations(db: DB, cfg: dict, session) -> str:
    mcfg = cfg.get("metrics", {}).get("citations", {})
    if not mcfg.get("enabled", True):
        return "Atıf sayıları: kapalı"
    since = iso(now_utc() - timedelta(days=mcfg.get("max_age_days", 365)))
    fresh = iso(now_utc() - timedelta(days=mcfg.get("refresh_days", 3)))
    rows = db.conn.execute(
        "SELECT i.id, i.url FROM items i LEFT JOIN metrics m ON m.item_id = i.id AND m.metric = 'cit' "
        "WHERE i.kind = 'makale' AND COALESCE(i.published, i.first_seen) >= ? "
        "AND (m.updated_at IS NULL OR m.updated_at < ?)", (since, fresh)).fetchall()
    refs = [(r["id"], paper_ref(r["url"])) for r in rows]
    refs = [(i, ref) for i, ref in refs if ref]
    if not refs:
        return "Atıf sayıları: güncellenecek makale yok"
    found = 0
    try:
        for start in range(0, len(refs), 400):
            chunk = refs[start:start + 400]
            r = session.post(S2_BATCH, params={"fields": "citationCount"},
                             json={"ids": [ref for _, ref in chunk]}, timeout=40)
            if r.status_code == 429:
                return f"Atıf sayıları: servis şu an yoğun, sonraki çekmede denenecek ({found} güncellendi)"
            r.raise_for_status()
            for (item_id, _), paper in zip(chunk, r.json()):
                # Servisin henüz tanımadığı makaleler null döner; 0 yazıp bir süre tekrar sormayız
                count = (paper or {}).get("citationCount") or 0
                db.set_metric(item_id, "cit", count)
                found += int(bool(paper))
        db.commit()
    except Exception as ex:   # popülerlik verisi olmasa da sistem çalışmaya devam eder
        log.warning("Atıf sayıları alınamadı: %s", ex)
        db.commit()
        return f"Atıf sayıları: alınamadı ({str(ex)[-100:]})"
    return f"Atıf sayıları: {len(refs)} makale soruldu, {found} tanesi bulundu"


def refresh_all(db: DB, cfg: dict, session) -> list[str]:
    return [refresh_citations(db, cfg, session)]
