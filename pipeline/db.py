"""SQLite şeması ve yazma işlemleri. Şema PROJECT.md §5'ten birebir."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pipeline.dedupe import Cluster
from sources.base import Item

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "digest.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  url_hash    TEXT PRIMARY KEY,
  title       TEXT NOT NULL,
  url         TEXT NOT NULL,
  category    TEXT NOT NULL,
  sources     TEXT NOT NULL,
  score       REAL NOT NULL,
  summary_tr  TEXT,
  why_tr      TEXT,
  raw_text    TEXT,           -- kaynağın kendi açıklaması; özet yoksa yedek metin
  published_at TEXT NOT NULL,
  first_seen  TEXT NOT NULL,
  digest_date TEXT
);
CREATE INDEX IF NOT EXISTS idx_digest_date ON items(digest_date);

CREATE TABLE IF NOT EXISTS item_aliases (
  alias_hash TEXT PRIMARY KEY,
  url_hash   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alias_url ON item_aliases(url_hash);

CREATE TABLE IF NOT EXISTS runs (
  run_at        TEXT PRIMARY KEY,
  items_raw     INTEGER,
  items_kept    INTEGER,
  failed_sources TEXT,
  llm_cost_usd  REAL,
  api_cost_usd  REAL
);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    # Mevcut veritabanları için basit göç: eksik sütunu ekle.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
    if "raw_text" not in cols:
        conn.execute("ALTER TABLE items ADD COLUMN raw_text TEXT")
        conn.commit()
    return conn


def upsert_items(conn: sqlite3.Connection, items: list[Item]) -> tuple[int, int]:
    """Item'ları yazar. Var olan url_hash için `sources` listesi birleştirilir.

    Döner: (yeni kayıt, güncellenen kayıt)
    NOT: buradaki `score` ham metriktir. Faz 3'te skorlama formülü bunun üzerine yazacak.
    """
    now = datetime.now(timezone.utc).isoformat()
    new = updated = 0
    for it in items:
        row = conn.execute(
            "SELECT sources, score FROM items WHERE url_hash = ?", (it.url_hash,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO items (url_hash, title, url, category, sources, score,"
                " published_at, first_seen, digest_date) VALUES (?,?,?,?,?,?,?,?,NULL)",
                (it.url_hash, it.title, it.url, it.category, json.dumps([it.source]),
                 it.raw_score, it.published_at.isoformat(), now),
            )
            new += 1
        else:
            srcs = json.loads(row["sources"])
            if it.source not in srcs:
                srcs.append(it.source)
            conn.execute(
                "UPDATE items SET sources = ?, score = ? WHERE url_hash = ?",
                (json.dumps(srcs), max(row["score"], it.raw_score), it.url_hash),
            )
            updated += 1
    conn.commit()
    return new, updated


def record_run(conn: sqlite3.Connection, *, items_raw: int, items_kept: int,
               failed_sources: list[str], llm_cost_usd: float = 0.0,
               api_cost_usd: float = 0.0) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO runs (run_at, items_raw, items_kept, failed_sources,"
        " llm_cost_usd, api_cost_usd) VALUES (?,?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), items_raw, items_kept,
         json.dumps(failed_sources), llm_cost_usd, api_cost_usd),
    )
    conn.commit()


def published_hashes(conn: sqlite3.Connection, before: str | None = None) -> set[str]:
    """ÖNCEKİ sayılarda yayınlanmış maddelerin hash'leri.

    Günlük gazete aynı maddeyi iki kez basmamalı. Bugünün tarihi hariç tutulur —
    yoksa collect.py aynı gün ikinci kez çalıştığında sayı boş çıkar.
    Kümedeki tüm üye hash'leri de dahil edilir (item_aliases).
    """
    before = before or datetime.now(timezone.utc).date().isoformat()
    rows = conn.execute(
        "SELECT i.url_hash, a.alias_hash FROM items i "
        "LEFT JOIN item_aliases a ON a.url_hash = i.url_hash "
        "WHERE i.digest_date IS NOT NULL AND i.digest_date < ?", (before,)).fetchall()
    out: set[str] = set()
    for r in rows:
        out.add(r[0])
        if r[1]:
            out.add(r[1])
    return out


def mark_digest(conn: sqlite3.Connection, clusters: list[Cluster], digest_date: str) -> None:
    """Sayıya giren maddeleri tarihle işaretler. sitegen/build.py bunları okur.

    İDEMPOTENT: aynı gün ikinci kez çalıştırıldığında o günün işaretleri önce
    temizlenir. Yoksa maddeler birikiyor — elle tetiklenen ikinci koşudan sonra
    sayfada 60 yerine 72 madde çıkmıştı.
    """
    conn.execute("UPDATE items SET digest_date = NULL WHERE digest_date = ?", (digest_date,))
    for c in clusters:
        conn.execute("UPDATE items SET digest_date = ? WHERE url_hash = ?",
                     (digest_date, c.lead.url_hash))
    conn.commit()


def digest_items(conn: sqlite3.Connection, digest_date: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM items WHERE digest_date = ? ORDER BY score DESC", (digest_date,)).fetchall()


def digest_dates(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT digest_date FROM items WHERE digest_date IS NOT NULL "
        "ORDER BY digest_date DESC")]


def last_run(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM runs ORDER BY run_at DESC LIMIT 1").fetchone()


def upsert_clusters(conn: sqlite3.Connection, clusters: list[Cluster]) -> tuple[int, int]:
    """Tekilleştirilmiş ve skorlanmış kümeleri yazar.

    Bir küme birden fazla üye taşır (aynı ürün, farklı kaynaklar). Temsilcinin
    url_hash'i birincil anahtar olur; kümedeki TÜM üyelerin hash'leri de aynı
    satıra işaret etsin diye `item_aliases` tablosuna yazılır — böylece yarın
    aynı ürün başka bir kaynaktan gelirse tekrar basılmaz.
    """
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS item_aliases (
        alias_hash TEXT PRIMARY KEY,
        url_hash   TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_alias_url ON item_aliases(url_hash);
    """)
    now = datetime.now(timezone.utc).isoformat()
    new = updated = 0
    for c in clusters:
        lead = c.lead
        row = conn.execute("SELECT sources FROM items WHERE url_hash = ?",
                           (lead.url_hash,)).fetchone()
        srcs = json.dumps(c.sources)
        if row is None:
            conn.execute(
                "INSERT INTO items (url_hash, title, url, category, sources, score,"
                " raw_text, published_at, first_seen, digest_date)"
                " VALUES (?,?,?,?,?,?,?,?,?,NULL)",
                (lead.url_hash, c.title, c.url, c.category, srcs, c.score,
                 c.raw_text, c.published_at.isoformat(), now))
            new += 1
        else:
            merged = json.loads(row["sources"])
            for s_ in c.sources:
                if s_ not in merged:
                    merged.append(s_)
            conn.execute("UPDATE items SET sources = ?, score = ?, title = ?, raw_text = ? "
                         "WHERE url_hash = ?",
                         (json.dumps(merged), c.score, c.title, c.raw_text, lead.url_hash))
            updated += 1
        for m in c.members:
            conn.execute("INSERT OR REPLACE INTO item_aliases (alias_hash, url_hash) VALUES (?,?)",
                         (m.url_hash, lead.url_hash))
    conn.commit()
    return new, updated
