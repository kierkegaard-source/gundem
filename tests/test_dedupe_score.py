"""Faz 3 testleri: tekilleştirme, skorlama, filtreleme."""
from datetime import datetime, timedelta, timezone

from pipeline.dedupe import Cluster, dedupe, normalize_title
from pipeline.score import (NEUTRAL_NORM, filter_clusters, recency_factor,
                            score_clusters)
from sources.base import Item

NOW = datetime.now(timezone.utc)

CFG = {
    "sources": {"hackernews": {"weight": 0.9}, "producthunt": {"weight": 1.0},
                "twitter": {"weight": 0.8}, "steam": {"weight": 0.6},
                "rss": {"weight": 0.7}},
    "scoring": {"multi_source_bonus": 1.4},
    "filters": {"max_per_category": 2, "max_total": 3},
}


def item(title, url, source, score=10.0, hours=1.0, cat="dev"):
    return Item(title=title, url=url, source=source, category=cat,
                raw_score=score, published_at=NOW - timedelta(hours=hours),
                raw_text=title)


# ---------- başlık normalizasyonu ----------

def test_prefix_ve_noktalama_atiliyor():
    assert normalize_title("Show HN: Foo-Bar, the Thing!") == "foo bar the thing"
    assert normalize_title("Now Available on Steam - Cool Game") == "cool game"


# ---------- 1. kademe: URL ----------

def test_ayni_url_farkli_kaynaklar_tek_maddeye_iniyor():
    items = [
        item("Widget", "https://widget.dev/?utm_source=ph", "producthunt"),
        item("Widget by someone", "https://WWW.widget.dev/", "hackernews"),
    ]
    clusters = dedupe(items)
    assert len(clusters) == 1
    assert set(clusters[0].sources) == {"producthunt", "hackernews"}


# ---------- 2. kademe: bulanık başlık ----------

def test_ayni_urun_uc_kaynakta_tek_satir_uc_rozet():
    """PROJECT.md §12 kabul kriteri — farklı URL'ler, benzer başlıklar."""
    items = [
        item("Show HN: Quantum Ledger Studio", "https://news.ycombinator.com/item?id=1",
             "hackernews", 42),
        item("Quantum Ledger Studio", "https://quantumledger.studio", "producthunt", 300),
        item("Quantum Ledger Studio is live!", "https://x.com/x/status/9", "twitter", 500),
    ]
    clusters = dedupe(items)
    assert len(clusters) == 1, [c.title for c in clusters]
    assert set(clusters[0].sources) == {"hackernews", "producthunt", "twitter"}
    assert clusters[0].multi_source


def test_ayni_kaynaktaki_benzer_basliklar_BIRLESMIYOR():
    """Yanlış pozitif koruması: iki ayrı Steam oyunu tek satıra inmemeli."""
    items = [
        item("Adventure Honor Chronicles", "https://store.steampowered.com/app/1", "steam"),
        item("Adventure Horror Chronicles", "https://store.steampowered.com/app/2", "steam"),
    ]
    assert len(dedupe(items)) == 2


def test_kisa_basliklar_bulanik_eslesmeye_girmiyor():
    items = [item("Bolt", "https://a.dev", "producthunt"),
             item("Bold", "https://b.dev", "hackernews")]
    assert len(dedupe(items)) == 2


def test_tek_kelimelik_baslik_uzun_baslige_gomulmuyor():
    """token_set_ratio alt küme durumunda 100 verir — tek kelimelik ürün adı
    uzun bir cümlenin içinde geçiyor diye birleşmemeli."""
    items = [item("Bolt", "https://bolt.dev", "producthunt"),
             item("Bolt Action Combat Simulator Deluxe", "https://steam.com/1", "steam")]
    assert len(dedupe(items)) == 2


def test_alt_kume_basliklar_birlesiyor():
    """Çok kelimeli başlık diğerinin içinde geçiyorsa aynı üründür."""
    items = [
        item("Hyperfocus Planner", "https://hyperfocus.app", "producthunt"),
        item("Hyperfocus Planner turns goals into daily progress",
             "https://news.ycombinator.com/item?id=5", "hackernews"),
    ]
    clusters = dedupe(items)
    assert len(clusters) == 1
    assert set(clusters[0].sources) == {"producthunt", "hackernews"}


# ---------- skorlama ----------

def test_recency_esikleri():
    assert recency_factor(0) == 1.0
    assert recency_factor(5.9) == 1.0
    assert recency_factor(6) == 0.9
    assert recency_factor(11.9) == 0.9
    assert recency_factor(12) == 0.8
    assert recency_factor(23.9) == 0.8
    assert recency_factor(24) == 0.5


def test_coklu_kaynak_bonusu_uygulaniyor():
    tek = Cluster(members=[item("Tek Kaynaklı Ürün Adı", "https://a.dev", "producthunt", 100)])
    cok = Cluster(members=[
        item("Çoklu Kaynaklı Ürün", "https://b.dev", "producthunt", 100),
        item("Çoklu Kaynaklı Ürün", "https://b.dev", "hackernews", 100),
    ])
    score_clusters([tek, cok], CFG)
    # İkisi de aynı ham puan ve tazelikte; fark yalnızca bonus.
    assert cok.score > tek.score
    assert abs(cok.score / tek.score - 1.4) < 0.01


def test_metriksiz_kaynak_notr_normalize_ediliyor():
    """RSS'in tüm maddeleri raw_score=1.0 taşır; hepsi kaynağın maksimumu
    sayılırsa Techmeme'in 15. haberi HN'in 1. sırasıyla eşitlenir."""
    rss = [Cluster(members=[item(f"Haber başlığı numara {i}", f"https://n.dev/{i}",
                                 "rss", 1.0)]) for i in range(3)]
    score_clusters(rss, CFG)
    beklenen = 0.7 * __import__("math").log1p(NEUTRAL_NORM) * 1.0
    assert all(abs(c.score - beklenen) < 1e-9 for c in rss)


def test_gercek_metrikli_kaynak_kaynak_icinde_normalize_ediliyor():
    a = Cluster(members=[item("Yüksek puanlı gönderi", "https://a.dev", "hackernews", 100)])
    b = Cluster(members=[item("Düşük puanlı gönderi", "https://b.dev", "hackernews", 10)])
    score_clusters([a, b], CFG)
    assert a.score > b.score


# ---------- filtreleme ----------

def test_kategori_ve_toplam_tavani():
    cs = [Cluster(members=[item(f"Madde numarası {i}", f"https://x.dev/{i}",
                                "producthunt", 100 - i, cat="dev" if i < 3 else "apps")])
          for i in range(6)]
    score_clusters(cs, CFG)
    kept = filter_clusters(cs, CFG)          # max_per_category=2, max_total=3
    assert len(kept) == 3
    assert sum(1 for c in kept if c.category == "dev") <= 2


def test_daha_once_yayinlanan_madde_tekrar_girmiyor():
    c = Cluster(members=[item("Dün yayınlanmış madde", "https://old.dev", "producthunt")])
    score_clusters([c], CFG)
    assert filter_clusters([c], CFG) == [c]
    assert filter_clusters([c], CFG, exclude_hashes={c.lead.url_hash}) == []
