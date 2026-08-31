"""KORNER dagilimini OLC — model kurmadan once.

Neden ayri betik: korner marketine ikinci bir empirik taban baglayacaksak,
once "korner hangi dagilima uyuyor" sorusunu OLCMEK gerekir. Gol modelinde
Poisson kullaniliyor diye korneri de Poisson saymak, olculmemis bir
varsayimi ikinci kaynak diye sunmak olur.

OLCULEN:
  1. Toplam korner: ortalama, varyans, varyans/ortalama  (Poisson ise ~1)
  2. Poisson vs Negatif Binom: log-olabilirlik karsilastirmasi
  3. Takim ortalamalarindan lambda kurup ILERI DOGRU tahmin -- gecmise
     bakma YOK: her mac, YALNIZCA kendisinden ONCEKI maclarla tahmin edilir
  4. Naif taban (lig ortalamasi) ile kiyas -- takim bilgisi EKLIYOR MU?
  5. Kalibrasyon: "%X dedik, gercekten %X mi cikti"
"""
from __future__ import annotations

import csv
import io
import math
import statistics as st
import urllib.request
from collections import defaultdict

KOK = "https://www.football-data.co.uk/mmz4281/"
LIG = ("E0", "E1", "E2", "E3", "EC", "SC0", "SC1", "SC2", "SC3", "D1", "D2",
       "I1", "I2", "SP1", "SP2", "F1", "F2", "N1", "B1", "P1", "T1", "G1")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
CIZGI = (8.5, 9.5, 10.5, 11.5, 12.5)
ISINMA = 5          # bir takim tahmine girmeden once en az bu kadar mac


def _cek(sezon: str, lig: str):
    try:
        r = urllib.request.Request(f"{KOK}{sezon}/{lig}.csv",
                                   headers={"User-Agent": UA})
        with urllib.request.urlopen(r, timeout=30) as y:
            return y.read().decode("utf-8-sig", "ignore")
    except Exception:
        return None


def maclar(sezon: str) -> list:
    out = []
    for lig in LIG:
        met = _cek(sezon, lig)
        if not met:
            continue
        for r in csv.DictReader(io.StringIO(met)):
            h, a = r.get("HomeTeam"), r.get("AwayTeam")
            try:
                hc, ac = float(r["HC"]), float(r["AC"])
            except (KeyError, ValueError, TypeError):
                continue
            if not (h and a):
                continue
            out.append({"lig": lig, "t": r.get("Date"), "ev": h, "dep": a,
                        "ev_k": hc, "dep_k": ac, "top": hc + ac})
    # tarih sirasi -- ileri dogru tahmin icin SART
    def gun(x):
        try:
            g, ay, y = x["t"].split("/")
            return (int(y), int(ay), int(g))
        except Exception:
            return (0, 0, 0)
    out.sort(key=gun)
    return out


def _poisson_loglik(v, lam):
    return sum(-lam + x * math.log(lam) - math.lgamma(x + 1) for x in v)


def _negbin_loglik(v, mu, k):
    """k = sekil parametresi; k -> sonsuz iken Poisson'a yakinsar."""
    t = 0.0
    for x in v:
        t += (math.lgamma(x + k) - math.lgamma(k) - math.lgamma(x + 1)
              + k * math.log(k / (k + mu)) + x * math.log(mu / (k + mu)))
    return t


def _negbin_ust(cizgi, mu, k):
    """P(toplam > cizgi) negatif binomla."""
    n = int(math.floor(cizgi))
    kum = 0.0
    for x in range(n + 1):
        kum += math.exp(math.lgamma(x + k) - math.lgamma(k) - math.lgamma(x + 1)
                        + k * math.log(k / (k + mu)) + x * math.log(mu / (k + mu)))
    return max(0.0, 1.0 - kum)


def _poisson_ust(cizgi, lam):
    n = int(math.floor(cizgi))
    kum = sum(math.exp(-lam + x * math.log(lam) - math.lgamma(x + 1))
              for x in range(n + 1))
    return max(0.0, 1.0 - kum)


