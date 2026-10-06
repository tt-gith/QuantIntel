"""SQLite depolama: ham kayıtlar (posts), tekil içerikler (items), özetler (briefs), çekme günlüğü.
Abone adresleri burada değil, qin/private.py'deki şifreli kayıtta tutulur."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .common import Item, Post, iso, norm_title, now_utc

STATUSES = ["yeni", "ilginç", "denenecek", "denendi", "elendi"]
_STATUS_ALIASES = {"ilginc": "ilginç", "incelenecek": "denenecek"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,
    guid        TEXT NOT NULL,
    title       TEXT,
    url         TEXT,
    published   TEXT,
    fetched_at  TEXT NOT NULL,
    raw_html    TEXT,
    UNIQUE(source, guid)
);
CREATE TABLE IF NOT EXISTS items (
    id          INTEGER PRIMARY KEY,
    post_id     INTEGER REFERENCES posts(id),
    source      TEXT NOT NULL,
    source_url  TEXT NOT NULL,
    url         TEXT NOT NULL,
    title       TEXT NOT NULL,
    title_norm  TEXT,
    origin      TEXT,
    section     TEXT,
    kind        TEXT,
    summary     TEXT,
    tags        TEXT,
    published   TEXT,
    first_seen  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'yeni',
    note        TEXT,
    UNIQUE(source, source_url)
);
CREATE INDEX IF NOT EXISTS ix_items_published ON items(published);
CREATE INDEX IF NOT EXISTS ix_items_status    ON items(status);
CREATE INDEX IF NOT EXISTS ix_items_url       ON items(url);
CREATE INDEX IF NOT EXISTS ix_items_title     ON items(title_norm);
CREATE TABLE IF NOT EXISTS metrics (
    item_id     INTEGER NOT NULL REFERENCES items(id),
    metric      TEXT NOT NULL,      -- up (oy), cm (yorum), cit (atıf), hot (bültende en popüler), views...
    value       REAL NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (item_id, metric)
);
CREATE TABLE IF NOT EXISTS translations (
    item_id     INTEGER NOT NULL REFERENCES items(id),
    lang        TEXT NOT NULL,
    title       TEXT,
    summary     TEXT,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (item_id, lang)
);
CREATE TABLE IF NOT EXISTS meta (
    key         TEXT PRIMARY KEY,
    value       TEXT
);
CREATE TABLE IF NOT EXISTS briefs (
    id          INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL,      -- daily | weekly
    period      TEXT NOT NULL,      -- günlük: 2026-10-06, haftalık: 2026-W41
    origin      TEXT NOT NULL,      -- llm (otomatik) | manual (yönetim panelinden)
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,      -- Markdown
    model       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT,
    sent_at     TEXT,               -- abonelere gönderildiği an (boşsa gönderilmedi)
    sent_to     INTEGER,
    draft_id    TEXT                -- paneldeki taslağın kimliği: aynı taslak iki kez eklenmesin
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_briefs_llm ON briefs(kind, period) WHERE origin = 'llm';
CREATE TABLE IF NOT EXISTS fetch_log (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,
    ran_at      TEXT NOT NULL,
    ok          INTEGER NOT NULL,
    new_posts   INTEGER DEFAULT 0,
    new_items   INTEGER DEFAULT 0,
    error       TEXT
);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    title, summary, origin, tags, content='items', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS items_ai AFTER INSERT ON items BEGIN
    INSERT INTO items_fts(rowid, title, summary, origin, tags)
    VALUES (new.id, new.title, new.summary, new.origin, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS items_ad AFTER DELETE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, summary, origin, tags)
    VALUES ('delete', old.id, old.title, old.summary, old.origin, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS items_au AFTER UPDATE OF title, summary, origin, tags ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, summary, origin, tags)
    VALUES ('delete', old.id, old.title, old.summary, old.origin, old.tags);
    INSERT INTO items_fts(rowid, title, summary, origin, tags)
    VALUES (new.id, new.title, new.summary, new.origin, new.tags);
END;
"""

