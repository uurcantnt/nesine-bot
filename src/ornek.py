"""Olculebilir ORNEKLEM: arsivdeki oranlar + gerceklesmis sonuclar.

geriye_donuk.py ve walkforward.py AYNI ornegi kullanir; burada tek yerde
uretilir (daha once geriye_donuk icinde gomuluydu).

ONEMLI YAPI FARKI: kayitlar MAC bazinda gruplanir. Nedeni konsul bulgusu --
198 secim 43 MACTAN geliyor ve ayni macin secenekleri MEKANIK OLARAK
bagimlidir (1X2'nin uc secenegi toplami 1'dir). Secim bazinda onyukleme
yapmak guven araligini SAHTE OLARAK DARALTIR. Mac bazinda gruplayarak
kumelenmis (clustered) onyukleme mumkun oluyor.
"""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import bulletin
import fotmob
import odds as O
import sonuc as S
import stats as ST

DATA = Path(__file__).resolve().parent.parent / "data"


def _bitmis_maclar() -> dict:
    """Fotmob'un dun+bugun BITMIS maclari -> (ev, dep) -> id."""
    bitmis = {}
    for gk in (0, -1):
        try:
            gun = (bulletin.datetime.now(bulletin.timezone.utc)
                   + timedelta(days=gk)).strftime("%Y%m%d")
            d = fotmob._get(fotmob.LISTE.format(gun))
        except Exception:
            continue
        for L in d.get("leagues") or []:
            for m in L.get("matches") or []:
                if not (m.get("status") or {}).get("finished"):
                    continue
                h = (m.get("home") or {}).get("name")
                a = (m.get("away") or {}).get("name")
                if h and a:
                    bitmis[(ST.sadelestir(h), ST.sadelestir(a))] = {
                        "id": m.get("id"),
                        "ev_id": str((m.get("home") or {}).get("id")),
                        "dep_id": str((m.get("away") or {}).get("id"))}
    return bitmis


def topla(en_fazla: int = 60, sessiz: bool = False) -> tuple[list, dict]:
    """(mac_kayitlari, istatistik_onbellegi).

    Her mac kaydi:
      {"mac": "A - B", "fm_id":.., "sonuc": {...},
       "ist_ev": {...}, "ist_dep": {...},
       "secimler": [{"mtid","idx","sov","nesine","oran","tuttu"}, ...]}
    Model olasiligi BURADA hesaplanMAZ -- cagiran taraf istedigi parametreyle
    hesaplar (walkforward icin sart).
    """
    ist = json.loads((DATA / "istatistik.json").read_text(encoding="utf-8"))
    dosyalar = sorted(bulletin.ARSIV.glob("*/*.json.gz"))
    tam = [f for f in dosyalar if bulletin.load(f).get("tam")]
    if not tam:
        if not sessiz:
            print("arsivde tam snapshot yok")
        return [], ist
    snap = bulletin.load(tam[0])
    if not sessiz:
        print(f"arsiv: {tam[0].parent.name}/{tam[0].name} · {len(snap['olay'])} mac")

    bitmis = _bitmis_maclar()
    if not sessiz:
        print(f"fotmob bitmis mac: {len(bitmis)}")

    def bul(ev, dep):
        h = ST.sadelestir(ST.ELLE.get(ev.lower(), ev))
        a = ST.sadelestir(ST.ELLE.get(dep.lower(), dep))
        if (h, a) in bitmis:
            return bitmis[(h, a)]
        for (ih, ia), v in bitmis.items():
            if (h and ih and (h in ih or ih in h)) and (a and ia and (a in ia or ia in a)):
                return v
        return None

    maclar, bakilan, denendi = [], 0, set()
    for e in snap["olay"]:
        if bakilan >= en_fazla:
            break
        fm = bul(e.get("ev") or "", e.get("dep") or "")
        if not fm:
            continue
        s = S.mac_sonucu(fm["id"])
        if not s:
            continue
        bakilan += 1
        for tid in (fm["ev_id"], fm["dep_id"]):
            if ist.get(tid) is None and tid not in denendi:
                denendi.add(tid)
                v = fotmob.takim_verisi(tid)
                if v:
                    ist[tid] = v
        secimler = []
        for mtid_s, m in e["m"].items():
            mtid = int(mtid_s)
            o = m.get("o") or []
            if m.get("ms") != 1 or any(x is None or x <= 1 for x in o):
                continue
            p = O.devig(o, 2 if mtid in (3, 8) else 1)
            if not p:
                continue
            for i in range(len(o)):
                r = S.degerlendir(mtid, i, m.get("sov"), s)
                if r is None:
                    continue
                secimler.append({"mtid": mtid, "idx": i, "sov": m.get("sov"),
                                 "nesine": p[i], "oran": o[i], "tuttu": bool(r)})
        if not secimler:
            continue
        maclar.append({"mac": f"{e.get('ev')} - {e.get('dep')}",
                       "fm_id": fm["id"], "sonuc": s,
                       "ist_ev": ist.get(fm["ev_id"]),
                       "ist_dep": ist.get(fm["dep_id"]),
                       "secimler": secimler})
    if not sessiz:
        print(f"degerlendirilen mac {len(maclar)} · "
              f"secim {sum(len(m['secimler']) for m in maclar)}")
    return maclar, ist
