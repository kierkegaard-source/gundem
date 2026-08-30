"""Spike'lar icin ortak stdlib fetch yardimcisi (uv kurulmadan calissin diye)."""
import gzip, json, ssl, urllib.error, urllib.request

UA = "daily-launch-spike/0.1 (+https://github.com/)"


def _ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def get(url, headers=None, timeout=20):
    h = {"User-Agent": UA, "Accept-Encoding": "gzip"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    ctx = _ctx()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return r.status, r.headers.get("Content-Type", ""), raw


def get_json(url, headers=None, timeout=20):
    status, ctype, raw = get(url, headers, timeout)
    return status, json.loads(raw.decode("utf-8", "replace"))


def report(name, ok, detail):
    print(f"[{'OK ' if ok else 'FAIL'}] {name}: {detail}")
