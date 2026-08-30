"""itch.io: yeni oyunlar feed'i. Birkac aday URL denenir."""
import re
from _fetch import get, report

CANDIDATES = [
    "https://itch.io/games/newest.xml",
    "https://itch.io/feed/new.xml",
    "https://itch.io/games.xml",
    "https://itch.io/games/new-and-popular.xml",
]
for url in CANDIDATES:
    try:
        status, ctype, raw = get(url)
    except Exception as e:
        report(url, False, repr(e)); continue
    doc = raw.decode("utf-8", "replace")
    items = re.findall(r"<item>(.*?)</item>", doc, re.S) or re.findall(r"<entry>(.*?)</entry>", doc, re.S)
    report(url, status == 200 and bool(items), f"HTTP {status}, ctype={ctype}, {len(items)} kayit")
    if items:
        it = items[0]
        print("  etiketler:", sorted(set(re.findall(r"<([a-zA-Z:]+)[ >]", it)))[:15])
        t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        l = re.search(r"<link>(.*?)</link>", it, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", it, re.S)
        print("  ornek:", (t.group(1).strip() if t else "?"), "|", (l.group(1).strip() if l else "?"),
              "|", (d.group(1).strip() if d else "?"))
        break
