#!/usr/bin/env python3
"""Build index.html from src/template.html + data/places.json + data/meta.json.

Usage: python3 tools/build.py [--out PATH ...]   (default: index.html at the repo root)
The output is deterministic, so validate.py can tell when index.html is stale.
"""
import html
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cities import CITIES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GROUP_VI = {"eat": "Ăn uống", "cafe": "Cà phê", "music": "Cà phê acoustic", "shop": "Mua sắm",
            "kids": "Khu vui chơi", "other": "Tham quan & khác"}
MUSIC = re.compile(r"acoustic|phòng trà|nhạc sống|live music|nhạc trịnh|tiệm nhạc", re.I)
FOOD_MARKET = re.compile(r"ẩm thực|sủi cảo|(^|\s)ốc(\s|$)|hải sản|chợ đêm|ăn vặt|ăn uống|món ăn|street food|food", re.I)
LIVE = ("open", "unverified")


def group(p):
    """The filter tab a place sits under."""
    text = " ".join([p["name"], p.get("sub") or "", " ".join(p.get("tags") or [])])
    if p["cat"] == "music" or (p["cat"] in ("cafe", "nightlife") and MUSIC.search(text)):
        return "music"
    if p["cat"] == "market":
        return "eat" if FOOD_MARKET.search(text) else "shop"
    return {"food": "eat", "cafe": "cafe", "shopping": "shop", "kids": "kids"}.get(p["cat"], "other")


def volume(p):
    """log10 of how many people engaged: review count (Foody has ~15x fewer reviews than Google), or
    Wikipedia page views/3 for public places whose reviews scatter over many listings. None if unknown."""
    r, v = p.get("rating"), None
    if r:
        v = math.log10(1 + (r.get("n") or 0) * (15 if r.get("scale") == 10 else 1))
    if p.get("views"):
        v = max(v or 0.0, math.log10(1 + p["views"] / 3))
    return v


