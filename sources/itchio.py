"""itch.io — yeni oyunlar feed'i.

Faz 0: PROJECT.md'de feed URL'i belirsizdi; çalışan `itch.io/games/newest.xml`.
Başlıklar `AD [Free] [Puzzle]` biçiminde geliyor, etiketler ayrıştırılıyor.
"""
from __future__ import annotations

import re

import httpx

from sources._feed import parse_feed
from sources.base import Item, Source, SourceError

DEFAULT_FEED = "https://itch.io/games/newest.xml"
_BRACKET = re.compile(r"\[([^\]]+)\]")


class Itchio(Source):
    name = "itchio"

    async def fetch(self, client: httpx.AsyncClient) -> list[Item]:
        url = self.cfg.get("feed", DEFAULT_FEED)
        try:
            r = await client.get(url)
            r.raise_for_status()
            records = parse_feed(r.content)
        except Exception as exc:
            raise SourceError(f"{url}: {exc!r}") from exc

        items: list[Item] = []
        for rec in records:
            pub = rec["published"]
            if pub is None or not self.in_window(pub):
                continue
            tags = _BRACKET.findall(rec["title"])
            clean = _BRACKET.sub("", rec["title"]).strip(" -–—")
            items.append(Item(
                title=clean or rec["title"],
                url=rec["link"],
                source=self.name,
                category="gamedev",
                raw_score=1.0,          # itch.io feed'inde popülerlik metriği yok
                published_at=pub,
                raw_text=f"{clean} — {rec['summary']}" if rec["summary"] else clean,
                author=rec["link"].split("//")[-1].split(".")[0] if "//" in rec["link"] else None,
                extra={"tags": tags},
            ))
        if not items and records:
            raise SourceError(f"{len(records)} kayıt geldi ama hiçbiri {self.lookback_hours}s penceresinde değil")
        return items
