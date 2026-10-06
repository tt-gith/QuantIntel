"""Örnek beslemelerle uçtan uca test (internet gerekmez).

Çalıştırma:  .venv\\Scripts\\python -m unittest discover tests
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Testler ortamdaki site parolasından etkilenmesin (bulut iş akışında tanımlıdır)
for _name in ("QIN_SITE_PASSWORD", "QIN_SITE_PASSWORD_OLD", "QIN_REQUIRE_PASSWORD"):
    os.environ.pop(_name, None)

import feedparser

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qin.common import load_config  # noqa: E402
from qin.digest import write_digest  # noqa: E402
from qin.cluster import canonical_url, cluster, title_tokens, titles_match  # noqa: E402
from qin.enrich import is_tool  # noqa: E402
from qin.export import export_site, tidy_url  # noqa: E402
from qin.fetch import _reddit_json_url, arxiv_url, reparse, store_posts  # noqa: E402
from qin.metrics import paper_ref  # noqa: E402
from qin.parsers import (parse_arxiv, parse_quantocracy, parse_reddit, parse_reddit_json,  # noqa: E402
                         parse_substack, parse_wordpress)
from qin.storage import DB  # noqa: E402

FX = Path(__file__).parent / "fixtures"


def feed(name):
    return feedparser.parse((FX / name).read_bytes(), sanitize_html=False)


class ParserTests(unittest.TestCase):
    def test_quantocracy(self):
        posts = parse_quantocracy(feed("quantocracy.xml"))
        items = posts[0].items
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].origin, "Quanter Lab")
        self.assertTrue(items[0].title.startswith("Buffett"))
        self.assertIn("redirect.php", items[0].source_url)
        self.assertIn("seven market measures", items[0].summary)

    def test_quantseeker(self):
        items = parse_substack(feed("quantseeker.xml"))[0].items
        titles = [i.title for i in items]
        self.assertEqual(len(items), 6, titles)
        first = items[0]
        self.assertEqual(first.section, "Equities")
        self.assertEqual(first.origin, "Jha, Jaffri, and Butt")
        self.assertIn("Key takeaway", first.summary)
        self.assertIsNone(items[3].summary)  # blog satırının özeti yok, disclaimer yapışmamalı
        self.assertFalse(any("Disclaimer" in (i.summary or "") for i in items))
        self.assertFalse(any("reader-supported" in (i.summary or "") for i in items))
        self.assertEqual(items[-1].section, "Podcasts")

    def test_openquant(self):
        items = parse_substack(feed("openquant.xml"))[0].items
        titles = [i.title for i in items]
        self.assertEqual(len(items), 4, titles)          # Share / View all butonları alınmamalı
        news, job, event, res = items
        self.assertTrue(news.title.startswith("Citi Shares Drop"))
        self.assertIn("#citi-shares-drop", news.source_url)
        self.assertEqual(news.hint, "📰")
        self.assertEqual(job.hint, "✨")
        self.assertEqual(event.hint, "📆")
        self.assertEqual(event.section, "Upcoming Events")
        self.assertIn("virtual", event.summary)
        self.assertEqual(res.title, "LLM Inference Handbook")

    def test_systematic(self):
        items = parse_substack(feed("systematic.xml"))[0].items
        self.assertEqual(len(items), 3, [i.title for i in items])
        self.assertTrue(items[0].title.startswith("Jane Street Quant Interview"))
        self.assertIn("youtube.com/watch?v=zIvslOeR2oM", items[0].source_url)
        self.assertIn("Quantedge", items[1].title)
        self.assertEqual(items[2].title, "The Math of Trading")
        self.assertEqual(items[2].section, "+ Worth Saving")
        self.assertIn("Kelly", items[2].summary)

    def test_quantpedia_skips_premium(self):
        posts = parse_wordpress(feed("quantpedia.xml"), {"skip_title_patterns": ["Premium Update"]})
        self.assertEqual(len(posts), 1)
        self.assertIn("order flow", posts[0].items[0].tags)

    def test_podcast_feed_with_shared_link(self):
        scfg = {"kind": "video/podcast", "section": "Podcast", "max_tags": 0}
        posts = parse_wordpress(feed("podcast.xml"), scfg)
        urls = [p.items[0].source_url for p in posts]
        self.assertEqual(len(set(urls)), 3, urls)                       # her bölüm ayrı kayıt
        self.assertTrue(urls[0].endswith("s7e34.mp3"))
        self.assertIn("ep=zz-11", urls[2])                              # ses dosyası yoksa bölüm kimliği
        self.assertEqual({p.items[0].kind for p in posts}, {"video/podcast"})
        self.assertEqual(posts[0].items[0].tags, [])
        from qin.cluster import canonical_url
        self.assertEqual(len({canonical_url(u) for u in urls}), 3)       # kümeleme bölümleri birleştirmez

    def test_reddit(self):
        it = parse_reddit(feed("reddit.xml"))[0].items[0]
        self.assertEqual(it.origin, "u/someone")
        self.assertNotIn("submitted by", it.summary)

    def test_arxiv(self):
        it = parse_arxiv(feed("arxiv.xml"), "LLM")[0].items[0]
        self.assertEqual(it.source_url, "https://arxiv.org/abs/2610.01234")
        self.assertEqual(it.title, "Agentic LLM Traders and Limit Order Book Dynamics")
        self.assertEqual(it.tags, ["q-fin.TR"])

    def test_arxiv_url(self):
        cfg = load_config()
        url = arxiv_url(cfg["arxiv"], 'abs:"large language model"')
        self.assertIn("cat%3Aq-fin.TR", url)
        self.assertIn("%22large+language+model%22", url)


class RuleTests(unittest.TestCase):
    def test_canonical_url(self):
        same = [
            ("https://www.quantseeker.com/p/x?utm_source=a&r=1", "http://quantseeker.com/p/x/"),
            ("http://arxiv.org/pdf/2609.31263v2.pdf", "https://arxiv.org/abs/2609.31263"),
            ("https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7530059", "https://ssrn.com/abstract=7530059"),
            ("https://youtu.be/abcDEF12345?si=z", "https://www.youtube.com/watch?v=abcDEF12345&t=10s"),
        ]
        for a, b in same:
            self.assertEqual(canonical_url(a), canonical_url(b), (a, b))
        self.assertNotEqual(canonical_url("https://a.com/p#x", True), canonical_url("https://a.com/p#y", True))

    def test_title_match(self):
        m = lambda a, b: titles_match(title_tokens(a), title_tokens(b))
        self.assertTrue(m("Barrier Crossings to Terminal Distributions: Skellam-Based Options Pricing for 0-DTE Markets",
                          "From Barrier Crossings to Terminal Distributions: A Skellam-Based Options Pricing Framework for 0-DTE Markets"))
        self.assertFalse(m("Momentum Mini-Portfolio Development - Part 3: ASX Momentum",
                           "Momentum Mini-Portfolio Development - Part 2: USA Pullback Momentum"))
        self.assertFalse(m("Weekly Research Recap", "Weekly Research Recap"))      # kısa/genel başlık
        self.assertFalse(m("Trend Following Is Changing Faster Than Ever | Systematic Investor | Ep.409",
                           "The Next Evolution of Trend Following | Systematic Investor | Ep.410"))

    def test_tool_rule(self):
        self.assertTrue(is_tool("I open-sourced my backtester", None, "tartışma"))
        self.assertTrue(is_tool("Transaction cost checks", "using a Python class from the open-source package", "yazı"))
        self.assertFalse(is_tool("Flow Traders - Institutional Trader", "a leading trading platform", "iş ilanı"))
        self.assertFalse(is_tool("Momentum and Reversal", "We introduce a framework for pricing", "makale"))
        self.assertFalse(is_tool("Why Most Portfolios Are Under Diversified", "our platform shows", "yazı"))

    def test_small_helpers(self):
        self.assertEqual(tidy_url("https://a.com/x?id=3&utm_source=q&utm_medium=z"), "https://a.com/x?id=3")
        self.assertEqual(paper_ref("https://arxiv.org/abs/2609.31263"), "ARXIV:2609.31263")
        self.assertEqual(paper_ref("https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7530059"), "DOI:10.2139/ssrn.7530059")
        self.assertEqual(_reddit_json_url({"url": "https://www.reddit.com/r/algotrading/top/.rss?t=week"}),
                         "https://www.reddit.com/r/algotrading/top.json?t=week&limit=25&raw_json=1")

    def test_reddit_json(self):
        import json
        posts = parse_reddit_json(json.loads((FX / "reddit.json").read_text()))
        self.assertEqual(len(posts), 1)                       # sabitlenmiş gönderi atlanır
        self.assertEqual(posts[0].items[0].metrics, {"up": 612, "cm": 143})


class VaultTest(unittest.TestCase):
    PW = "çok gizli şifre öğün 42"

    def test_file_roundtrip_and_password_change(self):
        from qin import vault
        with tempfile.TemporaryDirectory() as tmp:
            src, enc, out = Path(tmp) / "a.db", Path(tmp) / "a.enc", Path(tmp) / "b.db"
            src.write_bytes(b"SQLite format 3" + bytes(range(256)) * 50)
            vault.seal_file(src, enc, self.PW)
            self.assertNotIn(b"SQLite", enc.read_bytes())
            vault.open_file(enc, out, ["yeni parola burada 99", "  " + self.PW + " "])   # eski parola ikinci sırada
            self.assertEqual(out.read_bytes(), src.read_bytes())
            with self.assertRaises(ValueError):
                vault.open_file(enc, out, ["bambaşka bir parola 1"])
            with self.assertRaises(ValueError):
                vault.seal_file(src, enc, "kısa")

    def test_encrypted_export(self):
        import json
        import os
        from qin import vault
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config()
            cfg["db_path"] = Path(tmp) / "t.db"
            db = DB(cfg["db_path"])
            store_posts(db, "quantseeker", parse_substack(feed("quantseeker.xml")))
            out = Path(tmp) / "site"
            export_site(db, cfg, out)                                   # önce düz
            self.assertTrue((out / "manifest.json").exists())
            m = export_site(db, cfg, out, password=self.PW)             # sonra şifreli: düz dosya kalmamalı
            names = {f.name for f in out.iterdir()}
            self.assertTrue(m["locked"])
            self.assertFalse(any(n.endswith(".json") and n != "lock.json" for n in names), names)
            lock = json.loads((out / "lock.json").read_text())
            import base64
            key = vault.derive_key(self.PW, base64.b64decode(lock["salt"]), lock["iter"])
            manifest = json.loads(vault.unseal(key, (out / "manifest.bin").read_bytes()))
            month = json.loads(vault.unseal(key, (out / manifest["months"][0]["file"]).read_bytes()))
            self.assertEqual(len(month["items"]), 6)
            self.assertNotIn(b"Survivorship", (out / manifest["months"][0]["file"]).read_bytes())
            salt1 = lock["salt"]
            export_site(db, cfg, out, password=self.PW)                 # tuz kalıcı: hatırlanan anahtar geçerli kalır
            self.assertEqual(json.loads((out / "lock.json").read_text())["salt"], salt1)
            os.environ["QIN_REQUIRE_PASSWORD"] = "1"
            try:
                with self.assertRaises(RuntimeError):
                    export_site(db, cfg, out)
            finally:
                del os.environ["QIN_REQUIRE_PASSWORD"]
            db.close()


class PopularAndRepairTest(unittest.TestCase):
    def _db(self, tmp):
        cfg = load_config()
        cfg["db_path"] = Path(tmp) / "t.db"
        return cfg, DB(cfg["db_path"])

    def test_first_listing_wins(self):
        """Aynı makale iki sayıda geçerse: ilk sayının tarihi/bölümü kalır, 'en popüler' işareti eklenir."""
        with tempfile.TemporaryDirectory() as tmp:
            cfg, db = self._db(tmp)
            store_posts(db, "quantseeker", parse_substack(feed("quantseeker2.xml")))
            row = db.conn.execute("SELECT * FROM items WHERE url LIKE '%7467079%'").fetchone()
            self.assertEqual(row["section"], "Equities")
            self.assertTrue(row["published"].startswith("2026-09-22"))
            self.assertIn("option-implied", row["summary"])
            hot = db.conn.execute("SELECT value FROM metrics WHERE item_id=? AND metric='hot'", (row["id"],)).fetchone()
            self.assertEqual(hot["value"], 1)
            db.close()

    def test_reparse_repairs_old_archive(self):
        """Eski sürüm yeni sayıyı önce işliyordu; reparse bunu numaraları koruyarak düzeltir."""
        with tempfile.TemporaryDirectory() as tmp:
            cfg, db = self._db(tmp)
            posts = parse_substack(feed("quantseeker2.xml"))            # besleme sırası: yeni, eski
            for post in posts:
                store_posts(db, "quantseeker", [post])                   # eski davranışı taklit et
            db.conn.execute("DELETE FROM metrics")
            bad = db.conn.execute("SELECT * FROM items WHERE url LIKE '%7467079%'").fetchone()
            self.assertIn("Popular", bad["section"])
            db.set_status(bad["id"], "ilginç", "not")
            reparse(db, cfg)
            good = db.conn.execute("SELECT * FROM items WHERE url LIKE '%7467079%'").fetchone()
            self.assertEqual((good["id"], good["status"], good["note"]), (bad["id"], "ilginç", "not"))
            self.assertEqual(good["section"], "Equities")
            self.assertTrue(good["published"].startswith("2026-09-22"))
            self.assertEqual(db.conn.execute("SELECT COUNT(*) c FROM metrics WHERE metric='hot'").fetchone()["c"], 1)
            self.assertEqual(db.conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"], 2)
            db.close()

    def test_reddit_json_updates_rss_row(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            cfg, db = self._db(tmp)
            store_posts(db, "reddit_algotrading", parse_reddit(feed("reddit.xml")))
            store_posts(db, "reddit_algotrading", parse_reddit_json(json.loads((FX / "reddit.json").read_text())))
            self.assertEqual(db.conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"], 1)
            up = db.conn.execute("SELECT value FROM metrics WHERE metric='up'").fetchone()
            self.assertEqual(up["value"], 612)
            db.close()


class PipelineTest(unittest.TestCase):
    def test_store_and_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config()
            cfg["db_path"] = Path(tmp) / "t.db"
            cfg["digest_dir"] = Path(tmp) / "digests"
            db = DB(cfg["db_path"])
            sources = {
                "quantocracy": parse_quantocracy(feed("quantocracy.xml")),
                "quantseeker": parse_substack(feed("quantseeker.xml")),
                "openquant": parse_substack(feed("openquant.xml")),
                "systematic_traders": parse_substack(feed("systematic.xml")),
                "quantpedia": parse_wordpress(feed("quantpedia.xml"), {}),
                "reddit_algotrading": parse_reddit(feed("reddit.xml")),
                "arxiv": parse_arxiv(feed("arxiv.xml"), "LLM ve AI ajanlari"),
            }
            for name, posts in sources.items():
                store_posts(db, name, posts)
                db.log_fetch(name, True, 1, 1)
            # İkinci kayıt tekrar eklememeli
            _, again = store_posts(db, "quantseeker", parse_substack(feed("quantseeker.xml")))
            self.assertEqual(again, 0)

            kinds = {r["kind"] for r in db.conn.execute("SELECT kind FROM items")}
            self.assertTrue({"makale", "yazı", "video/podcast", "etkinlik", "iş ilanı", "tartışma", "haber"} <= kinds, kinds)
            self.assertTrue(db.search("survivorship"))
            self.assertTrue(db.set_status(1, "ilginc", "denemeye değer"))
            self.assertEqual(db.by_status(["ilginç"])[0]["note"], "denemeye değer")

            # Site dışa aktarımı: Quantocracy'deki kısaltılmış başlık Quantpedia yazısıyla tek kayıtta birleşir
            qo = parse_quantocracy(feed("quantocracy.xml"))
            qo[0].items.append(type(qo[0].items[0])(
                title="Can Weakening Morning Order Flow Predict SPY Reversals", origin="Quantpedia",
                source_url="https://quantocracy.com/redirect.php?key=QP",
                url="https://quantpedia.com/can-weakening-morning-order-flow-predict-spy-reversals/?utm_source=quantocracy",
                section="Quant Mashup", published="2026-09-26T05:15:05+00:00"))
            store_posts(db, "quantocracy", qo)
            out = Path(tmp) / "site"
            manifest = export_site(db, cfg, out)
            import json
            items = [i for m in manifest["months"] for i in json.loads((out / m["file"]).read_text(encoding="utf-8"))["items"]]
            self.assertEqual(manifest["total"], len(items))
            merged = [i for i in items if len(i["src"]) > 1]
            self.assertEqual(len(merged), 1, [i["t"] for i in merged])
            self.assertEqual(set(merged[0]["src"]), {"quantocracy", "quantpedia"})
            self.assertNotIn("utm_", merged[0]["u"])
            self.assertGreaterEqual(merged[0]["p"], 20)
            reddit = next(i for i in items if i["src"] == ["reddit_algotrading"])
            self.assertTrue(reddit.get("tool"))
            listed = {s["id"]: s for s in manifest["sources"]}
            self.assertTrue(set(sources) <= set(listed))                 # içeriği olan her kaynak listede
            on = [s for s in listed.values() if cfg["sources"].get(s["id"], cfg["arxiv"]).get("enabled", True)]
            self.assertEqual(len({s["slot"] for s in on}), len(on))      # etkin kaynakların renkleri çakışmaz
            self.assertTrue(all(1 <= s["slot"] <= 8 for s in listed.values()))

            md, html = write_digest(db, cfg, days=3650)
            text = md.read_text(encoding="utf-8")
            self.assertIn("Araç sinyalleri", text)
            self.assertIn("Survivorship Bias", text)
            self.assertIn("<details", html.read_text(encoding="utf-8"))
            self.assertTrue((cfg["digest_dir"] / "latest.html").exists())
            db.close()


if __name__ == "__main__":
    unittest.main()
