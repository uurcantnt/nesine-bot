# nesine-bot

Nesine bulteninden **maliyeti en dusuk** bahsi bulup Telegram'a oneri gonderen bot.
Bahsi bot oynamaz — kuponu kullanici kendi eliyle oynar.

## Once sunu oku

Bu bot **kazandirmaz.** Nesine'nin olculen marji %21,1; tek bahiste beklenen
getiri **-%17,4**, 3 macli kuponda **-%43,6**. Basabas icin gereken CLV de
%21,1 — yani marjin kendisi. Botun yaptigi sey ayni bahsi **en ucuz** sekilde
oynatmak ve her mesajda beklenen degeri acikca yazmaktir.

Detay: `MEKANIZMA_v1.0.md` (dondurulmus sartname) ve `ON_KAYIT.md` (basarisizlik
kriterleri, ilk oneri gonderilmeden once yazildi).
Ayrica `YAPILMAYACAKLAR.md` — olculerek elenmis fikirler; yeni bir model
onerisi gelmeden ONCE okunur.

## 2026-08-21 konsul turu — 5 degisiklik

Bes danisman + uc akran incelemesi modelin o anki halini degerlendirdi.
Uzerinde HEMFIKIR olunan bes nokta uygulandi:

1. **Asil kisit model degil aritmetik** — `YAPILMAYACAKLAR.md` yazildi.
   Bacak sayisi, modeldeki her iyilestirmeden buyuk kaldirac: modelin
   Nesine'den sapmasi ~5 puan, bir bacak eklemek 14 puan maliyet ekliyor.
2. **"Kaynaklarin minimumunu al" kurali kaldirildi** (`src/havuz.py`).
   Olculdu: o kural secenek olasiliklari toplamini 1'den 0,93'e dusuruyordu
   — her tahmine ~6,9 puan GIZLI asagi yanlilik. Yerine ters-varyans
   agirlikli LOGIT HAVUZU geldi; ayni testte sapma 0,06 puan. Ihtiyat
   kaybolmadi, gorunur bir kalem oldu (`havuz.GUVENLIK_PAYI`, 3 puan,
   yalnizca secim kapisinda). Kalibrasyon artik olculebilir.
3. **Tek mac onceligi** (`src/maliyet.py`) — Nesine maclarin %59'unda en az
   3 mac zorunlu kiliyor; tek oynanabilen 169 mac havuzda kayboluyordu.
   Artik ayri bolum. Her kuponun ustune kendi maliyet aritmetigi yaziliyor.
4. **Parametreler SONUCA gore yeniden sinandi** (`src/walkforward.py`).
   xG karisim orani (%33) ve tavan (3,0) "Nesine fiyatindan az sap"
   olcutuyle secilmisti — o olcut ISABETI degil TAKLIDI odullendirir.
   Gerceklesen sonucla olculunce 6 varyant arasindaki en buyuk fark
   **0,0004 Brier**; hicbiri ayirt edilemiyor. Parametreler DEGISMEDI ama
   "olculdu ve kazandi" iddiasi geri cekildi.
5. **Hacim kontrolu** (`src/hacim.py`) — gunluk 2 / haftalik 5 kupon,
   haftalik 100 TL (muhurlu aylik 400 TL tavanindan turetildi), sabit
   20 TL birim. Kapiya takilinca bot **"bugun pas"** der ve oneri URETMEZ.

### Yan bulgu: onceki karsilastirma HATALIYDI

Onyukleme SECIM duzeyinde yapiliyordu; ama 198 secim 40 MACTAN geliyor ve
ayni macin secenekleri mekanik olarak bagimli (1X2 toplami 1). Mac duzeyinde
kumelenince sonuc dondu:

| | secim duzeyi (hatali) | mac duzeyi (dogru) |
|---|---|---|
| Brier farki | +0,00679 | **-0,00292** |
| t | +0,75 | **-0,19** |
| %95 aralik | [-0,011, +0,024] | **[-0,032, +0,026]** |

