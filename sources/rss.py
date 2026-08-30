"""Genel RSS/Atom kaynağı — config.yaml'daki 25 feed.

Her feed kendi try/except'inde: biri düşerse diğerleri toplanmaya devam eder.
Faz 0'da hepsi tek tek doğrulandı, ölü olanlar config'e hiç girmedi.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from sources._feed import parse_feed
from sources.base import Item, Source, SourceError

# Bazı sunucular bot UA'sına 403 veriyor (Faz 0: TIGSource). Tarayıcı UA'sı yedek.
_BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


class Rss(Source):
    name = "rss"

    async def _one(self, client: httpx.AsyncClient, feed: dict) -> list[Item]:
        url = feed["url"]
        r = await client.get(url, headers={"User-Agent": _BROWSER_UA,
                                           "Accept": "application/rss+xml, application/xml, text/xml, */*"})
        r.raise_for_status()
        records = parse_feed(r.content)
        cat = feed.get("cat", "dev")
        items: list[Item] = []
        for rec in records:
            pub = rec["published"]
            if pub is None or not self.in_window(pub):
                continue
            items.append(Item(
                title=rec["title"],
                url=rec["link"],
                source=self.name,
                category=cat,
                # RSS'te popülerlik metriği yok; skorlama kaynak ağırlığına dayanır.
                raw_score=1.0,
                published_at=pub,
                raw_text=f"{rec['title']} — {rec['summary']}" if rec["summary"] else rec["title"],
                author=rec["author"],
                extra={"feed": url, "feed_weight": feed.get("weight", 0.5)},
            ))
        return items

    async def fetch(self, client: httpx.AsyncClient) -> list[Item]:
        feeds = self.cfg.get("feeds") or []
        if not feeds:
            raise SourceError("config'de feed listesi yok")

        results = await asyncio.gather(
            *(self._one(client, f) for f in feeds), return_exceptions=True
        )
        items: list[Item] = []
        failed: list[str] = []
        for feed, res in zip(feeds, results):
            if isinstance(res, BaseException):
                host = feed["url"].split("/")[2] if "//" in feed["url"] else feed["url"]
                failed.append(f"{host}({type(res).__name__})")
            else:
                items.extend(res)

        self.failed_feeds = failed
        if failed and not items:
            raise SourceError(f"{len(failed)} feed'in hepsi düştü: {', '.join(failed[:5])}")
        return items
