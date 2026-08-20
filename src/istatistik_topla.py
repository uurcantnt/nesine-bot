"""Yarinki Nesine maclarinda oynayan takimlarin istatistiklerini topla."""
from __future__ import annotations

import sys
import time

import bulletin
import fikstur
import istatistik

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 40

snap = bulletin.simplify(bulletin.fetch())
ix = fikstur.indeks(gunler=3)
print(f"Nesine: {len(snap['olay'])} mac | ESPN fikstur: {len(ix)} mac")

# eslesen maclardan takim id'lerini cikar
takimlar: dict = {}
for e in snap["olay"]:
    m = fikstur.esle(ix, e.get("ev", ""), e.get("dep", ""))
    if not m:
        continue
    for c in (m["espn"].get("competitors") or []):
        tid = str((c.get("team") or {}).get("id") or "")
        if tid:
            takimlar[tid] = (c.get("team") or {}).get("name") or tid
print(f"eslesen maclardaki farkli takim: {len(takimlar)}")

onb = istatistik.yukle()
t0 = time.time()
yeni = atlanan = hata = 0
for i, (tid, ad) in enumerate(list(takimlar.items())[:LIMIT], 1):
    if tid in onb and istatistik.taze(onb[tid]):
        atlanan += 1
        continue
    v = istatistik.takim_verisi(tid)
    if not v:
        hata += 1
        print(f"  [{i}] {ad}: veri yok")
        continue
    v["ad"] = ad
    onb[tid] = v
    yeni += 1
    print(f"  [{i}] {ad}: {v['mac']} mac · gol {v['gol_at']:.2f}/{v['gol_ye']:.2f}"
          f" · korner {v['korner'] if v['korner'] is None else round(v['korner'],1)}"
          f" · kart {v['kart'] if v['kart'] is None else round(v['kart'],1)}")

istatistik.kaydet(onb)
print(f"\nyeni {yeni} · onbellekten {atlanan} · hatali {hata} "
      f"· sure {time.time()-t0:.0f}s · toplam kayit {len(onb)}")
