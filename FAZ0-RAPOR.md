# Faz 0 — Kaynak doğrulama raporu (2026-08-30)

Tüm spike'lar `scripts/spike_*.py` altında, gerçekten çalıştırıldı. Mock yok.

## Anahtarsız kaynaklar — 6/6 çalışıyor

| Kaynak | Durum | Bulgu |
|---|---|---|
| HN Algolia "Show HN" | ✅ | son 24s / min 10 puan → 6 kayıt. Alanlar: `objectID, title, url, points, num_comments, author, created_at` |
| HN Algolia "Launch HN" | ⚠️ | son 24s min 10 puan → **0**. 7 günde 18, 30 günde 50 kayıt var ama puanları düşük. → `min_points` bu sorgu için 0 olmalı, yoksa hiç gelmez |
| GitHub Trending | ✅ | 19 repo, 17'si `min_stars_today: 50` eşiğini geçiyor. `stars_today`, `lang`, `desc` parse ediliyor. Toplam yıldız sayısı DOM'dan çıkmıyor — gerek yok, skor `stars_today` |
| itch.io | ✅ | `https://itch.io/games/newest.xml` → 36 kayıt. Alanlar: `title, link, pubDate, description, imageurl, price, platforms, plainTitle` (PROJECT.md'deki feed URL'i belirsizdi, doğrusu bu) |
| Steam | ✅ | İki yol da çalışıyor: store arama JSON (25 sonuç + appid) ve `feeds/newreleases.xml` (30 kayıt). **RSS tercih edilecek** — daha stabil |
| Webrazzi RSS | ✅ | 20 kayıt, `content:encoded` + `category` dahil |
| Sidebar.io RSS | ✅ | 20 kayıt (`ctype: text/html` dönüyor ama gövde geçerli RSS) |

## Bluesky — kısmen değişti, çözüldü