# Özet ve aramalarda kullanılan tarih: yayın tarihi, yoksa ilk görülme
WHEN = "COALESCE(i.published, i.first_seen)"


def normalize_status(s: str) -> str:
    s = s.strip().lower()
    s = _STATUS_ALIASES.get(s, s)
    if s not in STATUSES:
        raise ValueError(f"Geçersiz durum: {s}. Seçenekler: {', '.join(STATUSES)}")
    return s


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        try:
            self.conn.executescript(FTS_SCHEMA)
            self.has_fts = True
        except sqlite3.OperationalError:
            self.has_fts = False
        self.conn.commit()

    def close(self):
        try:    # WAL içeriğini ana dosyaya yaz: arşiv tek dosya olarak kopyalanabilsin
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
        self.conn.close()

    # ------------------------------------------------------------ yazma
    def upsert_post(self, source: str, post: Post) -> tuple[int, bool]:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO posts(source, guid, title, url, published, fetched_at, raw_html) "
            "VALUES (?,?,?,?,?,?,?)",
            (source, post.guid, post.title, post.url, post.published, iso(now_utc()), post.raw_html),
        )
        if cur.rowcount:
            return cur.lastrowid, True
        row = self.conn.execute(
            "SELECT id FROM posts WHERE source=? AND guid=?", (source, post.guid)
        ).fetchone()
        return row["id"], False

    def item_exists(self, source: str, source_url: str) -> bool:
        return self.item_id(source, source_url) is not None

    def item_id(self, source: str, source_url: str) -> int | None:
        row = self.conn.execute(
            "SELECT id FROM items WHERE source=? AND source_url=?", (source, source_url)
        ).fetchone()
        return row["id"] if row else None

    def item_id_like(self, source: str, pattern: str) -> int | None:
        row = self.conn.execute(
            "SELECT id FROM items WHERE source=? AND source_url LIKE ? ORDER BY id LIMIT 1",
            (source, pattern)).fetchone()
        return row["id"] if row else None

    def update_item(self, item_id: int, it: Item) -> None:
        """Yeniden ayrıştırmada alanları günceller (durum ve not korunur)."""
        self.conn.execute(
            "UPDATE items SET title=?, title_norm=?, origin=?, section=?, kind=?, summary=?, tags=?, "
            "published=COALESCE(?, published) WHERE id=?",
            (it.title, norm_title(it.title), it.origin, it.section, it.kind, it.summary,
             ", ".join(it.tags), it.published, item_id))

    def set_metric(self, item_id: int, metric: str, value: float) -> None:
        self.conn.execute(
            "INSERT INTO metrics(item_id, metric, value, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(item_id, metric) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (item_id, metric, float(value), iso(now_utc())))

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value))
        self.conn.commit()

    def insert_item(self, source: str, post_id: int | None, it: Item) -> int | None:
        """Yeni öğeyi ekler; eklendiyse id'sini, zaten varsa None döndürür."""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO items(post_id, source, source_url, url, title, title_norm, origin, "
            "section, kind, summary, tags, published, first_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (post_id, source, it.source_url, it.url or it.source_url, it.title, norm_title(it.title),
             it.origin, it.section, it.kind, it.summary, ", ".join(it.tags), it.published,
             iso(now_utc())),
        )
        return cur.lastrowid if cur.rowcount > 0 else None

    # ------------------------------------------------------------ özetler
    def save_brief(self, kind: str, period: str, origin: str, title: str, body: str,
                   model: str | None = None, brief_id: int | None = None, draft_id: str | None = None) -> int:
        """Özet ekler; brief_id verilirse o özeti günceller. Kimliğini döndürür."""
        now = iso(now_utc())
        if brief_id is not None:
            cur = self.conn.execute(
                "UPDATE briefs SET kind=?, period=?, title=?, body=?, updated_at=? WHERE id=?",
                (kind, period, title, body, now, brief_id))
            if not cur.rowcount:
                raise ValueError(f"Özet bulunamadı: #{brief_id}")
        else:
            brief_id = self.conn.execute(
                "INSERT INTO briefs(kind, period, origin, title, body, model, created_at, draft_id) "
                "VALUES (?,?,?,?,?,?,?,?)", (kind, period, origin, title, body, model, now, draft_id)).lastrowid
        self.conn.commit()
        return brief_id

    def brief(self, brief_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM briefs WHERE id=?", (brief_id,)).fetchone()

    def find_brief(self, kind: str, period: str, origin: str = "llm") -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM briefs WHERE kind=? AND period=? AND origin=? ORDER BY id DESC LIMIT 1",
            (kind, period, origin)).fetchone()

    def find_draft(self, draft_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM briefs WHERE draft_id=? ORDER BY id DESC LIMIT 1",
                                 (draft_id,)).fetchone()

    def briefs(self, limit: int | None = None) -> list[sqlite3.Row]:
        q = "SELECT * FROM briefs ORDER BY created_at DESC, id DESC"
        return self.conn.execute(q + (" LIMIT ?" if limit else ""), (limit,) if limit else ()).fetchall()

    def delete_brief(self, brief_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM briefs WHERE id=?", (brief_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def mark_brief_sent(self, brief_id: int, count: int) -> None:
        self.conn.execute("UPDATE briefs SET sent_at=?, sent_to=? WHERE id=?", (iso(now_utc()), count, brief_id))
        self.conn.commit()

    def log_fetch(self, source: str, ok: bool, new_posts=0, new_items=0, error=None):
        self.conn.execute(
            "INSERT INTO fetch_log(source, ran_at, ok, new_posts, new_items, error) VALUES (?,?,?,?,?,?)",
            (source, iso(now_utc()), int(ok), new_posts, new_items, error),
        )
        self.conn.commit()

    def commit(self):
        self.conn.commit()

    def set_status(self, item_id: int, status: str, note: str | None = None) -> bool:
        status = normalize_status(status)
        if note is None:
            cur = self.conn.execute("UPDATE items SET status=? WHERE id=?", (status, item_id))
        else:
            cur = self.conn.execute("UPDATE items SET status=?, note=? WHERE id=?", (status, note, item_id))
        self.conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------ okuma
    def items_between(self, start_iso: str, end_iso: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            f"SELECT i.* FROM items i WHERE {WHEN} >= ? AND {WHEN} <= ? "
            f"ORDER BY {WHEN} DESC, i.id", (start_iso, end_iso)
        ).fetchall()

    def posts_between(self, start_iso: str, end_iso: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM posts WHERE COALESCE(published, fetched_at) >= ? "
            "AND COALESCE(published, fetched_at) <= ? ORDER BY published DESC",
            (start_iso, end_iso),
        ).fetchall()

    def last_fetch_per_source(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT f.* FROM fetch_log f JOIN (SELECT source, MAX(id) mid FROM fetch_log GROUP BY source) m "
            "ON f.id = m.mid ORDER BY f.source"
        ).fetchall()

    def search(self, query: str, limit: int = 30) -> list[sqlite3.Row]:
        if self.has_fts:
            try:
                return self.conn.execute(
                    "SELECT i.* FROM items_fts f JOIN items i ON i.id = f.rowid "
                    "WHERE items_fts MATCH ? ORDER BY rank LIMIT ?", (query, limit)
                ).fetchall()
            except sqlite3.OperationalError:
                pass  # FTS sözdizimi hatası -> basit aramaya düş
        like = f"%{query}%"
        return self.conn.execute(
            "SELECT * FROM items WHERE title LIKE ? OR summary LIKE ? OR tags LIKE ? "
            "ORDER BY COALESCE(published, first_seen) DESC LIMIT ?", (like, like, like, limit)
        ).fetchall()

    def by_status(self, statuses: list[str]) -> list[sqlite3.Row]:
        q = ",".join("?" * len(statuses))
        return self.conn.execute(
            f"SELECT * FROM items WHERE status IN ({q}) ORDER BY status, first_seen DESC", statuses
        ).fetchall()

    def stats(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT source, COUNT(*) n, MIN(COALESCE(published, first_seen)) first, "
            "MAX(COALESCE(published, first_seen)) last FROM items GROUP BY source ORDER BY source"
        ).fetchall()
