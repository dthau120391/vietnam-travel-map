"""City settings shared by enrich.py, build.py and validate.py."""

CITIES = {
    "hcmc": {
        "name": "Hồ Chí Minh",
        "center": [10.7769, 106.7009],
        "zoom": 13,
        "core": 8,  # km from center that the first view fits; day trips sit outside it
        "bbox": [10.30, 106.30, 11.20, 107.10],  # south, west, north, east
    },
    "dalat": {
        "name": "Đà Lạt",
        "center": [11.9404, 108.4583],
        "zoom": 13,
        "core": 6,
        "bbox": [11.60, 108.20, 12.20, 108.80],
    },
    "nhatrang": {
        "name": "Nha Trang",
        "center": [12.2450, 109.1940],
        "zoom": 13,
        "core": 7,
        "bbox": [11.70, 108.90, 12.70, 109.50],
    },
    "mytho": {
        "name": "Mỹ Tho",
        "center": [10.3560, 106.3650],
        "zoom": 13,
        "core": 5,
        "bbox": [10.00, 105.80, 10.60, 106.80],
    },
}

CATS = ["food", "cafe", "sight", "shopping", "market", "nightlife", "nature", "experience", "kids"]


def in_bbox(city, lat, lng):
    s, w, n, e = CITIES[city]["bbox"]
    return s <= lat <= n and w <= lng <= e
