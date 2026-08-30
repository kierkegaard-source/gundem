"""config.yaml'daki Twitter handle'larini dogrular.
Cikti: handle | durum (OK/OLU/SESSIZ) | takipci | son tweet | 30 gunde tweet

Maliyet notu: handle basina TEK istek (last_tweets). Yanit zaten author bilgisini
tasidigi icin ayri profil cagrisi yapilmaz.
"""
import concurrent.futures as cf, json, os, re, pathlib, ssl, sys, urllib.request
from datetime import datetime, timezone

KEY = os.environ.get("TWITTERAPI_KEY")
if not KEY:
    print("[SKIP] TWITTERAPI_KEY yok."); sys.exit(0)
try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = ssl.create_default_context()
NOW = datetime.now(timezone.utc)

handles = sys.argv[1:]
if not handles:
    cfg = pathlib.Path(__file__).resolve().parent.parent / "config.yaml"
    twitter_block = cfg.read_text().split("twitter:")[-1]
    handles = re.findall(r"handle:\s*([A-Za-z0-9_]+)", twitter_block)

def call(path):
    req = urllib.request.Request(f"https://api.twitterapi.io{path}",
                                 headers={"X-API-Key": KEY, "User-Agent": "daily-launch/0.1"})
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        return json.loads(r.read())

def parse_dt(s):
    for fmt in ("%a %b %d %H:%M:%S %z %Y",):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def check(h):
    try:
        d = call(f"/twitter/user/last_tweets?userName={h}")
    except Exception as e:
        code = getattr(e, "code", None)
        return (3, h, "OLU" if code == 404 else "HATA", 0, "-", 0, f"{type(e).__name__}:{code}")
    if d.get("status") == "error" or d.get("code") not in (None, 0, 200):
        return (3, h, "OLU", 0, "-", 0, (d.get("msg") or "")[:40])
    tweets = (d.get("data") or {}).get("tweets") or d.get("tweets") or []
    if not tweets:
        return (2, h, "SESSIZ", 0, "tweet yok", 0, "")
    author = tweets[0].get("author") or {}
    followers = author.get("followers") or author.get("followers_count") or 0
    dates = []
    for t in tweets:
        try:
            dates.append(parse_dt(t.get("createdAt", "")))
        except Exception:
            pass
    if not dates:
        return (2, h, "SESSIZ", followers, "tarih yok", 0, "")
    last = max(dates); days = (NOW - last).days
    d30 = sum(1 for x in dates if (NOW - x).days <= 30)
    durum = "OK" if days <= 30 else "SESSIZ"
    return (0 if durum == "OK" else 2, h, durum, followers, f"{last:%Y-%m-%d} ({days}g)", d30, "")

print(f"{len(handles)} handle kontrol ediliyor (handle basina 1 istek)...\n")
print(f"{'handle':<18} {'durum':<7} {'takipci':>11}  {'son tweet':<18} {'30g':>4}  not")
print("-" * 74)
rows = []
with cf.ThreadPoolExecutor(max_workers=6) as ex:
    for r in ex.map(check, handles):
        rows.append(r)
for rank, h, durum, foll, last, d30, note in sorted(rows, key=lambda r: (r[0], -r[3])):
    print(f"{h:<18} {durum:<7} {foll:>11,}  {last:<18} {d30:>4}  {note}")

ok = sum(1 for r in rows if r[2] == "OK")
print(f"\nOK: {ok} | SESSIZ: {sum(1 for r in rows if r[2]=='SESSIZ')} | "
      f"OLU/HATA: {sum(1 for r in rows if r[2] in ('OLU','HATA'))} | toplam {len(rows)}")
dead = [r[1] for r in rows if r[2] != "OK"]
if dead:
    print("\nconfig.yaml'dan cikarilacaklar:")
    print("  " + ", ".join(dead))
