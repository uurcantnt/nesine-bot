"""VERI KAYNAGI SONDASI — hangi kaynak NEREDEN calisiyor.

NEDEN: bazi kaynaklar TURKIYE'den 403 doner ama GitHub Actions'tan (ABD/
Azure IP) calisir. ESPN'de bu tam olarak boyle oldu: TR'den 403, Actions'tan
sorunsuz. Ayni desen Sofascore'da da olabilir -- Sofascore'un alt lig
kapsamasi ve CANLI KORNER/KART verisi Fotmob'dan genis.

Bu betik hicbir sey degistirmez, yalnizca OLCER. Hem yerelde hem Actions'ta
calistirilip ciktilari kiyaslanir.

KULLANIM:  python kaynak_sonda.py
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# (ad, url, json_mu)
HEDEFLER = [
    ("sofascore-canli",
     "https://api.sofascore.com/api/v1/sport/football/events/live", True),
    ("sofascore-web",
     "https://www.sofascore.com/api/v1/sport/football/events/live", True),
    ("fotmob-liste",
     "https://www.fotmob.com/api/data/matches?date=20260821", True),
    ("thesportsdb-canli",
     "https://www.thesportsdb.com/api/v1/json/3/livescore.php?s=Soccer", True),
    ("iddaa-program",
     "https://sportsbookv2.iddaa.com/sportsbook/events?st=1&type=0&version=0", True),
    ("worldfootball", "https://www.worldfootball.net/", False),
    ("soccerstats", "https://www.soccerstats.com/", False),
    ("globalsportsarchive", "https://www.globalsportsarchive.com/", False),
    ("espn-program",
     "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard", True),
]


def dene(ad: str, url: str, json_mu: bool) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json,text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            b = r.read()
            out = {"ad": ad, "kod": r.status, "boyut": len(b)}
            if json_mu:
                try:
                    d = json.loads(b)
                    out["ozet"] = (f"{len(d)} anahtar" if isinstance(d, dict)
                                   else f"{len(d)} kayit")
                    if isinstance(d, dict) and "events" in d:
                        out["olay"] = len(d["events"] or [])
                except Exception:
                    out["ozet"] = "JSON degil"
            return out
    except urllib.error.HTTPError as e:
        return {"ad": ad, "kod": e.code, "boyut": 0}
    except Exception as e:
        return {"ad": ad, "kod": None, "hata": str(e)[:60]}


def calis():
    nerede = "GITHUB ACTIONS" if os.environ.get("CI") else "YEREL (Turkiye)"
    print(f"KAYNAK SONDASI — konum: {nerede}\n")
    print(f"{'kaynak':<22} {'kod':>5} {'boyut':>10}  not")
    print("-" * 62)
    for ad, url, jm in HEDEFLER:
        r = dene(ad, url, jm)
        kod = r.get("kod")
        isaret = "OK " if kod == 200 else ("BLK" if kod in (403, 451) else "   ")
        ek = r.get("hata") or r.get("ozet") or ""
        if r.get("olay") is not None:
            ek = f"{r['olay']} olay · {ek}"
        print(f"{isaret} {ad:<19} {str(kod):>5} {r.get('boyut',0):>10}  {ek}")


if __name__ == "__main__":
    calis()
