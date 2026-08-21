"""Kendi olasilik tahminimiz — ESPN istatistiklerinden Poisson modeli.

NE YAPAR: takimlarin son 10 macindaki gol/korner/kart ortalamalarindan
bu macin beklenen degerlerini (lambda) cikarir, Poisson dagilimiyla
market olasiliklarini hesaplar.

NE YAPMAZ: sakatlik, kadro, motivasyon, hava, hakem, saha zemini... Bunlarin
hicbiri hesaba girmiyor. Model BASIT ve bunu gizlemiyoruz.

VARSAYIMLAR (olculmedi, literaturdeki standart degerler):
  EV_AVANTAJI = 1.15
XG_AGIRLIK = 0.33     # xG'nin lambda'daki payi (gerisi gol ortalamasi)
XG_TAVAN = 3.0        # mac basi xG bunun ustune cikamaz
#
# ############################################################################
# BU PARAMETRENIN GEREKCESI GECERSIZ ILAN EDILDI (2026-08-21, konsul bulgusu).
# ############################################################################
#
# ESKI SECIM OLCUTU: "Nesine fiyatina karsi ortalama mutlak fark" (92 mac,
# 3083 secenek). O olcute gore siralama netti:
#     sadece gol   4,53p · karma %25 4,12p · karma %33+kirp3,0 3,98p (secildi)
#     karma %50    3,93p (ort. kotu) · sadece xG 5,12p
# HATA: bu olcut ISABETI degil, Nesine'yi TAKLIT ETMEYI odullendirir. Bir
# model Nesine'nin marjini ve yanliligini da kopyalayarak bu skoru
# iyilestirebilir. Yani "kazanan" varyant, en dogru olan degil, bahisciye en
# cok benzeyen olabilir.
#
# DOGRU OLCUTLE YENIDEN SINANDI (src/walkforward.py -- olcut GERCEKLESEN
# SONUC, 40 mac / 198 secim, mac duzeyinde kumelenmis onyukleme):
#     sadece gol            Brier 0,1850 · RPS 0,1944
#     karma %25             0,1847 · 0,1944
#     karma %33 + kirp 3,0  0,1846 · 0,1945   <- simdiki
#     karma %33 kirpsiz     0,1847 · 0,1948
#     karma %50             0,1846 · 0,1946
#     sadece xG             0,1848 · 0,1954
#   HICBIR VARYANT digerinden AYIRT EDILEMIYOR (tum %95 araliklari sifiri
#   iceriyor; en buyuk fark 0,0004 Brier).
#
# DURUM: %33 ve 3,0 degerleri KORUNUYOR -- degistirmek icin de kanit yok.
# Ama artik "olculdu ve kazandi" DENEMEZ. Dogru ifade: "gerekcesi yazilmadi,
# orneklem (40 mac) ayirt etmeye yetmiyor; birkac yuz mac gerekir."
# Parametre, walkforward.py ayirt edici sonuc verene kadar DONDURULMUSTUR.
# KIRPMA NEDEN: xG dagiliminda uc degerler var (p95 4,90 · maks 6,78);
# mac basi 6,78 xG imkansiz -- muhtemelen lig maci sayisi eksik sayilmis.
IY_ORAN = 0.45      # gollerin ilk yaride gerceklesme orani (VARSAYIM)
#
# IY_ORAN NEDEN VARSAYIM: elimizde ilk yari skorlari YOK (ESPN mac ozetinde
# saklamiyoruz). Literaturde ilk yari gol orani ~%44-46. Olculmedigi icin
# ilk yari tahminlerinin guveni DUSUK isaretlenir.  -- ev sahibi gol beklentisi carpani
  DEP_CARPANI = 0.90  -- deplasman gol beklentisi carpani
  Goller bagimsiz Poisson kabul edilir (gercekte hafif korelasyon var;
  Dixon-Coles duzeltmesi UYGULANMADI).
  Kart: Nesine'nin "Kart Puani" baraji OLCULDU -> 2,5-6,5 araliginda, yani
  KART SAYISI olceginde (sari=10 puan olsaydi baraj 35,5 olurdu). Model
  puan = sari + 2 x kirmizi kabul eder; kirmizinin agirligi DOGRULANMADI
  ama kirmizi kart nadir oldugu icin etkisi kucuk.
"""
from __future__ import annotations

from math import exp, factorial

