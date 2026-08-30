"""Makine çevirisi yedeği — LLM bütçesi yokken sayfa Türkçe kalsın diye.

Bu, LLM özetlemesinin YERİNE GEÇMEZ. Editoryal özet (`summary_tr`), "neden
okumalı" satırı (`why_tr`) ve potansiyel puanı yalnızca Claude'dan gelir.
Burada yapılan iş yalnızca çeviri: başlık ve kaynağın kendi açıklaması.

Kullanılan uç resmi değildir (translate.googleapis.com/translate_a/single,
tarayıcı istemcisi). Anahtarsız ve ücretsiz; her an değişebilir, bu yüzden
her çağrı kendi try/except'inde — düşerse madde İngilizce kalır, pipeline durmaz.

ÜRÜN ADLARI ÇEVRİLMEZ: tek kelimelik başlıklar, GitHub slug'ları ve kısa
adlar atlanır ("Hyperfocus" → "Aşırı Odak" olmasın diye).
"""
from __future__ import annotations

import asyncio
import re

import httpx

ENDPOINT = "https://translate.googleapis.com/translate_a/single"
CONCURRENCY = 5
TIMEOUT = 12

# Platform önekleri: çeviriye girmeden ayrılır, sonra atılır.
_PREFIX = re.compile(r"^(show hn|launch hn|ask hn|tell hn)\s*:\s*", re.I)
# Türkçeye özgü harfler — zaten Türkçe olan metni tekrar çevirmemek için.
_TR_CHARS = re.compile(r"[çğıöşüÇĞİÖŞÜ]")


def needs_title_translation(title: str) -> bool:
    """Başlık bir cümle mi, yoksa ürün adı mı?

    Ürün adları çevrilmemeli. Ölçüt: en az 4 kelime, slug değil, zaten
    Türkçe değil. "Olostep" ve "tt-a1i/archify" atlanır;
    "Planner that turns goals into daily progress" çevrilir.
    """
    t = _PREFIX.sub("", (title or "").strip())
    if not t or "/" in t.split()[0]:
        return False
    if len(t.split()) < 4:
        return False
    if _TR_CHARS.search(t):
        return False
    return True


async def _one(client: httpx.AsyncClient, text: str, sem: asyncio.Semaphore) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    async with sem:
        try:
            r = await client.get(ENDPOINT, timeout=TIMEOUT,
                                 params={"client": "gtx", "sl": "auto", "tl": "tr",
                                         "dt": "t", "q": text},
                                 headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            out = "".join(seg[0] for seg in r.json()[0] if seg and seg[0])
        except Exception:
            return None                     # çeviri opsiyoneldir
    out = out.strip()
    return out if out and out.lower() != text.lower() else None


async def translate_many(texts: list[str]) -> list[str | None]:
    """Sırayı koruyarak çevirir. Düşen madde None döner."""
    if not texts:
        return []
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        return list(await asyncio.gather(*(_one(client, t, sem) for t in texts)))


def strip_prefix(title: str) -> str:
    return _PREFIX.sub("", (title or "").strip())
