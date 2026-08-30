"""Maliyet takibi ve sert tavan.

PROJECT.md §2.3: "Maliyet tavanı serttir. Günlük LLM harcaması $0.20'yi aşarsa
özetleme durur, ham başlıklarla devam edilir. Bu bir öneri değil, kodda olacak."
"""
from __future__ import annotations

from dataclasses import dataclass, field

# claude-haiku-4-5 fiyatlandırması (USD / 1M token)
PRICE_INPUT = 1.00
PRICE_OUTPUT = 5.00
PRICE_CACHE_WRITE = 1.25    # girdi × 1.25
PRICE_CACHE_READ = 0.10     # girdi × 0.10 — sistem promptu cache'lenince buradan okunur

# twitterapi.io: tweet başına 15 kredi, 100.000 kredi = $1 (2026-08-30'da ölçüldü)
TWEET_COST_USD = 15 / 100_000


@dataclass
class Budget:
    """Bir çalıştırmanın maliyetini izler ve tavana çarpınca durdurur."""

    daily_llm_usd: float = 0.20
    daily_twitter_reads: int = 600

    llm_usd: float = 0.0
    tweet_reads: int = 0
    _events: list[str] = field(default_factory=list)

    @classmethod
    def from_config(cls, cfg: dict) -> "Budget":
        b = cfg.get("budget", {})
        return cls(
            daily_llm_usd=float(b.get("daily_llm_usd", 0.20)),
            daily_twitter_reads=int(b.get("daily_twitter_reads", 600)),
        )

    # ---- LLM ----
    @staticmethod
    def estimate_llm_usd(input_tokens: int, output_tokens: int,
                         cached_input_tokens: int = 0) -> float:
        return (
            input_tokens / 1_000_000 * PRICE_INPUT
            + cached_input_tokens / 1_000_000 * PRICE_CACHE_READ
            + output_tokens / 1_000_000 * PRICE_OUTPUT
        )

    def can_afford_llm(self, estimated_usd: float) -> bool:
        """Çağrıdan ÖNCE sorulur. Tavanı aşacaksa False."""
        return (self.llm_usd + estimated_usd) <= self.daily_llm_usd

    def charge_llm(self, input_tokens: int, output_tokens: int,
                   cached_input_tokens: int = 0, cache_write_tokens: int = 0) -> float:
        cost = self.estimate_llm_usd(input_tokens, output_tokens, cached_input_tokens)
        cost += cache_write_tokens / 1_000_000 * PRICE_CACHE_WRITE
        self.llm_usd += cost
        return cost

    @property
    def llm_exhausted(self) -> bool:
        return self.llm_usd >= self.daily_llm_usd

    # ---- Twitter ----
    def can_read_tweets(self, count: int) -> bool:
        return (self.tweet_reads + count) <= self.daily_twitter_reads

    def charge_tweets(self, count: int) -> float:
        self.tweet_reads += count
        return count * TWEET_COST_USD

    @property
    def twitter_usd(self) -> float:
        return self.tweet_reads * TWEET_COST_USD

    # ---- Rapor ----
    def note(self, msg: str) -> None:
        self._events.append(msg)

    @property
    def notes(self) -> list[str]:
        return list(self._events)

    def summary(self) -> str:
        return (
            f"LLM ${self.llm_usd:.4f}/{self.daily_llm_usd:.2f} · "
            f"Twitter {self.tweet_reads}/{self.daily_twitter_reads} okuma "
            f"(${self.twitter_usd:.4f})"
        )