EV_AVANTAJI = 1.15
XG_AGIRLIK = 0.33     # xG'nin lambda'daki payi (gerisi gol ortalamasi)
XG_TAVAN = 3.0        # mac basi xG bunun ustune cikamaz
#
# ############################################################################
# BU PARAMETRENIN GEREKCESI GECERSIZ ILAN EDILDI (2026-08-21, konsul bulgusu).
# ############################################################################
#
# ESKI SECIM OLCUTU: "Nesine fiyatina karsi ortalama mutlak fark" (92 mac,
# 3083 secenek). O olcute gore siralama netti:
#     sadece gol   4,53p · karma %25 4,12p · karma %33+kirp3,0 3,98p (secildi)
#     karma %50    3,93p (ort. kotu) · sadece xG 5,12p
# HATA: bu olcut ISABETI degil, Nesine'yi TAKLIT ETMEYI odullendirir. Bir
# model Nesine'nin marjini ve yanliligini da kopyalayarak bu skoru
# iyilestirebilir. Yani "kazanan" varyant, en dogru olan degil, bahisciye en
# cok benzeyen olabilir.
#
# DOGRU OLCUTLE YENIDEN SINANDI (src/walkforward.py -- olcut GERCEKLESEN
# SONUC, 40 mac / 198 secim, mac duzeyinde kumelenmis onyukleme):
#     sadece gol            Brier 0,1850 · RPS 0,1944
#     karma %25             0,1847 · 0,1944
#     karma %33 + kirp 3,0  0,1846 · 0,1945   <- simdiki
#     karma %33 kirpsiz     0,1847 · 0,1948
#     karma %50             0,1846 · 0,1946
#     sadece xG             0,1848 · 0,1954
#   HICBIR VARYANT digerinden AYIRT EDILEMIYOR (tum %95 araliklari sifiri
#   iceriyor; en buyuk fark 0,0004 Brier).
#
# DURUM: %33 ve 3,0 degerleri KORUNUYOR -- degistirmek icin de kanit yok.
# Ama artik "olculdu ve kazandi" DENEMEZ. Dogru ifade: "gerekcesi yazilmadi,
# orneklem (40 mac) ayirt etmeye yetmiyor; birkac yuz mac gerekir."
# Parametre, walkforward.py ayirt edici sonuc verene kadar DONDURULMUSTUR.
# KIRPMA NEDEN: xG dagiliminda uc degerler var (p95 4,90 · maks 6,78);
# mac basi 6,78 xG imkansiz -- muhtemelen lig maci sayisi eksik sayilmis.
IY_ORAN = 0.45      # gollerin ilk yaride gerceklesme orani (VARSAYIM)
#
# IY_ORAN NEDEN VARSAYIM: elimizde ilk yari skorlari YOK (ESPN mac ozetinde
# saklamiyoruz). Literaturde ilk yari gol orani ~%44-46. Olculmedigi icin
# ilk yari tahminlerinin guveni DUSUK isaretlenir.
DEP_CARPANI = 0.90
MAKS_GOL = 10
MAKS_KORNER = 30


