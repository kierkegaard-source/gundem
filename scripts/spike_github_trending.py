"""GitHub Trending: HTML scrape (resmi API yok). Article blogu bazli parse."""
import re, html
from _fetch import get, report

URL = "https://github.com/trending?since=daily"
try:
    status, ctype, raw = get(URL)
except Exception as e:
    report("GitHub Trending", False, repr(e)); raise SystemExit(1)

doc = raw.decode("utf-8", "replace")
blocks = re.split(r'<article class="Box-row"', doc)[1:]

rows = []
for b in blocks:
    m = re.search(r'<h2[^>]*>.*?href="/([^"]+?)"', b, re.S)
    if not m:
        continue
    slug = m.group(1)
    d = re.search(r'<p class="col-9[^"]*">\s*(.*?)\s*</p>', b, re.S)
    lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', b)
    tot = re.search(r'/stargazers"[^>]*>\s*([\d,]+)', b)
    today = re.search(r'([\d,]+)\s*stars today', b)
    rows.append({
        "slug": slug,
        "url": f"https://github.com/{slug}",
        "desc": html.unescape(re.sub(r"<[^>]+>", "", d.group(1))).strip() if d else "",
        "lang": lang.group(1) if lang else None,
        "stars_total": int(tot.group(1).replace(",", "")) if tot else None,
        "stars_today": int(today.group(1).replace(",", "")) if today else None,
    })

report("GitHub Trending", status == 200 and bool(rows), f"HTTP {status}, {len(rows)} repo")
for r in rows[:4]:
    print(f"  {r['slug']} | +{r['stars_today']}/gun | toplam {r['stars_total']} | {r['lang']} | {r['desc'][:70]}")
print("  min_stars_today=50 filtresini gecen:", sum(1 for r in rows if (r['stars_today'] or 0) >= 50))
