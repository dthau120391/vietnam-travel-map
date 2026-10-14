#!/usr/bin/env python3
"""Merge research files into data/places.json: check every pin against OpenStreetMap
and resolve every Wikimedia Commons photo to a verified URL with its credit.

Usage: python3 tools/enrich.py <research-dir> [--offline]
  <research-dir> holds hcmc-food.json, hcmc-explore.json, dalat.json, nhatrang.json, mytho.json.
  Network calls are cached in data/.cache/ so a re-run only asks for what is new.
Writes data/places.json and prints a report of every pin it moved or could not confirm.
"""
import html
import json
import math
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cities import CATS, CITIES, in_bbox  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / ".cache"
UA = "VietnamTravelMap/1.0 (personal travel map; https://github.com/dthau120391)"
FILES = {"hcmc-food": "hcmc", "hcmc-explore": "hcmc", "dalat": "dalat", "nhatrang": "nhatrang",
         "nhatrang-b": "nhatrang", "mytho": "mytho"}
AGREE_KM = 1.5  # an agent pin within this distance of an OSM match counts as confirmed


def fold(s):
    s = unicodedata.normalize("NFD", str(s or "")).replace("đ", "d").replace("Đ", "D")
    return re.sub(r"[^a-z0-9 ]", " ", "".join(c for c in s if unicodedata.category(c) != "Mn").lower()).strip()


def km(a, b):
    r = math.radians
    dlat, dlng = r(b[0] - a[0]), r(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(r(a[0])) * math.cos(r(b[0])) * math.sin(dlng / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


class Cache:
    def __init__(self, name):
        self.path = CACHE / f"{name}.json"
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self):
        CACHE.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=0))


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "vi,en"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


# ── OpenStreetMap (Nominatim: max 1 request per second) ─────────────────────
_last = [0.0]


