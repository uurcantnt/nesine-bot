"""football-data.co.uk sezon dosyalari: GERCEK KAPANIS FIYATI ve CLV.

NEDEN VAR: mevcut clv.py, onerimizi NESINE'nin kendi kapanis oraniyla
kiyasliyor. Olculdu (2026-08-31): 68 bahsin %59'unda Nesine orani MAC
BASINA KADAR HIC OYNAMIYOR. Kendi hareket etmeyen fiyatina karsi CLV
olcmek, cetveli kendisiyle olcmektir -- sonuc tanim geregi sifira yakin
cikar ve hicbir sey ogretmez.

Burada kapanis, BAGIMSIZ ve KESKIN bir piyasadan alinir: Betfair
borsasinin kapanis orani (BFECH/D/A), yoksa bukmeker kapanis ortalamasi
(AvgCH/D/A).

PINNACLE YOK — DUZELTME: bu isin planinda "Pinnacle kapanis oranlari"
vardi. 2026/27 sezon dosyalarinda PSCH sutunu 14 ligin HEPSINDE BOS
(olculdu 2026-08-31). Pinnacle verisi gecmis sezonlarda var, guncel
sezonda YOK. Plan bu yuzden Betfair kapanisina donduruldu; Betfair bir
borsadir ve keskinlik bakimindan Pinnacle'a denk kabul edilir, ama bu
bir VARSAYIMDIR, olculmus bir denklik degildir.

IKI AYRI CLV OLCULUR, cunku tek sayi yaniltir:

  1. HAM CLV = bahis_orani / kapanis_orani - 1
     Gercek ekonomi. Nesine'nin payi %18-21, Betfair'inki %2-5;
     dolayisiyla bu sayi neredeyse HER ZAMAN eksi cikar. Eksi cikmasi
     kotu SECIM demek DEGILDIR -- aradaki farkin buyuk kismi PAYDIR.
     Basabas noktasi: -pay kadar.

  2. PAYDAN ARINDIRILMIS CLV = kapanis_olasilik - bahis_ani_olasilik
     SECIM BECERISI. Iki tarafi da paydan aritip kiyaslar: piyasa
     bizim sectigimiz yone mi kaydi, tersine mi? Payin etkisi cikar.
     Artiysa, sectigimiz tarafin olasiligi biz bahsi kaydettikten
     SONRA yukselmis demektir.

Sadece 1X2 ve 2,5 Alt/Ust icin olculebilir; korner/kart/ilk yari
marketlerinde fd'de kapanis fiyati yoktur.
"""
from __future__ import annotations

import csv
import io
import json
import statistics as st
import time
import urllib.request
from pathlib import Path

import stats as ST

KOK = "https://www.football-data.co.uk/"
SEZON = "2627"
ANA = ("E0", "E1", "E2", "E3", "EC", "SC0", "SC1", "SC2", "SC3", "D1", "D2",
       "I1", "I2", "SP1", "SP2", "F1", "F2", "N1", "B1", "P1", "T1", "G1")
EK = ("ARG", "AUT", "BRA", "CHN", "DNK", "FIN", "IRL", "JPN", "MEX", "NOR",
      "POL", "ROU", "RUS", "SWE", "SWZ", "USA")
TTL = 6 * 3600
_ONB = Path(__file__).resolve().parent.parent / ".cache" / "fd_sezon"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# Kapanis kaynagi adaylari (sonek onekleri). Sira DEGIL, en dar marjli
# secilir -- fd.py'deki kuralin aynisi.
ADAY = (("BFEC", "Betfair kapanış"), ("AvgC", "bukmeker kapanış ort."))
MARJ_TAVAN = 0.12


def _cek(yol: str, ad: str) -> str | None:
    _ONB.mkdir(parents=True, exist_ok=True)
    f = _ONB / ad
    if f.exists() and time.time() - f.stat().st_mtime < TTL:
        return f.read_text(encoding="utf-8")
    try:
        istek = urllib.request.Request(KOK + yol, headers={"User-Agent": UA})
        with urllib.request.urlopen(istek, timeout=30) as y:
            met = y.read().decode("utf-8-sig", "ignore")
    except Exception:
        return f.read_text(encoding="utf-8") if f.exists() else None
    f.write_text(met, encoding="utf-8")
    return met


_IX: dict | None = None


