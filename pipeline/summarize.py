"""Claude API ile Türkçe özetleme.

PROJECT.md §7.2 — 20'şerlik batch, tek istekte, item başına ayrı çağrı YOK.

İKİ SAPMA (Faz 4'te doğrulandı, gerekçeleri aşağıda):

1. PROMPT CACHING KULLANILMIYOR. PROJECT.md "sistem promptu sabit → prompt
   caching kullan, girdi maliyeti %90 düşer" diyor. Ama claude-haiku-4-5'te
   cache'lenebilir minimum önek 4096 token; bizim sistem promptumuz ~400 token.
   Eşiğin altındaki promptlar SESSİZCE cache'lenmiyor — hata yok, sadece
   cache_creation_input_tokens: 0. Yapay dolguyla 4096'ya çıkarmak da ters
   teper: cache okuması 4096 × 0.1 = 410 efektif token eder, gerçek promptumuz
   zaten 400. Yani caching bu modelde bu proje için maliyeti DÜŞÜRMEZ.

2. YAPILANDIRILMIŞ ÇIKTI KULLANILIYOR. PROJECT.md "çıktı sadece JSON" deyip
   bozuk JSON'a karşı batch atlama öngörüyor. `output_config.format` ile şema
   API seviyesinde zorlanıyor (Haiku 4.5 destekliyor), bozuk JSON riski
   ortadan kalkıyor. Yine de savunma amaçlı ham başlık yedeği korunuyor.
"""
from __future__ import annotations

import json
import os

from anthropic import Anthropic

from pipeline.budget import Budget
from pipeline.dedupe import Cluster

MODEL = "claude-haiku-4-5"
BATCH_SIZE = 20
MAX_TOKENS = 4000
CATEGORIES = ["dev", "gamedev", "apps", "design", "startup", "tr"]

