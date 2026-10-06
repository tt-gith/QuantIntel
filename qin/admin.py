"""Yönetim: ikinci parola, yönetim paketi ve panelden gelen komutların uygulanması.

Site durağandır (sunucusu yoktur); yönetim paneli bu yüzden şöyle çalışır:

1. Dışa aktarma sırasında `admin.bin` üretilir. İçinde site anahtarı, abone listesi ve panelin
   GitHub'da iş akışını başlatmasına yarayan anahtar (ADMIN_TOKEN) bulunur; yönetim parolasından
   türetilen anahtarla şifrelidir. Yönetim parolasını bilen tarayıcı bu paketi açar.
2. Panel, yapılacak işi (özet ekle, abonelere gönder...) aynı anahtarla şifreleyip iş akışına
   girdi olarak yollar. İş akışı komutu burada çözer ve arşive uygular.

Komut yalnızca yönetim anahtarıyla şifrelenmişse çözülür; yani anahtarı bilmeyen biri iş akışını
başlatabilse bile geçerli bir komut üretemez. Her komut bir kez uygulanır ve bir gün sonra geçersizdir.
İşlemler yinelenmeye karşı güvenlidir: aynı taslak iki kez eklenmez, gönderilmiş özet açıkça istenmedikçe
yeniden gönderilmez (panel bir işlemi "başarısız" sanıp yeniden denese de abonelere çift e-posta gitmez).
"""
from __future__ import annotations

import base64
import binascii
import json
import os
from datetime import datetime, timedelta, timezone

from . import mailer, vault
from .brief import KINDS, manual_period
from .common import iso, now_utc
from .private import Private, admin_key, admin_password  # noqa: F401  (dışarıya buradan da sunulur)
from .storage import DB

MIN_LENGTH = 16                 # admin.bin herkese açık adreste durur ve içinde GitHub anahtarı vardır
MAX_AGE = timedelta(hours=24)
MAX_BODY = 60_000
WORKFLOW = "gunluk.yml"


def check(password: str, site_password: str) -> None:
    if len(password) < MIN_LENGTH:
        raise ValueError(f"Yönetim parolası en az {MIN_LENGTH} karakter olmalı (beş altı kelimelik bir cümle kullan).")
    if password == vault.normalize(site_password):
        raise ValueError("Yönetim parolası site parolasıyla aynı olamaz.")


def bundle(db: DB, cfg: dict, site_key: bytes, password: str) -> bytes:
    """admin.bin içeriği (şifreli). Yalnızca yönetim parolasıyla açılır."""
    private = Private(db, password)
    if private.plain:                       # yerelde düz yazılmış kayıt: artık şifrelenebilir
        private.save()
    providers = [p["name"] for p in cfg.get("llm", {}).get("providers", [])
                 if p.get("enabled", True) and os.environ.get(p.get("key_env", ""))]
    data = {
        "v": 1,
        "key": vault.b64(site_key),
        "token": os.environ.get("QIN_ADMIN_TOKEN", "").strip(),
        "repo": os.environ.get("GITHUB_REPOSITORY", ""),
        "workflow": WORKFLOW,
        "ref": os.environ.get("GITHUB_REF_NAME", "") or "main",
        "subscribers": private.subscribers,
        "locked": private.locked,           # abone kaydı eski yönetim parolasıyla şifreli: okunamadı
        "mail": mailer.configured(),
        "llm": {"providers": providers, "last": json.loads(db.get_meta("llm_last", "null"))},
        "last": private.last,
    }
    return vault.seal(admin_key(db, password), json.dumps(data, ensure_ascii=False).encode("utf-8"))


# ------------------------------------------------------------------ komutlar
class CommandError(ValueError):
    """Uygulanamayan komut. `private`, yalnızca panelde gösterilecek ayrıntıdır (ör. e-posta adresleri);
    iş akışı günlükleri herkese açık olduğu için oraya yalnızca ana ileti yazılır."""

    def __init__(self, message: str, private: str | None = None, cmd_id: str | None = None, replay: bool = False):
        super().__init__(message)
        self.private = private or message
        self.cmd_id = cmd_id                # komut çözüldüyse kimliği: panel sonucu bununla eşler
        self.replay = replay


