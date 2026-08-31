"""Telegram bildirimi. Token yoksa sessizce log'a düşer (bot yine çalışır)."""
from __future__ import annotations

import os
import urllib.parse
import urllib.request
from pathlib import Path


def _load_env() -> None:
    """.env dosyasını oku (git'e girmez). Ortam değişkeni varsa o kazanır."""
    f = Path(__file__).resolve().parent.parent / ".env"
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()
TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
CHAT = os.environ.get("TG_CHAT_ID", "").strip()


def enabled() -> bool:
    return bool(TOKEN and CHAT)


def send(text: str) -> bool:
    """Markdown'sız düz metin — biçim hatası mesajı düşürmesin."""
    if not enabled():
        print(f"[TG kapalı] {text}")
        return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT, "text": text, "disable_web_page_preview": "true"
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            govde = r.read()
            if r.status != 200:
                return False
            # HEDEFI KAYDA GEC: mesajin NEREYE gittigi gorunmeliydi.
            # 2026-08-31'de grup kurulumunda "gitti mi, nereye gitti"
            # sorusu loglardan cevaplanamiyordu -- send yalniz True/False
            # donuyordu. Sessizce yanlis sohbete gitmek, bu oturumda
            # defalarca yakalanan hata sinifinin ta kendisi.
            try:
                import json as _j
                c = ((_j.loads(govde).get("result") or {}).get("chat") or {})
                print(f"[TG] gonderildi -> {c.get('type')} "
                      f"'{c.get('title') or c.get('first_name') or ''}' "
                      f"(id {c.get('id')})")
            except Exception:
                pass
            return True
    except Exception as e:
        print(f"[TG hata] {type(e).__name__}: {e}")
        return False


V10_FREEZE = "2026-08-20"      # mekanizma v1.0 dondurulma tarihi
GATE_DAYS = 60


def send_many(lines: list[str]) -> bool:
    """Coklu satiri tek mesajda gonder (Telegram 4096 karakter siniri)."""
    text = "\n".join(lines)
    return send(text[:4000])
