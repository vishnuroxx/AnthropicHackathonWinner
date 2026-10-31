"""Run negotiate() on every demo row and save results/<row_id>.json so the demo works offline.

Usage: .venv/bin/python make_cache.py [row_id ...]
Expects middleman.negotiate(row, seed) -> dict (see app.py for the keys it reads).
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from demo_rows import DEMO_ROWS, SEED, row_date

RESULTS = Path(__file__).parent / "results"


# Runs negotiate() for one demo row and writes results/<row_id>.json.
# Args: row_id - key of DEMO_ROWS; negotiate - the middleman entry point.
# Returns: the result dict.
def cache_one(row_id, negotiate):
    spec = DEMO_ROWS[row_id]
    month, day = row_date(spec)
    result = negotiate({**spec, "month": month, "day": day}, SEED)
    result["row_id"] = row_id
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{row_id}.json").write_text(json.dumps(result, indent=2, default=str))
    return result


# Caches every requested demo row, continuing past per-row failures.
def main():
    load_dotenv(Path(__file__).parent / ".env.local")
    load_dotenv(Path(__file__).parent / ".env")
    try:
        from middleman import negotiate
    except ImportError:
        sys.exit("middleman.negotiate() not found: the middleman lane has not landed yet.")
    for row_id in sys.argv[1:] or DEMO_ROWS:
        try:
            r = cache_one(row_id, negotiate)
            print(f"ok   {row_id}: {r.get('outcome')} in {r.get('rounds')} round(s)")
        except Exception as e:  # keep going so one bad row doesn't block the rest
            print(f"FAIL {row_id}: {e!r}")


if __name__ == "__main__":
    main()
