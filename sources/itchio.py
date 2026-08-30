"""itch.io — yeni oyunlar feed'i.

Faz 0: PROJECT.md'de feed URL'i belirsizdi; çalışan `itch.io/games/newest.xml`.
Başlıklar `AD [Free] [Puzzle]` biçiminde geliyor, etiketler ayrıştırılıyor.
"""
from __future__ import annotations

import asyncio
import re

import httpx

from sources._feed import parse_feed
from sources.base import Item, Source, SourceError

# FAZ 4 BULGUSU: tek feed yetmiyor, ikisi birbirini tamamlıyor (ölçüldü).
#   newest.xml          → 20 kayıt 26s penceresinde, ama yalnızca 18/36'sında açıklama
#   new-and-popular.xml → 30/36'sında açıklama, ama yalnızca 2'si pencerede
# Açıklamasız maddeye LLM haklı olarak signal=1 veriyor ("Behind The Shade
# (Free, Simulation)" özetlenecek bir şey değil), gamedev bölümü boş kalıyordu.
#
# Çözüm: ikisi de çekilir.
#   - newest: gerçek yayın tarihi, pencere uygulanır (bugün çıkanlar)
#   - new-and-popular: küratörlü "şu an popüler" listesi; GitHub Trending'le
#     aynı mantık — sinyal tazelik değil popülerlik, o yüzden pencere
#     uygulanmaz. Yayın tarihi OLDUĞU GİBİ bırakılır (yaş sütunu yalan
#     söylemesin); eskiyse recency_factor zaten cezalandırır.
DEFAULT_FEEDS = [
    {"url": "https://itch.io/games/newest.xml",          "window": True,  "score": 1.0},
    {"url": "https://itch.io/games/new-and-popular.xml", "window": False, "score": 2.0},
]
_BRACKET = re.compile(r"\[([^\]]+)\]")


class Itchio(Source):
    name = "itchio"

    async def fetch(self, client: httpx.AsyncClient) -> list[Item]:
        feeds = self.cfg.get("feeds") or DEFAULT_FEEDS
        results = await asyncio.gather(
            *(self._one(client, f) for f in feeds), return_exceptions=True)
        items, failed = [], []
        for feed, res in zip(feeds, results):
            if isinstance(res, BaseException):
                failed.append(f"{feed['url'].rsplit('/', 1)[-1]}({type(res).__name__})")
            else:
                items.extend(res)
        self.failed_feeds = failed
        if not items:
            raise SourceError(f"hiç kayıt alınamadı: {', '.join(failed) or 'pencerede madde yok'}")
        return items

    async def _one(self, client: httpx.AsyncClient, feed: dict) -> list[Item]:
        url = feed["url"]
        r = await client.get(url)
        r.raise_for_status()
        records = parse_feed(r.content)

        items: list[Item] = []
        for rec in records:
            pub = rec["published"]
            if pub is None:
                continue
            if feed.get("window", True) and not self.in_window(pub):
                continue
            tags = _BRACKET.findall(rec["title"])
            clean = _BRACKET.sub("", rec["title"]).strip(" -–—")
            items.append(Item(
                title=clean or rec["title"],
                url=rec["link"],
                source=self.name,
                category="gamedev",
                # newest 1.0, new-and-popular 2.0 — küratörlü liste daha güçlü
                # sinyal. İki farklı değer olduğu için skorlama bu kaynağı
                # "metriği var" sayıp kaynak içinde normalize eder.
                raw_score=float(feed.get("score", 1.0)),
                published_at=pub,
                # FAZ 4: metinsiz maddeye LLM signal=1 veriyor. Feed'in
                # köşeli parantezli etiketleri ([Free] [Puzzle]) başlıktan
                # ayrılıyor ama bilgi taşıyor — metne katılıyor.
                raw_text=" ".join(x for x in (
                    clean,
                    f"({', '.join(tags)})" if tags else "",
                    f"— {rec['summary']}" if rec["summary"] else "",
                ) if x),
                author=rec["link"].split("//")[-1].split(".")[0] if "//" in rec["link"] else None,
                extra={"tags": tags, "feed": url.rsplit("/", 1)[-1]},
            ))
        return items
