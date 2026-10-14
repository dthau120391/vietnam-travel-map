#!/usr/bin/env python3
"""Check every link a visitor can click or load on the map, and record which work.

Usage:
  python3 tools/checklinks.py                  check links in data/places.json (cached for 7 days)
  python3 tools/checklinks.py --unsure FILE    write the links a plain request could not settle
                                               (403/429/5xx/timeouts) to FILE for a browser pass
  python3 tools/checklinks.py --merge FILE     fold a browser pass ({url: "ok"|"dead"}) into the results
Writes data/linkcheck.json ({url: "ok" | "dead" | "unsure"}); build.py drops every "dead" link.
"""
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock, Semaphore

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / ".cache" / "links.json"
OUT = ROOT / "data" / "linkcheck.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
FRESH_DAYS = 7
# A page that answers 200 but says it is gone ("soft 404").
SOFT_404 = re.compile(r"<title>[^<]*(404|not found|page not found|không tìm thấy|trang không tồn tại|"
                      r"this page isn.t available|content isn.t available)[^<]*</title>", re.I)


def links(places):
    """Every URL the page shows or loads, with what it is."""
    out = defaultdict(set)
    for p in places:
        if p["status"] not in ("open", "unverified"):
            continue
        for k in ("wiki", "web"):
            if p.get(k):
                out[p[k]].add(k)
        for u in p.get("sources") or []:
            out[u].add("source")
        if p.get("rating") and p["rating"].get("url"):
            out[p["rating"]["url"]].add("rating")
        for im in p.get("imgs") or []:
            for k in ("page", "src", "thumb"):
                out[im[k]].add("img")
    return out


_host_slots, _host_lock = {}, Lock()


def _slot(host):
    with _host_lock:
        return _host_slots.setdefault(host, Semaphore(2))  # at most 2 requests at once per site


def check(url):
    """Return (verdict, http code or error, final url)."""
    host = urllib.parse.urlsplit(url).hostname or ""
    # Vietnamese letters in a path must be percent-encoded, as a browser does, or urllib cannot send them.
    wire = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~")
    req = urllib.request.Request(wire, headers={"User-Agent": UA, "Accept-Language": "vi,en;q=0.8",
                                               "Accept": "text/html,application/xhtml+xml,image/*,*/*;q=0.8"})
    with _slot(host):
        try:
            with urllib.request.urlopen(req, timeout=25, context=ssl.create_default_context()) as r:
                final, code = r.geturl(), r.status
                head = r.read(60000).decode("utf-8", "ignore") if "html" in r.headers.get("Content-Type", "") else ""
        except urllib.error.HTTPError as e:
            return ("dead" if e.code in (404, 410) else "unsure"), e.code, url
        except urllib.error.URLError as e:
            reason = str(e.reason)
            if re.search(r"nodename nor servname|Name or service not known|getaddrinfo|No address associated", reason):
                return "dead", "dns", url  # the domain is gone
            return "unsure", reason[:80], url
        except Exception as e:  # noqa: BLE001 — timeouts and resets are settled by the browser pass
            return "unsure", type(e).__name__, url
    if SOFT_404.search(head):
        return "dead", f"{code} soft-404", final
    path_in, path_out = urllib.parse.urlsplit(url).path.strip("/"), urllib.parse.urlsplit(final).path.strip("/")
    if path_in and not path_out and urllib.parse.urlsplit(final).hostname == host:
        return "dead", f"{code} sent to home page", final  # a removed article redirected to the site's front page
    return "ok", code, final


def main():
    args = sys.argv[1:]
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    if "--merge" in args:
        browser = json.loads(Path(args[args.index("--merge") + 1]).read_text())
        for url, verdict in browser.items():
            if verdict in ("ok", "dead"):
                cache[url] = {"verdict": verdict, "code": "browser", "final": url, "checked": time.time()}
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0))
    places = json.loads((ROOT / "data" / "places.json").read_text(encoding="utf-8"))
    want = links(places)
    todo = [u for u in want if u not in cache or time.time() - cache[u]["checked"] > FRESH_DAYS * 86400
            or (cache[u]["verdict"] == "unsure" and "--merge" not in args)]
    print(f"{len(want)} links, {len(todo)} to check", file=sys.stderr)
    with ThreadPoolExecutor(12) as ex:
        for i, (u, (verdict, code, final)) in enumerate(zip(todo, ex.map(check, todo)), 1):
            cache[u] = {"verdict": verdict, "code": code, "final": final, "checked": time.time()}
            if i % 200 == 0:
                print(f"  … {i}/{len(todo)}", file=sys.stderr)
                CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0))
    result = {u: cache[u]["verdict"] for u in sorted(want)}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=0) + "\n")
    if "--unsure" in args:
        Path(args[args.index("--unsure") + 1]).write_text(
            json.dumps(sorted(u for u, v in result.items() if v == "unsure"), ensure_ascii=False, indent=0))
    tally = defaultdict(int)
    for v in result.values():
        tally[v] += 1
    print(json.dumps(dict(tally)))
    for u, v in result.items():
        if v == "dead":
            print(f"  dead [{cache[u]['code']}] {', '.join(sorted(want[u]))}: {u[:110]}")


if __name__ == "__main__":
    main()
