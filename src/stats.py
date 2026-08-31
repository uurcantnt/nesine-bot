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
    # 2026-08-31: 3. kademe (kelime ortusmesi) sikilastirilinca bu adlar
    # ARTIK tahminle baglanamiyor -- ortusen kelime YOK. Tahmin ettirmek
    # yerine ELLE yazildi; her biri tek tek dogrulandi.
    "kopenhag": "FC Copenhagen",
    "vaasan ps": "VPS",
    "tampereen i.": "Ilves",
    "amed sportif": "Amedspor",
    "kuopion": "KuPS",
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
    sv = seviye(ad)
    if sv == "kad":
        s = re.sub(r"\b(k|w)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # SEVIYE JETONU SONA EKLENIR (2026-08-31). Onceden "u21"/"b"/"ii"
    # tamamen ATILIYORDU: "Arsenal U21" ile "Arsenal" ayni dizeye dusuyor
    # ve esle() bunlari BIREBIR eslestiriyordu. 391 macliK bultende 8
    # boyle cakisma olculdu (Arsenal U21 / Derby County U21 / Celta Vigo B
    # ...). Genc takim macina A takimi istatistigi baglanmasi HATA
    # FIRLATMAZ, sessizce yanlis tahmin uretir.
    # Jeton SONA konur, TABAN ad degismez -- boylece alt-dize eslesmesi
    # ("brighton" ⊂ "brighton hove albion") calismaya devam eder;
    # esle() tabani ve seviyeyi AYRI karsilastirir.
    return f"{s} {sv}".strip() if sv else s


# Seviye isaretleri. Jeton olarak sadelestir() ciktisinin SONUNA eklenir.
# 3. kademe (kelime ortusmesi) esikleri.
ESIK_TARAF = 0.34   # HER IKI tarafin ayri ayri gecmesi gereken en az ortusme
ESIK_ORT = 0.50     # iki tarafin ortalamasi
AYIRT = 0.001       # en iyi aday, ikinciyi bu kadar GECMELI; yoksa belirsiz

SEVIYE_JETON = {"kad", "rez", "u15", "u16", "u17", "u18", "u19",
                "u20", "u21", "u22", "u23"}

_KADIN = re.compile(r"\((k|w)\)|\b(kadin|kadinlar|women|femenino|feminin|"
                    r"feminile|frauen|damen|dames)\b")
_YAS = re.compile(r"\bu\s?(1[5-9]|2[0-3])\b|\b(?:under|sub)\s?(1[5-9]|2[0-3])\b")
# REZERV: "ii"/"iii" nerede olursa olsun; "b"/"2" YALNIZCA SON jetonken.
# "c" KASITLI YOK: Nesine "Chelmsford C." (City) / "Haverfordwest C."
# (County) diye yaziyor -- rezerv sanip eslesmeyi kaybederdik.
# "b" bas jetonken de alinmaz: "B. Dortmund", "B. Münih" kulup kisaltmasi.
_REZ = re.compile(r"\b(?:ii|iii|castilla|reserves?|rezerv|academy|akademi|"
                  r"youth|genclik)\b|\s(?:b|2)\s*$")


def seviye(ad: str) -> str:
    """Takimin SEVIYESI: '' (A takimi) | 'kad' | 'rez' | 'u21' ...

    RAW isimden okunur, cunku sadelestir() bu isaretleri temizler.
    """
    t = unicodedata.normalize("NFKD", (ad or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    for a, b in (("\u0131", "i"), ("\u015f", "s"), ("\u011f", "g"),
                 ("\u00e7", "c"), ("\u00f6", "o"), ("\u00fc", "u")):
        t = t.replace(a, b)
    if _KADIN.search(t):
        return "kad"
    m = _YAS.search(t)
    if m:
        return "u" + next(g for g in m.groups() if g)
    t2 = re.sub(r"[.,]", " ", t)
    return "rez" if _REZ.search(t2) else ""


def ayir(sade: str) -> tuple[str, str]:
    """sadelestir() ciktisini (taban, seviye) olarak boler."""
    p = sade.split()
    if p and p[-1] in SEVIYE_JETON:
        return " ".join(p[:-1]), p[-1]
    return sade, ""


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
    # Taban ve seviye AYRI karsilastirilir: alt-dize/kelime testleri TABAN
    # uzerinde calisir, seviye ise BIREBIR tutmak zorundadir.
    th, sh = ayir(h)
    ta, sa = ayir(a)

    def _uygun(ih, ia):
        """Adayin (taban_ev, taban_dep) hali; seviye tutmuyorsa None."""
        if not (ih and ia):
            return None
        tih, sih = ayir(ih)
        tia, sia = ayir(ia)
        if sih != sh or sia != sa:
            return None
        return tih, tia

    # 2. KADEME: alt-dize. Eskiden "uzunluk farki en kucuk olani sec"
    # deniyordu; ama sorgu BIRDEN COK ayri kulubun icinde geciyorsa bu
    # kural secim degil KURA'dir. Olculdu: "Manchester" sorgusu indekste
    # hem "Manchester City" hem "Manchester United" varken sirf City daha
    # kisa diye City'ye baglaniyordu. Artik birden cok AYRI aday varsa
    # BELIRSIZ sayilir ve eslesme dusurulur.
    adaylar = []
    for (ih, ia), v in idx.items():
        u = _uygun(ih, ia)
        if not u:
            continue
        tih, tia = u
        if (th in tih or tih in th) and (ta in tia or tia in ta):
            fark = abs(len(tih) - len(th)) + abs(len(tia) - len(ta))
            adaylar.append((fark, (ih, ia), v))
    if len(adaylar) == 1:
        return adaylar[0][2]
    if len(adaylar) > 1:
        return None                     # belirsiz: yanlis baglamaktansa hic

    # 3. KADEME: kelime ortusmesi. IKI SIKILASTIRMA (2026-08-31):
    #
    #   a) Eskiden skor IKI TARAFIN ORTALAMASI idi ve esik 0,5'ti. Bir
    #      taraf birebir tutunca (arsenal=arsenal) oteki taraf TAMAMEN
    #      alakasiz olsa bile ortalama tam 0,5 cikip GECIYORDU. Olculdu:
    #      "Galatasaray - Arsenal" sorgusu "Aston Villa - Arsenal"
    #      kaydiyla eslesiyordu. Artik HER IKI taraf da ESIK_TARAF'i
    #      gecmek zorunda.
    #   b) Eskiden en yuksek skorlu aday kosulsuz donuyordu. Iki aday
    #      ayni skoru aliyorsa hangisinin dondugu sozluk sirasina kaliyor
    #      -- yani KURA. Artik berabere/yakin durumda BELIRSIZ sayilip
    #      None doner. Eslesmeme zararsizdir; YANLIS eslesme sessizce
    #      yanlis istatistik uretir.
    def _ort(x, y):
        sx, sy = set(x.split()), set(y.split())
        if not sx or not sy:
            return 0.0
        return len(sx & sy) / max(1, min(len(sx), len(sy)))

    en_iyi, en_skor, ikinci = None, 0.0, 0.0
    for (ih, ia), v in idx.items():
        u = _uygun(ih, ia)
        if not u:
            continue
        tih, tia = u
        o1, o2 = _ort(th, tih), _ort(ta, tia)
        if min(o1, o2) < ESIK_TARAF:
            continue
        sk = (o1 + o2) / 2
        if sk > en_skor:
            en_iyi, ikinci, en_skor = v, en_skor, sk
        elif sk > ikinci:
            ikinci = sk
    if en_iyi is None or en_skor < ESIK_ORT or en_skor <= ikinci + AYIRT:
        return None
    return en_iyi
