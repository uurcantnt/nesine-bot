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
import subprocess
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


def cli(*args: str, timeout: int = 40) -> dict | None:
    """sports-skills CLI'ini calistir.

    Kendi HTTP kodumu yazmak yerine CLI kullaniliyor: ESPN'in arama ucu
    site.api.espn.com uzerinde ve dogrudan cagrilinca 403 donuyor; CLI'in
    kendi baslik/parametre duzeni calisiyor (runner'da dogrulandi).
    """
    try:
        r = subprocess.run(["sports-skills", *args], capture_output=True,
                           text=True, timeout=timeout)
    except Exception:
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def espn_ara(ad: str) -> dict | None:
    """Takimi ESPN'de ara. Donus: {"id":..., "ad":...} veya None."""
    sorgu = ELLE.get(ad.strip().lower(), ad)
    d = cli("football", "search_team", f"--query={sorgu}")
    if not d or not d.get("status"):
        return None
    hedef = sadelestir(sorgu)
    adaylar = (d.get("data") or {}).get("results") or []
    # once tam eslesme, sonra icerme
    for kesin in (True, False):
        for it in adaylar:
            tk = it.get("team") or it
            isim = tk.get("name") or tk.get("short_name") or ""
            if not isim:
                continue
            n = sadelestir(isim)
            if (n == hedef) if kesin else (hedef in n or n in hedef):
                return {"id": str(tk.get("id")), "ad": isim,
                        "lig": (it.get("league") or {}).get("slug")}
    return None
