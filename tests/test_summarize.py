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
from pipeline.summarize import (MIN_SIGNAL_FOR_ALERT, OPPORTUNITY_LABEL,
                                POTENTIAL_ALERT, alerts, drop_low_signal,
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
           "signal": 4, "potential": 3, "opportunity": "yok", "potential_note": ""}])
    cs = [cluster("Olostep")]
    summarize(cs, CFG, Budget.from_config(CFG))
    assert cs[0].title_tr == "Olostep"
    assert cs[0].title == "Olostep"          # Cluster.title Türkçesini döndürür
    assert cs[0].summary_tr.startswith("İki cümlelik")


def test_haber_basligi_turkceye_ceviriliyor(fake):
    fake([{"id": 0, "title_tr": "Kuantum bilgisayar yarışına bakış",
           "summary": "Özet. İkinci cümle.", "why": "Sektör yönü değişiyor",
           "category": "startup", "signal": 3, "potential": 3, "opportunity": "yok", "potential_note": ""}])
    cs = [cluster("A look at the race to build quantum computers")]
    summarize(cs, CFG, Budget.from_config(CFG))
    assert cs[0].title == "Kuantum bilgisayar yarışına bakış"


def test_potansiyel_notu_yalnizca_esigin_ustunde_tutuluyor(fake):
    fake([
        {"id": 0, "title_tr": "Yüksek", "summary": "a. b.", "why": "c",
         "category": "dev", "signal": 4, "potential": 5, "opportunity": "ekosistem", "potential_note": "Kategori açıyor"},
        {"id": 1, "title_tr": "Düşük", "summary": "a. b.", "why": "c",
         "category": "dev", "signal": 3, "potential": 2, "opportunity": "yok", "potential_note": "olmamalı"},
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
                     "opportunity": "bosluk" if pot >= 4 else "yok",
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
           "category": "dev", "signal": 1, "potential": 1, "opportunity": "yok", "potential_note": ""}])
    cs = [cluster("Gurultu", 0), cluster("Ozetlenmemis", 1)]
    summarize(cs[:1], CFG, Budget.from_config(CFG))
    kept, dropped = drop_low_signal(cs, CFG)
    assert [c.title for c in dropped] == ["Gürültü"]
    assert [c.title for c in kept] == ["Ozetlenmemis"]   # signal=None elenmez


# ---------- makine çevirisi yedeği ----------

def test_urun_adlari_cevrilmiyor_cumleler_ceviriliyor():
    from pipeline.translate import needs_title_translation as n
    assert not n("Olostep")                       # tek kelime ürün adı
    assert not n("Hyperfocus")
    assert not n("tt-a1i/archify")                # GitHub slug
    assert not n("Kuantum yarışına kısa bir bakış")  # zaten Türkçe
    assert n("A look at the race to build quantum computers")
    assert n("Show HN: Bolnee-Chat Self Hosted Chatbot Integration")


def test_platform_oneki_ayikaniyor():
    from pipeline.translate import strip_prefix
    assert strip_prefix("Show HN: Bir şey") == "Bir şey"
    assert strip_prefix("Launch HN: Başka şey") == "Başka şey"
    assert strip_prefix("Normal başlık") == "Normal başlık"


def test_cluster_baslik_onceligi():
    c = cluster("Original Title")
    assert c.title == "Original Title"
    c.title_mt = "Makine Çevirisi"
    assert c.title == "Makine Çevirisi"
    c.title_tr = "LLM Çevirisi"
    assert c.title == "LLM Çevirisi"          # LLM makine çevirisini ezer


# ---------- ticari fırsat radarı ----------

def test_firsat_turu_esik_altinda_tutulmuyor(fake):
    fake([
        {"id": 0, "title_tr": "Fırsatlı", "summary": "a. b.", "why": "c", "category": "dev",
         "signal": 4, "potential": 5, "opportunity": "talep",
         "potential_note": "İnce bir sarmalayıcı SaaS olarak satılabilir"},
        {"id": 1, "title_tr": "Fırsatsız", "summary": "a. b.", "why": "c", "category": "dev",
         "signal": 4, "potential": 2, "opportunity": "bosluk", "potential_note": "olmamalı"},
    ])
    cs = [cluster("Firsatli", 0), cluster("Firsatsiz", 1)]
    summarize(cs, CFG, Budget.from_config(CFG))
    assert cs[0].opportunity == "talep"
    assert OPPORTUNITY_LABEL[cs[0].opportunity] == "Kanıtlı talep"
    assert cs[1].opportunity is None          # potential < 4 → tür tutulmaz
    assert cs[1].potential_note is None


def test_yorum_maddesi_yuksek_firsat_alsa_da_radara_girmiyor(fake):
    """Kullanıcı isteği: radar YENİ ÇIKIŞLAR için. Bir yorum ya da haber
    maddesi yüksek fırsat puanı alsa bile listeye girmemeli."""
    fake([
        {"id": 0, "title_tr": "Gerçek çıkış", "summary": "a. b.", "why": "c",
         "category": "dev", "signal": 4, "potential": 5, "opportunity": "ekosistem",
         "potential_note": "Üzerine ürün kurulabilir"},
        {"id": 1, "title_tr": "Sadece yorum", "summary": "a. b.", "why": "c",
         "category": "dev", "signal": 2, "potential": 5, "opportunity": "talep",
         "potential_note": "girmemeli"},
    ])
    cs = [cluster("Gercek cikis", 0), cluster("Sadece yorum", 1)]
    summarize(cs, CFG, Budget.from_config(CFG))
    hot = alerts(cs)
    assert [c.title for c in hot] == ["Gerçek çıkış"]
    assert all((c.signal or 0) >= MIN_SIGNAL_FOR_ALERT for c in hot)


