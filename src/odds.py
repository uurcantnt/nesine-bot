"""Oran matematigi. Saf hesap, ag erisimi yok, test edilebilir.

Terimler:
  overround (marj) : sum(1/oran)/kapsam - 1. Bahisciye odenen pay.
  devig            : marji cikarip olasiliga cevirme (carpimsal normalizasyon).
  EV               : 1 birim yatirimda beklenen net getiri (negatifse kayip).
"""
from __future__ import annotations

from math import prod


def overround(odds: list[float], kapsam: int = 1) -> float | None:
    """Marj. Cifte sansta her secenek 2 sonucu kapsar -> kapsam=2."""
    if not odds or any(o <= 1.0 for o in odds):
        return None
    return sum(1.0 / o for o in odds) / kapsam - 1.0


def devig(odds: list[float], kapsam: int = 1) -> list[float] | None:
    """Marjdan arindirilmis olasiliklar. Toplamlari kapsam kadardir.

    Carpimsal (multiplicative) yontem: her secenegin ham olasiligi ayni
    katsayiyla bolunur. Alternatifler (power/Shin) v1.0 kapsaminda degil --
    secilen yontem MEKANIZMA_v1.0.md'de dondurulmustur.
    """
    if not odds or any(o <= 1.0 for o in odds):
        return None
    ham = [1.0 / o for o in odds]
    s = sum(ham) / kapsam
    if s <= 0:
        return None
    return [h / s for h in ham]


def ev_tek(oran: float, olasilik: float) -> float:
    """Tek bahiste 1 TL basina beklenen net getiri."""
    return olasilik * oran - 1.0


def kupon_oran(oranlar: list[float]) -> float:
    """Kuponun toplam orani (bacaklarin carpimi)."""
    return prod(oranlar)


def kupon_ev(oranlar: list[float], olasiliklar: list[float]) -> float:
    """Kuponun EV'si.

    UYARI: bacaklarin BAGIMSIZ oldugu varsayilir. Ayni maca/ligi paylasan
    bacaklarda gercek varyans daha yuksektir; EV tahmini iyimserdir.
    """
    return prod(olasiliklar) * prod(oranlar) - 1.0


def kupon_marj(overroundlar: list[float]) -> float:
    """Kupon marji carpimsaldir: (1+m1)(1+m2)... - 1."""
    return prod(1.0 + m for m in overroundlar) - 1.0


def basabas_clv(marj: float) -> float:
    """Bu marjda basabas icin gereken goreli CLV.

    (1+c) * (1 - marj/(1+marj)) = 1  ->  c = marj
    Yani gereken CLV, marjin kendisine esittir.
    """
    return marj


def kelly(oran: float, olasilik: float, kesir: float = 1.0) -> float:
    """Optimal bahis orani. Edge negatifse 0 doner (bahis yok)."""
    b = oran - 1.0
    if b <= 0:
        return 0.0
    f = (b * olasilik - (1.0 - olasilik)) / b
    return max(0.0, f * kesir)