def olc(sezon: str = "2526") -> None:
    m = maclar(sezon)
    print(f"═══ {sezon} · {len(m)} mac (korner verisi olan) ═══\n")
    if len(m) < 200:
        print("Yetersiz veri.")
        return
    top = [x["top"] for x in m]
    ort, var = st.mean(top), st.variance(top)
    print("1) TOPLAM KORNER DAGILIMI")
    print(f"   ortalama {ort:.2f} · varyans {var:.2f} · "
          f"varyans/ortalama {var/ort:.3f}   (Poisson ise 1,00)")
    print(f"   medyan {st.median(top):.0f} · en az {min(top):.0f} · "
          f"en cok {max(top):.0f}")

    print("\n2) POISSON vs NEGATIF BINOM (tum veri, sabit ortalama)")
    lp = _poisson_loglik(top, ort)
    # k icin moment tahmini: var = mu + mu^2/k
    k0 = (ort * ort) / max(var - ort, 1e-6)
    en_k, en_l = k0, _negbin_loglik(top, ort, k0)
    for k in [k0 * f for f in (0.5, 0.7, 0.85, 1.0, 1.2, 1.5, 2.0, 3.0)]:
        l = _negbin_loglik(top, ort, k)
        if l > en_l:
            en_k, en_l = k, l
    print(f"   Poisson        log-olabilirlik {lp:11.1f}")
    print(f"   Negatif binom  log-olabilirlik {en_l:11.1f}  (k={en_k:.1f})")
    d = 2 * (en_l - lp)
    print(f"   fark 2ΔLL = {d:.1f} · 1 serbestlik derecesi, kritik ~3,8 → "
          f"{'NEGATIF BINOM daha iyi' if d > 3.8 else 'Poisson yeterli'}")

    print("\n3) ILERI DOGRU TAHMIN (gecmise bakma YOK)")
    at = defaultdict(list)      # takim -> attigi korner
    ye = defaultdict(list)      # takim -> yedigi korner
    lig_top = defaultdict(list)
    tahminler = []
    for x in m:
        e, dp, lg = x["ev"], x["dep"], x["lig"]
        yeterli = len(at[e]) >= ISINMA and len(at[dp]) >= ISINMA and lig_top[lg]
        if yeterli:
            lam_e = (st.mean(at[e]) + st.mean(ye[dp])) / 2
            lam_d = (st.mean(at[dp]) + st.mean(ye[e])) / 2
            tahminler.append({"lam": lam_e + lam_d,
                              "naif": st.mean(lig_top[lg]),
                              "gercek": x["top"]})
        at[e].append(x["ev_k"]); ye[e].append(x["dep_k"])
        at[dp].append(x["dep_k"]); ye[dp].append(x["ev_k"])
        lig_top[lg].append(x["top"])
    print(f"   tahmin edilebilen mac: {len(tahminler)}/{len(m)}")
    if len(tahminler) < 100:
        print("   yetersiz")
        return
    hata_m = st.mean([abs(t["lam"] - t["gercek"]) for t in tahminler])
    hata_n = st.mean([abs(t["naif"] - t["gercek"]) for t in tahminler])
    print(f"   ortalama mutlak hata · takim modeli {hata_m:.3f} · "
          f"naif lig ortalamasi {hata_n:.3f}")
    print(f"   → takim bilgisi {'EKLIYOR' if hata_m < hata_n else 'EKLEMIYOR'} "
          f"({100*(hata_n-hata_m)/hata_n:+.1f}%)")

    print("\n4) CIZGI BAZINDA KALIBRASYON (Üst tarafi)")
    print(f"   {'cizgi':<7}{'n':<7}{'Poisson':<22}{'NegBinom':<22}{'naif':<12}")
    for c in CIZGI:
        pp = [_poisson_ust(c, t["lam"]) for t in tahminler]
        pn = [_negbin_ust(c, t["lam"], en_k) for t in tahminler]
        pnf = [_negbin_ust(c, t["naif"], en_k) for t in tahminler]
        g = [1 if t["gercek"] > c else 0 for t in tahminler]
        gr = sum(g) / len(g)
        def oz(p):
            br = sum((a - b) ** 2 for a, b in zip(p, g)) / len(g)
            return f"%{100*st.mean(p):.0f}→%{100*gr:.0f} B{br:.3f}"
        print(f"   {c:<7}{len(g):<7}{oz(pp):<22}{oz(pn):<22}{oz(pnf):<12}")
    print("\n   okuma: '%X→%Y' = ortalama tahmin %X, gerceklesen %Y. "
          "B = Brier (dusuk iyi).")


if __name__ == "__main__":
    import sys
    sez = sys.argv[1] if len(sys.argv) > 1 else "2526"
    if len(sys.argv) > 2 and sys.argv[2] == "2":
        olc2(sez)
    else:
        olc(sez)


