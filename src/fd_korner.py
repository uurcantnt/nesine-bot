"""Korner marketleri icin IKINCI EMPIRIK TABAN (football-data.co.uk).

Botun korner sayilari Fotmob/Sofascore'dan geliyor ve o hattan daha once
SESSIZ bir hata cikti (sezon toplamini yanlis bolene bolup mac basina
23,5 korner uretmisti). Burada ayni maclar icin BAGIMSIZ bir kaynak var:
fd sezon dosyalarinda mac basina korner (HC/AC) dolu.

NE OLCULDU (GitHub Actions, 2026-08-31)

  Ham takim modeli (takim ortalamalarindan lambda):
      MAE 2,710 · naif lig ortalamasi 2,672  -> naiften KOTU
  Sebep bilgi yoklugu DEGIL, ASIRI GUVEN. Dilim testi (2025/26, 5224 mac):
      lam 8,36 dilimi -> gercek 9,16      lam 11,07 dilimi -> gercek 10,27
  Model 2,7 kornerlik fark tahmin ediyor, gerceklesen 1,1.

  DUZELTME: sapma olculen egimle buzulur.
      duzeltilmis_lam = lig_taban + A * (ham_lam - lig_taban)
      A 2024/25'te olculdu: 0,334   (2025/26'da bagimsizca 0,332 -- kararli)

  DIS ORNEKLEM SINAVI: A, 2024/25'te olculup 2025/26'ya HIC DOKUNULMADAN
  uygulandi (5224 mac):
      MAE  duzeltilmis 2,660 < naif 2,672 < ham 2,710
      Brier her cizgide naiften iyi (8,5: 0,232/0,233 · 10,5: 0,236/0,237)
      Kalibrasyon birebir: %38 dedik %39 cikti, %28 dedik %29, %20 dedik %20

  KAZANC KUCUKTUR VE BOYLE SUNULMALIDIR: Brier'de 0,001-0,002. Bu, Nesine'nin
  ~%20 payini KAPATMAZ. Bu modul KENAR kaynagi DEGIL, ikinci gorustur.

  SEZON BASI: ilk olcum 10 mac isinmayla yapilmisti. Kisa isinma AYRICA
  tarandi ve duzeltme uygulandiktan sonra 3 MAC BILE naiften iyi cikti
  (isinma 3: MAE 2,684 vs naif 2,692; Brier 0,2361 vs 0,2372). Egim
  isinmaya gore uc bantta degisir. 3 macin altinda LIG ORTALAMASI
  kullanilir ve kaynak adi "lig ortalamasi" diye YAZILIR -- takim modeli
  gibi gosterilmez, havuza da KATILMAZ.
  Gecen sezon katsayilariyla sezon basini tahmin etmek de olculdu
  (1079 mac): MAE 2,728 · naif 2,728 -> katki YOK, kullanilmadi.

NE KAPSAMAZ
  1. Yari korneri: fd'de ilk yari korneri YOKTUR (market 218 -> "yok").
  En Cok Korner (220): takim bazinda ayrim gerektirir, DOGRULANMADI -> "yok".
"""
from __future__ import annotations

import csv
import io
import math
import statistics as st
from collections import defaultdict

import stats as ST

# --- OLCULEN sabitler. Sonuca bakilarak SECILMEDI; egitim sezonundan geldi.
# Buzulme egimi ISINMAYA gore degisir. 2024/25'te her isinma icin AYRI
# olculup 2025/26'ya dokunulmadan uygulandi (GitHub Actions, 2026-08-31):
#
#   isinma  egim   n      MAE duz.  MAE naif  B(10,5) duz/naif
#     3     0,296  6506   2,684     2,692     0,2361 / 0,2372
#     5     0,285  6150   2,678     2,687     0,2357 / 0,2370
#     8     0,328  5594   2,663     2,674     0,2359 / 0,2374
#    10     0,334  5224   2,660     2,672     0,2357 / 0,2373
#    12     0,355  4852   2,665     2,678     0,2361 / 0,2379
#
# HEPSI naiften iyi -- yani 10 mac sarti GEREKSIZDI, 3 mac yetiyor. Egim
# kisa isinmada kendiliginden daha SERT buzuyor, dogru yon.
# Ham tabloyu degil UC BANTA yuvarlanmis halini kullaniyoruz: 4 ve 5'teki
# kucuk dusus gurultudur, ona uydurmak asiri uyum olur.
EGIM_BANT = ((10, 0.335), (6, 0.310), (3, 0.290))
NB_K = 56.0                # negatif binom sekil parametresi (egitim sezonu)
KATSAYI_BUZ = 3            # kucuk orneklemde lig ortalamasina buzulme
MIN_MAC = 3                # olculen en dusuk calisan isinma