def test_firsat_yoksa_radar_bos_doner(fake):
    fake([{"id": i, "title_tr": f"Madde {i}", "summary": "a. b.", "why": "c",
           "category": "dev", "signal": 4, "potential": 3, "opportunity": "yok",
           "potential_note": ""} for i in range(3)])
    cs = [cluster(f"Madde {i}", i) for i in range(3)]
    summarize(cs, CFG, Budget.from_config(CFG))
    assert alerts(cs) == []          # zorlama yok: fırsat yoksa liste boş


# ---------- modelin yanıtta atladığı maddeler ----------

def test_yanitta_atlanan_madde_tekrar_soruluyor(fake, monkeypatch):
    """Model batch'teki bazı id'leri yanıtta atlıyor (gerçek koşuda 82'nin 14'ü).
    İlk turda eksik kalanlar ikinci bir istekle tekrar sorulur."""
    calls = {"n": 0}

    def factory(api_key=None):
        class M:
            def count_tokens(self, **kw): return SimpleNamespace(input_tokens=500)
            def create(self, **kw):
                calls["n"] += 1
                rows = ([{"id": 0, "title_tr": "Var", "summary": "a. b.", "why": "c",
                          "category": "dev", "signal": 3, "potential": 2,
                          "opportunity": "yok", "potential_note": ""}]
                        if calls["n"] == 1 else
                        [{"id": 1, "title_tr": "Sonradan", "summary": "a. b.", "why": "c",
                          "category": "dev", "signal": 3, "potential": 2,
                          "opportunity": "yok", "potential_note": ""}])
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text",
                                             text=json.dumps({"items": rows}))],
                    stop_reason="end_turn",
                    usage=SimpleNamespace(input_tokens=500, output_tokens=200,
                                          cache_read_input_tokens=0))
        return SimpleNamespace(messages=M())

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("pipeline.summarize.Anthropic", factory)
    cs = [cluster("Var", 0), cluster("Atlanan", 1)]
    rep = summarize(cs, CFG, Budget.from_config(CFG))
    assert rep["missing_first_pass"] == 1
    assert rep["missing_after_retry"] == 0
    assert cs[1].title_tr == "Sonradan"      # ikinci turda geldi
    assert calls["n"] == 2


def test_tekrar_denemede_de_gelmeyen_madde_sayiya_girmiyor(fake, monkeypatch):
    """Kalite kontrolü yapılamamış madde sayfaya alınmaz — aksi hâlde
    'Hintli olsaydım' gibi tweet'ler sinyal filtresini atlayıp tepeye çıkıyor."""
    def factory(api_key=None):
        class M:
            def count_tokens(self, **kw): return SimpleNamespace(input_tokens=500)
            def create(self, **kw):
                rows = [{"id": 0, "title_tr": "Var", "summary": "a. b.", "why": "c",
                         "category": "dev", "signal": 3, "potential": 2,
                         "opportunity": "yok", "potential_note": ""}]
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text",
                                             text=json.dumps({"items": rows}))],
                    stop_reason="end_turn",
                    usage=SimpleNamespace(input_tokens=500, output_tokens=200,
                                          cache_read_input_tokens=0))
        return SimpleNamespace(messages=M())

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("pipeline.summarize.Anthropic", factory)
    cs = [cluster("Var", 0), cluster("Hic gelmeyen", 1)]
    summarize(cs, CFG, Budget.from_config(CFG))
    assert cs[1].summary_missing is True
    kept, dropped = drop_low_signal(cs, CFG)
    assert [c.lead.title for c in kept] == ["Var"]
    assert [c.lead.title for c in dropped] == ["Hic gelmeyen"]


def test_hic_denenmemis_madde_sayida_kaliyor(monkeypatch):
    """Bütçe tavanı ya da API hatası yüzünden HİÇ denenmemiş madde elenmez —
    onu elemek için gerekçemiz yok, ham başlıkla sayıda kalır."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cs = [cluster("Hic denenmedi", 0)]
    rep = summarize(cs, CFG, Budget.from_config(CFG))
    assert rep["degraded"] is True
    assert cs[0].summary_missing is False
    kept, dropped = drop_low_signal(cs, CFG)
    assert len(kept) == 1 and not dropped


# ---------- günlük kümülatif bütçe ----------

def test_butce_gun_basina_bugunku_kosular_sayiliyor(tmp_path):
    """Tavan koşu başına değil GÜN başına. Aynı gün ikinci koşu, birincinin
    harcamasını devralır; yoksa 20 koşu 20 kat harcama demek olur."""
    from pipeline.budget import TWEET_COST_USD, Budget
    from pipeline.db import connect, record_run

    conn = connect(tmp_path / "t.db")
    record_run(conn, items_raw=10, items_kept=5, failed_sources=[],
               llm_cost_usd=0.15, api_cost_usd=400 * TWEET_COST_USD)
    b = Budget.from_config({"budget": {"daily_llm_usd": 0.20,
                                       "daily_twitter_reads": 600}}, conn)
    assert b.llm_usd == pytest.approx(0.15)
    assert b.tweet_reads == 400
    # Kalan pay: LLM $0.05, 200 okuma
    assert b.can_afford_llm(0.04) and not b.can_afford_llm(0.06)
    assert b.can_read_tweets(200) and not b.can_read_tweets(201)
    conn.close()


def test_butce_baglantisiz_eski_davranisi_koruyor():
    from pipeline.budget import Budget
    b = Budget.from_config({"budget": {"daily_llm_usd": 0.20}})
    assert b.llm_usd == 0 and b.tweet_reads == 0
