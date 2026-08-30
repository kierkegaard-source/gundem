"""Steam — yeni çıkanlar.

Faz 2 DÜZELTMESİ: `store.steampowered.com/feeds/newreleases.xml` ÖLÜ.
En yeni kaydı 49 gün önceye ait, listede 2023 tarihli oyunlar var — feed
güncellenmiyor. (Faz 0'da sadece kayıt sayısına bakılmış, tarihlere bakılmamıştı.)

Yerine store arama endpoint'i: `sort_by=Released_DESC`, JSON içinde HTML döner.
Çıkış tarihi gün hassasiyetinde ("30 Aug, 2026") — saat bilgisi yok, bu yüzden
pencere kontrolü gün bazında yapılır ve `published_at` o günün 00:00 UTC'si olur.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

import httpx

from sources.base import Item, Source, SourceError

SEARCH = ("https://store.steampowered.com/search/results/"
          "?query&start=0&count=100&dynamic_data=&sort_by=Released_DESC"
          "&category1=998&supportedlang=english&infinite=1&ndl=1")

INDIE_TAG_ID = 492

_ROW = re.compile(r'<a href="https://store\.steampowered\.com/app/')
_APPID = re.compile(r'data-ds-appid="(\d+)"')
_TAGIDS = re.compile(r'data-ds-tagids="\[([\d,]*)\]"')
_TITLE = re.compile(r'<span class="title">(.*?)</span>')
_RELEASED = re.compile(r'<div class="search_released[^"]*">\s*(.*?)\s*</div>', re.S)
_PRICE = re.compile(r'data-price-final="(\d+)"')


def _parse_day(raw: str) -> datetime | None:
    raw = html.unescape(raw or "").strip()
    for fmt in ("%d %b, %Y", "%b %d, %Y", "%d %B, %Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None                    # "Coming soon", sadece yıl, boş vb.


class Steam(Source):
    name = "steam"

    async def fetch(self, client: httpx.AsyncClient) -> list[Item]:
        try:
            r = await client.get(SEARCH, headers={"Accept": "application/json"})
            r.raise_for_status()
            doc = r.json().get("results_html", "")
        except Exception as exc:
            raise SourceError(f"store arama isteği başarısız: {exc!r}") from exc
        if not doc:
            raise SourceError("results_html boş — endpoint şeması değişmiş olabilir")

        rows = _ROW.split(doc)[1:]
        if not rows:
            raise SourceError("sonuç satırı ayrıştırılamadı")

        # Gün hassasiyeti: pencere gün bazında değerlendirilir.
        oldest_day = (datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)).date()
        items: list[Item] = []
        for row in rows:
            t = _TITLE.search(row)
            appid = _APPID.search(row)
            if not (t and appid):
                continue
            rel = _RELEASED.search(row)
            day = _parse_day(rel.group(1)) if rel else None
            if day is None or day.date() < oldest_day:
                continue
            tags = _TAGIDS.search(row)
            tagids = [int(x) for x in tags.group(1).split(",") if x] if tags else []
            is_indie = INDIE_TAG_ID in tagids
            price = _PRICE.search(row)
            title = html.unescape(t.group(1)).strip()
            items.append(Item(
                title=title,
                url=f"https://store.steampowered.com/app/{appid.group(1)}",
                source=self.name,
                category="gamedev",
                # Steam aramasında popülerlik metriği yok. PROJECT.md §6
                # "indie tag öncelikli" der — indie etiketlisi öne alınır.
                raw_score=2.0 if is_indie else 1.0,
                published_at=day,
                raw_text=title,
                extra={"appid": appid.group(1), "indie": is_indie,
                       "price_cents": int(price.group(1)) if price else None,
                       "released": rel.group(1).strip() if rel else None},
            ))
        if not items:
            raise SourceError(
                f"{len(rows)} satır ayrıştırıldı ama hiçbiri {oldest_day} sonrasına ait değil"
            )
        return items
