"""LLM katmanı, özetler, e-posta ve yönetim komutları (internet gerekmez; LLM ve SMTP sahtedir).

Çalıştırma:  .venv\\Scripts\\python -m unittest discover tests
"""
import base64
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Testler ortamdaki gizli değerlerden etkilenmesin (bulut iş akışında tanımlıdır)
for _name in ("QIN_SITE_PASSWORD", "QIN_SITE_PASSWORD_OLD", "QIN_REQUIRE_PASSWORD", "QIN_ADMIN_PASSWORD",
              "QIN_ADMIN_TOKEN", "QIN_ADMIN_COMMAND", "GEMINI_API_KEY", "GROQ_API_KEY", "SMTP_USER",
              "SMTP_PASSWORD", "SMTP_HOST", "SMTP_PORT", "MAIL_FROM_NAME", "GITHUB_REPOSITORY", "GITHUB_REF_NAME"):
    os.environ.pop(_name, None)

import logging

import feedparser

logging.getLogger("qin").addHandler(logging.NullHandler())     # beklenen uyarılar test çıktısını kirletmesin

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qin import admin, brief, mailer, md, vault  # noqa: E402
from qin.common import iso, load_config, now_utc  # noqa: E402
from qin.export import build_items, export_site  # noqa: E402
from qin.fetch import store_posts  # noqa: E402
from qin.llm import LLM, LLMUnavailable, parse_json  # noqa: E402
from qin.parsers import parse_arxiv, parse_quantocracy, parse_reddit, parse_substack  # noqa: E402
from qin.private import Private  # noqa: E402
from qin.storage import DB  # noqa: E402
from qin.translate import translate_pending  # noqa: E402

FX = Path(__file__).parent / "fixtures"
SITE_PW = "çok gizli şifre öğün 42"
ADMIN_PW = "yalnızca yönetici bilir bunu 7"


def feed(name):
    return feedparser.parse((FX / name).read_bytes(), sanitize_html=False)


