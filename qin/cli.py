"""Komut satırı: fetch, llm, export, serve, brief, sub, admin, digest, weekly, search, mark, radar, stats, reparse."""
from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler

from .common import load_config, shorten
from .digest import write_digest
from .export import SITE_DIR, build_items, export_site
from .fetch import fetch_all, make_session, reparse
from .metrics import refresh_all
from .storage import DB, STATUSES


def _setup_io(cfg: dict) -> None:
    # pythonw (zamanlanmış görev) altında stdout yoktur; konsolda ise UTF-8 zorla
    if sys.stdout is None or sys.stderr is None:
        import io, os
        devnull = open(os.devnull, "w", encoding="utf-8")
        sys.stdout = sys.stdout or devnull
        sys.stderr = sys.stderr or devnull
    else:
        for s in (sys.stdout, sys.stderr):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
    cfg["log_dir"].mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(cfg["log_dir"] / "qin.log", maxBytes=1_000_000, backupCount=3,
                                  encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger("qin")
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _row(r) -> str:
    meta = " · ".join(m for m in (r["source"], r["kind"], r["status"]) if m)
    return f"#{r['id']:<6} {shorten(r['title'], 90)}\n        {meta}\n        {r['url']}"


def migrate(db, cfg) -> None:
    """Eski sürümle oluşturulmuş arşivi yeni kurallara taşır (bir kez çalışır)."""
    version = int(db.get_meta("schema_version", "1"))
    if version < 2:
        has_posts = db.conn.execute("SELECT 1 FROM posts LIMIT 1").fetchone()
        if has_posts:
            n = reparse(db, cfg)
            msg = f"Arşiv yeni sürüme taşındı: {n} bülten öğesi yeniden ayrıştırıldı."
            print(msg)
            logging.getLogger("qin").info(msg)
        db.set_meta("schema_version", "2")


def _say(line: str) -> None:
    print(line)
    logging.getLogger("qin").info(line)


def cmd_fetch(db, cfg, args):
    _say("Çekme başladı")
    for line in fetch_all(db, cfg, args.only):
        _say(line)
    if not args.only:
        for line in refresh_all(db, cfg, make_session(cfg)):
            _say(line)
    cmd_export(db, cfg, args)
    last = db.last_fetch_per_source()
    if not args.only and last and not any(f["ok"] for f in last):
        _say("Hiçbir kaynağa ulaşılamadı (internet ya da erişim sorunu).")
        return 2                    # otomatik çalışmada işin başarısız sayılması için


def cmd_export(db, cfg, args):
    m = export_site(db, cfg)
    kip = "şifreli" if m.get("locked") else "şifresiz, yalnızca bu bilgisayar için"
    _say(f"Site verisi güncellendi: {m['total']} içerik, {len(m['months'])} ay ({kip})")


def cmd_llm(db, cfg, args):
    """Yeni içeriği Türkçeye çevirir ve dönemi gelen özetleri yazar. LLM'e ulaşılamazsa site yine güncellenir."""
    import json

    from .brief import generate_due
    from .common import iso, now_utc
    from .llm import LLM
    from .translate import translate_pending

    llm = LLM(cfg)
    if not cfg.get("llm", {}).get("enabled", True):
        _say("LLM: kapalı (config.json > llm.enabled)")
        return
    if not llm.providers:
        _say("LLM: API anahtarı tanımlı değil; çeviri ve özet atlandı (bkz. YAYIN.md).")
        return
    lines = []
    try:
        items = build_items(db)
        if not args.no_brief:                       # önce özet: kota biterse çeviri ertesi güne kalabilir
            lines += generate_due(db, cfg, llm, items, only=args.brief, force=args.force)
        if not args.no_translate:
            lines.append(translate_pending(db, cfg, llm, items))
    except Exception as ex:                         # LLM hatası günlük çalışmayı durdurmaz
        logging.getLogger("qin").exception("LLM adımı yarıda kaldı")
        lines.append(f"LLM adımı yarıda kaldı: {type(ex).__name__}")
        llm.errors.append(f"{type(ex).__name__}: {str(ex)[:200]}")
    for line in lines:
        _say(line)
    db.set_meta("llm_last", json.dumps({"at": iso(now_utc()), "calls": llm.calls, "model": llm.last_model,
                                        "lines": lines, "errors": llm.errors[-6:]}, ensure_ascii=False))
    cmd_export(db, cfg, args)


def cmd_admin(db, cfg, args):
    """Yönetim panelinden gelen şifreli komutu uygular (bulut iş akışı çağırır)."""
    import os

    from . import admin
    payload = args.payload or os.environ.get("QIN_ADMIN_COMMAND", "")
    result = {"ok": False}
    try:
        if payload.strip():
            result = admin.apply(db, cfg, payload)
            for line in result["public"]:           # e-posta adresleri ve özet metni günlüğe yazılmaz
                _say(line)
        else:
            _say("Komut yok (QIN_ADMIN_COMMAND boş).")
    finally:
        cmd_export(db, cfg, args)                   # komut uygulanamasa da site verisi üretilir (yayın durmasın)
    return 0 if result["ok"] else 3


def cmd_brief(db, cfg, args):
    from . import mailer
    from .brief import manual_period, period_label
    from .common import now_utc
    from .private import Private

    if args.action == "list":
        for b in db.briefs(args.limit):
            sent = f"gönderildi ({b['sent_to']})" if b["sent_at"] else "gönderilmedi"
            print(f"#{b['id']:<4} {b['kind']:<7} {period_label(b['kind'], b['period']):<28} {b['origin']:<7} "
                  f"{sent:<16} {shorten(b['title'], 70)}")
        return
    if args.action == "add":
        from pathlib import Path
        body = Path(args.file).read_text(encoding="utf-8-sig").strip()
        title = args.title
        if not title and body.startswith("# "):     # başlık verilmediyse dosyanın ilk satırı
            title, _, body = body[2:].partition("\n")
        if not title or not body.strip():
            print("Başlık ve metin gerekli (--title ya da dosyanın ilk satırı '# Başlık').")
            return 1
        day = args.date or now_utc().strftime("%Y-%m-%d")
        brief_id = db.save_brief(args.kind, manual_period(args.kind, day), "manual", title.strip(), body.strip())
        print(f"Özet #{brief_id} eklendi.")
    elif args.action == "delete":
        print(f"#{args.id} silindi." if db.delete_brief(args.id) else f"#{args.id} bulunamadı.")
    elif args.action == "send":
        b = db.brief(args.id)
        if not b:
            print(f"#{args.id} bulunamadı.")
            return 1
        to = args.to or Private(db).subscribers
        if not to:
            print("Abone yok. Önce: qin sub add adres@ornek.com")
            return 1
        try:
            sent, failed = mailer.send_brief(b, to, cfg)
        except (RuntimeError, OSError) as ex:
            print(f"Gönderilemedi: {ex}")
            return 1
        if sent and not args.to:
            db.mark_brief_sent(b["id"], len(sent))
        print(f"{len(sent)} adrese gönderildi." + "".join(f"\n  başarısız: {f}" for f in failed))
    export_site(db, cfg)


def cmd_sub(db, cfg, args):
    from . import mailer
    from .private import Private
    private = Private(db)
    if private.locked:
        print("Abone kaydı başka bir yönetim parolasıyla şifreli; okunamadı.")
        return 1
    if args.action == "list":
        print("\n".join(private.subscribers) if private.subscribers else "Abone yok.")
        return
    emails, bad = mailer.clean_emails(args.emails)
    for e in bad:
        print(f"Geçersiz adres: {e}")
    change = private.add if args.action == "add" else private.remove
    n = sum(1 for e in emails if change(e))
    private.save()
    print(f"{n} abone {'eklendi' if args.action == 'add' else 'çıkarıldı'} (toplam {len(private.subscribers)}).")
    export_site(db, cfg)


def cmd_reparse(db, cfg, args):
    _say(f"{reparse(db, cfg)} bülten öğesi yeniden ayrıştırıldı.")
    cmd_export(db, cfg, args)


def cmd_vault(args) -> int:
    """Arşiv dosyasını şifreler / açar (bulut iş akışı kullanır)."""
    import os
    from pathlib import Path

    from . import vault
    src, dst = Path(args.src), Path(args.dst)
    try:
        if args.action == "seal":
            vault.seal_file(src, dst, os.environ.get("QIN_SITE_PASSWORD", ""))
        else:
            vault.open_file(src, dst, [os.environ.get("QIN_SITE_PASSWORD", ""),
                                       os.environ.get("QIN_SITE_PASSWORD_OLD", "")])
    except ValueError as ex:
        print(f"HATA: {ex}")
        return 1
    print(f"{src.name} -> {dst.name}")
    return 0


def cmd_serve(db, cfg, args):
    import functools
    import threading
    import webbrowser
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    data = SITE_DIR / "data"
    if not (data / "manifest.json").exists() and not (data / "lock.json").exists():
        cmd_export(db, cfg, args)

    class Handler(SimpleHTTPRequestHandler):
        # Windows bazen .js dosyalarını yanlış türle sunar ve tarayıcı modülleri reddeder; açıkça belirt.
        extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript",
                          ".css": "text/css", ".json": "application/json", ".html": "text/html",
                          ".svg": "image/svg+xml", ".woff2": "font/woff2"}

        def end_headers(self):                      # veri her çekmede değişir: önbelleğe alma
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, *a):
            pass

    port = args.port or cfg.get("site_port", 8765)
    server = ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler, directory=str(SITE_DIR)))
    url = f"http://localhost:{port}/"
    print(f"Site çalışıyor: {url}\nKapatmak için bu pencereyi kapatın ya da Ctrl+C.")
    if not args.no_browser:
        threading.Timer(0.6, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def cmd_digest(db, cfg, args):
    md, html = write_digest(db, cfg, args.days)
    print(f"Özet yazıldı:\n  {md}\n  {html}")
    logging.getLogger("qin").info("Özet yazıldı: %s", html)


def cmd_weekly(db, cfg, args):
    args.only = None
    cmd_fetch(db, cfg, args)
    cmd_digest(db, cfg, args)


def cmd_search(db, cfg, args):
    rows = db.search(" ".join(args.query), args.limit)
    print(f"{len(rows)} sonuç\n")
    for r in rows:
        print(_row(r))


def cmd_mark(db, cfg, args):
    try:
        ok = db.set_status(args.id, args.status, args.note)
    except ValueError as ex:
        print(ex)
        return 1
    print(f"#{args.id} → {args.status}" if ok else f"#{args.id} bulunamadı")
    if ok:
        export_site(db, cfg)        # işaret sitede de görünsün


def cmd_radar(db, cfg, args):
    rows = db.by_status(args.status or ["ilginç", "denenecek"])
    if not rows:
        print("Radar boş. Özetteki bir öğeyi işaretle: qin mark <id> ilginç")
    for r in rows:
        print(_row(r) + (f"\n        not: {r['note']}" if r["note"] else ""))


def cmd_stats(db, cfg, args):
    print("Kaynak                 Öğe   İlk                  Son")
    for r in db.stats():
        print(f"{r['source']:<20} {r['n']:>5}   {(r['first'] or '')[:16]:<20} {(r['last'] or '')[:16]}")
    print("\nSon çekme:")
    for f in db.last_fetch_per_source():
        state = "OK" if f["ok"] else f"HATA: {shorten(f['error'] or '', 100)}"
        print(f"  {f['source']:<20} {f['ran_at'][:16]}  {state}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="qin", description="Quant Intelligence Network")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="Tüm kaynakları çek ve kaydet")
    f.add_argument("--only", nargs="+", help="Yalnızca bu kaynaklar (ör. quantseeker arxiv)")
    f.set_defaults(func=cmd_fetch)

    d = sub.add_parser("digest", help="Haftalık özeti üret (Markdown + HTML)")
    d.add_argument("--days", type=int, help="Kaç günlük özet (varsayılan: config)")
    d.set_defaults(func=cmd_digest)

    w = sub.add_parser("weekly", help="Çek + özet üret")
    w.add_argument("--days", type=int)
    w.set_defaults(func=cmd_weekly)

    s = sub.add_parser("search", help="Arşivde tam metin arama")
    s.add_argument("query", nargs="+")
    s.add_argument("--limit", type=int, default=30)
    s.set_defaults(func=cmd_search)

    m = sub.add_parser("mark", help="Öğenin durumunu değiştir")
    m.add_argument("id", type=int)
    m.add_argument("status", help=" / ".join(STATUSES))
    m.add_argument("--note", help="Kısa not")
    m.set_defaults(func=cmd_mark)

    r = sub.add_parser("radar", help="İşaretlenmiş öğeleri listele")
    r.add_argument("--status", nargs="+", help="Varsayılan: ilginç denenecek")
    r.set_defaults(func=cmd_radar)

    st = sub.add_parser("stats", help="Arşiv ve kaynak durumu")
    st.set_defaults(func=cmd_stats)

    lm = sub.add_parser("llm", help="Yeni içeriği Türkçeye çevir, dönemi gelen özetleri yaz")
    lm.add_argument("--brief", choices=["daily", "weekly"], help="Yalnızca bu özeti dene")
    lm.add_argument("--force", action="store_true", help="Dönemin özeti varsa yeniden yaz")
    lm.add_argument("--no-brief", action="store_true", help="Özet yazma, yalnızca çevir")
    lm.add_argument("--no-translate", action="store_true", help="Çevirme, yalnızca özet yaz")
    lm.set_defaults(func=cmd_llm)

    br = sub.add_parser("brief", help="Özetler: listele, elle ekle, sil, abonelere gönder")
    brs = br.add_subparsers(dest="action", required=True)
    b1 = brs.add_parser("list")
    b1.add_argument("--limit", type=int, default=30)
    b2 = brs.add_parser("add", help="Markdown dosyasından özet ekle")
    b2.add_argument("file")
    b2.add_argument("--kind", choices=["daily", "weekly"], default="weekly")
    b2.add_argument("--title")
    b2.add_argument("--date", help="YYYY-AA-GG (varsayılan: bugün)")
    b3 = brs.add_parser("delete")
    b3.add_argument("id", type=int)
    b4 = brs.add_parser("send", help="Özeti abonelere e-postayla gönder")
    b4.add_argument("id", type=int)
    b4.add_argument("--to", nargs="+", help="Aboneler yerine yalnızca bu adreslere (deneme)")
    br.set_defaults(func=cmd_brief)

    sb = sub.add_parser("sub", help="Aboneler: listele, ekle, çıkar")
    sbs = sb.add_subparsers(dest="action", required=True)
    sbs.add_parser("list")
    for name in ("add", "remove"):
        sbs.add_parser(name).add_argument("emails", nargs="+")
    sb.set_defaults(func=cmd_sub)

    ad = sub.add_parser("admin", help="Yönetim panelinin şifreli komutunu uygula (bulut iş akışı için)")
    ad.add_argument("--payload", help="Varsayılan: QIN_ADMIN_COMMAND ortam değişkeni")
    ad.set_defaults(func=cmd_admin)

    ex = sub.add_parser("export", help="Site verisini (site\\data) yeniden üret")
    ex.set_defaults(func=cmd_export)

    sv = sub.add_parser("serve", help="Siteyi bu bilgisayarda aç")
    sv.add_argument("--port", type=int)
    sv.add_argument("--no-browser", action="store_true")
    sv.set_defaults(func=cmd_serve)

    va = sub.add_parser("vault", help="Arşiv dosyasını şifrele / aç (QIN_SITE_PASSWORD ile)")
    va.add_argument("action", choices=["seal", "open"])
    va.add_argument("src")
    va.add_argument("dst")

    rp = sub.add_parser("reparse", help="Bültenleri kayıtlı ham veriden yeniden ayrıştır")
    rp.set_defaults(func=cmd_reparse)

    args = p.parse_args(argv)
    if args.cmd == "vault":            # arşiv henüz açılmadan çalışır
        return cmd_vault(args)
    cfg = load_config()
    _setup_io(cfg)
    db = DB(cfg["db_path"])
    try:
        migrate(db, cfg)
        return args.func(db, cfg, args) or 0
    except Exception:
        logging.getLogger("qin").exception("Komut başarısız: %s", args.cmd)
        raise
    finally:
        db.close()
