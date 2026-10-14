#!/usr/bin/env python3
"""CI gate: the data is well formed, every pin sits inside its city, index.html is
up to date with its sources, and the page's script parses.

Usage: python3 tools/validate.py     (exit 1 with one line per problem)
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build import LIVE, build, fame, group, group_medians  # noqa: E402
from cities import CATS, CITIES, GROUPS, STATUSES, in_bbox  # noqa: E402

# The guides' consensus is the outside check on the fame score: a place 4+ independent major guides list
# (data/signature.json) must rank in its city's top 20%, or the default "most famous first" order is wrong.
STRONG_GUIDES = 4
TOP_SHARE = 0.20

ROOT = Path(__file__).resolve().parent.parent


def check_places(places):
    errs, ids = [], set()
    for i, p in enumerate(places):
        tag = f'#{i} {p.get("id")}'
        for key in ("id", "city", "name", "cat", "status"):
            if not p.get(key):
                errs.append(f"{tag}: missing {key}")
        if p.get("id") in ids:
            errs.append(f"{tag}: duplicate id")
        ids.add(p.get("id"))
        if p.get("city") not in CITIES:
            errs.append(f'{tag}: unknown city {p.get("city")!r}')
            continue
        if p.get("cat") not in CATS:
            errs.append(f'{tag}: unknown category {p.get("cat")!r}')
        if p.get("status") not in STATUSES:
            errs.append(f'{tag}: bad status {p.get("status")!r}')
        lat, lng = p.get("lat"), p.get("lng")
        if (lat is None) != (lng is None):
            errs.append(f"{tag}: only one of lat/lng set")
        elif lat is not None and not in_bbox(p["city"], lat, lng):
            errs.append(f'{tag}: pin {lat},{lng} is outside {CITIES[p["city"]]["name"]}')
        elif lat is None and p.get("status") in LIVE:
            errs.append(f"{tag}: open place with no pin")
        r = p.get("rating")
        if r is not None and not (0 < r.get("v", 0) <= r.get("scale", 5) and str(r.get("url", "")).startswith("http")):
            errs.append(f"{tag}: rating needs 0 < v <= scale (5, or 10 when marked) and a source url")
        if r is not None and not str(r.get("src", "")).strip():
            errs.append(f"{tag}: rating has no source name")
        if r is not None and "foody" in str(r.get("src", "")).lower() and r.get("scale") != 10:
            errs.append(f"{tag}: Foody scores out of 10, so this rating needs scale 10")
        for im in p.get("imgs", []):
            if not re.match(r"^https://(upload|thumb)\.wikimedia\.org/", str(im.get("src", ""))):
                errs.append(f'{tag}: image not from Wikimedia: {im.get("src")}')
            if im.get("kind") not in ("place", "dish"):
                errs.append(f"{tag}: image kind must be place or dish")
        for u in [p.get("wiki"), p.get("web"), *p.get("sources", [])]:
            if u and not re.match(r"^https?://", u):
                errs.append(f"{tag}: non-http link {u!r}")
    return errs


def check_ranking(places):
    """Places with strong guide consensus rank near the top of their city, and every place has a filter tab."""
    errs = []
    for p in places:
        if group(p) not in GROUPS:
            errs.append(f'{p["id"]}: group {group(p)!r} is not a filter tab')
    med = group_medians(places)
    for city in CITIES:
        ranked = sorted((p for p in places if p["city"] == city and p["status"] in LIVE),
                        key=lambda p: fame(p, med), reverse=True)
        top = max(5, round(len(ranked) * TOP_SHARE))
        strong = [(i, p) for i, p in enumerate(ranked, 1) if (p.get("guides") or 0) >= STRONG_GUIDES]
        if not strong and city != "mytho":
            errs.append(f"{city}: no place has {STRONG_GUIDES}+ guides — is data/signature.json missing?")
        for i, p in strong:
            if i > top:
                errs.append(f'{city}: {p["name"]!r} ({p["guides"]} guides) ranks #{i}, below the top {top}')
    return errs


def check_links(page_data):
    """No link tools/checklinks.py found dead reaches the page."""
    lc = ROOT / "data" / "linkcheck.json"
    if not lc.exists():
        return ["data/linkcheck.json missing: run python3 tools/checklinks.py"]
    dead = {u for u, v in json.loads(lc.read_text()).items() if v == "dead"}
    errs = []
    for p in page_data["places"]:
        shown = [p.get("web"), p.get("wiki"), *(p.get("sources") or []), (p.get("rating") or {}).get("url")]
        shown += [u for im in p.get("imgs") or [] for u in (im["src"], im["thumb"], im["page"])]
        errs += [f'{p["id"]}: dead link on the page: {u}' for u in shown if u in dead]
    return errs


def check_script(page):
    """node --check the page's own inline script (the last <script> without src or type)."""
    blocks = re.findall(r"<script>(.*?)</script>", page, re.S)
    if not blocks:
        return ["index.html: inline script not found"]
    node = shutil.which("node")
    if not node:
        return ["node not found: cannot syntax-check the inline script"]
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(blocks[-1])
    r = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
    Path(f.name).unlink()
    return [] if r.returncode == 0 else [f"inline script: {r.stderr.strip()}"]


def main():
    places = json.loads((ROOT / "data" / "places.json").read_text(encoding="utf-8"))
    errs = check_places(places) + check_ranking(places)
    page = build()
    on_disk = (ROOT / "index.html").read_text(encoding="utf-8")
    if page != on_disk:
        errs.append("index.html is stale: run python3 tools/build.py and commit it")
    data = re.search(r'<script id="places-data" type="application/json">(.*?)</script>', on_disk, re.S)
    if not data:
        errs.append("index.html: embedded data block not found")
    else:
        try:
            errs += check_links(json.loads(data.group(1)))
        except Exception as ex:  # noqa: BLE001
            errs.append(f"embedded data does not parse: {ex}")
    errs += check_script(on_disk)
    live = sum(p["status"] in LIVE for p in places)
    if errs:
        print("\n".join(errs))
        print(f"FAIL: {len(errs)} problem(s) in {len(places)} places")
        sys.exit(1)
    print(f"OK: {live} live places ({len(places) - live} closed or removed), guide-consensus places rank near the top, "
          "index.html up to date, script parses")


if __name__ == "__main__":
    main()
