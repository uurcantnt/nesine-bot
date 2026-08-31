"""football-data.co.uk: IKINCI FIYAT kaynagi.

NEDEN VAR: Nesine'nin 1X2 marji medyan %17-21. Tek fiyata bakip "deger
var" demek, kendi hatasini olcmemek demektir. Betfair borsasinin ayni
maclardaki marji %4,86 (2026-08-31, n=334) -- 3,7 kat keskin. Ikinci
fiyat, Nesine'nin nerede piyasadan AYRISTIGINI gosterir.

OLCULDU (2026-08-31, 41 ortak mac / 123 secim):
  Nesine 1X2 marj medyan   %17,8
  fd     1X2 marj medyan    %8,1   (BFE varsa %4,9)
  marjdan aritilmis fark    medyan 1,00 puan · ortalama 1,79 puan
  yanlilik (fd - nesine)    -0,00 puan  → iki kaynak AYNI seyi olcuyor;
                            sistematik kayma yok. Bu ayni zamanda
                            eslestirmenin dogrulugunun kanitidir:
                            yanlis eslesme olsa yanlilik sifirda cikmazdi.

NE VERIR:
  1X2 · Alt/Ust 2.5 · Asya handikap   — fd'nin kapsadigi ~22 lig
NE VERMEZ:
  korner · kart · ilk yari  — fd'de bunlar YALNIZCA oynanmis maclarin
  sonuc dosyalarinda (HC/AC/HY/AY) var, fikstur dosyasinda YOK.

KAPSAMA DURUSU: Nesine bulteninin ~%15-30'u. Kalan macta ikinci fiyat
YOKTUR. Bu SESSIZCE gizlenmez -- yok() nedeniyle birlikte doner ve
cagiran taraf kullaniciya "ikinci fiyat yok" yazmak ZORUNDADIR. Sessiz
yedege dusmek, ikinci gorusu sahte kilar.

KAPANIS FIYATI: fikstur dosyasindaki C sutunlari (BFECH/AvgCH) BOSTUR;
kapanis ancak mac oynandiktan sonra sezon sonuc dosyasina yazilir. Yani
CLV bu modulden DEGIL, gecmis dosyalardan olculur (bkz. fd_kapanis).
"""
from __future__ import annotations

import csv
import io
import json
import time
import urllib.request
from pathlib import Path

import stats as ST

KOK = "https://www.football-data.co.uk/"
FIKSTUR = ("fixtures.csv", "new_league_fixtures.csv")
TTL = 3600                      # fikstur dosyalari gunde birkac kez guncellenir
_ONB = Path(__file__).resolve().parent.parent / ".cache" / "fd"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# Aday olasilik kaynaklari. "Max" (en iyi oran) KASITLI YOK: birden cok
# bukmekerin EN YUKSEGI, uzlasma degil aykiri degerdir; marji dusuk
# gorunur ama tahmin olarak yanlidir.
#
# Sabit oncelik DEGIL, EN DAR MARJLI olan secilir. Sebep olculdu: buyuk
# liglerde Betfair borsasi %1-5 marjla en keskin, ama Veikkausliiga gibi
# kucuk liglerde borsada islem az ve spread aciliyor -- orada BFE %9-10'a
# cikarken bukmeker ortalamasi %6,7'de kaliyor. Sabit "once BFE" kurali
# bu maclarda daha KOTU fiyati secerdi.
ADAY = (("BFE", "Betfair borsa"), ("Avg", "bukmeker ort."), ("B365", "Bet365"))

# Ikinci gorusun ANLAMLI olmasi icin ust marj siniri. Nesine'nin 1X2
# marji medyan %17,8; bunun yanina %16'lik bir kaynak koyup "ikinci
# gorus" demek kendini kandirmaktir. Esigi gecen kaynak yoksa ikinci
# fiyat YOK sayilir -- zayif fiyati guclu gibi sunmaktansa hic sunmamak.
MARJ_TAVAN = 0.12


