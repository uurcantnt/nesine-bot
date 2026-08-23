"""DENETCI — botun onerdigi maclari MODELE GIRMEYEN verilerle gozden gecirir.

NE YAPAR: son kuponun bacaklarini alir, her mac icin sakatlik, hava
durumu, kadro ve kadro degeri cekip yorumlar.

NEDEN AYRI: bu veriler modelin HESABINA GIRMIYOR. Model yalniz gol/korner/
kart ortalamalarindan Poisson kuruyor; sakatlik, hava, kadro gucu hesaba
girmiyor (model.py'de "NE YAPMAZ" basligi altinda yazili). Denetci bu
korlugu KAPATMAZ -- gorunur kilar. Karari kullanici verir.

NE IDDIA ETMEZ: bu yorumlar bir avantaj (+EV) iddiasi DEGILDIR. Marj
%21,1 ve olculdu ki 254 secenegin 254'u eksi degerli. Denetci yalnizca
"botun bakmadigi seyler sunlar" der.

KAYNAK: Fotmob (Actions'tan calisiyor — dogrulandi 2026-08-22).
Sofascore GEREKMEZ; veri merkezi engeli bu isi etkilemez.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fotmob

DATA = Path(__file__).resolve().parent.parent / "data"
GOLGE = DATA / "golge.jsonl"

# ── Esikler: hepsi ACIK, hicbiri sonuca gore secilmedi ──
YAGMUR_MM = 1.0        # bunun ustu "yagisli" sayilir
RUZGAR_KMS = 25        # bunun ustu "ruzgarli"
SICAK_C = 30           # bunun ustu "cok sicak" (tempo duser)
SOGUK_C = 2
DEGER_ORANI = 2.0      # kadro degeri farki bu kati gecerse "buyuk fark"


def son_kupon() -> list:
    """Gölge kaydindaki EN SON kuponun bacaklari."""
    if not GOLGE.exists():
        return []
    sat = []
    for x in GOLGE.read_text(encoding="utf-8").splitlines():
        if x.strip():
            try:
                sat.append(json.loads(x))
            except Exception:
                pass
    if not sat:
        return []
    son_t = sat[-1].get("t")
    return [x for x in sat if x.get("t") == son_t]


def _hava(w: dict) -> list:
    if not w:
        return []
    L, uyari = [], []
    t = w.get("temperature")
    yag = w.get("precipitation") or 0
    ruz = w.get("windSpeed") or 0
    kar = w.get("snow") or 0
    L.append(f"hava {t}°C · rüzgâr {ruz} · yağış {yag}mm"
             + (f" · KAR {kar}" if kar else ""))
    if yag >= YAGMUR_MM:
        uyari.append("yağmurlu — zemin ıslak, top hızlanır ama hatalı pas "
                     "ve korner artabilir")
    if ruz >= RUZGAR_KMS:
        uyari.append("rüzgârlı — uzun top ve ortalar bozulur, gol düşebilir")
    if kar:
        uyari.append("KAR — oyun tempo kaybeder, gol beklentisi düşer")
    if isinstance(t, (int, float)):
        if t >= SICAK_C:
            uyari.append(f"{t}°C sıcak — tempo düşer, ikinci yarı gol azalabilir")
        elif t <= SOGUK_C:
            uyari.append(f"{t}°C soğuk")
    return L + [f"⚠️ {u}" for u in uyari]


def _kadro(l: dict) -> list:
    if not l or not l.get("homeTeam"):
        return ["kadro henüz açıklanmadı"]
    L = []
    ev, dep = l.get("homeTeam") or {}, l.get("awayTeam") or {}
    for t in (ev, dep):
        d = t.get("formation")
        v = t.get("totalStarterMarketValue")
        L.append(f"{t.get('name','?')}: diziliş {d or '?'}"
                 + (f" · ilk 11 değeri {v}" if v else ""))
    a, b = ev.get("totalStarterMarketValue"), dep.get("totalStarterMarketValue")
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and min(a, b) > 0:
        k = max(a, b) / min(a, b)
        if k >= DEGER_ORANI:
            guclu = ev.get("name") if a > b else dep.get("name")
            L.append(f"⚠️ kadro değeri {k:.1f} kat farklı — {guclu} belirgin "
                     "güçlü. MODEL BUNU HESABA KATMAZ (ham gol ortalaması "
                     "kullanır, rakip gücünü bilmez)")
    return L


def _sakat(tid) -> list:
    try:
        tv = fotmob._get(f"https://www.fotmob.com/api/data/teams?id={tid}")
    except Exception:
        return []
    ad = (tv.get("details") or {}).get("name") or str(tid)
    sak = []
    for g in ((tv.get("squad") or {}).get("squad") or []):
        for o in (g.get("members") or []):
            if o.get("injury"):
                d = o["injury"].get("expectedReturn") or "?"
                sak.append(f"{o.get('name')} (dönüş: {d})")
    if not sak:
        return [f"{ad}: sakat yok"]
    return [f"{ad}: {len(sak)} sakat — " + ", ".join(sak[:4])]


def mac_raporu(bacak: dict) -> list:
    fid = bacak.get("fotmob_id")
    L = ["", "━" * 30, f"⚽ {bacak.get('mac')}",
         f"🎯 {bacak.get('market')} → {bacak.get('secenek')}  @{bacak.get('oran')}"]
    if not fid:
        L.append("   dış veride eşleşmedi — denetlenemedi")
        return L
    try:
        d = fotmob._get(f"https://www.fotmob.com/api/data/matchDetails?matchId={fid}")
    except Exception as e:
        L.append(f"   detay alınamadı: {e}")
        return L
    c = d.get("content") or {}
    for x in _hava(c.get("weather")):
        L.append(f"   🌤 {x}" if not x.startswith("⚠️") else f"   {x}")
    for x in _kadro(c.get("lineup")):
        L.append(f"   👥 {x}" if not x.startswith("⚠️") else f"   {x}")
    ht = ((d.get("header") or {}).get("teams") or [])
    for t in ht[:2]:
        for x in _sakat(t.get("id")):
            L.append(f"   🩹 {x}")
    return L


def rapor() -> str:
    bacaklar = son_kupon()
    if not bacaklar:
        return "DENETÇİ: kayıtlı kupon yok."
    gorulen, L = set(), [
        "🔎 DENETÇİ — botun BAKMADIĞI veriler",
        "",
        "Model yalnızca gol/korner/kart ortalamalarından Poisson kurar.",
        "Sakatlık, hava, kadro ve rakip gücü hesabına GİRMEZ.",
        "Aşağıdakiler o boşluğu doldurmaz — görünür kılar. Karar senin.",
    ]
    for b in bacaklar:
        if b.get("mac") in gorulen:
            continue
        gorulen.add(b.get("mac"))
        L += mac_raporu(b)
    L += ["", "Bu yorumlar AVANTAJ İDDİASI DEĞİLDİR. Nesine marjı %21,1;",
          "ölçüldü ki 254 seçeneğin 254'ü eksi değerli."]
    return "\n".join(L)


if __name__ == "__main__":
    print(rapor())
