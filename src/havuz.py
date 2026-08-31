"""Kaynak birlestirme: ters-varyans agirlikli LOGIT havuzu.

NEDEN DEGISTI (konsul bulgusu, 2026-08-21) — eski kural "kaynaklarin
MINIMUMUNU al" idi ve istatistiksel olarak SAKATTI:

  k bagimsiz gurultulu tahminin minimumunun beklenen degeri
      E[min] = mu - c_k * sigma          (c_2=0,564 · c_3=1,029 · c_4=1,163)
  Bizim kaynaklar arasi sapma ~5 puan oldugundan bu kural her secenege
  SISTEMATIK ~5 puanlik ASAGI yanlilik ekliyordu. Uc sonucu vardi:

    1. Ayni marketin secenek olasiliklari toplami 1'in ALTINA duser.
       Toplami 1 olmayan sey olasilik DEGILDIR.
    2. Kalibrasyon GARANTILI bozulur: "bot %60 dedi, gercekten %60 oldu mu"
       sorusu olculemez hale gelir. Oysa ON_KAYIT'taki tek kapi (R1)
       kalibrasyondur -- yani eski kural kendi sinavimizi imkansiz kiliyordu.
    3. Secilen aday sistematik olarak kaynaklarin EN COK AYRISTIGI yer olur;
       yani en cok bilgi degil, en cok GURULTU olan secenek one cikar.

YENI KURAL: logit uzayinda ters-varyans agirlikli ortalama.
Tahmin YANSIZDIR (durust). Ihtiyat artik gizli bir yan urun degil, ayri ve
GORUNUR bir kalem: GUVENLIK_PAYI. Boylece kalibrasyon olculebilir kalir ve
ihtiyatin maliyeti ayrica izlenebilir.

NE DEGISMEDI: model hala Nesine'den isabetli KABUL EDILMIYOR. Eski kuralda
bu "modeli sadece asagi yonde dinle" seklindeydi; yenisinde modele DUSUK
AGIRLIK verilerek ifade ediliyor. Ikisi de ayni inanci tasir, ama yenisi
olasiligi bozmadan tasir.
"""
from __future__ import annotations

from math import exp, log

# --- Agirliklar --------------------------------------------------------------
# OLCULEN marja dayanir; sonuca gore SECILMEDI (parametreyi sonuca gore secmek
# BtcTurk botunda reddedilen davranistir).
#
# Bir piyasanin keskinligi marjiyla ters orantili kabul edilir (agirlik ~ 1/marj):
#     DraftKings marji %6,7   -> 1/0,067 = 14,9
#     Nesine      marji %21,1 -> 1/0,211 =  4,74      oran ~ 3,15 : 1
#
# Modelimiz ve Gecmis icin marj yok; agirliklari OLCUME DEGIL YARGIYA dayanir
# ve bu bilincli olarak boyle yaziliyor:
#   Modelimiz 0,50 -- Nesine'den isabetli oldugu KANITLANMADI (eslestirilmis
#     fark t=+0,75, %95 aralik [-0,011,+0,024] sifiri iceriyor). Ustelik
#     parametreleri (xG %33, tavan 3,0) "Nesine fiyatindan az sap" olcutuyle
#     secildi -- yani kismen Nesine'nin KOPYASI, bagimsiz bilgi tasidigi
#     olculmedi. Bu yuzden Nesine'nin yarisi.
#   Gecmis 0,25 -- en az 8 mac sarti var ama 8 mac hala kucuk orneklem.
#   Piyasa(fd) -- football-data.co.uk (Betfair borsasi / bukmeker ortalamasi).
#     Agirligi SABIT DEGIL: marji mac basina degisiyor (2026-08-31: %1,3 ile
#     %12 arasi olculdu), o yuzden agirlik da mac basina 1/marj kuralindan
#     hesaplanip ek_agirlik ile gecirilir (bkz. fd.agirlik). Asagidaki 3,15
#     yalnizca ek_agirlik verilmezse gecerli olan yedek degerdir ve
#     DraftKings ile ayni gerekceye dayanir (%6,7 marj).
AGIRLIK = {
    "DraftKings": 3.15,
    "Piyasa(fd)": 3.15,
    "Nesine":     1.00,
    "Modelimiz":  0.50,
    "Geçmiş":     0.25,
}

# Secim kapisinda dusulen SABIT ihtiyat payi (puan).
# Eski min() kurali ~5 puanlik GIZLI bir ihtiyat uyguluyordu. Onu tamamen
# kaldirmak yerine daha kucugunu ACIK ve SABIT halde tutuyoruz: sabit oldugu
# icin kalibrasyonu kaydirir ama BOZMAZ (her tahmine ayni miktar), ve
# istenirse tek sayiyla geri alinabilir.
# NOT: 0,03 bir YARGIDIR, olcum degil. Olculdugunde degistirilecek.
GUVENLIK_PAYI = 0.03

EPS = 1e-6


def _logit(p: float) -> float:
    p = min(max(float(p), EPS), 1.0 - EPS)
    return log(p / (1.0 - p))


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + exp(-z))
    e = exp(z)
    return e / (1.0 + e)


def birlestir(kaynaklar: dict, ek_agirlik: dict | None = None) -> dict | None:
    """{"Nesine": 0.62, "Modelimiz": 0.55, ...} -> havuzlanmis tahmin.

    ek_agirlik: kaynak adi -> agirlik. AGIRLIK tablosunu EZER. Marji mac
    basina degisen kaynaklar (fd) icin var; agirlik yine 1/marj kuralindan
    gelir, sonuca bakilarak SECILMEZ.

    Doner:
      tahmin_p  : yansiz havuz tahmini (EKRANDA ve KALIBRASYONDA kullanilir)
      secim_p   : tahmin_p - GUVENLIK_PAYI (yalnizca SECIM kapisinda kullanilir)
      agirlik   : kullanilan agirliklar
      ayrisma   : en yuksek ile en dusuk kaynak arasi fark (puan)
      baskin    : en buyuk agirliga sahip kaynak
    """
    v = {k: float(p) for k, p in kaynaklar.items()
         if isinstance(p, (int, float)) and 0.0 < float(p) < 1.0}
    if not v:
        return None

    ek = ek_agirlik or {}
    w = {k: float(ek[k]) if k in ek else AGIRLIK.get(k, 0.25) for k in v}
    top = sum(w.values()) or 1.0
    z = sum(_logit(v[k]) * w[k] for k in v) / top
    p = _sigmoid(z)

    return {
        "tahmin_p": p,
        "secim_p": max(EPS, p - GUVENLIK_PAYI),
        "agirlik": w,
        "kaynaklar": v,
        "ayrisma": max(v.values()) - min(v.values()),
        "baskin": max(w, key=w.get),
    }