Yani "modelimiz Nesine'den biraz iyi gorunuyor" ifadesi dusuyor. Model,
bir fark varsa, biraz daha KOTU. Etkin orneklem 198 degil **40**.

**Muhurlu mekanizma (`core/odds/coupon`) bu turda DEGISMEDI** — R3 hash ve
R4 bagimsiz hesap dogrulandi, golge sayaci sifirlanMADI.

## Veri yazma kurali (git cakismasi onlemi)

`data/` altina **YALNIZCA GitHub Actions yazar** (`src/depo.py` kilidi).
Yerelde her sey okunur ve hesaplanir ama hicbir sey yazilmaz.

NEDEN: veri dosyalari hem yerelden hem Actions'tan yazilinca rebase
cakismasi cikti; bir kez `reset --hard` yeni kod dosyalarini sildi.

- Actions'ta `CI=true` otomatik tanimli -> yazar
- Yerelde yazilmaz; bilerek yazmak gerekirse `NESINE_YAZ=1` verilir
- Yerel test: `python3 tiers.py --dry` (tam mantik, gercek veri, sifir yazma)

## Kullanim

```bash
cd src
python3 bulletin.py          # snapshot al + arsivle
python3 daily.py 1           # tek maclik oneri gonder
python3 daily.py 3           # 3 bacakli kupon onerisi (EV cok daha kotu, mesajda yazar)
python3 daily.py 1 --dry     # gondermeden ekrana yaz
python3 verify.py            # oz-denetim (R3 hash + R4 bagimsiz yeniden hesap)
```

Python 3.9+ yeterli — **harici bagimlilik yok**, sadece standart kutuphane.

## /kupon — iki tur, uc risk seviyesi

`src/tiers.py`. MAC ONU ve CANLI icin ayri ayri uc seviye uretir.

