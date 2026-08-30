"""Twitter hesaplarinin RSS karsiliklari — hangileri gercekten yayinda?"""
import concurrent.futures as cf, re
from _fetch import get

FEEDS = [
 # dev
 ("vercel",        "https://vercel.com/atom", "dev"),
 ("supabase",      "https://supabase.com/rss.xml", "dev"),
 ("github",        "https://github.blog/feed/", "dev"),
 ("huggingface",   "https://huggingface.co/blog/feed.xml", "dev"),
 ("anthropic",     "https://www.anthropic.com/rss.xml", "dev"),
 ("openai",        "https://openai.com/news/rss.xml", "dev"),
 ("deepmind",      "https://deepmind.google/blog/rss.xml", "dev"),
 ("replit",        "https://blog.replit.com/feed.xml", "dev"),
 ("simonw",        "https://simonwillison.net/atom/everything/", "dev"),
 ("latent.space",  "https://www.latent.space/feed", "dev"),
 ("rauchg",        "https://rauchg.com/rss", "dev"),
 ("stackoverflow", "https://stackoverflow.blog/feed/", "dev"),
 # startup
 ("techcrunch",    "https://techcrunch.com/feed/", "startup"),
 ("techmeme",      "https://www.techmeme.com/feed.xml", "startup"),
 ("ycombinator",   "https://www.ycombinator.com/blog/rss", "startup"),
 ("paulg",         "http://www.aaronsw.com/2002/feeds/pgessays.rss", "startup"),
 ("a16z",          "https://a16z.com/feed/", "startup"),
 ("indiehackers",  "https://www.indiehackers.com/feed.xml", "startup"),
 # gamedev
 ("godot",         "https://godotengine.org/rss.xml", "gamedev"),
 ("gamedeveloper", "https://www.gamedeveloper.com/rss.xml", "gamedev"),
 ("tigsource",     "https://www.tigsource.com/feed/", "gamedev"),
 ("unity",         "https://blog.unity.com/feed", "gamedev"),
 ("unrealengine",  "https://www.unrealengine.com/en-US/rss", "gamedev"),
 ("rockpapershot", "https://www.rockpapershotgun.com/feed", "gamedev"),
 # design
 ("figma",         "https://www.figma.com/blog/feed/", "design"),
 ("tailwind",      "https://tailwindcss.com/feed.xml", "design"),
 ("smashingmag",   "https://www.smashingmagazine.com/feed/", "design"),
 ("awwwards",      "https://www.awwwards.com/blog/feed/", "design"),
 ("uxdesigncc",    "https://uxdesign.cc/feed", "design"),
 # tr
 ("webrazzi",      "https://webrazzi.com/feed", "tr"),
 ("startupsome",   "https://startups.com.tr/feed/", "tr"),
]

def check(row):
    name, url, cat = row
    try:
        st, ct, raw = get(url, timeout=15)
        doc = raw.decode("utf-8", "replace")
        n = len(re.findall(r"<item[ >]", doc)) or len(re.findall(r"<entry[ >]", doc))
        d = re.search(r"<pubDate>(.*?)</pubDate>", doc) or re.search(r"<updated>(.*?)</updated>", doc)
        return (bool(n), f"{'OK  ' if n else 'BOS '} {name:<15} {cat:<8} {n:>3} kayit  son: {(d.group(1)[:25] if d else '?')}  {url}")
    except Exception as e:
        return (False, f"FAIL {name:<15} {cat:<8}   -  {type(e).__name__}: {getattr(e,'code',e)}  {url}")

with cf.ThreadPoolExecutor(max_workers=10) as ex:
    results = list(ex.map(check, FEEDS))
ok = sum(1 for r in results if r[0])
for _, line in sorted(results, key=lambda r: not r[0]):
    print(line)
print(f"\n=> {ok}/{len(FEEDS)} feed calisiyor")