def nominatim(q, city, cache, offline):
    key = f"{city}|{q}"
    if key in cache.data:
        return cache.data[key]
    if offline:
        return []
    s, w, n, e = CITIES[city]["bbox"]
    params = {"q": q, "format": "jsonv2", "limit": 3, "countrycodes": "vn",
              "viewbox": f"{w},{n},{e},{s}", "bounded": 1, "accept-language": "vi"}
    wait = 1.1 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    try:
        res = get_json("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params))
    except Exception as ex:  # noqa: BLE001 — a failed lookup is reported, not fatal
        print(f"  ! nominatim error for {q!r}: {ex}", file=sys.stderr)
        _last[0] = time.time()
        return []  # not cached: a timeout is not "OpenStreetMap has no match", so the next run asks again
    _last[0] = time.time()
    out = [{"lat": float(x["lat"]), "lng": float(x["lon"]), "name": x.get("name") or "",
            "type": f'{x.get("category")}/{x.get("type")}', "rank": x.get("place_rank"),
            "display": x.get("display_name", "")[:140]} for x in res]
    cache.data[key] = out
    return out


GENERIC = set("quan nha hang tiem cua so pho duong banh mi com bun hu tieu ca phe cafe coffee cho cong vien chua "
              "nha tho bao tang khu du lich sai gon ho chi minh da lat nha trang my tho the and of".split())


def addr_line(addr):
    """'55 Ngô Quyền, Phường 1, Mỹ Tho' -> '55 Ngô Quyền' (Nominatim cannot parse old ward/district names)."""
    return re.sub(r"\(.*?\)", "", (addr or "").split(",")[0]).strip()


def street_of(addr):
    return re.sub(r"^[\s\d/A-Za-z]*\d[\dA-Za-z/\-]*\s+", "", addr_line(addr)).strip()


def name_match(name, hit):
    """Most distinctive words of our name appear in the OSM name."""
    ours = [t for t in fold(name).split() if len(t) > 1]
    key = [t for t in ours if t not in GENERIC] or ours
    theirs = set(fold(hit["name"]).split())
    return bool(theirs) and sum(t in theirs for t in key) / len(key) >= 0.6


def key_tokens(name):
    toks = [t for t in fold(re.sub(r"\(.*?\)", "", name)).split() if len(t) > 1]
    return set(t for t in toks if t not in GENERIC) or set(toks)


def same_place(a, b):
    """Two researchers' entries for one venue under different names ("Hòn Tằm" / "Đảo Hòn Tằm").
    Only called across files, where a slip merges two real places, so a weak name match needs nearby pins."""
    ka, kb = key_tokens(a["name"]), key_tokens(b["name"])
    if not ka or not kb:
        return False
    ratio = len(ka & kb) / min(len(ka), len(kb))
    pins = None not in (a.get("lat"), a.get("lng"), b.get("lat"), b.get("lng"))
    d = km((a["lat"], a["lng"]), (b["lat"], b["lng"])) if pins else None
    if ratio >= 0.8 and min(len(ka), len(kb)) >= 2 and (d is None or d < 1.5):
        return True
    return d is not None and d < 0.3 and ratio >= (1.0 if min(len(ka), len(kb)) == 1 else 0.6)


def fill_from(keep, lose):
    """The kept entry takes whatever it lacks from its duplicate: a pin, a rating, hours, photos."""
    if keep.get("lat") is None and lose.get("lat") is not None:
        keep["lat"], keep["lng"], keep["coordSource"] = lose["lat"], lose["lng"], lose.get("coordSource")
    for k in ("rating", "hours", "price", "website", "wiki", "address", "mustTry", "tips_vi", "subtitle"):
        if not keep.get(k) and lose.get(k):
            keep[k] = lose[k]
    have = {(im or {}).get("commons") for im in keep.get("images") or []}
    keep["images"] = (keep.get("images") or []) + [im for im in lose.get("images") or [] if im.get("commons") not in have]
    keep["tags"] = list(dict.fromkeys((keep.get("tags") or []) + (lose.get("tags") or [])))
    keep["sources"] = list(dict.fromkeys((keep.get("sources") or []) + (lose.get("sources") or [])))


def richness(p):
    if p.get("status") == "draft":  # a skeleton must never replace a finished entry
        return -1
    return len(json.dumps(p, ensure_ascii=False)) + 400 * len(p.get("images") or []) + (300 if p.get("rating") else 0)


def locate(p, cache, offline):
    """Return (lat, lng, approx, how, note)."""
    city, cname = p["city"], CITIES[p["city"]]["name"]
    agent = (p.get("lat"), p.get("lng"))
    has_agent = None not in agent and in_bbox(city, *agent)
    names = [re.sub(r"\s*\(.*?\)", "", p["name"]).strip()] + re.findall(r"\((.*?)\)", p["name"])
    name_hits = []
    for n in names:
        name_hits = [h for h in nominatim(f"{n}, {cname}", city, cache, offline) if name_match(n, h)]
        if name_hits:
            break
    line, st = addr_line(p.get("address")), street_of(p.get("address"))
    by_addr = nominatim(f"{line}, {cname}", city, cache, offline) if line and line != st else []
    by_street = [h for h in (nominatim(f"{st}, {cname}", city, cache, offline) if st else [])
                 if h["type"].startswith("highway/")]  # a road, not a shop that shares its name
    if has_agent:
        cands = [("name", h) for h in name_hits] + [("address", h) for h in by_addr] + [("street", h) for h in by_street]
        if not cands:
            return agent[0], agent[1], False, "agent", "no OSM match to compare"
        d, kind, h = min(((km(agent, (h["lat"], h["lng"])), k, h) for k, h in cands), key=lambda x: x[0])
        if d <= AGREE_KM:
            return agent[0], agent[1], False, "agent+osm", f"OSM {kind} match within {d:.2f} km"
        # A road's OSM point is its middle, often kilometres from a house on it, so only a match
        # on the place's own name or on a building can dispute a researcher's pin.
        strong = name_hits + [h for h in by_addr if not h["type"].startswith("highway/")]
        if not strong:
            return agent[0], agent[1], False, "agent", f"only a street match, {d:.1f} km off"
        best = strong[0]
        d = km(agent, (best["lat"], best["lng"]))
        return agent[0], agent[1], False, "agent-disputed", f"OSM {'name' if name_hits else 'address'} {d:.1f} km away; best OSM: {best['lat']:.5f},{best['lng']:.5f} {best['display']}"
    if name_hits:
        h = name_hits[0]
        return h["lat"], h["lng"], False, "osm-name", h["display"]
    if by_addr:
        h = by_addr[0]
        exact = h["type"].split("/")[0] in ("building", "place", "amenity", "tourism", "shop", "leisure", "historic")
        return h["lat"], h["lng"], not exact, "osm-address", h["display"]
    if by_street:
        h = by_street[0]
        return h["lat"], h["lng"], True, "osm-street", h["display"]
    return None, None, True, "none", "no coordinates found"


# ── Wikimedia Commons ───────────────────────────────────────────────────────
def commons_info(titles, cache, offline):
    todo = [t for t in titles if t not in cache.data]
    for i in range(0, 0 if offline else len(todo), 40):
        batch = todo[i:i + 40]
        params = {"action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|extmetadata|mime|size",
                  "iiurlwidth": 960, "titles": "|".join(batch), "redirects": 1}
        data = get_json("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params))
        q = data.get("query", {})
        alias = {}
        for m in q.get("normalized", []) + q.get("redirects", []):
            alias[m["to"]] = alias.get(m["from"], m["from"])
        for page in q.get("pages", {}).values():
            asked = alias.get(page["title"], page["title"])
            if "missing" in page or "imageinfo" not in page:
                cache.data[asked] = None
                continue
            ii = page["imageinfo"][0]
            meta = ii.get("extmetadata", {})
            artist = html.unescape(re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", ""))).strip()
            src = (ii.get("thumburl") or ii["url"]).split("?")[0]  # drop Commons' utm_* tracking
            thumb = src.replace("/960px-", "/330px-") if "/960px-" in src else src
            cache.data[asked] = {"src": src, "thumb": thumb, "page": ii.get("descriptionurl"),
                                 "credit": re.sub(r"\s+", " ", artist)[:80],
                                 "lic": meta.get("LicenseShortName", {}).get("value", ""), "mime": ii.get("mime")}
        for t in batch:
            cache.data.setdefault(t, None)
        time.sleep(0.5)
    return {t: cache.data.get(t) for t in titles}


def url_ok(url, cache, offline):
    if url in cache.data:
        return cache.data[url]
    if offline:
        return False
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": UA, "Range": "bytes=0-1023"})
        with urllib.request.urlopen(req, timeout=30) as r:
            ok = r.status in (200, 206) and r.headers.get("Content-Type", "").startswith("image/")
    except Exception:  # noqa: BLE001 — any failure means "do not show this image"
        ok = False
    cache.data[url] = ok
    return ok


# ── main ────────────────────────────────────────────────────────────────────
def norm_title(t):
    t = (t or "").strip().replace("_", " ")
    return t if t.lower().startswith("file:") else ("File:" + t if t else "")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    offline = "--offline" in sys.argv
    src_dir = Path(args[0])
    places, merges = [], []
    for stem, city in FILES.items():
        f = src_dir / f"{stem}.json"
        if not f.exists():
            print(f"! missing {f}", file=sys.stderr)
            continue
        for p in json.loads(f.read_text()):
            p["city"], p["_file"] = city, stem
            twin = next((q for q in places if q["city"] == city and q["_file"] != stem and same_place(p, q)), None)
            if twin is None:
                places.append(p)
                continue
            keep, lose = (p, twin) if richness(p) > richness(twin) else (twin, p)
            fill_from(keep, lose)
            places[places.index(twin)] = keep
            merges.append(f'{city}: kept "{keep["name"]}" ({keep["_file"]}), merged "{lose["name"]}" ({lose["_file"]})')

    geo, img, head = Cache("nominatim"), Cache("commons"), Cache("urlcheck")
    # Manual decisions, keyed "city/name": {"accept": "agent"} keeps a disputed researcher pin,
    # {"lat", "lng", "source"} sets one by hand, {"drop": true} leaves the place out. Each carries a "why", so the decision stays reviewable.
    ov_path = ROOT / "data" / "overrides.json"
    overrides = json.loads(ov_path.read_text(encoding="utf-8")) if ov_path.exists() else {}
    used = set()
    report = {"moved": [], "disputed": [], "unlocated": [], "approx": [], "bad_images": [], "fixed": [],
              "merged": merges}
    ids = set()
    out = []
    for i, p in enumerate(places):
        if p.get("cat") not in CATS:
            report["fixed"].append(f'{p.get("name")}: cat {p.get("cat")!r} -> experience')
            p["cat"] = "experience"
        pid = p.get("id") or f'{p["city"]}-{fold(p["name"]).replace(" ", "-")}'
        while pid in ids:
            pid += "-2"
        ids.add(pid)
        if p.get("status") == "draft":  # an unfinished research entry (no description yet) stays out
            report["fixed"].append(f'{p["city"]}/{p["name"]}: held back — research draft')
            continue
        ov = overrides.get(f'{p["city"]}/{p["name"]}')
        if ov:
            used.add(f'{p["city"]}/{p["name"]}')
            if ov.get("drop"):
                report["fixed"].append(f'{p["city"]}/{p["name"]}: dropped — {ov.get("why", "")}')
                continue
        lat, lng, approx, how, note = locate(p, geo, offline)
        if ov:
            if "lat" in ov:
                lat, lng, approx, how = ov["lat"], ov["lng"], bool(ov.get("approx")), "manual"
            elif ov.get("accept") == "agent" and how == "agent-disputed":
                how = "agent-reviewed"
        if i % 10 == 0:
            geo.save()
            print(f"  … {i}/{len(places)} located", file=sys.stderr)
        tag = f'{p["city"]}/{p["name"]}'
        if how == "agent-disputed":
            report["disputed"].append(f"{tag}: {note}")
        elif how == "none":
            report["unlocated"].append(tag)
        elif approx:
            report["approx"].append(f"{tag}: {how} {note}")
        if how.startswith("osm") and p.get("lat") is not None:
            report["moved"].append(f"{tag}: agent pin outside city box, used {how}")
        rating = p.get("rating")
        if isinstance(rating, dict) and rating.get("value") and rating.get("url"):
            v = float(rating["value"])
            rating = {"v": v, "n": int(rating.get("count") or 0), "src": rating.get("source") or "",
                      "url": rating["url"], "seen": rating.get("seen") or ""}
            src = rating["src"].lower()
            if v > 5 or "foody" in src or "/10" in src or "thang diem 10" in fold(src):  # Foody scores out of 10
                rating["scale"] = 10
        else:
            rating = None
        out.append({
            "id": pid, "city": p["city"], "name": p["name"], "cat": p["cat"], "sub": p.get("subtitle") or "",
            "addr": p.get("address") or "", "lat": round(lat, 6) if lat is not None else None,
            "lng": round(lng, 6) if lng is not None else None, "approx": bool(approx), "coordHow": how,
            "price": p.get("price") or "", "hours": p.get("hours") or "", "must": p.get("mustTry") or "",
            "desc": p.get("desc_vi") or "", "review": p.get("review_vi") or "", "rating": rating,
            "hot": bool(p.get("trending")), "tags": [t for t in (p.get("tags") or []) if t][:6],
            "tips": p.get("tips_vi") or "", "imgsWanted": p.get("images") or [],
            "wiki": p.get("wiki") or None, "web": p.get("website") or None,
            "sources": [u for u in (p.get("sources") or []) if isinstance(u, str) and u.startswith("http")][:8],
            "status": p.get("status") or "open", "existing": bool(p.get("existing")),
        })
    geo.save()
    for k in sorted(set(overrides) - used):
        print(f"! override for {k!r} matched no place", file=sys.stderr)

    titles = sorted({norm_title(im.get("commons")) for p in out for im in p["imgsWanted"]
                     if isinstance(im, dict) and im.get("commons")})
    info = commons_info(titles, img, offline)
    img.save()
    checks = {}
    urls = sorted({u for v in info.values() if v for u in (v["src"], v["thumb"])})
    with ThreadPoolExecutor(4) as ex:
        for u, ok in zip(urls, ex.map(lambda u: url_ok(u, head, offline), urls)):
            checks[u] = ok
    head.save()
    for p in out:
        imgs = []
        for im in p.pop("imgsWanted"):
            t = norm_title(im.get("commons")) if isinstance(im, dict) else ""
            v = info.get(t)
            if not v or (v.get("mime") or "").endswith("svg+xml") or not (checks.get(v["src"]) and checks.get(v["thumb"])):
                if t:
                    report["bad_images"].append(f'{p["city"]}/{p["name"]}: {t}')
                continue
            if any(x["src"] == v["src"] for x in imgs):
                continue
            imgs.append({"src": v["src"], "thumb": v["thumb"], "page": v["page"], "credit": v["credit"],
                         "lic": v["lic"], "kind": "dish" if im.get("kind") == "dish" else "place"})
        imgs.sort(key=lambda x: x["kind"] == "dish")  # a photo of the place itself goes first
        p["imgs"] = imgs[:4]

    (ROOT / "data" / "places.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    (ROOT / "data" / ".cache" / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    by_city = {c: sum(1 for p in out if p["city"] == c and p["status"] != "closed") for c in CITIES}
    print(json.dumps({"places": len(out), "by_city": by_city,
                      "closed": sum(p["status"] == "closed" for p in out),
                      "with_rating": sum(1 for p in out if p["rating"]),
                      "with_place_photo": sum(1 for p in out if any(i["kind"] == "place" for i in p["imgs"])),
                      "with_any_photo": sum(1 for p in out if p["imgs"]),
                      "pins": {h: sum(p["coordHow"] == h for p in out) for h in sorted({p["coordHow"] for p in out})},
                      **{k: len(v) for k, v in report.items()}}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
