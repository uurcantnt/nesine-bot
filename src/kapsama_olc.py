"""Nesine maclarinin kaci ESPN istatistik verisinde bulunabiliyor?

Bu ORNEKLEM bir olcumdur, karar icin gereken tek rakam budur: kapsama
dusukse istatistik yonu bastan sinirlidir.
"""
from __future__ import annotations

import collections
import random

import bulletin
import stats

ORNEK = 60          # her arama ~0,3 sn; 60 mac yeterli tahmin verir

snap = bulletin.simplify(bulletin.fetch())
maclar = [e for e in snap["olay"] if e.get("ev") and e.get("dep")]
random.seed(20260821)
ornek = random.sample(maclar, min(ORNEK, len(maclar)))

bulunan = collections.Counter()
onbellek: dict = {}
detay = []
for e in ornek:
    sonuc = []
    for takim in (e["ev"], e["dep"]):
        if takim not in onbellek:
            onbellek[takim] = stats.espn_ara(takim)
        sonuc.append(onbellek[takim])
    ikisi = all(sonuc)
    bulunan["ikisi_de" if ikisi else ("biri" if any(sonuc) else "hicbiri")] += 1
    detay.append((e["ev"], e["dep"], sonuc[0], sonuc[1]))

n = len(ornek)
print(f"\n=== ORNEKLEM {n} MAC ===")
for k in ("ikisi_de", "biri", "hicbiri"):
    print(f"  {k:<9}: {bulunan[k]:>3}  (%{100*bulunan[k]/n:.0f})")
print("\n=== ORNEKLER ===")
for ev, dep, a, b in detay[:22]:
    ok = "✓" if (a and b) else "✗"
    print(f"  {ok} {ev[:22]:<22} -> {(a or {}).get('ad','-')[:24]:<24} | "
          f"{dep[:22]:<22} -> {(b or {}).get('ad','-')[:24]}")
