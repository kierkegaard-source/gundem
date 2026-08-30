"""Product Hunt — GraphQL v2.

Faz 0 bulgusu: `postedAfter` filtresi olmadan sorgu 3 haftalık eski ürünleri
döndürüyor. Filtre şart. Oran limiti 6250/15dk, biz günde 1 istek atıyoruz.
`topics` alanı kategoriyi LLM'e sormadan belirlemeye yetiyor.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from pipeline.config import secret
from sources.base import Item, Source, SourceError

ENDPOINT = "https://api.producthunt.com/v2/api/graphql"

QUERY = """
query TodayPosts($after: DateTime!) {
  posts(order: VOTES, first: 40, postedAfter: $after) {
    edges { node {
      id name tagline url website votesCount commentsCount createdAt
      topics(first: 5) { edges { node { name } } }
    } }
  }
}
"""

# topic adı (küçük harf) -> kategori. İlk eşleşen kazanır.
_TOPIC_MAP = [
    (("developer tools", "api", "development", "open source", "github", "no-code"), "dev"),
    (("design tools", "design", "user experience", "icons", "prototyping"), "design"),
    (("games", "gaming", "game development"), "gamedev"),
    (("venture capital", "fundraising", "startup"), "startup"),
]


def _category(topics: list[str]) -> str:
    low = [t.lower() for t in topics]
    for keys, cat in _TOPIC_MAP:
        if any(k in low for k in keys):
            return cat
    return "apps"


class ProductHunt(Source):
    name = "producthunt"

    async def fetch(self, client: httpx.AsyncClient) -> list[Item]:
        token = secret("PRODUCTHUNT_TOKEN")
        if not token:
            raise SourceError("PRODUCTHUNT_TOKEN yok")

        after = self.since.strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            r = await client.post(
                ENDPOINT,
                json={"query": QUERY, "variables": {"after": after}},
                headers={"Authorization": f"Bearer {token}",
                         "Accept": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            raise SourceError(f"GraphQL isteği başarısız: {exc!r}") from exc

        if "errors" in data:
            msg = "; ".join(e.get("message", "?") for e in data["errors"])[:200]
            raise SourceError(f"GraphQL hatası: {msg}")

        edges = (data.get("data") or {}).get("posts", {}).get("edges", [])
        items: list[Item] = []
        for e in edges:
            n = e["node"]
            topics = [t["node"]["name"] for t in n.get("topics", {}).get("edges", [])]
            pub = datetime.fromisoformat(n["createdAt"].replace("Z", "+00:00")).astimezone(timezone.utc)
            items.append(Item(
                title=n["name"],
                # website ürünün kendi sitesi — dedupe için kanonik hedef odur.
                # website yoksa PH sayfasına düşülür.
                url=n.get("website") or n["url"],
                source=self.name,
                category=_category(topics),
                raw_score=float(n.get("votesCount") or 0),
                published_at=pub,
                raw_text=f"{n['name']} — {n.get('tagline') or ''}",
                extra={"ph_url": n["url"], "topics": topics,
                       "comments": n.get("commentsCount") or 0},
            ))
        if not items:
            raise SourceError(f"postedAfter={after} için ürün dönmedi")
        return items
