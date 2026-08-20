"""Dogrulanmis market katalogu (68 market tipi).

KAYNAK: Nesine'nin kendi sitesindeki `CCAll.min.js` dosyasindan cikarildi.
Tahmin YOK -- isimler ve secenekler Nesine'nin kendi sozlugunden geliyor.

DOGRULAMA: her marketin katalogdaki secenek sayisi, bultendeki gercek secenek
sayisiyla karsilastirildi. 68 markette **0 uyusmazlik**. Secenekleri katalogda
dinamik uretilen 35 market (kesin skor gibi 29-68 secenekli) DISARIDA birakildi
-- secenek adini bilemedigimiz markete bahis onerilmez.

MEKANIZMA HASH'INE DAHIL DEGIL: core.MARKETS (2 market) muhurlu v1.0
mekanizmasini surer; bu katalog yalnizca arsiv ve /kupon icindir.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_YOL = Path(__file__).resolve().parent.parent / "data" / "market_katalog.json"
KATALOG: dict = {int(k): v for k, v in json.loads(_YOL.read_text(encoding="utf-8")).items()}

# Arsivlenecek ve /kupon'da kullanilacak marketler. Tum 68'i arsivlemek
# snapshot'i ~10 kat buyutur; asagidaki liste kapsam/boyut dengesi.
# (bkz. README "Market kapsami")
KAPSAM = [
    1,    # Maç Sonucu
    3,    # Çifte Şans
    12,   # 2,5 Gol Alt/Üst
    11,   # 1,5 Gol Alt/Üst
    13,   # 3,5 Gol Alt/Üst
    38,   # Karşılıklı Gol
    49,   # Tek/Çift
    7,    # 1. Yarı Sonucu
    8,    # 1. Yarı Çifte Şans
    14,   # 1. Yarı 1,5 Gol Alt/Üst
    209,  # 1. Yarı 0,5 Gol Alt/Üst
    20,   # Ev Sahibi 1,5 Gol Alt/Üst
    29,   # Deplasman 1,5 Gol Alt/Üst
    43,   # Toplam Gol Aralığı
    268,  # Handikaplı Maç Sonucu
    216,  # Korner Alt/Üst
    218,  # 1. Yarı Korner Alt/Üst
    301,  # Kart Puanı Alt/Üst
    220,  # En Çok Korner
    338,  # Toplam Korner Aralığı
]


def ad(mtid: int, sov: float | None = None) -> str:
    """Market adi. {{handicap}} / {{SOV}} yer tutuculari SOV ile doldurulur."""
    k = KATALOG.get(mtid)
    if not k:
        return f"MTID {mtid}"
    s = k["ad"]
    if sov is not None:
        deger = f"{sov:g}".replace(".", ",")
        s = re.sub(r"\{\{(handicap|SOV)\}\}", deger, s)
    return re.sub(r"\{\{[^}]+\}\}", "", s).strip()


def secenek(mtid: int, i: int) -> str:
    k = KATALOG.get(mtid)
    if not k or i >= len(k["secenek"]):
        return f"#{i+1}"
    return k["secenek"][i]


def secenek_sayisi(mtid: int) -> int:
    return len(KATALOG.get(mtid, {}).get("secenek", []))


def kapsamda(mtid: int) -> bool:
    return mtid in KAPSAM and mtid in KATALOG
