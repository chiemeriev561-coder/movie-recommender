# Movie Recommender

A small, testable movie recommendation tool with a command-line interface and optional fuzzy search.

This repository contains:

- `movie_recommender.py` — core recommender and CLI entrypoint
- `expand_dataset.py` — helper to expand or rebuild datasets
- `movies_cleaned.csv`, `ratings_cleaned.csv` — example datasets used by the tests

## Installation

Recommended: create and activate a virtual environment, then install dependencies:

```bash
python -m venv .venv
.\.venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

RapidFuzz is optional but recommended for typo-tolerant searches:

```bash
pip install rapidfuzz
```

## Quick start (CLI)

Run the recommender using the script directly or as a module:

```bash
# Run as module (preferred when package-installed)
python -m movie_recommender --query "Inception"

# Or run the script directly
python movie_recommender.py --query "Inception"
```

Examples with output format and fuzzy search:

```bash
# JSON output
python -m movie_recommender --query "Inception" --format json

# Fuzzy search (requires RapidFuzz)
python -m movie_recommender --query "Incption" --fuzzy --fuzzy-threshold 60 --format text
```

If you have a custom dataset file (JSON or CSV supported by loader), pass it with `--load`:

```bash
python -m movie_recommender --load my_movies.json --query "My Movie" --format json
```

## Public API

The tests call the loader function provided by the module. Use:

```py
from movie_recommender import load_movies
movies = load_movies("movies_cleaned.csv", "ratings_cleaned.csv")
```

If tests fail with a signature mismatch, update `load_movies` to accept the dataset paths used above.

## Tests & CI

Run tests locally with:

```bash
pytest -q
```

CI configuration is in `.github/workflows/ci.yml` (tests run on push/PR).

## Dataset notes

The repository includes a cleaned dataset (`movies_cleaned.csv`, `ratings_cleaned.csv`). To regenerate or expand the dataset, use `expand_dataset.py` and follow its README/comments.

## Contributing and License

Contributions are welcome — open an issue or submit a pull request. Add a short `CONTRIBUTING.md` if you want contribution guidelines.

This project does not include a license file; consider adding a `LICENSE` (for example, MIT) if you intend to make the project public.

---

For further edits, ensure examples match the actual CLI/loader signatures in `movie_recommender.py` and tests.


