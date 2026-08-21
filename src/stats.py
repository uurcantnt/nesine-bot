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
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    # BAGLAC KELIMELERI AT (2026-08-21, kullanici bildirdi):
    # Nesine "Académica de Coimbra" derken Sofascore "Académica Coimbra"
    # diyor. Eslestirici alt-dize kullandigi icin aradaki "de" yuzunden
    # ikisi de birbirini ICERMIYOR ve eslesme SESSIZCE dusuyordu.
    # Ayni sorun: "Union de Santa Fe"/"Union Santa Fe",
    # "Deportivo La Coruña"/"Deportivo Coruna".
    # Bu fonksiyon 6 ayri eslestirici tarafindan kullaniliyor (fotmob,
    # sofascore, canli_durum, fikstur, istatistik_topla, ornek) --
    # duzeltme hepsine birden gecerli.
    s = re.sub(r"\b(de|da|do|del|dos|das|di|du|la|le|les|el|of|the|and|ve|en)\b",
               " ", s)
    return re.sub(r"\s+", " ", s).strip()


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


def esle(idx: dict, ev: str, dep: str):
    """(sade_ev, sade_dep) anahtarli sozlukte maci bul. Yoksa None.

    2026-08-21'e kadar bu mantik ALTI ayri dosyada birebir kopyalanmisti
    (fotmob, sofascore, canli_durum, fikstur, istatistik_topla, ornek).
    Tek yere alindi.

    IKI KADEME:
      1. TAM eslesme (sadelestirilmis isimler birebir)
      2. ALT-DIZE eslesmesi — ama ILK bulunani degil, EN IYIsini secer.

    "En iyi" NEDEN onemli: alt-dize kurali farkli kulupleri eslestirebilir.
    Ornek: "Estudiantes" ile "Estudiantes de Rio Cuarto" AYRI kuluplerdir
    ama biri digerini icerir. Onceden dongude ILK rastlanan donuyordu, yani
    hangi kulubun geldigi sozlugun sirasina kaliyordu. Artik uzunluk farki
    EN KUCUK olan secilir; birebir ayni isim varsa o kazanir.

    Yanlis eslesme HATA FIRLATMAZ, sessizce yanlis istatistik uretir --
    bu yuzden en iyi adayi secmek onemli.
    """
    h = sadelestir(ELLE.get((ev or "").lower(), ev or ""))
    a = sadelestir(ELLE.get((dep or "").lower(), dep or ""))
    if not h or not a:
        return None
    if (h, a) in idx:
        return idx[(h, a)]
    en_iyi, en_fark = None, None
    for (ih, ia), v in idx.items():
        if not (ih and ia):
            continue
        if (h in ih or ih in h) and (a in ia or ia in a):
            fark = abs(len(ih) - len(h)) + abs(len(ia) - len(a))
            if en_fark is None or fark < en_fark:
                en_iyi, en_fark = v, fark
    if en_iyi is not None:
        return en_iyi
    # 3. KADEME: kelime ortusmesi (fotmob.esle ve canli_durum.esle'de zaten
    # vardi, sofascore.esle'de YOKTU). Esik 0,5 -- ayni kaynaklardaki deger.
    def _ort(x, y):
        sx, sy = set(x.split()), set(y.split())
        return len(sx & sy) / max(1, min(len(sx), len(sy)))
    en_iyi, en_skor = None, 0.0
    for (ih, ia), v in idx.items():
        sk = (_ort(h, ih) + _ort(a, ia)) / 2
        if sk > en_skor:
            en_iyi, en_skor = v, sk
    return en_iyi if en_skor >= 0.5 else None
