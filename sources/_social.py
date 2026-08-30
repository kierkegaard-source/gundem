"""Sosyal kaynaklar için lansman ön filtresi.

FAZ 6 BULGUSU: Twitter'ın 142 ham maddesinden 15'i aday oluyordu ve 14'ü
LLM tarafından `signal=1` ("çıkış değil: kişisel görüş, tartışma, meme")
verilerek eleniyordu. Sayıya 1 madde giriyordu. Bluesky'da daha beter:
15 aday, 15'i elendi, sayıda 0.

Sebep: skorlama en çok beğeni alan gönderileri seçiyor, en çok beğeni alan
gönderiler de lansman değil hararetli yorum oluyor. Aday slotları yanlış
maddelere harcanıyor, sonra sinyal filtresi onları haklı olarak eliyor —
hem sayı boş kalıyor hem LLM bütçesi çöpe gidiyor.

Ölçülen tepe maddeler (2026-08-30):
  ŞU AN     : "If I was Indian", "Hey Anthropic...", "Dubai'ye duyulan nefret"
  FİLTRELİ  : "Okay I built it!", "yeni oyunumuzun demosunu yayınladık",
              "Godot'ta stilize patlama efekti"

Ölçüt: dış bağlantı VEYA lansman kelimesi. Bir şey duyuran gönderi bir yere
link verir; kişisel yorum vermez. Twitter'da maddelerin %58'i, Bluesky'da
%46'sı bu ölçütü geçiyor — hacim fazlasıyla yeterli.
"""
from __future__ import annotations

import re

_URL = re.compile(r"https?://\S+")

# Duyuru dili. Türkçe karşılıkları da var — TR hesapları için.
_LAUNCH = re.compile(
    r"\b(launch|launched|launching|introduc\w*|shipped|shipping|"
    r"now available|now live|is live|releas\w*|out now|announc\w*|"
    r"early access|open source|open-sourced|beta|v\d+(\.\d+)?|"
    r"built|made|created|demo|wishlist|"
    r"yayında|yayınlad\w*|çıktı|duyur\w*|tanıt\w*|sürüm|güncelleme)\b",
    re.I)


def looks_like_launch(text: str, has_external_link: bool) -> bool:
    """Gönderi bir şey duyuruyor mu, yoksa yorum mu?"""
    if has_external_link:
        return True
    return bool(_LAUNCH.search(text or ""))


def has_url(text: str) -> bool:
    return bool(_URL.search(text or ""))
