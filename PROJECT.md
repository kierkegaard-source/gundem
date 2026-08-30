# Daily Launch — Günlük Ürün & Girişim Gazetesi

Bu dosya projenin tek kaynak referansıdır. Claude Code bu dosyayı okuyup adım adım
uygulayacak. Yeni bir oturuma başlarken önce bu dosyayı oku.

> **Durum (2026-08-30):** Beş fazın tamamı bitti; sistem canlı —
> https://kierkegaard-source.github.io/gundem/ · Faz 0-5 tamamlandı. Bu dosya o fazların ölçüm
> sonuçlarına göre güncellendi — değişen her yer `[Faz 0]` / `[Faz 1]` etiketiyle
> işaretli. Ayrıntılı ölçümler: `FAZ0-RAPOR.md`, `FAZ1-RAPOR.md`.

---

## 1. Amaç

Her sabah otomatik olarak çalışan, dört kategoride (developer tools, indie oyun,
yeni uygulama/girişim, tasarım) yeni çıkanları toplayan, Türkçe özetleyen ve tek
bir statik HTML sayfası olarak yayınlayan bir sistem. Kullanıcı bunu her gün
gazete okur gibi okuyacak. Arşiv birikecek.

**Başarı ölçütü:** Sabah sayfayı açtığımda 30–60 madde görüyorum, her biri iki
cümlelik Türkçe özetle, kategorilere ayrılmış, önem sırasına dizilmiş. Hiçbir
maddeyi başka bir yerden takip etmeme gerek kalmıyor.

---

## 2. Temel ilkeler

Bunlar tasarım kararlarını yönlendirir, ihlal etme:

1. **Önce doğrula, sonra yaz.** Hiçbir API'nin çalıştığını varsayma. Her kaynak
   için önce bir spike scripti yaz, gerçekten çalıştır, dönen şemayı gör. Endpoint
   ölmüşse bana söyle — uydurma, mock'lama.
2. **Kısmi başarı tam başarısızlıktan iyidir.** Bir kaynak patlarsa pipeline
   durmaz. O kaynak atlanır, sayfada "X kaynağı bugün alınamadı" notu görünür.
3. **Maliyet tavanı serttir.** Günlük LLM harcaması $0.20'yi aşarsa özetleme
   durur, ham başlıklarla devam edilir. Bu bir öneri değil, kodda olacak.
4. **Sinyal > hacim.** 200 vasat madde yerine 40 iyi madde. Skorlama ve eşik
   agresif olsun.
5. **Ücretsiz kaynak tercih edilir.** Bir veri hem ücretsiz hem ücretli kaynaktan
   geliyorsa ücretsiz olanı kullan.

---

## 3. Teknoloji

- Python 3.11+, bağımlılık yönetimi `uv`
- SQLite (dedupe geçmişi + arşiv)
- Jinja2 (HTML render)
- `httpx` (async, tüm kaynaklar paralel çekilsin)
- Claude API — model `claude-haiku-4-5` ($1/M girdi, $5/M çıktı)
- GitHub Actions (cron) + GitHub Pages (hosting)
- Repo **public** olacak (Actions ve Pages tamamen ücretsiz olsun diye)

---

## 4. Dizin yapısı

```
daily-launch/
├── PROJECT.md              # bu dosya
├── config.yaml             # hesap listeleri, ağırlıklar, eşikler
├── pyproject.toml
├── .env.example
├── FAZ0-RAPOR.md           # kaynak doğrulama ölçümleri
├── FAZ1-RAPOR.md           # iskelet testleri
├── sources/
│   ├── base.py             # Item dataclass + ortak Source arayüzü
│   ├── hackernews.py
│   ├── producthunt.py
│   ├── github_trending.py
│   ├── itchio.py
│   ├── steam.py
│   ├── reddit.py           # [Faz 0] yazılacak ama config'de kapalı
│   ├── bluesky.py
│   ├── twitter.py
│   └── rss.py
├── pipeline/
│   ├── config.py           # [Faz 1] config.yaml + .env yükleyici
│   ├── db.py               # [Faz 1] SQLite şeması ve yazma
│   ├── collect.py          # tüm kaynakları paralel çalıştır
│   ├── dedupe.py
│   ├── score.py
│   ├── summarize.py        # Claude API
│   └── budget.py           # maliyet takibi + tavan
├── sitegen/                # [Faz 1] `site` stdlib modülüyle çakışıyor, yeniden adlandırıldı
│   ├── build.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── day.html
│   │   └── archive.html
│   └── static/style.css
├── docs/                   # GitHub Pages kökü — çıktı buraya
│   ├── index.html          # bugünkü sayı
│   ├── arsiv.html
│   └── 2026-08-30.html     # günlük arşiv
├── data/digest.db
├── scripts/
│   └── validate_accounts.py
└── .github/workflows/daily.yml
```

