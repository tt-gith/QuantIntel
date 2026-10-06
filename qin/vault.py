"""Şifreleme: site verisini ve arşivi bir parolayla kilitler.

Site herkese açık bir adreste yayınlandığı için içerik dosyaları şifreli tutulur;
tarayıcı parolayı sorar ve veriyi kendi içinde çözer (site/js/data.js aynı yöntemi kullanır).

Yöntem: PBKDF2-HMAC-SHA256 ile paroladan anahtar türetilir, veri zlib ile sıkıştırılıp
AES-256-GCM ile şifrelenir. Dosya düzeni: nonce (12 bayt) + şifreli veri.
"""
from __future__ import annotations

import base64
import hashlib
import os
import struct
import unicodedata
import zlib
from pathlib import Path

ITERATIONS = 600_000
MIN_LENGTH = 12
_MAGIC = b"QINV1"


def site_password() -> str | None:
    """Ortam değişkeninden site parolası (yoksa None: veri şifrelenmez)."""
    pw = normalize(os.environ.get("QIN_SITE_PASSWORD", ""))
    return pw or None


def normalize(password: str) -> str:
    # Türkçe karakterler farklı klavyelerde farklı kodlanabilir; iki tarafta da aynı biçime getir
    return unicodedata.normalize("NFC", password.strip())


def check_strength(password: str) -> None:
    if len(password) < MIN_LENGTH:
        raise ValueError(
            f"Site parolası en az {MIN_LENGTH} karakter olmalı. Şifreli dosyalar herkese açık adreste "
            "durduğu için kısa parolalar deneme yanılmayla bulunabilir; dört beş kelimelik bir cümle kullan.")


def derive_key(password: str, salt: bytes, iterations: int = ITERATIONS) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", normalize(password).encode("utf-8"), salt, iterations, 32)


def _aes(key: bytes):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM   # yalnızca şifreleme gerektiğinde yüklenir
    return AESGCM(key)


def seal(key: bytes, data: bytes) -> bytes:
    nonce = os.urandom(12)
    return nonce + _aes(key).encrypt(nonce, zlib.compress(data, 6), None)


def unseal(key: bytes, blob: bytes) -> bytes:
    return zlib.decompress(_aes(key).decrypt(blob[:12], blob[12:], None))


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


# ---------------------------------------------------------------- arşiv dosyası
def seal_file(src: Path, dst: Path, password: str) -> None:
    """Tek dosyayı (arşiv) kendi tuzuyla şifreler: başlık + tuz + tur sayısı + şifreli veri."""
    check_strength(normalize(password))
    salt = os.urandom(16)
    key = derive_key(password, salt)
    dst.write_bytes(_MAGIC + salt + struct.pack(">I", ITERATIONS) + seal(key, src.read_bytes()))


def open_file(src: Path, dst: Path, passwords: list[str]) -> None:
    """Şifreli arşivi açar. Birden fazla parola verilirse sırayla dener (parola değişimi için)."""
    from cryptography.exceptions import InvalidTag

    blob = src.read_bytes()
    if blob[:5] != _MAGIC:
        raise ValueError(f"{src.name} beklenen biçimde değil.")
    salt, (iterations,) = blob[5:21], struct.unpack(">I", blob[21:25])
    for pw in passwords:
        if not pw:
            continue
        try:
            dst.write_bytes(unseal(derive_key(pw, salt, iterations), blob[25:]))
            return
        except InvalidTag:
            continue
    raise ValueError("Arşiv bu parolayla açılamadı. Parolayı değiştirdiysen eski parolayı "
                     "SITE_SIFRESI_ESKI adıyla ekle (bkz. YAYIN.md).")
