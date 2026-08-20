"""Dis istatistik verisi (ESPN) ile Nesine maclarini eslestirme.

NEDEN AYRI KATMAN: Nesine bulteninde takim adlari Turkce/kisaltilmis
("B. Dortmund", "Bayern Münih"), ESPN'de ingilizce tam ad. Eslestirme
yapilmadan hicbir istatistik kullanilamaz.

NEREDE CALISIR: ESPN Turkiye'den 403/timeout veriyor; GitHub Actions
runner'larindan (ABD) 200 donuyor. Bu yuzden istatistik katmani YALNIZCA
Actions'ta calisir, yerelde calismaz.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
ARA = "https://site.web.api.espn.com/apis/common/v3/search"

# Nesine kisaltmalari -> ESPN'in kullandigi ad. Elle dogrulanmis liste;
# tahmin YOK, her satir tek tek kontrol edildi.
ELLE = {
    "b. dortmund": "Borussia Dortmund",
    "bayern münih": "Bayern Munich",
    "m. united": "Manchester United",
    "m. city": "Manchester City",
    "a. madrid": "Atletico Madrid",
    "r. madrid": "Real Madrid",
    "i. milan": "Inter Milan",
    "psg": "Paris Saint-Germain",
    "b. leverkusen": "Bayer Leverkusen",
    "e. frankfurt": "Eintracht Frankfurt",
    "rb leipzig": "RB Leipzig",
    "w. bremen": "Werder Bremen",
    "g. saray": "Galatasaray",
    "f. bahçe": "Fenerbahce",
    "fenerbahçe": "Fenerbahce",
    "beşiktaş": "Besiktas",
    "trabzonspor": "Trabzonspor",
    "başakşehir": "Istanbul Basaksehir",
}


def sadelestir(ad: str) -> str:
    """Turkce karakterleri ve gurultuyu at, karsilastirilabilir hale getir."""
    s = unicodedata.normalize("NFKD", ad.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    for a, b in (("ı", "i"), ("ş", "s"), ("ğ", "g"), ("ç", "c"),
                 ("ö", "o"), ("ü", "u")):
        s = s.replace(a, b)
    s = re.sub(r"\b(fc|sk|ac|as|cf|sc|fk|cd|afc|u23|u21|ii|b)\b", " ", s)
    return re.sub(r"[^a-z0-9 ]", " ", s).strip()


def _get(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def espn_ara(ad: str) -> dict | None:
    """Takimi ESPN'de ara. Donus: {"id":..., "ad":...} veya None."""
    sorgu = ELLE.get(ad.strip().lower(), ad)
    url = f"{ARA}?query={urllib.parse.quote(sorgu)}&limit=8&sport=soccer"
    try:
        d = _get(url)
    except Exception:
        return None
    hedef = sadelestir(sorgu)
    for grup in d.get("results", []):
        if grup.get("type") != "team":
            continue
        for it in grup.get("contents", []):
            isim = it.get("displayName") or ""
            if not isim:
                continue
            n = sadelestir(isim)
            if n == hedef or hedef in n or n in hedef:
                m = re.search(r"/id/(\d+)", it.get("link", {}).get("web", "") or "")
                uid = it.get("id") or (m.group(1) if m else None)
                if uid:
                    return {"id": str(uid), "ad": isim}
    return None
