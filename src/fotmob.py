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


# ─────────────────── MAC ONCESI: FIKSTUR + TAKIM VERISI ───────────────────

TAKIM = "https://www.fotmob.com/api/data/teams?id={}"
SON_MAC = 12
HAZIRLIK = ("friendl", "hazırlık", "hazirlik")   # hazirlik maclari ELENIR


def fikstur_indeks(gunler: int = 3) -> dict:
    """{(ev_sade, dep_sade): mac} — Fotmob gunluk fiksturu.

    OLCULDU: Fotmob 3 gunde 1275 mac / 162 lig veriyor; ESPN 101 mac.
    Nesine'nin 964 macindan 642'si (%66,6) Fotmob'da, ESPN'de 89 (%9,2).
    """
    from datetime import timedelta
    ix = {}
    bugun = datetime.now(timezone.utc)
    for i in range(gunler):
        gun = (bugun + timedelta(days=i)).strftime("%Y%m%d")
        try:
            d = _get(LISTE.format(gun))
        except Exception as e:
            print(f"[fotmob] fikstur {gun}: {e}")
            continue
        n = 0
        for L in d.get("leagues") or []:
            for m in L.get("matches") or []:
                h = (m.get("home") or {}).get("name")
                a = (m.get("away") or {}).get("name")
                if not h or not a:
                    continue
                ix[(stats.sadelestir(h), stats.sadelestir(a))] = {
                    "id": m.get("id"), "lig": L.get("name"), "ev": h, "dep": a,
                    "ev_id": (m.get("home") or {}).get("id"),
                    "dep_id": (m.get("away") or {}).get("id"),
                    "ts": (m.get("status") or {}).get("utcTime"),
                }
                n += 1
        print(f"[fotmob] {gun}: {n} mac")
    return ix


def _sezon_stat(veri: dict) -> dict:
    """stats.teams -> {korner, sari, xg, xg_yenilen, gol, gol_yenilen}"""
    esle = {
        "corners": "korner", "yellow cards": "sari",
        "expected goals": "xg", "xg conceded": "xg_yenilen",
        "goals per match": "gol_sezon", "goals conceded per match": "gol_ye_sezon",
        "average possession": "topla_oynama", "fouls per match": "faul",
        "shots on target per match": "isabetli_sut",
    }
    out = {}
    for x in ((veri.get("stats") or {}).get("teams") or []):
        ad = str(x.get("header") or "").strip().lower()
        if ad in esle:
            v = (x.get("participant") or {}).get("value")
            if isinstance(v, (int, float)):
                out[esle[ad]] = float(v)
    return out


def takim_verisi(takim_id) -> dict | None:
    """Tek cagriyla takimin gecmisi + sezon ortalamalari.

    ESPN'de her mac icin ayri istatistik cagrisi gerekiyordu (takim basina
    ~10 istek). Fotmob tek cagrida hem 43 maclik fiksturu hem sezon
    ortalamalarini (korner, kart, xG) veriyor.
    """
    try:
        d = _get(TAKIM.format(takim_id))
    except Exception as e:
        print(f"[fotmob] takim {takim_id}: {e}")
        return None
    fs = ((d.get("fixtures") or {}).get("allFixtures") or {}).get("fixtures") or []
    maclar = []
    for m in fs:
        st = m.get("status") or {}
        if not st.get("finished"):
            continue
        turnuva = str((m.get("tournament") or {}).get("name") or "").lower()
        if any(h in turnuva for h in HAZIRLIK):
            continue                      # hazirlik maci: sonuc gurultu
        skor = str(st.get("scoreStr") or "")
        if " - " not in skor:
            continue
        try:
            a, b = (int(x) for x in skor.split(" - "))
        except ValueError:
            continue
        evde = str(((m.get("home") or {}).get("id"))) == str(takim_id)
        maclar.append({"at": a if evde else b, "ye": b if evde else a,
                       "ev": evde, "t": (st.get("utcTime") or "")[:10],
                       "rakip": str((m.get("opponent") or {}).get("id") or ""),
                       "lig": (m.get("tournament") or {}).get("name")})
    maclar.sort(key=lambda x: x["t"], reverse=True)
    maclar = maclar[:SON_MAC]
    if not maclar:
        return None
    n = len(maclar)
    ic = [m for m in maclar if m["ev"]]
    dis = [m for m in maclar if not m["ev"]]
    ort = lambda L, k: (sum(x[k] for x in L) / len(L)) if L else None
    sezon = _sezon_stat(d)
    return {
        "ad": ((d.get("details") or {}).get("name")
               or (d.get("details") or {}).get("shortName")),
        "mac": n, "maclar": maclar,
        "gol_at": sum(m["at"] for m in maclar) / n,
        "gol_ye": sum(m["ye"] for m in maclar) / n,
        "ic_at": ort(ic, "at"), "ic_ye": ort(ic, "ye"), "ic_n": len(ic),
        "dis_at": ort(dis, "at"), "dis_ye": ort(dis, "ye"), "dis_n": len(dis),
        "korner": sezon.get("korner"), "korner_n": n if sezon.get("korner") else 0,
        "sari": sezon.get("sari"), "kirmizi": 0.0,
        "kart_n": n if sezon.get("sari") else 0,
        "xg": sezon.get("xg"), "xg_yenilen": sezon.get("xg_yenilen"),
        "topla_oynama": sezon.get("topla_oynama"),
        "isabetli_sut": sezon.get("isabetli_sut"),
        "kaynak": "fotmob",
        "guncelleme": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
