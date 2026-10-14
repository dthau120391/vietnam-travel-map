# Bản đồ Du lịch & Ẩm thực Việt Nam

An interactive map of places to eat, drink coffee, hear acoustic music, shop and take the kids in Hồ Chí Minh, Đà Lạt, Nha Trang and Mỹ Tho, in Vietnamese.

**Live:** https://dthau120391.github.io/vietnam-travel-map/

Each place has a pin, photos from Wikimedia Commons with their credit, a summary of what reviewers praise and criticise, a sourced rating where one could be verified, price, hours and tips.

Buttons open Google Maps directions, Google reviews and TikTok reviews for the place.

The list opens most famous first. The order comes from `fame()` in `tools/build.py`: review volume compared with places of the same category, rating against its source's average, Wikipedia page views, a bonus when 3 or more independent guides list the place, Michelin and trending signals. Unconfirmed places sink. CI fails if a place 4 or more guides agree on drops out of its city's top 20%.

Visitors can mark a place 🎯 want to go, ✅ been there or 🚫 skip, add a note, and share their list as a link. They can set 🏠 a home base by tapping the map, which adds distances, a 1–3 km filter and near-home sorts. Marks and home stay in the visitor's own browser; nothing is sent to a server unless the visitor joins a group (only when `data/sync.json` holds a Firebase config, and then only marks and a chosen name are shared), and `tools/build.py` refuses to write a home into the published `index.html`.

## Layout

| Path                  | What it is                                                                                             |
|-----------------------|--------------------------------------------------------------------------------------------------------|
| `index.html`          | The published page, generated: do not edit by hand                                                     |
| `src/template.html`   | The page's layout, styles and map code, with a `__DATA__` placeholder                                  |
| `data/research/`      | The raw research, one file per city slice, as the research agents wrote it                             |
| `data/overrides.json` | Manual decisions (keep or move a pin, remove a place, add a warning), each with its reason             |
| `data/signature.json` | Which guides list which places, one URL per guide; 3 or more guides earn the 🏆 Biểu tượng mark         |
| `data/gratings.json`  | Google ratings read for places that first had only a Foody score                                       |
| `data/places.json`    | Every place, after enrichment                                                                          |
| `data/meta.json`      | The data's date                                                                                        |
| `tools/enrich.py`     | Merges research files, checks each pin against OpenStreetMap, resolves Commons photos                  |
| `tools/build.py`      | Puts the data into the template and writes `index.html`                                                |
| `tools/smoke.mjs`     | CI, in a real browser: no script errors, every city lists places, details open on desktop and phone    |
| `tools/checklinks.py` | Follows every link a visitor can click; `build.py` drops the dead ones (`data/linkcheck.json`)         |
| `firestore.rules`     | Rules for the shared group marks: members write only their own marks; nobody can list groups           |
| `tools/validate.py`   | The CI gate: data well formed, pins inside their city, `index.html` up to date, script parses          |

## Update

```sh
python3 tools/enrich.py data/research   # only when the research files change
python3 tools/build.py
python3 tools/validate.py
python3 tools/build.py --home <lat>,<lng> --out <path>   # a private local copy with a home preset
```

A push to `main` runs `tools/validate.py` and publishes `index.html` to GitHub Pages.

## Credits

Map data © OpenStreetMap contributors and Esri; satellite imagery © Esri, Maxar.

Photos come from Wikimedia Commons, under the licence named on each photo.

Place information was compiled in October 2026 from the Michelin Guide, Wikipedia, Tripadvisor and the Vietnamese travel and food sites listed on each place.