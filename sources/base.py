"""Item veri modeli, URL kanonikleştirme ve ortak Source arayüzü."""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

# Dedupe'u bozan izleme parametreleri. utm_* önek olarak, gerisi tam eşleşmeyle atılır.
_TRACKING_PREFIXES = ("utm_", "_hs")
_TRACKING_EXACT = {
    "fbclid", "gclid", "msclkid", "yclid", "igshid", "mc_cid", "mc_eid",
    "ref", "ref_src", "ref_url", "source", "si", "spm", "at_medium", "at_campaign",
}


def canonical_url(url: str) -> str:
    """Aynı ürünün farklı linklerini tek forma indirger.

    Şema/host küçük harfe, fragment atılır, izleme parametreleri silinir,
    kalan parametreler sıralanır, sondaki eğik çizgi atılır.
    """
    url = (url or "").strip()
    if not url:
        return ""
    parts = urlsplit(url)
    scheme = (parts.scheme or "https").lower()
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not k.lower().startswith(_TRACKING_PREFIXES) and k.lower() not in _TRACKING_EXACT
    ]
    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((scheme, host, path, urlencode(sorted(query)), ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()


@dataclass
class Item:
    title: str
    url: str
    source: str                 # "hackernews", "github_trending", ...
    category: str               # dev | gamedev | apps | design | startup | tr
    raw_score: float            # kaynağın kendi metriği (puan, yıldız, beğeni)
    published_at: datetime      # UTC
    raw_text: str               # başlık + açıklama, özetleme girdisi (max 1500 char)
    author: str | None = None
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.title = " ".join((self.title or "").split())
        self.url = canonical_url(self.url)
        self.raw_text = " ".join((self.raw_text or "").split())[:1500]
        if self.published_at.tzinfo is None:
            self.published_at = self.published_at.replace(tzinfo=timezone.utc)
        else:
            self.published_at = self.published_at.astimezone(timezone.utc)

    @property
    def url_hash(self) -> str:
        return url_hash(self.url)

    @property
    def age_hours(self) -> float:
        return (datetime.now(timezone.utc) - self.published_at).total_seconds() / 3600


class SourceError(RuntimeError):
    """Bir kaynak veri döndüremedi. Pipeline durmaz, kaynak atlanır."""


class Source(ABC):
    """Tüm kaynakların ortak arayüzü.

    Sözleşme: fetch() ya Item listesi döndürür ya da istisna fırlatır.
    Kısmi başarı serbesttir — 10 kayıttan 3'ü bozuksa 7'si döndürülür.
    """

    name: str = "base"

    def __init__(self, cfg: dict, settings: dict) -> None:
        self.cfg = cfg or {}
        self.settings = settings or {}
        # collect.py tarafından atanır. Maliyetli kaynaklar (Twitter) tavanı
        # kendi döngülerinin içinde kontrol eder.
        self.budget = None
        # Çoklu alt-kaynağı olan kaynaklar (rss, bluesky, twitter) kısmen
        # düşen alt-kaynakları buraya yazar; kaynak yine de başarılı sayılır.
        self.failed_feeds: list[str] = []
        self.weight = float(self.cfg.get("weight", 0.5))
        self.lookback_hours = int(
            self.settings.get("filters", {}).get("lookback_hours", 26)
        )

    @property
    def since(self) -> datetime:
        return datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)

    def in_window(self, dt: datetime) -> bool:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= self.since

    @abstractmethod
    async def fetch(self, client: httpx.AsyncClient) -> list[Item]:
        ...
