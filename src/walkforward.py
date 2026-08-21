"""PARAMETRE YENIDEN SINAMASI — Nesine'ye benzerlige gore DEGIL, SONUCA gore.

KONSUL BULGUSU (en rahatsiz edici olan): model parametreleri (XG_AGIRLIK
%33, XG_TAVAN 3,0 ve elenen ic/dis saha ayrimi) "Nesine fiyatindan ortalama
mutlak sapmayi minimize et" olcutuyle secildi. Bu olcut ISABETI degil
TAKLIDI optimize eder. Kantitatif danisman aynen soyle dedi:

    "xG karisimi Nesine fiyatindan sapma minimize edilerek secilmis. Bu,
     marji ve yanliligiyla birlikte bahisciyi TAKLIT etmeyi optimize eder,
     isabeti degil. O karar GECERSIZ, gercek sonuclarla yeniden test edilmeli."

Bu modul o testi yapar. Uc metodolojik duzeltme de burada:

  1. OLCUT: Nesine'ye yakinlik DEGIL, gerceklesen sonuc (Brier + RPS).
  2. RPS: 1X2 SIRALI bir sonuctur (1 / X / 2). Brier siralamayi yok sayar;
     futbol literaturunde standart olcu RPS'tir. Ikisi de raporlanir.
  3. KUMELENMIS ONYUKLEME: onyukleme SECIM degil MAC duzeyinde yapilir.
     Secim duzeyinde yapmak guven araligini sahte olarak daraltir (ayni
     macin secenekleri mekanik olarak bagimli).

NE YAPMAZ: parametre SECMEZ. Yalnizca olcer ve "ayirt edilebiliyor mu"
sorusunu cevaplar. Ayirt edilemiyorsa dogru cevap "elimizde bu parametreyi
hakli cikaracak kanit YOK" demektir -- parametreyi degistirmek degil.
"""
from __future__ import annotations

import random
import statistics as st
import sys

import model as M
import ornek

# (ad, XG_AGIRLIK, XG_TAVAN)
VARYANTLAR = [
    ("sadece gol",            0.00, 3.0),
    ("karma %25",             0.25, 3.0),
    ("karma %33 + kırp 3,0",  0.33, 3.0),      # SIMDIKI
    ("karma %33 kırpsız",     0.33, 99.0),
    ("karma %50",             0.50, 3.0),
    ("sadece xG",             1.00, 3.0),
]
SIMDIKI = "karma %33 + kırp 3,0"
ONYUKLEME = 4000


def _varyant_uygula(agirlik: float, tavan: float):
    M.XG_AGIRLIK, M.XG_TAVAN = agirlik, tavan


def _rps(p: list[float], gercek: int) -> float:
    """Sirali sonuc icin Ranked Probability Score (dusuk = iyi)."""
    r = len(p)
    ku_p = ku_o = 0.0
    t = 0.0
    for i in range(r - 1):
        ku_p += p[i]
        ku_o += 1.0 if i == gercek else 0.0
        t += (ku_p - ku_o) ** 2
    return t / (r - 1)


def mac_puanlari(maclar: list) -> dict:
    """Her varyant icin mac basi (brier_ort, rps_ort) listesi."""
    out = {}
    ilk_agirlik, ilk_tavan = M.XG_AGIRLIK, M.XG_TAVAN
    try:
        for ad, ag, tv in VARYANTLAR:
            _varyant_uygula(ag, tv)
            brier_mac, rps_mac, n_secim = [], [], 0
            for m in maclar:
                a, b = m.get("ist_ev"), m.get("ist_dep")
                if not (a and b):
                    continue
                t = M.tahmin(a, b)
                if not t:
                    continue
                bs = []
                for s in m["secimler"]:
                    mp = M.olasilik(s["mtid"], s["idx"], s["sov"], t)
                    if mp is None:
                        continue
                    bs.append((mp - (1.0 if s["tuttu"] else 0.0)) ** 2)
                if not bs:
                    continue
                brier_mac.append(st.mean(bs))
                n_secim += len(bs)
                # RPS yalnizca Mac Sonucu (MTID 1) icin -- tek sirali market
                ms = sorted([s for s in m["secimler"] if s["mtid"] == 1],
                            key=lambda x: x["idx"])
                if len(ms) == 3:
                    pv = [M.olasilik(1, i, None, t) for i in range(3)]
                    if all(x is not None for x in pv):
                        tot = sum(pv) or 1.0
                        pv = [x / tot for x in pv]
                        g = next((s["idx"] for s in ms if s["tuttu"]), None)
                        if g is not None:
                            rps_mac.append(_rps(pv, g))
            out[ad] = {"brier": brier_mac, "rps": rps_mac, "n_secim": n_secim}
    finally:
        M.XG_AGIRLIK, M.XG_TAVAN = ilk_agirlik, ilk_tavan
    return out


