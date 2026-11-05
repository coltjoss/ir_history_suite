"""Export a Collect-BrowserHistory.ps1 collection as JSON and Excel-ready CSV."""

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import sqlite3
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


CHROMIUM_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)
FIELDS = (
    "timestamp_et", "title", "domain", "url", "computer",
    "windows_user", "browser", "profile", "visit_id",
)


def read_visits(database, eastern):
    # SQLite can replay a rollback journal or rebuild its WAL index on this copy.
    with TemporaryDirectory() as scratch:
        working = Path(scratch) / database.name
        for suffix in ("", "-wal", "-journal"):
            source = database.with_name(database.name + suffix)
            if source.is_file():
                shutil.copyfile(source, working.with_name(working.name + suffix))

        connection = sqlite3.connect(working)
        try:
            connection.execute("PRAGMA trusted_schema = OFF")
            return [
                (visit_time, {
                    "timestamp_et": (
                        (CHROMIUM_EPOCH + timedelta(microseconds=visit_time))
                        .astimezone(eastern).isoformat(timespec="microseconds")
                        if visit_time else None
                    ),
                    "title": title,
                    "domain": hostname(url),
                    "url": url,
                    "visit_id": visit_id,
                })
                for visit_id, visit_time, title, url in connection.execute("""
                    SELECT visits.id, visits.visit_time, urls.title, urls.url
                    FROM visits LEFT JOIN urls ON urls.id = visits.url
                """)
            ]
        finally:
            connection.close()


def hostname(url):
    try:
        return urlsplit(url).hostname if url else None
    except ValueError:
        return None


def excel_value(value):
    # Treat browser-controlled strings as text when Excel opens the CSV.
    if isinstance(value, str) and (
        value.startswith(("\t", "\r", "\n"))
        or value.lstrip().startswith(("=", "+", "-", "@", "＝", "＋", "－", "＠"))
    ):
        return "'" + value
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("collection", type=Path, help="Collection directory printed by PowerShell")
    args = parser.parse_args()
    collection = args.collection.resolve()
    databases = sorted(
        path for path in collection.glob("*/*/*/History")
        if path.is_file() and not path.with_name(".incomplete").exists()
    )
    if not databases:
        parser.error(f"No collected History databases under {collection}")
    try:
        eastern = ZoneInfo("America/New_York")
    except ZoneInfoNotFoundError:
        parser.error("Eastern time zone data is missing. Run python -m pip install tzdata.")

    events = []
    incomplete = sorted(collection.glob("*/*/*/.incomplete"))
    for marker in incomplete:
        print(f"Skipping incomplete collection: {marker.parent}", file=sys.stderr)
    failures = len(incomplete)
    for database in databases:
        user, browser, profile, _ = database.relative_to(collection).parts
        try:
            visits = read_visits(database, eastern)
        except (OSError, sqlite3.Error, OverflowError, ValueError) as error:
            print(f"Could not parse {database}: {error}", file=sys.stderr)
            failures += 1
            continue
        for _, event in visits:
            event.update(computer=collection.name.rsplit("-", 1)[0],
                         windows_user=user, browser=browser, profile=profile)
        events.extend(visits)
        print(f"{user} / {browser} / {profile}: {len(visits)} visits")

    if failures == len(databases) + len(incomplete):
        return 1
    events.sort(key=lambda entry: (entry[0] is None, entry[0] or 0))
    rows = [event for _, event in events]
    stem = "browser-history-partial" if failures else "browser-history"
    with (collection / f"{stem}.json").open("w", encoding="utf-8") as output:
        json.dump(rows, output, ensure_ascii=False, indent=2)
        output.write("\n")
    with (collection / f"{stem}.csv").open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(FIELDS)
        writer.writerows([excel_value(row[field]) for field in FIELDS] for row in rows)
    print(f"Exported {len(rows)} visits. Database errors: {failures}.")
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