---

## 5. Veri modeli

```python
@dataclass
class Item:
    title: str
    url: str                  # kanonik URL (utm_* parametreleri temizlenmiş)
    source: str               # "hackernews", "twitter", ...
    category: str             # dev | gamedev | apps | design | startup | tr
    raw_score: float          # kaynağın kendi metriği (puan, upvote, like)
    published_at: datetime     # UTC
    raw_text: str             # başlık + açıklama, özetleme girdisi (max 1500 char)
    author: str | None = None
    extra: dict = field(default_factory=dict)
```

**SQLite şeması:**

```sql
CREATE TABLE items (
  url_hash    TEXT PRIMARY KEY,   -- sha256(kanonik url)
  title       TEXT NOT NULL,
  url         TEXT NOT NULL,
  category    TEXT NOT NULL,
  sources     TEXT NOT NULL,      -- JSON list, birden fazla kaynakta çıkabilir
  score       REAL NOT NULL,
  summary_tr  TEXT,
  why_tr      TEXT,
  published_at TEXT NOT NULL,
  first_seen  TEXT NOT NULL,
  digest_date TEXT               -- hangi sayıda yayınlandı, NULL = henüz değil
);
CREATE INDEX idx_digest_date ON items(digest_date);

CREATE TABLE runs (
  run_at        TEXT PRIMARY KEY,
  items_raw     INTEGER,
  items_kept    INTEGER,
  failed_sources TEXT,            -- JSON list
  llm_cost_usd  REAL,
  api_cost_usd  REAL
);
```

Dedupe için `url_hash` yeterli değil — aynı ürün farklı URL'lerle çıkabilir
(Product Hunt linki vs. kendi sitesi). İkinci kademe: başlık normalize edilip
(küçük harf, noktalama atılmış) `rapidfuzz` ile %85 üzeri benzerlik varsa aynı
kayıt sayılır, `sources` listesi birleştirilir.

---

## 6. Kaynaklar

Her satırdaki "auth" sütunu ne gerektiğini söyler. Faz 0'da hepsini doğrula.

| Kaynak | Ne çeker | Auth | Kategori |
|---|---|---|---|
| Hacker News (Algolia) | "Show HN" min 10 puan, "Launch HN" min 0 puan `[Faz 0]` | yok | dev |
| GitHub Trending | github.com/trending scrape, daily | yok | dev |
| Product Hunt | GraphQL v2, `postedAfter` filtresi ŞART `[Faz 0]` | token | apps |
| itch.io | `itch.io/games/newest.xml` `[Faz 0]` | yok | gamedev |
| Steam | `store.steampowered.com/feeds/newreleases.xml` `[Faz 0]` | yok | gamedev |
| ~~Reddit~~ | **KAPALI** `[Faz 0]` — aşağıdaki nota bak | — | — |
| Bluesky | feed generator URI + `getFeed`, ayrıca hesap timeline'ları `[Faz 0]` | yok | gamedev, design |
| RSS (25 feed) | tasarım, dev, startup, gamedev, tr `[Faz 0]` | yok | hepsi |
| TwitterAPI.io | config'deki 28 hesap `[Faz 0]` | API key | hepsi |

**Notlar:**

- **Bluesky.** `[Faz 0 DÜZELTMESİ]` `app.bsky.feed.searchPosts` anahtarsız erişime
  **kapatılmış (403)**. Yerine feed generator URI'leri + `app.bsky.feed.getFeed`
  kullanılıyor — anahtarsız, doğrulandı. Hesap timeline'ları (`getAuthorFeed`) da çalışıyor.
  Varsayım kısmen doğru çıktı: gamedev ve tasarım toplulukları gerçekten Bluesky'da,
  ama indie hacker / build-in-public kalabalığı X'te kaldı (28 aday hesap tarandı, 18'i ölü).