# Onbellegin en son ne kadar BAYAT oldugu (saniye). ikinci() bunu doner.
_YAS: float = 0.0


def _cek(dosya: str) -> str:
    """Dosyayi getir. Ag duserse BAYAT onbellek kullanilir -- ama SESSIZCE
    degil: _YAS guncellenir ve cagiran tarafa yas bilgisi gider.

    NEDEN BOYLE (2026-08-31): ag koptugunda eski davranis istisna firlatip
    ikinci fiyati TAMAMEN kaybediyordu. Iki ucun ikisi de yanlis:
      - bayat fiyati taze gibi sunmak  -> kullaniciyi yaniltir
      - bayat fiyati atmak             -> ise yarar bilgiyi ziyan eder
    Dogrusu: kullan, ama YASINI YAZ. Bahis oranlari saatler icinde cok
    degismez; 6 saatlik bir fiyat hala anlamli bir ikinci gorustur,
    2 gunluk degildir.
    """
    global _YAS
    _ONB.mkdir(parents=True, exist_ok=True)
    yol = _ONB / dosya
    if yol.exists() and time.time() - yol.stat().st_mtime < TTL:
        return yol.read_text(encoding="utf-8")
    try:
        istek = urllib.request.Request(KOK + dosya, headers={"User-Agent": UA})
        with urllib.request.urlopen(istek, timeout=30) as y:
            met = y.read().decode("utf-8-sig", "ignore")
    except Exception:
        if not yol.exists():
            raise
        _YAS = max(_YAS, time.time() - yol.stat().st_mtime)
        return yol.read_text(encoding="utf-8")
    yol.write_text(met, encoding="utf-8")
    return met


# Bayat fiyatin hala ikinci gorus sayildigi ust sinir. Ustunde KULLANILMAZ:
# gun degismis, kadro/sakatlik haberi gelmis olabilir.
BAYAT_TAVAN = 18 * 3600


def satirlar() -> list[dict]:
    """Iki fikstur dosyasini birlestirip (ev, dep, satir) listesi doner.

    Iki dosyanin sutun adlari FARKLI (HomeTeam/AwayTeam vs Home/Away);
    burada tek bicime indirgenir.
    """
    out = []
    for d in FIKSTUR:
        try:
            met = _cek(d)
        except Exception:
            continue                     # tek dosya duserse oteki calisir
        for r in csv.DictReader(io.StringIO(met)):
            h = r.get("HomeTeam") or r.get("Home")
            a = r.get("AwayTeam") or r.get("Away")
            if h and a:
                out.append({"ev": h, "dep": a, "tarih": r.get("Date"),
                            "lig": r.get("Div") or r.get("League"), "ham": r})
    return out


def _f(r: dict, k: str) -> float | None:
    v = (r.get(k) or "").strip()
    try:
        x = float(v)
    except ValueError:
        return None
    return x if x > 1.0 else None


def devig(oranlar: list[float]) -> list[float]:
    """Carpimsal marj aritma: 1/oran'lari toplama bol."""
    inv = [1.0 / o for o in oranlar]
    t = sum(inv)
    return [x / t for x in inv]


def marj(oranlar: list[float]) -> float:
    return sum(1.0 / o for o in oranlar) - 1.0


def _secim(r: dict, sonek: tuple[str, ...]) -> tuple | None:
    """Adaylar icinde EN DAR MARJLI tam oran setini bul. Yoksa None."""
    en = None
    for on, ad in ADAY:
        o = [_f(r, on + s) for s in sonek]
        if not all(o):
            continue
        m = marj(o)
        if m > MARJ_TAVAN:
            continue
        if en is None or m < en[2]:
            en = (o, ad, m)
    return en


def _indeks() -> dict:
    ix: dict = {}
    for s in satirlar():
        ix.setdefault((ST.sadelestir(s["ev"]), ST.sadelestir(s["dep"])), s)
    return ix


_IX: dict | None = None


