"""MAC'TE KOSAN SOFASCORE TOPLAYICISI — LaunchAgent ile 7/24.

NEDEN VAR: Sofascore veri merkezi IP'lerini engelliyor. OLCULDU 2026-08-21:
                        duz urllib   curl_cffi (TLS taklidi)
  yerel (TR ev IP'si)      403            200
  GitHub Actions           403            403
  Cloudflare Worker         -             403 {"reason":"challenge"}
Gecen tek yer EV IP'si. Bot ise Actions'ta kosuyor.

COZUM: bu betik Mac'te calisir, veriyi ceker, ESLESTIRMEYI DE BURADA YAPAR
(Nesine mac id'sine gore) ve sonucu Cloudflare KV'ye birakir. /kupon
(Actions) oradan hazir okur -- bot Sofascore'a HIC dokunmaz.

NEDEN ESLESTIRME BURADA: bot tarafinda yapilsaydi ham Sofascore listesini
(640 KB) tasimak gerekirdi; burada eslestirince ~20 KB'lik hazir veri kaliyor
ve Actions tarafinda isim eslestirme kodu tekrarlanmiyor.

ISTEK BUTCESI: dongu basina 1 Nesine + 1 Sofascore listesi + korner/kart
marketi ACIK maclar icin birer istatistik (olculdu: ~4 mac). Toplam ~6 istek.

Mac kapaliysa veri 20 dk sonra KV'den DUSER (TTL) ve bot Fotmob'a doner.
Bayat canli veri, veri yoklugundan tehlikelidir -- dolu gorunur.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bulletin
import sofascore as SF

KOK = Path(__file__).resolve().parent.parent
WORKER = "https://nesine-bot.tantaugur.workers.dev/sofa/yaz"
# Canli korner/kart marketleri (tiers.KORNER_KART_CANLI ile ayni kume)
KORNER_KART = {217, 219, 523, 604, 605}


def _token() -> str:
    for satir in (KOK / ".env").read_text(encoding="utf-8").splitlines():
        if satir.startswith("SOFA_TOKEN="):
            return satir.split("=", 1)[1].strip()
    raise SystemExit("SOFA_TOKEN .env'de yok")


def topla() -> dict:
    """Nesine canli maclarini Sofascore verisiyle esle. Nesine id -> veri."""
    sofa = SF.canli()
    if not sofa:
        return {"hata": "sofascore bos", "t": time.time()}
    idx = SF.indeks(sofa)
    try:
        raw = bulletin.fetch_live()
    except Exception as e:
        return {"hata": f"nesine canli alinamadi: {e}", "t": time.time()}

    out, ist_cekilen = {}, 0
    for e in raw.get("sg", {}).get("EA", []):
        if e.get("TYPE") != 1:
            continue
        sf = SF.esle(idx, e.get("HN") or "", e.get("AN") or "")
        if not sf:
            continue
        d = SF.durum(sf)
        if d.get("dakika") is None:
            continue
        kayit = {"skor": [d["ev_skor"], d["dep_skor"]], "dakika": d["dakika"],
                 "devre": d.get("devre"), "lig": d.get("lig")}
        # Istatistik YALNIZCA korner/kart marketi acik maclar icin
        if {m.get("MTID") for m in (e.get("MA") or [])} & KORNER_KART:
            st = SF.istatistik(sf["id"])
            ist_cekilen += 1
            if st:
                blok = {}
                for kaynak, hedef in (("ALL", "tam"), ("1ST", "ilk_yari")):
                    if st.get(kaynak):
                        blok[hedef] = {k: list(v) for k, v in st[kaynak].items()}
                if blok:
                    kayit["ist"] = blok
        out[str(e.get("C"))] = kayit
    return {"t": time.time(), "mac": out, "n": len(out),
            "ist": ist_cekilen, "sofa_toplam": len(sofa)}


def gonder(veri: dict) -> bool:
    """Worker'a yaz.

    DIKKAT: burada da curl_cffi SART. workers.dev Cloudflare arkasinda ve
    duz urllib POST'u 403 ile reddediyor (olculdu). Kendi Worker'imiza
    bile tarayici TLS parmak iziyle gitmemiz gerekiyor.
    """
    from curl_cffi import requests as rq
    govde = json.dumps(veri, ensure_ascii=False)
    try:
        r = rq.post(WORKER, data=govde.encode("utf-8"), impersonate="chrome",
                    timeout=30, headers={"Authorization": f"Bearer {_token()}",
                                         "Content-Type": "application/json"})
        if r.status_code != 200:
            print(f"[sofa] gonderilemedi: HTTP {r.status_code} {r.text[:80]}")
            return False
        print(f"[sofa] gonderildi: {r.text}")
        return True
    except Exception as e:
        print(f"[sofa] gonderilemedi: {e}")
        return False


if __name__ == "__main__":
    v = topla()
    if v.get("hata"):
        print(f"[sofa] {v['hata']}")
        raise SystemExit(1)
    print(f"[sofa] {v['n']} mac eslesti · {v['ist']} istatistik · "
          f"sofascore toplam {v['sofa_toplam']}")
    raise SystemExit(0 if gonder(v) else 1)
