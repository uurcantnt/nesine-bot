# YAPILMAYACAKLAR — asıl kısıt model değil, aritmetik

**Yazım:** 2026-08-21 · konsül turu sonrası (5 danışman + 3 akran incelemesi)

Bu dosya, gelecekte "şunu da ekleyelim" denince önce okunacak listedir.
Amacı, ölçülerek elenmiş fikirlerin sessizce geri dönmesini engellemek.

## Kısıt

Nesine marjı medyan **%21,1**. Kupon marjı **çarpımsaldır**:

| Bacak | Beklenen getiri |
|---|---|
| 1 | **-%17,4** |
| 2 | -%31,8 |
| 3 | **-%43,6** |
| 5 | -%61,5 |

Modelimizin Nesine fiyatından medyan sapması **~5 puan**. Yani 21 puanlık bir
vergiyi 5 puanlık bir sapmayla avlamaya çalışıyoruz. Bir bacak eklemek 14 puan
maliyet ekliyor — modelde yapılabilecek **hiçbir** iyileştirme buna yaklaşmıyor.

İlk-ilkeler danışmanının cümlesi: *"Bu bir tahmin problemi değil, aritmetik
problemi."*

## Ölçülen: modelimiz Nesine'den isabetli DEĞİL

| Ölçüm | Seçim düzeyi (HATALI) | Maç düzeyi (DOĞRU) |
|---|---|---|
| Brier farkı | +0,00679 | **-0,00292** |
| t | +0,75 | **-0,19** |
| %95 aralık | [-0,011, +0,024] | **[-0,032, +0,026]** |

198 seçim **40 maçtan** geliyor ve aynı maçın seçenekleri mekanik olarak
bağımlı (1X2 toplamı 1). Seçim düzeyinde önyükleme aralığı sahte olarak
daraltıyordu. Doğru hesapta **işaret döndü**: model, eğer bir fark varsa,
biraz daha KÖTÜ.

## Boşa gider — yapılmayacaklar

| Fikir | Neden yapılmıyor |
|---|---|
| **Dixon-Coles düzeltmesi** | Rakip gücü ayarı yokken ikinci derece düzeltme. Beklenen kazanç ~0,005 Brier; marj 0,21. |
| **Bivariate Poisson** | Aynı gerekçe. |
| **xG karışım oranını kurcalamak** | Sonuca göre ölçüldü: 6 varyant arasında en büyük fark **0,0004 Brier**, hepsi ayırt edilemez. "sadece gol" ile "sadece xG" bile ayrılmıyor. |
| **İlk yarı %45 varsayımını kalibre etmek** | Marjın çok altında kalan detay. |
| **Korner/kart marketlerini iyileştirmek** | Değerleri -%17,2, gol marketlerinin en iyisi -%14,6. Nesine bu marketlerden DAHA ÇOK pay alıyor. Ayrı komut olarak kalır, geliştirilmez. |
| **Canlı modeli derinleştirmek** | Hız avantajımız yok, canlı marj daha yüksek (%21-25). |
| **Model kapsamasını %62'den yukarı zorlamak** | Eşleşmeyen %38 alt lig/egzotik. Orada Nesine'nin marjı en yüksek, bizim bilgimiz en düşük. Kapsama bir kalite ölçüsü değil; SEÇİCİLİK avantajdır. |
| **İsabet oranını raporun başına koymak** | Rapor TL cinsinden kümülatif kaybı önce yazar. İsabet oranı iyi hissettirir, kayıp bilgi verir. |
| **İç/dış saha ayrımını geri getirmek** | Ölçüldü ve elendi (4,8p→5,9p). NOT: o eleme de geçersiz ölçütle yapıldı; geri getirilecekse önce `walkforward.py` ayırt edici sonuç vermeli. |

## Yapılabilir sayılanlar (henüz yapılmadı)

Konsülün desteklediği ama bu turda **kapsam dışı** bırakılanlar:

- **Rakip gücü ayarı** (Maher hücum/savunma katsayıları + lig ortalamasına
  shrinkage). Tek başına en büyük model eksiği. 1 hafta+ iş. Danışmanların
  1'i güçlü destek, 2'si karşı.
- **Marj haritası** — market/lig başına overround; -%3,7'lik ucun nerede
  olduğunu bulur. Arşiv zaten birikiyor.
- **CLV ölçümü** — kendi tahminimizi kapanış oranına karşı puanlar; sonuç
  beklemeden sinyal verir.
- **Fotmob eşleşme precision denetimi** — 100 eşleşmeyi elle etiketle.
  Yanlış takım eşleşmesi hata fırlatmaz, sessizce xG'yi bozar.
- **Bonus/iade/vergi kalemlerini EV'ye koymak** — akran turunun ortak
  bulgusu: tekelde ölçülebilir tek gerçek edge kaynağı burası olabilir.

## Kural

Yeni bir model fikri gelirse önce şu soru cevaplanır:

> **Bu, 21 puanlık marjın kaç puanını geri kazandırıyor?**

Cevap "bilmiyorum" ise `walkforward.py` ile ölçülür. Ölçüm ayırt edici
sonuç vermiyorsa fikir **uygulanmaz** — "mantıklı görünüyor" gerekçe değildir.
BtcTurk botunun dersi buydu.