def ikinci(ev: str, dep: str, yenile: bool = False) -> dict:
    """Bir mac icin ikinci fiyat. HER ZAMAN sozluk doner; yoksa neden yazar.

    Doner:
      {"var": False, "neden": "..."}                     -- kapsam disi
      {"var": True, "ms": {...}, "au25": {...}|None,
       "kaynak": "Betfair borsa", "marj": 0.0486,
       "fd_ev": "...", "fd_dep": "...", "lig": "E0"}
    """
    global _IX, _YAS
    if _IX is None or yenile:
        _YAS = 0.0
        try:
            _IX = _indeks()
        except Exception as e:
            return {"var": False, "neden": f"fd erişilemedi: {type(e).__name__}"}
    if _YAS > BAYAT_TAVAN:
        return {"var": False,
                "neden": f"fd fiyatı çok bayat ({_YAS/3600:.0f} saat) — "
                         "ağ erişimi yok"}
    if not _IX:
        return {"var": False, "neden": "fd fikstur listesi bos"}
    m = ST.esle(_IX, ev, dep)
    if not m:
        return {"var": False, "neden": "fd kapsaminda degil (~22 lig)"}
    r = m["ham"]
    ms = _secim(r, ("H", "D", "A"))
    if not ms:
        return {"var": False,
                "neden": f"fd 1X2 orani yok ya da marj >%{100*MARJ_TAVAN:.0f}"}
    o, kaynak, ms_marj = ms
    au = _secim(r, (">2.5", "<2.5"))
    au25 = None
    if au:
        oo, au_ad, au_m = au
        p = devig(oo)
        au25 = {"p_ust": p[0], "p_alt": p[1], "kaynak": au_ad, "marj": au_m}
    return {"var": True, "ms": {"p": devig(o), "oran": o},
            "au25": au25, "kaynak": kaynak, "marj": ms_marj,
            "yas_sn": _YAS,
            "fd_ev": m["ev"], "fd_dep": m["dep"], "lig": m["lig"]}


def kapsama(olaylar: list[dict]) -> dict:
    """Bir bulten listesi icin kapsama raporu. Kullaniciya yazilacak sayi."""
    var = yok = 0
    nedenler: dict = {}
    for e in olaylar:
        s = ikinci(e.get("ev") or "", e.get("dep") or "")
        if s.get("var"):
            var += 1
        else:
            yok += 1
            nedenler[s["neden"]] = nedenler.get(s["neden"], 0) + 1
    return {"var": var, "yok": yok, "toplam": var + yok, "nedenler": nedenler}


if __name__ == "__main__":
    import bulletin
    sn = bulletin.latest()
    ol = [e for e in sn.get("olay", []) if e.get("ts")]
    k = kapsama(ol)
    print(f"bulten {k['toplam']} mac · ikinci fiyat VAR {k['var']} "
          f"(%{100*k['var']/max(k['toplam'],1):.0f}) · YOK {k['yok']}")
    for n, c in sorted(k["nedenler"].items(), key=lambda z: -z[1]):
        print(f"   {c:>4}  {n}")
    for e in ol[:60]:
        s = ikinci(e.get("ev") or "", e.get("dep") or "")
        if s.get("var"):
            p = s["ms"]["p"]
            print(f"\n{e['ev']} - {e['dep']}  [{s['lig']}] {s['kaynak']} "
                  f"marj %{100*s['marj']:.1f}")
            print(f"   fd    : 1 %{100*p[0]:.1f}  X %{100*p[1]:.1f}  2 %{100*p[2]:.1f}")
            o = (e.get("m") or {}).get("1", {}).get("o")
            if o and len(o) == 3:
                q = devig(o)
                print(f"   nesine: 1 %{100*q[0]:.1f}  X %{100*q[1]:.1f}  2 %{100*q[2]:.1f}"
                      f"   (marj %{100*marj(o):.1f})")
                print("   fark  : " + "  ".join(
                    f"{100*(p[i]-q[i]):+.1f}p" for i in range(3)))


