# Faz 2 — Kalan kaynaklar (2026-08-30)

Sekiz kaynağın hepsi tek komutta, paralel, kendi try/except'inde çalışıyor.

```
uv run python -m pipeline.collect
→ 8 kaynak, 451 kayıt, 11.1 saniye, 0 başarısız kaynak
```

| Kaynak | Kayıt | Süre |
|---|---:|---:|
| bluesky | 220 | 1.5s |
| twitter | 87 | 11.0s |
| steam | 49 | 0.7s |
| rss | 28 | 3.0s |
| itchio | 25 | 0.6s |
| producthunt | 20 | 0.6s |
| github_trending | 17 | 1.6s |
| hackernews | 5 | 1.8s |

## Yazılan dosyalar

`sources/_feed.py` (ortak RSS/Atom ayrıştırıcı, stdlib), `rss.py`, `itchio.py`,
`steam.py`, `producthunt.py`, `bluesky.py`, `twitter.py`, `reddit.py` (kapalı).
`collect.py`'a `--only` / `--skip` bayrakları eklendi — maliyetli Twitter'ı
tekrarlı testlerde atlamak için.

## Faz 2'de bulunan üç hata

### 1. Steam RSS'i ölü — kaynak değiştirildi

`store.steampowered.com/feeds/newreleases.xml` **güncellenmiyor**. En yeni kaydı
2026-07-11 (49 gün önce), listede 2023 tarihli oyunlar var. Faz 0'da bu feed
"30 kayıt, HTTP 200" diye ✅ işaretlenmişti — sadece kayıt **sayısına** bakılmış,
**tarihlerine** bakılmamıştı. Ders: bir feed'in canlı olması güncel olduğu anlamına gelmiyor.

Yerine store arama endpoint'i (`sort_by=Released_DESC`) kullanılıyor. Çıkış tarihi
gün hassasiyetinde geldiği için pencere gün bazında değerlendiriliyor. PROJECT.md §6'nın
"indie tag öncelikli" isteği `data-ds-tagids` içindeki 492 numaralı etiketle karşılanıyor.
Sonuç: 49 kayıt, 6'sı indie.

### 2. UnrealEngine Atom feed'i bozuk — tolerans eklendi

`unrealengine.com/en-US/rss` gövdenin sonuna artık veri ekliyor:
`junk after document element: line 1, column 13061`. Ayrıştırıcıya kurtarma adımı
eklendi — kapanış etiketinden (`</feed>`, `</rss>`, `</RDF>`) sonrası atılıp tekrar
deneniyor. 10 kayıt kurtarıldı.

### 3. Tweet metinlerinde HTML entity çözülmüyordu

`Claude Code CLI &gt; Codex CLI` şeklinde geliyordu. `html.unescape` eklendi.

## Mükerrer kayıt analizi

- **Kaynak içi:** 63 mükerrer, **hepsi Bluesky'da** — aynı gönderi birden fazla feed
  generator'da çıkıyor ya da farklı gönderiler aynı dış linke işaret ediyor.
  `upsert_items` bunları tek satıra indiriyor.
- **Kaynaklar arası:** bugün 0. Bulanık başlık eşleşmesi (≥85) de 0.
- PROJECT.md §12'deki "aynı ürün 3 kaynakta → 1 satır, 3 rozet" kriteri bugünkü veriyle
  **doğrulanamıyor** (öyle bir çakışma yok). Faz 3'te sentetik veriyle test edilecek.

## Kategori dağılımı ve Faz 3 filtresi

| kategori | ham | filtre sonrası |
|---|---:|---:|
| gamedev | 230 | 15 |
| apps | 55 | 15 |
| dev | 49 | 15 |
| startup | 25 | 15 |
| tr | 20 | 15 |
| design | 9 | 9 |
| **toplam** | **388** | **60** (tavan) |

Bluesky tek başına gamedev'in %65'ini üretiyor. `min_likes_feed: 5` eşiği eklendi
ama yine de hacimli — Faz 3'ün skorlaması ve kategori tavanı bunu kesecek.

## Dikkat edilmesi gereken: Twitter sinyal kalitesi

Ham puana göre sıralandığında ilk sıraları kişisel tweet'ler alıyor
("If I was Indian", "So we're just outright wishing death on me now?").
Beğeni sayısı yüksek ama gazetenin amacıyla (bugün ne çıktı) ilgisiz.

İki savunma hattı zaten planda var:
1. **Faz 3** — kaynak içinde 0-1 normalizasyon, ham beğeni sayısı doğrudan
   GitHub yıldızıyla yarışmayacak.
2. **Faz 4** — LLM'in verdiği `signal: 1-5` puanı ve `min_signal: 2` eşiği.

Faz 4'ten sonra bu maddeler hâlâ üste çıkıyorsa Twitter ağırlığı düşürülmeli.

## Bütçe

Tam koşu: **560 Twitter okuma = $0.084**. LLM henüz devrede değil.

**Faz 3'e geçilebilir.**
