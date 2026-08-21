"""Canli mac modeli: mevcut skor + kalan sure uzerinden olasilik.

NEDEN AYRI: mac oncesi model canlida ZARARLIDIR. 80. dakikada 2-0 onde olan
takim icin mac oncesi model hala "%58 kazanir" der; gercek ~%99'dur. Skor ve
dakika olmadan canli tahmin yapilMAZ.

VERI: Nesine'nin canli bulteninde skor/dakika alani YOK (olculdu). Bu yuzden
skor ESPN'in gunluk programindan alinir. ESPN Turkiye'den engelli oldugu icin
bu modul YALNIZCA GitHub Actions'ta calisir.

TUZAK: ESPN'in canli verisi Nesine'den GERIDE kalabilir. Geride kalirsa
bulunan "deger" sahtedir -- Nesine golu fiyatlamis, biz gormemisizdir.
Bu yuzden her canli tahminde ESPN'in bildirdigi dakika mesaja YAZILIR.
"""
from __future__ import annotations

from math import exp, factorial

MAC_DK = 90


def _pois(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return exp(-lam) * lam ** k / factorial(k)


def kalan_oran(dakika: int | None) -> float:
    """Kalan surenin maca orani. Dakika bilinmiyorsa None -> model YOK."""
    if dakika is None:
        return 0.0
    return max(0.0, min(1.0, (MAC_DK - dakika) / MAC_DK))


def tahmin(le_tam: float, ld_tam: float, ev_skor: int, dep_skor: int,
           dakika: int, maks: int = 8) -> dict | None:
    """Kalan sureye gore mac sonu olasiliklari.

    le_tam / ld_tam: 90 dakikalik gol beklentileri (mac oncesi model)
    """
    k = kalan_oran(dakika)
    if k <= 0:
        return None
    le, ld = le_tam * k, ld_tam * k
    P = [[_pois(i, le) * _pois(j, ld) for j in range(maks + 1)]
         for i in range(maks + 1)]
    R = range(maks + 1)
    ev_k = ber = dep_k = 0.0
    toplam_ust: dict = {}
    for i in R:
        for j in R:
            p = P[i][j]
            se, sd = ev_skor + i, dep_skor + j
            if se > sd:
                ev_k += p
            elif se == sd:
                ber += p
            else:
                dep_k += p
            toplam_ust[se + sd] = toplam_ust.get(se + sd, 0.0) + p
    kg = sum(P[i][j] for i in R for j in R
             if (ev_skor + i) >= 1 and (dep_skor + j) >= 1)

    def ust(n: float) -> float:
        return sum(v for t, v in toplam_ust.items() if t > n)

    return {"MS1": ev_k, "MSX": ber, "MS2": dep_k,
            "CS1X": ev_k + ber, "CS12": ev_k + dep_k, "CSX2": ber + dep_k,
            "KG_VAR": kg, "KG_YOK": 1 - kg,
            "ust": ust, "dakika": dakika, "kalan": k,
            "skor": (ev_skor, dep_skor)}


def olasilik(mtid: int, idx: int, sov, t: dict) -> float | None:
    """Canli Nesine secenegi -> model olasiligi (mevcut skor + kalan sure).

    ILK YARI marketleri (61, 70, 453) KAPSAM DISI: ilk yarinin ne kadari
    kaldigini bilmiyoruz (ESPN dakika vermiyor, tahmin ediyoruz) ve mac 45'i
    gectiyse o marketler zaten kapanmis olur. Tahmin uretmek yerine
    None donuluyor -- bot o secenekleri yalnizca FIYATA gore degerlendirir.
    """
    if not t:
        return None
    s = None if sov is None else float(sov)
    if mtid == 53:
        return [t["MS1"], t["MSX"], t["MS2"]][idx]
    if mtid == 55:
        return [t["CS1X"], t["CS12"], t["CSX2"]][idx]
    if mtid == 287:
        return [t["KG_VAR"], t["KG_YOK"]][idx]
    if mtid in (66, 67, 68) and s is not None:      # 1,5 / 2,5 / 3,5 Gol A/U
        u = t["ust"](s)
        return [1 - u, u][idx]
    return None
