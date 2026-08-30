"""GitHub Trending — resmi API yok, HTML scrape.

Faz 0 bulgusu: başlık anchor'ında href diğer özniteliklerden SONRA geliyor,
naif `<h2><a href=` deseni login linklerini yakalıyor. Article bloğu bazlı parse şart.
Kırılgan bir kaynaktır; DOM değişirse SourceError fırlatır ve pipeline devam eder.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

import httpx

from sources.base import Item, Source, SourceError

URL = "https://github.com/trending"

_BLOCK = re.compile(r'<article class="Box-row"')
_SLUG = re.compile(r'<h2[^>]*>.*?href="/([^"]+?)"', re.S)
_DESC = re.compile(r'<p class="col-9[^"]*">\s*(.*?)\s*</p>', re.S)
_LANG = re.compile(r'itemprop="programmingLanguage">([^<]+)<')
_TODAY = re.compile(r'([\d,]+)\s*stars today')
_TAGS = re.compile(r"<[^>]+>")


class GithubTrending(Source):
    name = "github_trending"

    async def fetch(self, client: httpx.AsyncClient) -> list[Item]:
        params = {"since": self.cfg.get("since", "daily")}
        try:
            r = await client.get(URL, params=params,
                                 headers={"Accept": "text/html,application/xhtml+xml"})
            r.raise_for_status()
        except Exception as exc:
            raise SourceError(f"trending sayfası alınamadı: {exc!r}") from exc

        blocks = _BLOCK.split(r.text)[1:]
        if not blocks:
            raise SourceError("DOM değişmiş: 'article.Box-row' bulunamadı")

        min_stars = int(self.cfg.get("min_stars_today", 50))
        now = datetime.now(timezone.utc)
        items: list[Item] = []

        for b in blocks:
            m = _SLUG.search(b)
            if not m:
                continue
            slug = m.group(1)
            today = _TODAY.search(b)
            stars_today = int(today.group(1).replace(",", "")) if today else 0
            if stars_today < min_stars:
                continue
            d = _DESC.search(b)
            desc = html.unescape(_TAGS.sub("", d.group(1))).strip() if d else ""
            lang = _LANG.search(b)
            items.append(Item(
                title=slug,
                url=f"https://github.com/{slug}",
                source=self.name,
                category="dev",
                raw_score=float(stars_today),
                # Trending'de yayın tarihi yok; "bugün trend olan" bilgisi taşınıyor.
                published_at=now,
                raw_text=f"{slug} — {desc}" if desc else slug,
                author=slug.split("/")[0],
                extra={"language": lang.group(1) if lang else None,
                       "stars_today": stars_today, "description": desc},
            ))

        if not items:
            raise SourceError(
                f"{len(blocks)} blok parse edildi ama hiçbiri min_stars_today={min_stars} eşiğini geçmedi"
            )
        return items
