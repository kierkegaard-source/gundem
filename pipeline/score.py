"""Skorlama ve filtreleme.

PROJECT.md §7.1:
    score = source_weight × log1p(raw_score_normalized) × recency_factor
- raw_score_normalized: kaynak İÇİNDE 0-1'e normalize (HN puanı ile Twitter
  beğenisi doğrudan kıyaslanamaz)
- recency_factor: 0-6s → 1.0, 6-12 → 0.9, 12-24 → 0.8, 24s+ → 0.5
- Birden fazla kaynakta çıkan madde × 1.4 bonus
Filtre: kategori başına max_per_category, toplam tavan max_total.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from pipeline.dedupe import Cluster
from sources.base import Item

DEFAULT_RECENCY = {"0-6": 1.0, "6-12": 0.9, "12-24": 0.8, "24+": 0.5}


def recency_factor(age_hours: float, table: dict | None = None) -> float:
    t = table or DEFAULT_RECENCY
    if age_hours < 6:
        return float(t.get("0-6", 1.0))
    if age_hours < 12:
        return float(t.get("6-12", 0.9))
    if age_hours < 24:
        return float(t.get("12-24", 0.8))
    return float(t.get("24+", 0.5))


def source_weight(item: Item, cfg: dict) -> float:
    """Kaynak ağırlığı. RSS feed'i / Twitter hesabı / Bluesky hesabı kendi
    ağırlığını taşıyorsa o kullanılır — config'de tek tek belirtilmişler."""
    for key in ("feed_weight", "account_weight", "handle_weight"):
        if key in item.extra:
            return float(item.extra[key])
    return float(cfg.get("sources", {}).get(item.source, {}).get("weight", 0.5))


# Metriksiz kaynaklar için nötr normalizasyon değeri.
# RSS, itch.io gibi kaynaklarda popülerlik metriği yok; koda 1.0 sabiti giriyor.
# Bu değer normalize edilince 1.0 (kaynağın MAKSİMUMU) olur ve o kaynağın her
# maddesi, gerçek metriği olan kaynakların en iyi maddesiyle eşit skor alır —
# Techmeme'in 15. haberi HN'in 1. sırasıyla yarışır. Bunun yerine böyle
# kaynaklara orta bir değer verilir; sıralamayı kaynak ağırlığı ve tazelik belirler.
NEUTRAL_NORM = 0.5


def normalizers(items: list[Item]) -> dict[str, tuple[float, bool]]:
    """Kaynak başına (maksimum ham puan, gerçek metriği var mı).

    Bir kaynağın tüm maddeleri aynı ham puanı taşıyorsa o kaynakta metrik yoktur.
    """
    hi: dict[str, float] = {}
    lo: dict[str, float] = {}
    for it in items:
        v = float(it.raw_score)
        hi[it.source] = max(hi.get(it.source, v), v)
        lo[it.source] = min(lo.get(it.source, v), v)
    return {src: (hi[src], hi[src] > lo[src]) for src in hi}


def score_clusters(clusters: list[Cluster], cfg: dict) -> list[Cluster]:
    all_items = [m for c in clusters for m in c.members]
    maxima = normalizers(all_items)
    recency_table = cfg.get("scoring", {}).get("recency")
    bonus = float(cfg.get("scoring", {}).get("multi_source_bonus", 1.4))
    now = datetime.now(timezone.utc)

    for c in clusters:
        best = 0.0
        for m in c.members:
            denom, has_metric = maxima.get(m.source, (1.0, False))
            normalized = (float(m.raw_score) / denom) if (has_metric and denom)                          else NEUTRAL_NORM
            age = (now - m.published_at).total_seconds() / 3600
            s = (source_weight(m, cfg)
                 * math.log1p(normalized)
                 * recency_factor(age, recency_table))
            best = max(best, s)
        # Birden fazla kaynakta çıkmak en güçlü sinyal.
        c.score = best * (bonus if c.multi_source else 1.0)
    return sorted(clusters, key=lambda c: -c.score)


def filter_clusters(clusters: list[Cluster], cfg: dict,
                    exclude_hashes: set[str] | None = None,
                    oversample: float = 1.0) -> list[Cluster]:
    """Kategori başına tavan + toplam tavan. Zaten yayınlanmışlar dışlanır.

    `oversample`: tavanları bu katsayıyla genişletir. Faz 4'te gerekti —
    filtreleme özetlemeden ÖNCE çalıştığı için kategori kotasını düşük sinyalli
    maddeler kapıyor, sonra `signal` filtresi onları eliyor ve bölüm boş kalıyor.
    İlk koşuda gamedev 15 slotunu Bluesky'ın sanat paylaşımlarına verdi, signal
    filtresinden sonra 4 madde kaldı; Steam'in 52 yeni oyunu hiç şans bulamadı.
    Çözüm: kotadan fazla aday özetlenir, eleme sonrası tavan tekrar uygulanır.
    """
    f = cfg.get("filters", {})
    per_cat = int(int(f.get("max_per_category", 15)) * oversample)
    total_cap = int(int(f.get("max_total", 60)) * oversample)
    exclude = exclude_hashes or set()

    kept: list[Cluster] = []
    counts: dict[str, int] = {}
    for c in sorted(clusters, key=lambda c: -c.score):
        # Kümenin herhangi bir üyesi daha önce yayınlandıysa madde tekrar girmez.
        if any(m.url_hash in exclude for m in c.members):
            continue
        cat = c.category
        if counts.get(cat, 0) >= per_cat:
            continue
        kept.append(c)
        counts[cat] = counts.get(cat, 0) + 1
        if len(kept) >= total_cap:
            break
    return kept
