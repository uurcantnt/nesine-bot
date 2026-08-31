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


# ---------------------------------------------------------------------------
def _lambda_uret(m, isinma=10, buzulme=3):
    """Maclari sirayla gezip her mac icin ILERI DOGRU lam uretir."""
    at = defaultdict(list); ye = defaultdict(list); lig = defaultdict(list)
    T = []
    for x in m:
        e, d, lg = x["ev"], x["dep"], x["lig"]
        L = st.mean(lig[lg]) if len(lig[lg]) >= 40 else None
        if L and len(at[e]) >= isinma and len(at[d]) >= isinma:
            def kat(v):
                return (sum(v) + buzulme * L) / (len(v) + buzulme) / L
            lam = L * (kat(at[e]) * kat(ye[d]) + kat(at[d]) * kat(ye[e]))
            T.append({"lam": lam, "taban": 2 * L, "gercek": x["top"]})
        at[e].append(x["ev_k"]); ye[e].append(x["dep_k"])
        at[d].append(x["dep_k"]); ye[d].append(x["ev_k"])
        lig[lg] += [x["ev_k"], x["dep_k"]]
    return T


def _egim(T):
    """gercek_sapma = a * lam_sapma  regresyon egimi (kesme yok, sapmalar)."""
    xs = [t["lam"] - t["taban"] for t in T]
    ys = [t["gercek"] - t["taban"] for t in T]
    pay = sum(a * b for a, b in zip(xs, ys))
    payda = sum(a * a for a in xs)
    return pay / payda if payda else 0.0


