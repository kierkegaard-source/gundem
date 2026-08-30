"""Bluesky AT Protocol: anahtarsiz public AppView."""
import json
from _fetch import get_json, report

PUB = "https://public.api.bsky.app/xrpc"

# 1) Hesap timeline'i
for actor in ("godotengine.org", "itch.io"):
    try:
        status, data = get_json(f"{PUB}/app.bsky.feed.getAuthorFeed?actor={actor}&limit=5&filter=posts_no_replies")
        feed = data.get("feed", [])
        report(f"getAuthorFeed {actor}", status == 200 and bool(feed), f"HTTP {status}, {len(feed)} post")
        if feed:
            p = feed[0]["post"]
            print("  alanlar:", sorted(p.keys()))
            print("  ornek:", json.dumps({
                "uri": p["uri"], "createdAt": p["record"].get("createdAt"),
                "text": (p["record"].get("text") or "")[:90],
                "likes": p.get("likeCount"), "reposts": p.get("repostCount"),
                "handle": p["author"]["handle"]}, ensure_ascii=False))
    except Exception as e:
        report(f"getAuthorFeed {actor}", False, repr(e))

# 2) Etiket/kelime aramasi (feed yerine)
for q in ("screenshotsaturday", "gamedev"):
    try:
        status, data = get_json(f"{PUB}/app.bsky.feed.searchPosts?q={q}&limit=5&sort=top")
        posts = data.get("posts", [])
        report(f"searchPosts {q}", status == 200 and bool(posts), f"HTTP {status}, {len(posts)} post")
    except Exception as e:
        report(f"searchPosts {q}", False, repr(e))
