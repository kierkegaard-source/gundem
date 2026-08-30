"""Tüm kaynakları paralel çalıştırır, veritabanına yazar, terminale tablo basar.

PROJECT.md §2.2: "Kısmi başarı tam başarısızlıktan iyidir. Bir kaynak patlarsa
pipeline durmaz." Her kaynak kendi try/except'inde ve kendi zaman aşımında çalışır.

Kullanım:  uv run python -m pipeline.collect [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import sys
import time
from collections import Counter

import httpx

from pipeline.budget import Budget
from pipeline.config import enabled_sources, load_config
from pipeline.db import (connect, mark_digest, published_hashes, record_run,
                         upsert_clusters)
from pipeline.dedupe import Cluster, dedupe
from pipeline.score import filter_clusters, score_clusters
from pipeline.summarize import (OPPORTUNITY_LABEL, alerts, drop_low_signal,
                                summarize)
from pipeline.translate import needs_title_translation, strip_prefix, translate_many
from sources.base import Item, Source
from sources.bluesky import Bluesky
from sources.github_trending import GithubTrending
from sources.hackernews import HackerNews
from sources.itchio import Itchio
from sources.producthunt import ProductHunt
from sources.reddit import Reddit
from sources.rss import Rss
from sources.steam import Steam
from sources.twitter import Twitter

REGISTRY: dict[str, type[Source]] = {
    "hackernews": HackerNews,
    "github_trending": GithubTrending,
    "producthunt": ProductHunt,
    "itchio": Itchio,
    "steam": Steam,
    "rss": Rss,
    "bluesky": Bluesky,
    "twitter": Twitter,
    "reddit": Reddit,          # config'de kapalı — bkz. sources/reddit.py
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
        partial = ""
        if src.failed_feeds:
            partial = f"  [{len(src.failed_feeds)} alt-kaynak düştü]"
        print(f"  ✓ {name:<18} {len(items):>3} kayıt  ({dt:.1f}s){partial}")
        return name, items, None
    except asyncio.TimeoutError:
        print(f"  ✗ {name:<18} zaman aşımı ({SOURCE_TIMEOUT}s)")
        return name, [], f"zaman aşımı ({SOURCE_TIMEOUT}s)"
    except Exception as exc:
        print(f"  ✗ {name:<18} {type(exc).__name__}: {exc}")
        return name, [], f"{type(exc).__name__}: {exc}"


async def collect(cfg: dict, budget=None, only: set[str] | None = None,
                  skip: set[str] | None = None) -> tuple[list[Item], list[str], list[str]]:
    active = enabled_sources(cfg)
    if only:
        active = {k: v for k, v in active.items() if k in only}
    if skip:
        active = {k: v for k, v in active.items() if k not in skip}
    ready = {n: c for n, c in active.items() if n in REGISTRY}
    pending = sorted(set(active) - set(ready))

    print(f"Kaynaklar: {len(ready)} hazır" + (f", {len(pending)} beklemede" if pending else ""))
    if pending:
        print(f"  … beklemede: {', '.join(pending)}")
    print()

    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0), follow_redirects=True, limits=limits,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        instances = {}
        for name, conf in ready.items():
            src = REGISTRY[name](conf, cfg)
            src.budget = budget
            instances[name] = src
        results = await asyncio.gather(
            *(run_source(n, s_, client) for n, s_ in instances.items())
        )

    items: list[Item] = []
    failed: list[str] = []
    for name, got, err in results:
        items.extend(got)
        if err:
            failed.append(f"{name}: {err}")
        else:
            sub = instances[name].failed_feeds
            if sub:
                failed.append(f"{name} (kısmi): {', '.join(sub[:6])}"
                              + (f" +{len(sub)-6}" if len(sub) > 6 else ""))
    return items, failed, pending


def print_digest(clusters: list[Cluster], limit: int = 30) -> None:
    if not clusters:
        print("\n(hiç kayıt yok)")
        return
    print(f"\n{'skor':>6} {'':<4}{'kat':<8} {'yaş':>5}  {'kaynaklar':<20} başlık")
    print("-" * 104)
    for c in clusters[:limit]:
        age = (c.published_at and c.lead.age_hours) or 0
        badge = "+".join(c.sources)
        if len(badge) > 19:
            badge = badge[:18] + "…"
        star = "★" if c.multi_source else " "
        sig = f"s{c.signal}" if c.signal else " ·"
        title = c.title if len(c.title) <= 44 else c.title[:41] + "…"
        print(f"{c.score:>6.3f} {star}{sig:<3}{c.category:<8} {age:>4.0f}s  {badge:<20} {title}")
        if c.why_tr:
            print(f"          ↳ {c.why_tr}")
    if len(clusters) > limit:
        print(f"… ve {len(clusters) - limit} madde daha")


def main() -> int:
    ap = argparse.ArgumentParser(description="Kaynakları topla ve veritabanına yaz")
    ap.add_argument("--dry-run", action="store_true", help="veritabanına yazma")
    ap.add_argument("--limit", type=int, default=30, help="tabloda gösterilecek satır")
    ap.add_argument("--only", help="sadece bu kaynaklar (virgülle)")
    ap.add_argument("--skip", help="bu kaynakları atla (virgülle) — ör. maliyetli twitter")
    ap.add_argument("--no-llm", action="store_true", help="özetlemeyi atla (maliyetsiz test)")
    ap.add_argument("--no-translate", action="store_true", help="makine çevirisini atla")
    args = ap.parse_args()

    cfg = load_config()
    budget = Budget.from_config(cfg)

    t0 = time.perf_counter()
    only = {x.strip() for x in args.only.split(",")} if args.only else None
    skip = {x.strip() for x in args.skip.split(",")} if args.skip else None
    items, failed, pending = asyncio.run(collect(cfg, budget, only, skip))
    elapsed = time.perf_counter() - t0

    # ---- dedupe -> score -> filter ----
    clusters = dedupe(items)
    clusters = score_clusters(clusters, cfg)

    conn = None if args.dry_run else connect()
    already = published_hashes(conn) if conn else set()
    oversample = float(cfg.get("filters", {}).get("summarize_oversample", 1.5))
    # Kotadan fazla aday: düşük sinyalliler elenince bölümler boş kalmasın.
    candidates = filter_clusters(clusters, cfg, already, oversample=oversample)

    multi = sum(1 for c in clusters if c.multi_source)
    print(f"\ntoplanan {len(items)} kayıt → {len(clusters)} tekil madde "
          f"({len(items) - len(clusters)} mükerrer birleşti, {multi}'i çoklu kaynak) "
          f"→ {len(candidates)} aday özetlemeye gitti")

    # ---- özetleme ----
    if args.no_llm:
        print("\n[--no-llm] özetleme atlandı, ham başlıklar kullanılıyor")
        kept, dropped = filter_clusters(candidates, cfg, already), []
    else:
        rep = summarize(candidates, cfg, budget)
        survivors, dropped = drop_low_signal(candidates, cfg)
        # Eleme sonrası gerçek tavan. LLM kategoriyi düzeltmiş olabilir,
        # bu yüzden kota ikinci geçişte yeniden hesaplanıyor.
        kept = filter_clusters(survivors, cfg, already)
        print(f"\nözetleme: {rep['batches']} batch, {rep['summarized']} madde özetlendi"
              + (f", {rep['failed_batches']} batch başarısız" if rep["failed_batches"] else "")
              + (f", {rep['skipped_budget']} madde bütçe nedeniyle atlandı" if rep["skipped_budget"] else ""))
        if dropped:
            print(f"düşük sinyal ({cfg['filters'].get('min_signal', 2)} altı) elenen: {len(dropped)} madde")
        hot = alerts(kept)
        if hot:
            print(f"\n★ FIRSAT RADARI — {len(hot)} madde:")
            for c in hot:
                tur = OPPORTUNITY_LABEL.get(c.opportunity or "", "")
                print(f"   [{c.potential}/5] {tur:<14} {c.title[:48]}")
                if c.potential_note:
                    print(f"             → {c.potential_note}")
                print(f"             {c.url}")
        elif any(c.signal for c in kept):
            print("\n★ FIRSAT RADARI — bugün eşiği geçen madde yok.")
        if rep["degraded"]:
            print("UYARI: sayı eksik özetle üretildi — sayfaya uyarı bandı konacak")
        print(f"sayıya giren: {len(kept)} madde")

    # ---- makine çevirisi yedeği ----
    # LLM özeti/başlığı olmayan maddeler İngilizce kalmasın. Editoryal özetin
    # yerine geçmez, yalnızca çeviridir; ücretsiz ve anahtarsız.
    if not args.no_translate:
        pending_t = [c for c in kept
                     if not c.title_tr and needs_title_translation(c.lead.title)]
        pending_b = [c for c in kept if not c.summary_tr and c.raw_text
                     and c.raw_text.strip().lower() != c.lead.title.strip().lower()]
        if pending_t or pending_b:
            texts = ([strip_prefix(c.lead.title) for c in pending_t]
                     + [c.raw_text[:400] for c in pending_b])
            out = asyncio.run(translate_many(texts))
            n = len(pending_t)
            for c, tr in zip(pending_t, out[:n]):
                c.title_mt = tr
            for c, tr in zip(pending_b, out[n:]):
                c.body_mt = tr
            done_t = sum(1 for c in pending_t if c.title_mt)
            done_b = sum(1 for c in pending_b if c.body_mt)
            print(f"makine çevirisi: {done_t}/{len(pending_t)} başlık, "
                  f"{done_b}/{len(pending_b)} açıklama")

    print_digest(kept, args.limit)

    by_source = Counter(i.source for i in items)
    by_cat = Counter(c.category for c in kept)
    print(f"\nkaynak dağılımı (ham): {dict(by_source)}")
    print(f"sayıdaki kategoriler : {dict(by_cat)}")

    if args.dry_run:
        print("\n[dry-run] veritabanına yazılmadı")
    else:
        new, updated = upsert_clusters(conn, clusters)
        # Özetler yalnızca sayıya giren maddeler için üretildi; onları ayrıca yaz.
        for c in kept:
            if c.summary_tr or c.title_tr or c.title_mt or c.body_mt:
                conn.execute(
                    "UPDATE items SET title_tr = ?, title_mt = ?, body_mt = ?, "
                    "summary_tr = ?, why_tr = ?, category = ?, potential = ?, "
                    "opportunity = ?, potential_note = ? WHERE url_hash = ?",
                    (c.title_tr, c.title_mt, c.body_mt, c.summary_tr, c.why_tr,
                     c.category, c.potential, c.opportunity, c.potential_note,
                     c.lead.url_hash))
        conn.commit()
        today = datetime.now(timezone.utc).date().isoformat()
        mark_digest(conn, kept, today)
        record_run(conn, items_raw=len(items), items_kept=len(kept),
                   failed_sources=failed, llm_cost_usd=budget.llm_usd,
                   api_cost_usd=budget.twitter_usd,
                   llm_note=" | ".join(budget.notes) or None)
        total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        conn.close()
        print(f"\nveritabanı: {new} yeni, {updated} güncellendi, toplam {total} kayıt")

    print(f"bütçe    : {budget.summary()}")
    print(f"süre     : {elapsed:.1f}s")
    for note in budget.notes:
        print(f"not      : {note}")
    if failed:
        print(f"\nBAŞARISIZ / KISMİ KAYNAKLAR ({len(failed)}):")
        for f in failed:
            print(f"  - {f}")
    # Kısmi başarı da başarıdır: hiç kayıt yoksa hata koduyla çık.
    return 0 if items else 1


if __name__ == "__main__":
    sys.exit(main())
