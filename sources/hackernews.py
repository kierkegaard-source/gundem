"""Hacker News — Algolia arama API'si. Anahtar gerektirmez.

Faz 0 bulgusu: "Launch HN" min 10 puanla son 24 saatte 0 kayıt döndürüyor
(7 günde 18 var ama puanları düşük). Bu yüzden eşik sorgu başına ayrı.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from sources.base import Item, Source, SourceError

BASE = "https://hn.algolia.com/api/v1/search_by_date"


class HackerNews(Source):
    name = "hackernews"

    async def fetch(self, client: httpx.AsyncClient) -> list[Item]:
        since_ts = int(self.since.timestamp())
        queries = self.cfg.get("queries") or [{"q": "Show HN", "min_points": 10}]
        items: list[Item] = []
        errors: list[str] = []

        for q in queries:
            query = q["q"] if isinstance(q, dict) else str(q)
            min_points = int(q.get("min_points", 10)) if isinstance(q, dict) else 10
            params = {
                "query": query,
                "tags": "story",
                "numericFilters": f"created_at_i>{since_ts},points>={min_points}",
                "hitsPerPage": 50,
            }
            try:
                r = await client.get(BASE, params=params)
                r.raise_for_status()
                hits = r.json().get("hits", [])
            except Exception as exc:                      # kısmi başarı: diğer sorgu denenir
                errors.append(f"{query}: {exc!r}")
                continue

            for h in hits:
                title = h.get("title") or ""
                # Algolia'nın `query` parametresi TAM METİN araması yapar: "Show HN"
                # sorgusu "Ask HN: …" başlıklarını da döndürüyor ve o kayıtlar
                # "Launch HN" sorgusunun min_points=0 eşiğinden içeri sızıyor.
                # Başlık öneki + puan eşiği burada tekrar uygulanıyor.
                if not title.lower().startswith(query.lower()):
                    continue
                if float(h.get("points") or 0) < min_points:
                    continue
                # Metin gönderisinde url yok — HN tartışma sayfasına düşülür.
                url = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
                if not title:
                    continue
                items.append(Item(
                    title=title,
                    url=url,
                    source=self.name,
                    category="dev",
                    raw_score=float(h.get("points") or 0),
                    published_at=datetime.fromtimestamp(h["created_at_i"], tz=timezone.utc),
                    raw_text=title,
                    author=h.get("author"),
                    extra={
                        "hn_id": h["objectID"],
                        "comments": h.get("num_comments") or 0,
                        "query": query,
                        "discussion": f"https://news.ycombinator.com/item?id={h['objectID']}",
                    },
                ))

        if not items and errors:
            raise SourceError("; ".join(errors))
        return items
