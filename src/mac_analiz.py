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


def gecmis_bolumu(e: dict, esl: dict, ist: dict) -> list:
    """Iki takimin son maclari: MS, ILK YARI, korner (tam + ilk yari).

    Kullanici istegi (2026-08-22): "/mac komutunda takimlarin son ilk
    yarilari nasil bitmis, kac korner cikmis, cikan kornerlerin kaci ilk
    yari olmus gibi bilgiler de yer alabilir mi"

    MALIYET: mac basina 1 Fotmob istegi, ama KALICI onbellekli
    (iy_gecmis.json) -- ayni mac bir daha cekilmez.
    """
    import iy_gecmis
    k = esl.get(str(e.get("id")))
    if not k:
        return ["", "📋 SON MAÇLAR: bu maç dış veride eşleşmedi"]
    L = ["", "═" * 34, "📋 SON MAÇLAR — İLK YARI ve KORNER", "═" * 34]
    for rol, ad in (("ev", e.get("ev")), ("dep", e.get("dep"))):
        tid = str(k.get(rol))
        tv = ist.get(tid)
        if not tv:
            L.append(f"\n  {ad}: istatistik yok")
            continue
        satirlar = iy_gecmis.takim_detay(tv, tid, en_fazla=6)
        hz = " (HAZIRLIK maçları)" if tv.get("hazirlik_dahil") else ""
        L.append(f"\n  ▸ {ad}{hz}   (korner sütunu: kendi-rakip)")
        if not satirlar:
            L.append("     maç detayı çekilemedi")
            continue
        iy_gol = iy_kor = kor = n_iy = n_kor = 0
        biz_kor = biz_iy = n_biz = 0
        for m in satirlar:
            yer = "EV " if m["ev"] else "DEP"
            ms = f"{m['ms_at']}-{m['ms_ye']}"
            iy = (f"{m['iy_at']}-{m['iy_ye']}" if m["iy_at"] is not None else "?")
            # KORNER TAKIM AYRIMI: "kornerin kacini BIZ yaptik" sorusu
            # toplamla cevaplanamiyor (kullanici sordu 2026-08-22).
            if m.get("korner_biz") is not None:
                kk = f"{m['korner_biz']}-{m['korner_rakip']}"
            else:
                kk = f"{m['korner']}" if m["korner"] is not None else "?"
            if m.get("iy_korner_biz") is not None:
                ik = f"{m['iy_korner_biz']}-{m['iy_korner_rakip']}"
            else:
                ik = f"{m['iy_korner']}" if m["iy_korner"] is not None else "?"
            L.append(f"     {m['t']} {yer} attı-yedi {ms:<5} · İY {iy:<5} "
                     f"· korner {kk:<6} (İY {ik})")
            if m["iy_at"] is not None:
                iy_gol += m["iy_at"] + m["iy_ye"]; n_iy += 1
            if m["korner"] is not None:
                kor += m["korner"]; n_kor += 1
                if m["iy_korner"] is not None:
                    iy_kor += m["iy_korner"]
            if m.get("korner_biz") is not None:
                biz_kor += m["korner_biz"]; n_biz += 1
            if m.get("iy_korner_biz") is not None:
                biz_iy += m["iy_korner_biz"]
        ozet = []
        if n_iy:
            ozet.append(f"ilk yarı ort. {iy_gol/n_iy:.1f} gol")
        if n_kor:
            ozet.append(f"korner ort. {kor/n_kor:.1f}")
            if iy_kor:
                ozet.append(f"kornerin %{100*iy_kor/max(kor,1):.0f}'i ilk yarıda")
        if n_biz:
            ozet.append(f"kendi korneri ort. {biz_kor/n_biz:.1f} "
                        f"(toplamın %{100*biz_kor/max(kor,1):.0f}'i)")
            if biz_iy:
                ozet.append(f"ilk yarıda kendi korneri ort. {biz_iy/n_biz:.1f}")
        if ozet:
            L.append(f"     → {' · '.join(ozet)}")
        if not n_kor and satirlar:
            # OLCULDU: Fotmob HAZIRLIK maclarinda korner/kart tutmuyor,
            # yalnizca skor veriyor. "?" isaretini sebepsiz birakmak
            # veri hatasi gibi gorunuyordu.
            L.append("     (korner verisi yok — hazırlık maçlarında "
                     "Fotmob korner tutmuyor)")
    return L


def canli_bolumu(e: dict) -> list:
    """Mac SU AN canliysa skor/dakika + korner/kart istatistigi.

    Kaynak Sofascore koprusu (Mac'teki toplayici -> Cloudflare KV).
    Kopru bossa (Mac kapali / mac canli degil) bolum HIC yazilmaz --
    "veri yok" satiri gurultu olur.
    """
    import sofascore as SF
    k = SF.kopru_bul(e.get("id"), e.get("ev") or "", e.get("dep") or "")
    if not k:
        return []
    L = ["", "📡 ŞU AN CANLI (Sofascore)",
         f"   Skor    {k['skor'][0]}-{k['skor'][1]}   {k['dakika']}. dakika"
         + (f"  ({k['devre']})" if k.get("devre") else "")]
    if k.get("lig"):
        L.append(f"   Lig     {k['lig']}")
    ist = k.get("ist") or {}
    tam, ilk = ist.get("tam") or {}, ist.get("ilk_yari") or {}
    def cift(blok, ad):
        v = blok.get(ad)
        return (int(v[0]), int(v[1])) if v and len(v) == 2 and None not in v else None
    kor = cift(tam, "korner")
    if kor:
        satir = f"   Korner  {kor[0]}-{kor[1]} (toplam {sum(kor)})"
        ik = cift(ilk, "korner")
        if ik:
            satir += f" · ilk yarı {sum(ik)}"
        L.append(satir)
    sari = cift(tam, "sari")
    if sari:
        L.append(f"   Sarı    {sari[0]}-{sari[1]} (toplam {sum(sari)})")
    top = cift(tam, "topla_oynama")
    if top:
        L.append(f"   Topla oynama  %{top[0]} - %{top[1]}")
    sut = cift(tam, "isabetli_sut")
    if sut:
        L.append(f"   İsabetli şut  {sut[0]}-{sut[1]}")
    if not ist:
        L.append("   (bu maçta korner/kart marketi açık değil, istatistik çekilmedi)")
    return L


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

    L += gecmis_bolumu(e, esl, ist)

    # ── CANLI DURUM (Sofascore koprusu) ──────────────────────────────
    # /mac komutu canli veriyi HIC kullanmiyordu. Kopru Nesine mac id'siyle
    # dogrudan eslesiyor, o yuzden tek mac icin bakmak ucuz.
    L += canli_bolumu(e)

    ps, *_ = tiers.uc_kupon(snap, canli=False)
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
