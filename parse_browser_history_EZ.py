"""Place beside Chrome or Edge History databases and run with Python 3.9+."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)
SQLITE_HEADER = b"SQLite format 3\x00"


def domain_for(url):
    try:
        return urlsplit(url).hostname if url else None
    except ValueError:
        return None


def read_database(source, eastern):
    # Let SQLite recover committed data in a scratch copy.
    with TemporaryDirectory() as scratch:
        database = Path(scratch) / "History"
        for suffix in ("", "-wal", "-journal"):
            original = source.with_name(source.name + suffix)
            if original.is_file():
                shutil.copyfile(original, database.with_name(database.name + suffix))

        with closing(sqlite3.connect(database)) as connection:
            connection.execute("PRAGMA trusted_schema = OFF")
            tables = connection.execute("""
                SELECT count(*) FROM sqlite_master
                WHERE type = 'table' AND name IN ('visits', 'urls')
            """).fetchone()[0]
            if tables != 2:
                return None
            return [
                (stamp, {
                    "timestamp_et": (EPOCH + timedelta(microseconds=stamp))
                    .astimezone(eastern).isoformat(timespec="microseconds") if stamp else None,
                    "title": title,
                    "domain": domain_for(url),
                    "url": url,
                    "source_file": source.name,
                    "visit_id": visit_id,
                })
                for visit_id, stamp, title, url in connection.execute("""
                    SELECT visits.id, visits.visit_time, urls.title, urls.url
                    FROM visits LEFT JOIN urls ON urls.id = visits.url
                """)
            ]


def main():
    folder = Path(__file__).resolve().parent
    try:
        eastern = ZoneInfo("America/New_York")
    except ZoneInfoNotFoundError:
        sys.exit(f'Missing Eastern time zone data. Run:\n  & "{sys.executable}" -m pip install tzdata')

    events = []
    databases = 0
    failures = 0
    for source in sorted(folder.iterdir()):
        if not source.is_file() or source.name in ("browser-history-EZ.json", "browser-history-EZ-partial.json"):
            continue
        try:
            with source.open("rb") as candidate:
                if candidate.read(len(SQLITE_HEADER)) != SQLITE_HEADER:
                    continue
            visits = read_database(source, eastern)
            if visits is None:
                print(f"Skipped {source.name}: no Chromium history tables.")
                continue
        except (OSError, sqlite3.Error, OverflowError, ValueError) as error:
            print(f"Could not read {source.name}: {error}", file=sys.stderr)
            failures += 1
            continue
        events.extend(visits)
        databases += 1
        print(f"{source.name}: {len(visits):,} visits")

    if not databases:
        sys.exit(f"No readable Chrome or Edge history databases found beside the script in {folder}")

    events.sort(key=lambda row: (not row[0], row[0] or 0))
    output = folder / ("browser-history-EZ-partial.json" if failures else "browser-history-EZ.json")
    with output.open("w", encoding="utf-8") as stream:
        json.dump([event for _, event in events], stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Saved {len(events):,} visits from {databases} database(s) to {output}")
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
