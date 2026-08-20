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
    lig = ((m["espn"].get("competition") or {}).get("id")
           or (m["espn"].get("league") or {}).get("slug"))
    for c in (m["espn"].get("competitors") or []):
        tid = str((c.get("team") or {}).get("id") or "")
        if tid:
            takimlar[tid] = ((c.get("team") or {}).get("name") or tid, lig)
print(f"eslesen maclardaki farkli takim: {len(takimlar)}")

onb = istatistik.yukle()
t0 = time.time()
yeni = atlanan = hata = 0
for i, (tid, (ad, lig)) in enumerate(list(takimlar.items())[:LIMIT], 1):
    if tid in onb and istatistik.taze(onb[tid]):
        atlanan += 1
        continue
    v = istatistik.takim_verisi(tid, lig)
    if not v:
        hata += 1
        print(f"  [{i}] {ad}: veri yok")
        continue
    v["ad"] = ad
    onb[tid] = v
    yeni += 1
    print(f"  [{i}] {ad} ({lig}): {v['mac']} mac · gol {v['gol_at']:.2f}/{v['gol_ye']:.2f}"
          f" · korner {v['korner'] if v['korner'] is None else round(v['korner'],1)}"
          f" · sari {v['sari'] if v['sari'] is None else round(v['sari'],1)}"
          f" · kirmizi {v['kirmizi'] if v['kirmizi'] is None else round(v['kirmizi'],2)}")

# Nesine mac id -> ESPN takim id eslesmesi; /kupon bunu okur, ESPN'e GITMEZ
eslesme = {}
for e in snap["olay"]:
    m = fikstur.esle(ix, e.get("ev", ""), e.get("dep", ""))
    if not m:
        continue
    rak = m["espn"].get("competitors") or []
    ev_t = next((c for c in rak if c.get("qualifier") == "home"), None)
    dep_t = next((c for c in rak if c.get("qualifier") == "away"), None)
    if ev_t and dep_t:
        eslesme[str(e["id"])] = {
            "ev": str((ev_t.get("team") or {}).get("id")),
            "dep": str((dep_t.get("team") or {}).get("id")),
            "espn_ev": (ev_t.get("team") or {}).get("name"),
            "espn_dep": (dep_t.get("team") or {}).get("name"),
        }
import json as _json
(istatistik.ONBELLEK.parent / "eslesme.json").write_text(
    _json.dumps(eslesme, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"eslesme dosyasi: {len(eslesme)} mac")

istatistik.kaydet(onb)
print(f"\nyeni {yeni} · onbellekten {atlanan} · hatali {hata} "
      f"· sure {time.time()-t0:.0f}s · toplam kayit {len(onb)}")
