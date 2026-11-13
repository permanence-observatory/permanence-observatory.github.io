#!/usr/bin/env python3
"""
Count every GKG article of one UTC day (no filter, no model) and add the result as
`gkg_articles` to that day's existing summary file, leaving its other fields as they are.

It is the denominator for the candidates in the daily history, and recovers the days
collected before collect_day.py started counting it. It downloads the same 96 + 96
files as the collector (about 8 min) and counts with the same code (GkgCounter).

Usage:
  python pipeline/count_gkg_day.py --date 2026-11-05
  python pipeline/count_gkg_day.py --date 2026-11-05 --every 32 --dry-run   # quick test, writes nothing
"""

import argparse
import io
import json
import os
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'prototype'))
from gkg_prototype import BASE, C_URL, FEEDS, GkgCounter, download, timestamps  # noqa: E402


def count_day(day, every=1, workers=4):
    """Return (gkg_articles, files_ok, files_missing) for one UTC day."""
    jobs = [(feed, f"{BASE}/{FEEDS[feed].format(ts=ts)}")
            for ts in timestamps(day, every) for feed in FEEDS]
    counter, ok, missing, urls = GkgCounter(), 0, 0, set()
    with ThreadPoolExecutor(workers) as pool:
        for (feed, _), content in zip(jobs, pool.map(lambda j: download(j[1]), jobs)):
            if content is None:
                missing += 1
                continue
            ok += 1
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                text = z.read(z.namelist()[0]).decode('utf-8', 'replace')
            for line in text.split('\n'):
                row = line.split('\t')
                if len(row) >= 27:  # same rule as the collector
                    counter.add(feed, row)
                    urls.add(row[C_URL])
            print(f"  {ok + missing}/{len(jobs)} files, {counter.total} articles", flush=True)
    return {**counter.result(), 'unique_urls': len(urls)}, ok, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', required=True, help='UTC day YYYY-MM-DD')
    ap.add_argument('--every', type=int, default=1, help='use 1 of every N 15-min files (testing only)')
    ap.add_argument('--data', default=os.path.join(ROOT, 'data', 'gkg'))
    ap.add_argument('--dry-run', action='store_true', help='print the result, do not touch the summary')
    ap.add_argument('--force', action='store_true', help='overwrite an existing gkg_articles')
    args = ap.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    path = os.path.join(args.data, args.date[:4], args.date[5:7], f'{args.date}.summary.json')
    if not args.dry_run:
        if args.every != 1:
            sys.exit('--every other than 1 would write a partial count; use it only with --dry-run')
        if not os.path.exists(path):
            sys.exit(f'No summary for {args.date} ({path}): collect the day first')
        with open(path, encoding='utf-8') as f:
            summary = json.load(f)
        if 'gkg_articles' in summary and not args.force:
            sys.exit(f'{path} already has gkg_articles (use --force to replace it)')

    result, ok, missing = count_day(args.date, args.every)
    expected = ok + missing
    print(json.dumps({**result, 'by_language': dict(list(result['by_language'].items())[:8]),
                      'by_country': dict(list(result['by_country'].items())[:8])}, ensure_ascii=False, indent=2))
    print(f'{ok} files ok, {missing} missing')
    if ok == 0 or missing > expected / 4:
        sys.exit(f'{missing} of {expected} GKG files missing: the count would be too low, nothing written')
    if args.dry_run:
        return
    summary['gkg_articles'] = result
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f'Added gkg_articles to {path}')


if __name__ == '__main__':
    main()
