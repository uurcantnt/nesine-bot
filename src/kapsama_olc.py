"""Nesine maclarinin kaci ESPN fiksturunde bulunuyor? (toplu yontem)"""
from __future__ import annotations

import collections

import bulletin
import fikstur

snap = bulletin.simplify(bulletin.fetch())
maclar = [e for e in snap["olay"] if e.get("ev") and e.get("dep")]
print(f"Nesine bulteni: {len(maclar)} futbol maci")

ix = fikstur.indeks(gunler=3)
print(f"ESPN fiksturu : {len(ix)} mac\n")

if not ix:
    print("!! ESPN fiksturu BOS -- CLI cikti semasi degismis olabilir")
    raise SystemExit(0)

say = collections.Counter()
ornek = []
for e in maclar:
    m = fikstur.esle(ix, e["ev"], e["dep"])
    say["bulundu" if m else "yok"] += 1
    if m and len(ornek) < 14:
        ornek.append((e["ev"], e["dep"], m["ev"], m["dep"]))

n = len(maclar)
print(f"=== KAPSAMA ===")
print(f"  bulundu: {say['bulundu']:>4} / {n}  (%{100*say['bulundu']/n:.1f})")
print(f"  yok    : {say['yok']:>4} / {n}  (%{100*say['yok']/n:.1f})")
print("\n=== ESLESEN ORNEKLER ===")
for a, b, c, d in ornek:
    print(f"  {a[:20]:<20} - {b[:20]:<20}  ->  {c[:22]:<22} - {d[:22]}")
