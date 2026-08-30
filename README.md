# Gündem

Her sabah developer tools, indie oyun, yeni uygulama ve tasarım dünyasından
yeni çıkanları toplayan, Türkçe özetleyen ve tek bir statik sayfa olarak
yayınlayan sistem.

**→ https://kierkegaard-source.github.io/gundem/**

Her gün 08:00'de (TR) GitHub Actions kendi kendine çalışır. Sekiz kaynaktan
~450 kayıt toplanır, tekilleştirilir, skorlanır ve en iyi 60 madde
`claude-haiku-4-5` ile Türkçe özetlenip yayınlanır.

## Kaynaklar

Hacker News · GitHub Trending · Product Hunt · itch.io · Steam · Bluesky ·
X (28 hesap) · 25 RSS feed

## Çalıştırma

```bash
uv sync
cp .env.example .env      # anahtarları doldur
./scripts/set_env.sh      # ya da bunu kullan, değerler ekranda görünmez

uv run python -m pipeline.collect     # topla, tekilleştir, skorla, özetle
uv run python -m sitegen.build        # docs/ altına sayfaları üret
uv run pytest                         # testler
```

Faydalı bayraklar: `--no-llm` (özetlemeyi atla), `--skip twitter` (maliyetli
kaynağı atla), `--dry-run` (veritabanına yazma).

## Maliyet

| Kalem | Aylık |
|---|---|
| TwitterAPI.io (560 okuma/gün) | ~$2.52 |
| Claude API (Haiku 4.5, 90 özet/gün) | ~$1.45 |
| Diğer kaynaklar, Actions, Pages | $0 |
| **Toplam** | **~$4** |

Günlük LLM harcaması `config.yaml`'daki `budget.daily_llm_usd` tavanını
aşarsa özetleme durur, maddeler ham başlıkla yayınlanır ve sayfaya uyarı
bandı konur.

## Belgeler

`PROJECT.md` tek kaynak referanstır. Her fazın ölçüm sonuçları ve bulunan
hatalar `FAZ0-RAPOR.md` … `FAZ5-RAPOR.md` dosyalarında.
