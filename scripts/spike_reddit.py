"""Reddit OAuth (script app) — REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET gerekir."""
import base64, json, os, ssl, sys, urllib.parse, urllib.request

CID = os.environ.get("REDDIT_CLIENT_ID")
CSEC = os.environ.get("REDDIT_CLIENT_SECRET")
if not (CID and CSEC):
    print("[SKIP] REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET yok."); sys.exit(0)

UA = "macos:daily-launch:0.1 (by /u/daily-launch-bot)"
try:
    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    ctx = ssl.create_default_context()

auth = base64.b64encode(f"{CID}:{CSEC}".encode()).decode()
req = urllib.request.Request(
    "https://www.reddit.com/api/v1/access_token",
    data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
    headers={"Authorization": f"Basic {auth}", "User-Agent": UA})
try:
    with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
        tok = json.loads(r.read())["access_token"]
    print("[OK ] Reddit token alindi")
except Exception as e:
    print(f"[FAIL] Reddit token: {e!r}")
    if hasattr(e, "read"):
        print("  govde:", e.read()[:300])
    sys.exit(1)

for sub in ("gamedev", "IndieDev", "SideProject", "webdev"):
    req = urllib.request.Request(
        f"https://oauth.reddit.com/r/{sub}/new?limit=10&raw_json=1",
        headers={"Authorization": f"Bearer {tok}", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
            children = json.loads(r.read())["data"]["children"]
        print(f"[OK ] r/{sub}: {len(children)} post")
        if children:
            d = children[0]["data"]
            print("  alanlar:", sorted(d.keys())[:18])
            print(f"  ornek: {d['title'][:60]} | ▲{d['ups']} | {d['created_utc']} | {d['permalink']}")
    except Exception as e:
        print(f"[FAIL] r/{sub}: {e!r}")
