# Faz 1 — İskelet (2026-08-30)

`uv run python -m pipeline.collect` çalışıyor, veritabanına yazıyor, terminale tablo basıyor.
LLM yok, site yok — sadece veri akışı.

## Yazılan dosyalar

| Dosya | İş |
|---|---|
| `sources/base.py` | `Item` dataclass, `canonical_url()`, `url_hash()`, `Source` ABC, `SourceError` |
| `pipeline/config.py` | `config.yaml` + `.env` yükleyici, `enabled_sources()`, `secret()` |
| `pipeline/db.py` | PROJECT.md §5 şeması, `upsert_items()` (sources listesi birleştirir), `record_run()` |
| `pipeline/budget.py` | Haiku 4.5 fiyatları, prompt caching hesabı, LLM + Twitter sayaçları, sert tavan |
| `sources/hackernews.py` | Algolia, sorgu başına ayrı puan eşiği |
| `sources/github_trending.py` | HTML scrape, `article.Box-row` bazlı |
| `pipeline/collect.py` | asyncio paralel toplama, kaynak başına try/except + zaman aşımı |

## PROJECT.md'den sapma — `site/` → `sitegen/`

`site` Python'un **stdlib modülü** ve yorumlayıcı açılışında yükleniyor; yerel bir paket
onu gölgeleyemiyor. Doğrulandı:

```
$ python3 -m site.build
ModuleNotFoundError: __path__ attribute not found on 'site' while trying to find 'site.build'
```

Yani PROJECT.md §12'deki `python -m site.build` kabul kriteri o adla imkânsız.
Paket `sitegen/` olarak adlandırıldı, komut `python -m sitegen.build`.

## Faz 1'de bulunan iki veri hatası (düzeltildi)

1. **Algolia `query` tam metin araması yapıyor.** "Show HN" sorgusu `Ask HN: …`
   başlıklarını da döndürüyordu ve bu kayıtlar "Launch HN" sorgusunun `min_points: 0`
   eşiğinden içeri sızıyordu — tabloda 3 puanlık bir kayıt göründü. Çözüm: başlık öneki
   (`title.startswith(query)`) + puan eşiği kaynak tarafında tekrar uygulanıyor.
   Sonuç: 8 kayıt → 5 gerçek Show HN.
2. **GitHub Trending'de yayın tarihi yok.** `published_at = now` atanıyor; "bugün trend
   olan" bilgisi zaten güncelliği ifade ediyor. Faz 3'teki `recency_factor` için not.

## Testler

| Test | Sonuç |
|---|---|
| URL kanonikleştirme (utm/fbclid/ref temizliği, www, sondaki `/`, parametre sırası) | ✅ 4/4 |
| İzleme parametreli + www'li iki URL aynı `url_hash` | ✅ |
| Tekrar çalıştırma → 0 yeni, 22 güncellendi (mükerrer kayıt yok) | ✅ |
| Kaynak istisna fırlatınca pipeline çökmüyor, kısmi sonuç dönüyor | ✅ |
| Kaynak donunca 45s zaman aşımıyla atlanıyor | ✅ |
| `failed_sources` listesi doğru doluyor ve `runs` tablosuna yazılıyor | ✅ |
| Bütçe tavanı: $0.001 tavanla `can_afford_llm` False dönüyor | ✅ |
| Twitter sayacı: 560 okuma geçiyor, 960 geçmiyor | ✅ |

## Ölçülen maliyet gerçekleri

- 20 item'lik batch: **$0.0115** (caching'siz) → **$0.0084** (sistem promptu cache'li)
- $0.20 günlük tavan ≈ **17 batch = 340 item**. Bizim tavanımız 60 item ≈ **$0.035/gün ≈ $1.05/ay**
- Twitter: 560 okuma/gün = **$0.084/gün = $2.52/ay**

## Bu koşunun çıktısı

- Kaynaklar: 2 hazır (hackernews, github_trending), 6 beklemede (Faz 2)
- 22 kayıt: 17 GitHub Trending + 5 Show HN, hepsi `dev` kategorisi
- Süre: 0.9 saniye
- Başarısız kaynak: yok

**Faz 2'ye geçilebilir.**
