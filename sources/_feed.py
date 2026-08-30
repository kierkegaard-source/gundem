"""RSS 2.0 / Atom ayrıştırıcı — stdlib, ek bağımlılık yok.

Faz 0'da 25 feed test edildi; ikisi Atom (`<entry>`), gerisi RSS (`<item>`),
biri yanlış Content-Type (`text/html`) döndürüyor. Bu yüzden ayrıştırma
Content-Type'a değil gövdeye bakar ve etiket adları namespace'ten arındırılır.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

_TAGS = re.compile(r"<[^>]+>")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _text(el) -> str:
    if el is None:
        return ""
    raw = "".join(el.itertext())
    return html.unescape(_TAGS.sub(" ", raw)).strip()


def parse_date(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:                                   # RFC 2822 — <pubDate>
        return parsedate_to_datetime(raw).astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    try:                                   # ISO 8601 — <updated>, <published>
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _salvage(body: bytes):
    """Kapanış etiketinden sonrasını atarak bozuk gövdeyi kurtarmayı dener."""
    for close in (b"</feed>", b"</rss>", b"</RDF>"):
        idx = body.rfind(close)
        if idx != -1:
            try:
                return ET.fromstring(body[: idx + len(close)])
            except ET.ParseError:
                continue
    return None


def parse_feed(body: bytes) -> list[dict]:
    """Feed gövdesinden kayıt listesi çıkarır.

    Her kayıt: {title, link, published, summary, author}
    Bozuk tek kayıt tüm feed'i düşürmez — atlanır.
    """
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        # Faz 2: unrealengine.com/en-US/rss gövdenin sonuna artık veri ekliyor
        # ("junk after document element"). Kapanış etiketinden sonrasını atıp
        # tekrar denenir — kısmi başarı tam başarısızlıktan iyidir.
        root = _salvage(body)
        if root is None:
            raise ValueError(f"XML ayrıştırılamadı: {exc}") from exc

    out: list[dict] = []

    out: list[dict] = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        rec = {"title": "", "link": "", "published": None, "summary": "", "author": None}
        for child in el:
            name = _local(child.tag)
            if name == "title" and not rec["title"]:
                rec["title"] = _text(child)
            elif name == "link" and not rec["link"]:
                # RSS: <link>url</link>  |  Atom: <link href="url" rel="alternate"/>
                rec["link"] = (child.get("href") or "").strip() or _text(child)
            elif name in ("pubdate", "published", "updated", "date") and rec["published"] is None:
                rec["published"] = parse_date(_text(child))
            elif name in ("description", "summary", "content", "encoded") and not rec["summary"]:
                rec["summary"] = _text(child)[:600]
            elif name in ("creator", "author") and not rec["author"]:
                rec["author"] = _text(child)[:80] or None
        if rec["title"] and rec["link"]:
            out.append(rec)
    return out