def decode(db: DB, payload: str, password: str) -> dict:
    """Panelin ürettiği metni (base64 + şifreli JSON) çözer ve doğrular."""
    from cryptography.exceptions import InvalidTag

    try:
        blob = base64.b64decode("".join(payload.split()), validate=True)
        cmd = json.loads(vault.unseal(admin_key(db, password), blob))
    except (binascii.Error, InvalidTag, ValueError) as ex:
        raise CommandError("Komut çözülemedi: yönetim parolasıyla üretilmemiş ya da bozulmuş.") from ex
    if not isinstance(cmd, dict) or not isinstance(cmd.get("ops"), list) or not cmd.get("id") or not cmd.get("ts"):
        raise CommandError("Komut beklenen biçimde değil.")
    cmd_id = str(cmd["id"])[:64]
    try:
        made = datetime.fromisoformat(str(cmd["ts"]).replace("Z", "+00:00"))
        if made.tzinfo is None:
            made = made.replace(tzinfo=timezone.utc)
    except ValueError as ex:
        raise CommandError("Komutun zamanı okunamadı.", cmd_id=cmd_id) from ex
    age = now_utc() - made
    if age > MAX_AGE:
        raise CommandError("Komutun süresi dolmuş; panelden yeniden gönder.", cmd_id=cmd_id)
    if age < -timedelta(minutes=10):
        raise CommandError("Komutun zamanı ileride görünüyor; cihazının saatini kontrol edip yeniden gönder.",
                           cmd_id=cmd_id)
    if cmd_id in json.loads(db.get_meta("admin_seen", "[]")):
        raise CommandError("Bu komut daha önce uygulanmış.", cmd_id=cmd_id, replay=True)
    cmd["id"] = cmd_id
    return cmd


def _text(op: dict, key: str, limit: int) -> str:
    value = str(op.get(key) or "").replace("\x00", "").strip()
    if not value:
        raise CommandError(f"'{key}' boş olamaz.")
    if len(value) > limit:
        raise CommandError(f"'{key}' çok uzun (en fazla {limit} karakter).")
    return value


def _brief_id(db: DB, op: dict, last_saved: int | None) -> int:
    ref = op.get("id")
    brief_id = last_saved if ref == "last" else ref
    if not isinstance(brief_id, int) or isinstance(brief_id, bool) or not db.brief(brief_id):
        raise CommandError(f"Özet bulunamadı: {ref}")
    return brief_id


