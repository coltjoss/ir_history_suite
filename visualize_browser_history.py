"""Create an offline daily activity report from a browser history JSON export."""

import argparse
from collections import defaultdict
from datetime import datetime
from html import escape
import json
from pathlib import Path


def count_visits(events):
    """Use the Eastern wall-clock date and hour already stored in the export."""
    days = defaultdict(lambda: [0] * 24)
    skipped = 0
    for event in events:
        try:
            stamp = datetime.fromisoformat(event["timestamp_et"])
            if stamp.utcoffset() is None:
                raise ValueError("Missing UTC offset")
        except (KeyError, TypeError, ValueError):
            skipped += 1
            continue
        days[stamp.date()][stamp.hour] += 1
    return days, skipped


def day_chart(day, hours, daily_max, hourly_max, expanded):
    total = sum(hours)
    bars = []
    for hour, visits in enumerate(hours):
        label = f"{hour:02d}:00 Eastern, {visits:,} visits"
        bars.append(f"""
          <li aria-label="{label}" title="{label}">
            <div class="track" aria-hidden="true">
              <div class="bar" style="height:{visits / hourly_max:.4%}">
                <span>{visits if visits else ''}</span>
              </div>
            </div>
            <small aria-hidden="true">{f'{hour:02d}:00' if hour % 3 == 0 else ''}</small>
          </li>""")
    return f"""
      <details{' open' if expanded else ''}>
        <summary>
          <span><strong>{day.isoformat()}</strong> <small>{day:%A}</small></span>
          <span class="daily-bar" aria-hidden="true">
            <span style="width:{total / daily_max:.4%}"></span>
          </span>
          <strong class="total">{total:,} visits</strong>
        </summary>
        <p class="scale">Visits per hour · Shared scale 0–{hourly_max:,}</p>
        <div class="plot" role="region" aria-label="Hourly chart for {day}" tabindex="0">
          <ol class="hours" aria-label="Hourly visit counts">{''.join(bars)}</ol>
        </div>
        <p class="axis">Hour of day (Eastern time)</p>
      </details>"""


def render_report(source, days, skipped):
    charts = '<p>No visits with usable timestamps.</p>'
    summary = "0 timed visits"
    if days:
        first, last = min(days), max(days)
        daily_max = max(map(sum, days.values()))
        hourly_max = max(map(max, days.values()))
        busiest = max(sorted(days), key=lambda day: sum(days[day]))
        total = sum(map(sum, days.values()))
        summary = f"{total:,} timed visits · {len(days):,} active days · {first} to {last}"
        charts = "".join(
            day_chart(day, days[day], daily_max, hourly_max, day == busiest)
            for day in sorted(days)
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Browser history activity</title>
<style>
  :root {{
    color-scheme: light dark;
    --line: light-dark(#cbd5e1, #465568);
    --mark: light-dark(#245faa, #82b6ff);
    --quiet: light-dark(#48576a, #bcc8d6);
  }}
  body {{ font: 1rem/1.5 system-ui, sans-serif; max-width: 68rem; margin: 2rem auto; padding: 0 1rem; }}
  h1 {{ margin-bottom: .25rem; }}
  p {{ margin: .35rem 0; }}
  .source, .note, small, .axis, .scale {{ color: var(--quiet); }}
  .source {{ overflow-wrap: anywhere; }}
  .note {{ margin: 1rem 0; }}
  details {{ border-top: 1px solid var(--line); }}
  details:last-child {{ border-bottom: 1px solid var(--line); }}
  summary {{ cursor: pointer; padding: .75rem .25rem; }}
  summary > span:first-child {{ display: inline-block; min-width: 12rem; }}
  summary small {{ margin-left: .3rem; }}
  .daily-bar {{ display: inline-block; width: clamp(3rem, 37%, 25rem); margin-right: .5rem; }}
  .daily-bar span {{ display: block; height: .55rem; background: var(--mark); }}
  .total, .hours {{ font-variant-numeric: tabular-nums; }}
  .scale, .axis {{ font-size: .85rem; }}
  .axis {{ margin-bottom: 1rem; }}
  .plot {{ overflow-x: auto; }}
  .hours {{ list-style: none; display: grid; grid-template-columns: repeat(24, 1fr);
            gap: .3rem; margin: 0; padding: 1.6rem .3rem .2rem; min-width: 44rem; }}
  .track {{ height: 8rem; display: flex; align-items: end; border-bottom: 1px solid var(--line); }}
  .bar {{ width: 100%; position: relative; background: var(--mark); }}
  .bar span {{ position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%);
               font-size: .75rem; white-space: nowrap; }}
  @media (max-width: 36rem) {{
    summary > span:first-child {{ min-width: auto; margin-right: .5rem; }}
    .daily-bar {{ display: none; }}
  }}
</style>
</head>
<body>
<main>
  <h1>Browser history activity</h1>
  <p>{summary}</p>
  <p class="source">Source · {escape(source)} · {skipped:,} rows skipped for missing or invalid timestamps</p>
  <p class="note">Select a date for its hourly chart. Dates with no recorded visits are omitted.
    Hours use Eastern wall-clock time. The repeated hour when clocks fall back is combined.</p>
  <section aria-label="Daily browser activity">{charts}</section>
</main>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path, help="Path to the exported browser history JSON")
    parser.add_argument("-o", "--output", type=Path, help="HTML output path (defaults beside the JSON)")
    args = parser.parse_args()
    output = args.output or args.history.with_name(f"{args.history.stem}-activity.html")
    if output.suffix.lower() not in (".html", ".htm") or output.resolve() == args.history.resolve():
        parser.error("Choose a separate .html or .htm output file.")

    try:
        events = json.loads(args.history.read_text(encoding="utf-8-sig"))
        if not isinstance(events, list):
            parser.error("Expected an exported JSON array of visits.")
        days, skipped = count_visits(events)
        output.write_text(render_report(args.history.name, days, skipped), encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.exit(1, f"Could not create activity report: {error}\n")
    print(f"Saved {output.resolve()} ({len(days):,} active days, {skipped:,} skipped rows)")


if __name__ == "__main__":
    main()