- ✅ `app.bsky.feed.getAuthorFeed` (hesap timeline'ı) anahtarsız çalışıyor.
  `likeCount, repostCount, quoteCount, record.text, record.createdAt` mevcut.
- ❌ `app.bsky.feed.searchPosts` artık **403 Forbidden** — anahtarsız erişime kapanmış.
  PROJECT.md'deki `feeds: [gamedev, screenshotsaturday, design]` bu haliyle çalışmaz.
- ✅ **Çözüm:** feed generator URI'leri + `app.bsky.feed.getFeed` — anahtarsız, test edildi, çalışıyor.
  Doğrulanmış URI'ler:
  - Bluesky GameDev: `at://did:plc:3z7fz2uzhy5vt627pasakzxh/app.bsky.feed.generator/aaaojmdjtuco4`
  - Gamedev: New: `at://did:plc:brwvwcp2x6oj3gq7odlfq5qf/app.bsky.feed.generator/aaaji3ow5z6gs`
  - Screenshot Saturday: `at://did:plc:4jrld6fwpnwqehtce56qshzv/app.bsky.feed.generator/screenshot-sat`
  - Bluesky IndieDev: `at://did:plc:3z7fz2uzhy5vt627pasakzxh/app.bsky.feed.generator/aaaojh6h73gwq`
  - Graphic Design: `at://did:plc:fyal4ypom4hpb35m5wrtkg5l/app.bsky.feed.generator/aaacramas6xd4`

## Kimlik bilgisi bekleyenler — test edilemedi

| Kaynak | Gereken | Spike hazır |
|---|---|---|
| Product Hunt | `PRODUCTHUNT_TOKEN` | `scripts/spike_producthunt.py` |
| Reddit | `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` | `scripts/spike_reddit.py` |
| TwitterAPI.io | `TWITTERAPI_KEY` | `scripts/spike_twitter.py` + `scripts/validate_accounts.py` |

**config.yaml'daki 47 Twitter handle'ı hâlâ doğrulanmadı** — anahtar gelmeden çalıştırılamaz.

## Ortam sorunu (çözüldü)

python.org Python 3.14 kurulumu macOS kök sertifikalarını kurmamıştı; her HTTPS isteği
`CERTIFICATE_VERIFY_FAILED` veriyordu. `certifi` kullanıcı alanına kuruldu, spike'lar onu
kullanıyor. Proje `uv` ile kendi venv'inde çalışacağı için kalıcı sorun değil.

**`uv` kurulu değil** — Faz 1 öncesi gerekli.

---

## Ek ölçüm — Twitter alternatifleri (kullanıcı sorusu üzerine)

**1. X syndication ucu (anahtarsız):** `syndication.twitter.com/srv/timeline-profile/...`
İki ayrı denemede de **429 Too Many Requests**. Günlük cron için güvenilmez → elendi.

**2. Resmi RSS/changelog feed'leri:** 31 aday denendi, **23'ü canlı**. Ölüler:
Anthropic, a16z, Figma, Tailwind, rauchg (RSS'leri yok), TIGSource (403), IndieHackers (boş feed).
Bu markaların içeriği zaten HN + Techmeme üzerinden geliyor.

**3. Bluesky karşılıkları:** 28 hesap tarandı, **sadece 10'u son 30 günde aktif**.

- Aktif: github.com, ramiismail.com, chrismessina.me, webrazzi.com, itch.io,
  simonwillison.net, unity.com, godotengine.org, vercel.com, figma.com (sınırda, 30 günde 1 post)
- Terk edilmiş: levelsio (638 gün), IndieHackers (623), yongfook (643), dannypostma (570),
  csallen (530), rrhoover (515), arvidkahl (305), swyx (166), supabase (143), rauchg (132),
  shadcn / anthropic.com / realgarrytan (hiç post yok)

**Sonuç:** PROJECT.md'nin "topluluklar Bluesky'a taşındı" varsayımı gamedev + design için
doğru, indie hacker / build-in-public segmenti için yanlış — onlar X'te kaldı.

**Karar:** Twitter 53 hesabın tamamıyla açık kalıyor (kullanıcı kararı).
`validate_accounts.py` anahtar gelince ölüleri ayıklayacak.

## Ek ölçüm — Reddit anonim erişim

PROJECT.md'nin uyarısı doğrulandı, OAuth şart:

| Uç | Sonuç |
|---|---|
| `/r/<sub>/new.json` | **403** (4/4 subreddit) |
| `/r/<sub>/new/.rss` | İlk 2 istek OK, sonrası **429**; ayrıca **upvote sayısı yok** → `min_upvotes: 25` filtresi kurulamaz |

## config.yaml durumu

Yazıldı, ölçümlerle uyumlu: 25 RSS feed, 5 Bluesky feed, 10 Bluesky hesabı, 53 Twitter hesabı.
Her satırda hangi ölçümden geldiği yorum olarak duruyor.

## Faz 0'ı kapatmak için kalan

- [ ] `PRODUCTHUNT_TOKEN` → `spike_producthunt.py`
- [ ] `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` → `spike_reddit.py`
- [ ] `TWITTERAPI_KEY` → `spike_twitter.py` + `validate_accounts.py` (53 handle)
- [ ] `uv` kurulumu (Faz 1 için)

---

## Reddit — kapatıldı (2026-08-30)

Reddit'in **Responsible Builder Policy**'si okundu
(support.reddithelp.com/hc/en-us/articles/42728983564564). İki engel:

1. **"Approval is required"** — API'ye erişmeden önce açık onay şart. Bu yüzden
   `prefs/apps` üzerinden "create app" sessizce başarısız oluyor. Uygulamaların ayrıca
   kayıt olup developer profili oluşturması gerekiyor.
2. **"You must not sell, license, share, or otherwise commercialize Reddit data
   without express written approval"** — madde ticari olmayan kullanımı da kapsıyor.
   Bu proje çıktıyı public GitHub Pages'te yayınlıyor ve `digest.db`'yi public repoya
   commit ediyor; bu doğrudan "share" kapsamına giriyor.

AI maddesi ("train ML or AI models") bizi kapsamıyor — yaptığımız eğitim değil çıkarım.
Engel paylaşım maddesi.

Diğer 8 kaynakta benzer kısıt yok (public API veya RSS — yayınlanmak için tasarlanmış).

**Karar:** `enabled: false`. Kayıp düşük — r/SideProject ≈ Show HN + Product Hunt,
r/gamedev + r/IndieDev ≈ 5 Bluesky gamedev feed'i. `sources/reddit.py` yine yazılacak,
onay alınırsa tek satırla açılır.

`REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` artık gerekli değil.

---

## Product Hunt — DOĞRULANDI (2026-08-30)

Developer Token ile GraphQL v2 çalışıyor.

- **Kritik bulgu:** `postedAfter` filtresi olmadan sorgu **eski ürünleri** döndürüyor
  (4–19 Ağustos). `posts(order: VOTES, postedAfter: $after)` ile bugünün 20 ürünü geliyor.
  `sources/producthunt.py` bu filtreyi kullanacak, `lookback_hours: 26` ile besleyeceğiz.
- Alanlar: `id, name, tagline, url, website, votesCount, commentsCount, createdAt, topics`
- `topics` (ör. "Developer Tools", "Design Tools", "Artificial Intelligence")
  kategori eşlemesi için kullanılabilir — LLM'e sormadan `dev`/`design`/`apps` ayrımı yapılır.
- Oran limiti: `x-rate-limit-limit: 6250` / 15 dk. Günde 1 istek atacağız, sorun yok.

**Kaynak durumu: 7/8 doğrulandı.** Kalan tek doğrulanmamış kaynak Twitter (anahtar bekliyor).

---

## Twitter — DOĞRULANDI (2026-08-30)

`TWITTERAPI_KEY` ile `spike_twitter.py` çalıştı: `/twitter/user/last_tweets` çağrısı
20 tweet döndürüyor, `id, createdAt, likeCount, retweetCount, quoteCount, url, text,
author, entities, isReply, lang` alanları mevcut. **Arama kullanılmadı.**

`validate_accounts.py` 53 handle'ı taradı (handle başına **tek** istek — yanıt zaten
`author` bilgisini taşıdığı için ayrı profil çağrısı yapılmıyor, maliyet yarıya indi).

**Sonuç: 45 OK / 8 SESSİZ / 0 ÖLÜ.**

Handle'ı değişmiş olup kurtarılanlar (3):

| config'deki | gerçek | takipçi | son tweet |
|---|---|---|---|
| `marc_louvion` | **`marclou`** | 378.814 | bugün |
| `dannypostmaa` | **`dannypostma`** | 181.687 | dün |
| `t3dotgg` | **`theo`** | 379.886 | bugün |

Yorum satırına alınanlar (5):

| handle | sebep |
|---|---|
| `chrismessina` | tweet yok — Bluesky `@chrismessina.me` aktif, oradan geliyor |
| `tha_rami` | tweet yok — Bluesky `@ramiismail.com` aktif, oradan geliyor |
| `tigsource` | son tweet 2015, fiilen kapalı |
| `csallen` | 132 gün sessiz |
| `IndieHackers` | 66 gün sessiz |

Sınırda olup **tutulanlar:** `steveschoger` (10g, 30 günde 1 tweet),
`sinaafra` (30 günde 1), `nutlope` (9g). Faz 2'de hacim düşükse tekrar bakılır.

### Maliyet bulgusu — PROJECT.md tahmini tutmuyor

`last_tweets` **sayfa boyutu 20'de sabit**. `count`, `limit`, `pageSize` parametrelerinin
üçü de denendi, hepsi yok sayılıyor — hesap başına 20 tweet okumak zorunlu.

| | PROJECT.md §14 | 48 hesapla gerçek |
|---|---|---|
| Aylık okuma | ~6.000 | 28.800 |
| Twitter maliyeti | ~$0.90 | ~$4.32 |
| Toplam aylık | ~$2 | ~$5.50 |

PROJECT.md'nin 6.000 okuma tahmini yaklaşık 10 hesaba karşılık geliyor.

**Karar (kullanıcı):** İçeriği zaten RSS'ten gelen 20 hesap yorum satırına alındı —
TechCrunch, Techmeme, ycombinator, paulg, github, vercel, supabase, huggingface, OpenAI,
GoogleDeepMind, replit, simonw, swyx, godotengine, UnrealEngine, unity, itchio, awwwards,
sidebario, webrazzi. Bunları hem RSS hem tweet olarak çekmek çift maliyet + dedupe yüküydü.

**Sonuç: 28 aktif hesap = 560 okuma/gün ≈ $2.52/ay. Toplam ~$3.7/ay.**
`daily_twitter_reads` 800 → 600 olarak güncellendi.

config.yaml durumu: 53 handle satırı = 28 aktif + 25 kapalı (5 ölü/sessiz + 20 RSS kopyası).
YAML geçerliliği doğrulandı.

---

# FAZ 0 TAMAMLANDI

| Kaynak | Durum | Kayıt |
|---|---|---|
| Hacker News | ✅ | Show HN 6 (Launch HN eşiği 0'a çekildi) |
| GitHub Trending | ✅ | 19 repo, 17'si eşiği geçiyor |
| Product Hunt | ✅ | bugünün 20 ürünü (`postedAfter` şart) |
| itch.io | ✅ | 36 yeni oyun |
| Steam | ✅ | 30 yeni çıkan (RSS) |
| Bluesky | ✅ | 5 feed + 10 aktif hesap (`getFeed`) |
| RSS | ✅ | 25 canlı feed (31 aday denendi) |
| Twitter | ✅ | 28 aktif hesap (53 tarandı, 20'si RSS kopyası olduğu için kapatıldı) |
| Reddit | ⛔ | Responsible Builder Policy — kapatıldı |

**Faz 1'e geçilebilir.** Tek eksik: `uv` kurulumu.
