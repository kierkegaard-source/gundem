# Faz 3 — Dedupe + skorlama (2026-08-30)

```
449 kayıt → 386 tekil madde (63 mükerrer birleşti) → 60 madde sayıya girdi
dedupe süresi: 104 ms
```

## Yazılan dosyalar

- `pipeline/dedupe.py` — iki kademeli tekilleştirme, `Cluster` veri yapısı
- `pipeline/score.py` — PROJECT.md §7.1 formülü, kategori/toplam filtreleri
- `pipeline/db.py` — `upsert_clusters()`, `published_hashes()`, `item_aliases` tablosu
- `tests/test_dedupe_score.py` — 13 test

## Tasarım kararı: bulanık eşleşme yalnızca kaynaklar arası

Kaynak içi mükerrer zaten URL ile yakalanıyor (Faz 2: 63 mükerrerin hepsi Bluesky'da,
hepsi aynı URL'e düşüyordu). Kaynak içinde bulanık eşleşme açılırsa yanlış pozitif riski
kazancından büyük olurdu — ölçüldü:

```
"adventure honor chronicles" / "adventure horror chronicles"
    token_sort 94, token_set 94   ← iki AYRI Steam oyunu, %85 eşiğini rahat geçiyor
```

Bu iki oyun aynı kaynaktan geldiği için kural gereği kıyaslanmıyor. Hedef vaka zaten
kaynaklar arası: aynı ürünün Product Hunt + HN + Twitter'da çıkması.

## Bulunan hata 1: metriksiz kaynaklar sıralamayı ele geçiriyordu

RSS ve itch.io'da popülerlik metriği yok; koda `raw_score = 1.0` sabiti giriyor.
Kaynak içinde normalize edilince bu **1.0** oluyor — yani o kaynağın *maksimumu*.
Sonuç: Techmeme'in 15. haberi, HN'in 1. sırasıyla eşit skor alıyordu.

İlk koşuda `startup` kategorisinin 15 slotunun tamamı RSS'e gitmişti ve ilk 20 satırın
13'ü Techmeme başlığıydı.

**Çözüm:** bir kaynağın tüm maddeleri aynı ham puanı taşıyorsa o kaynakta metrik yoktur;
normalize değer olarak nötr `0.5` kullanılır, sıralamayı kaynak ağırlığı ve tazelik belirler.
Karar veriden çıkarılıyor, elle işaretleme yok.

Düzeltme sonrası ilk sıralar Product Hunt lansmanlarına ve Show HN'e geçti —
"bugün ne çıktı" gazetesi için doğru davranış. RSS 0.561'den 0.365'e indi.

## Bulunan hata 2: tek bulanık ölçüt gerçek eşleşmeleri kaçırıyor

PROJECT.md "rapidfuzz ile %85 üzeri benzerlik" diyor ama hangi ölçüt olduğunu söylemiyor.
`token_sort_ratio` ile ölçüldü:

| A | B | sort | set | olması gereken |
|---|---|---:|---:|---|
| quantum ledger studio | quantum ledger studio is live | **84** | 100 | birleşmeli |
| hyperfocus planner | hyperfocus planner turns goals into daily progress | **31** | 100 | birleşmeli |
| olostep | olostep turn the web into clean data for ai | **28** | 100 | birleşmeli |
| claude code cli | claude code sdk | 73 | **85** | birleşmemeli |

Tek başına `token_sort_ratio` üç gerçek eşleşmeyi de kaçırıyor. Tek başına
`token_set_ratio` 85 eşiğiyle "claude code cli/sdk"yi yanlış birleştiriyor.

**Çözüm:** iki ölçüt birlikte —
`token_sort_ratio ≥ 85` **veya** (`token_set_ratio ≥ 92` **ve** kısa başlıkta ≥2 kelime).
Tek kelimelik başlıklar set ölçütünden muaf, çünkü alt küme durumunda set 100 veriyor
("Bolt", "Bolt Action Combat Simulator" içinde 100 alır).

Gerçek veride bu değişiklik **0 ek birleşme** yaptı — yani yanlış pozitif getirmedi.

## Bulunan hata 3: uzunluk ön filtresi alt küme eşleşmesini engelliyordu

Hızlandırma amaçlı `abs(len(a)-len(b)) > max(len)*0.5` kuralı,
"Hyperfocus Planner" (18) ile "Hyperfocus Planner turns goals into daily progress" (49)
arasındaki 31 karakterlik farkı eleyip eşleşmeyi öldürüyordu. Kaldırıldı —
297 küme için O(n²) karşılaştırma 104 ms sürüyor, ön filtreye gerek yok.

## Günler arası tekrar koruması

Günlük gazete aynı maddeyi iki kez basmamalı. İki mekanizma:

- `items.digest_date IS NOT NULL` olan maddeler filtrelemede dışlanıyor
- `item_aliases` tablosu kümedeki **tüm** üye hash'lerini temsilciye bağlıyor —
  yarın aynı ürün başka bir kaynaktan gelirse yine yakalanıyor

## Testler — 13/13 geçiyor

| Test | Neyi doğruluyor |
|---|---|
| `test_ayni_url_farkli_kaynaklar_tek_maddeye_iniyor` | utm/www farkı olan iki URL birleşiyor |
| `test_ayni_urun_uc_kaynakta_tek_satir_uc_rozet` | **PROJECT.md §12 kabul kriteri** |
| `test_ayni_kaynaktaki_benzer_basliklar_BIRLESMIYOR` | Adventure Honor/Horror ayrı kalıyor |
| `test_tek_kelimelik_baslik_uzun_baslige_gomulmuyor` | Bolt / Bolt Action ayrı kalıyor |
| `test_alt_kume_basliklar_birlesiyor` | Hyperfocus Planner eşleşmesi |
| `test_coklu_kaynak_bonusu_uygulaniyor` | ×1.4 bonusu |
| `test_metriksiz_kaynak_notr_normalize_ediliyor` | hata 1'in regresyon testi |
| `test_recency_esikleri` | 0-6/6-12/12-24/24+ sınırları |
| `test_kategori_ve_toplam_tavani` | max_per_category, max_total |
| `test_daha_once_yayinlanan_madde_tekrar_girmiyor` | günler arası tekrar |

**Not:** §12'nin çoklu kaynak kriteri bugünkü gerçek veriyle doğrulanamıyor —
kaynaklar arası çakışma 0. Sentetik testle doğrulandı; gerçek veride ilk çakışma
görüldüğünde tekrar bakılacak.

## Sayının son hali

| kategori | madde |
|---|---:|
| dev | 15 |
| gamedev | 15 |
| startup | 15 |
| apps | 10 |
| design | 5 |
| **toplam** | **60** |

Twitter'ın kişisel tweet'leri hâlâ orta sıralarda ("Okay I built it!", "If I was Indian",
skor 0.46/0.44). Normalizasyon bunları tepeden indirdi ama tamamen elemedi —
Faz 4'ün `signal < 2` filtresi bu iş için.

**Faz 4'e geçilebilir.**
