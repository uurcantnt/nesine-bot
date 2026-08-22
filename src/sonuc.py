"""Mac sonuclarini cek ve bahsin TUTUP TUTMADIGINI belirle.

Bu modul olmadan bot kendini degerlendiremez: "model %74 dedi" cumlesinin
dogru olup olmadigi ancak sonuclar bilinince olculur.

KAYNAK: Fotmob matchDetails — skor, ILK YARI skoru (HT olayi), korner
(tam/1.yari/2.yari), sari ve kirmizi kart. Tek cagrida hepsi geliyor.
"""
from __future__ import annotations

import json
import math
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
DETAY = "https://www.fotmob.com/api/data/matchDetails?matchId={}"


def _get(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _donem_stat(per: dict, donem: str) -> dict:
    out = {}
    for g in ((per.get(donem) or {}).get("stats") or []):
        for it in (g.get("stats") or []):
            ad = str(it.get("title") or "").lower()
            v = it.get("stats")
            if not isinstance(v, list) or len(v) != 2 or None in v:
                continue
            if ad == "corners":
                out["korner"] = v
            elif ad == "yellow cards":
                out["sari"] = v
            elif ad == "red cards":
                out["kirmizi"] = v
    return out


def mac_sonucu(fotmob_id) -> dict | None:
    """Bitmis macin tum sonuc verisi. Mac bitmemisse None."""
    try:
        d = _get(DETAY.format(fotmob_id))
    except Exception as e:
        print(f"[sonuc] {fotmob_id}: {e}")
        return None
    h = d.get("header") or {}
    st = h.get("status") or {}
    if not st.get("finished"):
        return None
    takimlar = h.get("teams") or []
    if len(takimlar) != 2:
        return None
    try:
        ev_gol = int(takimlar[0].get("score"))
        dep_gol = int(takimlar[1].get("score"))
    except (TypeError, ValueError):
        return None

    # ilk yari skoru: olay akisindaki HT isareti
    iy_ev = iy_dep = None
    mf = (d.get("content") or {}).get("matchFacts") or {}
    ev_list = mf.get("events") or {}
    lst = ev_list.get("events") if isinstance(ev_list, dict) else ev_list
    if isinstance(lst, list):
        for x in lst:
            if str(x.get("halfStrShort") or "").upper() == "HT":
                iy_ev, iy_dep = x.get("homeScore"), x.get("awayScore")
                break
        if iy_ev is None:      # yedek: 45. dakikaya kadarki goller
            iy_ev = iy_dep = 0
            for x in lst:
                if "goal" not in str(x.get("type") or "").lower():
                    continue
                try:
                    dk = int(x.get("time") or 0)
                except (TypeError, ValueError):
                    continue
                if dk <= 45:
                    if x.get("isHome"):
                        iy_ev += 1
                    else:
                        iy_dep += 1

    per = ((d.get("content") or {}).get("stats") or {}).get("Periods") or {}
    tam, ilk = _donem_stat(per, "All"), _donem_stat(per, "FirstHalf")
    return {
        "ev_gol": ev_gol, "dep_gol": dep_gol,
        "iy_ev": iy_ev, "iy_dep": iy_dep,
        "korner": sum(tam["korner"]) if tam.get("korner") else None,
        "iy_korner": sum(ilk["korner"]) if ilk.get("korner") else None,
        # TAKIM AYRIMI: toplam tek basina "kornerin kacini BIZ yaptik"
        # sorusunu cevaplayamiyor. Ham veri zaten [ev, dep] cifti; toplama
        # indirgemek bilgiyi ATIYORDU (kullanici sordu, 2026-08-22).
        "korner_cift": tam.get("korner"),
        "iy_korner_cift": ilk.get("korner"),
        "sari": sum(tam["sari"]) if tam.get("sari") else None,
        "kirmizi": sum(tam["kirmizi"]) if tam.get("kirmizi") else None,
        "iy_sari": sum(ilk["sari"]) if ilk.get("sari") else None,
    }


def degerlendir(mtid: int, idx: int, sov, s: dict) -> bool | None:
    """Bahis tuttu mu? True/False, belirlenemiyorsa None.

    Canli MTID'ler mac oncesi karsiliklarina esitlenir (53→1, 67→12 gibi):
    sonuc acisindan ayni bahistir.
    """
    if not s:
        return None
    e, d = s["ev_gol"], s["dep_gol"]
    t = e + d
    v = None if sov is None else float(sov)
    # canli -> mac oncesi esleme
    canli = {53: 1, 55: 3, 287: 38, 109: 49, 66: 11, 67: 12, 68: 13,
             61: 7, 217: 216, 219: 218, 605: 301, 60: 268, 86: 29, 257: 256}
    mtid = canli.get(mtid, mtid)

    if mtid == 1:                                   # Mac Sonucu
        return [e > d, e == d, e < d][idx]
    if mtid == 3:                                   # Cifte Sans
        return [e >= d, e != d, e <= d][idx]
    if mtid == 38:                                  # Karsilikli Gol
        var = e >= 1 and d >= 1
        return [var, not var][idx]
    if mtid == 49:                                  # Tek/Cift
        return [t % 2 == 1, t % 2 == 0][idx]
    if mtid in (11, 12, 13) and v is not None:      # Gol Alt/Ust
        return [t < v, t > v][idx]
    if mtid == 43:                                  # Toplam Gol Araligi
        return [t <= 1, 2 <= t <= 3, 4 <= t <= 5, t >= 6][idx]
    if mtid == 268 and v is not None:               # Handikapli MS
        f = (e + v) - d
        return [f > 0, abs(f) < 1e-9, f < 0][idx]
    if mtid in (20, 455) and v is not None:         # Ev Sahibi Gol A/U
        return [e < v, e > v][idx]
    if mtid in (29, 256, 457) and v is not None:    # Deplasman Gol A/U
        return [d < v, d > v][idx]
    # ── ilk yari ──
    if s.get("iy_ev") is None:
        pass
    else:
        ie, idp = s["iy_ev"], s["iy_dep"]
        it = ie + idp
        if mtid == 7:
            return [ie > idp, ie == idp, ie < idp][idx]
        if mtid == 8:
            return [ie >= idp, ie != idp, ie <= idp][idx]
        if mtid in (14, 209, 15) and v is not None:
            return [it < v, it > v][idx]
        if mtid == 452:
            var = ie >= 1 and idp >= 1
            return [var, not var][idx]
        if mtid == 450:
            return [it % 2 == 1, it % 2 == 0][idx]
    # ── korner / kart ──
    if mtid == 216 and v is not None and s.get("korner") is not None:
        return [s["korner"] < v, s["korner"] > v][idx]
    if mtid == 218 and v is not None and s.get("iy_korner") is not None:
        return [s["iy_korner"] < v, s["iy_korner"] > v][idx]
    if mtid == 299 and s.get("korner") is not None:
        return [s["korner"] % 2 == 1, s["korner"] % 2 == 0][idx]
    if mtid == 301 and v is not None and s.get("sari") is not None:
        puan = s["sari"] + 2 * (s.get("kirmizi") or 0)
        return [puan < v, puan > v][idx]
    return None
