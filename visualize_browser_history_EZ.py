"""Combine nearby browser-history JSON exports into a CSV and an hourly heatmap."""

from collections import defaultdict
import csv
from datetime import datetime
from html import escape
import json
from pathlib import Path
import sys


def load_visits(folder):
    visits = []
    sources = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        try:
            rows = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as error:
            print(f"Skipped {path.name}: {error}", file=sys.stderr)
            continue
        if not isinstance(rows, list) or not all(
            isinstance(row, dict) and {"timestamp_et", "url"} <= row.keys() for row in rows
        ) or (not rows and not path.stem.startswith("browser-history")):
            print(f"Skipped {path.name}: expected a browser-history JSON array.", file=sys.stderr)
            continue
        sources.append(path.name)
        visits.extend((path.name, row) for row in rows)
        print(f"{path.name}: {len(rows):,} visits")
    return visits, sources


def excel_text(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    if isinstance(value, str) and (
        value.startswith(("\t", "\r", "\n"))
        or value.lstrip().startswith(("=", "+", "-", "@", "＝", "＋", "－", "＠"))
    ):
        return "'" + value
    return value


def write_csv(path, visits):
    fields = dict.fromkeys(("timestamp_et", "title", "domain", "url"))
    for _, row in visits:
        fields.update(dict.fromkeys(row))
    source_field = "input_json"
    while source_field in fields:
        source_field += "_"
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.writer(output)
        writer.writerow([source_field, *(excel_text(field) for field in fields)])
        for source, row in visits:
            writer.writerow([excel_text(source), *(excel_text(row.get(field)) for field in fields)])


def render_report(visits, sources):
    days = defaultdict(lambda: [0] * 24)
    skipped = 0
    for _, row in visits:
        try:
            stamp = datetime.fromisoformat(row["timestamp_et"])
            if stamp.utcoffset() is None:
                raise ValueError("Missing UTC offset")
        except (TypeError, ValueError):
            skipped += 1
            continue
        days[stamp.date()][stamp.hour] += 1

    peak = max((max(hours) for hours in days.values()), default=1)
    headings = "".join(f'<th scope="col">{hour:02d}</th>' for hour in range(24))
    rows = []
    for day, hours in sorted(days.items()):
        cells = "".join(
            f'<td class="{"active" if count else "quiet"}" '
            f'style="--strength:{25 + 75 * count / peak:.1f}%">{count or "·"}</td>'
            for count in hours
        )
        rows.append(f'<tr><th scope="row">{day}</th><td><strong>{sum(hours):,}</strong></td>{cells}</tr>')
    table = f"""
      <div class="scroll" role="region" aria-label="Hourly activity table" tabindex="0">
        <table>
          <caption>Recorded visits by date and hour (Eastern Time)</caption>
          <thead><tr><th scope="col">Date</th><th scope="col">Total</th>{headings}</tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>""" if rows else "<p>No visits with usable timestamps.</p>"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Browser history activity</title>
<style>
  body {{ font: 1rem/1.5 system-ui, sans-serif; margin: 2rem auto; max-width: 82rem;
          padding: 0 1rem; color: #172533; background: #fff; }}
  h1 {{ margin-bottom: .25rem; }}
  p {{ margin: .4rem 0 1rem; overflow-wrap: anywhere; }}
  .scroll {{ overflow-x: auto; }}
  table {{ border-collapse: separate; border-spacing: 3px; font-variant-numeric: tabular-nums; }}
  caption {{ text-align: left; font-weight: bold; margin-bottom: .5rem; }}
  th, td {{ text-align: center; padding: .3rem .45rem; white-space: nowrap; }}
  th[scope="row"] {{ text-align: left; }}
  .quiet {{ color: #5b6877; background: #f2f5f9; }}
  .active {{ color: #071e36; background: #a5cff6;
             background: color-mix(in srgb, #8abdf2 var(--strength), #edf6ff); }}
</style>
</head>
<body><main>
  <h1>Browser history activity</h1>
  <p>{len(visits) - skipped:,} timed visits · {len(days):,} active days · {len(sources):,} input files</p>
  {table}
  <p>Darker cells indicate more visits. A dot means zero. Dates without visits are omitted.
     The repeated hour when clocks fall back is combined.</p>
  <p>{skipped:,} visits without a usable timestamp are included only in the CSV.
     Overlapping input files can count the same visit more than once.</p>
  <p>Inputs · {escape(', '.join(sources))}</p>
</main></body>
</html>
"""


def main():
    folder = Path(__file__).resolve().parent
    visits, sources = load_visits(folder)
    if not sources:
        sys.exit(f"No browser-history JSON exports found beside the script in {folder}")

    csv_path = folder / "browser-history-EZ.csv"
    html_path = folder / "browser-history-EZ-activity.html"
    try:
        write_csv(csv_path, visits)
        html_path.write_text(render_report(visits, sources), encoding="utf-8")
    except OSError as error:
        sys.exit(f"Could not write report files: {error}")
    print(f"Saved {len(visits):,} visits to {csv_path}\nSaved activity report to {html_path}")


if __name__ == "__main__":
    main()
