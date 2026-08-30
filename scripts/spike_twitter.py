"""TwitterAPI.io — TWITTERAPI_KEY gerekir. SADECE hesap timeline'i, arama YOK."""
import json, os, ssl, sys, urllib.request

KEY = os.environ.get("TWITTERAPI_KEY")
if not KEY:
    print("[SKIP] TWITTERAPI_KEY yok."); sys.exit(0)
try:
    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    ctx = ssl.create_default_context()

def call(path):
    req = urllib.request.Request(f"https://api.twitterapi.io{path}",
                                 headers={"X-API-Key": KEY, "User-Agent": "daily-launch-spike/0.1"})
    with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
        return json.loads(r.read())

# Tek hesapla dene — maliyeti gormeden coklu istek atma
for handle in ("levelsio",):
    try:
        d = call(f"/twitter/user/last_tweets?userName={handle}")
        tweets = (d.get("data") or {}).get("tweets") or d.get("tweets") or []
        print(f"[OK ] @{handle}: {len(tweets)} tweet, ust anahtarlar={list(d.keys())}")
        if tweets:
            t = tweets[0]
            print("  alanlar:", sorted(t.keys())[:20])
            print("  ornek:", json.dumps({k: t.get(k) for k in ("id","createdAt","likeCount","retweetCount","url")}, ensure_ascii=False))
            print("  metin:", (t.get("text") or "")[:100])
    except Exception as e:
        print(f"[FAIL] @{handle}: {e!r}")
        if hasattr(e, "read"):
            print("  govde:", e.read()[:300])
