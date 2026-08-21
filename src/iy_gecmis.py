"""Ilk yari gecmisi: takimlarin son maclarindaki ILK YARI skorlari.

NEDEN AYRI: takim kayitlarinda yalnizca MAC SONU skoru var. Ilk yari skoru
Fotmob'da mac DETAYINDA; her mac icin ayri istek gerekiyor (1200 takim x
12 mac = ~14.000 istek). Bu yuzden gunluk toplamaya konulMADI.

YONTEM: ihtiyac aninda cek, kalici onbellege yaz. Bot yalnizca ILK YARI
bahsi onerdigi maclar icin cagirir -> kupon basina ~20 istek. Ayni mac
bir daha cekilmez; onbellek zamanla dolar ve maliyet sifira yaklasir.
"""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
ONBELLEK = DATA / "iy_gecmis.json"
MAKS_CAGRI = 24          # tek /kupon calismasinda en fazla bu kadar yeni istek


def _yukle() -> dict:
    if ONBELLEK.exists():
        try:
            return json.loads(ONBELLEK.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _kaydet(d: dict) -> None:
    import depo
    depo.yaz(ONBELLEK, json.dumps(d, ensure_ascii=False))


_ONB = None
_SAYAC = {"cagri": 0}


def _onb() -> dict:
    global _ONB
    if _ONB is None:
        _ONB = _yukle()
    return _ONB


def mac_iy(fotmob_mac_id) -> dict | None:
    """Tek macin ilk yari skoru (onbellekli)."""
    o = _onb()
    k = str(fotmob_mac_id)
    if k in o:
        return o[k]
    if _SAYAC["cagri"] >= MAKS_CAGRI:
        return None
    _SAYAC["cagri"] += 1
    import sonuc as S
    s = S.mac_sonucu(fotmob_mac_id)
    if not s or s.get("iy_ev") is None:
        o[k] = None
        _kaydet(o)
        return None
    o[k] = {"iy_ev": s["iy_ev"], "iy_dep": s["iy_dep"],
            "iy_korner": s.get("iy_korner"), "iy_sari": s.get("iy_sari")}
    _kaydet(o)
    return o[k]


def takim_iy(takim_verisi: dict, takim_id: str, en_fazla: int = 8) -> list:
    """Takimin son maclarindaki ilk yari sonuclari.

    Donus: [{"at": ilk yari attigi, "ye": yedigi, "ev": ev sahibi mi}, ...]
    """
    maclar = takim_verisi.get("maclar") or []
    # Eski kayitlarda fotmob mac id'si yok (bu alan sonradan eklendi).
    # 1300 takimi bastan toplamak yerine, ILK YARI sorulan takimi tazele.
    if maclar and not maclar[0].get("fotmob_mac_id"):
        import fotmob
        yeni = fotmob.takim_verisi(takim_id)
        if yeni and (yeni.get("maclar") or [{}])[0].get("fotmob_mac_id"):
            takim_verisi.update(yeni)
            maclar = yeni["maclar"]
    out = []
    for m in maclar[:en_fazla]:
        fid = m.get("fotmob_mac_id")
        if not fid:
            continue
        iy = mac_iy(fid)
        if not iy:
            continue
        evde = bool(m.get("ev"))
        out.append({"at": iy["iy_ev"] if evde else iy["iy_dep"],
                    "ye": iy["iy_dep"] if evde else iy["iy_ev"],
                    "ev": evde, "iy_korner": iy.get("iy_korner")})
    return out
