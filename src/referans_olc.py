"""Nesine vs DraftKings — TUM marketler + "en ucuz mu = en az kaybettiren mi" testi.

Basabas icin gereken sapma Nesine'nin marjina esittir. Bu olcum sapmalarin
o esige yaklasip yaklasmadigini ve MARKET ICINDEKI dagilimi gosterir.
"""
from __future__ import annotations

import statistics as st
from collections import defaultdict

import bulletin
import catalog
import fikstur
import odds as O
import referans

snap = bulletin.simplify(bulletin.fetch())
ix = fikstur.indeks(gunler=3)
print(f"Nesine {len(snap['olay'])} mac · ESPN fikstur {len(ix)} mac\n")

# (market_adi, nesine_mtid, secenek_indeksleri, dk_olasilik_fonksiyonu)
kayit = defaultdict(list)      # market -> [(deger, marj, mac, secenek, oran, ns_p, dk_p)]
marjlar = defaultdict(lambda: ([], []))

for e in snap["olay"]:
    m = fikstur.esle(ix, e.get("ev", ""), e.get("dep", ""),
                        (e.get("ts") or 0) / 1000 or None)
    if not m:
        continue
    espn = m["espn"]
    mac = f"{e['ev']} - {e['dep']}"

    # ---- 1) MAC SONUCU (moneyline) ----
    ml = referans.moneyline(espn)
    ns = e["m"].get("1")
    if ml and ns:
        o = ns["o"]
        p = O.devig(o, 1)
        if p and all(x and x > 1 for x in o):
            marjlar["Maç Sonucu"][0].append(ml["marj"])
            marjlar["Maç Sonucu"][1].append(O.overround(o, 1))
            for i, ad in enumerate(("1", "X", "2")):
                kayit["Maç Sonucu"].append(
                    (ml["p"][i] * o[i] - 1, O.overround(o, 1), mac, ad, o[i], p[i], ml["p"][i]))

    # ---- 2) ALT/UST (DK cizgisi hangisiyse Nesine'de karsiligini bul) ----
    tp = referans.toplam(espn)
    if tp and tp.get("cizgi") is not None:
        cizgi = float(tp["cizgi"])
        mtid = {1.5: 11, 2.5: 12, 3.5: 13}.get(cizgi)
        ns2 = e["m"].get(str(mtid)) if mtid else None
        if ns2:
            o = ns2["o"]
            p = O.devig(o, 1)
            if p and all(x and x > 1 for x in o):
                ad_m = f"{cizgi:g} Gol Alt/Üst".replace(".", ",")
                marjlar[ad_m][0].append(tp["marj"])
                marjlar[ad_m][1].append(O.overround(o, 1))
                for i, (ad, dkp) in enumerate((("Alt", tp["p_alt"]), ("Üst", tp["p_ust"]))):
                    kayit[ad_m].append(
                        (dkp * o[i] - 1, O.overround(o, 1), mac, ad, o[i], p[i], dkp))

print(f"{'MARKET':<22} {'n':>4} {'DK marj':>8} {'NS marj':>8} {'en iyi':>8} {'medyan':>8} {'pozitif':>8}")
print("-" * 74)
for ad, satirlar in sorted(kayit.items(), key=lambda kv: -len(kv[1])):
    d = sorted(x[0] for x in satirlar)
    dk, ns_ = marjlar[ad]
    poz = sum(1 for x in d if x > 0)
    print(f"{ad:<22} {len(d):>4} "
          f"{st.median(dk)*100:>7.1f}% {st.median(ns_)*100:>7.1f}% "
          f"{d[-1]*100:>+7.1f}% {st.median(d)*100:>+7.1f}% {poz:>5}/{len(d)}")

print("\n" + "=" * 74)
print('SORU: "en ucuz market" = "en az kaybettiren secenek" mi?')
print("=" * 74)
# ayni market ORNEGI icinde secenekler arasi deger farki
icsel = []
for ad, satirlar in kayit.items():
    gruplar = defaultdict(list)
    for deger, marj, mac, sec, oran, nsp, dkp in satirlar:
        gruplar[(mac, ad)].append(deger)
    for k, v in gruplar.items():
        if len(v) >= 2:
            icsel.append(max(v) - min(v))
if icsel:
    icsel.sort()
    print(f"\nAYNI maçın AYNI marketinde, secenekler arasi deger farki (n={len(icsel)}):")
    print(f"  medyan: {st.median(icsel)*100:.1f} puan")
    print(f"  p90   : {icsel[int(0.9*(len(icsel)-1))]*100:.1f} puan")
    print(f"  maks  : {icsel[-1]*100:.1f} puan")
    print("\n  -> Marj MARKET seviyesinde tektir ama secenekler arasi deger")
    print("     bu kadar farkli. Yani 'en dusuk marjli market' secmek,")
    print("     'en az kaybettiren SECENEK' i secmekle AYNI SEY DEGILDIR.")

# en dusuk marjli secenekler gercekten en degerli mi?
tum = [x for v in kayit.values() for x in v]
if len(tum) > 20:
    marja_gore = sorted(tum, key=lambda x: x[1])[:20]
    degere_gore = sorted(tum, key=lambda x: -x[0])[:20]
    print(f"\nEN DUSUK MARJLI 20 secenegin ortalama degeri : "
          f"{st.mean([x[0] for x in marja_gore])*100:+.1f}%")
    print(f"EN YUKSEK DEGERLI 20 secenegin ortalama degeri: "
          f"{st.mean([x[0] for x in degere_gore])*100:+.1f}%")
    ortak = len({(x[2], x[3]) for x in marja_gore} & {(x[2], x[3]) for x in degere_gore})
    print(f"Iki listenin KESISIMI: {ortak}/20 secenek")
