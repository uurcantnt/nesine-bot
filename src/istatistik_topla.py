"""Fotmob'dan takim istatistiklerini topla (mac oncesi model icin).

ESPN'DEN NEDEN GECILDI (olculdu 2026-08-21):
  kapsama: ESPN 89/964 mac (%9,2) · Fotmob 642/964 (%66,6)
  maliyet: ESPN takim basina ~10 istek · Fotmob TEK istek
  veri   : Fotmob ayrica xG, xG yenilen, topla oynama, isabetli sut veriyor
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import bulletin
import fotmob
import istatistik
import odds as O
import referans

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 400
DATA = Path(__file__).resolve().parent.parent / "data"

snap = bulletin.simplify(bulletin.fetch())
ix = fotmob.fikstur_indeks(gunler=3)
print(f"Nesine {len(snap['olay'])} mac · Fotmob fikstur {len(ix)} mac\n")


def esle(ev: str, dep: str):
    import stats as S
    h = S.sadelestir(S.ELLE.get(ev.lower(), ev))
    a = S.sadelestir(S.ELLE.get(dep.lower(), dep))
    if (h, a) in ix:
        return ix[(h, a)]
    for (ih, ia), v in ix.items():
        if (h and ih and (h in ih or ih in h)) and (a and ia and (a in ia or ia in a)):
            return v
    ort = lambda x, y: (len(set(x.split()) & set(y.split()))
                        / max(1, min(len(x.split()), len(y.split()))))
    en, es = None, 0.0
    for (ih, ia), v in ix.items():
        s = (ort(h, ih) + ort(a, ia)) / 2
        if s > es:
            en, es = v, s
    return en if es >= 0.6 else None


# ── eslesme + takim listesi ────────────────────────────────────────────
eslesme, takimlar = {}, {}
for e in snap["olay"]:
    m = esle(e.get("ev", ""), e.get("dep", ""))
    if not m:
        continue
    eslesme[str(e["id"])] = {"ev": str(m["ev_id"]), "dep": str(m["dep_id"]),
                             "espn_ev": m["ev"], "espn_dep": m["dep"],
                             "fotmob_id": m["id"], "lig": m.get("lig")}
    takimlar[str(m["ev_id"])] = m["ev"]
    takimlar[str(m["dep_id"])] = m["dep"]
print(f"eslesen mac {len(eslesme)} · farkli takim {len(takimlar)}")
(DATA / "eslesme.json").write_text(json.dumps(eslesme, ensure_ascii=False, indent=1),
                                   encoding="utf-8")

# ── takim verileri ─────────────────────────────────────────────────────
onb = istatistik.yukle()
t0 = time.time()
yeni = atlanan = hata = 0
for i, (tid, ad) in enumerate(list(takimlar.items())[:LIMIT], 1):
    kayit = onb.get(tid)
    if kayit and kayit.get("kaynak") == "fotmob" and istatistik.taze(kayit):
        atlanan += 1
        continue
    v = fotmob.takim_verisi(tid)
    if not v:
        hata += 1
        continue
    v.setdefault("ad", ad)
    onb[tid] = v
    yeni += 1
    if yeni <= 25 or yeni % 50 == 0:
        print(f"  [{i}] {v.get('ad') or ad}: {v['mac']} maç · "
              f"gol {v['gol_at']:.2f}/{v['gol_ye']:.2f} · korner {v.get('korner')} "
              f"· xG {v.get('xg')}")
istatistik.kaydet(onb)
print(f"\nyeni {yeni} · onbellekten {atlanan} · verisiz {hata} "
      f"· sure {time.time()-t0:.0f}s · toplam {len(onb)}")

# ── DraftKings referansi (ESPN gunluk programindan; Fotmob oran vermiyor) ──
try:
    import fikstur
    eix = fikstur.indeks(gunler=3)
    ref = {}
    for e in snap["olay"]:
        m = fikstur.esle(eix, e.get("ev", ""), e.get("dep", ""),
                         (e.get("ts") or 0) / 1000 or None)
        if not m:
            continue
        kayit = {}
        ml = referans.moneyline(m["espn"])
        if ml:
            kayit["1"] = ml["p"]
            kayit["3"] = [ml["p"][0] + ml["p"][1], ml["p"][0] + ml["p"][2],
                          ml["p"][1] + ml["p"][2]]
            kayit["dk_marj"] = ml["marj"]
        tp = referans.toplam(m["espn"])
        if tp and tp.get("cizgi") is not None:
            mt = {1.5: "11", 2.5: "12", 3.5: "13"}.get(float(tp["cizgi"]))
            if mt:
                kayit[mt] = [tp["p_alt"], tp["p_ust"]]
        if kayit:
            ref[str(e["id"])] = kayit
    # BOS SONUCLA UZERINE YAZMA: yerelde sports-skills yokken referans.json
    # 0 kayitla eziliyordu (veri kaybi).
    if ref:
        (DATA / "referans.json").write_text(
            json.dumps(ref, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"referans (DraftKings): {len(ref)} mac")
    else:
        print("referans: sonuc BOS — mevcut dosya korundu")
except Exception as e:
    print(f"referans atlandi: {e}")
