# Movie Recommender — Notes

This project provides a small, testable movie recommender engine (`movie_recommender.py`) with optional fuzzy matching and data expansion helpers.

## Optional dependency: RapidFuzz 🔎
- RapidFuzz enables **fuzzy** matching (typo-tolerant search) and is optional.
- Install it with:

  pip install rapidfuzz

- The code detects RapidFuzz at runtime. If `--fuzzy` is passed but RapidFuzz is not installed, a runtime warning is printed and the search falls back to fast tokenized substring matching.

## Performance & tuning ⚙️
- Default fuzzy candidate cap: `FUZZY_MAX_CANDIDATES = 250`. This keeps fuzzy searches fast and predictable on large datasets.
- Control fuzzy behavior via CLI flags:
  - `--fuzzy` : enable fuzzy matching
  - `--fuzzy-threshold <0-100>` : set match sensitivity (default 70)
- For very large datasets you can increase `FUZZY_MAX_CANDIDATES` in `movie_recommender.py`, or add an indexed storage backend (SQLite) for faster searching.

## CLI examples 💻
- Query and get JSON output:

  python -m movie_recommender --query "Inception" --format json

- Run fuzzy query (if RapidFuzz is installed):

  python -m movie_recommender --query "Incption" --fuzzy --fuzzy-threshold 60 --format text

- Load a custom dataset then query:

  python -m movie_recommender --load my_movies.json --query "My Movie" --format json

## Tests & CI ✅
- Run unit tests locally:

  python -m pytest -q

- CI workflow is in `.github/workflows/ci.yml` and runs tests on pushes and pull requests.

## Large datasets
- An expanded dataset was generated and saved as `movies_expanded_2019_2025_2000.json` (2000 movies across 2019–2025).

## Need help?
If you'd like, I can:
- Add SQLite-backed persistence for fast indexed queries
- Add a README section showing how to run the interactive mode
- Add performance benchmarks for fuzzy vs tokenized searches

Tell me which you'd like next and I'll implement it. 🎯