SYSTEM = """Sen teknoloji ve girişim dünyasını takip eden bir editörsün. Sana JSON listesi \
halinde yeni çıkan ürün/proje/haber verilecek. Her biri için Türkçe çıktı üret.

Her madde için:
- id: girdideki id, aynen
- title_tr: başlığın Türkçesi. ÜRÜN, ŞİRKET, PROJE VE OYUN ADLARINI ÇEVİRME — \
"Hyperfocus", "Olostep", "godot" olduğu gibi kalır. Haber cümlelerini, \
tanıtım cümlelerini ve açıklayıcı başlıkları çevir. "Show HN:" gibi platform \
önekleri atılır. Başlık zaten Türkçeyse aynen bırak.
- summary: 2 cümle. Ne olduğunu ve kime yaradığını anlat. Pazarlama dili kullanma, \
abartma. "Devrim niteliğinde", "oyunun kurallarını değiştiren" gibi ifadeler yasak.
- why: tek satır, en fazla 12 kelime. Bunu neden okumaya değer?
- category: dev | gamedev | apps | design | startup | tr
- signal: 1-5 arası.

signal, maddenin NE KADAR ÜNLÜ olduğunu değil, GERÇEKTEN YENİ BİR ŞEY OLUP \
OLMADIĞINI ölçer. Küçük ve niş bir çıkış da bir çıkıştır.

5 = geniş kitleyi ilgilendiren önemli yeni ürün, sürüm ya da haber
4 = açıklaması net, işe yarar yeni bir araç/oyun/proje
3 = gerçek bir çıkış, niş ya da küçük ölçekli
2 = gerçek bir çıkış ama elimizde çok az bilgi var
1 = çıkış DEĞİL: kişisel görüş, tartışma, şikayet, meme, alakasız sohbet, \
sanat paylaşımı, ekran görüntüsü, etkinlik izlenimi

Yeni yayınlanmış bir oyun, uygulama, kütüphane ya da araç ASLA 1 değildir — \
bilgi azsa 2, açıklaması varsa 3 veya üstü. 1'i yalnızca ortada bir çıkış \
yoksa kullan.

- potential: 1-5 arası TİCARİ FIRSAT PUANI.

Okuyucu, kendi ürününü kurup para kazanmak isteyen bir geliştirici/girişimci. \
Soru "bu iyi bir ürün mü" DEĞİL. Soru şu: bu maddede, okuyucunun ÜZERİNE İŞ \
KURABİLECEĞİ ya da GELİR ELDE EDEBİLECEĞİ somut bir fırsat var mı?

Fırsat sayılan şeyler:
- Yeni bir platform, API ya da ekosistem açılıyor; üzerine ürün kurulabilir
- İnsanların para ödediği kanıtlanmış bir talep görünüyor (gelir, kullanıcı \
  sayısı, satış rakamı paylaşılmış)
- Popüler bir üründe belirgin bir eksik var; daha iyisi ya da niş versiyonu \
  yapılabilir
- Yeni bir dağıtım kanalı ya da mağaza açılmış; erken girene avantaj
- Bir alanda talep hızla büyüyor ama arz yetersiz

Fırsat SAYILMAYAN şeyler: genel haberler, büyük şirket duyuruları, fon \
turları, kişisel görüşler, "ilginç ama ne yapacağım belli değil" olanlar.

5 = net ve uygulanabilir fırsat; bir hafta içinde bir şey inşa etmeye \
başlanabilir
4 = gerçek fırsat ama biraz araştırma ya da hazırlık gerekiyor
3 = fırsat olabilir, henüz erken ya da rekabet belirsiz
2 = zayıf; ilgi çekici ama gelir yolu görünmüyor
1 = ticari fırsat yok

ÇOK KATI OL. 60 maddelik bir listede 4-5 alan madde sayısı genelde 0 ile 3 \
arasındadır. Bazı günler HİÇ ÇIKMAZ ve bu normaldir — zorlamak yerine 3 ver. \
Sıradan bir ürün çıkışı 2'dir.

- opportunity: fırsatın türü. potential 4 veya 5 ise şunlardan biri: \
"ekosistem" (üzerine ürün kurulabilir), "bosluk" (eksik/daha iyisi yapılabilir), \
"talep" (ödeme yapan talep kanıtlanmış), "kanal" (yeni dağıtım kanalı). \
potential 3 veya altıysa "yok" ver.

- potential_note: potential 4 veya 5 ise, TEK CÜMLE, en fazla 18 kelime. \
SOMUT OL: ne yapılabileceğini söyle, maddeyi tekrar etme. \
Kötü örnek: "Bu araç çok popüler olabilir." \
İyi örnek: "Ajan altyapısı kuranlar için scraping katmanı; ince bir sarmalayıcı \
SaaS olarak satılabilir." \
potential 3 veya altıysa boş string ver.

Girdi İngilizceyse özet yine Türkçe olacak. Teknik terimleri zorlama çevirme — \
framework, endpoint, shader, repo, commit gibi kelimeler olduğu gibi kalsın."""

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "title_tr": {"type": "string"},
                    "summary": {"type": "string"},
                    "why": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    # NOT: JSON şemasında minimum/maximum desteklenmiyor, enum kullanılıyor.
                    "signal": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                    "potential": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                    "opportunity": {"type": "string",
                                    "enum": ["ekosistem", "bosluk", "talep", "kanal", "yok"]},
                    "potential_note": {"type": "string"},
                },
                "required": ["id", "title_tr", "summary", "why", "category",
                             "signal", "potential", "opportunity", "potential_note"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _payload(batch: list[Cluster], offset: int) -> str:
    rows = []
    for i, c in enumerate(batch):
        rows.append({
            "id": offset + i,
            "title": c.title[:200],
            "source": "+".join(c.sources),
            "text": c.raw_text[:600],
        })
    return json.dumps(rows, ensure_ascii=False)


def summarize(clusters: list[Cluster], cfg: dict, budget: Budget) -> dict:
    """Kümeleri yerinde özetler. Döner: çalışma raporu."""
    report = {"batches": 0, "summarized": 0, "skipped_budget": 0,
              "failed_batches": 0, "degraded": False}
    if not clusters:
        return report

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        budget.note("özetleme atlandı: ANTHROPIC_API_KEY yok, ham başlıklar kullanılıyor")
        report["degraded"] = True
        return report

    client = Anthropic(api_key=key)
    by_id = {}

    for start in range(0, len(clusters), BATCH_SIZE):
        batch = clusters[start:start + BATCH_SIZE]
        user = _payload(batch, start)
        messages = [{"role": "user", "content": user}]

        # --- Bütçe: çağrıdan ÖNCE tahmin et ---
        try:
            counted = client.messages.count_tokens(
                model=MODEL, system=SYSTEM, messages=messages).input_tokens
        except Exception:
            counted = len(user) // 3 + 600          # kaba yedek tahmin
        # Madde başına çıktı: özet + why + Türkçe başlık + potansiyel notu.
        est_output = len(batch) * 175
        est = Budget.estimate_llm_usd(counted, est_output)

        if not budget.can_afford_llm(est):
            remaining = len(clusters) - start
            budget.note(
                f"LLM bütçe tavanı: ${budget.llm_usd:.4f}/{budget.daily_llm_usd:.2f} — "
                f"{remaining} madde ham başlıkla kaldı")
            report["skipped_budget"] = remaining
            report["degraded"] = True
            break

        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=MAX_TOKENS, system=SYSTEM, messages=messages,
                output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
            )
            u = resp.usage
            budget.charge_llm(u.input_tokens, u.output_tokens,
                              getattr(u, "cache_read_input_tokens", 0) or 0)
            report["batches"] += 1

            if resp.stop_reason in ("refusal", "max_tokens"):
                raise ValueError(f"stop_reason={resp.stop_reason}")

            text = next(b.text for b in resp.content if b.type == "text")
            for row in json.loads(text)["items"]:
                by_id[int(row["id"])] = row
        except Exception as exc:
            # Savunma yedeği: bu batch ham başlıkla kalır, pipeline durmaz.
            report["failed_batches"] += 1
            report["degraded"] = True
            detail = str(getattr(exc, "message", None) or exc)[:300]
            budget.note(f"batch {start//BATCH_SIZE + 1} özetlenemedi "
                        f"({type(exc).__name__}: {detail}), "
                        f"{len(batch)} madde ham başlıkla kaldı")

    for i, c in enumerate(clusters):
        row = by_id.get(i)
        if not row:
            continue
        c.title_tr = (row.get("title_tr") or "").strip() or None
        c.summary_tr = (row.get("summary") or "").strip() or None
        c.why_tr = (row.get("why") or "").strip() or None
        c.signal = int(row.get("signal") or 0)
        c.potential = int(row.get("potential") or 0)
        note = (row.get("potential_note") or "").strip()
        c.potential_note = note if (note and c.potential >= 4) else None
        opp = (row.get("opportunity") or "").strip()
        c.opportunity = opp if (opp and opp != "yok" and c.potential >= 4) else None
        if row.get("category") in CATEGORIES:
            c.llm_category = row["category"]
        report["summarized"] += 1
    return report


