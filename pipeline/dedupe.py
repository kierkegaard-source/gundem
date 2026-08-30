"""İki kademeli tekilleştirme.

PROJECT.md §5: "Dedupe için url_hash yeterli değil — aynı ürün farklı URL'lerle
çıkabilir (Product Hunt linki vs. kendi sitesi). İkinci kademe: başlık normalize
edilip rapidfuzz ile %85 üzeri benzerlik varsa aynı kayıt sayılır."

TASARIM KARARI — bulanık eşleşme YALNIZCA farklı kaynaklar arasında uygulanır.
Kaynak içi mükerrer zaten URL ile yakalanıyor (Faz 2: 63 mükerrerin hepsi Bluesky'da,
hepsi aynı URL'e düşüyordu). Kaynak içinde bulanık eşleşme açılırsa "Adventure Honor"
ile "Adventure Horror" gibi iki ayrı Steam oyunu birleşir — yanlış pozitif riski
kazancından büyük. Hedef vaka zaten kaynaklar arası: aynı ürünün Product Hunt +
HN + Twitter'da çıkması.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from sources.base import Item

# İki ölçüt birlikte kullanılır (Faz 3'te gerçek + sentetik veriyle ölçüldü):
#
#   token_sort_ratio ≥ 85  — kelime sırası farklı, içerik aynı
#   token_set_ratio  ≥ 92  — bir başlık diğerinin içinde geçiyor
#
# Neden ikisi birden: "Quantum Ledger Studio" ile "Quantum Ledger Studio is live!"
# sort'ta 84 alıyor (eşiğin bir puan altı), set'te 100. Tek başına sort kullanmak
# gerçek eşleşmeleri kaçırıyor.
# Neden set eşiği 92: "claude code cli" / "claude code sdk" set'te 85 alıyor —
# 90'ın altında bir eşik iki ayrı ürünü birleştirirdi.
# set_ratio bir başlığı diğerinin alt kümesi sayınca 100 verdiği için tek kelimelik
# başlıklara uygulanmaz ("Bolt", "Bolt Action Combat Simulator" içinde 100 alır).
FUZZY_SORT_THRESHOLD = 85
FUZZY_SET_THRESHOLD = 92
MIN_TITLE_LEN = 15          # kısa başlıklar tesadüfen benzeşiyor
MIN_TOKENS_FOR_SET = 2      # set_ratio yalnızca çok kelimeli başlıklarda

# Başlık öneki gürültüsü — kaynaklar aynı ürünü farklı süsleyerek yazıyor.
_PREFIXES = re.compile(
    r"^(show hn|launch hn|ask hn|tell hn|now available on steam|"
    r"new release|introducing|announcing)\s*[:–—-]?\s*", re.I)
_NOISE = re.compile(r"[^a-z0-9\s]+")
_WS = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    t = _PREFIXES.sub("", (title or "").lower())
    t = _NOISE.sub(" ", t)
    return _WS.sub(" ", t).strip()


def _similar(a: str, b: str) -> bool:
    if fuzz.token_sort_ratio(a, b) >= FUZZY_SORT_THRESHOLD:
        return True
    shorter = a if len(a) <= len(b) else b
    if len(shorter.split()) < MIN_TOKENS_FOR_SET:
        return False
    return fuzz.token_set_ratio(a, b) >= FUZZY_SET_THRESHOLD


@dataclass
class Cluster:
    """Tek bir gerçek dünya maddesi — bir veya birden fazla kaynaktan gelmiş."""

    members: list[Item] = field(default_factory=list)
    score: float = 0.0
    # Faz 4'te LLM tarafından doldurulur. Bütçe tavanına çarpılırsa None kalır
    # ve sayfa ham başlıkla basılır.
    summary_tr: str | None = None
    why_tr: str | None = None
    signal: int | None = None
    llm_category: str | None = None

    @property
    def sources(self) -> list[str]:
        seen: list[str] = []
        for m in self.members:
            if m.source not in seen:
                seen.append(m.source)
        return seen

    @property
    def multi_source(self) -> bool:
        return len(self.sources) > 1

    @property
    def lead(self) -> Item:
        """Temsilci kayıt: en yüksek ham puanlı olan."""
        return max(self.members, key=lambda m: m.raw_score)

    @property
    def title(self) -> str:
        return self.lead.title

    @property
    def url(self) -> str:
        return self.lead.url

    @property
    def category(self) -> str:
        # LLM bir kategori verdiyse o kazanır — başlığı okuyup karar veriyor,
        # kaynak bazlı tahminden daha isabetli.
        if self.llm_category:
            return self.llm_category
        # Çoğunluk kategorisi; beraberlikte temsilcininki.
        counts: dict[str, int] = {}
        for m in self.members:
            counts[m.category] = counts.get(m.category, 0) + 1
        best = max(counts.values())
        winners = [c for c, n in counts.items() if n == best]
        return self.lead.category if self.lead.category in winners else winners[0]

    @property
    def published_at(self):
        return max(m.published_at for m in self.members)

    @property
    def raw_text(self) -> str:
        return max((m.raw_text for m in self.members), key=len, default="")


def dedupe(items: list[Item]) -> list[Cluster]:
    """1. kademe: kanonik URL hash'i. 2. kademe: kaynaklar arası bulanık başlık."""
    by_hash: dict[str, Cluster] = {}
    for it in items:
        by_hash.setdefault(it.url_hash, Cluster()).members.append(it)

    clusters = list(by_hash.values())

    # 2. kademe — yalnızca farklı kaynaklar arasında
    norms = [normalize_title(c.title) for c in clusters]
    parent = list(range(len(clusters)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(clusters)):
        ni = norms[i]
        if len(ni) < MIN_TITLE_LEN:
            continue
        si = set(clusters[i].sources)
        for j in range(i + 1, len(clusters)):
            nj = norms[j]
            if len(nj) < MIN_TITLE_LEN:
                continue
            if si & set(clusters[j].sources):
                continue                      # aynı kaynak — URL dedupe zaten yaptı
            # NOT: burada uzunluk ön filtresi YOK. Bir zamanlar vardı ama
            # alt küme eşleşmesini engelliyordu ("Hyperfocus Planner" ile
            # "Hyperfocus Planner turns goals into daily progress" arasındaki
            # 31 karakterlik fark ön filtreye takılıyordu). ~300 küme için
            # O(n²) karşılaştırma zaten milisaniyeler sürüyor.
            if _similar(ni, nj):
                union(i, j)

    merged: dict[int, Cluster] = {}
    for i, c in enumerate(clusters):
        root = find(i)
        if root not in merged:
            merged[root] = Cluster()
        merged[root].members.extend(c.members)
    return list(merged.values())
