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


def _zaman(iso):
    """Fotmob utcTime -> epoch saniye. Cozulemezse None."""
    if not iso:
        return None
    try:
        from datetime import datetime
        return datetime.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S").timestamp()
    except Exception:
        return None


def esle(ev: str, dep: str, ts=None):
    """Nesine macini Fotmob fiksturunde bul.

    KADEMELER: tam ad -> en iyi alt-dize -> kelime ortusmesi.
    Ortusme esigi 0,6 idi ve GERCEK maclar dusuyordu:

      Nesine "Nottingham F. - Leeds Utd"  -> 'nottingham f' / 'leeds utd'
      Fotmob "Nottm Forest - Leeds"       -> 'nottm forest' / 'leeds'
      ev benzerligi 0,00 · dep 1,00 -> ortalama 0,50 < 0,60  ELENDI
    Sonuc: PREMIER LIG maci "dis istatistik verisinde bulunamadi" diyordu
    (kullanici bildirdi, 2026-08-22).

    Esigi korlemesine dusurmek yanlis eslesme riskini artirir -- ve yanlis
    eslesme HATA FIRLATMAZ, sessizce yanlis istatistik uretir. Bu yuzden
    daha guclu bir kanit eklendi: BASLANGIC SAATI. Ayni dakikada baslayan
    ve bir takimi tam tutan mac ayni mactir. Saat kanidi varsa esik 0,50,
    yoksa 0,60 kalir.
    """
    import stats as S
    h = S.sadelestir(S.ELLE.get(ev.lower(), ev))
    a = S.sadelestir(S.ELLE.get(dep.lower(), dep))
    if (h, a) in ix:
        return ix[(h, a)]
    en_iyi, en_fark = None, None
    for (ih, ia), v in ix.items():
        if (h and ih and (h in ih or ih in h)) and (a and ia and (a in ia or ia in a)):
            fark = abs(len(ih) - len(h)) + abs(len(ia) - len(a))
            if en_fark is None or fark < en_fark:
                en_iyi, en_fark = v, fark
    if en_iyi is not None:
        return en_iyi
    ort = lambda x, y: (len(set(x.split()) & set(y.split()))
                        / max(1, min(len(x.split()), len(y.split()))))
    en, es, saatli = None, 0.0, False
    for (ih, ia), v in ix.items():
        sk = (ort(h, ih) + ort(a, ia)) / 2
        if sk <= es:
            continue
        vt = _zaman(v.get("ts"))
        en, es = v, sk
        saatli = bool(ts and vt and abs(vt - ts) <= 600)   # ±10 dk
    if en is None:
        return None
    return en if es >= (0.5 if saatli else 0.6) else None


# ── eslesme + takim listesi ────────────────────────────────────────────
eslesme, takimlar = {}, {}
for e in snap["olay"]:
    m = esle(e.get("ev", ""), e.get("dep", ""),
             (e.get("ts") / 1000) if e.get("ts") else None)
    if not m:
        continue
    eslesme[str(e["id"])] = {"ev": str(m["ev_id"]), "dep": str(m["dep_id"]),
                             "espn_ev": m["ev"], "espn_dep": m["dep"],
                             "fotmob_id": m["id"], "lig": m.get("lig")}
    takimlar[str(m["ev_id"])] = m["ev"]
    takimlar[str(m["dep_id"])] = m["dep"]
print(f"eslesen mac {len(eslesme)} · farkli takim {len(takimlar)}")
__import__("depo").yaz(DATA / "eslesme.json", json.dumps(eslesme, ensure_ascii=False, indent=1))

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
        __import__("depo").yaz(DATA / "referans.json", json.dumps(ref, ensure_ascii=False, indent=1))
        print(f"referans (DraftKings): {len(ref)} mac")
    else:
        print("referans: sonuc BOS — mevcut dosya korundu")
except Exception as e:
    print(f"referans atlandi: {e}")
