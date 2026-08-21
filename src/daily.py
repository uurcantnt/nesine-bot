"""Gunluk oneri akisi: aday sec -> mesaji kur -> Telegram -> golge kayit.

Bahis OTOMATIK OYNANMAZ. Bot yalnizca oneri gonderir; kuponu kullanici
kendi elleriyle Nesine'de oynar.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import bulletin
import coupon
import notify
import trtime
from core import LIMITS, MECHANISM_VERSION

DATA = Path(__file__).resolve().parent.parent / "data"
STATE = DATA / "state.json"
GOLGE = DATA / "golge.jsonl"


def _state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"ay": "", "ay_ciro": 0.0, "gonderim": 0, "son_gun": ""}


def _save(s: dict) -> None:
    import depo
    depo.yaz(STATE, json.dumps(s, ensure_ascii=False, indent=2))


def format_message(p: dict, tek_alternatif: dict | None = None) -> str:
    """Mesaj. Beklenen deger HER ZAMAN yazilir -- gizlenmez, yuvarlanmaz."""
    L = [f"NESINE · mekanizma v{MECHANISM_VERSION}",
         f"{p['n']} bacak · {p['stake']:.0f} TL"]
    L.append("")
    for b in p["bacak"]:
        L.append(f"• {b['mac']}")
        L.append(f"  {b['market']}: {b['secenek']}  @{b['oran']:.2f}"
                 f"   (marj %{b['marj']*100:.1f})")
        L.append(f"  {trtime.bicim(b['bas'])}")
    L.append("")
    L.append(f"Toplam oran : {p['toplam_oran']:.2f}")
    L.append(f"Isabet olas.: %{p['isabet_olasiligi']*100:.1f}")
    L.append(f"Kupon marji : %{p['toplam_marj']*100:.1f}")
    L.append(f"BEKLENEN DEGER: %{p['ev']*100:.1f}"
             f"  ({p['ev']*p['stake']:+.2f} TL / kupon)")
    if p["n"] > 1 and tek_alternatif:
        fark = (p["ev"] - tek_alternatif["ev"]) * 100
        L.append(f"Tek mac olsaydi: EV %{tek_alternatif['ev']*100:.1f}"
                 f"  (kupon {fark:+.1f} puan daha kotu)")
    L.append("")
    L.append(f"Basabas icin gereken CLV: %{p['gereken_clv']*100:.1f} — "
             "olculen edge YOK, bu oneri maliyeti en aza indirir, kazanc vaat etmez.")
    return "\n".join(L)


def run(bacak: int = 1, gonder: bool = True) -> dict | None:
    bulletin.run()                      # arsivi guncelle (kacan oran geri gelmez)
    snap = bulletin.latest()
    if not snap:
        print("[gunluk] snapshot yok"); return None

    s = _state()
    ay = datetime.now(timezone.utc).strftime("%Y-%m")
    if s["ay"] != ay:
        s.update({"ay": ay, "ay_ciro": 0.0, "gonderim": 0})
    gun = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if s["son_gun"] == gun and s["gonderim"] >= LIMITS["GUNLUK_PUSH"]:
        print("[gunluk] gunluk oneri kotasi dolu"); return None
    if s["ay_ciro"] + LIMITS["STAKE_TL"] > LIMITS["AYLIK_KAYIP_TAVANI_TL"]:
        if gonder:      # --dry modda bildirim GITMEZ (testte gercek mesaj atiyordu)
            notify.send(f"NESINE · aylik ciro tavanina ulasildi "
                        f"({s['ay_ciro']:.0f}/{LIMITS['AYLIK_KAYIP_TAVANI_TL']:.0f} TL). "
                        "Bu ay yeni oneri gonderilmeyecek.")
        print("[gunluk] aylik tavan"); return None

    p = coupon.build_kupon(snap, bacak) if bacak > 1 else coupon.build(snap)
    if not p:
        print("[gunluk] uygun aday yok"); return None
    tek = coupon.build(snap) if bacak > 1 else None

    msg = format_message(p, tek)
    print(msg)
    if gonder:
        notify.send(msg)
        s.update({"son_gun": gun, "gonderim": s["gonderim"] + 1,
                  "ay_ciro": s["ay_ciro"] + p["stake"]})
        _save(s)
        _golge_yaz(p)
    return p


def _golge_yaz(p: dict) -> None:
    """Golge kayit: her oneri sonradan degerlendirilebilsin diye loglanir.

    Sonuc eslestirmesi henuz YOK (Nesine sonuc endpoint'i bulunamadi) --
    kayitlar tarih/ID tasidigi icin geriye donuk doldurulabilir.
    """
    kayit = {
        "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mekanizma": MECHANISM_VERSION,
        "n": p["n"], "toplam_oran": p["toplam_oran"],
        "marj": p["toplam_marj"], "ev": p["ev"],
        "isabet_olasiligi": p["isabet_olasiligi"], "stake": p["stake"],
        "bacak": [{"id": b["id"], "mac": b["mac"], "mtid": b["mtid"],
                   "secenek": b["secenek"], "oran": b["oran"],
                   "olasilik": b["olasilik"], "marj": b["marj"],
                   "bas": b["bas"].isoformat()} for b in p["bacak"]],
        "sonuc": None,
    }
    import depo
    depo.ekle(GOLGE, json.dumps(kayit, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    gonder = "--dry" not in sys.argv
    run(bacak=n, gonder=gonder)
