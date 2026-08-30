# Faz 4 — Özetleme (2026-08-30)

```
439 kayıt → 383 tekil madde → 90 aday özetlendi → 29 düşük sinyal elendi → 51-60 madde sayıya girdi
LLM maliyeti: $0.048/gün ≈ $1.45/ay
```

## PROJECT.md'den iki sapma

### 1. Prompt caching KULLANILMIYOR — bu modelde imkânsız

PROJECT.md §7.2: *"Sistem promptu sabit → prompt caching kullan, girdi maliyeti %90 düşer."*

`claude-haiku-4-5`'te cache'lenebilir **minimum önek 4096 token**. Bizim sistem
promptumuz ~300 token. Eşiğin altındaki promptlar **sessizce** cache'lenmiyor —
hata yok, sadece `cache_creation_input_tokens: 0`.

Yapay dolguyla 4096'ya çıkarmak ters teper: cache okuması 4096 × 0.1 = **410
efektif token** eder, gerçek promptumuz zaten **400**. Yani caching bu proje için
maliyeti düşürmez, artırır.

Minimum eşik modele göre değişiyor ve nesillere göre monoton değil —
Opus 5'te 512, Sonnet 5'te 1024, Haiku 4.5'te 4096.

### 2. Yapılandırılmış çıktı KULLANILIYOR — bozuk JSON riski ortadan kalktı

PROJECT.md §11 Faz 4: *"JSON parse + hata toleransı (bozuk JSON gelirse o batch'i
atla, ham başlık kullan)."*

`output_config.format` ile JSON şeması **API seviyesinde** zorlanıyor
(Haiku 4.5 destekliyor). Bozuk JSON dönmesi mümkün değil. Yine de ham başlık
yedeği korundu — ve iyi ki korunmuş (aşağıya bak).

Şema notu: yapılandırılmış çıktıda `minimum`/`maximum` desteklenmiyor,
`signal` için `enum: [1,2,3,4,5]` kullanıldı.

## Bulunan hata 1: filtreleme özetlemeden önce çalışıyordu

`score → filter → summarize` sırasında kategori kotasını **düşük sinyalli**
maddeler kapıyor, sonra `signal` filtresi onları eliyor ve bölüm boş kalıyordu.

İlk koşuda gamedev 15 slotunu Bluesky'ın sanat paylaşımlarına verdi;
eleme sonrası **4 madde** kaldı. Steam'in 52 yeni oyunu hiç şans bulamadı.

**Çözüm:** `filters.summarize_oversample: 1.5` — kotadan %50 fazla aday
özetlenir, eleme sonrası tavan yeniden uygulanır. LLM maliyetini ~%40 artırıyor.

## Bulunan hata 2: metinsiz maddeye LLM haklı olarak 1 veriyordu

Steam arama sonucu yalnızca oyun **adını** veriyor. LLM'e `"Banana Kingdom"`
diye tek kelime gidiyordu; özetlenecek bir şey yok, signal=1.

**Çözüm:** `store.steampowered.com/api/appdetails` ile zenginleştirme —
tür + kısa açıklama. Ücretsiz, appid başına tek istek (toplu istek `null` dönüyor),
5 eşzamanlı, ~8s. **52/52 kayıt zenginleşti.** Başarısız olan madde ham
başlığıyla kalır. itch.io tarafında da feed etiketleri (`[Free] [Puzzle]`)
metne katıldı.

## Bulunan hata 3: itch.io'nun tek feed'i yetmiyor

Ölçüm:

| feed | kayıt | açıklamalı | 26s penceresinde |
|---|---:|---:|---:|
| `newest.xml` | 36 | 18 | 20 |
| `new-and-popular.xml` | 36 | 30 | 2 |
| `featured.xml` | 36 | 36 | 0 |

Taze olan açıklamasız, açıklamalı olan taze değil. **İkisi de çekiliyor:**
`newest` pencereye tabi (bugün çıkanlar), `new-and-popular` değil — sinyali
tazelik değil popülerlik, GitHub Trending'le aynı mantık. Yayın tarihi olduğu
gibi bırakılıyor (yaş sütunu yalan söylemesin), eskiyse `recency_factor` zaten
cezalandırıyor. `raw_score` 1.0 / 2.0 olduğu için skorlama küratörlü listeyi
öne alıyor.

## Bulunan hata 4: sistem promptu yeniliği ünlülükle karıştırıyordu

İlk prompt *"signal puanlamasında katı ol"* diyordu. Sonuç: küçük ama gerçek
bir oyun çıkışı 1 puan alıyor, gamedev bölümü boş kalıyordu.

Ölçek yeniden tanımlandı — signal **ne kadar ünlü** olduğunu değil, **gerçekten
yeni bir şey olup olmadığını** ölçer:

```
5 = geniş kitleyi ilgilendiren önemli yeni ürün/sürüm/haber
4 = açıklaması net, işe yarar yeni araç/oyun/proje
3 = gerçek bir çıkış, niş ya da küçük ölçekli
2 = gerçek bir çıkış ama az bilgi var
1 = çıkış DEĞİL: kişisel görüş, tartışma, meme, sanat paylaşımı, etkinlik izlenimi
```

**Sonuç: gamedev 4 → 15 madde.** Twitter gürültüsü ("If I was Indian",
"Hey Anthropic…") elenmeye devam ediyor.

## Bütçe tavanı testi — GEÇTİ

PROJECT.md §11: *"Tavanı $0.001'e çekip gerçekten durduğunu doğrula."*

```
tavan: $0.001 | 40 madde
sonuç: {'batches': 0, 'summarized': 0, 'skipped_budget': 40, 'degraded': True}
harcanan: $0.000000
```

**Hiç API çağrısı yapılmadı.** Tavan kontrolü çağrıdan önce, `count_tokens` ile
gerçek girdi token'ı sayılarak yapılıyor.

## Kazara canlı dayanıklılık testi

Son koşuda Anthropic bakiyesi tükendi:

```
BadRequestError: 'Your credit balance is too low to access the Anthropic API.'
```

Pipeline **çökmedi**: 5 batch'in hepsi yedek yola düştü, 60 madde ham başlıkla
sayıya girdi, her batch için uyarı notu üretildi, `degraded: True` işaretlendi.
PROJECT.md §2.2 gerçek bir arızada doğrulandı.

Bu bulgu üzerine hata notlarına API mesajının kendisi eklendi — "BadRequestError"
tek başına teşhis için yetmiyordu.

## Örnek çıktı

```
0.624 s4 design   8s  producthunt   Topview Motion Studio
        ↳ Video editlemesini basitleştiren yeni araç.
0.545 s4 dev      8s  producthunt   Olostep
        ↳ Web scraping'i AI için otomatize edip standardize ediyor.
0.388 s3 gamedev 22s  itchio        UNDERSTORY
        ↳ Ilginç mekanikli indie simülasyon oyunu.
```

## Maliyet

| | |
|---|---|
| Batch başına (20 madde) | ~$0.011 |
| Günlük (90 aday, 5 batch) | **$0.048** |
| Aylık | **~$1.45** |
| Tavan | $0.20/gün — 4 kat pay var |

PROJECT.md tahmini $1.20 idi; fark `summarize_oversample: 1.5`'ten geliyor.
Oversample kapatılırsa ~$1.05'e iner ama gamedev/design bölümleri zayıflar.

**Faz 5'e geçilebilir** — ama önce Anthropic bakiyesi yüklenmeli.
