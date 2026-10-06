"""LLM bağlantısı: ücretsiz, OpenAI uyumlu sohbet uç noktalarına tek bir arayüz.

Sağlayıcılar config.json > llm.providers içinde sıralıdır. Anahtarı (ortam değişkeni) tanımlı olan
sağlayıcılar sırayla denenir; bir model hata verir ya da sınırı dolarsa sıradaki modele, o da olmazsa
sıradaki sağlayıcıya geçilir. Yeni sağlayıcı eklemek için OpenAI uyumlu bir adres, model adı ve
anahtarın ortam değişkeni yeterlidir.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

import requests

log = logging.getLogger("qin")


class LLMUnavailable(RuntimeError):
    """Kullanılabilir sağlayıcı yok ya da hepsi başarısız. İleti kısa tutulur (herkese açık günlüğe yazılabilir);
    sağlayıcının hata gövdesi gibi ayrıntılar LLM.errors içindedir."""


class LLM:
    def __init__(self, cfg: dict, session=None, sleep=time.sleep, clock=time.monotonic):
        self.cfg = cfg.get("llm", {})
        self.session = session or requests.Session()
        self.sleep = sleep
        self.clock = clock
        self.providers = [p for p in self.cfg.get("providers", [])
                          if p.get("enabled", True) and os.environ.get(p.get("key_env", ""))]
        self._last_call: dict[str, float] = {}
        self._dead: set[tuple[str, str]] = set()   # bu çalışmada sınırı dolan / erişilemeyen (sağlayıcı, model)
        self.calls = 0
        # Zaman bütçesi: ücretsiz katmanlar yavaşlarsa iş akışı adımı yarıda kesilmesin, kalan iş yarına kalsın
        self.deadline = clock() + 60 * self.cfg.get("max_minutes", 18)
        self.last_model: str | None = None         # son başarılı yanıtın geldiği "sağlayıcı/model"
        self.errors: list[str] = []

    # ------------------------------------------------------------ durum
    def _models(self, p: dict, task: str) -> list[str]:
        models = p.get("models", [])
        if isinstance(models, dict):
            models = models.get(task) or models.get("default") or next(iter(models.values()), [])
        return [m for m in models if (p["name"], m) not in self._dead]

    def _usable(self, task: str = "default") -> bool:
        return any(self._models(p, task) for p in self.providers)

    @property
    def available(self) -> bool:
        return bool(self.cfg.get("enabled", True)) and self._usable()

    # ------------------------------------------------------------ istek
    def _post(self, p: dict, model: str, system: str, user: str, max_tokens: int, extra: dict) -> str:
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": min(max_tokens, p.get("max_output_tokens", max_tokens)),
            **extra,
        }
        gap = p.get("min_interval_seconds", 2) - (self.clock() - self._last_call.get(p["name"], -1e9))
        if gap > 0:
            self.sleep(gap)                       # ücretsiz katmanların dakika sınırına takılmamak için
        self._last_call[p["name"]] = self.clock()
        r = self.session.post(
            p["base_url"].rstrip("/") + "/chat/completions", json=body, timeout=p.get("timeout", 90),
            headers={"Authorization": f"Bearer {os.environ[p['key_env']]}", "Content-Type": "application/json"})
        if r.status_code >= 400:
            raise _HTTPError(r.status_code, r.text[:300])
        content = r.json()["choices"][0]["message"].get("content")
        if isinstance(content, list):             # bazı sağlayıcılar parçalı içerik döndürür
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        content = (content or "").strip()
        if not content:
            raise RuntimeError("boş yanıt")
        return content

    def _try(self, p: dict, model: str, system: str, user: str, max_tokens: int) -> str:
        # İsteğe bağlı parametreler; sağlayıcı birini tanımazsa (HTTP 400) istek yalın haliyle yinelenir
        extra = {"temperature": self.cfg.get("temperature", 0.3), **p.get("extra", {})}
        waited = False
        while True:
            try:
                return self._post(p, model, system, user, max_tokens, extra)
            except _HTTPError as ex:
                if ex.status == 400 and extra:
                    extra = {}
                    continue
                if ex.status == 429 and not waited:   # dakika sınırı: bir kez bekle
                    waited = True
                    self.sleep(p.get("retry_after_seconds", 65))
                    continue
                raise

    def chat(self, system: str, user: str, max_tokens: int = 2000, task: str = "default") -> str:
        """Yanıt metnini döndürür. Hiçbir sağlayıcı yanıt vermezse LLMUnavailable."""
        if self.clock() > self.deadline:
            raise LLMUnavailable("bu çalışmanın zaman bütçesi doldu; kalan iş sonraki çalışmaya kaldı")
        short = []
        for p in self.providers:
            for model in self._models(p, task):
                try:
                    out = self._try(p, model, system, user, max_tokens)
                    self.calls += 1
                    self.last_model = f"{p['name']}/{model}"
                    return out
                except Exception as ex:           # ağ, sınır, biçim: sıradaki modele geç
                    name = f"{p['name']}/{model}"
                    self.errors.append(f"{name}: {str(ex)[:200]}")
                    short.append(f"{name}: " + (f"HTTP {ex.status}" if isinstance(ex, _HTTPError) else type(ex).__name__))
                    log.warning("LLM başarısız: %s: %s", name, str(ex)[:200])
                    self._dead.add((p["name"], model))
        raise LLMUnavailable("; ".join(short) or "kullanılabilir LLM yok (API anahtarı tanımlı mı?)")


class _HTTPError(RuntimeError):
    def __init__(self, status: int, text: str):
        super().__init__(f"HTTP {status}: {text}")
        self.status = status


_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def strip_fence(text: str) -> str:
    """Yanıt tümüyle bir kod çitine sarılmışsa çiti atar."""
    text = text.strip()
    return _FENCE.sub("", text).strip() if text.startswith("```") else text


def parse_json(text: str):
    """Model yanıtından JSON nesnesini ayıklar (kod çitine ve çevresindeki açıklamaya dayanıklı)."""
    text = strip_fence(text)
    try:
        return json.loads(text)
    except ValueError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("yanıtta JSON bulunamadı")
