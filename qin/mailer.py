"""Özetlerin abonelere e-postayla gönderilmesi (SMTP).

Gönderim hiçbir zaman kendiliğinden yapılmaz; yalnızca yönetim panelindeki "özeti yayınla" komutuyla
ya da `qin brief send` ile çalışır. Ayarlar ortam değişkenlerinden okunur (bulutta: GitHub gizli değerleri):

  SMTP_USER, SMTP_PASSWORD   gönderen hesabın adresi ve (uygulama) parolası — zorunlu
  SMTP_HOST, SMTP_PORT       varsayılan smtp.gmail.com / 587 (465 verilirse doğrudan TLS)
  MAIL_FROM_NAME             gönderen adı (varsayılan: Quant Intelligence)
"""
from __future__ import annotations

import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from . import md
from .brief import period_label

EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+$")

# E-posta istemcileri <style> bloklarını güvenilir işlemez; stiller satır içine yazılır.
STYLES = {
    "h2": "font:600 20px/1.3 Georgia,serif;color:#101730;margin:28px 0 10px",
    "h3": "font:600 17px/1.35 Georgia,serif;color:#101730;margin:26px 0 8px;padding-top:14px;border-top:1px solid #e3e6ee",
    "h4": "font:600 15px/1.4 Arial,sans-serif;color:#101730;margin:20px 0 6px",
    "p": "margin:0 0 14px",
    "ul": "margin:0 0 14px;padding-left:22px",
    "ol": "margin:0 0 14px;padding-left:22px",
    "li": "margin:0 0 7px",
    "a": "color:#1d5fbf",
    "cite": "color:#1d5fbf;font-size:12px;text-decoration:none;vertical-align:2px;padding:0 1px",
    "code": "font-family:Consolas,monospace;font-size:13px;background:#f1f3f8;padding:1px 4px;border-radius:3px",
    "pre": "font-family:Consolas,monospace;font-size:13px;background:#f1f3f8;padding:12px;border-radius:6px;white-space:pre-wrap",
    "blockquote": "margin:0 0 14px;padding:2px 0 2px 14px;border-left:3px solid #c9cfdd;color:#4a5370",
    "table": "border-collapse:collapse;margin:0 0 14px;font-size:14px",
    "th": "border:1px solid #d5d9e4;padding:6px 10px;background:#f1f3f8;text-align:left",
    "td": "border:1px solid #d5d9e4;padding:6px 10px",
    "hr": "border:0;border-top:1px solid #e3e6ee;margin:22px 0",
}


def valid(email: str) -> bool:
    return bool(EMAIL.match(email)) and len(email) <= 254


def clean_emails(values) -> tuple[list[str], list[str]]:
    """(geçerli adresler, geçersiz girdiler). Adresler küçük harfe çevrilir ve tekilleştirilir."""
    good, bad = [], []
    for v in values or []:
        e = str(v).strip().lower()
        if not e:
            continue
        if not valid(e):
            bad.append(e)
        elif e not in good:
            good.append(e)
    return good, bad


def settings() -> dict | None:
    user, password = os.environ.get("SMTP_USER", "").strip(), os.environ.get("SMTP_PASSWORD", "")
    if not user or not password:
        return None
    host = os.environ.get("SMTP_HOST", "").strip() or "smtp.gmail.com"
    if host.endswith("gmail.com"):
        password = password.replace(" ", "")          # Google uygulama parolasını boşluklu gösterir
    port = os.environ.get("SMTP_PORT", "").strip()
    return {"host": host, "port": int(port) if port.isdigit() else 587, "user": user,
            "password": password, "name": os.environ.get("MAIL_FROM_NAME", "").strip() or "Quant Intelligence"}


def configured() -> bool:
    return settings() is not None


def site_url(cfg: dict) -> str:
    """Sitenin adresi: config.json > site_url, yoksa GitHub Pages adresi (bulutta)."""
    if cfg.get("site_url"):
        return cfg["site_url"]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in repo:
        return ""
    owner, name = repo.split("/", 1)
    host = f"{owner.lower()}.github.io"
    return f"https://{host}/" if name.lower() == host else f"https://{host}/{name}/"


