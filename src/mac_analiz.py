"""Tek bir mac icin botun TUM hesabini dok — /mac komutu.

Amac: "bot bu maci neden onerdi / neden onermedi" sorusunun tam cevabi.
Gizli hesap yok; ham veri, model adimlar, tum secenekler ve siralar.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bulletin
import model as M
import tiers
import trtime

KOK = Path(__file__).resolve().parent.parent / "data"


def _oku(ad: str) -> dict:
    try:
        return json.loads((KOK / ad).read_text(encoding="utf-8"))
    except Exception:
        return {}


def analiz(arama: str) -> str:
    snap = bulletin.latest()
    if not snap:
        return "Bülten arşivi yok."
    a = arama.lower().strip()
    bulunan = [e for e in snap["olay"]
               if a in (e.get("ev") or "").lower() or a in (e.get("dep") or "").lower()]
    if not bulunan:
        return f"'{arama}' için maç bulunamadı."
    if len(bulunan) > 1:
        L = [f"'{arama}' için {len(bulunan)} maç var, birini seç:"]
        for e in bulunan[:8]:
            L.append(f"  /mac {e['ev']}   →  {e['ev']} - {e['dep']}")
        return "\n".join(L)

    e = bulunan[0]
    ist, esl, ref = _oku("istatistik.json"), _oku("eslesme.json"), _oku("referans.json")
    d = trtime.yerel(__import__("datetime").datetime.fromtimestamp(
        e["ts"] / 1000, tz=__import__("datetime").timezone.utc))
    L = [f"🔍 {e['ev']} - {e['dep']}"]
    if e.get("lig_ad"):
        L.append(f"🏆 {e['lig_ad']}")
    L.append(f"🕐 {d.strftime('%d.%m %H:%M')}")

    ek = esl.get(str(e["id"])) or {}
    ev_i, dep_i = ist.get(ek.get("ev", "")), ist.get(ek.get("dep", ""))
    L += ["", "1️⃣ ELİMİZDEKİ HAM VERİ"]
    if ev_i and dep_i:
        for ad, v in ((e["ev"], ev_i), (e["dep"], dep_i)):
            L.append(f"   {ad[:22]:<22} son {v['mac']} maç · "
                     f"{v['gol_at']:.2f} attı / {v['gol_ye']:.2f} yedi"
                     + (f" · {v['korner']:.1f} korner" if v.get("korner") else ""))
    else:
        L.append("   ❌ Bu maç dış istatistik verisinde YOK "
                 "(ESPN büyük ligleri kapsıyor, hepsini değil)")

    if ev_i and dep_i:
        t = M.tahmin(ev_i, dep_i)
        g = t["gol"]
        L += ["", "2️⃣ MODELİN HESABI"]
        L.append(f"   ev beklenen gol  = ({ev_i['gol_at']:.2f} + {dep_i['gol_ye']:.2f})/2 "
                 f"× 1,15 = {g['ev_lambda']:.2f}")
        L.append(f"   dep beklenen gol = ({dep_i['gol_at']:.2f} + {ev_i['gol_ye']:.2f})/2 "
                 f"× 0,90 = {g['dep_lambda']:.2f}")
        L.append(f"   → MS1 %{g['MS1']*100:.0f} · X %{g['MSX']*100:.0f} · "
                 f"MS2 %{g['MS2']*100:.0f}")
        L.append("   ⚠️ Model rakip GÜCÜNÜ hesaba katmaz; büyük takımların")
        L.append("      ortalamasını orta takımlarla eşit sayar. Bilinen zaaf.")

    havuz = tiers._sirala(tiers.tahmin_birlestir(
        tiers.model_ekle(tiers.referans_ekle(tiers.pre_adaylar(snap)))))
    bu = sorted([x for x in havuz if x["id"] == e["id"]], key=lambda z: z["sira"])
    L += ["", f"3️⃣ BU MAÇIN SEÇENEKLERİ ({len(bu)} tanesi filtreleri geçti)"]
    if not bu:
        L.append("   Hiçbiri geçmedi (oran aralığı / marj / saat penceresi).")
    for x in bu[:10]:
        mp = f"%{x['model_p']*100:.0f}" if x.get("model_p") is not None else "—"
        dk = f"%{x['dk_p']*100:.0f}" if x.get("dk_p") is not None else "—"
        L.append(f"   {x['market'][:20]:<20} {x['secenek']:<7} @{x['oran']:<5} "
                 f"Nesine %{x['olasilik']*100:<3.0f} model {mp:<4} DK {dk:<4} "
                 f"→ seçimde %{x['tahmin_p']*100:.0f} · sıra {x['sira']}")

    ps, _, _ = tiers.uc_kupon(snap, canli=False)
    giren = [(p["seviye"], x) for p in ps for x in p["bacak"] if x["id"] == e["id"]]
    L += ["", "4️⃣ KUPONA GİRDİ Mİ"]
    if giren:
        for s, x in giren:
            L.append(f"   ✅ {s}: {x['market']} → {x['secenek']}")
    else:
        L.append("   ❌ Hayır — bu maçın hiçbir seçeneği kupona girmedi.")
        L.append("      (sıralamada yeterince yukarı çıkmadı)")
    return "\n".join(L)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("kullanim: python mac_analiz.py <takim adi>")
        raise SystemExit(1)
    print(analiz(" ".join(sys.argv[1:])))
