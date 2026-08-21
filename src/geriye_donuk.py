"""GERIYE DONUK KALIBRASYON: arsivdeki oranlar + gerceklesmis sonuclar.

NEDEN: golge kaydinin anlamli sayiya ulasmasi haftalar surer. Ama elimizde
zaten arsivlenmis oranlar ve artik BITMIS maclar var.

SINIR: bu bir BACKTEST'tir, ileriye donuk kanit degildir. Buradaki sonuc
yalnizca TESHIS icin kullanilir, parametre secmek icin DEGIL.

2026-08-21 DUZELTMELERI (konsul, olcum tasarimi elestirisi):
  1. Orneklem uretimi ornek.py'ye tasindi (walkforward.py ile ortak).
  2. ONYUKLEME artik MAC duzeyinde kumelenmis. Onceden secim duzeyindeydi;
     198 secim 43 MACTAN geldigi ve ayni macin secenekleri mekanik olarak
     bagimli oldugu icin (1X2 toplami 1) o aralik SAHTE OLARAK DARDI.
     Etkin orneklem 198 degil ~43'tur.
  3. RPS eklendi: 1X2 SIRALI bir sonuctur, Brier siralamayi yok sayar.
"""
from __future__ import annotations

import random
import statistics as st
import sys
from collections import defaultdict

import model as M
import ornek
import walkforward as WF

ORNEK = int(sys.argv[1]) if len(sys.argv) > 1 else 60


def calis():
    maclar, ist = ornek.topla(ORNEK)
    if not maclar:
        return

    # model olasiliklarini SIMDIKI ayarla hesapla
    kayit = []
    for m in maclar:
        a, b = m.get("ist_ev"), m.get("ist_dep")
        t = M.tahmin(a, b) if a and b else None
        for s in m["secimler"]:
            mp = M.olasilik(s["mtid"], s["idx"], s["sov"], t) if t else None
            kayit.append({"mac": m["mac"], "nesine": s["nesine"], "model": mp,
                          "tuttu": s["tuttu"], "oran": s["oran"],
                          "mtid": s["mtid"]})
    print()

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

    import json
    from pathlib import Path
    __import__("depo").yaz(ornek.DATA / "istatistik.json",
                           json.dumps(ist, ensure_ascii=False, indent=1))

    # ── Model vs Nesine: MAC duzeyinde kumelenmis karsilastirma ──
    mac_fark = []
    ikisi_n = 0
    for m in maclar:
        v = [x for x in kayit
             if x["mac"] == m["mac"] and isinstance(x.get("model"), (int, float))]
        if not v:
            continue
        ikisi_n += len(v)
        bn = st.mean((x["nesine"] - (1 if x["tuttu"] else 0)) ** 2 for x in v)
        bm = st.mean((x["model"] - (1 if x["tuttu"] else 0)) ** 2 for x in v)
        mac_fark.append(bn - bm)          # arti = modelimiz iyi
    if len(mac_fark) < 5:
        print("\nkarsilastirma icin yeterli mac yok")
        return

    print(f"\nMODEL vs NESİNE  ({ikisi_n} seçim, {len(mac_fark)} MAÇ)")
    print(f"  Etkin örneklem SEÇİM değil MAÇ sayısıdır: {len(mac_fark)}")
    ort, alt, ust = WF._kumelenmis_aralik(mac_fark)
    print(f"  maç başı Brier farkı : {ort:+.5f}  (artı = modelimiz iyi)")
    sd = st.pstdev(mac_fark) or 1e-9
    print(f"  t istatistiği        : {ort/(sd/len(mac_fark)**0.5):+.2f}")
    print(f"  %95 KÜMELENMİŞ aralık: [{alt:+.5f}, {ust:+.5f}]")
    if alt > 0:
        print("  → SIFIRDAN FARKLI: modelimiz gerçekten daha isabetli")
    elif ust < 0:
        print("  → SIFIRDAN FARKLI: Nesine daha isabetli")
    else:
        print("  → SIFIR ARALIKTA: fark GÜRÜLTÜDEN AYIRT EDİLEMİYOR.")
        print("    Bu sonuca dayanarak 'modelimiz daha iyi' DENEMEZ.")


if __name__ == "__main__":
    calis()
