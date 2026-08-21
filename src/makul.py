"""Takim istatistikleri icin MAKUL ARALIK kapisi.

KOK SEBEP (olculdu 2026-08-21, kullanici bildirdi: "bir mac 19 korner
bekliyorum dedi"):

Fotmob'un takim ucundaki "Corners", "Yellow cards", "Expected goals"
alanlari SEZON TOPLAMIDIR. Bunlari mac basina cevirmek icin oynanan mac
sayisina bolunuyor. Bolen olarak `fixtures.allFixtures` icindeki bitmis
lig maclari sayiliyordu. AMA O LISTE SEZONUN TAMAMI DEGIL, BIR PENCERE:

    River Plate (id 10076) — OLCULDU
      Corners (sezon toplami) : 141
      allFixtures kayit       : 21  (yalnizca 9'u bitmis)
      primary ligde bitmis    : 6      <-- bolen buydu
      sonuc                   : 141/6 = 23,5 korner/mac  (IMKANSIZ)
      gercege yakin           : ~20 mac oynanmis -> ~7 korner/mac

Ayni bolen xG'yi de bozuyor: River Plate xG 40,7/6 = 6,78/mac. model.py'deki
XG_TAVAN = 3.0 aslinda BU HATAYI ortuyordu.

Dogru boleni bu payload'da bulmak MUMKUN DEGIL (sezon istatistikleri butun
turnuvalari kapsiyor, tablo ise yalnizca guncel grup asamasini gosteriyor;
Arjantin'de Apertura+Clausura+kupa ayni sezon sayiliyor).

Bu yuzden kurtarmaya CALISILMAZ: makul araligin disina dusen deger
KULLANILMAZ. Yanlis sayiyla tahmin yapmaktansa "veri yok" demek dogrudur --
kullaniciya 19 korner beklendigini soylemek, hicbir sey sylememekten kotudur.

ARALIKLAR: takim basina, MAC BASI. Kaynak: futbol istatistik dagilimlari.
  korner  1,5-9,0  (sezon ortalamasi olarak 9 ustu bir takim yok)
  sari    0,5-5,0
  xG      0,3-3,5
"""
from __future__ import annotations

ARALIK = {
    "korner":       (1.5, 9.0),
    "korner_yenilen": (1.5, 9.0),
    "sari":         (0.5, 5.0),
    "sari_yenilen": (0.5, 5.0),
    "xg":           (0.3, 3.5),
    "xg_yenilen":   (0.3, 3.5),
}

# Kac deger elendi -- gorunur olsun diye sayilir (sessiz kayip olmasin).
ELENEN: dict = {}


def gecerli(anahtar: str, deger) -> bool:
    """Deger makul araliktaysa True. Aralik tanimli degilse hep True."""
    if not isinstance(deger, (int, float)):
        return False
    sinir = ARALIK.get(anahtar)
    if not sinir:
        return True
    return sinir[0] <= float(deger) <= sinir[1]


def suz(d: dict | None) -> dict | None:
    """Takim istatistigi sozlugunden makul olmayan degerleri CIKAR."""
    if not d:
        return d
    out = dict(d)
    for k in list(ARALIK):
        if k in out and out[k] is not None and not gecerli(k, out[k]):
            ELENEN[k] = ELENEN.get(k, 0) + 1
            out[k] = None
            n = k + "_n"
            if n in out:
                out[n] = 0
    return out
