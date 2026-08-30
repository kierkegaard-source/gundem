"""Bluesky — AT Protocol public AppView, anahtarsız.

Faz 0 DÜZELTMESİ: `app.bsky.feed.searchPosts` anahtarsız erişime kapatılmış (403).
PROJECT.md'deki `feeds: [gamedev, screenshotsaturday, design]` bu haliyle çalışmaz.
Yerine feed generator URI'leri + `app.bsky.feed.getFeed` kullanılıyor.
Hesap timeline'ları için `getAuthorFeed`.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from sources._social import looks_like_launch
from sources.base import Item, Source, SourceError

PUB = "https://public.api.bsky.app/xrpc"


def _first_link(post: dict) -> str | None:
    """Gönderideki dış bağlantıyı bulur — asıl ilgilendiğimiz şey o."""
    embed = post.get("embed") or {}
    ext = embed.get("external") or (embed.get("media") or {}).get("external")
    if isinstance(ext, dict) and ext.get("uri"):
        return ext["uri"]
    for facet in (post.get("record", {}).get("facets") or []):
        for f in facet.get("features", []):
            if f.get("$type", "").endswith("#link") and f.get("uri"):
                return f["uri"]
    return None


class Bluesky(Source):
    name = "bluesky"

    def _to_item(self, post: dict, category: str, kind: str) -> Item | None:
        rec = post.get("record") or {}
        text = (rec.get("text") or "").strip()
        if not text:
            return None
        created = rec.get("createdAt") or post.get("indexedAt")
        try:
            pub = datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone(timezone.utc)
        except (AttributeError, ValueError):
            return None
        if not self.in_window(pub):
            return None

        link = _first_link(post)
        # Lansman ön filtresi — bkz. sources/_social.py'deki ölçüm.
        if self.cfg.get("require_launch_signal", True) \
                and not looks_like_launch(text, bool(link)):
            return None

        handle = (post.get("author") or {}).get("handle", "")
        rkey = post["uri"].rsplit("/", 1)[-1]
        permalink = f"https://bsky.app/profile/{handle}/post/{rkey}"
        return Item(
            title=text.split("\n")[0][:200] or text[:200],
            # Dış bağlantı varsa dedupe onun üzerinden yürüsün; yoksa gönderinin kendisi.
            url=link or permalink,
            source=self.name,
            category=category,
            raw_score=float(post.get("likeCount") or 0) + 2 * float(post.get("repostCount") or 0),
            published_at=pub,
            raw_text=text,
            author=handle,
            extra={"kind": kind, "permalink": permalink,
                   "likes": post.get("likeCount") or 0,
                   "reposts": post.get("repostCount") or 0},
        )

    async def _feed(self, client: httpx.AsyncClient, feed: dict) -> list[Item]:
        url = f"{PUB}/app.bsky.feed.getFeed?feed={quote(feed['uri'], safe='')}&limit=100"
        r = await client.get(url)
        r.raise_for_status()
        min_likes = int(self.cfg.get("min_likes_feed", 5))
        out = []
        for entry in r.json().get("feed", []):
            post = entry.get("post") or {}
            if (post.get("likeCount") or 0) < min_likes:
                continue                      # sinyal > hacim: feed'ler çok gürültülü
            it = self._to_item(post, feed.get("cat", "gamedev"), f"feed:{feed.get('name')}")
            if it:
                out.append(it)
        return out

    async def _author(self, client: httpx.AsyncClient, acc: dict) -> list[Item]:
        url = (f"{PUB}/app.bsky.feed.getAuthorFeed?actor={acc['handle']}"
               f"&limit=30&filter=posts_no_replies")
        r = await client.get(url)
        r.raise_for_status()
        out = []
        for entry in r.json().get("feed", []):
            it = self._to_item(entry.get("post") or {}, acc.get("cat", "dev"),
                               f"handle:{acc['handle']}")
            if it:
                out.append(it)
        return out

    async def fetch(self, client: httpx.AsyncClient) -> list[Item]:
        feeds = self.cfg.get("feeds") or []
        handles = self.cfg.get("handles") or []
        if not feeds and not handles:
            raise SourceError("config'de feed veya handle yok")

        jobs = [self._feed(client, f) for f in feeds] + [self._author(client, a) for a in handles]
        labels = [f"feed:{f.get('name')}" for f in feeds] + [f"@{a['handle']}" for a in handles]
        results = await asyncio.gather(*jobs, return_exceptions=True)

        items, failed = [], []
        for label, res in zip(labels, results):
            if isinstance(res, BaseException):
                failed.append(f"{label}({type(res).__name__})")
            else:
                items.extend(res)
        self.failed_feeds = failed
        if failed and not items:
            raise SourceError(f"hepsi düştü: {', '.join(failed[:5])}")
        return items
