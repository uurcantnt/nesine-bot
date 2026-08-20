"""ESPN gunluk fikstürünü TOPLU cekip Nesine maclariyla eslestir.

NEDEN TOPLU: takim basina ayri CLI cagrisi olcekLENMIYOR -- 60 mac icin
20+ dakika surdu (her cagri ayri Python sureci + ag gidis-donusu).
Gunluk fikstur birkac cagriyla tum maclari verir, eslestirme yerelde yapilir.

NEREDE CALISIR: ESPN Turkiye'den engelli (403/timeout), GitHub Actions
runner'indan acik. Bu modul YALNIZCA Actions'ta calisir.
"""
from __future__ import annotations

import json
import re
import subprocess
import unicodedata
from datetime import datetime, timedelta, timezone

import stats


def _cli(*args: str, timeout: int = 120) -> dict | None:
    try:
        r = subprocess.run(["sports-skills", *args], capture_output=True,
                           text=True, timeout=timeout)
    except Exception as e:
        print(f"[fikstur] CLI hata: {e}")
        return None
    if r.returncode != 0 or not r.stdout.strip():
        print(f"[fikstur] CLI bos donus (kod {r.returncode}): {r.stderr[:200]}")
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def gunluk(tarih: str) -> list:
    """ESPN'in o gunku tum futbol maclari. tarih: YYYYMMDD."""
    d = _cli("football", "get_daily_schedule", f"--date={tarih}")
    if not d or not d.get("status"):
        return []
    veri = d.get("data") or {}
    for anahtar in ("events", "matches", "schedule", "results"):
        if isinstance(veri.get(anahtar), list):
            return veri[anahtar]
    # bazi surumlerde lig -> mac listesi
    out = []
    for v in veri.values():
        if isinstance(v, list):
            out.extend(v)
    return out


def _ad(x) -> str:
    if isinstance(x, dict):
        return (x.get("name") or x.get("displayName") or x.get("short_name")
                or x.get("team", {}).get("name") or "")
    return str(x or "")


def _takimlar(ev: dict) -> tuple:
    """Mactan (ev sahibi, deplasman) adlarini cikar -- sema surumden surume degisiyor."""
    for a, b in (("home", "away"), ("home_team", "away_team"),
                 ("homeTeam", "awayTeam")):
        if ev.get(a) or ev.get(b):
            return _ad(ev.get(a)), _ad(ev.get(b))
    rak = ev.get("competitors") or ev.get("teams") or []
    if len(rak) == 2:
        ilk, ikinci = rak
        if str(ilk.get("homeAway", "")).lower() == "away":
            ilk, ikinci = ikinci, ilk
        return _ad(ilk), _ad(ikinci)
    ad = ev.get("name") or ev.get("shortName") or ""
    if " at " in ad:
        d, e = ad.split(" at ", 1)
        return e, d
    if " vs " in ad.lower():
        p = re.split(r"\s+vs\.?\s+", ad, flags=re.I)
        if len(p) == 2:
            return p[0], p[1]
    return "", ""


def indeks(gunler: int = 3) -> dict:
    """{(ev_sade, dep_sade): mac} sozlugu."""
    ix = {}
    bugun = datetime.now(timezone.utc).date()
    for i in range(gunler):
        t = (bugun + timedelta(days=i)).strftime("%Y%m%d")
        maclar = gunluk(t)
        print(f"[fikstur] {t}: {len(maclar)} mac")
        for ev in maclar:
            h, a = _takimlar(ev)
            if h and a:
                ix[(stats.sadelestir(h), stats.sadelestir(a))] = {
                    "espn": ev, "ev": h, "dep": a, "tarih": t}
    return ix


def esle(ix: dict, nesine_ev: str, nesine_dep: str) -> dict | None:
    """Nesine maci fikstürde var mi. Once tam, sonra parcali eslesme."""
    h, a = stats.sadelestir(stats.ELLE.get(nesine_ev.lower(), nesine_ev)), \
           stats.sadelestir(stats.ELLE.get(nesine_dep.lower(), nesine_dep))
    if (h, a) in ix:
        return ix[(h, a)]
    for (ih, ia), v in ix.items():
        if (h and ih and (h in ih or ih in h)) and (a and ia and (a in ia or ia in a)):
            return v
    return None
