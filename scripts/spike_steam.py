"""Steam: yeni cikanlar. Store arama JSON endpoint'i + RSS alternatifi."""
import re, html
from _fetch import get, get_json, report

SEARCH = ("https://store.steampowered.com/search/results/?query&start=0&count=25"
          "&dynamic_data=&sort_by=Released_DESC&category1=998&supportedlang=english"
          "&infinite=1&ndl=1")
try:
    status, data = get_json(SEARCH)
    doc = data.get("results_html", "")
    ids = re.findall(r'data-ds-appid="(\d+)"', doc)
    titles = re.findall(r'<span class="title">(.*?)</span>', doc)
    dates = re.findall(r'<div class="col search_released responsive_secondrow">(.*?)</div>', doc)
    report("Steam search JSON", status == 200 and bool(titles),
           f"HTTP {status}, total_count={data.get('total_count')}, {len(titles)} baslik, {len(ids)} appid")
    for i, t in enumerate(titles[:5]):
        print(f"  {ids[i] if i < len(ids) else '?'} | {html.unescape(t)} | "
              f"{html.unescape(dates[i]).strip() if i < len(dates) else '?'}")
except Exception as e:
    report("Steam search JSON", False, repr(e))

for url in ("https://store.steampowered.com/feeds/newreleases.xml",):
    try:
        status, ctype, raw = get(url)
        items = re.findall(r"<item>", raw.decode("utf-8", "replace"))
        report(url, status == 200 and bool(items), f"HTTP {status}, {len(items)} kayit")
    except Exception as e:
        report(url, False, repr(e))