def group_medians(places):
    """A mall collects far more reviews than a market stall or a restaurant, so volume is compared within
    each category (food, market, shopping, sight…), not across them."""
    out = {}
    for c in {p["cat"] for p in places}:
        vs = sorted(v for p in places if p["status"] in LIVE and p["cat"] == c and (v := volume(p)) is not None)
        out[c] = vs[len(vs) // 2] if vs else 3.0
    return out


def fame(p, med):
    """How famous and worth going a place is, among places of its kind: review volume against its group's
    median, rating against its source's average, then Michelin, Wikipedia, guide-consensus and trending
    signals. Unconfirmed places sink."""
    r, v = p.get("rating"), volume(p)
    s = 3.2 + (1.6 * (v - med[p["cat"]]) if v is not None else 0.0)
    if r:
        s += (r["v"] - 7.0) * 0.6 if r.get("scale") == 10 else (r["v"] - 4.3) * 1.5
    if (p.get("guides") or 0) >= 3:  # listed by 3+ independent major guides
        s += 2.5
    tags = " ".join(p.get("tags") or []).lower()
    if re.search(r"michelin \d sao", tags):
        s += 3.0
    elif "bib gourmand" in tags:
        s += 2.0
    elif "michelin" in tags:
        s += 1.2
    s += 1.5 if p.get("wiki") else 0
    s += 0.8 if p.get("hot") else 0
    s -= 0.6 if "Ít người biết" in (p.get("tags") or []) else 0
    s -= 3.0 if p["status"] == "unverified" else 0
    return round(s, 2)


def info_html(places, meta):
    live = [p for p in places if p["status"] in LIVE]
    closed = [p for p in places if p["status"] == "closed"]
    removed = [p for p in places if p["status"] == "removed"]
    per_city = ", ".join(f'{c["name"]} {sum(p["city"] == k for p in live)}' for k, c in CITIES.items())
    per_cat = ", ".join(f"{GROUP_VI[k]} {n}" for k, n in Counter(group(p) for p in live).most_common())
    hosts = Counter()
    for p in live:
        for u in p["sources"]:
            hosts[u.split("/")[2].removeprefix("www.")] += 1
    top = ", ".join(h for h, _ in hosts.most_common(14))
    e = html.escape
    parts = [
        f'<p><b>{len(live)} địa điểm</b> ({e(per_city)}) — {e(per_cat)}. '
        f'Tổng hợp ngày {e(meta["generated"])} từ Michelin Guide, Wikipedia, Tripadvisor, báo và blog du lịch, '
        f'kiểm tra chéo vị trí với OpenStreetMap.</p>',
        "<h2 style='font-size:15px;margin-top:12px'>Cách dùng</h2><ul>"
        "<li>Chọn thành phố, rồi một loại: <b>Tất cả</b> gồm Ăn uống, Cà phê, Cà phê acoustic, Mua sắm và Khu vui chơi; "
        "điểm tham quan, thiên nhiên và quán bar nằm riêng ở <b>🏛️ Tham quan & khác</b>.</li>"
        "<li>Danh sách xếp <b>nổi tiếng & đáng đi nhất trước</b>: nhiều người đánh giá, điểm cao so với mặt bằng của nguồn, "
        "có Michelin, có trang Wikipedia hoặc đang hot; nơi chưa xác minh xếp cuối.</li>"
        "<li>🏠 <b>Nhà của tôi</b>: bấm 🏠 trên bản đồ rồi bấm vào chỗ bạn ở — danh sách hiện khoảng cách, lọc trong 1–3 km "
        "và có cách xếp “Đáng đi nhất gần nhà”. Vị trí nhà chỉ lưu trong trình duyệt của bạn.</li>"
        "<li>⭐ <b>Michelin</b>: có trong Michelin Guide 2026 · 🔥 <b>Hot</b>: nổi trên TikTok/báo 2025–2026.</li>"
        "<li>Trong trang chi tiết, đánh dấu <b>🎯 Muốn đi</b>, <b>✅ Đã đi</b> hoặc <b>🚫 Bỏ qua</b> và ghi chú riêng. "
        "Đánh dấu lưu trong trình duyệt của bạn (không gửi đi đâu); mục 🚫 bị ẩn khỏi bản đồ cho gọn.</li>"
        "<li><b>🔗 Chia sẻ danh sách</b> tạo một link chứa các đánh dấu của bạn — gửi cho bạn bè, họ bấm "
        "“Gộp vào danh sách của tôi” để nhận.</li>"
        "<li>📍 trên bản đồ = vị trí của bạn và sắp xếp theo khoảng cách; 🗺️ = xem cả vùng kể cả điểm đi trong ngày.</li></ul>",
        "<h2 style='font-size:15px;margin-top:12px'>Lưu ý về dữ liệu</h2><ul>"
        "<li><b>Điểm đánh giá</b> chỉ hiện khi có nguồn kiểm chứng (ghi rõ nguồn và thời điểm). Bấm "
        "“Đánh giá & ảnh Google” để xem điểm và review mới nhất.</li>"
        "<li><b>Phần “Được khen / Bị chê”</b> là tóm tắt từ nhiều nguồn, không phải trích nguyên văn.</li>"
        "<li><b>Ảnh</b> lấy từ Wikimedia Commons, ghi tác giả và giấy phép trên ảnh. Ảnh có nhãn "
        "“minh họa” là ảnh món ăn, không phải ảnh của chính quán.</li>"
        "<li><b>Địa chỉ</b> dùng tên quận/phường cũ (trước sáp nhập 1/7/2025) vì Google Maps và biển hiệu vẫn dùng "
        "phổ biến. Mỹ Tho nay thuộc tỉnh Đồng Tháp; Đà Lạt thuộc Lâm Đồng; Nha Trang thuộc Khánh Hòa.</li>"
        "<li>Ghim <b>viền nét đứt</b> = vị trí gần đúng; nút “Chỉ đường” tìm theo tên + địa chỉ nên vẫn chính xác.</li>"
        "<li>Giờ mở cửa và giá có thể thay đổi — nên kiểm tra lại trước khi đi.</li></ul>",
    ]
    if closed:
        parts.append("<p><b>Đã loại vì đóng cửa:</b> " + e(", ".join(
            f'{p["name"]} ({CITIES[p["city"]]["name"]})' for p in closed)) + ".</p>")
    if removed:
        parts.append("<p><b>Đã loại vì không nguồn nào còn xác nhận đang hoạt động:</b> " + e(", ".join(
            f'{p["name"]} ({CITIES[p["city"]]["name"]})' for p in removed)) + ".</p>")
    parts.append(f"<p style='color:#667085;font-size:12px'>Nguồn chính: {e(top)}. "
                 "Bản đồ © OpenStreetMap, © Esri; ảnh vệ tinh © Esri, Maxar.</p>")
    return "".join(parts)


def og_image(places):
    for p in places:
        if p["city"] == "hcmc" and p["cat"] == "sight" and p["status"] != "closed":
            for im in p.get("imgs", []):
                if im["kind"] == "place":
                    return im["src"]
    return ""


def build(home=None):
    """home: (lat, lng) for a LOCAL copy only — the published page never carries anyone's home."""
    places = json.loads((ROOT / "data" / "places.json").read_text(encoding="utf-8"))
    meta = json.loads((ROOT / "data" / "meta.json").read_text(encoding="utf-8"))
    med = group_medians(places)
    for p in places:
        p["grp"], p["fame"] = group(p), fame(p, med)
    live = [p for p in places if p["status"] in LIVE]
    cities = {k: {kk: v[kk] for kk in ("name", "center", "zoom", "core", "bbox")} for k, v in CITIES.items()}
    payload = {"generated": meta["generated"], "cities": cities, "places": places,
               "infoHtml": info_html(places, meta)}
    if home:
        payload["home"] = list(home)
    # "<" as < keeps "</script>" and "<!--" inside the data from ending the script block
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    desc = (f"{len(live)} địa điểm ăn uống, cà phê, tham quan, mua sắm và chỗ chơi cho bé ở Hồ Chí Minh, "
            "Đà Lạt, Nha Trang, Mỹ Tho — bản đồ, đánh giá, ảnh, đánh dấu đã đi.")
    tpl = (ROOT / "src" / "template.html").read_text(encoding="utf-8")
    for key in ("__DATA__", "__DESC__", "__OGIMG__"):
        assert key in tpl, f"template lost its {key} placeholder"
    return (tpl.replace("__DESC__", html.escape(desc)).replace("__OGIMG__", html.escape(og_image(places)))
            .replace("__DATA__", data))


def main():
    args = sys.argv[1:]
    home = None
    if "--home" in args:  # a private local copy: never pass this for the repo's index.html
        lat, lng = (float(x) for x in args.pop(args.index("--home") + 1).split(","))
        args.remove("--home")
        home = (lat, lng)
    outs = [Path(a) for a in args[args.index("--out") + 1:]] if "--out" in args else [ROOT / "index.html"]
    if home and ROOT / "index.html" in [o.resolve() for o in outs]:
        sys.exit("refusing to write a home location into the published index.html")
    page = build(home)
    for out in outs:
        out.write_text(page, encoding="utf-8")
        print(f"wrote {out} ({len(page.encode()):,} bytes)")


if __name__ == "__main__":
    main()