class FakeResponse:
    def __init__(self, status, content="", text=""):
        self.status_code, self._content, self.text = status, content, text or content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class FakeSession:
    """Sırayla verilen yanıtları döndürür; her yanıt bir FakeResponse ya da (gövde -> FakeResponse) işlevidir."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def post(self, url, json=None, timeout=None, headers=None):
        self.calls.append({"url": url, "body": json, "headers": headers})
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return reply(json) if callable(reply) else reply


PROVIDERS = {"llm": {"providers": [
    {"name": "a", "base_url": "https://a.test/v1/", "key_env": "QIN_TEST_KEY_A", "min_interval_seconds": 5,
     "models": {"brief": ["a-big", "a-small"], "translate": ["a-small"]}, "max_output_tokens": 900,
     "extra": {"reasoning_effort": "low"}},
    {"name": "b", "base_url": "https://b.test/v1", "key_env": "QIN_TEST_KEY_B", "models": ["b-one"]},
    {"name": "c", "base_url": "https://c.test/v1", "key_env": "QIN_TEST_KEY_YOK", "models": ["c-one"]},
]}}


class Env:
    """Ortam değişkenlerini test süresince ayarlar."""

    def __init__(self, **values):
        self.values = values

    def __enter__(self):
        self.old = {k: os.environ.get(k) for k in self.values}
        os.environ.update(self.values)

    def __exit__(self, *exc):
        for k, v in self.old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


KEYS = {"QIN_TEST_KEY_A": "ka", "QIN_TEST_KEY_B": "kb"}


def make_llm(*replies):
    session, naps = FakeSession(*replies), []
    return LLM(PROVIDERS, session=session, sleep=naps.append, clock=lambda: 100.0 + sum(naps)), session, naps


class LLMTest(unittest.TestCase):
    def test_only_providers_with_keys(self):
        with Env(**KEYS):
            llm, _, _ = make_llm(FakeResponse(200, "tamam"))
            self.assertEqual([p["name"] for p in llm.providers], ["a", "b"])
            self.assertTrue(llm.available)
        self.assertFalse(LLM(PROVIDERS).available)                     # anahtar yoksa hiçbir şey denenmez

    def test_falls_through_models_and_providers(self):
        with Env(**KEYS):
            llm, session, _ = make_llm(FakeResponse(500, text="boom"), FakeResponse(404, text="no model"),
                                       FakeResponse(200, "merhaba"))
            self.assertEqual(llm.chat("s", "u", max_tokens=5000, task="brief"), "merhaba")
            self.assertEqual(llm.last_model, "b/b-one")
            self.assertEqual([c["body"]["model"] for c in session.calls], ["a-big", "a-small", "b-one"])
            self.assertEqual(session.calls[0]["url"], "https://a.test/v1/chat/completions")
            self.assertEqual(session.calls[0]["headers"]["Authorization"], "Bearer ka")
            self.assertEqual(session.calls[0]["body"]["max_tokens"], 900)       # sağlayıcının tavanı
            self.assertEqual(session.calls[2]["body"]["max_tokens"], 5000)
            self.assertNotIn("reasoning_effort", session.calls[2]["body"])
            session.replies = [FakeResponse(200, "ikinci")]
            llm.chat("s", "u", task="brief")
            self.assertEqual(session.calls[-1]["body"]["model"], "b-one")       # ölü modeller yeniden denenmez

    def test_rate_limit_waits_once_and_bad_param_is_dropped(self):
        with Env(**KEYS):
            llm, session, naps = make_llm(FakeResponse(429, text="slow down"), FakeResponse(200, "geldi"))
            self.assertEqual(llm.chat("s", "u", task="translate"), "geldi")
            self.assertEqual(naps, [65])
            llm, session, _ = make_llm(FakeResponse(400, text="unknown field"), FakeResponse(200, "oldu"))
            self.assertEqual(llm.chat("s", "u", task="translate"), "oldu")
            self.assertIn("reasoning_effort", session.calls[0]["body"])
            self.assertEqual(session.calls[0]["body"]["temperature"], 0.3)
            self.assertEqual(set(session.calls[1]["body"]), {"model", "messages", "max_tokens"})   # yalın istek
            self.assertEqual(llm.last_model, "a/a-small")

    def test_all_fail(self):
        with Env(**KEYS):
            llm, _, _ = make_llm(FakeResponse(503, text="down"))
            with self.assertRaises(LLMUnavailable):
                llm.chat("s", "u", task="brief")
            self.assertFalse(llm.available)

    def test_time_budget(self):
        with Env(**KEYS):
            now = [0.0]
            llm = LLM({"llm": {**PROVIDERS["llm"], "max_minutes": 1}}, session=FakeSession(FakeResponse(200, "ok")),
                      sleep=lambda s: None, clock=lambda: now[0])
            self.assertEqual(llm.chat("s", "u"), "ok")
            now[0] = 61.0
            with self.assertRaises(LLMUnavailable):
                llm.chat("s", "u")
            self.assertEqual(llm.calls, 1)

    def test_parse_json(self):
        self.assertEqual(parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(parse_json('İşte sonuç:\n{"items": []} umarım yardımcı olur'), {"items": []})
        with self.assertRaises(ValueError):
            parse_json("json yok")


class MarkdownTest(unittest.TestCase):
    def test_render_is_safe_and_structured(self):
        html = md.render("# Baş <script>x</script>\n\n**Kısaca**\n- bir [3](https://a.b/c?x=1&y=2)\n  - alt\n- iki\n\n"
                         "Metin [kötü](javascript:alert(1)) ve https://ornek.com/yol.\n\n| A | B |\n|---|---|\n| 1 | 2 |")
        self.assertNotIn("<script>", html)
        self.assertIn("<h2>Baş &lt;script&gt;", html)
        self.assertIn('<a href="https://a.b/c?x=1&amp;y=2" class="cite"', html)
        self.assertIn("<ul><li>bir", html)
        self.assertIn("<ul><li>alt</li></ul>", html)
        self.assertNotIn('href="javascript', html)
        self.assertIn('<a href="https://ornek.com/yol"', html)
        self.assertIn("<table><thead><tr><th>A</th>", html)
        self.assertIn("başlık (https://x.y)", md.to_text("## Bölüm\n[başlık](https://x.y) **kalın** [2](https://z.w)"))


def filled_db(tmp):
    cfg = load_config()
    cfg["db_path"] = Path(tmp) / "t.db"
    db = DB(cfg["db_path"])
    store_posts(db, "quantseeker", parse_substack(feed("quantseeker.xml")))
    store_posts(db, "quantocracy", parse_quantocracy(feed("quantocracy.xml")))
    store_posts(db, "reddit_algotrading", parse_reddit(feed("reddit.xml")))
    store_posts(db, "arxiv", parse_arxiv(feed("arxiv.xml"), "LLM ve AI ajanlari"))
    db.commit()
    return cfg, db


class TranslateTest(unittest.TestCase):
    def test_translations_reach_the_site(self):
        def reply(body):
            asked = json.loads(body["messages"][1]["content"])["items"]
            rows = [{"id": str(i["id"]), "t": "TR " + i["t"], "s": "TR özet"} for i in asked]
            rows.append({"id": 999999, "t": "uydurma"})                   # istenmeyen id yok sayılır
            return FakeResponse(200, "```json\n" + json.dumps({"items": rows}, ensure_ascii=False) + "\n```")

        with tempfile.TemporaryDirectory() as tmp, Env(**KEYS):
            cfg, db = filled_db(tmp)
            cfg["llm"] = {**PROVIDERS["llm"], "translate": {"max_age_days": None, "max_items_per_request": 5}}
            llm = LLM(cfg, session=FakeSession(reply), sleep=lambda s: None)
            items = build_items(db)
            wanted = [i for i in items if i["k"] != "iş ilanı"]
            line = translate_pending(db, cfg, llm, items)
            self.assertIn(f"{len(wanted)} içerik çevrildi, 0 bekliyor", line)
            self.assertGreater(llm.calls, 1)                              # parçalara bölündü
            after = build_items(db)
            done = [i for i in after if i.get("tr")]
            self.assertEqual(len(done), len(wanted))
            self.assertTrue(all(i["tr"]["tr"]["t"].startswith("TR ") for i in done))
            no_summary = next(i for i in done if not i.get("s"))
            self.assertIsNone(no_summary["tr"]["tr"]["s"])                # özeti olmayana özet uydurulmaz
            self.assertEqual(translate_pending(db, cfg, llm, after), "Çeviri: bekleyen içerik yok")
            db.close()


class BriefTest(unittest.TestCase):
    NOW = datetime(2026, 10, 7, 5, 30, tzinfo=timezone.utc)              # Çarşamba 08:30 İstanbul

    def test_periods(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = DB(Path(tmp) / "t.db")
            period, start, end = brief.due(db, {}, "weekly", self.NOW)
            self.assertEqual(period, "2026-W40")                          # tamamlanmış son hafta: 28 Eyl – 4 Eki
            self.assertEqual((start, end), ("2026-09-27T21:00:00+00:00", "2026-10-04T21:00:00+00:00"))
            self.assertEqual(brief.period_label("weekly", period), "28 Eylül – 4 Ekim 2026")
            period, start, end = brief.due(db, {}, "daily", self.NOW)
            self.assertEqual(period, "2026-10-07")
            self.assertEqual((start, end), (iso(self.NOW - timedelta(hours=30)), iso(self.NOW)))
            db.save_brief("daily", "2026-10-06", "llm", "dün", "gövde")
            db.conn.execute("UPDATE briefs SET created_at=?", ("2026-10-06T05:20:00+00:00",))
            self.assertEqual(brief.due(db, {}, "daily", self.NOW)[1], "2026-10-06T05:20:00+00:00")
            # gece yarısından sonra, İstanbul saatiyle yeni gün
            self.assertEqual(brief.due(db, {}, "daily", datetime(2026, 10, 7, 21, 30, tzinfo=timezone.utc))[0], "2026-10-08")
            self.assertEqual(brief.manual_period("weekly", "2026-10-07"), "2026-W41")
            self.assertEqual(brief.period_label("daily", "2026-10-07"), "7 Ekim 2026")
            db.close()

    def test_select_keeps_variety(self):
        pool = ([{"id": n, "k": "tartışma", "p": 90 - n, "d": "2026-10-01", "src": ["r"]} for n in range(10)]
                + [{"id": 100 + n, "k": "makale", "p": 40 - n, "d": "2026-10-01", "src": ["a"], "s": "x"} for n in range(10)])
        picked = brief.select(pool, 8)
        kinds = [i["k"] for i in picked]
        self.assertEqual(kinds[:6].count("tartışma"), 2)                 # önce tavanlar: tartışma en fazla dörtte bir
        self.assertEqual(kinds.count("makale"), 4)                      # puanı düşük olsa da makaleler yer bulur
        self.assertEqual(len(picked), 8)                                # kalan yer güce göre dolar
        self.assertEqual(len(brief.select(pool[:3], 8)), 3)

    def test_finish_links_citations(self):
        picked = [{"t": "Bir [x]", "u": "https://a.test/1", "src": ["arxiv"]},
                  {"t": "İki", "u": "https://a.test/2", "src": ["quantocracy", "arxiv"]}]
        text = "```markdown\n# Asıl başlık\n\n**Kısaca**\n- Önemli [1].\n\n## Tema\n" + "Uzun bir paragraf. " * 20 + "[1, 2] ve uydurma [9].\n```"
        title, body = brief.finish(text, picked, {"arxiv": "arXiv", "quantocracy": "Quantocracy"}, "yedek")
        self.assertEqual(title, "Asıl başlık")
        self.assertNotIn("# Asıl başlık", body)
        self.assertIn("Önemli [1](https://a.test/1).", body)
        self.assertIn("[1](https://a.test/1)[2](https://a.test/2) ve uydurma .", body)
        self.assertIn("- **[2]** [İki](https://a.test/2) · Quantocracy, arXiv", body)
        self.assertIn("[Bir (x)](https://a.test/1)", body)
        with self.assertRaises(ValueError):
            brief.finish("# Başlık\n" + "atıfsız metin " * 40, picked, {}, "yedek")

    def test_generate_stores_once(self):
        answer = ("# Haftanın özeti\n\n**Kısaca**\n- Birinci çıkarım [1].\n- İkinci çıkarım [2].\n\n## Tema\n"
                  + "Bu hafta öne çıkan çalışmalar birbirini tamamlıyor. " * 8 + "[1][3]\n\n## Radar\n- Kısa not [2].")
        with tempfile.TemporaryDirectory() as tmp, Env(**KEYS):
            cfg, db = filled_db(tmp)
            cfg["llm"] = {**PROVIDERS["llm"], "briefs": {"weekly_min_items": 3, "daily_min_items": 3}}
            db.conn.execute("UPDATE items SET published='2026-10-01T10:00:00+00:00', first_seen='2026-10-07T05:00:00+00:00'")
            db.commit()
            session = FakeSession(FakeResponse(200, answer))
            llm = LLM(cfg, session=session, sleep=lambda s: None)
            items = build_items(db)
            self.assertTrue(all("_seen" in i for i in items))
            lines = brief.generate_due(db, cfg, llm, items, now=self.NOW)
            self.assertIn("2026-10-07 hazır", lines[0])
            self.assertIn("2026-W40 hazır", lines[1])
            prompt = session.calls[-1]["body"]["messages"]
            self.assertIn("haftalık", prompt[0]["content"])
            self.assertIn("[1] ", prompt[1]["content"])
            self.assertLessEqual(len(prompt[1]["content"]), 10200)
            self.assertNotIn("iş ilanı", prompt[1]["content"])
            stored = db.find_brief("weekly", "2026-W40")
            self.assertEqual((stored["title"], stored["model"], stored["sent_at"]), ("Haftanın özeti", "a/a-big", None))
            self.assertIn("## Bu özetteki içerikler", stored["body"])
            self.assertRegex(stored["body"], r"Birinci çıkarım \[1\]\(https?://")
            again = brief.generate_due(db, cfg, llm, items, now=self.NOW)
            self.assertTrue(all("zaten var" in line for line in again))
            self.assertEqual(len(db.briefs()), 2)
            # bozuk yanıt kaydedilmez
            llm2 = LLM(cfg, session=FakeSession(FakeResponse(200, "Üzgünüm, yardımcı olamam.")), sleep=lambda s: None)
            line = brief.generate(db, cfg, llm2, items, "weekly", now=self.NOW, force=True)
            self.assertIn("üretilemedi", line)
            self.assertEqual(db.find_brief("weekly", "2026-W40")["title"], "Haftanın özeti")

            out = Path(tmp) / "site"
            manifest = export_site(db, cfg, out)
            self.assertEqual(manifest["briefs"]["n"], 2)
            data = json.loads((out / "briefs.json").read_text(encoding="utf-8"))
            self.assertEqual({b["k"] for b in data["briefs"]}, {"daily", "weekly"})
            month = json.loads((out / manifest["months"][0]["file"]).read_text(encoding="utf-8"))
            self.assertFalse(any(k.startswith("_") for i in month["items"] for k in i))   # iç alanlar siteye yazılmaz
            db.close()


class FakeSMTP:
    def __init__(self, fail=(), drop_after=None):
        self.sent, self.fail, self.login_args, self.closed = [], set(fail), None, False
        self.drop_after = drop_after                    # bu kadar gönderimden sonra bağlantı kopar

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, msg):
        import smtplib
        if self.drop_after is not None and len(self.sent) >= self.drop_after:
            raise ConnectionResetError("bağlantı koptu")
        if msg["To"] in self.fail:
            raise smtplib.SMTPRecipientsRefused({msg["To"]: (550, b"no such user")})
        self.sent.append(msg)

    def quit(self):
        self.closed = True


def command(db, ops, password=ADMIN_PW, ts=None, cid="c1"):
    """Panelin yaptığı gibi: komutu yönetim anahtarıyla şifreleyip base64 metne çevirir."""
    cmd = {"id": cid, "ts": ts or iso(now_utc()).replace("+00:00", ".000Z"), "ops": ops}
    return base64.b64encode(vault.seal(admin.admin_key(db, password), json.dumps(cmd).encode())).decode()


class AdminTest(unittest.TestCase):
    MAIL = {"SMTP_USER": "ozet@ornek.com", "SMTP_PASSWORD": "abcd efgh ijkl mnop"}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg, self.db = filled_db(self.tmp.name)
        self.out = Path(self.tmp.name) / "site"
        export_site(self.db, self.cfg, self.out, password=SITE_PW)          # tuz oluşsun

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def subs(self):
        return Private(self.db, ADMIN_PW).subscribers

    def add_sub(self, *emails):
        p = Private(self.db, ADMIN_PW)
        for e in emails:
            p.add(e)
        p.save()

    def test_bundle_opens_site_and_stays_private(self):
        self.add_sub("ali@ornek.com")
        with Env(QIN_ADMIN_PASSWORD=ADMIN_PW, QIN_ADMIN_TOKEN="github_pat_GIZLI", GITHUB_REPOSITORY="Kisi/quant-intel"):
            manifest = export_site(self.db, self.cfg, self.out, password=SITE_PW)
        self.assertTrue(manifest["admin"])
        lock = json.loads((self.out / "lock.json").read_text())
        self.assertTrue(lock["admin"])
        raw = (self.out / "admin.bin").read_bytes()
        self.assertNotIn(b"github_pat", raw)
        self.assertNotIn(b"ali@ornek.com", raw)
        salt = base64.b64decode(lock["salt"])
        data = json.loads(vault.unseal(vault.derive_key(ADMIN_PW, salt), raw))
        self.assertEqual((data["token"], data["repo"], data["workflow"], data["ref"]),
                         ("github_pat_GIZLI", "Kisi/quant-intel", "gunluk.yml", "main"))
        self.assertEqual(data["subscribers"], ["ali@ornek.com"])
        self.assertFalse(data["mail"])
        self.assertFalse(data["locked"])
        site_key = base64.b64decode(data["key"])                        # yönetim parolası siteyi de açar
        self.assertEqual(site_key, vault.derive_key(SITE_PW, salt))
        json.loads(vault.unseal(site_key, (self.out / "manifest.bin").read_bytes()))
        from cryptography.exceptions import InvalidTag
        with self.assertRaises(InvalidTag):                               # site parolası yönetim paketini açamaz
            vault.unseal(site_key, raw)
        export_site(self.db, self.cfg, self.out, password=SITE_PW)       # yönetim parolası kalkınca paket silinir
        self.assertFalse((self.out / "admin.bin").exists())
        with Env(QIN_ADMIN_PASSWORD=SITE_PW):
            with self.assertRaises(ValueError):
                export_site(self.db, self.cfg, self.out, password=SITE_PW)
        with Env(QIN_ADMIN_PASSWORD="kısa parola 1"):
            with self.assertRaises(ValueError):
                export_site(self.db, self.cfg, self.out, password=SITE_PW)

    def test_save_subscribe_and_publish(self):
        smtp = FakeSMTP(fail={"yok@ornek.com"})
        ops = [{"op": "sub.add", "emails": ["Ali@Ornek.com", "veli@ornek.com", "yok@ornek.com", "ali@ornek.com"]},
               {"op": "brief.save", "kind": "weekly", "date": "2026-10-07", "title": "Elle yazılan özet",
                "body": "## Bölüm\nMetin **kalın** ve [bağlantı](https://ornek.com/a)."},
               {"op": "brief.send", "id": "last", "to": "all"}]
        with Env(**self.MAIL, GITHUB_REPOSITORY="Kisi/quant-intel"):
            result = admin.apply(self.db, self.cfg, command(self.db, ops), ADMIN_PW, smtp_factory=lambda s: smtp)
        self.assertFalse(result["ok"])                                     # bir adres reddedildi
        self.assertEqual(self.subs(), ["ali@ornek.com", "veli@ornek.com", "yok@ornek.com"])
        b = self.db.briefs()[0]
        self.assertEqual((b["kind"], b["period"], b["origin"], b["sent_to"]), ("weekly", "2026-W41", "manual", 2))
        self.assertIsNotNone(b["sent_at"])
        self.assertEqual(smtp.login_args, ("ozet@ornek.com", "abcdefghijklmnop"))
        self.assertTrue(smtp.closed)
        self.assertEqual([m["To"] for m in smtp.sent], ["ali@ornek.com", "veli@ornek.com"])   # herkese ayrı e-posta
        msg = smtp.sent[0]
        self.assertEqual(msg["Subject"], "Elle yazılan özet · Haftalık özet")
        self.assertIn("ozet@ornek.com", msg["From"])
        html = msg.get_body(("html",)).get_content()
        self.assertIn("<strong>kalın</strong>", html)
        self.assertIn(f"https://kisi.github.io/quant-intel/#tab=briefs&amp;brief={b['id']}", html)
        self.assertNotIn("veli@ornek.com", msg.as_string())
        self.assertIn("bağlantı (https://ornek.com/a)", msg.get_body(("plain",)).get_content())
        # herkese açık günlükte adres yok; ayrıntı yalnızca panele gider
        self.assertFalse(any("@" in line for line in result["public"]), result["public"])
        self.assertTrue(any("yok@ornek.com" in line for line in result["log"]))
        self.assertEqual(Private(self.db, ADMIN_PW).last["log"], result["log"])

    def test_test_send_edit_delete(self):
        llm_id = self.db.save_brief("daily", "2026-10-06", "llm", "Otomatik", "gövde")
        smtp = FakeSMTP()
        ops = [{"op": "brief.save", "id": llm_id, "kind": "weekly", "date": "2026-01-01", "title": "Düzeltilmiş", "body": "yeni gövde"},
               {"op": "brief.send", "id": llm_id, "to": ["Ben@Ornek.com"]},
               {"op": "sub.add", "emails": ["a@b.co"]}, {"op": "sub.remove", "emails": ["a@b.co"]}]
        with Env(**self.MAIL):
            result = admin.apply(self.db, self.cfg, command(self.db, ops), ADMIN_PW, smtp_factory=lambda s: smtp)
        self.assertTrue(result["ok"], result["log"])
        b = self.db.brief(llm_id)
        self.assertEqual((b["title"], b["kind"], b["period"], b["origin"]), ("Düzeltilmiş", "daily", "2026-10-06", "llm"))
        self.assertIsNone(b["sent_at"])                                    # deneme gönderimi "yayınlandı" saymaz
        self.assertEqual([m["To"] for m in smtp.sent], ["ben@ornek.com"])
        self.assertEqual(self.subs(), [])
        result = admin.apply(self.db, self.cfg, command(self.db, [{"op": "brief.delete", "id": llm_id}], cid="c2"), ADMIN_PW)
        self.assertTrue(result["ok"])
        self.assertIsNone(self.db.brief(llm_id))

    def test_rejections(self):
        save = [{"op": "brief.save", "kind": "daily", "date": "2026-10-07", "title": "t", "body": "b"}]
        ok = admin.apply(self.db, self.cfg, command(self.db, save, cid="tek"), ADMIN_PW)
        self.assertTrue(ok["ok"])
        cases = {
            "yinelenen": command(self.db, save, cid="tek"),
            "yanlış parola": command(self.db, save, password=SITE_PW, cid="x1"),
            "eski": command(self.db, save, ts="2026-01-01T00:00:00Z", cid="x2"),
            "bozuk": "bu bir komut değil",
            "bilinmeyen işlem": command(self.db, [{"op": "db.drop"}], cid="x3"),
            "geçersiz adres": command(self.db, [{"op": "sub.add", "emails": ["a@b.co\nBcc: x@y.z"]}], cid="x4"),
            "abonesiz gönderim": command(self.db, [{"op": "brief.send", "id": 1}], cid="x5"),
            "olmayan özet": command(self.db, [{"op": "brief.delete", "id": 4242}], cid="x6"),
            "boş gövde": command(self.db, [{"op": "brief.save", "kind": "daily", "date": "2026-10-07", "title": "t", "body": " "}], cid="x7"),
        }
        for name, payload in cases.items():
            with self.subTest(name):
                result = admin.apply(self.db, self.cfg, payload, ADMIN_PW)
                self.assertFalse(result["ok"])
                self.assertTrue(result["log"][-1].startswith("HATA"))
        self.assertEqual(len(self.db.briefs()), 1)
        self.assertEqual(self.subs(), [])
        missing = admin.apply(self.db, self.cfg, command(self.db, save, cid="x9"))   # ADMIN_SIFRESI tanımsız
        self.assertFalse(missing["ok"])
        self.assertIn("ADMIN_SIFRESI", missing["log"][-1])
        two_lines = [{"op": "brief.save", "kind": "daily", "date": "2026-10-08", "title": "iki\nsatır  başlık", "body": "b"}]
        self.assertTrue(admin.apply(self.db, self.cfg, command(self.db, two_lines, cid="x10"), ADMIN_PW)["ok"])
        self.assertEqual(self.db.briefs()[0]["title"], "iki satır başlık")
        self.db.delete_brief(self.db.briefs()[0]["id"])
        self.add_sub("a@b.co")                                             # e-posta ayarlı değilken gönderim
        result = admin.apply(self.db, self.cfg, command(self.db, [{"op": "brief.send", "id": 1}], cid="x8"), ADMIN_PW)
        self.assertFalse(result["ok"])
        self.assertIn("SMTP_USER", result["log"][-1])
        self.assertIsNone(self.db.brief(1)["sent_at"])

    def test_subscribers_need_the_admin_password(self):
        """Arşiv site parolasıyla açılır; abone adresleri ise yalnızca yönetim parolasıyla okunabilmeli."""
        ops = [{"op": "sub.add", "emails": ["gizli.abone@ornek.com"]},
               {"op": "brief.save", "kind": "daily", "date": "2026-10-07", "title": "t", "body": "b"},
               {"op": "brief.send", "id": "last", "to": "all"}]
        with Env(**self.MAIL):
            result = admin.apply(self.db, self.cfg, command(self.db, ops), ADMIN_PW,
                                 smtp_factory=lambda s: FakeSMTP(fail={"gizli.abone@ornek.com"}))
        self.assertIn("gizli.abone@ornek.com", result["log"][-1])            # panel ayrıntıyı görür
        self.db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        raw = Path(self.cfg["db_path"]).read_bytes()
        self.assertNotIn(b"gizli.abone", raw)                               # arşivde düz metin olarak yok
        self.assertFalse(self.db.get_meta("private").startswith("{"))
        other = Private(self.db, "bambaşka bir yönetim parolası 9")           # yanlış / değişmiş parola
        self.assertTrue(other.locked)
        self.assertEqual(other.subscribers, [])
        other.add("yeni@ornek.com")
        other.save()                                                        # eski kayıt silinmez, yedeğe alınır
        self.assertEqual(Private(self.db, "bambaşka bir yönetim parolası 9").subscribers, ["yeni@ornek.com"])
        self.assertTrue(self.db.get_meta("private_onceki"))
        plain = DB(Path(self.tmp.name) / "yerel.db")                         # yönetim parolasız yerel kullanım
        p = Private(plain)
        p.add("a@b.co")
        p.save()
        self.assertEqual((Private(plain).subscribers, Private(plain).plain), (["a@b.co"], True))
        plain.close()

    def test_retries_do_not_duplicate(self):
        """Panel bir işlemi başarısız sanıp yeniden gönderirse özet iki kez eklenmez, e-posta iki kez gitmez."""
        self.add_sub("ali@ornek.com", "veli@ornek.com")
        save = {"op": "brief.save", "draft": "taslak-1", "kind": "weekly", "date": "2026-10-07", "title": "İlk hali", "body": "b"}
        send = {"op": "brief.send", "id": "last", "to": "all"}
        first, second = FakeSMTP(), FakeSMTP()
        with Env(**self.MAIL):
            a = admin.apply(self.db, self.cfg, command(self.db, [save, send], cid="r1"), ADMIN_PW, smtp_factory=lambda s: first)
            b = admin.apply(self.db, self.cfg, command(self.db, [{**save, "title": "Düzeltilmiş"}, send], cid="r2"), ADMIN_PW,
                            smtp_factory=lambda s: second)
        self.assertTrue(a["ok"])
        self.assertFalse(b["ok"])
        self.assertIn("zaten gönderilmiş", b["log"][-1])
        self.assertEqual((len(first.sent), len(second.sent)), (2, 0))
        briefs = self.db.briefs()
        self.assertEqual([x["title"] for x in briefs], ["Düzeltilmiş"])      # aynı taslak: tek kayıt, güncellenmiş
        third = FakeSMTP()
        with Env(**self.MAIL):                                              # bilerek yeniden yayınlama
            c = admin.apply(self.db, self.cfg, command(self.db, [{"op": "brief.send", "id": briefs[0]["id"], "to": "all", "again": True}],
                                                       cid="r3"), ADMIN_PW, smtp_factory=lambda s: third)
        self.assertTrue(c["ok"])
        self.assertEqual(len(third.sent), 2)

    def test_connection_drop_keeps_what_was_sent(self):
        self.add_sub("a@ornek.com", "b@ornek.com", "c@ornek.com")
        brief_id = self.db.save_brief("daily", "2026-10-07", "manual", "t", "b")
        smtp = FakeSMTP(drop_after=1)
        with Env(**self.MAIL, SMTP_PORT="yanlış"):
            self.assertEqual(mailer.settings()["port"], 587)                 # bozuk değer çalışmayı durdurmaz
            result = admin.apply(self.db, self.cfg, command(self.db, [{"op": "brief.send", "id": brief_id}]), ADMIN_PW,
                                 smtp_factory=lambda s: smtp)
        self.assertFalse(result["ok"])
        self.assertIn("1 aboneye gönderildi, 2 başarısız", result["public"][0])
        self.assertEqual(self.db.brief(brief_id)["sent_to"], 1)              # gönderilen kayda geçti: yeniden deneme çift atmaz

    def test_rejected_command_reaches_the_panel(self):
        save = [{"op": "brief.save", "kind": "daily", "date": "2026-10-07", "title": "t", "body": "b"}]
        ok = admin.apply(self.db, self.cfg, command(self.db, save, cid="ilk"), ADMIN_PW)
        self.assertEqual(Private(self.db, ADMIN_PW).last["id"], "ilk")
        replay = admin.apply(self.db, self.cfg, command(self.db, save, cid="ilk"), ADMIN_PW)
        self.assertFalse(replay["ok"])
        self.assertTrue(Private(self.db, ADMIN_PW).last["ok"])               # yineleme ilk sonucu ezmez
        old = admin.apply(self.db, self.cfg, command(self.db, save, ts="2026-01-01T00:00:00Z", cid="eski"), ADMIN_PW)
        last = Private(self.db, ADMIN_PW).last
        self.assertEqual((old["id"], last["id"], last["ok"]), ("eski", "eski", False))   # panel nedenini görebilir
        self.assertIn("süresi dolmuş", last["log"][-1])
        self.assertTrue(ok["ok"])


if __name__ == "__main__":
    unittest.main()
