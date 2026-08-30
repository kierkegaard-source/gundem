"""HN Algolia: Show HN / Launch HN, son 24 saat, min 10 puan."""
import sys, time, json
from _fetch import get_json, report

BASE = "https://hn.algolia.com/api/v1/search_by_date"
since = int(time.time()) - 24 * 3600

for q in ("Show HN", "Launch HN"):
    url = (f"{BASE}?query={q.replace(' ', '%20')}&tags=story"
           f"&numericFilters=created_at_i>{since},points>=10&hitsPerPage=50")
    try:
        status, data = get_json(url)
    except Exception as e:
        report(f"HN {q}", False, repr(e)); continue
    hits = data.get("hits", [])
    report(f"HN {q}", status == 200 and bool(hits), f"HTTP {status}, {len(hits)} hit")
    if hits:
        h = hits[0]
        print("  alanlar:", sorted(h.keys()))
        print("  ornek:", json.dumps({k: h.get(k) for k in
              ("objectID","title","url","points","num_comments","author","created_at")},
              ensure_ascii=False))
