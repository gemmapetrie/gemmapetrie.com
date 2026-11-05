# Site build

    python3 build/build.py        # regenerates every page from build/*.json and images/

- **Speaking / Publications:** add entries to `build/speaking.json` / `build/publications.json`, then rebuild.
  Each entry: `{"title": "...", "publication": "venue or note", "date": "2025-02", "url": "https://..."}`.
  (`detail`, `date` and `url` are optional. Newest year first.)
- **Writing / Recipes:** scraped from Squarespace into `build/collections.json`.
- **Local archive (not published):** `python3 build/archive_local.py` writes `../gemmapetrie-archive`.