# ---------------------------------------------------------------------------
def olc2(sezon: str = "2526") -> None:
    """Null sonucu KABUL ETMEDEN once modeli duzgun kur.

    olc()'deki model ham ortalamalarin toplamiydi; lig taban duzeyini
    tasidigi icin naif lig ortalamasiyla neredeyse ayni sayiyi uretiyor
    olabilir. Burada CARPIMSAL kurgu denenir:

        lam = lig_ortalamasi * ev_atak * dep_savunma * ...

    katsayilar lig ortalamasina gore NORMALIZE, ve kucuk orneklem gurultusune
    karsi lig ortalamasina BUZULUYOR (shrinkage). Ayrica isinma suresine ve
    takimin ucta olup olmadigina duyarlilik olculur.
    """
    m = maclar(sezon)
    print(f"═══ olc2 · {sezon} · {len(m)} mac ═══\n")
    if len(m) < 500:
        print("yetersiz"); return

    for isinma in (5, 10, 15):
        for buz in (0, 3, 8):
            at = defaultdict(list); ye = defaultdict(list)
            lig_at = defaultdict(list)          # lig genelinde takim basi korner
            T = []
            for x in m:
                e, d, lg = x["ev"], x["dep"], x["lig"]
                L = st.mean(lig_at[lg]) if len(lig_at[lg]) >= 40 else None
                if L and len(at[e]) >= isinma and len(at[d]) >= isinma:
                    def kat(v):
                        """orneklem ortalamasini lig ortalamasina BUZ."""
                        n = len(v)
                        return (sum(v) + buz * L) / (n + buz) / L
                    lam = L * (kat(at[e]) * kat(ye[d])
                               + kat(at[d]) * kat(ye[e]))
                    T.append({"lam": lam, "naif": 2 * L, "gercek": x["top"]})
                at[e].append(x["ev_k"]); ye[e].append(x["dep_k"])
                at[d].append(x["dep_k"]); ye[d].append(x["ev_k"])
                lig_at[lg] += [x["ev_k"], x["dep_k"]]
            if len(T) < 200:
                print(f"   isinma={isinma} buzulme={buz}: yetersiz ({len(T)})")
                continue
            hm = st.mean([abs(t["lam"] - t["gercek"]) for t in T])
            hn = st.mean([abs(t["naif"] - t["gercek"]) for t in T])
            # tahmin ile gercek arasi korelasyon: model AYIRT EDEBILIYOR MU
            lm = [t["lam"] for t in T]; gr = [t["gercek"] for t in T]
            ml, mg = st.mean(lm), st.mean(gr)
            pay = sum((a-ml)*(b-mg) for a, b in zip(lm, gr))
            pd = (sum((a-ml)**2 for a in lm) * sum((b-mg)**2 for b in gr)) ** 0.5
            r = pay / pd if pd else 0.0
            print(f"   isinma={isinma:<3} buzulme={buz:<3} n={len(T):<5} "
                  f"MAE model {hm:.3f} · naif {hn:.3f} "
                  f"({100*(hn-hm)/hn:+.2f}%) · r={r:+.3f} "
                  f"· lam yayilimi {st.pstdev(lm):.2f}")

    print("\n── UC TAKIMLAR: model yalnizca uclarda mi ise yariyor? ──")
    at = defaultdict(list); ye = defaultdict(list); lig_at = defaultdict(list)
    T = []
    for x in m:
        e, d, lg = x["ev"], x["dep"], x["lig"]
        L = st.mean(lig_at[lg]) if len(lig_at[lg]) >= 40 else None
        if L and len(at[e]) >= 10 and len(at[d]) >= 10:
            def kat(v):
                return (sum(v) + 3 * L) / (len(v) + 3) / L
            lam = L * (kat(at[e]) * kat(ye[d]) + kat(at[d]) * kat(ye[e]))
            T.append({"lam": lam, "naif": 2*L, "gercek": x["top"]})
        at[e].append(x["ev_k"]); ye[e].append(x["dep_k"])
        at[d].append(x["dep_k"]); ye[d].append(x["ev_k"])
        lig_at[lg] += [x["ev_k"], x["dep_k"]]
    T.sort(key=lambda t: t["lam"])
    n = len(T); dilim = max(1, n // 5)
    print(f"   {'dilim':<8}{'n':<7}{'ort lam':<10}{'gercek ort':<12}{'fark'}")
    for i in range(5):
        p = T[i*dilim:(i+1)*dilim] if i < 4 else T[4*dilim:]
        if not p: continue
        ol, og = st.mean([t["lam"] for t in p]), st.mean([t["gercek"] for t in p])
        print(f"   {i+1}/5     {len(p):<7}{ol:<10.2f}{og:<12.2f}{og-ol:+.2f}")
    print("   okuma: lam dusuk dilimde gercek de DUSUK cikiyorsa model ayirt")
    print("   ediyor demektir. Dilimler arasi gercek ortalama DEGISMIYORSA")
    print("   model hicbir sey ayirmiyor.")
