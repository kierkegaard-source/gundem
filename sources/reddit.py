"""Reddit — OAuth (script app).

KAPALI. config.yaml'da `enabled: false`. Sebep (Faz 0, FAZ0-RAPOR.md):

1. Responsible Builder Policy API erişimi için açık onay şart kılıyor;
   `prefs/apps` üzerinden app oluşturma bu onay olmadan başarısız oluyor.
2. Aynı politika Reddit verisinin yazılı onay olmadan PAYLAŞILMASINI yasaklıyor.
   Bu proje çıktıyı public GitHub Pages'te yayınlıyor ve digest.db'yi public
   repoya commit ediyor — doğrudan o maddenin kapsamında.

Kod, onay alınırsa `enabled: true` yapmak yeterli olsun diye tamamlandı.
Anonim erişim de ölçüldü ve elendi: `.json` 403, `.rss` ikinci istekte 429
ve upvote sayısı taşımıyor (min_upvotes filtresi kurulamıyor).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from pipeline.config import secret
from sources.base import Item, Source, SourceError

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API = "https://oauth.reddit.com"
UA = "macos:daily-launch:0.1 (kisisel gunluk ozet)"

_CATEGORY = {"gamedev": "gamedev", "indiedev": "gamedev",
             "sideproject": "apps", "webdev": "dev"}


class Reddit(Source):
    name = "reddit"

    async def _token(self, client: httpx.AsyncClient) -> str:
        cid, csec = secret("REDDIT_CLIENT_ID"), secret("REDDIT_CLIENT_SECRET")
        if not (cid and csec):
            raise SourceError("REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET yok")
        r = await client.post(TOKEN_URL, data={"grant_type": "client_credentials"},
                              auth=(cid, csec), headers={"User-Agent": UA})
        r.raise_for_status()
        return r.json()["access_token"]

    async def _sub(self, client: httpx.AsyncClient, sub: str, token: str) -> list[Item]:
        r = await client.get(f"{API}/r/{sub}/new", params={"limit": 50, "raw_json": 1},
                             headers={"Authorization": f"Bearer {token}", "User-Agent": UA})
        r.raise_for_status()
        min_up = int(self.cfg.get("min_upvotes", 25))
        out = []
        for child in r.json()["data"]["children"]:
            d = child["data"]
            ups = int(d.get("ups") or 0)
            if ups < min_up:
                continue
            pub = datetime.fromtimestamp(d["created_utc"], tz=timezone.utc)
            if not self.in_window(pub):
                continue
            out.append(Item(
                title=d.get("title") or "",
                url=d.get("url_overridden_by_dest") or f"https://reddit.com{d['permalink']}",
                source=self.name,
                category=_CATEGORY.get(sub.lower(), "dev"),
                raw_score=float(ups),
                published_at=pub,
                raw_text=f"{d.get('title')} — {(d.get('selftext') or '')[:400]}",
                author=d.get("author"),
                extra={"subreddit": sub, "comments": d.get("num_comments") or 0,
                       "permalink": f"https://reddit.com{d['permalink']}"},
            ))
        return out

    async def fetch(self, client: httpx.AsyncClient) -> list[Item]:
        token = await self._token(client)
        subs = self.cfg.get("subreddits") or []
        results = await asyncio.gather(*(self._sub(client, s, token) for s in subs),
                                       return_exceptions=True)
        items, failed = [], []
        for sub, res in zip(subs, results):
            if isinstance(res, BaseException):
                failed.append(f"r/{sub}({type(res).__name__})")
            else:
                items.extend(res)
        self.failed_feeds = failed
        if failed and not items:
            raise SourceError(f"hepsi düştü: {', '.join(failed)}")
        return items
