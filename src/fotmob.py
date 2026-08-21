"""Canli mac verisi: skor, dakika, KORNER ve KART — Fotmob.

NEDEN FOTMOB (2026-08-21 taramasi):
  Fotmob       → skor ✓ dakika ✓ KORNER ✓ KART ✓ sut ✓ ilk yari ayrimi ✓
                 · anahtar GEREKMEZ · Turkiye'den ACIK
  TheSportsDB  → skor ✓ dakika ✓ · korner ✗ (ucretsiz katmanda kapali)
  ESPN         → skor ✓ dakika ✗ · Turkiye'den 403
  Sofascore    → Turkiye'den DE runner'dan DA 403 (veri merkezi IP'leri engelli)
  api-sports   → anahtar ister · Nesine/livescore.com/flashscore → istatistik yok

Yani canli korner/kart icin BULUNAN TEK anahtarsiz kaynak Fotmob.
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone

import stats

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
LISTE = "https://www.fotmob.com/api/data/matches?date={}"
DETAY = "https://www.fotmob.com/api/data/matchDetails?matchId={}"


def _get(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _dakika(m: dict) -> int | None:
    st = (m.get("status") or {})
    kisa = ((st.get("liveTime") or {}).get("short") or "")
    n = re.sub(r"\D", "", kisa)
    if not n:
        return 45 if "HT" in str(st.get("reason", {}).get("short", "")).upper() else None
    try:
        return max(0, min(95, int(n)))
    except ValueError:
        return None


def canli_maclar(gun_kaydir: int = 0) -> list:
    """Su an oynanan maclar (skor + dakika)."""
    t = datetime.now(timezone.utc)
    if gun_kaydir:
        from datetime import timedelta
        t = t + timedelta(days=gun_kaydir)
    try:
        d = _get(LISTE.format(t.strftime("%Y%m%d")))
    except Exception as e:
        print(f"[fotmob] liste alinamadi: {e}")
        return []
    out = []
    for L in d.get("leagues") or []:
        for m in L.get("matches") or []:
            st = m.get("status") or {}
            if not st.get("started") or st.get("finished"):
                continue
            out.append({
                "id": m.get("id"), "lig": L.get("name"),
                "ev": (m.get("home") or {}).get("name"),
                "dep": (m.get("away") or {}).get("name"),
                "ev_skor": (m.get("home") or {}).get("score"),
                "dep_skor": (m.get("away") or {}).get("score"),
                "dakika": _dakika(m),
            })
    return out


def istatistik(mac_id) -> dict | None:
    """Bir canli macin KORNER/KART/SUT istatistigi. [ev, dep] cifti doner."""
    try:
        d = _get(DETAY.format(mac_id))
    except Exception as e:
        print(f"[fotmob] detay alinamadi ({mac_id}): {e}")
        return None
    per = ((d.get("content") or {}).get("stats") or {}).get("Periods") or {}
    out: dict = {}
    for donem, anahtar in (("All", "tam"), ("FirstHalf", "ilk_yari")):
        blok = per.get(donem) or {}
        bul: dict = {}
        for grup in (blok.get("stats") or []):
            for it in (grup.get("stats") or []):
                ad = str(it.get("title") or "").lower()
                deger = it.get("stats")
                if not isinstance(deger, list) or len(deger) != 2:
                    continue
                if None in deger:
                    continue
                if ad == "corners":
                    bul["korner"] = deger
                elif ad == "yellow cards":
                    bul["sari"] = deger
                elif ad == "red cards":
                    bul["kirmizi"] = deger
                elif ad == "shots on target":
                    bul["isabetli_sut"] = deger
                elif ad == "ball possession":
                    bul["topla_oynama"] = deger
        if bul:
            out[anahtar] = bul
    return out or None


def esle(maclar: list, nesine_ev: str, nesine_dep: str) -> dict | None:
    """Nesine takim adlariyla Fotmob macini eslestir."""
    h = stats.sadelestir(stats.ELLE.get(nesine_ev.lower(), nesine_ev))
    a = stats.sadelestir(stats.ELLE.get(nesine_dep.lower(), nesine_dep))
    en_iyi, en_skor = None, 0.0
    for m in maclar:
        ih, ia = stats.sadelestir(m["ev"] or ""), stats.sadelestir(m["dep"] or "")
        if (h and ih and (h in ih or ih in h)) and (a and ia and (a in ia or ia in a)):
            return m
        ort = lambda x, y: (len(set(x.split()) & set(y.split()))
                            / max(1, min(len(x.split()), len(y.split()))))
        s = (ort(h, ih) + ort(a, ia)) / 2
        if s > en_skor:
            en_iyi, en_skor = m, s
    return en_iyi if en_skor >= 0.5 else None
