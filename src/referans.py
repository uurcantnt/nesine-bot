"""Dis referans piyasa: DraftKings oranlari (ESPN gunluk programindan).

NEDEN ONEMLI: Nesine'nin marji %21. Kendi Poisson modelimizin bunu asmasi
zor. Ama BASKA BIR PIYASA'nin fiyati elimizdeyse, Nesine'nin nerede saptigini
dogrudan gorebiliriz -- kendi tahminimize hic guvenmeden.

OLCULDU (2026-08-21): ESPN gunluk programindaki 98 macin 88'inde (%90)
DraftKings moneyline + handikap + alt/ust 2,5 oranlari var. Acilis oranlari
(`open`) da geliyor.

DraftKings Pinnacle degildir; marji ~%6 (olculecek). Yine de Nesine'nin
%21'ine karsi anlamli bir kiyas noktasidir.
"""
from __future__ import annotations


def amerikan_ondalik(o) -> float | None:
    """Amerikan oranini ondalik orana cevir. '-190' -> 1.526, '+600' -> 7.0"""
    if o is None:
        return None
    s = str(o).strip().replace(" ", "")
    if not s or s in ("-", "+"):
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if v == 0:
        return None
    return 1 + (100 / abs(v)) if v < 0 else 1 + (v / 100)


def devig(oranlar: list) -> tuple:
    """(olasiliklar, marj). Eksik oran varsa (None, None)."""
    if not oranlar or any(o is None or o <= 1.0 for o in oranlar):
        return None, None
    ham = [1 / o for o in oranlar]
    t = sum(ham)
    return [h / t for h in ham], t - 1


def moneyline(ev: dict) -> dict | None:
    """ESPN olayindan DraftKings 1X2 olasiliklari."""
    o = (ev.get("odds") or {}).get("moneyline") or {}
    d = [amerikan_ondalik(o.get("home")), amerikan_ondalik(o.get("draw")),
         amerikan_ondalik(o.get("away"))]
    p, m = devig(d)
    if p is None:
        return None
    return {"p": p, "marj": m, "oran": d}


def toplam(ev: dict) -> dict | None:
    """Alt/Ust marketi (genellikle 2,5)."""
    t = (ev.get("odds") or {}).get("total") or {}
    ust, alt = t.get("over") or {}, t.get("under") or {}
    d = [amerikan_ondalik(alt.get("odds")), amerikan_ondalik(ust.get("odds"))]
    p, m = devig(d)
    if p is None:
        return None
    cizgi = (ev.get("odds") or {}).get("over_under")
    return {"p_alt": p[0], "p_ust": p[1], "marj": m, "cizgi": cizgi}
