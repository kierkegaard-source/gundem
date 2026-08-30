"""Tüm kaynakları paralel çalıştırır, veritabanına yazar, terminale tablo basar.

PROJECT.md §2.2: "Kısmi başarı tam başarısızlıktan iyidir. Bir kaynak patlarsa
pipeline durmaz." Her kaynak kendi try/except'inde ve kendi zaman aşımında çalışır.

Kullanım:  uv run python -m pipeline.collect [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections import Counter

import httpx

from pipeline.budget import Budget
from pipeline.config import enabled_sources, load_config
from pipeline.db import connect, record_run, upsert_items
from sources.base import Item, Source
from sources.github_trending import GithubTrending
from sources.hackernews import HackerNews

# Uygulanmış kaynaklar. Faz 2'de bu sözlük büyüyecek.
REGISTRY: dict[str, type[Source]] = {
    "hackernews": HackerNews,
    "github_trending": GithubTrending,
}

SOURCE_TIMEOUT = 45          # saniye — bir kaynak bunu aşarsa atlanır
USER_AGENT = "daily-launch/0.1 (kisisel gunluk ozet; +https://github.com/)"


async def run_source(name: str, src: Source,
                     client: httpx.AsyncClient) -> tuple[str, list[Item], str | None]:
    """Tek kaynağı çalıştırır. Asla istisna sızdırmaz."""
    t0 = time.perf_counter()
    try:
        items = await asyncio.wait_for(src.fetch(client), timeout=SOURCE_TIMEOUT)
        dt = time.perf_counter() - t0
        print(f"  ✓ {name:<18} {len(items):>3} kayıt  ({dt:.1f}s)")
        return name, items, None
    except asyncio.TimeoutError:
        print(f"  ✗ {name:<18} zaman aşımı ({SOURCE_TIMEOUT}s)")
        return name, [], f"zaman aşımı ({SOURCE_TIMEOUT}s)"
    except Exception as exc:
        print(f"  ✗ {name:<18} {type(exc).__name__}: {exc}")
        return name, [], f"{type(exc).__name__}: {exc}"


async def collect(cfg: dict) -> tuple[list[Item], list[str], list[str]]:
    active = enabled_sources(cfg)
    ready = {n: c for n, c in active.items() if n in REGISTRY}
    pending = sorted(set(active) - set(ready))

    print(f"Kaynaklar: {len(ready)} hazır, {len(pending)} beklemede (Faz 2)")
    if pending:
        print(f"  … beklemede: {', '.join(pending)}")
    print()

    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0), follow_redirects=True, limits=limits,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        tasks = [
            run_source(name, REGISTRY[name](conf, cfg), client)
            for name, conf in ready.items()
        ]
        results = await asyncio.gather(*tasks)

    items: list[Item] = []
    failed: list[str] = []
    for name, got, err in results:
        items.extend(got)
        if err:
            failed.append(f"{name}: {err}")
    return items, failed, pending


def print_table(items: list[Item], limit: int = 25) -> None:
    if not items:
        print("\n(hiç kayıt yok)")
        return
    print(f"\n{'kaynak':<16} {'kat':<8} {'ham':>7} {'yaş':>6}  başlık")
    print("-" * 96)
    for it in sorted(items, key=lambda i: (-i.raw_score))[:limit]:
        title = it.title if len(it.title) <= 54 else it.title[:51] + "…"
        print(f"{it.source:<16} {it.category:<8} {it.raw_score:>7.0f} "
              f"{it.age_hours:>5.0f}s  {title}")
    if len(items) > limit:
        print(f"… ve {len(items) - limit} kayıt daha")


def main() -> int:
    ap = argparse.ArgumentParser(description="Kaynakları topla ve veritabanına yaz")
    ap.add_argument("--dry-run", action="store_true", help="veritabanına yazma")
    ap.add_argument("--limit", type=int, default=25, help="tabloda gösterilecek satır")
    args = ap.parse_args()

    cfg = load_config()
    budget = Budget.from_config(cfg)

    t0 = time.perf_counter()
    items, failed, pending = asyncio.run(collect(cfg))
    elapsed = time.perf_counter() - t0

    print_table(items, args.limit)

    by_source = Counter(i.source for i in items)
    by_cat = Counter(i.category for i in items)
    print(f"\nkaynak dağılımı  : {dict(by_source)}")
    print(f"kategori dağılımı: {dict(by_cat)}")

    if args.dry_run:
        print("\n[dry-run] veritabanına yazılmadı")
    else:
        conn = connect()
        new, updated = upsert_items(conn, items)
        record_run(conn, items_raw=len(items), items_kept=len(items),
                   failed_sources=failed, llm_cost_usd=budget.llm_usd,
                   api_cost_usd=budget.twitter_usd)
        total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        conn.close()
        print(f"\nveritabanı: {new} yeni, {updated} güncellendi, toplam {total} kayıt")

    print(f"bütçe    : {budget.summary()}")
    print(f"süre     : {elapsed:.1f}s")
    if failed:
        print(f"\nBAŞARISIZ KAYNAKLAR ({len(failed)}):")
        for f in failed:
            print(f"  - {f}")
    # Kısmi başarı da başarıdır: hiç kayıt yoksa hata koduyla çık.
    return 0 if items else 1


if __name__ == "__main__":
    sys.exit(main())