- **Reddit KAPALI.** `[Faz 0]` İki engel: (1) Responsible Builder Policy API erişimi için
  açık onay şart kılıyor, app oluşturma bu yüzden başarısız oluyor; (2) aynı politika
  Reddit verisinin yazılı onay olmadan **paylaşılmasını** yasaklıyor — bu proje çıktıyı
  public GitHub Pages'te yayınlıyor ve `digest.db`'yi public repoya commit ediyor.
  Anonim erişim de ölçüldü: `.json` 403, `.rss` ikinci istekte 429 ve upvote sayısı yok.
  Kayıp düşük: r/SideProject ≈ Show HN + Product Hunt, r/gamedev ≈ Bluesky gamedev feed'leri.
- **Twitter en pahalı kaynak.** Anahtar kelime araması YAPMA — arama binlerce
  alakasız tweet döndürür ve hepsi okuma olarak faturalanır. Sadece config'deki
  hesap listesinin timeline'ı çekilecek.
  `[Faz 0]` `last_tweets` **sayfa boyutu 20'de sabit** — `count`/`limit`/`pageSize`
  parametrelerinin üçü de yok sayılıyor. Hesap başına 20 tweet okumak zorunlu.

---

## 7. Pipeline

```
collect → dedupe → score → filter → summarize → render → publish
```

### 7.1 Skorlama

```
score = source_weight × log1p(raw_score_normalized) × recency_factor
```

- `source_weight`: config.yaml'dan (hesap/kaynak bazlı, 0.3–1.0)
- `raw_score_normalized`: kaynak içinde 0–1'e normalize (HN puanı ile Twitter
  beğenisi doğrudan kıyaslanamaz)
- `recency_factor`: 0–6 saat → 1.0, 6–12 → 0.9, 12–24 → 0.8, 24s+ → 0.5
- Birden fazla kaynakta çıkan madde `× 1.4` bonus alır — bu en güçlü sinyal

**Filtre:** kategori başına en yüksek skorlu N madde (config'de `max_per_category`,
varsayılan 15), toplam tavan 60.

### 7.2 Özetleme

Tek istekte batch halinde gönder, item başına ayrı çağrı YAPMA.

- Model: `claude-haiku-4-5`
- 20'şerlik gruplar halinde gönder (tek istekte 60 item çıktı limitini zorlar)
- Sistem promptu sabit → **prompt caching kullan**, girdi maliyeti %90 düşer
- Çıktı sadece JSON, başka hiçbir şey yok

**Sistem promptu (özet):**

> Sen teknoloji ve girişim dünyasını takip eden bir editörsün. Sana JSON listesi
> halinde yeni çıkan ürün/proje/haber verilecek. Her biri için Türkçe çıktı üret.
> Yalnızca JSON dizisi döndür — markdown bloğu, açıklama, önsöz yok.
>
> Her madde için:
> - `id`: girdideki id, aynen
> - `summary`: 2 cümle. Ne olduğunu ve kime yaradığını anlat. Pazarlama dili
>   kullanma, abartma. "Devrim niteliğinde" gibi ifadeler yasak.
> - `why`: tek satır, en fazla 12 kelime. Bunu neden okumaya değer?
> - `category`: dev | gamedev | apps | design | startup
> - `signal`: 1–5 arası. 5 = gerçekten yeni ve önemli, 1 = gürültü.
>
> Girdi İngilizceyse özet yine Türkçe olacak. Teknik terimleri zorlama çevirme
> (framework, endpoint, shader gibi kelimeler olduğu gibi kalsın).

`signal < 2` gelen maddeler sayfaya alınmaz.

### 7.3 Bütçe koruması (`pipeline/budget.py`)

- Her Claude API çağrısından önce tahmini token maliyetini hesapla
- Çalışma başına kümülatif maliyeti izle
- `config.daily_llm_budget_usd` (varsayılan 0.20) aşılırsa: özetlemeyi durdur,
  kalan maddeleri ham başlıkla sayfaya koy, sayfaya uyarı bandı ekle
- Her çalıştırmanın gerçek maliyetini `runs` tablosuna yaz
- Twitter tarafı için de ayrı sayaç: çekilen tweet sayısı × $0.00015

---