def drop_low_signal(clusters: list[Cluster], cfg: dict) -> tuple[list[Cluster], list[Cluster]]:
    """signal eşiğinin altındakileri ayıklar. Özetlenmemişler (signal=None) kalır —
    bütçe yüzünden özetlenmemiş bir maddeyi elemek için gerekçemiz yok."""
    min_signal = int(cfg.get("filters", {}).get("min_signal", 2))
    kept, dropped = [], []
    for c in clusters:
        (dropped if (c.signal is not None and c.signal < min_signal) else kept).append(c)
    return kept, dropped


# Fırsat radarı eşiği.
POTENTIAL_ALERT = 4
# Radar yalnızca GERÇEK ÇIKIŞLARA açıktır. Yorum, tartışma ve haber maddeleri
# yüksek fırsat puanı alsa bile radara girmez — kullanıcının isteği
# "yeni çıkmış bir uygulama veya yayın olsun".
MIN_SIGNAL_FOR_ALERT = 3

OPPORTUNITY_LABEL = {
    "ekosistem": "Ekosistem",       # üzerine ürün kurulabilir
    "bosluk": "Boşluk",             # eksik var, daha iyisi yapılabilir
    "talep": "Kanıtlı talep",       # ödeme yapan talep görünüyor
    "kanal": "Dağıtım kanalı",      # erken girene avantaj
}


def alerts(clusters: list[Cluster], limit: int = 6) -> list[Cluster]:
    """Ticari fırsat taşıyan yeni çıkışlar — sayfanın en üstünde listelenir."""
    hot = [c for c in clusters
           if (c.potential or 0) >= POTENTIAL_ALERT
           and (c.signal or 0) >= MIN_SIGNAL_FOR_ALERT]
    hot.sort(key=lambda c: (-(c.potential or 0), -c.score))
    return hot[:limit]
