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

## Market kimligi

Nesine market tipi (MTID) icin isim veren bir endpoint YOK. Isim uydurmamak icin
bot yalnizca kimligi **kanitlanmis** marketleri kullanir:

- `MTID=1` **Mac Sonucu** — 3 secenek, SOV=0, overround ~1,21 (yapisal)
- `MTID=3` **Cifte Sans** — her secenegi 3 sonucun 2'sini kapsar. MS'ten
  turetilen olasiliklarla capraz dogrulandi: 690 macta medyan maks-hata
  **0,0094**, maclarin **%99,9**'unda hata < 0,02.

Poisson tabanli seviye eslestirmesiyle alt/ust ve KG marketleri de denendi;
hicbiri "kesin" esigini gecmedi (en iyi MAE 0,042-0,08). Bu yuzden kapsam disi.

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
