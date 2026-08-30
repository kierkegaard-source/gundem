"""Statik sayfaları üretir: bugünkü sayı, günlük arşiv kopyası, arşiv listesi.

Kullanım:  uv run python -m sitegen.build [--date YYYY-MM-DD] [--rebuild-all]

PROJECT.md §8: gazete hissi, tek sütun, harici font yok, JS yok, < 100KB.
CSS sayfaya gömülüyor — ayrı dosya bir HTTP isteği daha demek ve toplam
boyut zaten 100KB'ın çok altında.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from pipeline.db import connect, digest_dates, digest_items, last_run

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
TEMPLATES = Path(__file__).resolve().parent / "templates"
STATIC = Path(__file__).resolve().parent / "static"

# Kategori sırası ve Türkçe başlıklar. PROJECT.md §1'deki dört ana kategori önce.
SECTIONS = [
    ("dev", "Geliştirici Araçları"),
    ("apps", "Yeni Uygulamalar"),
    ("gamedev", "Indie Oyun"),
    ("design", "Tasarım"),
    ("startup", "Girişim ve Yatırım"),
    ("tr", "Türkiye"),
]

SOURCE_LABEL = {
    "hackernews": "HN", "github_trending": "GitHub", "producthunt": "Product Hunt",
    "itchio": "itch.io", "steam": "Steam", "bluesky": "Bluesky",
    "twitter": "X", "rss": "RSS", "reddit": "Reddit",
}

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
         "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def tr_date(iso: str, with_weekday: bool = True) -> str:
    d = date.fromisoformat(iso)
    out = f"{d.day} {AYLAR[d.month - 1]} {d.year}"
    return f"{GUNLER[d.weekday()]}, {out}" if with_weekday else out


def tr_short(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {AYLAR[d.month - 1]}"


def _hours_ago(published_at: str, ref: datetime) -> str:
    try:
        dt = datetime.fromisoformat(published_at)
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    h = int((ref - dt).total_seconds() // 3600)
    if h < 1:
        return "az önce"
    if h < 24:
        return f"{h} saat önce"
    d = h // 24
    return "dün" if d == 1 else f"{d} gün önce"


def build_notices(run: sqlite3.Row | None) -> list[str]:
    """Sayfanın üstündeki uyarı bandı. PROJECT.md §2.2: eksik kaynak görünsün."""
    if not run:
        return []
    notices: list[str] = []
    try:
        failed = json.loads(run["failed_sources"] or "[]")
    except (TypeError, json.JSONDecodeError):
        failed = []
    for f in failed:
        name = f.split(":")[0].strip()
        label = SOURCE_LABEL.get(name, name)
        if "(kısmi)" in f:
            notices.append(f"{label} kaynağı kısmen alınabildi.")
        else:
            notices.append(f"{label} kaynağı bugün alınamadı.")
    return notices


def collect_day(conn: sqlite3.Connection, day: str, run: sqlite3.Row | None) -> dict:
    rows = digest_items(conn, day)
    ref = datetime.now(timezone.utc)
    by_cat: dict[str, list[dict]] = {}
    sources_seen: set[str] = set()

    for r in rows:
        srcs = json.loads(r["sources"])
        sources_seen.update(srcs)
        by_cat.setdefault(r["category"], []).append({
            "title": r["title"],
            "url": r["url"],
            "why": r["why_tr"],
            "summary": r["summary_tr"],
            "badges": [SOURCE_LABEL.get(s, s) for s in srcs],
            "published_iso": r["published_at"],
            "published_human": _hours_ago(r["published_at"], ref),
        })

    # NOT: anahtar "items" OLAMAZ — Jinja `sec.items`i dict.items metoduna
    # çözümlüyor ve `|length` patlıyor. "entries" kullanılıyor.
    sections = [{"key": k, "label": label, "entries": by_cat[k]}
                for k, label in SECTIONS if by_cat.get(k)]
    # Config'de olmayan bir kategori çıkarsa yine de göster.
    for k, items in by_cat.items():
        if k not in {s["key"] for s in sections}:
            sections.append({"key": k, "label": k.title(), "entries": items})

    notices = build_notices(run)
    if rows and not any(r["summary_tr"] for r in rows):
        notices.append("Özetleme yapılamadı — maddeler ham başlıklarıyla listelendi.")

    return {
        "date": day,
        "date_long": tr_date(day),
        "total": len(rows),
        "source_count": len(sources_seen),
        "sections": sections,
        "notices": notices,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Statik sayfaları üret")
    ap.add_argument("--date", help="YYYY-MM-DD (varsayılan: en son sayı)")
    ap.add_argument("--rebuild-all", action="store_true",
                    help="tüm arşiv günlerini yeniden üret")
    args = ap.parse_args()

    conn = connect()
    all_days = digest_dates(conn)
    if not all_days:
        print("Veritabanında yayınlanmış sayı yok. Önce: python -m pipeline.collect")
        return 1

    run = last_run(conn)
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    env = Environment(loader=FileSystemLoader(TEMPLATES),
                      autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True)
    generated = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    DOCS.mkdir(parents=True, exist_ok=True)

    latest = all_days[0]
    targets = all_days if args.rebuild_all else [args.date or latest]
    day_tpl = env.get_template("day.html")
    written = []

    for day in targets:
        if day not in all_days:
            print(f"'{day}' için sayı yok. Mevcut: {', '.join(all_days[:5])}")
            return 1
        ctx = collect_day(conn, day, run if day == latest else None)
        idx = all_days.index(day)
        # all_days azalan sıralı: sonraki eleman daha ESKİ gün.
        prev_day = all_days[idx + 1] if idx + 1 < len(all_days) else None
        next_day = all_days[idx - 1] if idx > 0 else None
        html = day_tpl.render(
            css=css, generated_at=generated,
            prev_date=prev_day, prev_label=tr_short(prev_day) if prev_day else None,
            next_date=next_day, next_label=tr_short(next_day) if next_day else None,
            **ctx)
        (DOCS / f"{day}.html").write_text(html, encoding="utf-8")
        written.append(f"{day}.html ({len(html) // 1024} KB, {ctx['total']} madde)")
        if day == latest:
            (DOCS / "index.html").write_text(html, encoding="utf-8")

    counts = {d: len(digest_items(conn, d)) for d in all_days}
    archive = env.get_template("archive.html").render(
        css=css, generated_at=generated,
        days=[{"date": d, "label": tr_date(d), "count": counts[d]} for d in all_days])
    (DOCS / "arsiv.html").write_text(archive, encoding="utf-8")
    (DOCS / ".nojekyll").write_text("")     # GitHub Pages Jekyll'i atlasın
    conn.close()

    print("Üretildi:")
    for w in written:
        print(f"  docs/{w}")
    print(f"  docs/index.html (en son sayı: {latest})")
    print(f"  docs/arsiv.html ({len(all_days)} gün)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
