# Bản đồ Du lịch & Ẩm thực Việt Nam

An interactive map of places to eat, drink, see, shop and take the kids in Hồ Chí Minh, Đà Lạt, Nha Trang and Mỹ Tho, in Vietnamese.

**Live:** https://dthau120391.github.io/vietnam-travel-map/

Each place has a pin, photos from Wikimedia Commons with their credit, a summary of what reviewers praise and criticise, a sourced rating where one could be verified, price, hours and tips.

Buttons open Google Maps directions, Google reviews and TikTok reviews for the place.

Visitors can mark a place 🎯 want to go, ✅ been there or 🚫 skip, add a note, and share their list as a link. Marks stay in the visitor's own browser; nothing is sent to a server.

## Layout

| Path                  | What it is                                                                                    |
|-----------------------|-----------------------------------------------------------------------------------------------|
| `index.html`          | The published page, generated: do not edit by hand                                            |
| `src/template.html`   | The page's layout, styles and map code, with a `__DATA__` placeholder                         |
| `data/research/`      | The raw research, one file per city slice, as the research agents wrote it                    |
| `data/overrides.json` | Manual pin decisions (keep, move or drop a place), each with its reason                       |
| `data/places.json`    | Every place, after enrichment                                                                 |
| `data/meta.json`      | The data's date                                                                               |
| `tools/enrich.py`     | Merges research files, checks each pin against OpenStreetMap, resolves Commons photos         |
| `tools/build.py`      | Puts the data into the template and writes `index.html`                                       |
| `tools/validate.py`   | The CI gate: data well formed, pins inside their city, `index.html` up to date, script parses |

## Update

```sh
python3 tools/enrich.py data/research   # only when the research files change
python3 tools/build.py
python3 tools/validate.py
```

A push to `main` runs `tools/validate.py` and publishes `index.html` to GitHub Pages.

## Credits

Map data © OpenStreetMap contributors and Esri; satellite imagery © Esri, Maxar.

Photos come from Wikimedia Commons, under the licence named on each photo.

Place information was compiled in October 2026 from the Michelin Guide, Wikipedia, Tripadvisor and the Vietnamese travel and food sites listed on each place.