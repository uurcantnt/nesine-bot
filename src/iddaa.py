"""IDDAA resmi sportsbook API'si — BAGIMSIZ IKINCI BULTEN KAYNAGI.

NE ICIN: Nesine'nin CDN'i 2026-08-20'de bir kez 960 yerine 96 mac dondurdu
(sebep bulunamadi, 6 tekrar denemede uretilemedi). O gun konulan sanity
kapisi yalnizca ONCEKI SNAPSHOT'a bakiyordu; bu iki durumda kordur:
  1. Elde onceki snapshot yoksa (ilk kosu, temiz depo)
  2. Kucultme kademeliyse (her seferinde %10 kayip esigi asmaz)
Bu modul o kapiya DIS CAPA saglar.

NEDEN AYNI PROGRAM: Turkiye'de tum yasal siteler (Nesine/Misli/Bilyoner/
Tuttur) ayni Iddaa programini yayinlar. OLCULDU 2026-08-21:
    Nesine futbol bulteni      : 1013 mac
    Iddaa type=0 futbol        : 1041 mac
    ORTAK ID                   :  911  (Nesine'nin %90'i)
Mac ID'leri de AYNI uzayda -- Nesine'nin canli 31 macinin 30'u Iddaa
ID'siyle birebir eslesti. Yani bu bir tahmin degil, dogrudan kiyas.

NE VERMEZ: skor, dakika, korner, kart. Olay nesnesi yalnizca oran tasir
(olculdu). statistics.iddaa.com DNS'te var ama her yolda 503 doner.
Canli istatistik icin tek calisan kaynak hala Fotmob.

ANAHTAR GEREKMEZ, Turkiye'den acik.
"""
from __future__ import annotations

import json
import time
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
# type=0 ve type=3 ayni sonucu veriyor (olculdu); type=1 yalnizca canli
# bahse acik alt kume (781), type=2 uzun vadeli bahisler.
PROGRAM = "https://sportsbookv2.iddaa.com/sportsbook/events?st=1&type=0&version=0"
FUTBOL = 1                # sid alani
ONBELLEK_SN = 600         # 10 dk: kapi 15 dk'da bir kosuyor, her seferinde
                          # 4 MB cekmenin anlami yok
_ONBELLEK: dict = {}


def _get(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json",
        "Referer": "https://www.iddaa.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def program(timeout: int = 30) -> list[dict] | None:
    """Iddaa futbol programi. Ulasilamazsa None (HATA FIRLATMAZ).

    Bilincli: bu kaynak bir YARDIMCIDIR. Iddaa cokerse Nesine boru hatti
    calismaya devam etmeli -- ikinci kaynak yeni bir ariza noktasi olmamali.
    """
    simdi = time.time()
    if _ONBELLEK.get("t", 0) + ONBELLEK_SN > simdi:
        return _ONBELLEK.get("v")
    try:
        d = _get(PROGRAM, timeout)
        if not d.get("isSuccess"):
            return None
        ev = [e for e in (d.get("data") or {}).get("events", [])
              if e.get("sid") == FUTBOL]
        _ONBELLEK.update(t=simdi, v=ev)
        return ev
    except Exception as e:
        print(f"[iddaa] alinamadi: {e}")
        return None


def sayi(timeout: int = 30) -> int | None:
    """Iddaa'daki futbol mac sayisi. Ulasilamazsa None."""
    ev = program(timeout)
    return len(ev) if ev is not None else None


def kimlikler(timeout: int = 30) -> set | None:
    """Iddaa mac ID kumesi (Nesine ile AYNI uzay)."""
    ev = program(timeout)
    return {e["i"] for e in ev if "i" in e} if ev is not None else None