def _kumelenmis_aralik(fark: list[float], tohum: int = 20260821) -> tuple:
    """Mac duzeyinde onyukleme -> (ortalama, alt, ust)."""
    if len(fark) < 5:
        return (st.mean(fark) if fark else 0.0), float("nan"), float("nan")
    random.seed(tohum)
    boot = []
    for _ in range(ONYUKLEME):
        v = [random.choice(fark) for _ in fark]
        boot.append(st.mean(v))
    boot.sort()
    return st.mean(fark), boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot))]


def calis(en_fazla: int = 60):
    maclar, _ = ornek.topla(en_fazla)
    if not maclar:
        print("orneklem yok")
        return
    p = mac_puanlari(maclar)
    temel = p.get(SIMDIKI)
    if not temel or not temel["brier"]:
        print("simdiki ayar icin puan uretilemedi")
        return

    n_mac = len(temel["brier"])
    print(f"\nMODEL PARAMETRESI YENIDEN SINAMASI")
    print(f"olcut: GERCEKLESEN SONUC (Nesine'ye benzerlik DEGIL)")
    print(f"model olasiligi uretilen mac: {n_mac} · secim: {temel['n_secim']}")
    print(f"RPS hesaplanan mac (1X2): {len(temel['rps'])}\n")

    print(f"{'varyant':<24} {'Brier':>8} {'RPS':>8}   {'şimdikine karşı fark':>34}")
    print("-" * 80)
    for ad, _, _ in VARYANTLAR:
        d = p.get(ad)
        if not d or not d["brier"]:
            print(f"{ad:<24} {'-':>8}")
            continue
        b = st.mean(d["brier"])
        r = st.mean(d["rps"]) if d["rps"] else float("nan")
        if ad == SIMDIKI:
            print(f"{ad:<24} {b:>8.4f} {r:>8.4f}   {'(temel)':>34}")
            continue
        n = min(len(d["brier"]), len(temel["brier"]))
        fark = [d["brier"][i] - temel["brier"][i] for i in range(n)]
        ort, alt, ust = _kumelenmis_aralik(fark)
        karar = ("BU DAHA İYİ" if ust < 0 else
                 "şimdiki daha iyi" if alt > 0 else "AYIRT EDİLEMİYOR")
        print(f"{ad:<24} {b:>8.4f} {r:>8.4f}   "
              f"{ort:+.5f} [{alt:+.4f},{ust:+.4f}] {karar}")

    print("\n(fark eksi = o varyant daha iyi · aralık MAÇ düzeyinde kümelenmiş "
          f"önyükleme, n={n_mac} maç)")

    ayirt = [ad for ad, _, _ in VARYANTLAR if ad != SIMDIKI]
    print("\nSONUÇ")
    hicbiri = True
    for ad in ayirt:
        d = p.get(ad)
        if not d or not d["brier"]:
            continue
        n = min(len(d["brier"]), len(temel["brier"]))
        _, alt, ust = _kumelenmis_aralik(
            [d["brier"][i] - temel["brier"][i] for i in range(n)])
        if alt == alt and (ust < 0 or alt > 0):
            hicbiri = False
    if hicbiri:
        print("  Hiçbir varyant şimdikinden AYIRT EDİLEMİYOR.")
        print("  Yani XG_AGIRLIK=%33 ve XG_TAVAN=3,0 seçimini SONUÇ verisiyle")
        print("  haklı çıkaracak kanıt YOK. Bu, 'değiştir' demek değildir --")
        print("  'bu parametrenin gerekçesi hâlâ yazılmadı' demektir.")
        print(f"  Örneklem {n_mac} maç; ayırt etmek için birkaç yüz maç gerekir.")
    print("\nİÇ/DIŞ SAHA AYRIMI bu testte YOK: kod tabanında artık yok "
          "(ölçülüp\ngeri alınmıştı). Yeniden sınamak için önce geri yazmak "
          "gerekir --\nbu bir MODEL DEĞİŞİKLİĞİdir, ölçüm değil.")


if __name__ == "__main__":
    calis(int(sys.argv[1]) if len(sys.argv) > 1 else 60)