# --- Nesine market koprusu ---------------------------------------------------
# fd YALNIZCA su iki markete karsilik verir. Nesine'nin 559 marketinin
# geri kalaninda (korner, kart, ilk yari, cifte sans, KG ...) ikinci fiyat
# YOKTUR. Listeyi genisletmek icin fd'de karsilik BULUNMASI sart -- yakin
# bir marketi "yeterince benzer" sayip baglamak, ikinci gorusu uydurmaktir.
# Deger: (fd_alan, {nesine_secenek: TOPLANACAK indeksler})
# Cifte Sans indeks TOPLAMIYLA turetilir. Bu bir VARSAYIM DEGIL, olasilik
# ozdesligidir: P(1 veya X) = P(1) + P(X); sonuclar ayrik. Yani turetilen
# sayi, 1X2 fiyatinin tasidigindan fazla bilgi IDDIA ETMEZ.
KOPRU = {
    "1":  ("ms",   {"MS 1": (0,), "MS X": (1,), "MS 2": (2,)}),
    "53": ("ms",   {"MS 1": (0,), "MS X": (1,), "MS 2": (2,)}),
    "3":  ("ms",   {"ÇŞ 1-X": (0, 1), "ÇŞ 1-2": (0, 2), "ÇŞ X-2": (1, 2)}),
    "55": ("ms",   {"ÇŞ 1-X": (0, 1), "ÇŞ 1-2": (0, 2), "ÇŞ X-2": (1, 2)}),
    "12": ("au25", {"Üst": (0,), "Alt": (1,)}),
    "67": ("au25", {"Üst": (0,), "Alt": (1,)}),
}


def secenek_p(ev: str, dep: str, market_id: str, secenek: str) -> dict:
    """Tek bir SECIM icin ikinci fiyat olasiligi.

    HER ZAMAN sozluk doner. {"var": False, "neden": ...} ya da
    {"var": True, "p": 0.53, "kaynak": "...", "marj": 0.048}.
    Cagiran taraf "var" False ise kullaniciya bunu YAZMALIDIR.
    """
    k = KOPRU.get(str(market_id))
    if not k:
        return {"var": False, "neden": "bu markette fd karsiligi yok"}
    alan, harita = k
    ix = harita.get(secenek)
    if ix is None:
        return {"var": False, "neden": f"secenek eslesmedi: {secenek}"}
    s = ikinci(ev, dep)
    if not s.get("var"):
        return s
    if alan == "ms":
        return {"var": True, "p": sum(s["ms"]["p"][i] for i in ix),
                "kaynak": s["kaynak"], "marj": s["marj"],
                "yas_sn": s.get("yas_sn", 0.0), "turetilmis": len(ix) > 1}
    au = s.get("au25")
    if not au:
        return {"var": False,
                "neden": "fd'de 2,5 alt/ust orani yok (ek lig dosyasinda "
                         "yalnizca 1X2 var)"}
    liste = [au["p_ust"], au["p_alt"]]
    return {"var": True, "p": sum(liste[i] for i in ix),
            "kaynak": au["kaynak"], "marj": au["marj"],
            "yas_sn": s.get("yas_sn", 0.0), "turetilmis": len(ix) > 1}


def agirlik(marj_deger: float, nesine_marj: float = 0.211) -> float:
    """Havuz agirligi = (1/marj) / (1/nesine_marj). Nesine = 1,00.

    havuz.py'deki kuralin AYNISI; orada DraftKings icin sabit 3,15 yazili
    cunku onun marji sabit olculmustu. fd'nin marji mac basina degisiyor
    (%1,3 ile %12 arasi olculdu), o yuzden agirlik da mac basina hesaplanir.
    Ust sinir 6,0: %3,5'ten dar marjda agirlik hizla buyuyup havuzu tek
    kaynaga cevirmesin -- borsa fiyati keskindir ama tek dogru degildir.
    """
    m = max(float(marj_deger), 1e-4)
    return min(6.0, nesine_marj / m)
