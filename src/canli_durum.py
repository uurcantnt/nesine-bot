"""Canli mac durumu (skor + tahmini dakika) — ESPN'den.

NEDEN GEREKLI: Nesine'nin canli bulteninde skor ve dakika alani YOK
(dogrulandi: 8 canli macin tum alanlari dokuldu; canli-skor sayfasi
WebSocket ile besleniyor, erisilebilir API yok).

DAKIKA TAHMINI: ESPN de dakika vermiyor, sadece `status: "live"` ve skor.
Dakika baslangic saatinden tahmin edilir; devre arasi (15 dk) ve uzatmalar
yuzunden HATA PAYI VAR. Bu yuzden mesajda "yaklasik" diye yazilir ve
tahmini dakika 85'i gecince model KULLANILMAZ (hata payi sonucu belirler).

TUZAK: ESPN'in canli verisi Nesine'den geride kalabilir. Geride kalirsa
model yanlis "deger" uretir. Bu yuzden skorun ESPN'e gore oldugu ve
kullanicinin Nesine ekraniyla karsilastirmasi gerektigi mesajda yazilir.
"""
from __future__ import annotations

from datetime import datetime, timezone

DEVRE_ARASI = 15
GUVENLI_DAKIKA = 85      # bunun ustunde model kullanilmaz


def tahmini_dakika(baslangic_iso: str, simdi: datetime | None = None) -> int | None:
    """Baslangic saatinden gecen sureye gore dakika tahmini."""
    if not baslangic_iso:
        return None
    try:
        b = datetime.fromisoformat(baslangic_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    simdi = simdi or datetime.now(timezone.utc)
    gecen = (simdi - b).total_seconds() / 60
    if gecen < 0:
        return None
    # Devre arasi DUSULUR ama dakika 45'in ALTINA inemez: gecen sure 50 iken
    # 50-15=35 demek "devre arasindan once" demektir, imkansiz.
    # (testte yakalandi: 50 dk gecmisken 35. dakika diyordu)
    dk = gecen if gecen <= 45 else max(45, gecen - DEVRE_ARASI)
    return max(0, min(95, int(dk)))


def durumlar(gunluk_olaylar: list) -> dict:
    """{(espn_ev_id, espn_dep_id): {skor, dakika}} — yalnizca canli maclar.

    ISIMLE DEGIL ID ile anahtarlanir: isim eslestirmesi canlida coktu
    (ESPN "Liga de Quito" vs Nesine "LDU Quito" hicbiri digerini icermiyor).
    Nesine mac id -> ESPN takim id eslesmesi gunluk iste dogrulanip
    `data/eslesme.json` dosyasina yaziliyor; burada o kullanilir.
    """
    out = {}
    for e in gunluk_olaylar:
        if e.get("status") != "live":
            continue
        rak = e.get("competitors") or []
        ev = next((c for c in rak if c.get("qualifier") == "home"), None)
        dep = next((c for c in rak if c.get("qualifier") == "away"), None)
        if not ev or not dep:
            continue
        dk = tahmini_dakika(e.get("start_time") or "")
        out[(str((ev.get("team") or {}).get("id")),
             str((dep.get("team") or {}).get("id")))] = {
            "ev_skor": int(ev.get("score") or 0),
            "dep_skor": int(dep.get("score") or 0),
            "dakika": dk,
            "guvenli": dk is not None and dk <= GUVENLI_DAKIKA,
            "espn_ev": (ev.get("team") or {}).get("name"),
            "espn_dep": (dep.get("team") or {}).get("name"),
        }
    return out
