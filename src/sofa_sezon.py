"""SEZON BASI TAKIM ORTALAMALARI — Mac'te kosar, kopruye birakir.

SORUN (olculdu 2026-08-22, Genoa-Napoli): sezon yeni basladiginda korner/
kart ortalamasi HICBIR KAYNAKTA yok. Fotmob'da iki takimin da ligde 1 maci
var, korner/kart/xG alanlari hic olusmamis. 1 mactan ortalama cikarmak
zaten anlamsiz. Sonuc: Serie A gibi buyuk liglerde korner modeli calismiyor.

COZUM: Sofascore'dan GECEN SEZON ortalamalari. Olculdu:
    Napoli   25/26  38 mac · 5,47 korner · 1,26 sari
    Genoa    25/26  38 mac · 3,68 korner · 1,63 sari
    Fenerbahce      34 mac · 6,91 korner · 2,47 sari
Bu, "veri yok" demekten cok daha iyi bir tahmindir ve kullaniciya HANGI
SEZON oldugu YAZILIR -- gizlenmez.

NEDEN MAC'TE: Sofascore veri merkezi IP'lerini engelliyor (Actions 403,
Cloudflare Worker 403). Bkz. sofascore.py.

MALIYET: takim basina ~4 istek, ama sonuc 7 GUN onbelleklenir (gecen
sezon verisi degismez). Kosu basina en fazla YENI_TAVAN yeni takim
cekilir; havuz birkac kosuda dolar.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bulletin
import sofascore as SF
import stats as ST

KOK = Path(__file__).resolve().parent.parent
ONB = KOK / ".cache" / "sofa_sezon.json"
TTL = 7 * 24 * 3600
YENI_TAVAN = 12          # kosu basina en fazla bu kadar YENI takim.
                         # 40'ti; art arda ~150 istek Sofascore'u
                         # 403'e sokuyordu (olculdu 2026-08-22).
                         # Takim basi ~4 istek -> kosuda ~48 istek.
WORKER = "https://nesine-bot.tantaugur.workers.dev/sofa/yaz?k=takim"


def _token() -> str:
    for s in (KOK / ".env").read_text(encoding="utf-8").splitlines():
        if s.startswith("SOFA_TOKEN="):
            return s.split("=", 1)[1].strip()
    raise SystemExit("SOFA_TOKEN yok")


def _onb() -> dict:
    try:
        return json.loads(ONB.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _onb_yaz(d: dict) -> None:
    ONB.parent.mkdir(parents=True, exist_ok=True)
    ONB.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _korner_var(ist: dict, tid) -> bool:
    v = ist.get(str(tid)) or {}
    return v.get("korner") is not None


def topla() -> dict:
    """Fotmob'da korner verisi OLMAYAN takimlar icin sezon ortalamasi."""
    snap = bulletin.simplify(bulletin.fetch())
    try:
        esl = json.loads((KOK / "data" / "eslesme.json").read_text(encoding="utf-8"))
        ist = json.loads((KOK / "data" / "istatistik.json").read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[sezon] repo verisi okunamadi: {e}")
        esl, ist = {}, {}

    # ONCELIK: en yakin baslayan maclar once. 1400+ takim var; kupon
    # komutu YALNIZCA bugunun maclarina bakiyor, dolayisiyla once onlar
    # doldurulmali. Aksi halde havuz alfabetik/rastgele dolar ve bugunku
    # mac saatlerce beklenir.
    gerek: dict = {}
    olaylar = sorted([e for e in snap.get("olay", []) if e.get("ts")],
                     key=lambda x: x["ts"])
    for e in olaylar:
        k = esl.get(str(e.get("id"))) or {}
        for rol, ad in (("ev", e.get("ev")), ("dep", e.get("dep"))):
            if not ad:
                continue
            tid = k.get(rol)
            if tid and _korner_var(ist, tid):
                continue                       # Fotmob'da veri VAR, gerek yok
            gerek[ST.sadelestir(ad)] = ad

    onb = _onb()
    simdi = time.time()
    yeni = 0
    for sade, ad in gerek.items():
        k = onb.get(sade)
        if k and simdi - k.get("t", 0) < TTL:
            continue
        if yeni >= YENI_TAVAN:
            break
        v = SF.sezon_istatistik(ad)
        yeni += 1
        # BASARISIZLIK DA ONBELLEKLENIR. Onceden yalnizca basarili sonuc
        # yaziliyordu; bulunamayan takimlar HER kosuda yeniden deneniyor
        # ve 40'lik butceyi yiyordu (kosu basina havuz 2-3 buyuyordu).
        # Basarisizlik daha kisa TTL ile tutulur (takim sonradan
        # Sofascore'a girebilir).
        onb[sade] = {"t": simdi if v else simdi - TTL + 86400,
                     "ad": ad, "v": v}
    _onb_yaz(onb)

    # kopruye YALNIZCA veri gonderilir (zaman damgalari yerelde kalir)
    cikti = {sade: k["v"] for sade, k in onb.items() if k.get("v")}
    return {"t": simdi, "takim": cikti, "n": len(cikti),
            "gereken": len(gerek), "yeni": yeni}


def gonder(veri: dict) -> bool:
    from curl_cffi import requests as rq
    try:
        r = rq.post(WORKER, data=json.dumps(veri, ensure_ascii=False).encode(),
                    impersonate="chrome", timeout=60,
                    headers={"Authorization": f"Bearer {_token()}",
                             "Content-Type": "application/json"})
        if r.status_code != 200:
            print(f"[sezon] gonderilemedi: HTTP {r.status_code} {r.text[:80]}")
            return False
        print(f"[sezon] gonderildi: {r.text}")
        return True
    except Exception as e:
        print(f"[sezon] gonderilemedi: {e}")
        return False


if __name__ == "__main__":
    v = topla()
    print(f"[sezon] gereken {v['gereken']} takim · onbellekte {v['n']} · "
          f"bu kosuda yeni {v['yeni']}")
    raise SystemExit(0 if gonder(v) else 1)