def pois(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return exp(-lam) * lam ** k / factorial(k)


def gol_lambdalari(ev: dict, dep: dict) -> tuple:
    """(ev_lambda, dep_lambda).

    Karisik (ic+dis) ortalama x sabit carpan. Alternatifler olculdu ve
    ELENDI -- asagidaki nota bak.
    """
    # ÖLÇÜLDÜ (2908 secenek, Nesine fiyatina karsi ortalama mutlak fark):
    #   karisik ortalama + sabit carpan : 4,8 puan  <- KAZANAN
    #   buzusturulmus (k=5)             : 4,9 puan
    #   saf ic/dis ayrimi               : 5,9 puan
    # Teorik olarak "dogru" olan saf ic/dis EN KOTU cikti: 10 maci ikiye
    # bolunce her ortalama 5 maca iniyor ve gurultu, ic saha bilgisinin
    # katkisini yiyor. ic_at/dis_at alanlari yine de saklaniyor -- mac sayisi
    # arttiginda bu olcum TEKRARLANMALI.
    le = (ev["gol_at"] + dep["gol_ye"]) / 2 * EV_AVANTAJI
    ld = (dep["gol_at"] + ev["gol_ye"]) / 2 * DEP_CARPANI
    # xG varsa karistir: gol ortalamasi ne yapildigini, xG ne yapilmasi
    # gerektigini olcer. Ikisinin karmasi tek basina her birinden iyi.
    if all(ev.get(k) and dep.get(k) for k in ("xg", "xg_yenilen")):
        kir = lambda v: min(float(v), XG_TAVAN)
        xe = (kir(ev["xg"]) + kir(dep["xg_yenilen"])) / 2 * EV_AVANTAJI
        xd = (kir(dep["xg"]) + kir(ev["xg_yenilen"])) / 2 * DEP_CARPANI
        le = le * (1 - XG_AGIRLIK) + xe * XG_AGIRLIK
        ld = ld * (1 - XG_AGIRLIK) + xd * XG_AGIRLIK
    return max(0.05, le), max(0.05, ld)


def skor_matrisi(le: float, ld: float) -> list:
    return [[pois(i, le) * pois(j, ld) for j in range(MAKS_GOL + 1)]
            for i in range(MAKS_GOL + 1)]


def gol_olasiliklari(le: float, ld: float) -> dict:
    """Gol tabanli marketlerin olasiliklari."""
    P = skor_matrisi(le, ld)
    R = range(MAKS_GOL + 1)
    ev_k = sum(P[i][j] for i in R for j in R if i > j)
    ber = sum(P[i][i] for i in R)
    dep_k = sum(P[i][j] for i in R for j in R if i < j)
    kg = sum(P[i][j] for i in range(1, MAKS_GOL + 1) for j in range(1, MAKS_GOL + 1))
    tek = sum(P[i][j] for i in R for j in R if (i + j) % 2 == 1)

    def ust(n: float) -> float:
        return sum(P[i][j] for i in R for j in R if i + j > n)

    def aralik(a: int, b: int) -> float:
        return sum(P[i][j] for i in R for j in R if a <= i + j <= b)

    return {
        "MS1": ev_k, "MSX": ber, "MS2": dep_k,
        "CS1X": ev_k + ber, "CS12": ev_k + dep_k, "CSX2": ber + dep_k,
        "KG_VAR": kg, "KG_YOK": 1 - kg,
        "TEK": tek, "CIFT": 1 - tek,
        "ust": ust, "aralik": aralik,
        "ev_lambda": le, "dep_lambda": ld,
    }


def sayac_olasiliklari(lam: float, maks: int = MAKS_KORNER) -> dict:
    """Korner/kart gibi sayim marketleri icin Poisson."""
    p = [pois(k, lam) for k in range(maks + 1)]

    def ust(n: float) -> float:
        return sum(p[k] for k in range(maks + 1) if k > n)

    def aralik(a: int, b: int) -> float:
        return sum(p[k] for k in range(maks + 1) if a <= k <= b)

    return {"ust": ust, "aralik": aralik, "tek": sum(p[k] for k in range(maks + 1) if k % 2),
            "lambda": lam, "dagilim": p}


def takim_ust(lam: float, n: float) -> float:
    """Tek takimin gol sayisi n'i asma olasiligi."""
    return sum(pois(k, lam) for k in range(MAKS_GOL + 1) if k > n)


def handikap(le: float, ld: float, h: float) -> list:
    """Handikapli mac sonucu: ev skoruna h eklenir. [1, X, 2] olasiliklari."""
    P = skor_matrisi(le, ld)
    R = range(MAKS_GOL + 1)
    bir = ber = iki = 0.0
    for i in R:
        for j in R:
            fark = (i + h) - j
            p = P[i][j]
            if fark > 0:
                bir += p
            elif abs(fark) < 1e-9:
                ber += p
            else:
                iki += p
    return [bir, ber, iki]


def tahmin(ev: dict, dep: dict) -> dict:
    """Bir mac icin tum model ciktisi. Eksik veri varsa o bolum None."""
    out: dict = {"kaynak": {"ev_mac": ev.get("mac"), "dep_mac": dep.get("mac")}}
    le, ld = gol_lambdalari(ev, dep)
    out["gol"] = gol_olasiliklari(le, ld)
    out["gol"]["handikap"] = lambda h: handikap(le, ld, h)
    out["gol"]["ev_ust"] = lambda n: takim_ust(le, n)
    out["gol"]["dep_ust"] = lambda n: takim_ust(ld, n)
    # ilk yari: gollerin IY_ORAN kadari (VARSAYIM, olculmedi)
    out["iy"] = gol_olasiliklari(le * IY_ORAN, ld * IY_ORAN)
    # Guvenilirlik kapilari — OLCULDU:
    #   sari kart ortalamasi: medyan 1,80 · p10 0,90; 17/170 takim 1,0 altinda
    #   ve UCU tam 0,00 (Cardiff, Erzurum BB, Corum FK) -> 10 macta sifir sari
    #   imkansiz, veri yok demek. Boyle veriyle tahmin URETMEK, tahmin
    #   uretmemekten KOTUDUR (yanlis guven verir).
    if (ev.get("korner") or 0) >= 2.0 and (dep.get("korner") or 0) >= 2.0 \
            and min(ev.get("korner_n", 0), dep.get("korner_n", 0)) >= 5:
        out["korner"] = sayac_olasiliklari(ev["korner"] + dep["korner"])
    if (ev.get("sari") or 0) >= 1.0 and (dep.get("sari") or 0) >= 1.0 \
            and min(ev.get("kart_n", 0), dep.get("kart_n", 0)) >= 5:
        puan = (ev["sari"] + dep["sari"]) + 2 * ((ev.get("kirmizi") or 0)
                                                 + (dep.get("kirmizi") or 0))
        out["kart"] = sayac_olasiliklari(puan, maks=20)
    return out


# ── Nesine market/secenek -> model olasiligi eslemesi ────────────────────
def olasilik(mtid: int, idx: int, sov, t: dict) -> float | None:
    """Bu Nesine secenegi icin model olasiligi. Modellenemiyorsa None."""
    g = t.get("gol")
    if g is None:
        return None
    s = None if sov is None else float(sov)

    if mtid in (1, 53):                      # Mac Sonucu
        return [g["MS1"], g["MSX"], g["MS2"]][idx]
    if mtid in (3, 55):                      # Cifte Sans
        return [g["CS1X"], g["CS12"], g["CSX2"]][idx]
    if mtid in (38, 287):                    # Karsilikli Gol
        return [g["KG_VAR"], g["KG_YOK"]][idx]
    if mtid in (49, 109):                    # Tek/Cift
        return [g["TEK"], g["CIFT"]][idx]
    if mtid in (11, 12, 13) and s is not None:   # 1,5 / 2,5 / 3,5 Gol Alt/Ust
        u = g["ust"](s)
        return [1 - u, u][idx]
    if mtid == 43:                           # Toplam Gol Araligi 0-1/2-3/4-5/6+
        return [g["aralik"](0, 1), g["aralik"](2, 3),
                g["aralik"](4, 5), 1 - g["aralik"](0, 5)][idx]
    # ── İLK YARI ────────────────────────────────────────────────────────
    iy = t.get("iy")
    if iy:
        if mtid == 7:                        # 1. Yari Sonucu
            return [iy["MS1"], iy["MSX"], iy["MS2"]][idx]
        if mtid == 8:                        # 1. Yari Cifte Sans
            return [iy["CS1X"], iy["CS12"], iy["CSX2"]][idx]
        if mtid in (14, 209, 15) and s is not None:   # 1.Y Gol Alt/Ust
            u = iy["ust"](s)
            return [1 - u, u][idx]
        if mtid == 452:                      # 1. Yari Karsilikli Gol
            return [iy["KG_VAR"], iy["KG_YOK"]][idx]
        if mtid == 450:                      # 1. Yari Tek/Cift
            return [iy["TEK"], iy["CIFT"]][idx]
    # ── TAKIM BAZLI TOPLAM ──────────────────────────────────────────────
    if mtid in (20, 455) and s is not None:  # Ev Sahibi Gol Alt/Ust
        u = g["ev_ust"](s)
        return [1 - u, u][idx]
    if mtid in (29, 256, 457) and s is not None:   # Deplasman Gol Alt/Ust
        u = g["dep_ust"](s)
        return [1 - u, u][idx]
    # ── HANDIKAP ────────────────────────────────────────────────────────
    if mtid in (268, 60) and s is not None:
        return g["handikap"](s)[idx]
    if mtid == 216 and s is not None and t.get("korner"):     # Korner Alt/Ust
        u = t["korner"]["ust"](s)
        return [1 - u, u][idx]
    if mtid == 299 and t.get("korner"):                       # Korner Tek/Cift
        return [t["korner"]["tek"], 1 - t["korner"]["tek"]][idx]
    if mtid == 218 and s is not None and t.get("korner"):     # 1.Y Korner Alt/Ust
        k2 = sayac_olasiliklari(t["korner"]["lambda"] * IY_ORAN)
        u = k2["ust"](s)
        return [1 - u, u][idx]
    if mtid == 338 and t.get("korner"):      # Toplam Korner Araligi
        # secenek adlari "0-8", "9-11", "12+" gibi -> katalogdan okunur
        return None                           # aralik sinirlari degisken, atlanir
    if mtid == 301 and s is not None and t.get("kart"):       # Kart Puani Alt/Ust
        # SOV kart PUANI cinsinden (or. 4.5); model sari sayisi uzerinden
        u = t["kart"]["ust"](s)
        return [1 - u, u][idx]
    return None
