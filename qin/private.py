"""Özel veriler: abone adresleri ve son yönetim işleminin ayrıntıları.

Arşiv site parolasıyla şifrelenir ve o parolayı siteyi okuyan herkes bilir. Abone adresleri ise yalnızca
yöneticiyi ilgilendirir; bu yüzden arşivin içinde ayrıca, YÖNETİM parolasından türetilen anahtarla
şifrelenmiş tek bir kayıtta (meta > private) tutulur. Site parolasını bilen biri arşivi açsa da bu kaydı okuyamaz.

Yönetim parolası tanımlı değilse (yalnızca kendi bilgisayarında kullanım) kayıt düz JSON olarak durur.
Yönetim parolası değişirse eski kayıt okunamaz; `locked` işaretlenir ve ilk kaydetmede yenisi yazılır.
"""
from __future__ import annotations

import base64
import binascii
import functools
import json
import os

from . import vault
from .storage import DB

KEY = "private"


def admin_password() -> str | None:
    pw = vault.normalize(os.environ.get("QIN_ADMIN_PASSWORD", ""))
    return pw or None


@functools.lru_cache(maxsize=8)
def _derive(password: str, salt_b64: str) -> bytes:
    return vault.derive_key(password, base64.b64decode(salt_b64))


def admin_key(db: DB, password: str) -> bytes:
    """Yönetim anahtarı, site anahtarıyla aynı tuzdan türetilir (tarayıcı tek bir lock.json okur)."""
    salt = db.get_meta("site_salt")
    if not salt:
        raise ValueError("Site henüz şifreli olarak dışa aktarılmamış (site_salt yok).")
    return _derive(vault.normalize(password), salt)


class Private:
    def __init__(self, db: DB, password: str | None = None):
        self.db = db
        self.password = password or admin_password()
        self.subscribers: list[str] = []
        self.last: dict | None = None        # son yönetim işleminin sonucu (panelde gösterilir)
        self.locked = False                  # kayıt başka bir yönetim parolasıyla şifreli: okunamadı
        self.plain = False                   # kayıt şifresiz duruyor
        raw = db.get_meta(KEY)
        if not raw:
            return
        if raw.startswith("{"):
            data, self.plain = json.loads(raw), True
        else:
            data = self._open(raw)
            if data is None:
                self.locked = True
                return
        self.subscribers = list(data.get("subscribers") or [])
        self.last = data.get("last")

    def _can_seal(self) -> bool:
        return bool(self.password and self.db.get_meta("site_salt"))

    def _open(self, raw: str) -> dict | None:
        from cryptography.exceptions import InvalidTag
        if not self._can_seal():
            return None
        try:
            return json.loads(vault.unseal(admin_key(self.db, self.password), base64.b64decode(raw)))
        except (InvalidTag, ValueError, binascii.Error):
            return None

    def save(self) -> None:
        text = json.dumps({"subscribers": self.subscribers, "last": self.last}, ensure_ascii=False)
        self.plain = not self._can_seal()
        if self.locked:                      # okunamayan eski kayıt silinmez; eski parolayla kurtarılabilir
            self.db.set_meta(KEY + "_onceki", self.db.get_meta(KEY) or "")
        if not self.plain:
            text = vault.b64(vault.seal(admin_key(self.db, self.password), text.encode("utf-8")))
        self.db.set_meta(KEY, text)
        self.locked = False

    def add(self, email: str) -> bool:
        if email in self.subscribers:
            return False
        self.subscribers.append(email)
        return True

    def remove(self, email: str) -> bool:
        if email not in self.subscribers:
            return False
        self.subscribers.remove(email)
        return True