def indeks(yenile: bool = False) -> dict:
    """(sade_ev, sade_dep) -> sezon satiri. Tum ligler birlestirilir."""
    global _IX
    if _IX is not None and not yenile:
        return _IX
    ix: dict = {}
    for lig in ANA:
        met = _cek(f"mmz4281/{SEZON}/{lig}.csv", f"{SEZON}_{lig}.csv")
        if not met:
            continue
        for r in csv.DictReader(io.StringIO(met)):
            h, a = r.get("HomeTeam"), r.get("AwayTeam")
            if h and a:
                ix.setdefault((ST.sadelestir(h), ST.sadelestir(a)),
                              {"lig": lig, "ham": r})
    for k in EK:
        met = _cek(f"new/{k}.csv", f"new_{k}.csv")
        if not met:
            continue
        for r in csv.DictReader(io.StringIO(met)):
            h, a = r.get("Home"), r.get("Away")
            if h and a:
                ix.setdefault((ST.sadelestir(h), ST.sadelestir(a)),
                              {"lig": k, "ham": r})
    _IX = ix
    return ix


def _f(r: dict, k: str) -> float | None:
    v = (r.get(k) or "").strip()
    try:
        x = float(v)
    except ValueError:
        return None
    return x if x > 1.0 else None


def _en_dar(r: dict, sonek: tuple[str, ...]) -> tuple | None:
    en = None
    for on, ad in ADAY:
        o = [_f(r, on + s) for s in sonek]
        if not all(o):
            continue
        m = sum(1.0 / x for x in o) - 1.0
        if m > MARJ_TAVAN:
            continue
        if en is None or m < en[2]:
            en = (o, ad, m)
    return en


def kapanis(ev: str, dep: str, mtid, secenek: str) -> dict:
    """Bir SECIM icin kapanis orani + paydan aritilmis olasilik."""
    import fd
    k = fd.KOPRU.get(str(mtid))
    if not k:
        return {"var": False, "neden": "bu markette fd kapanisi yok"}
    alan, harita = k
    ix = harita.get(secenek)
    if ix is None:
        return {"var": False, "neden": f"secenek eslesmedi: {secenek}"}
    m = ST.esle(indeks(), ev, dep)
    if not m:
        return {"var": False, "neden": "fd sezon dosyalarinda bulunamadi"}
    r = m["ham"]
    sonek = ("H", "D", "A") if alan == "ms" else (">2.5", "<2.5")
    en = _en_dar(r, sonek)
    if not en:
        return {"var": False, "neden": "kapanis orani bos ya da marj yuksek"}
    o, ad, marj = en
    inv = [1.0 / x for x in o]
    t = sum(inv)
    pp = sum(inv[i] / t for i in ix)
    # TURETILMIS secenekte (Cifte Sans) KAPANIS ORANI YOKTUR: elimizde o
    # marketin kendi kapanis fiyati degil, 1X2'den toplanmis PAYSIZ bir
    # olasilik var. Paysiz sayidan "kapanis orani" uydurup ham CLV
    # hesaplamak, Nesine'nin payini beceri sanmaya yol acar. Bu yuzden
    # oran None doner ve ham CLV o satirda ATLANIR; yalnizca paydan
    # aritilmis CLV olculur.
    return {"var": True, "oran": (o[ix[0]] if len(ix) == 1 else None),
            "p": pp, "kaynak": ad, "marj": marj, "lig": m["lig"],
            "turetilmis": len(ix) > 1}


# --- CLV raporu --------------------------------------------------------------
DATA = Path(__file__).resolve().parent.parent / "data"