def olc3(egitim="2526", sinav="2627") -> None:
    """Buzulme katsayisini EGITIM sezonunda olc, SINAV sezonunda dogrula.

    Ayni veride hem olcup hem sinamak, modelin kendi kendini onaylamasidir.
    Katsayi burada 2025/26'da tahmin edilir ve 2026/27'ye HIC DOKUNMADAN
    uygulanir.
    """
    me = maclar(egitim)
    print(f"═══ olc3 · egitim {egitim} ({len(me)} mac) → sinav {sinav} ═══\n")
    Te = _lambda_uret(me)
    a = _egim(Te)
    print(f"1) EGITIM SEZONUNDA OLCULEN EGIM: a = {a:.3f}")
    print(f"   Yani modelin lig ortalamasindan sapmasinin yalnizca "
          f"%{100*a:.0f}'i gerceklesiyor.")
    print(f"   duzeltilmis lam = taban + {a:.3f} × (ham_lam − taban)")
    ms = maclar(sinav)
    print(f"\n2) SINAV SEZONU: {len(ms)} mac (korner verisi olan)")
    Ts = _lambda_uret(ms)
    print(f"   tahmin edilebilen: {len(Ts)}")
    if len(Ts) < 60:
        print("   ⚠️ Sezon yeni, orneklem kucuk. Sonuc AYIRT EDICI DEGIL;")
        print("   asagidaki sayilar yon gosterir, kapi olarak kullanilamaz.")
    if not Ts:
        return
    for ad, f in (("ham model", lambda t: t["lam"]),
                  ("duzeltilmis", lambda t: t["taban"] + a*(t["lam"]-t["taban"])),
                  ("naif taban", lambda t: t["taban"])):
        h = st.mean([abs(f(t) - t["gercek"]) for t in Ts])
        print(f"   MAE {ad:<14} {h:.3f}")
    # negatif binom k: egitim sezonundan
    top_e = [t["gercek"] for t in Te]
    mu, var = st.mean(top_e), st.variance(top_e)
    k = (mu*mu) / max(var - mu, 1e-6)
    print(f"\n3) CIZGI BAZINDA (negatif binom, k={k:.1f} egitimden)")
    print(f"   {'cizgi':<7}{'n':<6}{'ham':<20}{'duzeltilmis':<20}{'naif':<20}")
    for c in CIZGI:
        g = [1 if t["gercek"] > c else 0 for t in Ts]
        if not g: continue
        gr = sum(g)/len(g)
        def oz(f):
            p = [_negbin_ust(c, max(f(t), 0.5), k) for t in Ts]
            br = sum((x-y)**2 for x, y in zip(p, g))/len(g)
            return f"%{100*st.mean(p):.0f}→%{100*gr:.0f} B{br:.3f}"
        print(f"   {c:<7}{len(g):<6}"
              f"{oz(lambda t: t['lam']):<20}"
              f"{oz(lambda t: t['taban']+a*(t['lam']-t['taban'])):<20}"
              f"{oz(lambda t: t['taban']):<20}")
    print("\n4) SINAVDA DILIM TESTI (duzeltilmis lam)")
    Ts.sort(key=lambda t: t["lam"])
    n = len(Ts); dl = max(1, n//4)
    for i in range(4):
        p = Ts[i*dl:(i+1)*dl] if i < 3 else Ts[3*dl:]
        if not p: continue
        print(f"   {i+1}/4  n={len(p):<5} ort lam {st.mean([t['lam'] for t in p]):.2f}"
              f"  → gercek {st.mean([t['gercek'] for t in p]):.2f}")


# ---------------------------------------------------------------------------
def _sezon_katsayi(m, buzulme=3):
    """Bir sezonun TAMAMINDAN takim atak/savunma katsayisi (lig-normalize)."""
    at = defaultdict(list); ye = defaultdict(list); lig = defaultdict(list)
    takim_lig = {}
    for x in m:
        e, d, lg = x["ev"], x["dep"], x["lig"]
        at[e].append(x["ev_k"]); ye[e].append(x["dep_k"])
        at[d].append(x["dep_k"]); ye[d].append(x["ev_k"])
        lig[lg] += [x["ev_k"], x["dep_k"]]
        takim_lig[e] = lg; takim_lig[d] = lg
    K = {}
    for t in at:
        L = st.mean(lig[takim_lig[t]])
        if not L:
            continue
        K[t] = {"atak": (sum(at[t]) + buzulme*L)/(len(at[t])+buzulme)/L,
                "sav":  (sum(ye[t]) + buzulme*L)/(len(ye[t])+buzulme)/L,
                "n": len(at[t])}
    return K, {lg: st.mean(v) for lg, v in lig.items()}


def olc4(gecmis="2425", sinav="2526") -> None:
    """GECEN SEZON katsayilari, YENI sezonun ILK maclarini tahmin ediyor mu?

    Sezon basinda takimin bu sezona ait 2-3 maci var; dogrulanmis ayar 10
    mac istiyor. Alternatif gecen sezonun katsayisini kullanmak -- ama
    takimlar degisiyor (transfer, teknik direktor, lig degistirme). Bunun
    ISE YARAYIP YARAMADIGI VARSAYILAMAZ, olculur.
    """
    mg = maclar(gecmis); msn = maclar(sinav)
    K, ligort = _sezon_katsayi(mg)
    print(f"═══ olc4 · {gecmis} katsayilari → {sinav} maclari ═══")
    print(f"   {gecmis}: {len(mg)} mac, {len(K)} takim katsayisi")
    print(f"   {sinav}: {len(msn)} mac\n")
    A = 0.334          # olc3'te olculen buzulme egimi
    # sinav sezonunun ILK N macini al -- sezon basi durumunu taklit eder
    lig_say = defaultdict(int)
    T = []; kapsam = 0
    for x in msn:
        lig_say[x["lig"]] += 1
        if lig_say[x["lig"]] > 60:        # ~ilk 6 hafta
            continue
        ke, kd = K.get(x["ev"]), K.get(x["dep"])
        L = ligort.get(x["lig"])
        if not (ke and kd and L):
            continue
        kapsam += 1
        ham = L * (ke["atak"]*kd["sav"] + kd["atak"]*ke["sav"])
        taban = 2 * L
        T.append({"lam": taban + A*(ham-taban), "ham": ham,
                  "taban": taban, "gercek": x["top"]})
    print(f"   sezon basi tahmin edilebilen: {len(T)}")
    if len(T) < 200:
        print("   yetersiz"); return
    for ad, f in (("gecen sezon (duzeltilmis)", lambda t: t["lam"]),
                  ("gecen sezon (ham)", lambda t: t["ham"]),
                  ("naif lig ortalamasi", lambda t: t["taban"])):
        print(f"   MAE {ad:<28} {st.mean([abs(f(t)-t['gercek']) for t in T]):.3f}")
    mu = st.mean([t["gercek"] for t in T]); var = st.variance([t["gercek"] for t in T])
    k = (mu*mu)/max(var-mu, 1e-6)
    print(f"\n   {'cizgi':<7}{'n':<6}{'gecen sezon':<20}{'naif':<20}")
    for c in CIZGI:
        g = [1 if t["gercek"] > c else 0 for t in T]
        gr = sum(g)/len(g)
        def oz(f):
            pr = [_negbin_ust(c, max(f(t), 0.5), k) for t in T]
            return (f"%{100*st.mean(pr):.0f}→%{100*gr:.0f} "
                    f"B{sum((a-b)**2 for a,b in zip(pr,g))/len(g):.3f}")
        print(f"   {c:<7}{len(g):<6}{oz(lambda t: t['lam']):<20}"
              f"{oz(lambda t: t['taban']):<20}")
    T.sort(key=lambda t: t["lam"]); n=len(T); dl=max(1,n//4)
    print("\n   DILIM TESTI")
    for i in range(4):
        pz = T[i*dl:(i+1)*dl] if i<3 else T[3*dl:]
        if pz: print(f"     {i+1}/4 n={len(pz):<5} lam {st.mean([t['lam'] for t in pz]):.2f}"
                     f" → gercek {st.mean([t['gercek'] for t in pz]):.2f}")


# ---------------------------------------------------------------------------
def olc5(*sezonlar) -> None:
    """LIG ortalamasi sezondan sezona kararli mi?

    Sezon basinda takim modeli kullanilamiyor (10 mac isinma). Geriye lig
    ortalamasi kaliyor -- ama cari sezonda o da 2 haftalik. Gecen sezonun
    lig ortalamasini kullanmak MAKUL GORUNUYOR; makul gorunmek yeterli
    degil, KARARLILIK olculur.
    """
    sez = sezonlar or ("2324", "2425", "2526")
    tab = {}
    for s in sez:
        m = maclar(s)
        d = defaultdict(list)
        for x in m:
            d[x["lig"]].append(x["top"])
        tab[s] = {k: (st.mean(v), len(v)) for k, v in d.items() if len(v) >= 100}
        print(f"   {s}: {len(m)} mac · {len(tab[s])} lig")
    ortak = set.intersection(*[set(v) for v in tab.values()]) if tab else set()
    print(f"\n═══ olc5 · {len(ortak)} ligde {len(sez)} sezon ═══\n")
    print(f"   {'lig':<6}" + "".join(f"{s:<9}" for s in sez) + "yayilim")
    farklar = []
    for lg in sorted(ortak):
        v = [tab[s][lg][0] for s in sez]
        farklar.append(max(v) - min(v))
        print(f"   {lg:<6}" + "".join(f"{x:<9.2f}" for x in v) +
              f"{max(v)-min(v):.2f}")
    print(f"\n   ligler arasi yayilim (sezon icinde): "
          f"{min(tab[sez[-1]][l][0] for l in ortak):.2f} … "
          f"{max(tab[sez[-1]][l][0] for l in ortak):.2f}")
    print(f"   AYNI ligin sezonlar arasi yayilimi: medyan {st.median(farklar):.2f}"
          f" · en cok {max(farklar):.2f}")
    # ardisik sezon tahmini: gecen sezon ortalamasi bu sezonu ne kadar tutar
    if len(sez) >= 2:
        h = [abs(tab[sez[-2]][l][0] - tab[sez[-1]][l][0]) for l in ortak]
        genel = st.mean([tab[sez[-1]][l][0] for l in ortak])
        h2 = [abs(genel - tab[sez[-1]][l][0]) for l in ortak]
        print(f"\n   {sez[-2]} ortalamasi -> {sez[-1]} tahmini : MAE {st.mean(h):.3f}")
        print(f"   TUM ligler ortalamasi   -> {sez[-1]}   : MAE {st.mean(h2):.3f}")
        print(f"   → lig kimligi {'BILGI TASIYOR' if st.mean(h) < st.mean(h2) else 'tasimiyor'}")


if __name__ == "__main__":
    import sys
    sez = sys.argv[1] if len(sys.argv) > 1 else "2526"
    a = sys.argv[2] if len(sys.argv) > 2 else "1"
    if a == "2":
        olc2(sez)
    elif a == "5":
        olc5()
    elif a == "4":
        olc4(sez, sys.argv[3] if len(sys.argv) > 3 else "2526")
    elif a == "3":
        olc3(sez, sys.argv[3] if len(sys.argv) > 3 else "2627")
    else:
        olc(sez)
