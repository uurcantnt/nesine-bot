"""Canli mac durumu: skor + GERCEK dakika.

KAYNAK SECIMI (olculdu 2026-08-21):
  TheSportsDB  → skor ✓ · DAKIKA ✓ (`strProgress`) · devre ✓ (`strStatus`)
                 · Kolombiya 2. ligi / CONCACAF / Sudamericana gibi kucuk
                 turnuvalari da kapsiyor · TURKIYE'DEN CALISIYOR
  ESPN         → skor ✓ · dakika ✗ (baslangic saatinden TAHMIN gerekiyordu)
                 · yalnizca buyuk ligler · Turkiye'den 403
  Nesine       → skor ✗ dakika ✗ (bultende alan YOK, dogrulandi)
  Sofascore    → Turkiye'den 403

Bu yuzden birincil kaynak TheSportsDB. Korner/kart CANLI olarak HICBIRINDEN
gelmiyor (TheSportsDB'nin istatistik ucu ucretsiz katmanda bos donuyor).
"""
from __future__ import annotations

import json
import urllib.request

import stats

URL = "https://www.thesportsdb.com/api/v1/json/3/livescore.php?s=Soccer"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
GUVENLI_DAKIKA = 85      # bunun ustunde model kullanilmaz (hata payi sonucu belirler)


def _cek(timeout: int = 20) -> list:
    req = urllib.request.Request(URL, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    return d.get("livescore") or []


def _dakika(kayit: dict) -> int | None:
    """strProgress dakikayi verir; devre arasinda 'HT' gelebilir."""
    durum = str(kayit.get("strStatus") or "").upper()
    ham = str(kayit.get("strProgress") or "").strip()
    if durum in ("HT", "HALFTIME"):
        return 45
    if durum in ("FT", "AET", "PEN", "FINISHED"):
        return None
    try:
        return max(0, min(95, int(float(ham.replace("+", "").split(" ")[0]))))
    except (ValueError, TypeError):
        return None


def durumlar() -> dict:
    """{(sade_ev, sade_dep): {ev_skor, dep_skor, dakika, ...}}"""
    try:
        ham = _cek()
    except Exception as e:
        print(f"[canli durum] alinamadi: {e}")
        return {}
    out = {}
    for k in ham:
        h, a = k.get("strHomeTeam"), k.get("strAwayTeam")
        if not h or not a:
            continue
        dk = _dakika(k)
        try:
            es, ds = int(k.get("intHomeScore") or 0), int(k.get("intAwayScore") or 0)
        except (TypeError, ValueError):
            continue
        out[(stats.sadelestir(h), stats.sadelestir(a))] = {
            "ev_skor": es, "dep_skor": ds, "dakika": dk,
            "devre": k.get("strStatus"),
            "guvenli": dk is not None and dk <= GUVENLI_DAKIKA,
            "kaynak_ev": h, "kaynak_dep": a, "lig": k.get("strLeague"),
        }
    return out


def _benzerlik(a: str, b: str) -> float:
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def esle(durum: dict, nesine_ev: str, nesine_dep: str) -> dict | None:
    """Nesine takim adlariyla canli durumu eslestir.

    Isimler birebir tutmuyor ("Botafogo RJ" vs "Botafogo", "CS Cienciano" vs
    "Cienciano"); once icerme, sonra kelime ortusmesi denenir.
    """
    h = stats.sadelestir(stats.ELLE.get(nesine_ev.lower(), nesine_ev))
    a = stats.sadelestir(stats.ELLE.get(nesine_dep.lower(), nesine_dep))
    if (h, a) in durum:
        return durum[(h, a)]
    for (ih, ia), v in durum.items():
        if (h and ih and (h in ih or ih in h)) and (a and ia and (a in ia or ia in a)):
            return v
    en_iyi, en_skor = None, 0.0
    for (ih, ia), v in durum.items():
        s = (_benzerlik(h, ih) + _benzerlik(a, ia)) / 2
        if s > en_skor:
            en_iyi, en_skor = v, s
    return en_iyi if en_skor >= 0.5 else None