## 8. Site çıktısı

- `docs/index.html` → en son sayı
- `docs/YYYY-MM-DD.html` → o günün arşiv kopyası
- `docs/arsiv.html` → tarih listesi

**Tasarım yönü:** Gazete hissi. Okunabilirlik her şeyin önünde.

- Serif başlık fontu, sans-serif gövde
- Tek sütun, max 720px genişlik, mobilde tam genişlik
- Kategori başlıkları belirgin ayraçlarla
- Her madde bir kart: başlık (link) → `why` satırı → 2 cümlelik özet → kaynak
  rozetleri + saat
- `prefers-color-scheme` ile koyu/açık tema, JS gerektirmeden
- Üstte tarih ve "N madde, M kaynak" satırı
- Altta önceki/sonraki gün navigasyonu
- Toplam sayfa < 100KB, harici font yükleme yok (system font stack)

---

## 9. GitHub Actions

`.github/workflows/daily.yml`

- Cron: `0 5 * * *` (UTC 05:00 = TR 08:00)
- `workflow_dispatch` da olsun (elle tetikleme)
- Adımlar: checkout → uv kur → bağımlılıklar → `python -m pipeline.collect` →
  `python -m sitegen.build` `[Faz 1]` → `docs/` ve `data/digest.db` commit et → push
- Timeout 15 dakika
- Hata olursa: iş başarısız olsun ama **kısmi sonuç varsa yine de commit et**
- Actions izinleri: `contents: write`

**GitHub Secrets:**

```
ANTHROPIC_API_KEY
PRODUCTHUNT_TOKEN
TWITTERAPI_KEY
```

`[Faz 0]` `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` kaldırıldı — kaynak kapalı.
Bluesky, HN, GitHub Trending, itch.io, Steam ve RSS'ler anahtar gerektirmez.

---

## 10. config.yaml

