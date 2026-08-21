"""GERIYE DONUK KALIBRASYON: arsivdeki oranlar + gerceklesmis sonuclar.

NEDEN: golge kaydinin anlamli sayiya ulasmasi haftalar surer. Ama elimizde
zaten arsivlenmis oranlar ve artik BITMIS maclar var. Bu ikisini birlestirip
"Nesine %60 dediginde gercekten %60 oluyor mu, modelimiz ne kadar isabetli"
sorusunu BUGUN cevaplayabiliriz.

SINIR: bu bir BACKTEST'tir, ileriye donuk kanit degildir. Ayni veriyle model
ayarlanirsa asiri uyum olur -- o yuzden buradaki sonuc yalnizca TESHIS icin
kullanilir, parametre secmek icin DEGIL.
"""
from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import bulletin
import model as M
import odds as O
import sonuc as S

DATA = Path(__file__).resolve().parent.parent / "data"
ORNEK = int(sys.argv[1]) if len(sys.argv) > 1 else 60


def calis():
    esl = json.loads((DATA / "eslesme.json").read_text(encoding="utf-8"))
    ist = json.loads((DATA / "istatistik.json").read_text(encoding="utf-8"))
    # arsivdeki en eski TAM snapshot: o anki oranlar
    dosyalar = sorted(bulletin.ARSIV.glob("*/*.json.gz"))
    tam = [f for f in dosyalar if bulletin.load(f).get("tam")]
    if not tam:
        print("arsivde tam snapshot yok")
        return
    snap = bulletin.load(tam[0])
    print(f"arsiv: {tam[0].parent.name}/{tam[0].name} · {len(snap['olay'])} mac\n")

    # Arsivdeki maclar DUNE ait; eslesme.json BUGUNKU fiksturden kuruldu,
    # kesisim bos cikiyordu. Bu yuzden Fotmob'un BITMIS maclariyla dogrudan
    # isim eslestirmesi yapilir.
    import fotmob
    import stats as ST
    from datetime import timedelta
    bitmis = {}
    for gk in (0, -1):
        try:
            gun = (bulletin.datetime.now(bulletin.timezone.utc)
                   + timedelta(days=gk)).strftime("%Y%m%d")
            d = fotmob._get(fotmob.LISTE.format(gun))
        except Exception:
            continue
        for L in d.get("leagues") or []:
            for m in L.get("matches") or []:
                if not (m.get("status") or {}).get("finished"):
                    continue
                h = (m.get("home") or {}).get("name")
                a2 = (m.get("away") or {}).get("name")
                if h and a2:
                    bitmis[(ST.sadelestir(h), ST.sadelestir(a2))] = {
                        "id": m.get("id"),
                        "ev_id": str((m.get("home") or {}).get("id")),
                        "dep_id": str((m.get("away") or {}).get("id"))}
    print(f"fotmob bitmis mac: {len(bitmis)}")

    def bul(ev, dep):
        h = ST.sadelestir(ST.ELLE.get(ev.lower(), ev))
        a2 = ST.sadelestir(ST.ELLE.get(dep.lower(), dep))
        if (h, a2) in bitmis:
            return bitmis[(h, a2)]
        for (ih, ia), v in bitmis.items():
            if (h and ih and (h in ih or ih in h)) and (a2 and ia and (a2 in ia or ia in a2)):
                return v
        return None

    kayit = []
    bakilan = 0
    eksik_denendi = set()
    for e in snap["olay"]:
        if bakilan >= ORNEK:
            break
        fm = bul(e.get("ev") or "", e.get("dep") or "")
        if not fm:
            continue
        s = S.mac_sonucu(fm["id"])
        if not s:
            continue
        bakilan += 1
        # Takim istatistigi DOGRUDAN fotmob takim id'siyle bulunur.
        # Onbellekte yoksa ANINDA cekilir (dunku takimlar bugunku toplamada
        # yok; onlarsiz model karsilastirmasi yapilamiyordu).
        a, b = ist.get(fm["ev_id"]), ist.get(fm["dep_id"])
        for tid, mevcut in ((fm["ev_id"], a), (fm["dep_id"], b)):
            if mevcut is None and tid not in eksik_denendi:
                eksik_denendi.add(tid)
                v = fotmob.takim_verisi(tid)
                if v:
                    ist[tid] = v
        a, b = ist.get(fm["ev_id"]), ist.get(fm["dep_id"])
        t = M.tahmin(a, b) if a and b else None
        for mtid_s, m in e["m"].items():
            mtid = int(mtid_s)
            o = m.get("o") or []
            if m.get("ms") != 1 or any(x is None or x <= 1 for x in o):
                continue
            p = O.devig(o, 2 if mtid in (3, 8) else 1)
            if not p:
                continue
            for i in range(len(o)):
                r = S.degerlendir(mtid, i, m.get("sov"), s)
                if r is None:
                    continue
                mp = M.olasilik(mtid, i, m.get("sov"), t) if t else None
                kayit.append({"nesine": p[i], "model": mp, "tuttu": bool(r),
                              "oran": o[i], "mtid": mtid})
    print(f"degerlendirilen mac {bakilan} · secim {len(kayit)}\n")
    if not kayit:
        return

    def olc(ad, alan):
        v = [x for x in kayit if isinstance(x.get(alan), (int, float))]
        if len(v) < 20:
            print(f"  {ad:<12} yetersiz ({len(v)})")
            return
        tahmin = st.mean(x[alan] for x in v)
        gercek = sum(1 for x in v if x["tuttu"]) / len(v)
        brier = st.mean((x[alan] - (1 if x["tuttu"] else 0)) ** 2 for x in v)
        print(f"  {ad:<12} n={len(v):<6} ortalama tahmin %{tahmin*100:.1f} → "
              f"gerçekleşen %{gercek*100:.1f} · Brier {brier:.4f}")

    print("KALİBRASYON")
    olc("Nesine", "nesine")
    olc("Modelimiz", "model")

    print("\nOLASILIK DİLİMLERİ (Nesine ne dedi → ne oldu)")
    kova = defaultdict(list)
    for x in kayit:
        kova[min(9, int(x["nesine"] * 10))].append(x["tuttu"])
    for d in sorted(kova):
        v = kova[d]
        if len(v) < 15:
            continue
        print(f"  %{d*10:>2}-%{d*10+10:<3} n={len(v):<5} gerçekleşen "
              f"%{100*sum(v)/len(v):.1f}")

    # cekilen yeni takim verilerini onbellege yaz
    __import__("depo").yaz(DATA / "istatistik.json", json.dumps(ist, ensure_ascii=False, indent=1))

    ikisi = [x for x in kayit if isinstance(x.get("model"), (int, float))]
    if len(ikisi) >= 30:
        bn = st.mean((x["nesine"] - (1 if x["tuttu"] else 0)) ** 2 for x in ikisi)
        bm = st.mean((x["model"] - (1 if x["tuttu"] else 0)) ** 2 for x in ikisi)
        print(f"\nAYNI {len(ikisi)} SEÇİMDE KARŞILAŞTIRMA")
        print(f"  Nesine Brier    {bn:.4f}")
        print(f"  Modelimiz Brier {bm:.4f}")
        print(f"  → {'MODELİMİZ' if bm < bn else 'NESİNE'} daha isabetli "
              f"({abs(bm-bn):.4f} fark)")
        # ANLAMLI MI? Eslestirilmis fark uzerinden t ve onyukleme.
        # (Kripto botu dersi: kucuk orneklemde 'daha iyi' cikan her sey
        #  gurultu olabilir; olcmeden iddia edilmez.)
        import random
        fark = [((x["nesine"] - (1 if x["tuttu"] else 0)) ** 2
                 - (x["model"] - (1 if x["tuttu"] else 0)) ** 2) for x in ikisi]
        ort = st.mean(fark)
        sd = st.pstdev(fark) or 1e-9
        tstat = ort / (sd / len(fark) ** 0.5)
        random.seed(20260821)
        boot = []
        for _ in range(4000):
            ornek = [random.choice(fark) for _ in fark]
            boot.append(st.mean(ornek))
        boot.sort()
        alt, ust = boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot))]
        print("")
        print(f"  ANLAMLILIK (eslestirilmis fark, n={len(fark)})")
        print(f"    ortalama Brier farki : {ort:+.5f}  (arti = modelimiz iyi)")
        print(f"    t istatistigi        : {tstat:+.2f}")
        print(f"    %95 onyukleme araligi: [{alt:+.5f}, {ust:+.5f}]")
        if alt > 0:
            print("    → SIFIRDAN FARKLI: modelimiz gercekten daha isabetli")
        elif ust < 0:
            print("    → SIFIRDAN FARKLI: Nesine daha isabetli")
        else:
            print("    → SIFIR ARALIKTA: fark GURULTUDEN AYIRT EDILEMIYOR.")
            print("      Bu sonuca dayanarak 'modelimiz daha iyi' DENEMEZ.")


if __name__ == "__main__":
    calis()
