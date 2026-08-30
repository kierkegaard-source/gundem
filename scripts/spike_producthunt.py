"""Product Hunt GraphQL v2 — PRODUCTHUNT_TOKEN gerekir."""
import json, os, urllib.request, ssl, sys

TOKEN = os.environ.get("PRODUCTHUNT_TOKEN")
if not TOKEN:
    print("[SKIP] PRODUCTHUNT_TOKEN yok. .env'e ekleyip tekrar calistir."); sys.exit(0)

# DOGRULANDI: postedAfter olmadan eski urunler donuyor. Tarih filtresi sart.
from datetime import datetime, timezone, timedelta
SINCE = (datetime.now(timezone.utc) - timedelta(hours=26)).strftime("%Y-%m-%dT%H:%M:%SZ")

QUERY = """
query TodayPosts($after: DateTime!) {
  posts(order: VOTES, first: 20, postedAfter: $after) {
    edges { node {
      id name tagline url website votesCount commentsCount createdAt
      topics(first: 3) { edges { node { name } } }
    } }
  }
}
"""
body = json.dumps({"query": QUERY, "variables": {"after": SINCE}}).encode()
req = urllib.request.Request(
    "https://api.producthunt.com/v2/api/graphql", data=body,
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
             "Accept": "application/json", "User-Agent": "daily-launch-spike/0.1"})
try:
    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    ctx = ssl.create_default_context()
try:
    with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
        data = json.loads(r.read())
except Exception as e:
    print(f"[FAIL] Product Hunt: {e!r}")
    if hasattr(e, "read"):
        print("  govde:", e.read()[:400])
    sys.exit(1)

if "errors" in data:
    print("[FAIL] Product Hunt GraphQL hatasi:", json.dumps(data["errors"], ensure_ascii=False)[:400]); sys.exit(1)

edges = data["data"]["posts"]["edges"]
print(f"[OK ] Product Hunt: {len(edges)} urun")
for e in edges[:5]:
    n = e["node"]
    print(f"  {n['name']} | ▲{n['votesCount']} | {n['createdAt']} | {n['tagline'][:60]}")
