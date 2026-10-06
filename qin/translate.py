"""İçerik başlık ve özetlerinin Türkçeye çevrilmesi.

Her içerik (aynı içeriğin kopyaları tek sayılır) bir kez çevrilir ve translations tablosuna yazılır.
En yeni içerikten başlanır; bir çalışmadaki istek sayısı sınırlıdır, kalanlar sonraki günlere kalır.
Çok eski içerik (llm.translate.max_age_days) çevrilmez: ücretsiz kotalar güncel içeriğe harcanır.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta

from .common import iso, now_utc
from .llm import LLM, LLMUnavailable, parse_json
from .storage import DB

log = logging.getLogger("qin")

SYSTEM = """Sen kantitatif finans alanında uzman bir çevirmensin. Verilen İngilizce başlık ve özetleri \
doğal, akıcı Türkçeye çevir.

Kurallar:
- Anlamı koru; bilgi ekleme, yorum katma, kısaltma yapma.
- Kişi, kurum, ürün, kütüphane adlarını ve ticker'ları çevirme.
- Yerleşik Türkçe karşılığı olmayan teknik terimleri İngilizce bırak (ör. backtest, momentum, Sharpe, \
order book, overfitting, alpha, drawdown).
- Yalnızca JSON döndür: {"items":[{"id":<aynı id>,"t":"<başlık>","s":"<özet ya da boş>"}]}
- Girdideki her id için tam olarak bir kayıt olmalı."""

SKIP_KINDS = {"iş ilanı"}


def pending(items: list[dict], lang: str = "tr", max_age_days: int | None = None) -> list[dict]:
    """Çevirisi olmayan içerikler, en yeni önce (build_items zaten yeniden eskiye sıralıdır)."""
    since = iso(now_utc() - timedelta(days=max_age_days)) if max_age_days else ""
    return [i for i in items
            if i["k"] not in SKIP_KINDS and i["d"] >= since and not (i.get("tr") or {}).get(lang)]


def batches(items: list[dict], max_chars: int, max_items: int) -> list[list[dict]]:
    out, cur, size = [], [], 0
    for i in items:
        n = len(i["t"]) + len(i.get("s") or "") + 40
        if cur and (size + n > max_chars or len(cur) >= max_items):
            out.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += n
    if cur:
        out.append(cur)
    return out


def translate_pending(db: DB, cfg: dict, llm: LLM, items: list[dict], lang: str = "tr") -> str:
    tcfg = cfg.get("llm", {}).get("translate", {})
    if not tcfg.get("enabled", True):
        return "Çeviri: kapalı"
    todo = pending(items, lang, tcfg.get("max_age_days", 45))
    if not todo:
        return "Çeviri: bekleyen içerik yok"
    groups = batches(todo, tcfg.get("max_chars_per_request", 4500), tcfg.get("max_items_per_request", 12))
    groups = groups[:tcfg.get("max_requests_per_run", 12)]
    done = 0
    note = ""
    for group in groups:
        payload = {"items": [{"id": i["id"], "t": i["t"], "s": i.get("s") or ""} for i in group]}
        try:
            reply = llm.chat(SYSTEM, json.dumps(payload, ensure_ascii=False),
                             max_tokens=tcfg.get("max_output_tokens", 8000), task="translate")
            rows = parse_json(reply).get("items", [])
        except LLMUnavailable as ex:
            note = f" (durdu: {str(ex)[:120]})"
            break
        except (ValueError, AttributeError) as ex:
            log.warning("Çeviri yanıtı okunamadı: %s", ex)
            continue
        wanted = {i["id"]: i for i in group}
        for row in rows if isinstance(rows, list) else []:
            try:
                src = wanted.get(int(row["id"]))
                title = str(row.get("t") or "").strip()
            except (TypeError, ValueError, KeyError, AttributeError):
                continue
            if not src or not title:
                continue
            db.conn.execute(
                "INSERT INTO translations(item_id, lang, title, summary, updated_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(item_id, lang) DO UPDATE SET title=excluded.title, summary=excluded.summary, "
                "updated_at=excluded.updated_at",
                (src["id"], lang, title,
                 (str(row.get("s") or "").strip() or None) if src.get("s") else None,   # özeti olmayana özet uydurulmasın
                 iso(now_utc())))
            done += 1
        db.commit()
    left = len(todo) - done
    return f"Çeviri: {done} içerik çevrildi, {left} bekliyor{note}"