```yaml
budget:
  daily_llm_usd: 0.20
  daily_twitter_reads: 800

filters:
  max_per_category: 15
  max_total: 60
  min_signal: 2
  lookback_hours: 26        # cron kaymalarına tolerans

scoring:
  multi_source_bonus: 1.4
  recency:
    "0-6": 1.0
    "6-12": 0.9
    "12-24": 0.8
    "24+": 0.5

sources:
  hackernews:
    enabled: true
    weight: 0.9
    queries: ["Show HN", "Launch HN"]
    min_points: 10

  github_trending:
    enabled: true
    weight: 0.7
    min_stars_today: 50

  producthunt:
    enabled: true
    weight: 1.0

  itchio:
    enabled: true
    weight: 0.7

  steam:
    enabled: true
    weight: 0.6

  reddit:
    enabled: true
    weight: 0.6
    subreddits: [gamedev, IndieDev, SideProject, webdev]
    min_upvotes: 25

  bluesky:
    enabled: true
    weight: 0.8
    handles:
      - godotengine.org
      - itch.io
    feeds: [gamedev, screenshotsaturday, design]

  rss:
    enabled: true
    feeds:
      - { url: "https://webrazzi.com/feed", weight: 1.0, cat: tr }
      - { url: "https://sidebar.io/feed.xml", weight: 0.8, cat: design }

  twitter:
    enabled: true
    provider: twitterapi.io
    accounts:
      # ── Indie hacker / build in public ──
      - { handle: levelsio,        weight: 1.0, cat: apps }
      - { handle: marc_louvion,    weight: 0.9, cat: apps }
      - { handle: tdinh_me,        weight: 0.9, cat: apps }
      - { handle: dannypostmaa,    weight: 0.8, cat: apps }
      - { handle: yongfook,        weight: 0.8, cat: apps }
      - { handle: arvidkahl,       weight: 0.9, cat: apps }
      - { handle: tibo_maker,      weight: 0.8, cat: apps }
      - { handle: dagorenouf,      weight: 0.7, cat: apps }
      - { handle: thisiskp_,       weight: 0.7, cat: apps }
      - { handle: agazdecki,       weight: 0.7, cat: apps }
      - { handle: csallen,         weight: 0.8, cat: apps }
      - { handle: IndieHackers,    weight: 0.8, cat: apps }

      # ── Launch platformları ──
      - { handle: ProductHunt,     weight: 1.0, cat: apps }
      - { handle: rrhoover,        weight: 0.8, cat: apps }
      - { handle: chrismessina,    weight: 0.7, cat: apps }
      - { handle: ycombinator,     weight: 1.0, cat: startup }

      # ── Startup / VC / haber ──
      - { handle: TechCrunch,      weight: 0.8, cat: startup }
      - { handle: Techmeme,        weight: 0.9, cat: startup }
      - { handle: garrytan,        weight: 0.8, cat: startup }
      - { handle: paulg,           weight: 0.7, cat: startup }
      - { handle: a16z,            weight: 0.7, cat: startup }
      - { handle: sama,            weight: 0.7, cat: startup }

      # ── Dev tools / AI ──
      - { handle: vercel,          weight: 0.8, cat: dev }
      - { handle: supabase,        weight: 0.8, cat: dev }
      - { handle: github,          weight: 0.7, cat: dev }
      - { handle: huggingface,     weight: 0.8, cat: dev }
      - { handle: AnthropicAI,     weight: 0.9, cat: dev }
      - { handle: OpenAI,          weight: 0.9, cat: dev }
      - { handle: GoogleDeepMind,  weight: 0.8, cat: dev }
      - { handle: cursor_ai,       weight: 0.8, cat: dev }
      - { handle: replit,          weight: 0.7, cat: dev }
      - { handle: railway,         weight: 0.6, cat: dev }
      - { handle: rauchg,          weight: 0.8, cat: dev }
      - { handle: shadcn,          weight: 0.8, cat: dev }
      - { handle: simonw,          weight: 0.9, cat: dev }
      - { handle: swyx,            weight: 0.8, cat: dev }
      - { handle: t3dotgg,         weight: 0.7, cat: dev }
      - { handle: nutlope,         weight: 0.7, cat: dev }

      # ── Oyun ──
      - { handle: godotengine,     weight: 0.9, cat: gamedev }
      - { handle: UnrealEngine,    weight: 0.7, cat: gamedev }
      - { handle: unity,           weight: 0.6, cat: gamedev }
      - { handle: itchio,          weight: 0.9, cat: gamedev }
      - { handle: tigsource,       weight: 0.7, cat: gamedev }
      - { handle: tha_rami,        weight: 0.7, cat: gamedev }

      # ── Tasarım ──
      - { handle: figma,           weight: 0.8, cat: design }
      - { handle: sidebario,       weight: 0.9, cat: design }
      - { handle: awwwards,        weight: 0.7, cat: design }
      - { handle: steveschoger,    weight: 0.7, cat: design }
      - { handle: adamwathan,      weight: 0.7, cat: design }

      # ── Türkiye ──
      - { handle: webrazzi,        weight: 1.0, cat: tr }
      - { handle: tansuyegen,      weight: 0.6, cat: tr }
      - { handle: alphanmanas,     weight: 0.6, cat: tr }
      - { handle: sinaafra,        weight: 0.5, cat: tr }
```

**Uyarı:** Yukarıdaki handle'lar doğrulanmadı. Faz 0'da `validate_accounts.py`
çalıştırılacak, ölü/değişmiş olanlar yorum satırına alınacak.

---

## 11. Yapım sırası

Sırayla ilerle. Her fazın sonunda dur ve sonucu göster.

### Faz 0 — Doğrulama ✅ TAMAMLANDI (2026-08-30)

1. `scripts/spike_<kaynak>.py` — her kaynak için tek dosyalık deneme scripti yaz
   ve **gerçekten çalıştır**. Dönen JSON'un şemasını kaydet.
2. Çalışmayan kaynakları raporla. Alternatif öner ya da o kaynağı kapat.
3. `scripts/validate_accounts.py` — config'deki tüm Twitter handle'larını kontrol
   et. Çıktı tablosu: `handle | durum (OK/ÖLÜ/DEĞİŞMİŞ/SESSİZ) | takipçi | son tweet`.
   "Sessiz" = son 30 günde tweet yok.
4. Bulguları özetle, config.yaml'ı güncelle.

**Bu faz bitmeden Faz 1'e geçme.**

### Faz 1 — İskelet ✅ TAMAMLANDI (2026-08-30)
- `sources/base.py`, SQLite şeması, config yükleyici, `budget.py`
- İki kaynak: Hacker News + GitHub Trending
- `collect.py` çalışsın, veritabanına yazsın, terminale tablo bassın
- LLM yok, site yok — sadece veri akışı doğru mu?

