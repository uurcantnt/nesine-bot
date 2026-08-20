"""Nesine ile DraftKings ne kadar ayrisiyor? KARAR VERICI OLCUM.

Basabas icin gereken sapma, Nesine'nin marjina esittir (~%21 goreli).
Bu olcum, sapmalarin o esige HIC yaklasip yaklasmadigini soyler.
"""
from __future__ import annotations

import statistics as st

import bulletin
import fikstur
import odds as O
import referans

snap = bulletin.simplify(bulletin.fetch())
ix = fikstur.indeks(gunler=3)
print(f"Nesine {len(snap['olay'])} mac · ESPN fikstur {len(ix)} mac\n")

dk_marj, ns_marj, sapmalar, satir = [], [], [], []
for e in snap["olay"]:
    m = fikstur.esle(ix, e.get("ev", ""), e.get("dep", ""))
    if not m:
        continue
    ml = referans.moneyline(m["espn"])
    ns = e["m"].get("1")
    if not ml or not ns:
        continue
    o = ns["o"]
    if any(x is None or x <= 1.0 for x in o):
        continue
    np_ = O.devig(o, 1)
    nm = O.overround(o, 1)
    if np_ is None:
        continue
    dk_marj.append(ml["marj"])
    ns_marj.append(nm)
    for i, ad in enumerate(("1", "X", "2")):
        if ml["p"][i] <= 0:
            continue
        # Nesine, DK'ya gore bu secenege NE KADAR daha iyi fiyat veriyor?
        # deger = (DK olasiligi x Nesine orani) - 1
        deger = ml["p"][i] * o[i] - 1
        sapmalar.append(deger)
        satir.append((deger, f"{e['ev']} - {e['dep']}", ad, o[i],
                      np_[i], ml["p"][i]))

print(f"karsilastirilan mac: {len(dk_marj)} · secenek: {len(sapmalar)}")
if dk_marj:
    print(f"\nMARJ KARSILASTIRMASI")
    print(f"  DraftKings : medyan %{st.median(dk_marj)*100:.1f}")
    print(f"  Nesine     : medyan %{st.median(ns_marj)*100:.1f}")
if sapmalar:
    s = sorted(sapmalar)
    print(f"\nDEGER DAGILIMI  (DK olasiligi x Nesine orani - 1)")
    for q, ad in ((0.05, "p05"), (0.5, "medyan"), (0.9, "p90"),
                  (0.99, "p99"), (1.0, "en yuksek")):
        v = s[min(len(s) - 1, int(q * (len(s) - 1)))]
        print(f"  {ad:>9}: {v*100:+.1f}%")
    arti = [x for x in s if x > 0]
    print(f"\n  POZITIF degerli secenek: {len(arti)} / {len(s)} "
          f"(%{100*len(arti)/len(s):.1f})")
    satir.sort(key=lambda x: -x[0])
    print("\n=== EN YUKSEK DEGERLI 10 SECENEK ===")
    print(f"  {'deger':>7}  {'mac':<40} {'sec':<4} {'oran':>6} {'Nesine%':>8} {'DK%':>6}")
    for d, mac, ad, oran, npp, dkp in satir[:10]:
        print(f"  {d*100:+6.1f}%  {mac[:40]:<40} {ad:<4} {oran:>6} "
              f"{npp*100:>7.1f}% {dkp*100:>5.1f}%")