# Lig tabani: CARI sezon gozlemleri + GECEN sezon ortalamasi (onsel).
# Gecen sezonun agirligi ONSEL_N gozlem degerinde sayilir; sezon ilerledikce
# cari veri onu dogal olarak bastirir.
#
# NEDEN MESRU (olculdu, GitHub Actions 2026-08-31, 3 sezon x 21 lig):
#   ayni ligin sezonlar arasi oynamasi  : medyan 0,46 korner (en cok 1,10)
#   gecen sezon ortalamasi -> bu sezon  : MAE 0,333
#   tum liglerin ortalamasi -> bu sezon : MAE 0,380
#   yani lig kimligi BILGI TASIYOR ve gecen sezon iyi bir onseldir.
ONSEL_N = 40

SEZON = "2627"
ONCEKI_SEZON = "2526"
LIG = ("E0", "E1", "E2", "E3", "EC", "SC0", "SC1", "SC2", "SC3", "D1", "D2",
       "I1", "I2", "SP1", "SP2", "F1", "F2", "N1", "B1", "P1", "T1", "G1")

_TAKIM: dict | None = None
_LIG: dict | None = None
_TAKIM_LIG: dict | None = None


def _sezon_oku(sezon: str):
    """(takim_atilan, takim_yenilen, lig_gozlemleri, takim->lig)"""
    import fd_kapanis as FK
    at = defaultdict(list); ye = defaultdict(list)
    lig = defaultdict(list); tlig = {}
    for kod in LIG:
        met = FK._cek(f"mmz4281/{sezon}/{kod}.csv", f"{sezon}_{kod}.csv")
        if not met:
            continue
        for r in csv.DictReader(io.StringIO(met)):
            h, a = r.get("HomeTeam"), r.get("AwayTeam")
            try:
                hc, ac = float(r["HC"]), float(r["AC"])
            except (KeyError, ValueError, TypeError):
                continue
            if not (h and a):
                continue
            sh, sa = ST.sadelestir(h), ST.sadelestir(a)
            at[sh].append(hc); ye[sh].append(ac)
            at[sa].append(ac); ye[sa].append(hc)
            # BIRIM: lig sozlugunde MAC TOPLAMI tutulur, takim basi DEGIL.
            # Once burada takim basi degerler tutuluyordu ve yedek sabit
            # mac toplami birimindeydi; ag duserken karisip E0 tabanini
            # 10,0 yerine 15,7 yapti. Ayni birim hatasi sinifi 2026-08-21'de
            # "mac basi 23,5 korner" olarak da cikmisti. Tek birim: MAC.
            lig[kod].append(hc + ac)
            tlig[sh] = kod; tlig[sa] = kod
    return at, ye, lig, tlig


def _yukle(yenile: bool = False) -> None:
    global _TAKIM, _LIG, _TAKIM_LIG
    if _TAKIM is not None and not yenile:
        return
    at, ye, lig, tlig = _sezon_oku(SEZON)
    _, _, onceki_lig, onceki_tlig = _sezon_oku(ONCEKI_SEZON)
    onceki = {k: st.mean(v) for k, v in onceki_lig.items() if len(v) >= 50}
    # Yedek: 2023/24-2025/26'da 21 ligin mac basi toplam korner ortalamasi
    # 8,73 ile 10,45 arasindaydi (olculdu). Orta deger alinir. MAC birimi.
    genel = st.mean(list(onceki.values())) if onceki else 9.80
    kodlar = set(lig) | set(onceki)
    _LIG = {}
    for k in kodlar:
        v = lig.get(k, [])
        o = onceki.get(k, genel)
        _LIG[k] = (sum(v) + ONSEL_N * o) / (len(v) + ONSEL_N)
    # Takim -> lig eslemesi: cari sezon once, yoksa gecen sezondan. Bir takim
    # cari sezonda hic oynamamis olabilir (lig degistirmis, ust/alt lige
    # cikmis); ligini bilmek TABAN icin yeterlidir.
    _TAKIM_LIG = {**onceki_tlig, **tlig}
    _TAKIM = {t: {"at": at[t], "ye": ye[t]} for t in at}


def _nb_ust(cizgi: float, mu: float, k: float = NB_K) -> float:
    """P(toplam > cizgi), negatif binom."""
    n = int(math.floor(cizgi))
    kum = 0.0
    for x in range(n + 1):
        kum += math.exp(math.lgamma(x + k) - math.lgamma(k) - math.lgamma(x + 1)
                        + k * math.log(k / (k + mu)) + x * math.log(mu / (k + mu)))
    return min(1.0, max(0.0, 1.0 - kum))


