"""TwitterAPI.io — SADECE hesap timeline'ı.

PROJECT.md §6: "Anahtar kelime araması YAPMA — arama binlerce alakasız tweet
döndürür ve hepsi okuma olarak faturalanır."

Faz 0 bulgusu: `last_tweets` sayfa boyutu 20'de SABİT. count/limit/pageSize
parametrelerinin üçü de yok sayılıyor. Hesap başına 20 okuma zorunlu, yani
maliyet doğrudan hesap sayısıyla orantılı. Bütçe tavanı bu yüzden hesap
döngüsünün İÇİNDE kontrol ediliyor — tavana çarpınca kalan hesaplar atlanır.
"""
from __future__ import annotations

import asyncio
import html
from datetime import datetime, timezone

import httpx

from pipeline.config import secret
from sources._social import has_url, looks_like_launch
from sources.base import Item, Source, SourceError

BASE = "https://api.twitterapi.io"
PAGE_SIZE = 20            # sabit, değiştirilemiyor (Faz 0'da doğrulandı)
# 67 hesapla 5 eşzamanlılıkta koşu 27 saniye sürüyordu; hesap listesi
# büyüdükçe doğrusal artıyor. 8'e çıkarıldı.
CONCURRENCY = 8


def _parse_dt(raw: str) -> datetime | None:
    try:                                      # "Sun Aug 30 13:31:57 +0000 2026"
        return datetime.strptime(raw, "%a %b %d %H:%M:%S %z %Y").astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat((raw or "").replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


class Twitter(Source):
    name = "twitter"

    async def _account(self, client: httpx.AsyncClient, acc: dict,
                       key: str, sem: asyncio.Semaphore) -> list[Item]:
        handle = acc["handle"]
        async with sem:
            r = await client.get(f"{BASE}/twitter/user/last_tweets",
                                 params={"userName": handle},
                                 headers={"X-API-Key": key})
            r.raise_for_status()
            data = r.json()

        tweets = (data.get("data") or {}).get("tweets") or data.get("tweets") or []
        if self.budget:
            self.budget.charge_tweets(len(tweets))

        out: list[Item] = []
        for t in tweets:
            # API metni HTML kaçışlı döndürüyor (&gt;, &amp;, &lt;).
            text = html.unescape(t.get("text") or "").strip()
            if not text or t.get("isReply") or text.startswith("RT @"):
                continue                       # yanıt ve retweet gürültüdür
            # Lansman ön filtresi — bkz. sources/_social.py'deki ölçüm.
            if self.cfg.get("require_launch_signal", True) \
                    and not looks_like_launch(text, has_url(text)):
                continue
            pub = _parse_dt(t.get("createdAt", ""))
            if pub is None or not self.in_window(pub):
                continue
            url = t.get("url") or f"https://x.com/{handle}/status/{t.get('id')}"
            out.append(Item(
                title=text.split("\n")[0][:200] or text[:200],
                url=url,
                source=self.name,
                category=acc.get("cat", "apps"),
                raw_score=float(t.get("likeCount") or 0) + 2 * float(t.get("retweetCount") or 0),
                published_at=pub,
                raw_text=text,
                author=handle,
                extra={"likes": t.get("likeCount") or 0,
                       "retweets": t.get("retweetCount") or 0,
                       "account_weight": acc.get("weight", 0.5)},
            ))
        return out

    async def fetch(self, client: httpx.AsyncClient) -> list[Item]:
        key = secret("TWITTERAPI_KEY")
        if not key:
            raise SourceError("TWITTERAPI_KEY yok")
        accounts = self.cfg.get("accounts") or []
        if not accounts:
            raise SourceError("config'de hesap listesi yok")

        # Bütçe: her hesap PAGE_SIZE okuma demek. Tavanı aşacak hesaplar hiç istenmez.
        allowed = accounts
        if self.budget:
            room = max(0, self.budget.daily_twitter_reads - self.budget.tweet_reads)
            cap = room // PAGE_SIZE
            if cap < len(accounts):
                allowed = accounts[:cap]
                self.budget.note(
                    f"twitter: bütçe tavanı — {len(accounts)} hesaptan {len(allowed)}'i çekildi"
                )
        if not allowed:
            raise SourceError(
                f"bütçe tavanı: {self.budget.tweet_reads}/{self.budget.daily_twitter_reads} okuma dolu"
            )

        sem = asyncio.Semaphore(CONCURRENCY)
        results = await asyncio.gather(
            *(self._account(client, a, key, sem) for a in allowed), return_exceptions=True
        )
        items, failed = [], []
        for acc, res in zip(allowed, results):
            if isinstance(res, BaseException):
                failed.append(f"@{acc['handle']}({type(res).__name__})")
            else:
                items.extend(res)
        self.failed_feeds = failed
        if failed and not items:
            raise SourceError(f"{len(failed)} hesabın hepsi düştü: {', '.join(failed[:5])}")
        return items