def olc() -> dict:
    """golge.jsonl'daki onerileri gercek kapanis fiyatiyla kiyasla."""
    kayit = []
    p = DATA / "golge.jsonl"
    if p.exists():
        for s in p.read_text(encoding="utf-8").splitlines():
            s = s.strip()
            if not s:
                continue
            try:
                kayit.append(json.loads(s))
            except json.JSONDecodeError:
                pass
    gorulen = set()
    satir = []
    yok: dict = {}
    for k in kayit:
        ad = (k.get("mac") or "").split(" - ")
        if len(ad) != 2:
            continue
        anahtar = (k.get("mac_id"), k.get("mtid"), k.get("secenek"))
        if anahtar in gorulen:
            continue                     # ayni bahis birden cok kez loglanmis
        gorulen.add(anahtar)
        c = kapanis(ad[0], ad[1], k.get("mtid"), k.get("secenek") or "")
        if not c.get("var"):
            yok[c["neden"]] = yok.get(c["neden"], 0) + 1
            continue
        oran = k.get("oran")
        if not oran:
            continue
        satir.append({
            "mac": k.get("mac"), "market": k.get("market"),
            "secenek": k.get("secenek"), "oran": oran,
            "kapanis_oran": c["oran"], "kapanis_p": c["p"],
            "bahis_p": k.get("nesine_p"), "kaynak": c["kaynak"],
            "turetilmis": c.get("turetilmis", False),
            "ham_clv": (oran / c["oran"] - 1.0) if c["oran"] else None,
            "arit_clv": (c["p"] - k["nesine_p"]) if k.get("nesine_p") else None,
            "surum": k.get("surum") or "v1",
        })
    return {"satir": satir, "yok": yok, "aday": len(gorulen)}


def rapor() -> str:
    o = olc()
    s = o["satir"]
    L = ["📉 CLV — GERÇEK KAPANIŞ FİYATINA KARŞI", ""]
    L.append(f"Kayıtlı ayrı bahis: {o['aday']} · kapanış fiyatı bulunan: {len(s)}")
    for n, c in sorted(o["yok"].items(), key=lambda z: -z[1]):
        L.append(f"   {c:>4} ölçülemedi — {n}")
    if len(s) < 5:
        L += ["", "Ölçüm için yeterli eşleşme yok. CLV, fd'nin kapsadığı",
              "liglerdeki 1X2 ve 2,5 Alt/Üst bahislerinde ölçülebilir."]
        return "\n".join(L)
    ham = [x["ham_clv"] for x in s if x["ham_clv"] is not None]
    tur = sum(1 for x in s if x.get("turetilmis"))
    ar = [x["arit_clv"] for x in s if x["arit_clv"] is not None]
    L.append("")
    L.append("1) HAM CLV (bahis oranı ÷ kapanış oranı − 1)")
    if tur:
        L.append(f"   ({tur} türetilmiş seçim (Çifte Şans) bu ölçümün DIŞINDA:")
        L.append("    o markette kapanış fiyatının kendisi yok, sadece")
        L.append("    1X2'den toplanmış paysız olasılık var.)")
    L.append(f"   n={len(ham)} · ortalama {100*st.mean(ham):+.1f}% · "
             f"medyan {100*st.median(ham):+.1f}%")
    L.append("   Bu sayının eksi olması BEKLENİR: Nesine'nin payı %18-21,")
    L.append("   kapanış kaynağının payı %2-5. Farkın büyük kısmı PAYDIR,")
    L.append("   seçim hatası değil. Başabaş nokta ≈ −pay.")
    if ar:
        m = st.mean(ar)
        se = (st.pstdev(ar) / len(ar) ** 0.5) if len(ar) > 1 else 0.0
        L.append("")
        L.append("2) PAYDAN ARINDIRILMIŞ CLV (seçim becerisi)")
        L.append(f"   n={len(ar)} · ortalama {100*m:+.2f} puan · "
                 f"medyan {100*st.median(ar):+.2f} puan")
        L.append(f"   %95 aralık: {100*(m-1.96*se):+.2f} … "
                 f"{100*(m+1.96*se):+.2f} puan")
        if (m - 1.96 * se) <= 0 <= (m + 1.96 * se):
            L.append("   → Aralık SIFIRI içeriyor: seçimlerimizin piyasayı")
            L.append("     öngördüğüne dair kanıt YOK. (Kanıt yok = yanlış")
            L.append("     olduğu kanıtlandı DEĞİL; ölçüm henüz ayırt edemiyor.)")
        elif m > 0:
            L.append("   ⚠️ Aralık sıfırın ÜSTÜNDE — incelenmeli, n hâlâ küçük.")
        else:
            L.append("   ⚠️ Aralık sıfırın ALTINDA: piyasa seçtiğimizin")
            L.append("     TERSİNE kayıyor. Bu ciddi bir uyarıdır.")
    sur = {}
    for x in s:
        sur[x["surum"]] = sur.get(x["surum"], 0) + 1
    if len(sur) > 1:
        L.append("")
        L.append("⚠️ KARIŞIK SÜRÜM: " + " · ".join(f"{a}:{c}" for a, c in sur.items()))
    return "\n".join(L)


if __name__ == "__main__":
    print(rapor())
