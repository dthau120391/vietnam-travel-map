#!/usr/bin/env python3
"""Build index.html from src/template.html + data/places.json + data/meta.json.

Usage: python3 tools/build.py [--out PATH ...]   (default: index.html at the repo root)
The output is deterministic, so validate.py can tell when index.html is stale.
"""
import html
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cities import CITIES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CAT_VI = {"food": "Ăn uống", "cafe": "Cà phê", "sight": "Tham quan", "shopping": "Mua sắm",
          "market": "Chợ & phố ẩm thực", "nightlife": "Về đêm", "nature": "Thiên nhiên",
          "experience": "Trải nghiệm", "kids": "Cho bé"}


def info_html(places, meta):
    live = [p for p in places if p["status"] != "closed"]
    closed = [p for p in places if p["status"] == "closed"]
    per_city = ", ".join(f'{c["name"]} {sum(p["city"] == k for p in live)}' for k, c in CITIES.items())
    per_cat = ", ".join(f"{CAT_VI[k]} {n}" for k, n in Counter(p["cat"] for p in live).most_common())
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
        "<li>Bấm tab thành phố, chọn loại địa điểm ở hàng chip; bấm một chip khi tất cả đang bật = chỉ xem loại đó.</li>"
        "<li>🔥 <b>Đang hot</b>: nổi trên TikTok/báo 2025–2026 · ⭐ <b>Michelin</b>: có trong Michelin Guide · "
        "👶 <b>Đi cùng bé</b>: khu vui chơi và nơi hợp với trẻ em.</li>"
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


def build():
    places = json.loads((ROOT / "data" / "places.json").read_text(encoding="utf-8"))
    meta = json.loads((ROOT / "data" / "meta.json").read_text(encoding="utf-8"))
    live = [p for p in places if p["status"] != "closed"]
    cities = {k: {kk: v[kk] for kk in ("name", "center", "zoom", "core")} for k, v in CITIES.items()}
    payload = {"generated": meta["generated"], "cities": cities, "places": places,
               "infoHtml": info_html(places, meta)}
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
    outs = [Path(a) for a in sys.argv[sys.argv.index("--out") + 1:]] if "--out" in sys.argv else [ROOT / "index.html"]
    page = build()
    for out in outs:
        out.write_text(page, encoding="utf-8")
        print(f"wrote {out} ({len(page.encode()):,} bytes)")


if __name__ == "__main__":
    main()
