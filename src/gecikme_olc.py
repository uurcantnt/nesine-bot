"""ESPN canli verisi Nesine'den GERIDE mi? — kritik olcum.

MANTIK: gol atildiginda (a) Nesine'nin orani siçrar, (b) ESPN'in skoru degisir.
Ikisinin zaman damgasi karsilastirilir.

NEDEN KRITIK: ESPN geride kalirsa model sahte "deger" uretir -- Nesine golu
fiyatlamistir, biz gormemisizdir. O durumda canli modele GUVENILEMEZ.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

import bulletin
import stats

SURE_DK = int(sys.argv[1]) if len(sys.argv) > 1 else 30
ARALIK_SN = 20
SICRAMA = 0.12          # oranda bu goreli degisim "olay" sayilir


def espn_skorlar() -> dict:
    try:
        from sports_skills import football
    except ImportError:
        return {}
    out = {}
    for gun in (None, (datetime.now(timezone.utc)).strftime("%Y%m%d")):
        try:
            d = football.get_daily_schedule(**({"date": gun} if gun else {}))
        except Exception:
            continue
        for e in ((d or {}).get("data") or {}).get("events") or []:
            if e.get("status") != "live":
                continue
            rak = e.get("competitors") or []
            ev = next((c for c in rak if c.get("qualifier") == "home"), None)
            dep = next((c for c in rak if c.get("qualifier") == "away"), None)
            if not ev or not dep:
                continue
            ad = (stats.sadelestir((ev.get("team") or {}).get("name") or ""),
                  stats.sadelestir((dep.get("team") or {}).get("name") or ""))
            out[ad] = (int(ev.get("score") or 0), int(dep.get("score") or 0))
    return out


def nesine_oranlar() -> dict:
    raw = bulletin.fetch_live()
    out = {}
    for e in raw.get("sg", {}).get("EA", []):
        if e.get("TYPE") != 1:
            continue
        ms = [m for m in e.get("MA", []) if m.get("MTID") == 53 and m.get("MS") == 1]
        if not ms:
            continue
        o = [x.get("O") for x in ms[0].get("OCA", [])]
        if len(o) == 3 and all(x and x > 1 for x in o):
            out[(stats.sadelestir(e.get("HN") or ""),
                 stats.sadelestir(e.get("AN") or ""))] = o
    return out


def _esles(ad_n, espn):
    if ad_n in espn:
        return ad_n
    for k in espn:
        if (ad_n[0] and k[0] and (ad_n[0] in k[0] or k[0] in ad_n[0])) and \
           (ad_n[1] and k[1] and (ad_n[1] in k[1] or k[1] in ad_n[1])):
            return k
    return None


onceki_o, onceki_s = {}, {}
olaylar = []
t0 = time.time()
tick = 0
print(f"olcum basliyor: {SURE_DK} dk, {ARALIK_SN} sn araliklarla\n")
while time.time() - t0 < SURE_DK * 60:
    tick += 1
    t = time.time() - t0
    try:
        o_now = nesine_oranlar()
    except Exception as e:
        print(f"[{t:6.0f}s] nesine hata: {e}")
        time.sleep(ARALIK_SN)
        continue
    s_now = espn_skorlar()
    for ad, o in o_now.items():
        eski = onceki_o.get(ad)
        if eski:
            fark = max(abs(o[i] - eski[i]) / eski[i] for i in range(3))
            if fark >= SICRAMA:
                olaylar.append(("NESINE_ORAN", t, ad, f"{eski}->{o} (%{fark*100:.0f})"))
                print(f"[{t:6.0f}s] ORAN SICRAMASI {ad[0][:16]}: {eski} -> {o}")
        onceki_o[ad] = o
        k = _esles(ad, s_now)
        if k:
            sk = s_now[k]
            if ad in onceki_s and onceki_s[ad] != sk:
                olaylar.append(("ESPN_SKOR", t, ad, f"{onceki_s[ad]}->{sk}"))
                print(f"[{t:6.0f}s] ESPN SKOR   {ad[0][:16]}: {onceki_s[ad]} -> {sk}")
            onceki_s[ad] = sk
    time.sleep(ARALIK_SN)

print(f"\n=== {tick} ornekleme · {len(olaylar)} olay ===")
print(f"Nesine'de izlenen canli mac: {len(onceki_o)} · ESPN'de eslesen: {len(onceki_s)}")
eslesen = 0
for tur, t, ad, d in olaylar:
    print(f"  {t:6.0f}s  {tur:<12} {ad[0][:18]:<18} {d}")
# ayni maca ait olaylari esle
for ad in set(x[2] for x in olaylar):
    ns = [x[1] for x in olaylar if x[2] == ad and x[0] == "NESINE_ORAN"]
    es = [x[1] for x in olaylar if x[2] == ad and x[0] == "ESPN_SKOR"]
    for e in es:
        yakin = [n for n in ns if abs(n - e) < 300]
        if yakin:
            en = min(yakin, key=lambda n: abs(n - e))
            eslesen += 1
            print(f"\n  GOL: {ad[0][:20]} — Nesine {en:.0f}s, ESPN {e:.0f}s "
                  f"→ ESPN {e-en:+.0f}s {'GERIDE' if e > en else 'ONDE'}")
if not eslesen:
    print("\n  Eslesen gol olayi yok (bu surede gol olmamis olabilir).")