def lam(ev: str, dep: str) -> dict:
    """Mac icin beklenen TOPLAM korner. Her zaman sozluk doner."""
    _yukle()
    e, d = ST.sadelestir(ev), ST.sadelestir(dep)
    te, td = (_TAKIM or {}).get(e), (_TAKIM or {}).get(d)
    kod = (_TAKIM_LIG or {}).get(e) or (_TAKIM_LIG or {}).get(d)
    L = (_LIG or {}).get(kod)          # MAC BASI TOPLAM korner
    if L is None:
        return {"var": False, "neden": "fd korner kapsaminda degil"}
    taban = L
    tl = L / 2.0                       # takim basi -- katsayilarin paydasi
    if not (te and td) or min(len(te["at"]), len(td["at"])) < MIN_MAC:
        # Takim modeli DOGRULANMIS ISINMAYI doldurmuyor. Lig ortalamasi
        # kullanilir; bu bir tahmindir ama TAKIM tahmini degildir ve oyle
        # sunulmaz. (Gecen sezon katsayisi da olculdu: naiften farksiz.)
        n = min(len(te["at"]) if te else 0, len(td["at"]) if td else 0)
        return {"var": True, "lam": taban, "kaynak": "lig ortalaması",
                "lig": kod, "n": n,
                "not": f"takım modeli için {MIN_MAC} maç gerekli, {n} var"}

    def kat(v):
        return (sum(v) + KATSAYI_BUZ * tl) / (len(v) + KATSAYI_BUZ) / tl
    ham = tl * (kat(te["at"]) * kat(td["ye"]) + kat(td["at"]) * kat(te["ye"]))
    n = min(len(te["at"]), len(td["at"]))
    egim = next(e for esik, e in EGIM_BANT if n >= esik)
    return {"var": True, "lam": taban + egim * (ham - taban),
            "ham_lam": ham, "kaynak": "takım modeli", "lig": kod,
            "n": n, "egim": egim}


# --- Nesine market koprusu ---------------------------------------------------
# 216 : {{handicap}} Korner Alt/Ust   -> sov = cizgi
# 338 : Toplam Korner Araligi         -> 0-8 / 9-11 / 12+
# 218 (1. Yari) ve 220 (En Cok Korner) KASITLI YOK, sebepleri asagida.
YOK = {
    "218": "fd'de ilk yarı korneri yok (yalnızca maç sonu)",
    "220": "takım bazında ayrım doğrulanmadı (yalnızca toplam ölçüldü)",
}


def secenek_p(ev: str, dep: str, mtid, secenek: str, sov=None) -> dict:
    m = str(mtid)
    if m in YOK:
        return {"var": False, "neden": YOK[m]}
    if m not in ("216", "338"):
        return {"var": False, "neden": "bu markette fd korner karşılığı yok"}
    L = lam(ev, dep)
    if not L.get("var"):
        return L
    mu = L["lam"]
    if m == "216":
        if sov is None:
            return {"var": False, "neden": "korner çizgisi okunamadı"}
        p = _nb_ust(float(sov), mu)
        if secenek == "Alt":
            p = 1.0 - p
        elif secenek != "Üst":
            return {"var": False, "neden": f"seçenek eşleşmedi: {secenek}"}
    else:
        u8 = _nb_ust(8.5, mu)          # P(>8)  = P(9+)
        u11 = _nb_ust(11.5, mu)        # P(>11) = P(12+)
        p = {"0-8": 1.0 - u8, "9-11": u8 - u11, "12+": u11}.get(secenek)
        if p is None:
            return {"var": False, "neden": f"seçenek eşleşmedi: {secenek}"}
    return {"var": True, "p": p, "lam": mu, "kaynak": L["kaynak"],
            "n": L.get("n"), "not": L.get("not")}


def capraz(ev: str, dep: str, bizim_lam: float) -> dict:
    """Bizim korner tahminimizi fd'ninkiyle kiyasla. Makullik kapisi.

    Sessiz hatanin yakalanacagi yer burasi: 23,5 kornerlik bir tahmin
    fd'nin ~10'una karsi 13 korner sapar ve BAGIRIR.
    """
    L = lam(ev, dep)
    if not L.get("var"):
        return {"var": False, "neden": L.get("neden")}
    f = L["lam"]
    return {"var": True, "fd_lam": f, "bizim": bizim_lam,
            "fark": bizim_lam - f, "kaynak": L["kaynak"],
            "supheli": abs(bizim_lam - f) > 4.0}