### Faz 2 — Kalan kaynaklar ✅ TAMAMLANDI (2026-08-30)
- Product Hunt, Bluesky, itch.io, Steam, RSS, Twitter (Reddit kapalı `[Faz 0]`)
- Hepsi paralel (asyncio), her biri kendi try/except'inde
- `failed_sources` listesi doğru dolsun

### Faz 3 — Dedupe + skorlama ✅ TAMAMLANDI (2026-08-30)
- URL kanonikleştirme, hash dedupe, fuzzy başlık dedupe
- Skorlama ve filtreleme
- Kontrol: aynı ürünün 3 kaynaktan gelen kaydı tek satır mı oldu?

### Faz 4 — Özetleme ✅ TAMAMLANDI (2026-08-30)
- Batch halinde Claude API, prompt caching açık
- JSON parse + hata toleransı (bozuk JSON gelirse o batch'i atla, ham başlık kullan)
- Bütçe tavanı test et: tavanı $0.001'e çekip gerçekten durduğunu doğrula

### Faz 5 — Site + otomasyon ✅ TAMAMLANDI (2026-08-30)
- Jinja2 şablonlar, CSS, `build.py`
- GitHub Actions workflow
- Elle bir kez tetikle, Pages'te sayfayı gör

---

## 12. Kabul kriterleri

Sistem şunları sağlıyorsa bitmiştir:

- [ ] `uv run python -m pipeline.collect && uv run python -m sitegen.build` tek komutta çalışıyor `[Faz 1]`
- [x] Bir kaynağın ağını kesince (örn. yanlış API key) pipeline çökmüyor `[Faz 1: test edildi]`
      — sayfada gösterme kısmı Faz 5'te
- [ ] Aynı ürün Product Hunt + HN + Twitter'da varsa sayfada bir kez görünüyor,
      üç kaynak rozeti taşıyor
- [ ] Günlük LLM maliyeti `runs` tablosunda kayıtlı ve $0.10'un altında
- [ ] Sayfa mobilde tek elle okunabiliyor, yatay kaydırma yok
- [ ] Actions iki gün üst üste elle müdahale olmadan çalışıp commit atıyor
- [ ] Arşiv sayfasından 3 gün öncesine gidilebiliyor

---

## 13. Kapsam dışı (şimdilik yapma)

- Kullanıcı hesabı, giriş, kişiselleştirme
- Tam makale çekip özetleme (girdi token'ı 10 katına çıkar)
- Bildirim, e-posta, Telegram — sadece web sayfası
- Arama, etiket filtresi, RSS çıktısı
- Veritabanı olarak SQLite dışında bir şey

Bunlar sonra konuşulur. Önce her sabah düzgün çalışan bir sayfa.

---

## 14. Maliyet beklentisi

| Kalem | İlk tahmin | `[Faz 0/1]` ölçülen |
|---|---|---|
| Ücretsiz kaynaklar (HN, GitHub, Bluesky, itch, Steam, 25 RSS, PH) | $0 | $0 |
| TwitterAPI.io | ~$0.90 (~6.000 okuma) | **~$2.52** (16.800 okuma) |
| Claude API (Haiku 4.5, ~60 özet/gün, caching ile) | ~$1.20 | **~$1.05** |
| GitHub Actions + Pages (public repo) | $0 | $0 |
| **Toplam** | **~$2** | **~$3.6** |

`[Faz 0]` İlk tahmindeki 6.000 okuma yaklaşık 10 Twitter hesabına karşılık geliyor;
config'de 53 hesap vardı. Sayfa boyutu 20'de sabit olduğu için okuma sayısı hesap
sayısıyla doğrusal artıyor. İçeriği zaten RSS'ten gelen 20 hesap kapatıldı → 28 kaldı.

`[Faz 1]` Ölçülen LLM maliyeti: 20 item'lik batch $0.0115, prompt caching ile $0.0084.
60 item'lik günlük sayı ≈ $0.035/gün.

Bu rakam aşılıyorsa bir şey yanlış gidiyor demektir — büyük ihtimalle Twitter'da
arama yapılıyor ya da özetlemeye çok fazla metin gidiyor. `runs` tablosuna bak.
