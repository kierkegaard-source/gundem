# Faz 5 — Site + otomasyon (2026-08-30)

**Canlı:** https://kierkegaard-source.github.io/gundem/

```
uv run python -m pipeline.collect && uv run python -m sitegen.build
→ 493 kayıt → 427 tekil madde → 60 madde → docs/index.html (26 KB)
```

## Yazılan dosyalar

- `sitegen/build.py` — bugünkü sayı, günlük arşiv kopyası, arşiv listesi
- `sitegen/templates/{base,day,archive}.html`
- `sitegen/static/style.css` — 5.7 KB, sayfaya gömülüyor
- `.github/workflows/daily.yml`
- `pipeline/db.py` — `mark_digest`, `digest_items`, `digest_dates`, `last_run`

## PROJECT.md §8 karşılığı

| İstenen | Durum |
|---|---|
| Serif başlık, sans gövde | ✅ sistem font yığını, harici font yok |
| Tek sütun, max 720px, mobilde tam genişlik | ✅ |
| Kategori başlıkları belirgin ayraçlarla | ✅ çift çizgi + aksan rengi + madde sayacı |
| Kart: başlık → why → özet → rozet + saat | ✅ |
| `prefers-color-scheme`, JS gerektirmeden | ✅ hiç JS yok |
| Üstte tarih ve "N madde, M kaynak" | ✅ |
| Altta önceki/sonraki gün navigasyonu | ✅ |
| Toplam sayfa < 100KB | ✅ **26.8 KB** |

Kaynak alınamazsa üstte uyarı bandı çıkıyor (§2.2). Türkçe tarih biçimlendirme
elle yazıldı — `locale` GitHub runner'ında güvenilir değil.

## Bulunan dört hata

### 1. Jinja `sec.items` ifadesini dict metoduna çözümlüyordu

`{{ sec.items|length }}` → `TypeError: object of type 'builtin_function_or_method'
has no len()`. Jinja önce `dict.items` metodunu buluyor. Anahtar `entries` yapıldı.

### 2. autoescape gömülü CSS'i bozuyordu — sessizce

`{{ css }}` içindeki `>` karakteri `&gt;` oluyordu. Sonuç: `.section > h2` gibi
**tüm alt-eleman seçicileri** çalışmıyordu, ama `>` içermeyen kurallar
çalıştığı için sayfa "çalışıyor gibi" görünüyordu — kategori başlıkları
stilsizdi ama fark edilmesi ekran görüntüsü karşılaştırması gerektirdi.
`{{ css|safe }}`.

### 3. `published_hashes` bugünü de hariç tutuyordu

Aynı gün ikinci koşuda sayı **boş** çıkıyordu: tüm maddeler "zaten yayınlandı"
sayılıyordu. Sorgu `digest_date < bugün` oldu.

### 4. `mark_digest` idempotent değildi

Elle tetiklenen ikinci koşudan sonra sayfada 60 yerine **72 madde** çıktı —
iki koşunun maddeleri birikti. Artık o günün işaretleri önce temizleniyor.
İkinci Actions koşusunda doğrulandı: 60 madde.

## Ortam hatası: dizin adı değişince venv kırıldı

`daily-launch` → `gundem` yeniden adlandırmasından sonra `uv run pytest`
`Failed to spawn: pytest` verdi. Sebep: venv script'lerinin shebang'inde eski
mutlak yol gömülü. `rm -rf .venv && uv sync` çözdü. Actions'ta venv her koşuda
sıfırdan kurulduğu için oraya yansımıyordu.

## GitHub Actions

İki ardışık koşu, elle müdahale olmadan, başarılı:

| koşu | sonuç | commit |
|---|---|---|
| 33318535766 | success | `Sayı: 2026-08-30 — 72 madde` (idempotency öncesi) |
| 33319103542 | success | `Sayı: 2026-08-30 — 60 madde` |

8 kaynağın hepsi runner'da çalıştı. Özetleme başarısız oldu (Anthropic
bakiyesi tükenmiş) → sayfaya uyarı bandı kondu, pipeline çökmedi.

Workflow tasarımı: toplama ve üretim adımları `continue-on-error`, commit her
hâlükârda atılıyor, iş en sonda başarısız ediliyor — PROJECT.md §9'daki
"kısmi sonuç varsa yine de commit et" kuralı.

## Kabul kriterleri (PROJECT.md §12)

- [x] `collect && build` tek komutta çalışıyor
- [x] Bir kaynağın ağı kesilince pipeline çökmüyor, sayfada eksik olduğu yazıyor
- [ ] Aynı ürün 3 kaynakta → 1 satır 3 rozet — **kod hazır, testte doğrulandı,
      gerçek veride henüz çakışma çıkmadı**
- [x] Günlük LLM maliyeti `runs` tablosunda kayıtlı ve $0.10'un altında ($0.048)
- [x] Sayfa mobilde tek elle okunabiliyor, yatay kaydırma yok
- [x] Actions üst üste iki koşuda elle müdahale olmadan commit atıyor
- [ ] Arşivden 3 gün öncesine gidilebiliyor — **kod hazır, 3 gün veri birikmesi
      gerekiyor**

## Bilinen kısıt: yerel/Actions dosya çakışması

`docs/` ve `data/digest.db` her gün Actions tarafından yeniden üretiliyor.
Yerelde de üretilirse ikili çakışma çıkıyor (bir kez yaşandı, rebase iptal
edilip dal `origin/main`'e sıfırlandı). `.gitattributes` bunu belgeliyor:
yerelde commit'lemeden önce `git checkout origin/main -- docs data`.
