"""Faz 4/6 testleri: özetleme sözleşmesi, Türkçe başlık, radar eşiği.

API çağrısı yapılmaz — Anthropic istemcisi taklit edilir. Amaç şemanın,
alan eşlemesinin ve eşiklerin doğruluğunu doğrulamak.
"""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from pipeline.budget import Budget
from pipeline.dedupe import Cluster
from pipeline.summarize import (POTENTIAL_ALERT, alerts, drop_low_signal,
                                summarize)
from sources.base import Item

CFG = {"budget": {"daily_llm_usd": 1.0}, "filters": {"min_signal": 2}}


def cluster(title, i=0):
    return Cluster(members=[Item(
        title=title, url=f"https://x.dev/{i}", source="producthunt", category="dev",
        raw_score=10.0, published_at=datetime.now(timezone.utc), raw_text=title)])


class FakeMessages:
    """messages.create / count_tokens taklidi."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def count_tokens(self, **kw):
        return SimpleNamespace(input_tokens=800)

    def create(self, **kw):
        self.calls += 1
        # Şemanın gerçekten gönderildiğini doğrula
        assert kw["output_config"]["format"]["type"] == "json_schema"
        payload = json.dumps({"items": self.rows}, ensure_ascii=False)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=payload)],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=800, output_tokens=400,
                                  cache_read_input_tokens=0))


@pytest.fixture
def fake(monkeypatch):
    def install(rows):
        holder = {}

        def factory(api_key=None):
            holder["msgs"] = FakeMessages(rows)
            return SimpleNamespace(messages=holder["msgs"])

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setattr("pipeline.summarize.Anthropic", factory)
        return holder
    return install


def test_turkce_baslik_uygulaniyor_urun_adi_korunuyor(fake):
    fake([{"id": 0, "title_tr": "Olostep", "summary": "İki cümlelik özet. Devamı.",
           "why": "Veri hazırlığını hızlandırıyor", "category": "dev",
           "signal": 4, "potential": 3, "potential_note": ""}])
    cs = [cluster("Olostep")]
    summarize(cs, CFG, Budget.from_config(CFG))
    assert cs[0].title_tr == "Olostep"
    assert cs[0].title == "Olostep"          # Cluster.title Türkçesini döndürür
    assert cs[0].summary_tr.startswith("İki cümlelik")


def test_haber_basligi_turkceye_ceviriliyor(fake):
    fake([{"id": 0, "title_tr": "Kuantum bilgisayar yarışına bakış",
           "summary": "Özet. İkinci cümle.", "why": "Sektör yönü değişiyor",
           "category": "startup", "signal": 3, "potential": 3, "potential_note": ""}])
    cs = [cluster("A look at the race to build quantum computers")]
    summarize(cs, CFG, Budget.from_config(CFG))
    assert cs[0].title == "Kuantum bilgisayar yarışına bakış"


def test_potansiyel_notu_yalnizca_esigin_ustunde_tutuluyor(fake):
    fake([
        {"id": 0, "title_tr": "Yüksek", "summary": "a. b.", "why": "c",
         "category": "dev", "signal": 4, "potential": 5, "potential_note": "Kategori açıyor"},
        {"id": 1, "title_tr": "Düşük", "summary": "a. b.", "why": "c",
         "category": "dev", "signal": 3, "potential": 2, "potential_note": "olmamalı"},
    ])
    cs = [cluster("Yuksek", 0), cluster("Dusuk", 1)]
    summarize(cs, CFG, Budget.from_config(CFG))
    assert cs[0].potential_note == "Kategori açıyor"
    assert cs[1].potential_note is None      # eşik altında not tutulmaz


def test_radar_esigi_ve_siralamasi(fake):
    rows, cs = [], []
    for i, pot in enumerate([2, 5, 4, 3, 4]):
        rows.append({"id": i, "title_tr": f"Madde {i}", "summary": "a. b.", "why": "c",
                     "category": "dev", "signal": 3, "potential": pot,
                     "potential_note": "not" if pot >= 4 else ""})
        cs.append(cluster(f"Madde {i}", i))
    fake(rows)
    summarize(cs, CFG, Budget.from_config(CFG))
    hot = alerts(cs)
    assert [c.potential for c in hot] == [5, 4, 4]        # eşik altı yok, azalan sıra
    assert all(c.potential >= POTENTIAL_ALERT for c in hot)


def test_bozuk_yanit_pipeline_i_durdurmuyor(fake, monkeypatch):
    def factory(api_key=None):
        class Bad:
            def count_tokens(self, **kw): return SimpleNamespace(input_tokens=500)
            def create(self, **kw): raise RuntimeError("500 sunucu hatası")
        return SimpleNamespace(messages=Bad())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("pipeline.summarize.Anthropic", factory)
    cs = [cluster("Bir ürün")]
    b = Budget.from_config(CFG)
    rep = summarize(cs, CFG, b)
    assert rep["failed_batches"] == 1 and rep["degraded"] is True
    assert cs[0].summary_tr is None and cs[0].title == "Bir ürün"   # ham başlığa düşer
    assert any("özetlenemedi" in n for n in b.notes)


def test_dusuk_sinyal_eleniyor_ozetlenmemis_kaliyor(fake):
    fake([{"id": 0, "title_tr": "Gürültü", "summary": "a. b.", "why": "c",
           "category": "dev", "signal": 1, "potential": 1, "potential_note": ""}])
    cs = [cluster("Gurultu", 0), cluster("Ozetlenmemis", 1)]
    summarize(cs[:1], CFG, Budget.from_config(CFG))
    kept, dropped = drop_low_signal(cs, CFG)
    assert [c.title for c in dropped] == ["Gürültü"]
    assert [c.title for c in kept] == ["Ozetlenmemis"]   # signal=None elenmez
