# ÖN KAYIT — MÜHÜRLÜ

**Yazim tarihi:** 2026-08-20 (ilk oneri gonderilmeden ONCE)
**Kural:** Bu dosya degistirilirse golge sayaci SIFIRLANIR.

## Neden bu dosya var

BtcTurk botunda 81 kombinasyonun ic-orneklem en iyisi +%255,7 getirdi,
dis orneklemde -%68,6 oldu. Kriter sonradan yazilirsa her sonuc basari
gibi gorunur. Bu yuzden kriterler ONCE yazildi.

## Botun edge iddiasi

**YOKTUR.** Mekanizma v1.0 kazanc vaat etmez; maliyeti asgariye indirir.
Beklenen deger her oneride NEGATIFTIR ve her mesajda yazilir.

## Hipotezler

- **H1 (temel):** Gerceklesen getiri, mekanizmanin onceden yazdigi EV'ye esittir.
  Yani kayip, ilan edilen -%14…-%17 bandinda seyreder.
- **H2:** Nesine'nin devig edilmis olasiliklari KALIBREDIR. Bot "%70 isabet"
  dediginde gercek isabet %65-75 arasindadir.
- **H3 (tek ilginc olasilik):** En ucuz marketlerden secmek sistematik bir
  sapma yakalar ve gerceklesen getiri EV'yi ISTATISTIKSEL OLARAK asar.

## Basarisizlik kriterleri — onceden yazildi

| # | Kosul | Sonuc |
|---|---|---|
| R1 | 300 bacak sonrasi kalibrasyon bozuk (%70 kovasi %60-80 disinda) | Devig yontemi gecersiz → mekanizma OLU |
| R2 | Gerceklesen getiri, EV'nin 2 standart hatasindan KOTU | Model kendi maliyetini bile bilemiyor → OLU |
| R3 | \`MEKANIZMA_v1.0.md\` hash'i tutmuyor | Golge sayaci SIFIR, kapi bastan baslar |
| R4 | Divergence (bagimsiz yeniden hesap) sapma verirse | Alarm; 3 sapma → OLU |
| R5 | 180 gun doldu, n<300 bacak | Ekonomik olarak olu; kapi UZAR, parametre kurcalanMAZ |

## ROI KAPI DEGILDIR

Bahis basi standart sapma ~1,9. n=300'de standart hata ~%11. Yani 300 bahiste
"kar ettim / zarar ettim" ayrimi ISTATISTIKSEL OLARAK YAPILAMAZ. ROI'yi kapi
yapmak, gurultuye anlam yuklemektir. Anlamli bir ROI kapisi icin n≥1500 gerekir;
gunde 1 oneriyle bu 4 yildir. Bu yuzden kapi KALIBRASYONDUR.

## H3 dogrulanirsa ne olur

Hicbir sey — otomatik olarak. H3 dogrulanirsa ayri bir konsul turu acilir.
Tek basina "kar cikti" diye stake yukseltilmez. (BtcTurk dersi: kuyruk asiri
konsantre, en iyi 5 islem tum kari tasiyordu.)

## Hash degisimleri (R3 kaydi)

| Tarih | Sebep | Golge sayaci |
|---|---|---|
| 2026-08-21 | `coupon._pick` kapsam disi markette KeyError ile cokuyordu; arsiv 2→20 markete genisleyince `daily.py` TAMAMEN calismiyordu. Tek satirlik koruma eklendi. Secim mantigi MTID 1 ve 3 icin AYNI kaldi. | Sifirlandi (o an 1 kayit vardi, maliyet yok) |

**KURAL DEGISMEDI:** hash degisimi golge sayacini sifirlar. Bu bir hata
duzeltmesi olsa bile istisna yapilMAZ — istisna yapmaya baslarsak kural
anlamini yitirir.

## Yasaklar

- Parametreler kar cikana kadar kurcalanMAZ.
- Bot "haklı ciktigi" hafta stake YUKSELTILMEZ.
- Kayip telafisi icin bacak sayisi ARTIRILMAZ (marj carpimsal, tam tersi olur).
- Kimligi kanitlanMAMIS market kapsama EKLENMEZ.
