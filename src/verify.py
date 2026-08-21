"""Oz-denetim: R3 (hash) ve R4 (bagimsiz yeniden hesap).

Bagimsiz yeniden hesap NEDEN: bot kendi kodunu kullanarak kendini dogrularsa
hicbir sey dogrulamis olmaz. Burada overround/devig SIFIRDAN, odds.py'ye
bakmadan yeniden yazilir; sonuc botunkiyle karsilastirilir.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import bulletin
import coupon
from core import LIMITS, MARKETS

KOK = Path(__file__).resolve().parent.parent
SAPMA = KOK / "data" / "sapma.jsonl"


def hash_kontrol() -> tuple[bool, str, str]:
    """R3: mekanizma dosyalarinin hash'i sartnamedekiyle ayni mi."""
    h = hashlib.sha256()
    for f in ("core.py", "odds.py", "coupon.py"):
        h.update((KOK / "src" / f).read_bytes())
    simdi = h.hexdigest()[:16]
    m = re.search(r"`([0-9a-f]{16})`", (KOK / "MEKANIZMA_v1.0.md").read_text())
    beklenen = m.group(1) if m else "?"
    return simdi == beklenen, simdi, beklenen


def bagimsiz_en_iyi(snap: dict) -> dict | None:
    """Adim adim sifirdan: en dusuk marjli, uygun adayi bul."""
    now = datetime.now(timezone.utc)
    en_iyi = None
    for e in snap.get("olay", []):
        ts = e.get("ts")
        if not ts:
            continue
        saat = (ts / 1000 - now.timestamp()) / 3600.0
        if not (LIMITS["MIN_SAAT"] <= saat <= LIMITS["MAX_SAAT"]):
            continue
        for mtid_s, m in e.get("m", {}).items():
            mtid = int(mtid_s)
            if mtid not in MARKETS or m.get("ms") != 1:
                continue
            kapsam = MARKETS[mtid]["kapsam"]
            o = m.get("o") or []
            if len(o) != len(MARKETS[mtid]["secenek"]) or any(
                    x is None or x <= 1.0 for x in o):
                continue
            ters = [1.0 / x for x in o]
            toplam = sum(ters) / kapsam
            marj = toplam - 1.0
            if marj > LIMITS["MAX_OVERROUND"]:
                continue
            olas = [t / toplam for t in ters]
            i = olas.index(max(olas))
            if not (LIMITS["MIN_ODD"] <= o[i] <= LIMITS["MAX_ODD"]):
                continue
            aday = {"id": e["id"], "mtid": mtid, "oran": o[i],
                    "marj": marj, "olasilik": olas[i]}
            if en_iyi is None or (round(marj, 4), -olas[i]) < (
                    round(en_iyi["marj"], 4), -en_iyi["olasilik"]):
                en_iyi = aday
    return en_iyi


def run() -> int:
    snap = bulletin.latest()
    if not snap:
        print("[verify] snapshot yok"); return 1

    ok, simdi, beklenen = hash_kontrol()
    print(f"[R3] hash {'TAMAM' if ok else 'SAPMA'}: {simdi} (beklenen {beklenen})")

    bot = coupon.candidates(snap)
    bot_ilk = bot[0] if bot else None
    bag = bagimsiz_en_iyi(snap)

    sapmalar = []
    if not ok:
        sapmalar.append(f"hash: {simdi} != {beklenen}")
    if (bot_ilk is None) != (bag is None):
        sapmalar.append("biri aday buldu digeri bulamadi")
    elif bot_ilk and bag:
        for alan in ("id", "mtid", "oran"):
            if bot_ilk[alan] != bag[alan]:
                sapmalar.append(f"{alan}: bot={bot_ilk[alan]} bagimsiz={bag[alan]}")
        if abs(bot_ilk["marj"] - bag["marj"]) > 1e-9:
            sapmalar.append(f"marj: {bot_ilk['marj']} vs {bag['marj']}")

    if sapmalar:
        print("[R4] SAPMA:", "; ".join(sapmalar))
        import depo
        depo.ekle(SAPMA, json.dumps({"t": datetime.now(timezone.utc).isoformat(),
                                     "sapma": sapmalar}, ensure_ascii=False) + "\n")
        try:
            import notify
            notify.send("NESINE · SAPMA ALARMI\n" + "\n".join(sapmalar))
        except Exception as e:
            print(f"[verify] bildirim yok: {e}")
        return 2
    print(f"[R4] bagimsiz hesap TAMAM — {len(bot)} aday, ilk secim ayni "
          f"(mac {bot_ilk['id']}, marj %{bot_ilk['marj']*100:.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(run())
