"""Golge kayit: her oneriyi yaz, sonucunu coz, KALIBRASYONU olc.

NEDEN: "model %74 dedi" cumlesinin dogru olup olmadigi ancak sonuclar
bilinince olculur. Bu dosya olmadan bot kendini degerlendiremez ve
"birkac kupon tuttu" gibi anlamsiz kanitlara mahkum kaliriz.

OLCULEN: her kaynagin (Nesine / modelimiz / DraftKings / gecmis) tahmin
ettigi olasilik ile GERCEKLESEN isabet oraninin karsilastirmasi.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
KAYIT = DATA / "golge.jsonl"


def kaydet(paketler: list, kaynak: str = "kupon") -> int:
    """Onerilen her bacagi tum tahmin kaynaklariyla birlikte logla."""
    import json as _j
    esl = {}
    try:
        esl = _j.loads((DATA / "eslesme.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    import depo
    if not depo.yazilabilir():
        print("[depo] yerel calisma: golge kaydi YAPILMADI (kilit)")
        return 0
    n = 0
    KAYIT.parent.mkdir(parents=True, exist_ok=True)
    with KAYIT.open("a", encoding="utf-8") as f:
        for p in paketler:
            for b in p["bacak"]:
                amp = b.get("_ampirik")
                f.write(json.dumps({
                    "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "kaynak": kaynak, "seviye": p.get("seviye"),
                    "kaynak_tur": p.get("kaynak"),
                    "mac_id": b["id"], "mac": b["mac"], "lig": b.get("lig_ad"),
                    "fotmob_id": (esl.get(str(b["id"])) or {}).get("fotmob_id"),
                    "mtid": b["mtid"], "idx": b["idx"], "sov": b.get("sov"),
                    "market": b["market"], "secenek": b["secenek"],
                    "oran": b["oran"], "canli": bool(b.get("canli")),
                    "nesine_p": b["olasilik"], "model_p": b.get("model_p"),
                    "dk_p": b.get("dk_p"), "ampirik_p": (amp or {}).get("oran"),
                    "tahmin_p": b.get("tahmin_p"), "deger": b.get("deger"),
                    "sonuc": None,
                }, ensure_ascii=False) + "\n")
                n += 1
    return n


def _oku() -> list:
    if not KAYIT.exists():
        return []
    out = []
    for satir in KAYIT.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if satir:
            try:
                out.append(json.loads(satir))
            except json.JSONDecodeError:
                pass
    return out


def _yaz(kayitlar: list) -> None:
    import depo
    depo.yaz(KAYIT, "\n".join(json.dumps(k, ensure_ascii=False)
                               for k in kayitlar) + "\n")


def coz(en_fazla: int = 300) -> tuple:
    """Sonucu bilinmeyen kayitlari cozumle. (cozulen, kalan)"""
    import sonuc as S
    kayitlar = _oku()
    bekleyen = [k for k in kayitlar if k.get("sonuc") is None and k.get("fotmob_id")]
    onbellek: dict = {}
    cozulen = 0
    for k in bekleyen[:en_fazla]:
        fid = k["fotmob_id"]
        if fid not in onbellek:
            onbellek[fid] = S.mac_sonucu(fid)
        s = onbellek[fid]
        if not s:
            continue                      # mac bitmemis
        r = S.degerlendir(k["mtid"], k["idx"], k.get("sov"), s)
        if r is None:
            k["sonuc"] = "belirlenemedi"
        else:
            k["sonuc"] = bool(r)
            k["mac_skoru"] = f"{s['ev_gol']}-{s['dep_gol']}"
        cozulen += 1
    _yaz(kayitlar)
    kalan = sum(1 for k in kayitlar if k.get("sonuc") is None)
    return cozulen, kalan


def rapor() -> str:
    """Kalibrasyon raporu: her kaynak ne kadar isabetli tahmin ediyor?"""
    kayitlar = [k for k in _oku() if isinstance(k.get("sonuc"), bool)]
    if not kayitlar:
        return "📊 GÖLGE RAPOR\nHenüz sonucu belli olan öneri yok."
    L = [f"📊 GÖLGE RAPOR · {len(kayitlar)} sonuçlanmış seçim", ""]
    tutan = sum(1 for k in kayitlar if k["sonuc"])
    L.append(f"Tutan: {tutan}/{len(kayitlar)} (%{100*tutan/len(kayitlar):.1f})")

    # gerceklesen getiri vs beklenen
    yatirim = len(kayitlar)
    donen = sum(k["oran"] for k in kayitlar if k["sonuc"])
    L.append(f"Her seçime 1 birim: {donen:.2f} birim döndü → "
             f"{100*(donen/yatirim-1):+.1f}%")
    bek = sum((k.get("tahmin_p") or k["nesine_p"]) * k["oran"] - 1 for k in kayitlar) / yatirim
    L.append(f"Beklenen (modelin dediği): {100*bek:+.1f}%")
    L.append("")

    # kaynak bazli kalibrasyon
    L.append("KAYNAK KALİBRASYONU (tahmin → gerçekleşen)")
    for alan, ad in (("nesine_p", "Nesine"), ("model_p", "Modelimiz"),
                     ("dk_p", "DraftKings"), ("tahmin_p", "Botun kullandığı")):
        v = [k for k in kayitlar if isinstance(k.get(alan), (int, float))]
        if len(v) < 5:
            L.append(f"  {ad:<18} yetersiz veri ({len(v)})")
            continue
        tahmin = sum(k[alan] for k in v) / len(v)
        gercek = sum(1 for k in v if k["sonuc"]) / len(v)
        brier = sum((k[alan] - (1 if k["sonuc"] else 0)) ** 2 for k in v) / len(v)
        L.append(f"  {ad:<18} n={len(v):<4} tahmin %{tahmin*100:.0f} → "
                 f"gerçek %{gercek*100:.0f} · Brier {brier:.3f}")
    L.append("")
    L.append("Brier düşük = daha isabetli. Rastgele tahmin ~0,25.")
    L.append("Tahmin ile gerçek arasındaki fark büyükse o kaynak sapmalı.")
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    if "--coz" in sys.argv:
        c, k = coz()
        print(f"cozulen {c} · bekleyen {k}")
    print(rapor())