**Kurallar (tiers.py'de, core.py'ye DOKUNMAZ -- mekanizma hash'i saglam kalir):**

- `MIN_KUPON_ORAN = 1.40` — toplam orani bunun altinda kalan kupon ONERILMEZ.
  Aritmetik sonucu: marj %17 iken tek macta `p = 0.83 / oran`, yani 1.40 tabani
  isabet olasiligina **%59 tavan** koyar. "Az riskli" %70 isabet ISTEYEMEZ.
- **Isabet tabani** — bacak sayisi hedef degil TAVAN. Bir bacak daha eklemek
  kuponun toplam isabetini tabanin altina dusuruyorsa o bacak EKLENMEZ; kupon
  1-2 bacakla kalir. ("3 mac verecegim" diye anlamsiz bacak eklemek marj
  carpimsal oldugu icin hem isabeti hem EV'yi bozar.)
- `CANLI_MAX_MARJ = 0.28` — canli marjlar olculdu %21-25; maç oncesinin %22
  kapisi canlinin yarisini eliyordu.
- `CANLI_MIN_BACAK_ORAN = 1.05` — oran tabani BACAK duzeyinde degil KUPON
  duzeyinde uygulanir. Canli cifte sanslar tek basina 1.06-1.15 oduyor ama
  ikisi birlesince 1.21'e cikip %57 isabetli gercek bir kupon oluyor.

Uretilemeyen seviye SESSIZCE atlanmaz; nedeni mesaja yazilir
("bantta aday yok", "toplam oran 1.12 < 1.4", "isabet tabani %12 korundu").

**Canli maclarda skor/dakika alani YOK** — bot macin 89'unda 0-2 geride oldugunu
dogrudan goremez. Koruma orandir: 89'da 0-2 geride olan takim %45 fiyatlanmaz.

## Oran hareketi (NOT satiri)

`bulletin.hareket()` arsivden gecmis orani okur; mesajda soyle gorunur:

```
NOT: 1 saat önce 4,88 idi → şimdi 4,72 (%3,3 düştü)
     piyasa bu ihtimali artık daha YÜKSEK görüyor
```

- Pencereler kademeli: `(1, 3, 6, 12, 24)` saat. En UZUN elde olan ve gercekten
  degismis pencere secilir; arsiv 1 saatlikken de bilgi uretir.
- Esik `%2,5` — altindaki oynamalar gurultu sayilir, yazilmaz.
- Delta arsivde mac yoksa "degismedi" demektir; bu yuzden `oran_at()` t'den
  geriye dogru gidip macin GORULDUGU ilk dosyayi kullanir.
- **Canli maclarda NOT satiri YOK** — canli oranlar arsivlenmiyor.

## Marj NASIL hesaplaniyor (yaygin yanlis anlama)

Marj **baska sitelerle karsilastirilarak** bulunmuyor. Tamamen Nesine'nin KENDI
oranlarindan: bir marketteki tum seceneklerin `1/oran` toplami 1'i ne kadar
asiyorsa, o fazlalik Nesine'nin payidir. Disaridan hicbir veri kullanilmaz.

README'de gecen "Pinnacle ~%2,5 / Bet365 ~%6" rakamlari genel bilgidir,
bu bot tarafindan OLCULMEDI. Olculen tek sey Nesine'nin kendi marjidir.

## Saat dilimi

Tum mesajlarda saatler **Turkiye saatidir** (`src/trtime.py`, sabit UTC+3 —
Turkiye 2016'dan beri yaz saati uygulamiyor).

GitHub Actions runner'lari UTC'de kosar; `datetime.now()` ve `.astimezone()`
runner'da UTC uretir ve mesajlarda saat 3 saat geri gorunur (16:47 vs 19:47).
Bu yuzden saat ACIKCA cevrilir. Mac saatleri bultendeki `ESD` (epoch ms)
alanindan hesaplanir; 965 macta Nesine'nin kendi gosterdigi `D`/`T` alanlariyla
birebir dogrulandi (0 fark).

## Market kapsami (2026-08-21 genisletildi)

**Market isimleri artik TAHMIN DEGIL.** Nesine'nin kendi sitesindeki
`CCAll.min.js` dosyasindan tam market sozlugu cikarildi: **559 market tipi**,
her biri isim + secenek listesiyle.

DOGRULAMA: katalogdaki secenek sayisi, bultendeki gercek secenek sayisiyla
karsilastirildi — **28.983 mac oncesi + 51 canli market kontrol edildi,
0 uyusmazlik**. Secenekleri dinamik uretilen marketler (kesin skor gibi
29-68 secenekli) katalogda secenek tasimadigi icin otomatik disarida kalir.

Bu, daha once davranistan cikardigimiz kimlikleri de dogruladi:
`53`=Mac Sonucu, `55`=Cifte Sans, `56`="Kalan Sureyi Kim Kazanir?" — ucu de tuttu.

`catalog.KAPSAM` (20 market) arsivlenir ve /kupon'da kullanilir:
Mac Sonucu, Cifte Sans, 1,5/2,5/3,5 Gol Alt/Ust, Karsilikli Gol, Tek/Cift,
1.Y Sonucu/CS/Alt-Ust, Ev Sahibi ve Deplasman Alt/Ust, Toplam Gol Araligi,
Handikapli MS, **Korner Alt/Ust, 1.Y Korner, Kart Puani, En Cok Korner,
Toplam Korner Araligi**.

Canli kapsam: Mac Sonucu, Cifte Sans, Handikapli MS, 2.Y Sonucu,
Karsilikli Gol, Tek/Cift, 2.Y Karsilikli Gol.

Arsiv boyutu: 2 marketle 45 KB -> 20 marketle **133 KB** tam snapshot
(~1,6 MB/gun). Aylik sikistirma/rotasyon ileride gerekecek.

**ONEMLI:** korner marji olculdu, medyan **%21,1** — mac sonucuyla ayni.
Korner daha kolay tahmin edilebilir olabilir ama daha ucuz bilet DEGIL.

## Her secimin gerekcesi

Mesajda her bacak icin: ne zaman, bahsin duz Turkce anlami, tutma ihtimali,
hak ettigi oran, Nesine'nin verdigi oran ve aradaki fark, **NEDEN SECILDI**
(havuzdaki kacinci en ucuz secenek + hangi olasilik bandina girdigi) ve varsa
**NOT** (oranin arsivdeki gecmisi).

Bot tahmin YAPMAZ: istatistige, forma, sakatliga bakmaz. Tek yaptigi ayni riski
en ucuz veren secenegi bulmaktir. Bu mesajda acikca yazilidir.

## Market kimligi

Nesine market tipi (MTID) icin isim veren bir endpoint YOK. Isim uydurmamak icin
bot yalnizca kimligi **kanitlanmis** marketleri kullanir:

- `MTID=1` **Mac Sonucu** — 3 secenek, SOV=0, overround ~1,21 (yapisal)
- `MTID=3` **Cifte Sans** — her secenegi 3 sonucun 2'sini kapsar. MS'ten
  turetilen olasiliklarla capraz dogrulandi: 690 macta medyan maks-hata
  **0,0094**, maclarin **%99,9**'unda hata < 0,02.

Poisson tabanli seviye eslestirmesiyle alt/ust ve KG marketleri de denendi;
hicbiri "kesin" esigini gecmedi (en iyi MAE 0,042-0,08). Bu yuzden kapsam disi.

**Canlida MTID uzayi FARKLI:** `53`=Mac Sonucu, `56`=Kalan Mac Sonucu (gol
atilinca 53'ten ayrisir), `55`=Cifte Sans. 55'in hangisiyle eslestigi
kanitlanamadi (ayrisan maclarda 55 yok). Bu yuzden `canli_ms_dogrula()` her maci
CALISMA ANINDA test eder: cifte sans imzasi tutmuyorsa mac ATLANIR. Olculdu:
22 canli macin 4'u gecti ve **hepsinde 53==56** — yani hangi yorum dogru olursa
olsun kullanilan oran dogru.

## Veri

`data/arsiv/YYYY-MM-DD/HHMMSS.json.gz` — delta arsiv. 00 ve 12 UTC'de tam
snapshot (~45 KB), arada yalnizca orani degisen maclar (3-8 KB).
`oddVersion` degismediyse hic yazilmaz.

Yeniden kurma: `bulletin.latest()` son tam snapshot + sonraki deltalari uygular.

## CDN kismi yanit anomalisi

Nesine CDN'i **seyrek olarak** ~960 yerine ~96-98 mac donduruyor (2026-08-20'de
2 kez goruldu; hemen ardindan yapilan 10 ve 6 istekte 0 kez). Muhtemel sebep:
edge cache yenilenirken yarim nesnenin servis edilmesi.

Korunma iki katmanli:
- `sanity()` — onceki bilinen mac sayisinin %50'sinden az gelirse arsive YAZMAZ
- `run(deneme=3)` — kotu yanitta 4 sn bekleyip tekrar dener, hepsi basarisizsa
  `data/anomali.jsonl`'a yazip hata verir

Bu kapi olmasaydi tek bir kotu yanit TAM snapshot olarak arsive girip tum
gecmisi bozacakti.

## Bilinen eksikler

- **Sonuc eslestirmesi yok.** Nesine'nin sonuc endpoint'i bulunamadi; canli
  bultende skor alani yok. Golge kayitlar (`data/golge.jsonl`) mac ID ve tarih
  tasidigi icin geriye donuk doldurulabilir. ON_KAYIT'taki kalibrasyon kapisi
  bu cozulene kadar OLCULEMEZ.
- Canli bahis kapsam disi (Actions cron 5 dk cozunurluk, canli icin yetersiz).