def _run(db: DB, cfg: dict, op: dict, state: dict, smtp_factory=None) -> tuple[str, str]:
    """Tek işlemi uygular. (herkese açık günlüğe yazılabilecek satır, panelde gösterilecek satır) döndürür;
    ilkinde e-posta adresi ya da özet metni bulunmaz (iş akışı günlükleri herkese açıktır)."""
    name = op.get("op")
    private: Private = state["private"]

    if name == "brief.save":
        kind = op.get("kind")
        if kind not in KINDS:
            raise CommandError("Özet türü 'daily' ya da 'weekly' olmalı.")
        try:
            period = manual_period(kind, str(op.get("date") or ""))
        except ValueError as ex:
            raise CommandError("Özet tarihi YYYY-AA-GG biçiminde olmalı.") from ex
        title, body = " ".join(_text(op, "title", 200).split()), _text(op, "body", MAX_BODY)   # başlık tek satır
        draft = str(op.get("draft") or "")[:64] or None
        target = op.get("id")
        if target is None and draft and (same := db.find_draft(draft)):
            target = same["id"]                             # aynı taslak yeniden geldi: ikinci kez eklenmez
        if target is None:
            state["last"] = db.save_brief(kind, period, "manual", title, body, draft_id=draft)
            line = f"Özet #{state['last']} eklendi"
        else:
            state["last"] = _brief_id(db, {"id": target}, None)
            old = db.brief(state["last"])
            if old["origin"] == "llm":                      # otomatik özetin dönemi sabittir
                kind, period = old["kind"], old["period"]
            db.save_brief(kind, period, old["origin"], title, body, brief_id=state["last"])
            line = f"Özet #{state['last']} güncellendi"
        return line, line

    if name == "brief.delete":
        brief_id = _brief_id(db, op, state.get("last"))
        db.delete_brief(brief_id)
        return (f"Özet #{brief_id} silindi",) * 2

    if name == "brief.send":
        brief_id = _brief_id(db, op, state.get("last"))
        brief = db.brief(brief_id)
        to = op.get("to", "all")
        everyone = to == "all"
        recipients, bad = (list(private.subscribers), []) if everyone else mailer.clean_emails(to if isinstance(to, list) else [])
        if bad:
            raise CommandError("Geçersiz e-posta adresi.", f"Geçersiz adres: {', '.join(bad)[:200]}")
        if not recipients:
            raise CommandError("Gönderilecek kimse yok: önce abone ekle.")
        if everyone and brief["sent_at"] and not op.get("again"):
            raise CommandError(f"Özet #{brief_id} abonelere zaten gönderilmiş ({brief['sent_at'][:10]}); "
                               "yeniden göndermek için panelde «Yeniden yayınla»yı kullan.")
        if not mailer.configured() and not smtp_factory:
            raise CommandError("E-posta ayarlı değil: SMTP_USER ve SMTP_PASSWORD gizli değerleri eksik.")
        sent, failed = mailer.send_brief(brief, recipients, cfg, smtp_factory)
        if everyone and sent:
            db.mark_brief_sent(brief_id, len(sent))
        who = "aboneye" if everyone else "deneme adresine"
        line = f"Özet #{brief_id}: {len(sent)} {who} gönderildi" + (f", {len(failed)} başarısız" if failed else "")
        if failed:
            state["failed"] = True
        return line, line + ("".join(f"\n  {f}" for f in failed) if failed else "")

    if name in ("sub.add", "sub.remove"):
        emails, bad = mailer.clean_emails(op.get("emails"))
        if bad:
            raise CommandError("Geçersiz e-posta adresi.", f"Geçersiz adres: {', '.join(bad)[:200]}")
        change = private.add if name == "sub.add" else private.remove
        n = sum(1 for e in emails if change(e))
        private.save()
        line = f"{n} abone {'eklendi' if name == 'sub.add' else 'çıkarıldı'} (toplam {len(private.subscribers)})"
        return line, line

    raise CommandError(f"Bilinmeyen işlem: {name}")


def apply(db: DB, cfg: dict, payload: str, password: str | None = None, smtp_factory=None) -> dict:
    """Paneldeki komutu uygular. Sonuç şifreli kayda yazılır ve bir sonraki admin.bin ile panele döner.
    Dönen sözlükte 'public' satırları günlüğe yazılabilir; 'log' yalnızca panel içindir."""
    password = password or admin_password()
    result = {"id": None, "at": iso(now_utc()), "ok": False, "log": [], "public": []}
    private = None
    record = True
    try:
        if not password:
            raise CommandError("Yönetim parolası tanımlı değil (ADMIN_SIFRESI).")
        cmd = decode(db, payload, password)
        result["id"] = cmd["id"]
        seen = json.loads(db.get_meta("admin_seen", "[]"))
        db.set_meta("admin_seen", json.dumps((seen + [result["id"]])[-200:]))   # yarıda kalsa da yinelenmesin
        private = Private(db, password)
        state: dict = {"private": private}
        for op in cmd["ops"]:
            if not isinstance(op, dict):
                raise CommandError("Komut beklenen biçimde değil.")
            public, detail = _run(db, cfg, op, state, smtp_factory)
            result["public"].append(public)
            result["log"].append(detail)
        result["ok"] = not state.get("failed")
    except CommandError as ex:                          # kalan işlemler uygulanmaz
        result["id"] = result["id"] or ex.cmd_id
        record = not ex.replay                          # yinelenen komut, ilk uygulamanın sonucunu ezmesin
        result["public"].append(f"HATA: {ex}")
        result["log"].append(f"HATA: {ex.private}")
    except Exception as ex:                             # e-posta sunucusu, veritabanı...: sonuç yine panele dönsün
        result["public"].append(f"HATA: {type(ex).__name__} (ayrıntı yönetim panelinde)")
        result["log"].append(f"HATA: {type(ex).__name__}: {str(ex)[:300]}")
    if record and password and db.get_meta("site_salt"):
        private = private or Private(db, password)
        private.last = {k: result[k] for k in ("id", "at", "ok", "log")}
        private.save()
    return result
