"""X'in embed/syndication ucu — anahtarsiz, resmi degil. Gercekten calisiyor mu?"""
import json, re
from _fetch import get, report

for handle in ("levelsio", "TechCrunch"):
    url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{handle}"
    try:
        st, ct, raw = get(url, headers={"Accept": "text/html"})
    except Exception as e:
        report(f"syndication @{handle}", False, repr(e)); continue
    doc = raw.decode("utf-8", "replace")
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', doc, re.S)
    if not m:
        report(f"syndication @{handle}", False, f"HTTP {st}, __NEXT_DATA__ yok (len={len(doc)})"); continue
    try:
        data = json.loads(m.group(1))
        entries = data["props"]["pageProps"]["timeline"]["entries"]
    except Exception as e:
        report(f"syndication @{handle}", False, f"HTTP {st}, sema degismis: {e!r}"); continue
    tweets = [e for e in entries if e.get("type") == "tweet"]
    report(f"syndication @{handle}", bool(tweets), f"HTTP {st}, {len(tweets)} tweet")
    if tweets:
        c = tweets[0]["content"]["tweet"]
        print("  alanlar:", sorted(c.keys())[:16])
        print(f"  ornek: {c.get('created_at')} ♥{c.get('favorite_count')} ↻{c.get('retweet_count')}")
        print("  metin:", (c.get("full_text") or c.get("text") or "")[:100].replace("\n", " "))
