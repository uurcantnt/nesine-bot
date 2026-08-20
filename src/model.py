"""Kendi olasilik tahminimiz — ESPN istatistiklerinden Poisson modeli.

NE YAPAR: takimlarin son 10 macindaki gol/korner/kart ortalamalarindan
bu macin beklenen degerlerini (lambda) cikarir, Poisson dagilimiyla
market olasiliklarini hesaplar.

NE YAPMAZ: sakatlik, kadro, motivasyon, hava, hakem, saha zemini... Bunlarin
hicbiri hesaba girmiyor. Model BASIT ve bunu gizlemiyoruz.

VARSAYIMLAR (olculmedi, literaturdeki standart degerler):
  EV_AVANTAJI = 1.15  -- ev sahibi gol beklentisi carpani
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
DEP_CARPANI = 0.90
MAKS_GOL = 10
MAKS_KORNER = 30


def pois(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return exp(-lam) * lam ** k / factorial(k)


def gol_lambdalari(ev: dict, dep: dict) -> tuple:
    """(ev_lambda, dep_lambda) — hucum ve savunma ortalamalarinin ortasi."""
    le = (ev["gol_at"] + dep["gol_ye"]) / 2 * EV_AVANTAJI
    ld = (dep["gol_at"] + ev["gol_ye"]) / 2 * DEP_CARPANI
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


def tahmin(ev: dict, dep: dict) -> dict:
    """Bir mac icin tum model ciktisi. Eksik veri varsa o bolum None."""
    out: dict = {"kaynak": {"ev_mac": ev.get("mac"), "dep_mac": dep.get("mac")}}
    le, ld = gol_lambdalari(ev, dep)
    out["gol"] = gol_olasiliklari(le, ld)
    if ev.get("korner") is not None and dep.get("korner") is not None:
        out["korner"] = sayac_olasiliklari(ev["korner"] + dep["korner"])
    if ev.get("sari") is not None and dep.get("sari") is not None:
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
    if mtid == 216 and s is not None and t.get("korner"):     # Korner Alt/Ust
        u = t["korner"]["ust"](s)
        return [1 - u, u][idx]
    if mtid == 299 and t.get("korner"):                       # Korner Tek/Cift
        return [t["korner"]["tek"], 1 - t["korner"]["tek"]][idx]
    if mtid == 301 and s is not None and t.get("kart"):       # Kart Puani Alt/Ust
        # SOV kart PUANI cinsinden (or. 4.5); model sari sayisi uzerinden
        u = t["kart"]["ust"](s)
        return [1 - u, u][idx]
    return None
