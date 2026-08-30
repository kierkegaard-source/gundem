"""RSS: Webrazzi (tr) + Sidebar.io (design)."""
import re
from _fetch import get, report

FEEDS = [
    ("webrazzi", "https://webrazzi.com/feed"),
    ("sidebar", "https://sidebar.io/feed.xml"),
]
for name, url in FEEDS:
    try:
        status, ctype, raw = get(url)
    except Exception as e:
        report(name, False, f"{url} -> {repr(e)}"); continue
    doc = raw.decode("utf-8", "replace")
    items = re.findall(r"<item>(.*?)</item>", doc, re.S) or re.findall(r"<entry>(.*?)</entry>", doc, re.S)
    report(name, status == 200 and bool(items), f"HTTP {status}, ctype={ctype}, {len(items)} kayit")
    if items:
        it = items[0]
        print("  etiketler:", sorted(set(re.findall(r"<([a-zA-Z:]+)[ >]", it)))[:15])
        t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", it, re.S) or re.search(r"<updated>(.*?)</updated>", it, re.S)
        print("  ornek:", (t.group(1).strip()[:70] if t else "?"), "|", (d.group(1).strip() if d else "?"))