def compose(brief, to: str, sender: dict, cfg: dict) -> EmailMessage:
    kind = "Günlük özet" if brief["kind"] == "daily" else "Haftalık özet"
    kicker = "GÜNLÜK ÖZET" if brief["kind"] == "daily" else "HAFTALIK ÖZET"   # CSS büyük harfi Türkçe "i"yi bozar
    label = period_label(brief["kind"], brief["period"])
    url = site_url(cfg)
    footer_text = "Bu e-postayı Quant Intelligence abonesi olduğun için aldın. Ayrılmak için bu e-postayı yanıtlaman yeterli."
    link_html = (f'<p style="margin:0 0 6px"><a href="{url}#tab=briefs&amp;brief={brief["id"]}" '
                 f'style="color:#1d5fbf">Sitede oku</a></p>') if url else ""

    msg = EmailMessage()
    msg["Subject"] = f"{' '.join(brief['title'].split())} · {kind}"     # başlıkta satır sonu olamaz
    msg["From"] = formataddr((sender["name"], sender["user"]))
    msg["To"] = to
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=sender["user"].split("@")[-1])
    msg["List-Unsubscribe"] = f"<mailto:{sender['user']}?subject=abonelikten%20ayril>"
    msg.set_content(f"{brief['title']}\n{kind} · {label}\n\n{md.to_text(brief['body'])}\n\n--\n"
                    + (f"Sitede oku: {url}#tab=briefs&brief={brief['id']}\n" if url else "") + footer_text)
    msg.add_alternative(f"""<!doctype html>
<html lang="tr"><body style="margin:0;padding:0;background:#eef0f5">
<div style="max-width:640px;margin:0 auto;padding:28px 22px 34px;background:#ffffff;font:16px/1.6 Georgia,'Times New Roman',serif;color:#1c2338">
<p style="margin:0 0 4px;font:600 11px/1.4 Arial,sans-serif;letter-spacing:.14em;color:#8a6a2f">QUANT INTELLIGENCE · {kicker}</p>
<p style="margin:0 0 14px;font:13px/1.4 Arial,sans-serif;color:#6b7390">{label}</p>
<h1 style="font:600 26px/1.25 Georgia,serif;color:#101730;margin:0 0 20px">{md.inline(brief['title'])}</h1>
{md.render(brief['body'], STYLES)}
<div style="margin-top:30px;padding-top:16px;border-top:1px solid #e3e6ee;font:13px/1.5 Arial,sans-serif;color:#6b7390">
{link_html}<p style="margin:0">{footer_text}</p>
</div></div></body></html>""", subtype="html")
    return msg


def send_brief(brief, recipients: list[str], cfg: dict, smtp_factory=None) -> tuple[list[str], list[str]]:
    """Özeti her aboneye ayrı e-posta olarak gönderir (adresler birbirine görünmez).
    (gönderilenler, 'adres: hata' biçiminde başarısızlar) döndürür."""
    sender = settings()
    if not sender:
        raise RuntimeError("E-posta ayarlı değil: SMTP_USER ve SMTP_PASSWORD tanımlanmalı (bkz. YAYIN.md).")
    if smtp_factory:
        server = smtp_factory(sender)
    elif sender["port"] == 465:
        server = smtplib.SMTP_SSL(sender["host"], 465, timeout=30, context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(sender["host"], sender["port"], timeout=30)
        server.starttls(context=ssl.create_default_context())
    sent, failed = [], []
    try:
        server.login(sender["user"], sender["password"])
        for n, to in enumerate(recipients):
            try:
                server.send_message(compose(brief, to, sender, cfg))
                sent.append(to)
            except smtplib.SMTPResponseException as ex:      # sunucu bu alıcıyı reddetti: sıradakine geç
                failed.append(f"{to}: {ex.smtp_code} {str(ex.smtp_error)[:100]}")
            except smtplib.SMTPRecipientsRefused as ex:
                failed.append(f"{to}: {str(ex)[:120]}")
            except OSError as ex:                            # bağlantı koptu: kalanlar gönderilemedi sayılır,
                failed += [f"{r}: bağlantı koptu ({type(ex).__name__})" for r in recipients[n:]]
                break                                        # gönderilenlerin kaydı ise korunur
    finally:
        try:
            server.quit()
        except OSError:
            pass
    return sent, failed
